"""Спецификация до исполнения (P2.1, аудит 2026-10-05).

Для крупной неоднозначной задачи JARVIS сначала присылает план из четырёх блоков и ждёт её «да».
Бот сам узнаёт план в ответе, сохраняет его для чата и прикрепляет к следующему ходу —
тому, где работа выполняется (по нему в P2.2 проверяет ревьюер). Модели ничего писать не нужно.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import events, spec

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]

PLAN = """Задача большая — сначала план.

**Сделаю:** комплект на неделю: 3 поста, 2 карусели, 2 рилса.
**Готово, когда:**
- в essa-ai/content/ 7 папок со статусом draft
- каждый текст прошёл textwriter → humaniser
**Не делаю:** не публикую, не трачу деньги.
**Вопросы:** нет.
"""


def test_plan_is_recognised():
    assert spec.is_spec(PLAN)
    assert spec.is_spec(PLAN.replace("**", "").replace("Сделаю:", "📋 Сделаю:"))


@pytest.mark.parametrize("text", [
    "Готово: пост в essa-ai/content/x/post.md",
    "Сделаю позже, когда скажешь.",
    "Готово, когда появится файл. Сделаю завтра.",      # слова есть, блоков-заголовков нет
    "",
    None,
])
def test_ordinary_answers_are_not_plans(text):
    assert not spec.is_spec(text)


def test_save_load_close(tmp_path, monkeypatch):
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    assert spec.load("1") is None
    spec.save("1", "t-plan", PLAN)
    got = spec.load("1")
    assert got["task_id"] == "t-plan" and got["text"] == PLAN.strip()
    spec.close("1", "t-work")
    assert spec.load("1") is None
    archived = json.loads((tmp_path / "specs" / "done" / "t-plan.json").read_text(encoding="utf-8"))
    assert archived["executed_by"] == "t-work"


def test_stale_plan_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    spec.save("1", "t-old", PLAN, now=1000.0)
    assert spec.load("1", now=1000.0 + spec.MAX_AGE_SEC + 1) is None
    assert spec.load("1", now=1000.0 + 60)["task_id"] == "t-old"


def test_turn_prompt_has_the_plan_rule():
    text = (Path(__file__).resolve().parents[1] / "runtime" / "jarvis-turn.md").read_text(encoding="utf-8")
    for heading in ("Сделаю:", "Готово, когда:", "Не делаю:", "Вопросы:"):
        assert heading in text
    assert "по расписанию" in text and "сразу" in text


# ---------- в очереди ----------

@pytest.fixture
def router(tmp_path, monkeypatch):
    from runtime import sessions, task_router
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "ok", "FAKE_CLAUDE_LOG": str(tmp_path / "calls.jsonl")}
    r = task_router.TaskRouter(env=env, claude_cmd=FAKE, budget_path=tmp_path / "budget.json",
                               git_status=lambda: set())
    r.tmp = tmp_path
    return r


async def _turn(router, chat, answer, context="chat"):
    from runtime import task_router
    router.env = {**router.env, "FAKE_CLAUDE_TEXT": answer}
    job = task_router.Job(prompt="задача", context=context)
    router.submit(chat, job)
    res = await asyncio.wait_for(job.result, 15)
    return job, res


def _events(router):
    return [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]


async def test_plan_then_work_links_the_plan_to_the_work_turn(router):
    plan_job, _ = await _turn(router, 5, PLAN)
    assert spec.load("5")["task_id"] == plan_job.task_id
    assert any(e["type"] == "spec_proposed" and e["task_id"] == plan_job.task_id for e in _events(router))

    work_job, _ = await _turn(router, 5, "Готово: семь папок в essa-ai/content/.")
    assert work_job.spec and work_job.spec["task_id"] == plan_job.task_id
    assert spec.load("5") is None                                      # план закрыт исполнением
    done = [e for e in _events(router) if e["type"] == "task_done" and e["task_id"] == work_job.task_id]
    assert done[0]["spec_task_id"] == plan_job.task_id


async def test_revised_plan_replaces_the_old_one(router):
    first, _ = await _turn(router, 6, PLAN)
    second, _ = await _turn(router, 6, PLAN.replace("3 поста", "5 постов"))
    assert spec.load("6")["task_id"] == second.task_id
    assert "5 постов" in spec.load("6")["text"]


async def test_plan_of_one_chat_does_not_leak_into_another(router):
    await _turn(router, 7, PLAN)
    other, _ = await _turn(router, 8, "ответ")
    assert other.spec is None and spec.load("7") is not None


async def test_scheduled_tasks_ignore_plans(router):
    await _turn(router, 9, PLAN)
    sched, _ = await _turn(router, 9, "Доброе утро", context="isolated")
    assert sched.spec is None and spec.load("9") is not None
