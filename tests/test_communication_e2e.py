"""Сквозной сценарий скриншотов: настоящий роутер и HTTP-разрешение, фейковые CLI и Telegram."""
import asyncio
import os
import json
import sys
import pytest
from pathlib import Path
from types import SimpleNamespace

from runtime import events, sessions, spec, task_router
from runtime.approvals import ApprovalsServer
from integrations.telegram.gateway import Gateway
from tests.test_telegram import OWNER, FakeBot, FakeContext, FakeIncoming, FakeUpdate


async def test_approval_question_copy_and_stop_never_start_another_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "state" / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "state" / "sessions.json")
    monkeypatch.setattr(sessions, "ACTIVITY_PATH", tmp_path / "state" / "activity.json")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "state" / "specs")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "memory" / "episodes")
    monkeypatch.setattr(task_router, "ROOT", tmp_path)
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "approval_wait", "FAKE_APPROVAL_ROOT": str(tmp_path),
           "FAKE_CLAUDE_LOG": str(tmp_path / "calls.jsonl"), "JARVIS_REVIEW": "off"}
    cli = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]
    router = task_router.TaskRouter(env=env, claude_cmd=cli, budget_path=tmp_path / "budget.json", git_status=lambda: set())
    server = ApprovalsServer(timeout=5)
    await server.start(tmp_path)
    bot = FakeBot()
    ctx = FakeContext(bot)
    g = Gateway(owner_id=OWNER, root=tmp_path, router=router, approvals=server, status_delay=60)
    g.attach(bot)
    server.on_request(g.on_approval_request)
    run = asyncio.create_task(g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="посмотри идеи")), ctx))
    try:
        for _ in range(200):
            if server.pending and g._approval_messages:
                break
            await asyncio.sleep(0.02)
        assert server.pending and g._approval_messages
        msg = FakeIncoming(text="зачем тебе это?")
        msg.reply_to_message = SimpleNamespace(message_id=next(iter(g._approval_messages))[1], text="карточка")
        await g.on_message(FakeUpdate(OWNER, message=msg), ctx)
        assert "Посмотреть идеи недели" in bot.sent[-1]["text"]
        copy = FakeIncoming(text="Хочу запустить программу.\nКоманда: python …\nМожно, я это сделаю?")
        await g.on_message(FakeUpdate(OWNER, message=copy), ctx)
        await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming(text="/stop")), ctx)
        await asyncio.wait_for(run, 10)
        assert router.pending(OWNER) == 0 and server.pending == []
        assert sum("argv" in json.loads(line) for line in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()) == 1
        assert bot.sent[-1]["text"] == "Остановил текущую работу."
    finally:
        router.cancel_chat(OWNER)
        await server.stop()
        await asyncio.wait_for(run, 10)


async def test_stop_discards_album_before_it_becomes_a_job(tmp_path):
    from tests.test_telegram import make_gateway
    g = make_gateway(tmp_path)
    g.ALBUM_WAIT_SEC = 0.05
    ctx = FakeContext()
    upd = FakeUpdate(OWNER, message=FakeIncoming())
    await g._album_add(upd, ctx, "album", tmp_path / "photo.png", "старый запрос")
    await g.cmd_stop(upd, ctx)
    await asyncio.sleep(0.1)
    assert not g.router.jobs


async def test_python_handler_does_not_post_or_submit_after_stop(tmp_path, monkeypatch):
    import datetime as dt
    import threading
    from runtime import schedule_jobs
    from tests.test_telegram import make_gateway
    entered, release = threading.Event(), threading.Event()

    def work(*args):
        entered.set()
        release.wait(2)
        return schedule_jobs.Outcome(prompt="старое продолжение")

    monkeypatch.setattr(schedule_jobs, "run", work)
    g = make_gateway(tmp_path)
    control = schedule_jobs.ScheduleControl(str(OWNER))
    run = asyncio.create_task(g._run_handler({"id": "test", "handler": "morning"}, dt.datetime.now(), dt.datetime.now(), control))
    while not entered.is_set():
        await asyncio.sleep(0.01)
    control.cancel()
    release.set()
    await run
    assert not g.router.jobs and control.finished


async def test_outbox_drops_late_letter_of_cancelled_task(tmp_path, monkeypatch):
    from integrations.telegram import outbox
    monkeypatch.setenv("JARVIS_TASK_ID", "old")
    path = outbox.post(tmp_path, "позднее готово")
    outbox.cancel_tasks(tmp_path, {"old"})
    assert path not in outbox.pending(tmp_path)
    later = outbox.post(tmp_path, "ещё позднее готово")
    assert later not in outbox.pending(tmp_path)


async def test_outbox_rechecks_cancellation_after_network_wait(tmp_path, monkeypatch):
    from integrations.telegram import outbox, render
    from tests.test_telegram import make_gateway
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    monkeypatch.setenv("JARVIS_TASK_ID", "one")
    first = outbox.post(tmp_path, "first")
    monkeypatch.setenv("JARVIS_TASK_ID", "two")
    second = outbox.post(tmp_path, "second")
    monkeypatch.setattr(outbox, "pending", lambda root: [first, second])
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def send(bot, chat, text, **kwargs):
        sent.append(text)
        entered.set()
        await release.wait()
    monkeypatch.setattr(render, "send", send)
    delivery = asyncio.create_task(g.check_outbox())
    await entered.wait()
    outbox.cancel_tasks(tmp_path, {"two"})
    release.set()
    await delivery
    assert sent == ["first"]


@pytest.mark.parametrize("runtime", ["codex", "claude2"])
async def test_switch_callback_cannot_resume_after_stop(tmp_path, runtime):
    from tests.test_telegram import make_gateway
    g = make_gateway(tmp_path)
    g.router.offer_job = lambda chat, **kwargs: task_router.Job(prompt="старый запрос", runtime=runtime)
    entered, release = asyncio.Event(), asyncio.Event()
    async def edit(**kwargs):
        entered.set()
        await release.wait()
    ctx = FakeContext()
    upd = FakeUpdate(OWNER, message=FakeIncoming())
    callback = asyncio.create_task(g._switch_action(upd, ctx, SimpleNamespace(edit_message_text=edit), str(OWNER), runtime))
    await entered.wait()
    await g.cmd_stop(upd, ctx)
    release.set()
    await callback
    assert not g.router.jobs


async def test_stop_before_first_jobs_tick_consumes_existing_request(tmp_path):
    from tests.test_telegram import make_gateway
    from tests.test_jobs import put
    from integrations.jobs.runner import JobRunner
    g = make_gateway(tmp_path)
    g.router.cancel_chat = lambda chat: SimpleNamespace(task_ids=[])
    async def stopped(*args):
        return True
    g.router.wait_stopped = stopped
    g.approvals = None
    put(tmp_path, "old")
    await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming()), FakeContext())
    assert isinstance(g.jobs, JobRunner)
    spawned = []
    g.jobs.popen = lambda *a, **kw: spawned.append(1)
    await g.check_jobs()
    assert not spawned and g.jobs._records()[0]["status"] == "stopped"


async def test_normal_answer_stops_between_chunks(tmp_path, monkeypatch):
    from tests.test_telegram import make_gateway
    from integrations.telegram import render
    from runtime.claude_bridge import TurnResult
    g = make_gateway(tmp_path)
    ctx = FakeContext()
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    monkeypatch.setattr(render, "prepare", lambda text: ["first", "second"])
    async def send(*args, **kwargs):
        sent.append(args[2])
        entered.set()
        await release.wait()
    monkeypatch.setattr(render, "send", send)
    delivery = asyncio.create_task(g._deliver(ctx, OWNER, TurnResult("готово", "sid", False, 0, "ok")))
    await entered.wait()
    await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming()), ctx)
    release.set()
    await delivery
    assert sent == ["first"]


async def test_handler_control_kills_actual_child_process():
    from runtime.schedule_jobs import ScheduleControl
    control = ScheduleControl("test")
    run = asyncio.create_task(asyncio.to_thread(control.run, [sys.executable, "-c", "import time; time.sleep(60)"], capture_output=True, timeout=10))
    for _ in range(200):
        with control._lock:
            active = bool(control._procs)
        if active:
            break
        await asyncio.sleep(0.01)
    assert active
    control.cancel()
    result = await asyncio.wait_for(run, 5)
    assert result.returncode != 0 and not control._procs


async def test_stopped_untagged_outbox_does_not_retry_next_poll(tmp_path, monkeypatch):
    from integrations.telegram import outbox, render
    from tests.test_telegram import make_gateway
    monkeypatch.delenv("JARVIS_TASK_ID", raising=False)
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    outbox.post(tmp_path, "first")
    outbox.post(tmp_path, "second")
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def send(*args, **kwargs):
        sent.append(args[2])
        entered.set()
        await release.wait()
    monkeypatch.setattr(render, "send", send)
    delivery = asyncio.create_task(g.check_outbox())
    await entered.wait()
    await g.cmd_stop(FakeUpdate(OWNER, message=FakeIncoming()), FakeContext())
    release.set()
    await delivery
    await g.check_outbox()
    assert len(sent) == 1 and outbox.pending(tmp_path) == []
