"""Переключение на Codex в роутере (P4.1e): лимит Claude → предложение; кнопка → Codex со сводкой;
сброс лимита → снова Claude. Швы: фейковый claude и фейковый codex."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import events, sessions, spec, worker

FAKE_CLAUDE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]
FAKE_CODEX = [sys.executable, str(Path(__file__).parent / "fake_codex" / "fake_codex.py")]


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def router(tmp_path, monkeypatch):
    from runtime import task_router
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "ok", "FAKE_CLAUDE_LOG": str(tmp_path / "claude.jsonl"),
           "FAKE_CODEX_SCENARIO": "ok", "FAKE_CODEX_LOG": str(tmp_path / "codex.jsonl"),
           "JARVIS_REVIEW": "off", "JARVIS_CODEX": "on"}
    clock = Clock()
    ready = {"ok": True}

    async def codex_check():
        return (True, "") if ready["ok"] else (False, "Codex не запускаю: подтверди /hooks")

    r = task_router.TaskRouter(env=env, claude_cmd=FAKE_CLAUDE, codex_cmd=FAKE_CODEX,
                               budget_path=tmp_path / "budget.json", git_status=lambda: set(),
                               clock=clock, codex_check=codex_check, limits_reader=lambda tid: None)
    r.tmp, r.clock_, r.ready = tmp_path, clock, ready
    return r


def calls(router, who):
    path = router.tmp / f"{who}.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [r for r in rows if "argv" in r]


async def submit(router, job, chat=1):
    router.submit(chat, job)
    return await asyncio.wait_for(job.result, 20)


async def _limited(router, chat=1):
    from runtime import task_router
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "rate_limit"}
    res = await submit(router, task_router.Job(prompt="сделай комплект про ИИ", task="комплект про ИИ"), chat)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "ok"}
    return res


async def test_claude_limit_offers_codex(router):
    res = await _limited(router)
    assert res.status == "rate_limited"
    assert res.switch_offer["task"] == "комплект про ИИ" and res.switch_offer["prompt"] == "сделай комплект про ИИ"
    assert worker.load_offer("1")["task"] == "комплект про ИИ"


async def test_no_offer_when_codex_is_switched_off(router):
    router.env = {**router.env, "JARVIS_CODEX": "off"}
    res = await _limited(router)
    assert res.switch_offer is None and worker.load_offer("1") is None


async def test_button_runs_codex_with_handoff_and_marks_the_answer(router):
    await _limited(router)
    job = router.offer_job(1, until=router.clock_.t + 3600)
    assert job.runtime == "codex" and "сделай комплект про ИИ" in job.prompt and "Claude" in job.prompt
    res = await submit(router, job)
    assert res.status == "ok" and res.runtime == "codex"
    assert res.text.endswith("🟢 Сделано в Codex")
    assert len(calls(router, "codex")) == 1
    assert sessions.get("1:codex") == "thread-new-0001" and worker.load_offer("1") is None


async def test_following_messages_stay_in_codex_until_reset(router):
    from runtime import task_router
    await _limited(router)
    await submit(router, router.offer_job(1, until=router.clock_.t + 3600))
    res = await submit(router, task_router.Job(prompt="ещё одно"))
    assert res.runtime == "codex"
    argv = calls(router, "codex")[-1]["argv"]
    assert argv[:3] == ["exec", "resume", "thread-new-0001"]


async def test_back_to_claude_after_reset_with_summary(router):
    from runtime import task_router
    await _limited(router)
    await submit(router, router.offer_job(1, until=router.clock_.t + 3600))
    router.clock_.t += 3601
    res = await submit(router, task_router.Job(prompt="продолжаем"))
    assert res.runtime == "claude" and res.switched_back
    assert "Codex" in calls(router, "claude")[-1]["stdin_tail"]
    res = await submit(router, task_router.Job(prompt="и ещё"))
    assert not res.switched_back                                    # говорим один раз


async def test_codex_not_ready_means_no_codex_run(router):
    router.ready["ok"] = False
    await _limited(router)
    res = await submit(router, router.offer_job(1, until=None))
    assert res.status == "error" and res.error == "codex_not_ready" and "/hooks" in res.text
    assert calls(router, "codex") == []


async def test_manual_switch_commands(router):
    from runtime import task_router
    router.set_runtime(1, "codex")
    res = await submit(router, task_router.Job(prompt="привет"))
    assert res.runtime == "codex"
    router.set_runtime(1, "claude")
    res = await submit(router, task_router.Job(prompt="привет"))
    assert res.runtime == "claude" and router.runtime_for(1) == "claude"


async def test_reviewer_in_codex_mode_is_codex(router):
    from runtime import task_router
    router.env = {**router.env, "JARVIS_REVIEW": "on", "FAKE_CODEX_SCENARIO": "schema", "FAKE_CODEX_VERDICT": "pass"}
    router.set_runtime(1, "codex")
    res = await submit(router, task_router.Job(prompt="сделай пост"))
    review_call = calls(router, "codex")[-1]["argv"]
    assert "--output-schema" in review_call and 'sandbox_mode="read-only"' in review_call
    assert res.review["verdict"] == "pass" and "проверял Codex" in res.text
    assert calls(router, "claude") == []


async def test_codex_limits_are_saved(router):
    from runtime import task_router
    router.limits_reader = lambda tid: {"primary": {"used_percent": 46.0, "resets_at": 1}}
    router.set_runtime(1, "codex")
    await submit(router, task_router.Job(prompt="привет"))
    assert worker.limits()["codex"]["primary"]["used_percent"] == 46.0


async def test_stop_reaches_codex(router):
    from runtime import task_router
    router.env = {**router.env, "FAKE_CODEX_SCENARIO": "sleep"}
    router.set_runtime(1, "codex")
    job = task_router.Job(prompt="долго")
    router.submit(1, job)
    for _ in range(100):
        await asyncio.sleep(0.05)
        if calls(router, "codex"):
            break
    assert router.stop(1) is True
    res = await asyncio.wait_for(job.result, 10)
    assert res.status == "stopped"


async def test_task_done_records_runtime(router):
    from runtime import task_router
    router.set_runtime(1, "codex")
    job = task_router.Job(prompt="привет")
    await submit(router, job)
    rows = [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    done = [r for r in rows if r["type"] == "task_done" and r["task_id"] == job.task_id][0]
    assert done["runtime"] == "codex"


async def test_offer_lists_files_claude_already_changed(router):
    from runtime import task_router
    states = iter([set(), {"essa-ai/content/x/post.md"}])
    router.git_status = lambda: next(states)
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": "rate_limit"}
    res = await submit(router, task_router.Job(prompt="комплект", task="комплект"))
    assert res.switch_offer["files"] == ["essa-ai/content/x/post.md"]
    job = router.offer_job(1)
    assert "essa-ai/content/x/post.md" in job.prompt


# ---------- её поправка 2026-10-05: «он теряет контекст», ложное «контекст потерялся» ----------

async def test_first_turn_is_not_reported_as_lost_context(router):
    from runtime import task_router
    res = await submit(router, task_router.Job(prompt="привет"))
    assert res.new_session is False                       # терять было нечего
    res = await submit(router, task_router.Job(prompt="утро", context="isolated"))
    assert res.new_session is False


async def test_manual_switch_to_codex_carries_a_summary(router):
    from runtime import task_router
    (router.tmp / "episodes").mkdir(parents=True)
    (router.tmp / "episodes" / "2026-10.jsonl").write_text(json.dumps(
        {"date": "2026-10-05T20:00:00+03:00", "context": "chat", "status": "ok",
         "request": "сделай карусель про промпты", "result": "Готово: 9 слайдов"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    router.set_runtime(1, "codex")
    res = await submit(router, task_router.Job(prompt="что мы делали?"))
    tail = calls(router, "codex")[0]["stdin_tail"]
    assert "сделай карусель про промпты" in tail and "что мы делали?" in tail
    assert res.new_session is False
    await submit(router, task_router.Job(prompt="ещё"))
    assert "сделай карусель" not in calls(router, "codex")[1]["stdin_tail"]   # дальше — своя сессия
