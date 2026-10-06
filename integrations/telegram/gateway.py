"""Telegram-бот JARVIS: единственный интерфейс владелицы.

Слой держит на себе всё телеграмное — апдейты, allow-list, команды, кнопки, отправку —
и ничего не решает сам: текст уходит в `task_router` → `claude_bridge`, думает Claude Code.

Секреты (`.env`) читает только этот модуль; значения никогда не печатаются и не логируются,
а в окружение дочернего `claude` попадают через `claude_bridge.build_env`, который вырезает
Telegram-переменные.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, MessageHandler,
                          filters)

from integrations.telegram import files, outbox, render, voice
from integrations.telegram.status import STATUS_DELAY, StatusReporter, too_long
from runtime import activation
from runtime import schedule as schedule_mod
from runtime import schedule_jobs
from runtime import sessions as sessions_mod
from runtime import task_router, task_state, worker
from runtime.approvals import ApprovalsServer
from runtime.task_router import Job

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("jarvis.telegram")

DEFAULT_OWNER_NAME = "Катерина"   # перекрывается переменной окружения JARVIS_OWNER_NAME


def greeting() -> str:
    """Приветствие при запуске: по имени, а не служебное «JARVIS на связи»."""
    name = (os.environ.get("JARVIS_OWNER_NAME", "") or "").strip() or DEFAULT_OWNER_NAME
    return f"Привет, {name}! На связи Джарвис."
SETUP_HINT = ("Бот в режиме настройки: в .env пуст TELEGRAM_OWNER_ID.\n"
              "Отправь /whoami, впиши показанный номер в .env и перезапусти start.bat.")
VOICE_FAILED = "Ой, не расслышал голосовое 😅 Запиши ещё раз или напиши текстом."
NO_TOKEN = ("Не вижу TELEGRAM_BOT_TOKEN.\n"
            "Создай бота у @BotFather и впиши токен в файл .env рядом со start.bat:\n"
            "TELEGRAM_BOT_TOKEN=...\n"
            "Там же TELEGRAM_OWNER_ID — свой номер подскажет команда /whoami.")
# Меню команд: (команда, подсказка в меню Telegram, пояснение в /help). Меню ставится при старте бота.
COMMANDS = [
    ("today", "Что у нас на сегодня", "утренняя сводка: что ждёт решения, свежая тема, один шаг на сегодня"),
    ("status", "Чем ты сейчас занят", "что делаю, что в очереди и сколько осталось лимита у Claude и Codex"),
    ("stop", "Остановить текущую задачу", "если пошло не туда — я сразу остановлюсь"),
    ("new", "Начать разговор заново", "забываю текущий разговор, начинаем с чистого листа"),
    ("codex", "Работать через Codex", "переключаюсь на Codex, когда у Claude кончается лимит"),
    ("claude", "Вернуться к Claude", "обратно на Claude"),
    ("browser_login", "Войти на сайт в моём браузере", "/browser_login адрес — открою окно, войди сама; пароль я не вижу"),
    ("whoami", "Показать мой Telegram ID", "нужно только при первой настройке бота"),
]
HELP = ("Пиши мне текстом или голосом, присылай фото и файлы — разберёмся 🙂\n\nКоманды:\n"
        + "\n".join(f"/{name} — {about}" for name, _short, about in COMMANDS))

APPROVE_PREFIX = "ap"
CONTENT_PREFIX = "ct"
DRAFT_PREFIX = "df"
SWITCH_PREFIX = "rt"   # «Продолжить в Codex / Подождать» (P4.1e)
DRAFT_POLL_INTERVAL = 10.0   # черновик замечаем в течение десяти секунд после появления
TOKEN_TTL = 24 * 3600.0   # столько живёт кнопка, если её так и не нажали
MAX_TOKENS = 200


# --------------------------------------------------------------------- .env

def load_env(path: str | Path = None) -> dict:
    """Читает .env (KEY=VALUE) в os.environ, не перекрывая уже заданное снаружи.

    Возвращает список прочитанных ключей — без значений: значениям в логах не место.
    """
    path = Path(path) if path else ROOT / ".env"
    keys: dict = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        log.info("файл .env не найден: %s", path.name)
        return keys
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        keys[key] = True
        os.environ.setdefault(key, value)
    log.info("прочитано переменных из .env: %d", len(keys))
    return keys


@dataclass(repr=False)
class Config:
    token: str = ""
    owner_id: int | None = None

    @classmethod
    def from_env(cls) -> "Config":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        raw = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
        owner = int(raw) if raw.lstrip("-").isdigit() else None
        return cls(token=token, owner_id=owner)

    def __repr__(self) -> str:  # чтобы токен и ID не утекли в лог через f-строку
        return (f"Config(token={'задан' if self.token else 'пуст'}, "
                f"owner_id={'задан' if self.owner_id is not None else 'пуст'})")


# --------------------------------------------------------------------- бот

MAX_CODE_FILES_SHOWN = 10


_TODAY_QUESTION = re.compile(r"(что|чем|какие|какой).{0,20}(на сегодня|сегодня)|план на сегодня",
                             re.IGNORECASE)


async def _keep_typing(bot, chat_id, every: float = 4.0) -> None:
    """Telegram гасит «печатает…» через ~5 с, поэтому обновляем; сбой Telegram ход не роняет."""
    send = getattr(bot, "send_chat_action", None)
    if send is None:
        return
    while True:
        try:
            await send(chat_id=chat_id, action="typing")
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(every)


class Gateway:
    """Обработчики апдейтов. Все зависимости подменяемы — поэтому тесты идут без сети."""

    def __init__(self, *, owner_id: int | None, root: str | Path = ROOT, router=None,
                 sessions=None, approvals=None, transcriber=None,
                 min_status_interval: float = 3.0, status_delay: float = STATUS_DELAY):
        self.owner_id = owner_id
        self.root = Path(root)
        self.router = router if router is not None else task_router.default_router()
        self.sessions = sessions if sessions is not None else sessions_mod
        self.approvals = approvals
        self.transcriber = transcriber
        self.min_status_interval = min_status_interval
        self.status_delay = status_delay
        self.bot = None
        # короткий токен кнопки -> (значение, момент создания); чистится после нажатия и по TTL
        self._tokens: dict[str, tuple[str, float]] = {}
        self._counter = 0

    # ---- служебное

    @property
    def setup_mode(self) -> bool:
        return self.owner_id is None

    def attach(self, bot) -> None:
        self.bot = bot

    def _allowed(self, update) -> bool:
        uid = getattr(getattr(update, "effective_user", None), "id", None)
        if self.setup_mode:
            log.info("режим настройки: апдейт от user_id=%s не обработан", uid)
            return False
        if uid != self.owner_id:
            log.info("чужой апдейт: user_id=%s — игнорирую", uid)
            return False
        return True

    def _prune_tokens(self) -> None:
        now = time.monotonic()
        stale = [t for t, (_v, born) in self._tokens.items() if now - born > TOKEN_TTL]
        for tok in stale:
            self._tokens.pop(tok, None)
        while len(self._tokens) > MAX_TOKENS:
            self._tokens.pop(next(iter(self._tokens)))

    def _token_for(self, prefix: str, value: str) -> str:
        self._prune_tokens()
        for tok, (val, _born) in self._tokens.items():
            if tok.startswith(prefix + ":") and val == value:
                return tok
        self._counter += 1
        tok = f"{prefix}:{self._counter:x}"
        self._tokens[tok] = (value, time.monotonic())
        return tok

    def approval_callback_data(self, request_id: str, decision: str) -> str:
        return f"{self._token_for(APPROVE_PREFIX, request_id)}:{decision}"

    def content_callback_data(self, name: str, decision: str) -> str:
        return f"{self._token_for(CONTENT_PREFIX, name)}:{decision}"

    def draft_callback_data(self, kind: str, name: str, decision: str) -> str:
        return f"{self._token_for(DRAFT_PREFIX, f'{kind}:{name}')}:{decision}"

    def switch_callback_data(self, chat_id, decision: str) -> str:
        return f"{self._token_for(SWITCH_PREFIX, str(chat_id))}:{decision}"

    @staticmethod
    async def _send(context, chat_id, text, **kw):
        return await context.bot.send_message(chat_id, text, **kw)

    # ---- команды

    async def cmd_start(self, update, context) -> None:
        # В режиме настройки бот молчит на всё, кроме /whoami: пустой allow-list = никто не свой.
        if not self._allowed(update):
            return
        await self._send(context, update.effective_chat.id, HELP)

    async def cmd_whoami(self, update, context) -> None:
        uid = update.effective_user.id
        if not self.setup_mode and uid != self.owner_id:
            log.info("чужой /whoami: user_id=%s — игнорирую", uid)
            return
        await self._send(context, update.effective_chat.id,
                         f"Твой Telegram ID: {uid}\nВпиши его в .env как TELEGRAM_OWNER_ID.")

    async def cmd_new(self, update, context) -> None:
        if not self._allowed(update):
            return
        self.sessions.reset(update.effective_chat.id)
        await self._send(context, update.effective_chat.id, "Хорошо, начинаем с чистого листа 🙂")

    async def cmd_stop(self, update, context) -> None:
        if not self._allowed(update):
            return
        stopped = self.router.stop(update.effective_chat.id)
        await self._send(context, update.effective_chat.id,
                         "Всё, остановился." if stopped else "Я сейчас ничем не занят — останавливать нечего.")

    async def cmd_status(self, update, context) -> None:
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        # Что делаю, что в очереди и чем кончилась последняя задача — по журналу (P2.4).
        snap = task_state.snapshot(self.root / "state" / "events.jsonl", chat=chat_id)
        text = task_state.describe(snap)
        pending = self.router.pending(chat_id)
        if not snap["active"] and not snap["queued"] and pending:
            text = f"В работе и в очереди: {pending}.\n" + text
        current = worker.current(str(chat_id))
        if current.get("runtime") == "codex":
            until = current.get("until")
            text += "\n\nРаботает: 🟢 Codex" + (f" до {_hhmm(until)}, потом вернусь к Claude" if until else
                                                 " (вернуться к Claude — /claude)")
        else:
            text += "\n\nРаботает: Claude"
        limits = worker.describe_limits()
        if limits:
            text += "\n" + limits
        await self._send(context, chat_id, text)

    async def cmd_today(self, update, context) -> None:
        if not self._allowed(update):
            return
        out = schedule_jobs.morning(self.root, dt.datetime.now())
        await self._send(context, update.effective_chat.id, out.text)

    async def cmd_codex(self, update, context) -> None:
        """Ручное переключение на Codex — до команды /claude."""
        if not self._allowed(update):
            return
        self.router.set_runtime(update.effective_chat.id, "codex")
        await self._send(context, update.effective_chat.id,
                         "Ну вот, дальше работаю через Codex 🟢 Проверки и кнопки те же. Вернуться к Claude — /claude.")

    async def cmd_claude(self, update, context) -> None:
        if not self._allowed(update):
            return
        self.router.set_runtime(update.effective_chat.id, "claude")
        await self._send(context, update.effective_chat.id, "Вернулся к Claude, продолжаем 🙂")

    async def cmd_browser_login(self, update, context) -> None:
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        args = getattr(context, "args", None) or []
        if not args:
            await self._send(context, chat_id, "Напиши адрес сайта, например: /browser_login https://instagram.com")
            return
        script = self.root / "integrations" / "browser" / "login.py"
        if not script.exists():
            await self._send(context, chat_id,
                             "Браузерный вход ещё не установлен: нет integrations/browser/login.py.")
            return
        try:
            subprocess.Popen([sys.executable, "-m", "integrations.browser.login", args[0]],
                             cwd=str(self.root))
        except OSError as exc:
            log.warning("не удалось запустить браузер: %s", type(exc).__name__)
            await self._send(context, chat_id, "Не получилось открыть браузер на компьютере 😕")
            return
        await self._send(context, chat_id,
                         "Открываю окно браузера JARVIS на компьютере. Войди сама и закрой окно — "
                         "пароль я не вижу и не ввожу.")

    # ---- сообщения

    async def on_message(self, update, context) -> None:
        if not self._allowed(update):
            return
        text = (getattr(update.message, "text", None) or "").strip()
        if not text:
            return
        await self._run(update, context, text)

    async def on_voice(self, update, context) -> None:
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        media = update.message.voice or getattr(update.message, "audio", None)
        path = await self._download(context, media.file_id,
                                    f"voice-{getattr(media, 'file_unique_id', 'msg')}.ogg")
        text = voice.transcribe(path, transcriber=self.transcriber) if path else None
        if not text:
            await self._send(context, chat_id, VOICE_FAILED)
            return
        await self._send(context, chat_id, f"🎙 Услышал так: {text}")
        await self._run(update, context, text)

    async def on_file(self, update, context) -> None:
        if not self._allowed(update):
            return
        chat_id = update.effective_chat.id
        msg = update.message
        doc = getattr(msg, "document", None)
        if doc is not None:
            file_id = doc.file_id
            name = getattr(doc, "file_name", None) or f"file-{doc.file_unique_id}"
        elif getattr(msg, "photo", None):
            photo = msg.photo[-1]
            file_id, name = photo.file_id, f"photo-{photo.file_unique_id}.jpg"
        else:
            return
        path = await self._download(context, file_id, name)
        if path is None:
            await self._send(context, chat_id, "Не получилось сохранить файл 😕 Пришли, пожалуйста, ещё раз.")
            return
        caption = (getattr(msg, "caption", None) or "").strip()
        prompt = (f"{caption}\n\n" if caption else "") + f"Файл от владелицы: {path}"
        await self._run(update, context, prompt)

    async def _download(self, context, file_id: str, name: str) -> Path | None:
        path = files.reserve_path(self.root, name)
        try:
            tg_file = await context.bot.get_file(file_id)
            await tg_file.download_to_drive(str(path))
        except Exception as exc:  # noqa: BLE001 — сеть Telegram не должна ронять бота
            log.warning("не удалось скачать файл: %s", type(exc).__name__)
            path.unlink(missing_ok=True)   # занятое имя освобождаем, пустышку не оставляем
            return None
        return path

    # ---- ход агента

    async def _run(self, update, context, prompt: str, task: str = "", runtime: str | None = None) -> None:
        chat_id = update.effective_chat.id
        if _TODAY_QUESTION.search(prompt) and len(prompt) <= 60:
            # «что на сегодня» — Python отвечает сам, мгновенно и без лимита (её жалоба 2026-10-06: долго и технично)
            out = schedule_jobs.morning(self.root, dt.datetime.now())
            await self._send(context, chat_id, out.text)
            return
        task = task or _task_name(prompt)
        runtime_for = getattr(self.router, "runtime_for", None)
        codex = (runtime or (runtime_for(chat_id) if runtime_for else "claude")) == "codex"
        reporter = StatusReporter(context.bot, chat_id, task=("🟢 Codex · " + task) if codex else task,
                                  min_interval=self.min_status_interval,
                                  start_after=self.status_delay)

        async def on_event(ev):
            reporter.note(ev)
            await reporter.update()

        # uses_browser не угадывается по словам: угадав, ход занял бы глобальный браузерный
        # замок и заблокировал чужие задачи. Факт использования браузера виден только по ходу.
        job = Job(prompt=prompt, task=task, uses_browser=False, on_event=on_event, runtime=runtime)
        position = self.router.submit(chat_id, job)
        if position:
            # Статус-сообщение не создаём: оно появится, когда ход реально начнётся.
            await self._send(context, chat_id, self._queued_text(chat_id, position))
        typing = asyncio.ensure_future(_keep_typing(context.bot, chat_id))   # «печатает…» пока работаю
        try:
            result = await job.result
        finally:
            typing.cancel()
        # Статус-карточка уходит из чата вместе с концом хода; итоговая строка нужна только
        # репортёру с выключенным удалением (`delete_on_finish=False`).
        await reporter.finish(_final_line(result, reporter))
        await self._deliver(context, chat_id, result)

    async def _deliver(self, context, chat_id, result) -> None:
        try:
            await self._deliver_inner(context, chat_id, result)
        except Exception as exc:  # noqa: BLE001 — сбой Telegram не должен ронять ход
            log.warning("не удалось доставить ответ: %s", type(exc).__name__)
            try:
                await self._send(context, chat_id,
                                 "Ответ у меня готов, но Telegram его не принял 😕 "
                                 "Попроси ещё раз — или загляни в state/events.jsonl, там видно, что случилось.")
            except Exception:  # noqa: BLE001 — молчание лучше падения бота
                log.warning("не удалось сообщить о неудачной отправке")

    def _queued_text(self, chat_id, position: int) -> str:
        """Её поправка 2026-10-05: не «в очереди: 4», а чем занят и что можно сделать."""
        try:
            active = task_state.snapshot(self.root / "state" / "events.jsonl", chat=chat_id)["active"]
        except Exception:  # noqa: BLE001
            active = None
        busy = f"задачей «{active['task']}»" if active and active.get("task") else "другой задачей"
        if position <= 1:
            return f"Секунду, я ещё занят {busy} — сразу после неё займусь твоим сообщением."
        return (f"Секунду, я ещё занят {busy}, а перед твоим сообщением есть ещё {position - 1}. Отвечу, как только дойду до него. "
                "Посмотреть, что делаю, — /status, остановить — /stop.")

    def _offer_text(self, offer: dict) -> str:
        reset = offer.get("resets_at")
        lines = ["⏳ У Claude закончился лимит" + (f", обновится в {_hhmm(reset)}." if reset else ".")]
        files = offer.get("files") or []
        lines.append(f"Задача «{offer.get('task') or 'задача'}» не доделана"
                     + (": уже изменены " + ", ".join(files[:5]) + ("…" if len(files) > 5 else "") + "." if files else "."))
        lines.append("Могу передать Codex — он получит сводку и доделает, проверки и кнопки те же. Как тебе?")
        return "\n".join(lines)

    def _switch_keyboard(self, chat_id, offer: dict) -> InlineKeyboardMarkup:
        reset = offer.get("resets_at")
        wait = f"Подождать до {_hhmm(reset)}" if reset else "Подождать час"
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Продолжить в Codex", callback_data=self.switch_callback_data(chat_id, "codex")),
            InlineKeyboardButton(wait, callback_data=self.switch_callback_data(chat_id, "wait")),
        ]])

    async def _switch_action(self, update, context, query, chat: str, decision: str) -> None:
        if decision == "codex":
            job = self.router.offer_job(chat)
            if job is None:
                await query.edit_message_text(text="Это предложение уже неактуально.", reply_markup=None)
                return
            await query.edit_message_text(text="Хорошо, продолжаю в Codex 🟢", reply_markup=None)
            await self._run(update, context, job.prompt, task=job.task, runtime="codex")
            return
        offer = worker.load_offer(chat)
        if not offer:
            await query.edit_message_text(text="Это предложение уже неактуально.", reply_markup=None)
            return
        at = offer.get("resets_at") or (time.time() + 3600)
        worker.defer(chat, at=at, prompt=offer.get("prompt", ""), task=offer.get("task") or "задача")
        worker.drop_offer(chat)
        await query.edit_message_text(text=f"Договорились, подожду. В {_hhmm(at)} продолжу в Claude и напишу тебе.", reply_markup=None)

    async def check_deferred(self, now: float | None = None) -> list[str]:
        """«Подождать»: задачи, чьё время пришло, — в Claude, ответ придёт как обычный."""
        if self.bot is None or self.owner_id is None:
            return []
        started = []
        for item in worker.due_deferred(now):
            job = Job(prompt=item["prompt"], task=item["task"], uses_browser=False, on_event=_ignore_event,
                      runtime="claude")
            if not hasattr(self, "_schedule_runs"):
                self._schedule_runs = []
            self._schedule_runs.append(asyncio.ensure_future(self._run_scheduled(job)))
            started.append(item["task"])
        return started

    async def _deliver_inner(self, context, chat_id, result) -> None:
        if getattr(result, "switched_back", False) is True:
            await self._send(context, chat_id, "Лимит у Claude восстановился, так что возвращаюсь к нему 🙂")
        offer = getattr(result, "switch_offer", None)
        if isinstance(offer, dict):
            await self._send(context, chat_id, self._offer_text(offer),
                             reply_markup=self._switch_keyboard(chat_id, offer))
            return
        if getattr(result, "brief", False) is True:
            pass   # новый разговор после паузы — служебная кухня, ей это не нужно (её поправка 2026-10-06)
        elif getattr(result, "new_session", False):
            await self._send(context, chat_id,
                             "Не смог подхватить прошлый разговор и начал заново 😅 Если что-то важное из него нужно — напомни.")
        raw = (getattr(result, "text", "") or "").strip()
        if not raw:
            return
        # Строки «📎 <путь>» — не текст для владелицы, а инструкция боту прислать файл;
        # из показанного текста их убираем до разметки и до поиска черновика комплекта.
        text, attachments = files.extract_attachments(raw)
        text = text.strip()
        if text:
            # Ответ агента — markdown; владелице он уходит оформленным (render), а в файл
            # кладётся исходный markdown: файл она открывает и правит, теги там лишние.
            parts = render.prepare(text)
            # Порог «лентой или файлом» считается по готовым к отправке кускам HTML, а не по
            # markdown-кускам: владелице важно число сообщений в чате, а оно берётся отсюда.
            if too_long(parts):
                stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
                await context.bot.send_document(
                    chat_id, document=text.encode("utf-8"), filename=f"answer-{stamp}.md",
                    caption="Получилось длинно, поэтому весь ответ — в файле.")
            else:
                for part in parts:
                    if part.strip():
                        await render.send(context.bot, chat_id, part)
        if attachments:
            await self._send_attachments(context, chat_id, attachments)
        bundle = files.find_content_bundle(text, self.root)
        if bundle:
            await self._send(context, chat_id, "Черновик готов — посмотри и скажи, что с ним делать.",
                             reply_markup=self._content_keyboard(bundle))

    async def _send_attachments(self, context, chat_id, raw_paths: list[str]) -> None:
        """Отправляет файлы, названные агентом строками «📎 <путь>» — без пережатия.

        Плохой файл не мешает остальным: причина отказа уходит одной строкой,
        остальные вложения всё равно доставляются.
        """
        for i, raw in enumerate(raw_paths):
            name = Path(raw.strip()).name or raw.strip() or "(пусто)"
            if i >= files.ATTACH_MAX_FILES:
                await self._send(context, chat_id,
                                 f"Не получилось прислать {name}: больше {files.ATTACH_MAX_FILES} файлов за раз")
                continue
            try:
                path = files.resolve_attachment(self.root, raw)
            except ValueError as exc:
                await self._send(context, chat_id, f"Не получилось прислать {name}: {exc}")
                continue
            try:
                with open(path, "rb") as fh:
                    await context.bot.send_document(chat_id, document=fh, filename=path.name)
            except Exception as exc:  # noqa: BLE001 — сбой одного файла не должен ронять остальные
                log.warning("не удалось отправить вложение %s: %s", path.name, type(exc).__name__)
                await self._send(context, chat_id, f"Не получилось прислать {path.name}: Telegram не принял")

    # ---- кнопки

    def _content_keyboard(self, name: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Принято", callback_data=self.content_callback_data(name, "accepted")),
            InlineKeyboardButton("Переделать", callback_data=self.content_callback_data(name, "redo")),
            InlineKeyboardButton("Опубликовано", callback_data=self.content_callback_data(name, "published")),
        ]])

    def _approval_keyboard(self, request_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Подтвердить", callback_data=self.approval_callback_data(request_id, "allow")),
            InlineKeyboardButton("Отклонить", callback_data=self.approval_callback_data(request_id, "deny")),
        ]])

    async def on_approval_request(self, request_id, level, tool, summary, details) -> None:
        """Подписка на approvals.on_request: показать владелице, что именно произойдёт."""
        if self.bot is None or self.owner_id is None:
            log.warning("некому показать запрос подтверждения (%s)", level)
            return
        mark = "💸" if level == "MONEY" else "🌐"
        text = f"{mark} {summary}\n\nМожно, я это сделаю?"
        try:
            await self.bot.send_message(self.owner_id, text,
                                        reply_markup=self._approval_keyboard(request_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("не удалось отправить запрос подтверждения: %s", type(exc).__name__)

    # ---- черновики навыков и помощников

    def _draft_keyboard(self, kind: str, name: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Активировать", callback_data=self.draft_callback_data(kind, name, "on")),
            InlineKeyboardButton("Посмотреть", callback_data=self.draft_callback_data(kind, name, "show")),
            InlineKeyboardButton("Удалить черновик", callback_data=self.draft_callback_data(kind, name, "rm")),
        ]])

    def _draft_confirm_keyboard(self, kind: str, name: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Да, удалить", callback_data=self.draft_callback_data(kind, name, "rm2")),
            InlineKeyboardButton("Отмена", callback_data=self.draft_callback_data(kind, name, "no")),
        ]])

    @staticmethod
    def _draft_text(draft) -> str:
        head = "Новый навык" if draft.kind == "skill" else "Новый помощник"
        mark = {"passed": "Тест: пройден", "failed": "Тест: не пройден"}.get(
            draft.test_status, "Тест: не прогонялся")
        lines = [f"{head} {draft.name}: {draft.description or '(без описания)'}", mark]
        if draft.problems:
            lines.append("Проверка не пройдена: " + "; ".join(draft.problems))
        if getattr(draft, "code_files", None):
            # Включая навык, она включает и код, который JARVIS будет запускать.
            lines.append("⚠️ В навыке есть код — JARVIS будет его запускать: "
                         + ", ".join(draft.code_files) + ". Посмотри его перед включением.")
        return "\n".join(lines)

    def _seen_path(self) -> Path:
        return self.root / "state" / "drafts-seen.json"

    def _load_seen(self) -> set:
        try:
            data = json.loads(self._seen_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return set(data) if isinstance(data, list) else set()

    def _save_seen(self, seen: set) -> None:
        # Одна операция на файл: опрос и нажатие кнопки могут совпасть по времени,
        # а половина записанного набора хуже устаревшей.
        path = self._seen_path()
        tmp = path.with_suffix(".json.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("не смог запомнить показанные черновики: %s", type(exc).__name__)

    def _forget_draft(self, key: str) -> None:
        """Черновик исчез (включён или удалён) — снова появится под тем же именем, снова покажем."""
        seen = self._load_seen()
        if key in seen:
            seen.discard(key)
            self._save_seen(seen)

    async def check_drafts(self) -> list:
        """Один опрос drafts/: о каждом новом черновике сообщаем владелице ровно раз."""
        if self.bot is None or self.owner_id is None:
            return []
        seen = self._load_seen()
        fresh = []
        for draft in activation.list_drafts(self.root):
            key = f"{draft.kind}:{draft.name}"
            if key in seen:
                continue
            try:
                await self.bot.send_message(
                    self.owner_id, self._draft_text(draft),
                    reply_markup=self._draft_keyboard(draft.kind, draft.name))
            except Exception as exc:  # noqa: BLE001 — не отметим показанным, покажем в следующий раз
                log.warning("не удалось показать черновик %s: %s", key, type(exc).__name__)
                continue
            seen.add(key)
            fresh.append(draft)
        if fresh:
            self._save_seen(seen)
        return fresh

    async def check_outbox(self) -> int:
        """Письма из `state/outbox/` (задачи по расписанию) — владелице; ушедшие переносятся в sent/."""
        if self.bot is None or self.owner_id is None:
            return 0
        delivered = 0
        for path in outbox.pending(self.root):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            text, attachments = files.extract_attachments(raw)
            try:
                for part in render.prepare(text.strip()):
                    if part.strip():
                        await render.send(self.bot, self.owner_id, part)
            except Exception as exc:  # noqa: BLE001 — письмо остаётся и уйдёт на следующем опросе
                log.warning("письмо %s не ушло: %s", path.name, type(exc).__name__)
                continue
            if attachments:
                await self._send_attachments(_BotContext(self.bot), self.owner_id, attachments)
            outbox.mark_sent(path)
            delivered += 1
        return delivered

    async def check_schedule(self, now: dt.datetime | None = None) -> list[str]:
        """Задачи `runtime/schedule.json`, которым пора: слот отмечается ДО запуска (дважды не пойдёт),
        ход идёт фоном от имени владелицы, ответ приходит ей как обычный ответ JARVIS."""
        if self.bot is None or self.owner_id is None:
            return []
        now = now or dt.datetime.now()
        started = []
        state = schedule_mod.load_state(self.root)
        for task, slot in schedule_mod.due_tasks(now, self.root):
            handler = task.get("handler")
            prompt = "" if handler else schedule_mod.prompt_for(task, self.root).strip()
            if not prompt and not handler:
                continue
            state[task["id"]] = slot.isoformat()
            schedule_mod.save_state(state, self.root)
            if handler:   # делает Python; Claude — только если обработчик вернул задание
                self._schedule_runs = getattr(self, "_schedule_runs", [])
                self._schedule_runs.append(asyncio.ensure_future(self._run_handler(task, slot, now)))
                started.append(task["id"])
                continue
            header = (f"Это задача по расписанию «{task['id']}» ({slot:%Y-%m-%d %H:%M}), владелица сейчас "
                      "ничего не писала. Твой ответ уйдёт ей в Telegram как есть.\n\n")
            minutes = task.get("timeout_min")
            # Фон идёт без её истории (isolated): не растит и не путает разговор в чате.
            job = Job(prompt=header + prompt, task=f"по расписанию: {task['id']}", uses_browser=False,
                      on_event=_ignore_event,   # статус-карточку для фоновой задачи не показываем
                      context="isolated", timeout_sec=float(minutes) * 60 if minutes else None,
                      browser=False,      # расписанию браузер не нужен: минус ~17 тыс. токенов на ход
                      queue="schedule")   # своя очередь: долгий радар не задерживает её сообщения
            if not hasattr(self, "_schedule_runs"):
                self._schedule_runs = []
            self._schedule_runs.append(asyncio.ensure_future(self._run_scheduled(job)))
            started.append(task["id"])
        return started

    async def _run_handler(self, task: dict, slot: dt.datetime, now: dt.datetime) -> None:
        """Задача на Python: письмо уходит через почтовый ящик; задание Claude — обычным фоновым ходом."""
        try:
            out = await asyncio.to_thread(schedule_jobs.run, task["handler"], self.root, now)
        except Exception as exc:  # noqa: BLE001 — сбой расписания не роняет бота
            log.warning("задача по расписанию %s не выполнилась: %s", task["id"], type(exc).__name__)
            return
        if out.prompt:
            header = (f"Это задача по расписанию «{task['id']}» ({slot:%Y-%m-%d %H:%M}), владелица сейчас "
                      "ничего не писала. Твой ответ уйдёт ей в Telegram как есть.\n\n")
            minutes = task.get("timeout_min")
            job = Job(prompt=header + out.prompt, task=f"по расписанию: {task['id']}", uses_browser=False,
                      on_event=_ignore_event, context="isolated", browser=False, queue="schedule",
                      timeout_sec=float(minutes) * 60 if minutes else None)
            await self._run_scheduled(job)
        elif out.text:
            outbox.post(self.root, out.text, out.files)

    async def _run_scheduled(self, job) -> None:
        try:
            self.router.submit(self.owner_id, job)
            result = await job.result
        except Exception as exc:  # noqa: BLE001 — сбой расписания не роняет бота
            log.warning("задача по расписанию %s не выполнилась: %s", job.task, type(exc).__name__)
            return
        await self._deliver(_BotContext(self.bot), self.owner_id, result)

    async def schedule_tasks_done(self) -> None:
        """Дождаться запущенных задач по расписанию (нужно тестам и мягкой остановке)."""
        runs = getattr(self, "_schedule_runs", [])
        if runs:
            await asyncio.gather(*runs, return_exceptions=True)
        self._schedule_runs = []

    async def watch_drafts(self, interval: float = DRAFT_POLL_INTERVAL, sleep=None) -> None:
        """Фоновый опрос. Сон подменяем в тестах — ждать по-настоящему там незачем."""
        sleep = sleep or asyncio.sleep
        while True:
            await sleep(interval)
            try:
                await self.check_drafts()
            except Exception as exc:  # noqa: BLE001 — наблюдение не должно ронять бота
                log.warning("опрос черновиков не удался: %s", type(exc).__name__)
            try:
                await self.check_outbox()
            except Exception as exc:  # noqa: BLE001
                log.warning("опрос почтового ящика не удался: %s", type(exc).__name__)
            try:
                await self.check_schedule()
            except Exception as exc:  # noqa: BLE001
                log.warning("проверка расписания не удалась: %s", type(exc).__name__)
            try:
                await self.check_deferred()
            except Exception as exc:  # noqa: BLE001
                log.warning("отложенные задачи не запустились: %s", type(exc).__name__)

    async def _draft_action(self, query, token: str, value: str, decision: str) -> None:
        kind, _, name = value.partition(":")
        if decision == "on":
            try:
                activation.activate(kind, name, self.root)
            except activation.ActivationError as exc:
                await query.edit_message_text(text=f"Не включил {name}: {exc}", reply_markup=None)
                return
            self._tokens.pop(token, None)
            self._forget_draft(value)
            word = "Навык" if kind == "skill" else "Помощник"
            await query.edit_message_text(
                text=f"{word} {name} включён — доступен со следующего хода.", reply_markup=None)
        elif decision == "show":
            await self._show_draft(query, kind, name)
        elif decision == "rm":
            await query.edit_message_text(
                text=f"Удалить черновик {name}? Вернуть его будет нельзя.",
                reply_markup=self._draft_confirm_keyboard(kind, name))
        elif decision == "rm2":
            try:
                gone = activation.discard(kind, name, self.root)
            except activation.ActivationError as exc:
                await query.edit_message_text(text=f"Не удалил: {exc}", reply_markup=None)
                return
            self._tokens.pop(token, None)
            self._forget_draft(value)
            await query.edit_message_text(
                text=(f"Удалил черновик {name}." if gone else f"Черновика {name} уже нет."),
                reply_markup=None)
        elif decision == "no":
            await query.edit_message_text(text=f"Оставил черновик {name}.",
                                          reply_markup=self._draft_keyboard(kind, name))

    async def _show_draft(self, query, kind: str, name: str) -> None:
        path = activation.draft_path(kind, name, self.root)
        if kind == "skill":
            # TEST.md — половина решения: по нему видно, что навык вообще проверяли.
            docs = [(path / "SKILL.md", f"{name}-SKILL.md"),
                    (path / "TEST.md", f"{name}-TEST.md")]
            # Код навыка — тоже на просмотр: включая навык, она включает и его.
            docs += [(path / rel, f"{name}-{rel.replace('/', '-')}")
                     for rel in activation.code_files(kind, name, self.root)[:MAX_CODE_FILES_SHOWN]]
        else:
            docs = [(path, f"{name}.md")]
        sent = 0
        for doc, filename in docs:
            try:
                data = doc.read_bytes()
            except OSError:
                continue
            try:
                await self.bot.send_document(self.owner_id, document=data, filename=filename,
                                             caption=f"Черновик {name} — решай, включать ли.")
            except Exception as exc:  # noqa: BLE001
                log.warning("не удалось отправить черновик: %s", type(exc).__name__)
                return
            sent += 1
        if not sent:
            await query.edit_message_text(text=f"Не нашёл черновик {name} — похоже, его уже нет.",
                                          reply_markup=None)

    async def on_callback(self, update, context) -> None:
        query = update.callback_query
        uid = getattr(getattr(query, "from_user", None), "id", None)
        if self.setup_mode or uid != self.owner_id:
            log.info("чужое нажатие кнопки: user_id=%s — игнорирую", uid)
            await query.answer("Недоступно.")
            return
        await query.answer()
        data = query.data or ""
        prefix, _, rest = data.partition(":")
        token_id, _, decision = rest.partition(":")
        token = f"{prefix}:{token_id}"
        entry = self._tokens.get(token)
        if entry is None:
            await query.edit_message_text(text="Эта кнопка уже не работает — запрос устарел.",
                                          reply_markup=None)
            return
        value = entry[0]
        if prefix == APPROVE_PREFIX:
            self._tokens.pop(token, None)   # подтверждение одноразовое
            await self._resolve_approval(query, value, decision)
        elif prefix == CONTENT_PREFIX:
            await self._mark_content(query, value, decision)
        elif prefix == DRAFT_PREFIX:
            await self._draft_action(query, token, value, decision)
        elif prefix == SWITCH_PREFIX:
            self._tokens.pop(token, None)   # выбор одноразовый
            await self._switch_action(update, context, query, value, decision)
        self._prune_tokens()

    async def _resolve_approval(self, query, request_id: str, decision: str) -> None:
        if decision not in ("allow", "deny"):
            return
        if self.approvals is None or not self.approvals.resolve(request_id, decision):
            await query.edit_message_text(
                text="Запрос уже неактуален: Claude его снял (истёк или отменён).",
                reply_markup=None)
            return
        word = "Подтверждено" if decision == "allow" else "Отклонено"
        await query.edit_message_text(text=f"{word}.", reply_markup=None)

    async def _mark_content(self, query, name: str, decision: str) -> None:
        try:
            label = files.mark_content(self.root, name, decision)
        except (FileNotFoundError, ValueError):
            await query.edit_message_text(text="Не нашёл этот комплект на диске.",
                                          reply_markup=None)
            return
        await query.edit_message_text(text=f"Отмечено: {label}.", reply_markup=None)

    # ---- регистрация и старт

    def register(self, app) -> None:
        app.add_handler(CommandHandler(["start", "help"], self.cmd_start))
        app.add_handler(CommandHandler("whoami", self.cmd_whoami))
        app.add_handler(CommandHandler("new", self.cmd_new))
        app.add_handler(CommandHandler("stop", self.cmd_stop))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("today", self.cmd_today))
        app.add_handler(CommandHandler("codex", self.cmd_codex))
        app.add_handler(CommandHandler("claude", self.cmd_claude))
        app.add_handler(CommandHandler("browser_login", self.cmd_browser_login))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, self.on_file))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))
        app.add_handler(CallbackQueryHandler(self.on_callback))

    async def announce(self) -> None:
        if self.bot is None or self.owner_id is None:
            log.warning("%s", SETUP_HINT)
            return
        try:
            await self.bot.send_message(self.owner_id, greeting())
        except Exception as exc:  # noqa: BLE001
            log.warning("не удалось поздороваться: %s", type(exc).__name__)


# --------------------------------------------------------------------- вспомогательное

async def _ignore_event(ev) -> None:
    """События хода фоновой задачи никуда не идут — ей не нужна карточка «думаю…»."""


@dataclass
class _BotContext:
    """То же, что telegram `context`, для отправки вне хода: `_send_attachments` берёт из него `.bot`."""
    bot: object


def _hhmm(epoch) -> str:
    try:
        return dt.datetime.fromtimestamp(float(epoch)).strftime("%H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "?"


def _task_name(prompt: str) -> str:
    first = (prompt or "").strip().splitlines()[0] if prompt.strip() else "задача"
    return first[:40]


def _final_line(result, reporter) -> str:
    from integrations.telegram.status import human_elapsed
    elapsed = human_elapsed(reporter.clock() - reporter.started)
    status = getattr(result, "status", "ok")
    if status == "stopped":
        return f"⏹ Остановлено ({elapsed})."
    if status == "timeout":
        return f"⏱ Остановлено по пределу времени ({elapsed})."
    if status == "ok":
        return f"✅ Готово за {elapsed}."
    return f"⚠️ Ход завершился со статусом {status} ({elapsed})."


# --------------------------------------------------------------------- запуск

def run(config: Config | None = None) -> int:
    """Поднимает Approvals API и бота (polling). Блокирует до Ctrl+C."""
    config = config or Config.from_env()
    approvals = ApprovalsServer()
    gw = Gateway(owner_id=config.owner_id, approvals=approvals)

    watcher: asyncio.Task | None = None

    async def post_init(app: Application) -> None:
        nonlocal watcher
        gw.attach(app.bot)
        try:   # меню команд в Telegram: кнопка «Меню» рядом со строкой ввода
            await app.bot.set_my_commands([BotCommand(n, short) for n, short, _ in COMMANDS])
        except Exception as exc:  # noqa: BLE001 — без меню бот работает
            log.warning("не удалось поставить меню команд: %s", type(exc).__name__)
        approvals.on_request(gw.on_approval_request)
        port = await approvals.start(ROOT)
        log.info("Approvals API слушает 127.0.0.1:%s", port)
        # Папки заводим до первого черновика: новая .claude/agents/ требует перезапуска Claude Code.
        activation.ensure_dirs(ROOT)
        watcher = asyncio.create_task(gw.watch_drafts())
        await gw.announce()

    async def post_shutdown(app: Application) -> None:
        if watcher is not None:
            watcher.cancel()
        await approvals.stop()

    # concurrent_updates: пока ход ждёт её кнопку «Подтвердить», /stop или /status, эти апдейты должны
    # обрабатываться, а не стоять в очереди за ходом. Порядок задач чата держит очередь task_router.
    app = (Application.builder().token(config.token).concurrent_updates(True)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    gw.register(app)
    log.info("JARVIS запущен, режим настройки: %s", gw.setup_mode)
    app.run_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
    return 0


def main(argv: list[str] | None = None, env_path: str | Path | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_env(env_path)
    config = Config.from_env()
    if not config.token:
        print(NO_TOKEN)
        return 2
    if shutil.which("claude") is None:
        print("Не вижу claude в PATH: установи Claude Code и войди в него "
              "(в терминале claude, затем /login) — иначе агент не сможет думать.")
    if config.owner_id is None:
        print("TELEGRAM_OWNER_ID пуст — бот стартует в режиме настройки: "
              "напиши ему /whoami и впиши показанный номер в .env.")
    try:
        return run(config)
    except KeyboardInterrupt:
        return 0
