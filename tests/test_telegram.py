"""Тесты Telegram-слоя: без сети, без реального бота и без загрузки модели whisper."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

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


# ---------------------------------------------------------------- status


class TelegramDown(RuntimeError):
    """То, чем Telegram API отвечает в плохой день."""


class FakeBot:
    def __init__(self, fail_document=False, fail_get_file=False, fail_message=False):
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.documents: list[dict] = []
        self.fail_document = fail_document
        self.fail_get_file = fail_get_file
        self.fail_message = fail_message
        self._next_id = 100

    async def send_message(self, chat_id, text, **kw):
        if self.fail_message:
            raise TelegramDown("send_message")
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
    assert "Bash" in bot.edits[-1]["text"]


async def test_status_finish_forces_edit():
    bot, clock = FakeBot(), Clock()
    rep = status.StatusReporter(bot, 7, min_interval=3.0, clock=clock)
    await rep.start()
    clock.now += 0.1
    await rep.finish("готово")
    assert bot.edits[-1]["text"].startswith("готово")


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

    def __init__(self, text=None, voice=None, document=None, photo=None, caption=None):
        self.message_id = 1
        self.text = text
        self.voice = voice
        self.document = document
        self.photo = photo or []
        self.caption = caption


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


async def test_new_resets_session_and_stop_stops(tmp_path):
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    g.sessions.set(OWNER, "sid-old")
    await g.cmd_new(FakeUpdate(OWNER, message=FakeIncoming(text="/new")), ctx)
    assert g.sessions.resets == [str(OWNER)]
    await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming(text="/stop")), ctx)
    assert g.router.stopped == [OWNER]


async def test_voice_failure_never_reaches_agent(tmp_path):
    g = make_gateway(tmp_path, transcriber=lambda p: None)
    ctx = FakeContext()
    msg = FakeIncoming(voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())
    await g.on_voice(FakeUpdate(OWNER, message=msg), ctx)
    assert g.router.jobs == []
    assert "не разобрал" in ctx.bot.sent[-1]["text"]


async def test_voice_success_shows_transcript_and_runs(tmp_path):
    g = make_gateway(tmp_path, transcriber=lambda p: "сделай контент на завтра")
    ctx = FakeContext()
    msg = FakeIncoming(voice=type("V", (), {"file_id": "f1", "file_unique_id": "u1"})())
    await g.on_voice(FakeUpdate(OWNER, message=msg), ctx)
    assert "🎙 распознал" in ctx.bot.sent[0]["text"]
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
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="посчитай")), ctx)
    statuses = [m for m in ctx.bot.sent if m["text"].startswith("⚙️")]
    assert len(statuses) == 1                      # ровно одно статус-сообщение на ход
    assert any("Bash" in e["text"] for e in ctx.bot.edits)
    assert ctx.bot.edits[-1]["text"].startswith("✅")


async def test_queued_turn_says_position_and_waits_with_status(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(position=2))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="ещё задача")), ctx)
    assert "в очереди: 2" in ctx.bot.sent[0]["text"]
    assert not ctx.bot.sent[0]["text"].startswith("⚙️")  # тикающий статус — только когда ход пошёл

    # ход без единого события статус вообще не заводит — владелице нечего смотреть
    g2 = make_gateway(tmp_path, router=FakeRouter(events=[]))
    ctx2 = FakeContext()
    await g2.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="молча")), ctx2)
    assert [m for m in ctx2.bot.sent if m["text"].startswith("⚙️")] == []
    assert ctx2.bot.edits == []


async def test_new_session_is_announced_before_the_answer(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(new_session=True))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="привет")), ctx)
    texts = [m["text"] for m in ctx.bot.sent]
    notice = next(i for i, t in enumerate(texts) if "Начал новый разговор" in t)
    answer = next(i for i, t in enumerate(texts) if "ответ агента" in t)
    assert notice < answer


async def test_delivery_failure_is_reported_not_raised(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="строка\n" * 3000))
    ctx = FakeContext(bot=FakeBot(fail_document=True))
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="дай много")), ctx)
    assert ctx.bot.documents == []
    assert any("не смог отправить" in m["text"].lower() for m in ctx.bot.sent)


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
    assert "не смог сохранить" in ctx.bot.sent[-1]["text"].lower()
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
    assert "устарела" in cb.edits[-1]["text"]


async def test_stranger_cannot_press_buttons(tmp_path):
    g = make_gateway(tmp_path)
    cb = FakeCallback(g.approval_callback_data("rid-3", "allow"), user_id=STRANGER)
    await g.on_callback(FakeUpdate(STRANGER, callback_query=cb), FakeContext())
    assert g.approvals.calls == []


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
