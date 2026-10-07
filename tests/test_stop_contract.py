"""Стоп отменяет существующие очереди, но разрешает новый явный запрос."""
import asyncio
import json

import pytest

from runtime import events, spec, task_router, worker
from runtime.claude_bridge import TurnResult


@pytest.fixture
def router(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    return task_router.TaskRouter(budget_path=tmp_path / "budget.json", git_status=lambda: set())


async def test_stop_clears_all_chat_queues_and_allows_new_request(router, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def run(key, job):
        calls.append(job.prompt)
        started.set()
        if job.prompt == "active":
            await release.wait()
        return TurnResult("готово", None, False, None, "ok", None)

    monkeypatch.setattr(router, "_run", run)
    active, queued, side = (task_router.Job(prompt=p) for p in ("active", "queued", "side"))
    side.queue = "side"
    router.submit(1, active)
    await started.wait()
    router.submit(1, queued)
    router.submit(1, side)
    report = router.cancel_chat(1)
    release.set()
    assert await router.wait_stopped(report.task_ids, timeout=1)
    assert [j.result.result().status for j in (active, queued, side)] == ["stopped"] * 3
    assert calls == ["active"]
    new = task_router.Job(prompt="new")
    router.submit(1, new)
    assert (await new.result).status == "ok"
    assert calls == ["active", "new"]


async def test_stop_does_not_cancel_other_chat_and_drops_only_own_deferred(router, monkeypatch):
    monkeypatch.setattr(router, "_run", lambda *a: asyncio.sleep(0, result=TurnResult("", None, False, None, "ok", None)))
    a, b = task_router.Job("a"), task_router.Job("b")
    router.submit(1, a)
    router.submit(2, b)
    worker.defer(1, 0, "old", "old")
    worker.defer(2, 0, "other", "other")
    worker.save_offer(1, {"prompt": "old"})
    router.cancel_chat(1)
    assert (await a.result).status == "stopped"
    assert (await b.result).status == "ok"
    assert worker.load_offer(1) is None
    assert [r["chat"] for r in worker.due_deferred()] == ["2"]


def test_stopped_background_requests_never_spawn_or_send_late_done(tmp_path):
    from integrations import jobs
    from integrations.jobs.runner import JobRunner
    req = tmp_path / "jobs" / "requests" / "old.json"
    req.parent.mkdir(parents=True)
    req.write_text(json.dumps({"title": "old", "argv": ["-m", "integrations.radar"], "chat": "1"}), encoding="utf-8")
    spawned, mail = [], []
    runner = JobRunner(tmp_path, post=lambda *a: mail.append(a), popen=lambda *a, **kw: spawned.append(a))
    assert runner.cancel_chat("1") == ["old"]
    runner.tick()
    runner._finish(runner._records()[0], 0)
    assert not spawned and not mail


async def test_stop_during_review_never_launches_fix(router, monkeypatch):
    from runtime import review
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    job = task_router.Job("review")
    job.chat, job.run_key = "1", "1"

    async def timed(*args, **kwargs):
        calls.append(args[2])
        entered.set()
        await release.wait()
        return TurnResult("", None, False, None, "ok", None,
                          structured={"verdict": "fix", "problems": ["нет файла"], "checked": []})

    monkeypatch.setattr(router, "_timed", timed)
    router._active["1"] = job
    check = asyncio.create_task(router._review("1", job, TurnResult("готово", None, False, None, "ok", None), 1))
    await entered.wait()
    router.cancel_chat(1)
    release.set()
    assert (await check).status == "stopped"
    assert len(calls) == 1
