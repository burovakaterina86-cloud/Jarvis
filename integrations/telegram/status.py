"""Одно редактируемое статус-сообщение и разбиение длинных ответов.

Статус редактируется не чаще раза в `min_interval` секунд (по умолчанию 3 с) —
Telegram ограничивает частоту правок, а владелице важен не каждый кадр, а ход работы.

Статус-сообщение появляется только на ходах длиннее `start_after` секунд, а в конце хода
удаляется: на коротком ходе карточка «⚙️ JARVIS … Этап: принял задачу … ⏱ 0 с» успевала
только замусорить переписку, и владелица попросила её убрать. До порога события копятся
в репортёре, и первая же карточка показывает актуальный этап, а не «принял задачу».
"""
from __future__ import annotations

import time

TELEGRAM_LIMIT = 4096
MAX_MESSAGES = 3          # больше — отправляем документом
FENCE = "```"
LONG_AFTER = 60.0         # после минуты честно говорим, что задача большая
STATUS_DELAY = 6.0        # короче — ход кончится раньше, чем владелица успеет заглянуть в статус


# ------------------------------------------------------------------ разбиение

def _hard_split(line: str, size: int) -> list[str]:
    if len(line) <= size:
        return [line]
    return [line[i:i + size] for i in range(0, len(line), size)]


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Режет текст на куски ≤ limit по строкам, не разрывая ``` блоки.

    Кусок, оборвавшийся внутри блока кода, закрывается ```, следующий — открывается тем же
    заголовком блока, поэтому подсветка не растекается на весь остаток ответа.
    """
    text = text or ""
    if len(text) <= limit:
        return [text]
    reserve = len(FENCE) + 1
    max_line = max(1, limit - reserve - 16)
    parts: list[str] = []
    cur: list[str] = []
    cur_len = 0
    fence: str | None = None

    def flush() -> None:
        nonlocal cur, cur_len
        if not cur:
            return
        chunk = "\n".join(cur)
        if fence is not None:
            chunk += "\n" + FENCE
        parts.append(chunk)
        cur = []
        cur_len = 0

    for raw in text.split("\n"):
        for line in _hard_split(raw, max_line):
            if not cur and fence is not None:
                cur.append(fence)
                cur_len = len(fence)
            add = len(line) + (1 if cur else 0)
            need = reserve if fence is not None else 0
            if cur and cur_len + add + need > limit:
                flush()
                if fence is not None:
                    cur.append(fence)
                    cur_len = len(fence)
                add = len(line) + (1 if cur else 0)
            cur.append(line)
            cur_len += add
            if line.strip().startswith(FENCE):
                fence = None if fence is not None else line.strip()
    flush()
    return parts or [""]


def too_long(parts: list[str]) -> bool:
    """True — ответ стоит отправить документом, а не лентой сообщений."""
    return len(parts) > MAX_MESSAGES


# ------------------------------------------------------------------ статус

def human_elapsed(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} с"
    return f"{seconds // 60}:{seconds % 60:02d}"


_TOOL_PHRASES = {
    "Bash": "Смотрю файлы", "PowerShell": "Смотрю файлы", "Read": "Смотрю файлы", "Glob": "Ищу нужный файл",
    "Grep": "Ищу нужный файл", "Write": "Пишу файл", "Edit": "Пишу файл", "MultiEdit": "Пишу файл",
    "apply_patch": "Пишу файл", "WebSearch": "Ищу в интернете", "WebFetch": "Читаю страницу",
    "Skill": "Беру нужный навык", "Agent": "Прошу помощника", "Task": "Прошу помощника",
}


class StatusReporter:
    """Одно сообщение на ход: этап, инструмент, время. Редактируется с троттлингом."""

    def __init__(self, bot, chat_id, *, task: str = "", min_interval: float = 3.0,
                 start_after: float = STATUS_DELAY, delete_on_finish: bool = True,
                 clock=time.monotonic):
        self.bot = bot
        self.chat_id = chat_id
        self.task = task
        self.min_interval = float(min_interval)
        self.start_after = float(start_after)
        self.delete_on_finish = bool(delete_on_finish)
        self.clock = clock
        self.message_id = None
        self._begun = False
        self._created = False   # ставится ДО первого await: два события подряд не создадут два статуса
        self.stage = "принял задачу"
        self.tool: str | None = None
        self.blocked: str | None = None
        self.started = clock()
        self._last_edit = self.started
        self._last_text: str | None = None

    # ---- сборка текста

    def text(self) -> str:
        """Живая реплика вместо карточки с этапами: что делаю и что скоро отвечу."""
        mark = "🟢 Codex · " if self.task.startswith("🟢 Codex") else ""
        if self.blocked:
            line = "это действие мне не разрешено, ищу другой путь"
        elif self.tool:
            doing = _TOOL_PHRASES.get(self.tool, "Работаю")
            line = f"{doing[0].lower()}{doing[1:]}, скоро отвечу"
        else:
            line = "минутку, думаю — скоро дам ответ 🙂"
        line = line[0].upper() + line[1:]
        text = f"💭 {mark}{line}"
        if self.clock() - self.started >= LONG_AFTER:
            text += "\nЗадача большая, это займёт несколько минут — я на связи ☕"
        return text

    # ---- приём событий stream-json

    def note(self, ev: dict) -> None:
        if not isinstance(ev, dict):
            return
        etype, sub = ev.get("type"), ev.get("subtype")
        if etype == "system" and sub == "init":
            self.stage = "думаю"
        elif etype == "system" and sub == "api_retry":
            self.stage = "жду ответа Claude"
        elif etype == "rate_limit_event":
            self.stage = "жду обновления лимита подписки"
        elif etype == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    self.tool = block.get("name")
                    self.stage = "работаю"
                elif block.get("type") == "text":
                    self.stage = "думаю"
        elif etype == "user":
            self.stage = "разбираю результат"
        elif etype == "result":
            self.stage = "готово"

    def note_blocked(self, reason: str) -> None:
        self.blocked = reason

    # ---- отправка

    def _begin(self) -> None:
        """Отсчёт хода — от первого события, а не от создания репортёра: ход мог ждать в очереди."""
        if self._begun:
            return
        self._begun = True
        self.started = self.clock()
        self._last_edit = self.started

    async def start(self) -> None:
        """Создаёт статус-сообщение ровно один раз. Обычно его зовёт `update` по порогу."""
        if self._created:
            return
        self._created = True
        self._begin()
        msg = await self._safe(self.bot.send_message, self.chat_id, self.text())
        self.message_id = getattr(msg, "message_id", None)
        self._last_edit = self.clock()
        self._last_text = self.text()

    async def update(self, *, force: bool = False) -> bool:
        if not self._created:
            self._begin()
            if not force and self.clock() - self.started < self.start_after:
                return False    # ход ещё короткий: события копим, в чат не лезем
            await self.start()
            return True
        if self.message_id is None:
            return False
        text = self.text()
        if text == self._last_text:
            return False
        now = self.clock()
        if not force and now - self._last_edit < self.min_interval:
            return False
        await self._safe(self.bot.edit_message_text,
                         text=text, chat_id=self.chat_id, message_id=self.message_id)
        self._last_edit = now
        self._last_text = text
        return True

    async def finish(self, text: str = "") -> None:
        """Ход кончился: статус убираем, чтобы в чате остался только ответ.

        Ничего не создаём: если карточки не было (короткий ход), её и не должно появиться.
        Не удалилась — оставляем как есть: вторым сообщением про это не спамим.
        """
        if self.message_id is None:
            return
        if self.delete_on_finish:
            message_id, self.message_id = self.message_id, None
            await self._safe(self.bot.delete_message,
                             chat_id=self.chat_id, message_id=message_id)
            return
        self._last_text = text
        await self._safe(self.bot.edit_message_text,
                         text=text, chat_id=self.chat_id, message_id=self.message_id)

    @staticmethod
    async def _safe(call, *args, **kw):
        """Ошибки Telegram (та же правка, флуд-лимит, чужое сообщение) не должны ронять ход."""
        try:
            return await call(*args, **kw)
        except Exception:  # noqa: BLE001
            return None
