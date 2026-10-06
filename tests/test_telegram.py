"""Тесты Telegram-слоя: без сети, без реального бота и без загрузки модели whisper."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from integrations.telegram import files, status, voice

# ---------------------------------------------------------------- files


def test_sanitize_name_drops_paths_and_specials():
    assert files.sanitize_name(r"..\..\state\secrets\a b:c?.txt") == "a_b_c_.txt"
    assert files.sanitize_name("отчёт ESSA.md") == "отчёт_ESSA.md"
    assert files.sanitize_name("   ") == "file"
    assert files.sanitize_name("CON.txt").startswith("_CON")


def test_inbox_path_uses_date_and_avoids_collision(tmp_path):
    when = dt.date(2026, 9, 18)
    first = files.inbox_path(tmp_path, "photo.jpg", when=when)
    assert first == tmp_path / "inbox" / "2026-09-18" / "photo.jpg"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("x", encoding="utf-8")
    second = files.inbox_path(tmp_path, "photo.jpg", when=when)
    assert second.name == "photo-1.jpg"


def test_reserve_path_creates_file_atomically(tmp_path):
    when = dt.date(2026, 9, 18)
    first = files.reserve_path(tmp_path, "photo.jpg", when=when)
    second = files.reserve_path(tmp_path, "photo.jpg", when=when)
    assert first.exists() and second.exists() and first != second
    assert second.name == "photo-1.jpg"


def test_published_line_appended(tmp_path):
    bundle = tmp_path / "essa-ai" / "content" / "2026-09-18-ai-agents"
    bundle.mkdir(parents=True)
    files.mark_content(tmp_path, "2026-09-18-ai-agents", "published", when=dt.date(2026, 9, 18))
    assert (bundle / "status").read_text(encoding="utf-8").strip() == "published"
    published = (tmp_path / "essa-ai" / "content" / "PUBLISHED.md").read_text(encoding="utf-8")
    assert "2026-09-18" in published and "2026-09-18-ai-agents" in published


def test_find_content_bundle_only_when_exists(tmp_path):
    (tmp_path / "essa-ai" / "content" / "2026-09-18-tema").mkdir(parents=True)
    text = "Готово, комплект в essa-ai/content/2026-09-18-tema/post.md — черновик."
    assert files.find_content_bundle(text, tmp_path) == "2026-09-18-tema"
    assert files.find_content_bundle("essa-ai/content/2026-01-01-нет", tmp_path) is None


# ---------------------------------------------------------------- split


def test_split_message_keeps_code_fences_balanced():
    body = "\n".join(f"line {i}" for i in range(400))
    text = "вступление\n```python\n" + body + "\n```\nхвост"
    parts = status.split_message(text, limit=200)
    assert len(parts) > 1
    assert all(len(p) <= 200 for p in parts)
    assert all(p.count("```") % 2 == 0 for p in parts)
    assert "".join(p for p in parts).count("line 399") == 1


def test_split_message_short_text_is_one_part():
    assert status.split_message("привет") == ["привет"]


def test_split_message_hard_splits_long_line():
    parts = status.split_message("я" * 500, limit=100)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts) == "я" * 500


# ---------------------------------------------------------------- render


def test_markdown_becomes_readable_telegram_html():
    from integrations.telegram import render
    md = ("## Итоги дня\n\nСделано **много** и *быстро*.\n\n"
          "- первый\n- второй\n\n1. раз\n2. два\n")
    html = render.to_html(md)
    assert "<b>Итоги дня</b>\n\n" in html
    assert "#" not in html
    assert "<b>много</b>" in html and "<i>быстро</i>" in html
    assert "• первый" in html and "• второй" in html
    assert "1. раз" in html and "2. два" in html
    assert "**" not in html and "- первый" not in html


def test_table_becomes_pairs_without_pipes():
    """Колонки на телефоне нечитаемы: таблица разворачивается в «строка: значение»."""
    from integrations.telegram import render
    md = ("| Формат | День | Тема |\n|---|---|---|\n"
          "| Reels | вторник | найм |\n| Пост | среда | цена |\n")
    html = render.to_html(md)
    assert "|" not in html
    assert "<b>Reels</b>" in html and "<b>Пост</b>" in html
    assert "День: вторник" in html and "Тема: найм" in html
    assert "День: среда" in html and "Тема: цена" in html


def test_only_telegram_markup_refusal_counts_as_markup_error(monkeypatch):
    """Чужое исключение со словом «tag» — не повод отправлять ответ второй раз."""
    from telegram.error import BadRequest, NetworkError

    from integrations.telegram import render
    assert render.is_markup_error(BadRequest("Can't parse entities: unsupported start tag"))
    assert not render.is_markup_error(NetworkError("tag lookup failed"))
    assert not render.is_markup_error(TelegramDown("unclosed tag in parse"))
    monkeypatch.setattr(render, "BadRequest", None)   # telegram не импортировался
    assert not render.is_markup_error(TelegramDown("unclosed tag in parse"))


def test_long_answer_splits_into_valid_html_chunks():
    """Кусок не должен обрываться внутри тега: Telegram отклонит такое сообщение целиком."""
    from html.parser import HTMLParser

    from integrations.telegram import render

    class Balance(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.bad = []

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)

        def handle_endtag(self, tag):
            if not self.stack or self.stack.pop() != tag:
                self.bad.append(tag)

    md = "".join(f"Строка **номер {i}** про [ссылку](https://example.com/{i}).\n\n"
                 for i in range(120))
    assert len(md) > status.TELEGRAM_LIMIT
    parts = render.prepare(md)
    assert len(parts) > 1 and not status.too_long(parts)   # лентой, а не файлом
    for part in parts:
        assert len(part) <= status.TELEGRAM_LIMIT
        parser = Balance()
        parser.feed(part)
        parser.close()
        assert parser.stack == [] and parser.bad == []
        assert "<" not in part.rsplit(">", 1)[-1]          # хвост не обрывается внутри тега
    assert "номер 0" in parts[0] and "номер 119" in parts[-1]


# ---------------------------------------------------------------- status


class TelegramDown(RuntimeError):
    """То, чем Telegram API отвечает в плохой день."""


class FakeBot:
    def __init__(self, fail_document=False, fail_get_file=False, fail_message=False,
                 fail_delete=False, fail_markup=False):
        self.sent: list[dict] = []
        self.attempts: list[dict] = []
        self.edits: list[dict] = []
        self.documents: list[dict] = []
        self.deleted: list[dict] = []
        self.fail_document = fail_document
        self.fail_get_file = fail_get_file
        self.fail_message = fail_message
        self.fail_delete = fail_delete
        self.fail_markup = fail_markup
        self._next_id = 100

    async def send_message(self, chat_id, text, **kw):
        self.attempts.append({"chat_id": chat_id, "text": text, **kw})
        if self.fail_message:
            raise TelegramDown("send_message")
        if self.fail_markup and kw.get("parse_mode"):
            from telegram.error import BadRequest
            raise BadRequest("Can't parse entities: unsupported start tag")
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text, **kw})
        return FakeMessage(self._next_id, text)

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kw):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, **kw})
        return FakeMessage(message_id, text)

    async def send_document(self, chat_id, document, filename=None, caption=None, **kw):
        if self.fail_document:
            raise TelegramDown("send_document")
        self._next_id += 1
        self.documents.append({"chat_id": chat_id, "document": document,
                               "filename": filename, "caption": caption})
        return FakeMessage(self._next_id, caption or "")

    async def delete_message(self, chat_id=None, message_id=None, **kw):
        if self.fail_delete:
            raise TelegramDown("delete_message")
        self.deleted.append({"chat_id": chat_id, "message_id": message_id})
        return True

    async def get_file(self, file_id):
        if self.fail_get_file:
            raise TelegramDown("get_file")
        return FakeFile()


class FakeMessage:
    def __init__(self, message_id, text=""):
        self.message_id = message_id
        self.text = text


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


async def test_status_edits_not_more_than_once_per_three_seconds():
    bot, clock = FakeBot(), Clock()
    rep = status.StatusReporter(bot, 7, task="контент", min_interval=3.0, clock=clock)
    await rep.start()
    assert len(bot.sent) == 1

    for i in range(5):  # пять событий подряд внутри одной секунды
        clock.now += 0.2
        rep.note({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": f"Tool{i}"}]}})
        await rep.update()
    assert bot.edits == []

    clock.now += 3.1
    rep.note({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}})
    await rep.update()
    assert len(bot.edits) == 1
    assert "Смотрю файлы" in bot.edits[-1]["text"]


async def test_status_finish_forces_edit():
    bot, clock = FakeBot(), Clock()
    rep = status.StatusReporter(bot, 7, min_interval=3.0, delete_on_finish=False, clock=clock)
    await rep.start()
    clock.now += 0.1
    await rep.finish("готово")
    assert bot.edits[-1]["text"].startswith("готово")


def _tool_event(name):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name}]}}


async def test_short_turn_never_creates_a_status_message():
    bot, clock = FakeBot(), Clock()
    rep = status.StatusReporter(bot, 7, task="почему ты так странно отвечаешь",
                                min_interval=0.0, start_after=6.0, clock=clock)
    for i in range(4):   # ход уложился в секунду: событий много, карточки быть не должно
        clock.now += 0.25
        rep.note(_tool_event(f"Tool{i}"))
        await rep.update()
    await rep.finish("✅ Готово за 1 с.")
    assert bot.sent == [] and bot.edits == [] and bot.deleted == []


async def test_long_turn_shows_status_and_deletes_it_at_the_end():
    bot, clock = FakeBot(), Clock()
    rep = status.StatusReporter(bot, 7, task="собери контент",
                                min_interval=3.0, start_after=6.0, clock=clock)
    clock.now += 1.0
    rep.note(_tool_event("Read"))
    await rep.update()
    assert bot.sent == []                      # порог ещё не перейдён

    clock.now += 6.0
    rep.note(_tool_event("Read"))
    await rep.update()
    assert len(bot.sent) == 1 and bot.sent[0]["text"].startswith("💭")
    assert "Смотрю файлы" in bot.sent[0]["text"]
    message_id = rep.message_id

    clock.now += 4.0
    rep.note(_tool_event("WebSearch"))
    await rep.update()
    assert any("ищу в интернете" in e["text"].lower() for e in bot.edits)

    await rep.finish("✅ Готово за 11 с.")
    assert [d["message_id"] for d in bot.deleted] == [message_id]
    assert not any(e["text"].startswith("✅") for e in bot.edits)


async def test_status_delete_failure_is_silent():
    bot, clock = FakeBot(fail_delete=True), Clock()
    rep = status.StatusReporter(bot, 7, min_interval=0.0, start_after=0.0, clock=clock)
    await rep.update()
    assert len(bot.sent) == 1
    await rep.finish("✅ Готово.")            # Telegram отказал — ход всё равно не падает
    assert bot.deleted == [] and bot.edits == []


# ---------------------------------------------------------------- voice


def test_transcribe_uses_injected_transcriber(tmp_path):
    ogg = tmp_path / "v.ogg"
    ogg.write_bytes(b"OggS-not-real")
    calls = []

    def fake(path):
        calls.append(path)
        return "  привет, джарвис  "

    assert voice.transcribe(ogg, transcriber=fake) == "привет, джарвис"
    assert calls == [ogg]


def test_transcribe_returns_none_on_empty_or_failure(tmp_path):
    ogg = tmp_path / "v.ogg"
    ogg.write_bytes(b"")

    def blank(path):
        return "   "

    def boom(path):
        raise RuntimeError("ffmpeg упал")

    assert voice.transcribe(ogg, transcriber=blank) is None
    assert voice.transcribe(ogg, transcriber=boom) is None
    assert voice.transcribe(tmp_path / "нет.ogg", transcriber=blank) is None


def test_model_name_from_env(monkeypatch):
    monkeypatch.delenv("JARVIS_WHISPER_MODEL", raising=False)
    assert voice.model_name() == "small"
    monkeypatch.setenv("JARVIS_WHISPER_MODEL", "medium")
    assert voice.model_name() == "medium"


# ---------------------------------------------------------------- gateway

OWNER = 4242
STRANGER = 9999


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.username = "owner"


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeFile:
    def __init__(self, data=b"data"):
        self.data = data

    async def download_to_drive(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(self.data)
        return path


class FakeIncoming:
    """Входящее сообщение Telegram: текст, голос, документ или фото."""

    def __init__(self, text=None, voice=None, document=None, photo=None, caption=None,
                 video=None, video_note=None, animation=None):
        self.message_id = 1
        self.text = text
        self.voice = voice
        self.document = document
        self.photo = photo or []
        self.caption = caption
        self.video = video
        self.video_note = video_note
        self.animation = animation


class FakeUpdate:
    def __init__(self, user_id=OWNER, chat_id=None, message=None, callback_query=None):
        self.effective_user = FakeUser(user_id)
        self.effective_chat = FakeChat(chat_id if chat_id is not None else user_id)
        self.message = message
        self.effective_message = message
        self.callback_query = callback_query


class FakeCallback:
    def __init__(self, data, user_id=OWNER, chat_id=OWNER):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(55)
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kw):
        self.answers.append(text)

    async def edit_message_text(self, text, **kw):
        self.edits.append({"text": text, **kw})

    async def edit_message_reply_markup(self, reply_markup=None, **kw):
        self.edits.append({"reply_markup": reply_markup})


class FakeContext:
    def __init__(self, bot=None, args=None):
        self.bot = bot or FakeBot()
        self.args = args or []


TOOL_EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "sid-1"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
    {"type": "result", "subtype": "success", "session_id": "sid-1"},
]


class FakeRouter:
    """Ход завершается позже submit и по пути шлёт события — как настоящий."""

    def __init__(self, answer="ответ агента", status="ok", position=0, events=None,
                 new_session=False, pending=0):
        self.answer, self.status, self.position = answer, status, position
        self.events = TOOL_EVENTS if events is None else events
        self.new_session = new_session
        self._pending = pending
        self.jobs = []
        self.stopped = []
        self.tasks = []

    def submit(self, chat_id, job):
        import asyncio

        from runtime.claude_bridge import TurnResult
        self.jobs.append((chat_id, job))
        loop = asyncio.get_running_loop()
        job.result = loop.create_future()

        async def turn():
            await asyncio.sleep(0)
            for ev in self.events:
                await job.on_event(ev)
            job.result.set_result(TurnResult(self.answer, "sid-1", self.new_session,
                                             0.01, self.status))

        self.tasks.append(loop.create_task(turn()))
        return self.position

    def stop(self, chat_id):
        self.stopped.append(chat_id)
        return True

    def pending(self, chat_id):
        return self._pending


class FakeSessions:
    def __init__(self):
        self.store = {}
        self.resets = []

    def get(self, chat_id):
        return self.store.get(str(chat_id))

    def set(self, chat_id, sid):
        self.store[str(chat_id)] = sid

    def reset(self, chat_id):
        self.resets.append(str(chat_id))
        self.store.pop(str(chat_id), None)


class FakeApprovals:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def resolve(self, request_id, decision, reason=""):
        self.calls.append((request_id, decision, reason))
        return self.ok


def make_gateway(tmp_path, owner_id=OWNER, **kw):
    from integrations.telegram import gateway as gw
    kw.setdefault("router", FakeRouter())
    kw.setdefault("sessions", FakeSessions())
    kw.setdefault("approvals", FakeApprovals())
    return gw.Gateway(owner_id=owner_id, root=tmp_path, min_status_interval=0.0, **kw)


async def test_stranger_never_reaches_the_agent(tmp_path, caplog):
    caplog.set_level("INFO")
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(STRANGER, message=FakeIncoming(text="привет")), ctx)
    assert g.router.jobs == []
    assert ctx.bot.sent == []


async def test_setup_mode_answers_only_whoami(tmp_path):
    g = make_gateway(tmp_path, owner_id=None)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(STRANGER, message=FakeIncoming(text="привет")), ctx)
    await g.cmd_start(FakeUpdate(STRANGER, message=FakeIncoming(text="/start")), ctx)
    await g.cmd_start(FakeUpdate(STRANGER, message=FakeIncoming(text="/help")), ctx)
    await g.cmd_status(FakeUpdate(STRANGER, message=FakeIncoming(text="/status")), ctx)
    await g.on_voice(FakeUpdate(STRANGER, message=FakeIncoming(
        voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())), ctx)
    await g.on_file(FakeUpdate(STRANGER, message=FakeIncoming(
        document=type("D", (), {"file_id": "f2", "file_name": "a.pdf",
                                "file_unique_id": "u2"})())), ctx)
    assert ctx.bot.sent == [] and g.router.jobs == []
    await g.cmd_whoami(FakeUpdate(STRANGER, message=FakeIncoming(text="/whoami")), ctx)
    assert len(ctx.bot.sent) == 1 and str(STRANGER) in ctx.bot.sent[-1]["text"]


async def test_text_goes_to_router_and_answer_comes_back(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="Сделай контент")), ctx)
    chat_id, job = g.router.jobs[0]
    assert chat_id == OWNER and "Сделай контент" in job.prompt
    assert any("ответ агента" in m["text"] for m in ctx.bot.sent)


async def test_very_long_answer_goes_as_document(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="строка ответа\n" * 3000))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай много")), ctx)
    assert len(ctx.bot.documents) == 1
    assert ctx.bot.documents[0]["filename"].endswith(".md")


MARKDOWN_ANSWER = "## Итог\n\n- **раз**\n- два\n"


async def test_answer_reaches_the_owner_with_markup(tmp_path):
    """Владелице уходит оформленный HTML, а не решётки со звёздочками."""
    g = make_gateway(tmp_path, router=FakeRouter(answer=MARKDOWN_ANSWER))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай итог")), ctx)
    msg = next(m for m in ctx.bot.sent if "раз" in m["text"])
    assert msg.get("parse_mode") == "HTML"
    assert "<b>Итог</b>" in msg["text"] and "<b>раз</b>" in msg["text"]
    assert "•" in msg["text"]
    assert "##" not in msg["text"] and "**" not in msg["text"]


# ---------------------------------------------------------------- вложения 📎


def test_extract_attachments_strips_lines_and_keeps_order():
    text = "Привет\n\n📎 a.pdf\nОстальное\n📎 b.png\n"
    cleaned, paths = files.extract_attachments(text)
    assert paths == ["a.pdf", "b.png"]
    assert "📎" not in cleaned
    assert "Привет" in cleaned and "Остальное" in cleaned


def test_resolve_attachment_rejects_path_outside_root(tmp_path):
    outside = tmp_path.parent / "jarvis-attachment-outside.txt"
    outside.write_text("x", encoding="utf-8")
    try:
        with pytest.raises(ValueError):
            files.resolve_attachment(tmp_path, str(outside))
    finally:
        outside.unlink(missing_ok=True)


async def test_attachment_line_is_sent_as_document_and_stripped_from_text(tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4 fake")
    g = make_gateway(tmp_path, router=FakeRouter(answer="Готово.\n\n📎 report.pdf"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="сделай pdf")), ctx)
    assert len(ctx.bot.documents) == 1
    assert ctx.bot.documents[0]["filename"] == "report.pdf"
    assert not any("📎" in m["text"] for m in ctx.bot.sent)


async def test_attachment_only_answer_still_sends_the_file(tmp_path):
    """Ответ из одной строки 📎 не должен потеряться из-за проверки «текст пуст»."""
    (tmp_path / "only.png").write_bytes(b"\x89PNG")
    g = make_gateway(tmp_path, router=FakeRouter(answer="📎 only.png"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="картинку")), ctx)
    assert len(ctx.bot.documents) == 1
    assert ctx.bot.documents[0]["filename"] == "only.png"


@pytest.mark.parametrize("raw", [".env", "./.env", "sub/../.env"])
async def test_dotenv_never_sent_by_relative_forms(tmp_path, raw):
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    g = make_gateway(tmp_path, router=FakeRouter(answer=f"секрет\n\n📎 {raw}"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай .env")), ctx)
    assert ctx.bot.documents == []
    assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)


async def test_dotenv_absolute_path_never_sent(tmp_path):
    envfile = tmp_path / ".env"
    envfile.write_text("X=1", encoding="utf-8")
    g = make_gateway(tmp_path, router=FakeRouter(answer=f"📎 {envfile}"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай .env")), ctx)
    assert ctx.bot.documents == []
    assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)


async def test_path_outside_project_not_sent(tmp_path):
    outside_dir = tmp_path.parent / "jarvis-attachment-outside-dir"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "leak.txt"
    outside_file.write_text("x", encoding="utf-8")
    try:
        g = make_gateway(tmp_path, router=FakeRouter(answer=f"📎 {outside_file}"))
        ctx = FakeContext()
        await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай файл")), ctx)
        assert ctx.bot.documents == []
        assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)
    finally:
        outside_file.unlink(missing_ok=True)
        outside_dir.rmdir()


async def test_directory_not_sent(tmp_path):
    (tmp_path / "folder").mkdir()
    g = make_gateway(tmp_path, router=FakeRouter(answer="📎 folder"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="папку")), ctx)
    assert ctx.bot.documents == []
    assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)


async def test_too_many_attachments_only_limit_sent(tmp_path):
    lines = []
    for i in range(files.ATTACH_MAX_FILES + 1):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        lines.append(f"📎 f{i}.txt")
    g = make_gateway(tmp_path, router=FakeRouter(answer="комплект\n\n" + "\n".join(lines)))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай всё")), ctx)
    assert len(ctx.bot.documents) == files.ATTACH_MAX_FILES
    assert any("Не получилось прислать" in m["text"] and str(files.ATTACH_MAX_FILES) in m["text"]
               for m in ctx.bot.sent)


async def test_over_size_limit_not_sent(tmp_path, monkeypatch):
    (tmp_path / "big.bin").write_bytes(b"x")
    monkeypatch.setattr(files, "ATTACH_MAX_BYTES", 0)
    g = make_gateway(tmp_path, router=FakeRouter(answer="📎 big.bin"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="файл")), ctx)
    assert ctx.bot.documents == []
    assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)


async def test_one_bad_attachment_does_not_block_others(tmp_path):
    (tmp_path / "good.txt").write_text("ok", encoding="utf-8")
    (tmp_path / ".env").write_text("X=1", encoding="utf-8")
    g = make_gateway(tmp_path, router=FakeRouter(answer="готово\n\n📎 .env\n📎 good.txt"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="файлы")), ctx)
    assert len(ctx.bot.documents) == 1
    assert ctx.bot.documents[0]["filename"] == "good.txt"
    assert any("Не получилось прислать" in m["text"] for m in ctx.bot.sent)


async def test_markup_refusal_never_costs_the_answer(tmp_path):
    """Telegram не принял теги — тот же текст уходит простым, ответ не теряется."""
    g = make_gateway(tmp_path, router=FakeRouter(answer=MARKDOWN_ANSWER))
    ctx = FakeContext(bot=FakeBot(fail_markup=True))
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай итог")), ctx)
    assert any(m.get("parse_mode") == "HTML" for m in ctx.bot.attempts)   # попытка была
    msg = next(m for m in ctx.bot.sent if "раз" in m["text"])
    assert msg.get("parse_mode") is None
    assert "<b>" not in msg["text"]
    assert "Итог" in msg["text"] and "раз" in msg["text"]


async def test_long_answer_file_keeps_the_original_markdown(tmp_path):
    """Файл — рабочий материал владелицы: в нём markdown, а не теги Telegram."""
    long_md = "## Раздел\n\nстрока **ответа**\n" * 500
    g = make_gateway(tmp_path, router=FakeRouter(answer=long_md))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай много")), ctx)
    assert len(ctx.bot.documents) == 1
    body = ctx.bot.documents[0]["document"].decode("utf-8")
    assert "## Раздел" in body and "**ответа**" in body
    assert "<b>" not in body


async def test_content_buttons_survive_the_markup(tmp_path):
    (tmp_path / "essa-ai" / "content" / "2026-09-18-tema").mkdir(parents=True)
    g = make_gateway(tmp_path, router=FakeRouter(
        answer="## Готово\n\nКомплект в `essa-ai/content/2026-09-18-tema/`"))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="сделай контент")), ctx)
    assert ctx.bot.sent[-1].get("reply_markup") is not None


async def test_new_resets_session_and_stop_stops(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    g.sessions.set(OWNER, "sid-old")
    await g.cmd_new(FakeUpdate(OWNER, message=FakeIncoming(text="/new")), ctx)
    assert g.sessions.resets == [str(OWNER), f"{OWNER}:codex"]
    await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming(text="/stop")), ctx)
    assert g.router.stopped == [OWNER]


async def test_voice_failure_never_reaches_agent(tmp_path):
    g = make_gateway(tmp_path, transcriber=lambda p: None)
    ctx = FakeContext()
    msg = FakeIncoming(voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())
    await g.on_voice(FakeUpdate(OWNER, message=msg), ctx)
    assert g.router.jobs == []
    assert "не расслышал" in ctx.bot.sent[-1]["text"]


async def test_voice_success_shows_transcript_and_runs(tmp_path):
    g = make_gateway(tmp_path, transcriber=lambda p: "сделай контент на завтра")
    ctx = FakeContext()
    msg = FakeIncoming(voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())
    await g.on_voice(FakeUpdate(OWNER, message=msg), ctx)
    assert "🎙 Услышал" in ctx.bot.sent[0]["text"]
    assert "сделай контент на завтра" in g.router.jobs[0][1].prompt


async def test_document_saved_to_inbox_and_path_in_prompt(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    doc = type("D", (), {"file_id": "f2", "file_name": "../секрет отчёт.pdf",
                         "file_unique_id": "u2"})()
    await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(document=doc, caption="разбери")), ctx)
    saved = list((tmp_path / "inbox").rglob("*.pdf"))
    assert len(saved) == 1 and saved[0].name == "секрет_отчёт.pdf"
    prompt = g.router.jobs[0][1].prompt
    assert "разбери" in prompt and saved[0].name in prompt


async def test_approval_request_shows_summary_and_resolves(tmp_path):
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.on_approval_request("rid-1", "MONEY", "Bash",
                                'Отправить ответ @user: "привет"?', {"kind": "message"})
    assert 'Отправить ответ @user: "привет"?' in bot.sent[-1]["text"]
    assert bot.sent[-1]["reply_markup"] is not None

    cb = FakeCallback(g.approval_callback_data("rid-1", "allow"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert g.approvals.calls == [("rid-1", "allow", "")]


async def test_stale_approval_says_so_and_clears_buttons(tmp_path):
    g = make_gateway(tmp_path, approvals=FakeApprovals(ok=False))
    bot = FakeBot()
    g.attach(bot)
    await g.on_approval_request("rid-2", "EXTERNAL", "Bash", "Опубликовать пост?", {})
    cb = FakeCallback(g.approval_callback_data("rid-2", "deny"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert "неактуален" in cb.edits[-1]["text"]
    assert cb.edits[-1].get("reply_markup") is None


async def test_published_button_writes_published_md(tmp_path):
    bundle = tmp_path / "essa-ai" / "content" / "2026-09-18-tema"
    bundle.mkdir(parents=True)
    g = make_gateway(tmp_path)
    cb = FakeCallback(g.content_callback_data("2026-09-18-tema", "published"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext())
    assert (bundle / "status").read_text(encoding="utf-8").strip() == "published"
    assert "2026-09-18-tema" in (tmp_path / "essa-ai" / "content" / "PUBLISHED.md").read_text(
        encoding="utf-8")


async def test_one_status_message_per_turn(tmp_path):
    g = make_gateway(tmp_path, status_delay=0.0)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="посчитай")), ctx)
    statuses = [m for m in ctx.bot.sent if m["text"].startswith("💭")]
    assert len(statuses) == 1                      # ровно одно статус-сообщение на ход
    assert any("Смотрю файлы" in e["text"] for e in ctx.bot.edits)
    assert len(ctx.bot.deleted) == 1               # и в конце оно исчезает
    assert not any(e["text"].startswith("✅") for e in ctx.bot.edits)


async def test_short_turn_leaves_only_the_answer(tmp_path):
    g = make_gateway(tmp_path)      # порог по умолчанию, ход в тесте мгновенный
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="привет")), ctx)
    assert [m for m in ctx.bot.sent if m["text"].startswith("💭")] == []
    assert ctx.bot.edits == []
    assert [m["text"] for m in ctx.bot.sent] == ["ответ агента"]


async def test_status_delete_failure_does_not_break_the_answer(tmp_path):
    g = make_gateway(tmp_path, status_delay=0.0)
    ctx = FakeContext(bot=FakeBot(fail_delete=True))
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="посчитай")), ctx)
    assert any("ответ агента" in m["text"] for m in ctx.bot.sent)


async def test_queued_turn_says_position_and_waits_with_status(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(position=2))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="ещё задача")), ctx)
    text = ctx.bot.sent[0]["text"]
    assert "я ещё занят" in text and "ещё 1" in text and "/status" in text and "/stop" in text
    assert "в очереди:" not in text                      # её поправка 2026-10-05: без голого номера
    assert not text.startswith("💭")  # тикающий статус — только когда ход пошёл

    # ход без единого события статус вообще не заводит — владелице нечего смотреть
    g2 = make_gateway(tmp_path, router=FakeRouter(events=[]))
    ctx2 = FakeContext()
    await g2.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="молча")), ctx2)
    assert [m for m in ctx2.bot.sent if m["text"].startswith("💭")] == []
    assert ctx2.bot.edits == []


async def test_new_session_is_announced_before_the_answer(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(new_session=True))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="привет")), ctx)
    texts = [m["text"] for m in ctx.bot.sent]
    notice = next(i for i, t in enumerate(texts) if "Не смог подхватить прошлый разговор" in t)
    answer = next(i for i, t in enumerate(texts) if "ответ агента" in t)
    assert notice < answer


async def test_delivery_failure_is_reported_not_raised(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="строка\n" * 3000))
    ctx = FakeContext(bot=FakeBot(fail_document=True))
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай много")), ctx)
    assert ctx.bot.documents == []
    assert any("не принял" in m["text"].lower() for m in ctx.bot.sent)


async def test_browser_flag_is_not_guessed_from_words(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(
        text="напомни, сколько стоил билет в кино")), ctx)
    assert g.router.jobs[0][1].uses_browser is False


async def test_status_command_reports_queue(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(pending=3))
    ctx = FakeContext()
    await g.cmd_status(FakeUpdate(OWNER, message=FakeIncoming(text="/status")), ctx)
    assert "3" in ctx.bot.sent[-1]["text"]


async def test_browser_login_without_args_and_without_script(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.cmd_browser_login(FakeUpdate(OWNER, message=FakeIncoming(text="/browser_login")), ctx)
    assert "адрес" in ctx.bot.sent[-1]["text"]
    ctx2 = FakeContext(args=["https://instagram.com"])
    await g.cmd_browser_login(FakeUpdate(OWNER, message=FakeIncoming(text="/browser_login x")), ctx2)
    assert "login.py" in ctx2.bot.sent[-1]["text"]  # в tmp_path скрипта нет
    assert g.router.jobs == []


async def test_download_failure_tells_owner(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext(bot=FakeBot(fail_get_file=True))
    doc = type("D", (), {"file_id": "f9", "file_name": "a.pdf", "file_unique_id": "u9"})()
    await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(document=doc)), ctx)
    assert g.router.jobs == []
    assert "не получилось сохранить" in ctx.bot.sent[-1]["text"].lower()
    assert list((tmp_path / "inbox").rglob("*.pdf")) == []  # пустышка не остаётся


async def test_approval_button_works_once(tmp_path):
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.on_approval_request("rid-9", "EXTERNAL", "Bash", "Отправить письмо?", {})
    data = g.approval_callback_data("rid-9", "allow")
    for _ in range(2):
        cb = FakeCallback(data)
        await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert g.approvals.calls == [("rid-9", "allow", "")]
    assert "уже не работает" in cb.edits[-1]["text"]


async def test_stranger_cannot_press_buttons(tmp_path):
    g = make_gateway(tmp_path)
    cb = FakeCallback(g.approval_callback_data("rid-3", "allow"), user_id=STRANGER)
    await g.on_callback(FakeUpdate(STRANGER, callback_query=cb), FakeContext())
    assert g.approvals.calls == []


async def test_greeting_calls_the_owner_by_name(tmp_path, monkeypatch):
    """Владелица просила здороваться по имени: «привет Катерина! На связи Джарвис»."""
    monkeypatch.delenv("JARVIS_OWNER_NAME", raising=False)
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.announce()
    assert bot.sent[-1]["text"] == "Привет, Катерина! На связи Джарвис."
    monkeypatch.setenv("JARVIS_OWNER_NAME", "Аня")
    await g.announce()
    assert bot.sent[-1]["text"] == "Привет, Аня! На связи Джарвис."


# ---------------------------------------------------------------- карта essa-ai


def test_essa_stubs_point_to_files_that_exist():
    """Заглушки — указатели: владелица жаловалась, что агент «не видит половины файлов»."""
    import re
    root = Path(__file__).resolve().parents[1]
    essa = root / "essa-ai"
    for stub in ("PROFILE.md", "STRATEGY.md", "PRODUCTS.md", "ANALYTICS.md"):
        text = (essa / stub).read_text(encoding="utf-8")
        assert "00_PROJECT_MAP.md" in text, stub
        named = set(re.findall(r"`([^`\n]+\.md)`", text))
        assert named, f"{stub}: указатель никуда не ведёт"
        for name in named:
            assert (essa / name).exists(), f"{stub} ссылается на несуществующий {name}"


def test_claude_md_map_leads_to_the_project_map():
    root = Path(__file__).resolve().parents[1]
    line = next(ln for ln in (root / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
                if ln.startswith("| `essa-ai/"))
    assert "00_PROJECT_MAP.md" in line
    assert "PROFILE" not in line and "ANALYTICS" not in line


# ---------------------------------------------------------------- запуск и секреты


def test_missing_token_gives_human_error(tmp_path, capsys, monkeypatch):
    from integrations.telegram import gateway as gw
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_OWNER_ID=1\n", encoding="utf-8")
    assert gw.main([], env_path=env) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().out


def test_env_values_are_never_printed_or_logged(tmp_path, capsys, caplog, monkeypatch):
    from integrations.telegram import gateway as gw
    caplog.set_level("DEBUG")
    secret = "1234567:SECRET-TOKEN-VALUE"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)
    env = tmp_path / ".env"
    env.write_text(f'TELEGRAM_BOT_TOKEN="{secret}"\n# комментарий\nTELEGRAM_OWNER_ID=4242\n',
                   encoding="utf-8")
    gw.load_env(env)
    cfg = gw.Config.from_env()
    assert cfg.token == secret and cfg.owner_id == 4242
    blob = capsys.readouterr().out + caplog.text + repr(cfg) + str(cfg)
    assert secret not in blob and "4242" not in repr(cfg)



async def test_queue_message_names_the_current_task(tmp_path):
    """Её поправка 2026-10-05: бот говорит, чем занят, а не «в очереди: 4»."""
    import json as _json
    p = tmp_path / "state" / "events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps({"type": "task_state", "ts": "2026-10-05T10:00:00+00:00", "task_id": "a",
                              "task": "пост про ИИ", "state": "running", "chat": str(OWNER)}) + "\n",
                 encoding="utf-8")
    g = make_gateway(tmp_path, router=FakeRouter(position=1))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="ещё")), ctx)
    assert ctx.bot.sent[0]["text"] == "Секунду, я ещё занят задачей «пост про ИИ» — сразу после неё займусь твоим сообщением."


async def test_today_question_is_answered_by_python_without_agent(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="привет, что у нас на сегодня?")), ctx)
    assert g.router.jobs == []
    assert any("Доброе утро" in m["text"] for m in ctx.bot.sent)


async def test_typing_indicator_while_agent_works(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="готово"))
    ctx = FakeContext()
    actions = []

    async def send_chat_action(chat_id, action):
        actions.append(action)
    ctx.bot.send_chat_action = send_chat_action
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="сделай пост")), ctx)
    assert actions and set(actions) == {"typing"}


def test_help_lists_every_registered_command():
    from integrations.telegram.gateway import COMMANDS, HELP
    assert {n for n, _, _ in COMMANDS} >= {"today", "status", "stop", "new", "codex", "claude"}
    assert all(f"/{n} —" in HELP for n, _, _ in COMMANDS)


async def test_today_command_answers_without_agent(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.cmd_today(FakeUpdate(OWNER, message=FakeIncoming(text="/today")), ctx)
    assert g.router.jobs == [] and any("Доброе утро" in m["text"] for m in ctx.bot.sent)


async def test_status_admits_long_task_after_a_minute():
    clock = Clock()
    rep = status.StatusReporter(FakeBot(), OWNER, task="x", clock=clock)
    rep.note({"type": "system", "subtype": "init"})
    assert "несколько минут" not in rep.text()
    clock.now += 61
    assert "несколько минут" in rep.text()


# ------------------------------------------------ голос не блокирует бота, лог в файле, весть о прерванном

async def test_voice_transcribed_off_the_event_loop(tmp_path):
    """Whisper считает секунды: в цикле событий он заморозил бы /stop, кнопки и расписание (аудит 2026-10-06)."""
    import threading
    seen = []

    def transcriber(path):
        seen.append(threading.current_thread())
        return "привет"

    g = make_gateway(tmp_path, transcriber=transcriber)
    msg = FakeIncoming(voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())
    await g.on_voice(FakeUpdate(OWNER, message=msg), FakeContext())
    assert seen and seen[0] is not threading.main_thread()


def test_setup_logging_writes_file_once(tmp_path):
    import logging
    from integrations.telegram import gateway as gw
    path = tmp_path / "state" / "jarvis.log"
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        gw.setup_logging(path)
        gw.setup_logging(path)   # повторный вызов не дублирует строки
        logging.getLogger("jarvis.test").warning("не удалось доставить ответ")
        for h in root.handlers:
            h.flush()
        assert path.read_text(encoding="utf-8").count("не удалось доставить ответ") == 1
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()


async def test_announce_interrupted_lists_lost_tasks(tmp_path):
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.announce_interrupted([
        {"task_id": "a", "task": "сделай контент", "state": "running"},
        {"task_id": "b", "task": "рилс", "state": "queued"},
    ])
    text = bot.sent[-1]["text"]
    assert bot.sent[-1]["chat_id"] == OWNER
    assert "перезапустил" in text and "сделай контент" in text and "рилс" in text
    assert "напиши" in text.lower()


async def test_announce_interrupted_silent_when_nothing_lost(tmp_path):
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.announce_interrupted([])
    assert bot.sent == []


async def test_video_sent_as_video_is_saved_and_path_goes_to_agent(tmp_path):
    """Видео «обычным способом» (не файлом) раньше молча терялось: на него не было обработчика."""
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    vid = type("V", (), {"file_id": "v1", "file_unique_id": "uv1", "file_size": 5 * 1024 * 1024, "file_name": None})()
    await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(video=vid, caption="смонтируй")), ctx)
    saved = list((tmp_path / "inbox").rglob("*.mp4"))
    assert len(saved) == 1 and saved[0].name.startswith("video-uv1")
    prompt = g.router.jobs[0][1].prompt
    assert "смонтируй" in prompt and saved[0].name in prompt


async def test_video_note_and_animation_are_handled_too(tmp_path):
    g = make_gateway(tmp_path)
    for kind in ("video_note", "animation"):
        ctx = FakeContext()
        obj = type("V", (), {"file_id": "x", "file_unique_id": "u" + kind, "file_size": 1000})()
        await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(**{kind: obj})), ctx)
    assert len(g.router.jobs) == 2


async def test_video_over_bot_limit_explains_what_to_do_instead_of_silence(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    vid = type("V", (), {"file_id": "v2", "file_unique_id": "uv2", "file_size": 87 * 1024 * 1024, "file_name": "reel.mp4"})()
    await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(video=vid)), ctx)
    text = ctx.bot.sent[-1]["text"]
    assert "87 МБ" in text and "20 МБ" in text and "inbox" in text and "смонтируй рилс из inbox/reel.mp4" in text
    assert g.router.jobs == [] and list((tmp_path / "inbox").rglob("*.mp4")) == []


async def test_telegram_too_big_error_with_unknown_size_gets_the_same_explanation(tmp_path):
    class TooBigBot(FakeBot):
        async def get_file(self, file_id):
            raise RuntimeError("File is too big")
    g = make_gateway(tmp_path)
    ctx = FakeContext(bot=TooBigBot())
    doc = type("D", (), {"file_id": "f", "file_name": "raw.mov", "file_unique_id": "ur"})()
    await g.on_file(FakeUpdate(OWNER, message=FakeIncoming(document=doc)), ctx)
    assert "20 МБ" in ctx.bot.sent[-1]["text"] and g.router.jobs == []


def test_gateway_registers_video_handler(tmp_path):
    import inspect
    from integrations.telegram import gateway
    src = inspect.getsource(gateway)
    assert "filters.VIDEO" in src and "filters.VIDEO_NOTE" in src
