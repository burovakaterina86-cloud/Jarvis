"""Явные состояния задачи и /status по журналу (P2.4, аудит 2026-10-05).

queued → running → (waiting_approval → running) → (review → running при исправлении → review) →
done | failed | timeout | stopped. Роутер пишет `task_state` на каждом переходе; «ждёт подтверждения»
берётся из событий Approvals (в них есть task_id). /status читает хвост журнала.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import events, sessions, spec, task_state

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]


def write_events(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def ev(type_, ts, **kw):
    return {"type": type_, "ts": ts, **kw}


def test_snapshot_finds_active_queued_and_last(tmp_path):
    p = tmp_path / "events.jsonl"
    write_events(p, [
        ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="пост", state="queued", chat="1"),
        ev("task_state", "2026-10-05T10:00:01+00:00", task_id="a", task="пост", state="running", chat="1"),
        ev("task_state", "2026-10-05T10:05:00+00:00", task_id="a", task="пост", state="done", chat="1"),
        ev("task_done", "2026-10-05T10:05:00+00:00", task_id="a", review_verdict="pass"),
        ev("task_state", "2026-10-05T10:06:00+00:00", task_id="b", task="карусель", state="queued", chat="1"),
        ev("task_state", "2026-10-05T10:06:01+00:00", task_id="b", task="карусель", state="running", chat="1"),
        ev("approval_request", "2026-10-05T10:07:00+00:00", task_id="b", request_id="r1"),
        ev("task_state", "2026-10-05T10:08:00+00:00", task_id="c", task="рилс", state="queued", chat="1"),
        ev("task_state", "2026-10-05T10:09:00+00:00", task_id="z", task="чужой чат", state="running", chat="2"),
    ])
    snap = task_state.snapshot(p, chat="1")
    assert snap["active"]["task_id"] == "b" and snap["active"]["state"] == "waiting_approval"
    assert [q["task_id"] for q in snap["queued"]] == ["c"]
    assert snap["last"]["task_id"] == "a" and snap["last"]["state"] == "done"
    assert snap["last"]["review_verdict"] == "pass"


def test_approval_decision_returns_to_running(tmp_path):
    p = tmp_path / "events.jsonl"
    write_events(p, [
        ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="x", state="running", chat="1"),
        ev("approval_request", "2026-10-05T10:01:00+00:00", task_id="a"),
        ev("approval_decision", "2026-10-05T10:02:00+00:00", task_id="a", decision="allow"),
    ])
    assert task_state.snapshot(p, chat="1")["active"]["state"] == "running"


def test_empty_or_missing_journal(tmp_path):
    snap = task_state.snapshot(tmp_path / "нет.jsonl", chat="1")
    assert snap == {"active": None, "queued": [], "last": None}


def test_reads_only_the_tail_of_a_big_journal(tmp_path):
    p = tmp_path / "events.jsonl"
    filler = [ev("tool_use", "2026-10-05T09:00:00+00:00", tool="Read", summary="x" * 200)] * 6000
    write_events(p, filler + [ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="x",
                                 state="running", chat="1")])
    assert p.stat().st_size > task_state.TAIL_BYTES
    assert task_state.snapshot(p, chat="1")["active"]["task_id"] == "a"


def test_describe_for_the_owner():
    snap = {"active": {"task": "карусель", "state": "waiting_approval", "since": "2026-10-05T10:07:00+00:00"},
            "queued": [{"task": "рилс"}],
            "last": {"task": "пост", "state": "done", "since": "2026-10-05T10:05:00+00:00", "review_verdict": "pass"}}
    text = task_state.describe(snap, now="2026-10-05T10:10:00+00:00")
    assert "карусель" in text and "жду твоего «да»" in text and "3 мин" in text
    assert "В очереди: 1" in text and "рилс" in text
    assert "пост" in text and "готово" in text and "перепроверил" in text
    assert task_state.describe({"active": None, "queued": [], "last": None}) == "Сейчас ничем не занят."


# ---------- роутер пишет переходы ----------

@pytest.fixture
def router(tmp_path, monkeypatch):
    from runtime import task_router
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    monkeypatch.setattr(task_router.public_texts, "check", lambda *a, **kw: [])
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "ok", "FAKE_CLAUDE_LOG": str(tmp_path / "calls.jsonl"),
           "FAKE_REVIEW_COUNTER": str(tmp_path / "rc.txt"), "JARVIS_REVIEW": "on"}
    r = task_router.TaskRouter(env=env, claude_cmd=FAKE, budget_path=tmp_path / "budget.json",
                               git_status=lambda: set(), tests_runner=lambda: "ok")
    r.tmp = tmp_path
    return r


def states(router, task_id):
    rows = [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r["state"] for r in rows if r["type"] == "task_state" and r["task_id"] == task_id]


async def _go(router, scenario="ok", **job_kw):
    from runtime import task_router
    router.env = {**router.env, "FAKE_CLAUDE_SCENARIO": scenario}
    job = task_router.Job(prompt="задача", **job_kw)
    router.submit(4, job)
    await asyncio.wait_for(job.result, 20)
    return job


async def test_simple_turn_states(router):
    job = await _go(router)
    assert states(router, job.task_id) == ["queued", "running", "done"]


async def test_reviewed_turn_states(router):
    router.env = {**router.env, "FAKE_REVIEW_VERDICTS": "fix,pass"}
    job = await _go(router, scenario="ledger")
    assert states(router, job.task_id) == ["queued", "running", "review", "running", "review", "done"]


async def test_timeout_and_budget_states(router):
    job = await _go(router, scenario="sleep", timeout_sec=1)
    assert states(router, job.task_id)[-1] == "timeout"
    router.budget = 0
    job = await _go(router)
    assert states(router, job.task_id) == ["queued", "failed"]


async def test_task_state_events_carry_the_chat(router):
    job = await _go(router)
    rows = [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r.get("chat") for r in rows if r["type"] == "task_state"} == {"4"}
    assert "task_state" in events.TYPES


# ---------- /status в Telegram ----------

async def test_status_command_reads_the_journal(tmp_path):
    from tests.test_telegram import OWNER, FakeContext, FakeIncoming, FakeRouter, FakeUpdate, make_gateway
    write_events(tmp_path / "state" / "events.jsonl", [
        ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="пост про ИИ", state="running",
           chat=str(OWNER)),
    ])
    g = make_gateway(tmp_path, router=FakeRouter(pending=1))
    ctx = FakeContext()
    await g.cmd_status(FakeUpdate(OWNER, message=FakeIncoming(text="/status")), ctx)
    text = ctx.bot.sent[-1]["text"]
    assert "пост про ИИ" in text and "работаю" in text


# --- призрачные задачи: процесс упал посреди хода, в журнале остался «running» (аудит 2026-10-06) ---

def test_close_orphans_marks_unfinished_tasks_failed(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    monkeypatch.setattr(events, "EVENTS_PATH", p)
    write_events(p, [
        ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="пост", state="running", chat="1"),
        ev("task_state", "2026-10-05T10:01:00+00:00", task_id="a", task="пост", state="done", chat="1"),
        ev("task_state", "2026-10-05T10:02:00+00:00", task_id="b", task="карусель", state="running", chat="1"),
        ev("task_state", "2026-10-05T10:03:00+00:00", task_id="c", task="рилс", state="review", chat="1"),
        ev("task_state", "2026-10-05T10:04:00+00:00", task_id="d", task="в очереди", state="queued", chat="1"),
    ])
    assert task_state.snapshot(p, chat="1")["active"] is not None
    closed = task_state.close_orphans(p)
    assert sorted(closed) == ["b", "c", "d"]
    snap = task_state.snapshot(p, chat="1")
    assert snap["active"] is None and snap["queued"] == []
    assert snap["last"]["state"] == "failed"
    assert task_state.describe(snap).startswith("Сейчас ничем не занят")


def test_close_orphans_is_idempotent_and_ignores_finished(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    monkeypatch.setattr(events, "EVENTS_PATH", p)
    write_events(p, [ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="x", state="stopped", chat="1")])
    assert task_state.close_orphans(p) == []
    write_events(p, [ev("task_state", "2026-10-05T10:00:00+00:00", task_id="b", task="x", state="running", chat="1")])
    assert task_state.close_orphans(p) == ["b"]
    assert task_state.close_orphans(p) == []


def test_close_orphans_missing_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    assert task_state.close_orphans(tmp_path / "нет.jsonl") == []


def test_find_orphans_reports_names_and_states(tmp_path):
    p = tmp_path / "events.jsonl"
    write_events(p, [
        ev("task_state", "2026-10-05T10:00:00+00:00", task_id="a", task="пост", state="done", chat="1"),
        ev("task_state", "2026-10-05T10:02:00+00:00", task_id="b", task="карусель", state="running", chat="1"),
        ev("task_state", "2026-10-05T10:04:00+00:00", task_id="d", task="в очереди", state="queued", chat="1"),
    ])
    found = task_state.find_orphans(p)
    assert [(o["task_id"], o["task"], o["state"]) for o in found] == [
        ("b", "карусель", "running"), ("d", "в очереди", "queued")]
