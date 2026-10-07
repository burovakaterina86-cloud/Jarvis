"""Свежая сессия после паузы с кратким брифом (P3.1, аудит 2026-10-05).

Режимы контекста хода: `chat` продолжает сессию (fork), `isolated` — без истории (расписание,
проверяющий), `brief` — новая сессия со сводкой последних задач из `memory/episodes/`.
Чат молчал дольше JARVIS_SESSION_IDLE_HOURS — следующий ход идёт в `brief`.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import events, sessions, spec

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]
HOUR = 3600.0


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def router(tmp_path, monkeypatch):
    from runtime import task_router
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(sessions, "ACTIVITY_PATH", tmp_path / "session_activity.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    monkeypatch.delenv("JARVIS_SESSION_IDLE_HOURS", raising=False)
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "ok", "FAKE_CLAUDE_LOG": str(tmp_path / "calls.jsonl"),
           "JARVIS_REVIEW": "off", "TELEGRAM_OWNER_ID": "1"}
    clock = Clock()
    r = task_router.TaskRouter(env=env, claude_cmd=FAKE, budget_path=tmp_path / "budget.json",
                               git_status=lambda: set(), clock=clock)
    r.tmp, r.clock_ = tmp_path, clock
    return r


def episodes(router, rows):
    path = router.tmp / "episodes" / "2026-10.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


async def turn(router, chat=1, prompt="привет", context="chat"):
    from runtime import task_router
    job = task_router.Job(prompt=prompt, context=context)
    router.submit(chat, job)
    return job, await asyncio.wait_for(job.result, 15)


def calls(router):
    rows = [json.loads(x) for x in (router.tmp / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if "argv" in r]


async def test_short_pause_keeps_the_session(router):
    await turn(router)
    router.clock_.t += 2 * HOUR
    _, res = await turn(router)
    assert "--resume" in calls(router)[-1]["argv"]
    assert not res.brief


async def test_long_pause_starts_fresh_session_with_brief(router):
    await turn(router)
    episodes(router, [
        {"date": "2026-10-04T10:00:00+03:00", "task": "карусель", "status": "ok", "context": "chat",
         "request": "сделай карусель про ИИ", "result": "Готово: 9 слайдов", "files": ["essa-ai/content/x/carousel.md"]},
        {"date": "2026-10-04T08:00:00+03:00", "task": "по расписанию: morning", "status": "ok",
         "context": "isolated", "request": "утро", "result": "Доброе утро"},
        {"date": "2026-10-04T11:00:00+03:00", "task": "пост", "status": "ok", "context": "chat",
         "request": "пост про промпты", "result": "Пост готов"},
    ])
    router.clock_.t += 9 * HOUR
    job, res = await turn(router, prompt="продолжим?")
    last = calls(router)[-1]
    assert "--resume" not in last["argv"]
    tail = last["stdin_tail"]
    assert "продолжим?" in tail
    assert res.brief and not res.new_session
    assert sessions.get(1) == "sess-new-0001"


async def test_brief_text_lists_recent_chat_tasks_without_schedule(router):
    from runtime import task_router
    episodes(router, [
        {"date": f"2026-10-04T0{i}:00:00+03:00", "task": f"задача {i}", "status": "ok", "context": "chat",
         "request": f"запрос {i}", "result": f"итог {i}"} for i in range(1, 6)
    ] + [{"date": "2026-10-04T09:30:00+03:00", "task": "по расписанию: morning", "context": "isolated",
          "status": "ok", "request": "утро", "result": "Доброе утро"}])
    job = task_router.Job(prompt="что дальше?")
    text = router._brief_prompt(job, 9.5)
    assert "9 ч" in text or "9.5 ч" in text
    assert "итог 5" in text and "итог 3" in text and "итог 2" not in text   # три последних
    assert "Доброе утро" not in text
    assert text.rstrip().endswith("что дальше?")


async def test_brief_carries_a_pending_plan(router):
    from runtime import task_router
    job = task_router.Job(prompt="да")
    job.spec = {"task_id": "p1", "text": "**Сделаю:** 7 постов"}
    assert "7 постов" in router._brief_prompt(job, 10)


async def test_unknown_activity_does_not_reset(router):
    sessions.set(1, "old-sid")          # сессия есть, когда был последний ход — неизвестно
    router.clock_.t += 100 * HOUR
    _, res = await turn(router)
    argv = calls(router)[-1]["argv"]
    assert argv[argv.index("--resume") + 1] == "old-sid" and not res.brief


async def test_idle_limit_from_env_and_zero_disables(router, monkeypatch):
    from runtime import task_router
    monkeypatch.setenv("JARVIS_SESSION_IDLE_HOURS", "0")
    r = task_router.TaskRouter(clock=router.clock_)
    assert r.idle_hours == 0
    monkeypatch.setenv("JARVIS_SESSION_IDLE_HOURS", "мусор")
    assert task_router.TaskRouter().idle_hours == task_router.DEFAULT_IDLE_HOURS == 8


async def test_disabled_idle_never_resets(router):
    router.idle_hours = 0
    await turn(router)
    router.clock_.t += 50 * HOUR
    _, res = await turn(router)
    assert "--resume" in calls(router)[-1]["argv"] and not res.brief


async def test_scheduled_tasks_neither_reset_nor_count_as_activity(router):
    await turn(router)
    router.clock_.t += 7 * HOUR
    await turn(router, context="isolated")          # утро по расписанию — не её активность
    router.clock_.t += 2 * HOUR                     # от её последнего хода прошло 9 ч
    _, res = await turn(router)
    assert res.brief


async def test_episode_records_context_and_task_done_records_mode(router):
    await turn(router)
    router.clock_.t += 9 * HOUR
    job, _ = await turn(router)
    ep = json.loads((router.tmp / "episodes").glob("*.jsonl").__next__().read_text(encoding="utf-8").splitlines()[-1])
    assert ep["context"] == "chat"
    done = [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    done = [d for d in done if d["type"] == "task_done" and d["task_id"] == job.task_id][0]
    assert done["session_mode"] == "brief"


def test_activity_store(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "ACTIVITY_PATH", tmp_path / "a.json")
    assert sessions.last_active(5) is None
    sessions.touch(5, 123.0)
    assert sessions.last_active("5") == 123.0
