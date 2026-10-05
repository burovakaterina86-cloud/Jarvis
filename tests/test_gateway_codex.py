"""Telegram-часть переключения на Codex (P4.1e/f): кнопки, команды, отложенный запуск, /status."""
import asyncio
from pathlib import Path

from runtime import worker
from runtime.claude_bridge import TurnResult
from tests.test_telegram import OWNER, FakeBot, FakeCallback, FakeContext, FakeIncoming, FakeRouter, FakeUpdate, make_gateway


class SwitchRouter(FakeRouter):
    """FakeRouter + исполнители: offer_job / set_runtime / runtime_for, как у настоящего роутера."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.runtime = "claude"

    def runtime_for(self, chat_id):
        return self.runtime

    def set_runtime(self, chat_id, runtime, until=None):
        self.runtime = runtime
        worker.switch(str(chat_id), runtime, until=until)

    def offer_job(self, chat_id, until=None):
        from runtime.task_router import Job
        offer = worker.load_offer(str(chat_id))
        if not offer:
            return None
        worker.drop_offer(str(chat_id))
        self.set_runtime(chat_id, "codex", until=offer.get("resets_at"))
        return Job(prompt="[сводка] " + offer["prompt"], task=offer["task"], runtime="codex")


OFFER = {"task": "комплект про ИИ", "prompt": "сделай комплект", "spec": None,
         "files": ["essa-ai/content/x/post.md"], "resets_at": 1_900_000_000.0}


def labels(msg):
    return [b.text for row in msg["reply_markup"].inline_keyboard for b in row]


async def test_limit_shows_offer_with_two_buttons(tmp_path):
    g = make_gateway(tmp_path, router=SwitchRouter())
    ctx = FakeContext()
    worker.save_offer(str(OWNER), OFFER)
    res = TurnResult("Лимит подписки Claude исчерпан", None, False, None, "rate_limited", "rate_limit")
    res.switch_offer = OFFER
    await g._deliver(ctx, OWNER, res)
    msg = ctx.bot.sent[-1]
    assert "Лимит Claude закончился" in msg["text"] and "комплект про ИИ" in msg["text"]
    assert "essa-ai/content/x/post.md" in msg["text"]
    assert labels(msg)[0] == "Продолжить в Codex" and labels(msg)[1].startswith("Подождать до ")


async def test_continue_in_codex_button_runs_the_task_in_codex(tmp_path):
    router = SwitchRouter(answer="Готово\n\n🟢 Сделано в Codex")
    g = make_gateway(tmp_path, router=router)
    bot = FakeBot()
    g.attach(bot)
    worker.save_offer(str(OWNER), OFFER)
    cb = FakeCallback(g.switch_callback_data(OWNER, "codex"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert "Codex" in cb.edits[0]["text"] and cb.edits[0].get("reply_markup") is None
    chat, job = router.jobs[-1]
    assert job.runtime == "codex" and "сделай комплект" in job.prompt
    assert any("Сделано в Codex" in m["text"] for m in bot.sent)


async def test_wait_button_defers_the_task_to_claude(tmp_path):
    router = SwitchRouter()
    g = make_gateway(tmp_path, router=router)
    bot = FakeBot()
    g.attach(bot)
    worker.save_offer(str(OWNER), OFFER)
    cb = FakeCallback(g.switch_callback_data(OWNER, "wait"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert "Claude" in cb.edits[0]["text"]
    assert router.jobs == [] and worker.load_offer(str(OWNER)) is None
    assert await g.check_deferred(now=OFFER["resets_at"] - 10) == []
    started = await g.check_deferred(now=OFFER["resets_at"] + 1)
    assert started == ["комплект про ИИ"]
    await g.schedule_tasks_done()
    chat, job = router.jobs[-1]
    assert job.runtime == "claude" and job.prompt == "сделай комплект"


async def test_stale_button(tmp_path):
    g = make_gateway(tmp_path, router=SwitchRouter())
    cb = FakeCallback(g.switch_callback_data(OWNER, "codex"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext())
    assert "устарел" in cb.edits[0]["text"]


async def test_switched_back_is_announced_before_the_answer(tmp_path):
    g = make_gateway(tmp_path, router=SwitchRouter())
    ctx = FakeContext()
    res = TurnResult("ответ Claude", "s", False, None, "ok")
    res.switched_back = True
    await g._deliver(ctx, OWNER, res)
    texts = [m["text"] for m in ctx.bot.sent]
    assert "Лимит Claude восстановился" in texts[0] and "ответ Claude" in texts[-1]


async def test_codex_and_claude_commands(tmp_path):
    router = SwitchRouter()
    g = make_gateway(tmp_path, router=router)
    ctx = FakeContext()
    await g.cmd_codex(FakeUpdate(OWNER, message=FakeIncoming(text="/codex")), ctx)
    assert router.runtime == "codex" and "/claude" in ctx.bot.sent[-1]["text"]
    await g.cmd_claude(FakeUpdate(OWNER, message=FakeIncoming(text="/claude")), ctx)
    assert router.runtime == "claude" and "Claude" in ctx.bot.sent[-1]["text"]


async def test_status_card_is_marked_in_codex_mode(tmp_path):
    router = SwitchRouter()
    router.runtime = "codex"
    g = make_gateway(tmp_path, router=router)
    g.status_delay = 0
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="сделай пост")), ctx)
    assert any("🟢 Codex" in m["text"] for m in ctx.bot.sent)


async def test_status_shows_runtime_and_limits(tmp_path):
    g = make_gateway(tmp_path, router=SwitchRouter())
    worker.switch(str(OWNER), "codex", until=1_900_000_000.0)
    worker.save_limits("claude", {"status": "rejected", "resets_at": 1_900_000_000.0})
    worker.save_limits("codex", {"primary": {"used_percent": 46.0, "resets_at": 1_900_000_000.0}})
    ctx = FakeContext()
    await g.cmd_status(FakeUpdate(OWNER, message=FakeIncoming(text="/status")), ctx)
    text = ctx.bot.sent[-1]["text"]
    assert "Работает: 🟢 Codex" in text and "потом вернусь к Claude" in text
    assert "Claude: лимит исчерпан" in text and "Codex: 5 ч — 46%" in text


def test_bot_handles_updates_concurrently():
    """Иначе во время хода не дойдут «Подтвердить», /stop и /status: обработчик ждёт конца хода."""
    src = (Path(__file__).resolve().parents[1] / "integrations" / "telegram" / "gateway.py").read_text(encoding="utf-8")
    assert ".concurrent_updates(True)" in src
