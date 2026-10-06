"""Быстрая полоса: вопрос во время долгой задачи получает ответ сразу, просьба идёт в обычную очередь."""
from __future__ import annotations

import json

import pytest

from runtime import side_lane
from tests.test_telegram import OWNER, FakeContext, FakeIncoming, FakeRouter, FakeUpdate, make_gateway


@pytest.mark.parametrize("text", ["ты здесь?", "Как там монтаж?", "что с роликом", "сколько ещё ждать?", "Готово?",
                                  "когда будет готов рилс", "статус", "алло"])
def test_questions_in_flight_are_recognised(text):
    assert side_lane.looks_like_question(text)


@pytest.mark.parametrize("text", ["сделай карусель про агентов", "смонтируй рилс из inbox/x.mp4", "/status", "",
                                  "напиши пост", "x" * 200 + "?", "первая строка?\nвторая строка"])
def test_work_requests_and_long_texts_are_not_side_questions(text):
    assert not side_lane.looks_like_question(text)


def test_model_can_hand_a_request_back_to_the_normal_queue():
    assert side_lane.wants_queue("ОЧЕРЕДЬ") and side_lane.wants_queue("  очередь.") and not side_lane.wants_queue("Идёт сборка")


def test_context_shows_active_task_recent_steps_and_background_jobs(tmp_path):
    events = tmp_path / "state" / "events.jsonl"
    events.parent.mkdir(parents=True)
    rows = [{"type": "task_state", "state": "running", "task_id": "t1", "task": "монтаж рилса", "chat": str(OWNER),
             "ts": "2026-10-06T09:30:00+00:00"},
            {"type": "tool_use", "task_id": "t1", "task": "монтаж рилса", "tool": "Bash"},
            {"type": "assistant_message", "task_id": "t1", "task": "монтаж рилса", "text": "Собираю рилс, минут шесть."}]
    events.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    jobs_dir = tmp_path / "state" / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "j.json").write_text(json.dumps({"id": "j", "title": "Сборка рилса", "status": "running", "queued_at": 1}),
                                     encoding="utf-8")
    text = side_lane.build_prompt(tmp_path, OWNER, "ты здесь?")
    assert "Основная задача: «монтаж рилса»" in text and "инструмент Bash" in text and "Собираю рилс" in text
    assert "«Сборка рилса» — идёт" in text and text.rstrip().endswith("ты здесь?")


def test_context_without_any_task_says_so(tmp_path):
    assert "Основной задачи сейчас нет." in side_lane.context(tmp_path, OWNER)


def test_side_lane_is_read_only_light_and_has_its_own_prompt():
    o = side_lane.OPTIONS
    assert o.read_only and o.persist is False and o.browser is False and o.max_turns <= 6
    assert o.settings.name == "reviewer-settings.json" and o.prompt_file.is_file()
    assert "ОЧЕРЕДЬ" in o.prompt_file.read_text(encoding="utf-8")


# ---------- бот ----------

async def test_question_during_a_long_task_goes_to_its_own_lane_and_is_answered(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="Сборка идёт, примерно ещё три минуты.", pending=1))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="ты здесь?")), ctx)
    (_chat, job), = g.router.jobs
    assert job.queue == "side" and job.context == "isolated" and job.options is side_lane.OPTIONS
    assert "Что сейчас происходит" in job.prompt and "ты здесь?" in job.prompt
    assert any("ещё три минуты" in m["text"] for m in ctx.bot.sent)
    assert not any("Секунду, я ещё занят" in m["text"] for m in ctx.bot.sent)     # не «подожди в очереди»


async def test_request_phrased_as_a_question_is_handed_back_to_the_normal_queue(tmp_path):
    g = make_gateway(tmp_path, router=FakeRouter(answer="ОЧЕРЕДЬ", pending=1, position=1))
    ctx = FakeContext()
    await g.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="что с роликом, можешь ещё карусель сделать?")), ctx)
    queues = [job.queue for _chat, job in g.router.jobs]
    assert queues == ["side", None]                                    # сначала быстрая, потом обычная
    assert any("Секунду, я ещё занят" in m["text"] for m in ctx.bot.sent)


async def test_nothing_changes_when_the_bot_is_idle_or_the_message_is_work(tmp_path):
    idle = make_gateway(tmp_path, router=FakeRouter(pending=0))
    await idle.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="ты здесь?")), FakeContext())
    assert [job.queue for _c, job in idle.router.jobs] == [None]
    busy = make_gateway(tmp_path, router=FakeRouter(pending=1, position=1))
    await busy.on_message(FakeUpdate(OWNER, message=FakeIncoming(text="сделай карусель про агентов")), FakeContext())
    assert [job.queue for _c, job in busy.router.jobs] == [None]
