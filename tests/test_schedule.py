"""Планировщик внутри бота: задачи по расписанию с догоном пропущенного (2026-09-25)."""
import datetime as dt
import json

from runtime import schedule as sch
from tests.test_telegram import OWNER, FakeBot, FakeRouter, make_gateway

MON = dt.date(2026, 9, 28)   # понедельник


def at(day: dt.date, hhmm: str) -> dt.datetime:
    h, m = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m))


DAILY = {"id": "morning", "kind": "daily", "at": "08:00", "catch_up_hours": 4}
WEEKLY = {"id": "radar", "kind": "weekly", "weekday": 0, "at": "09:00"}


def test_daily_slot_and_due():
    assert sch.last_slot(DAILY, at(MON, "07:59")) == at(MON - dt.timedelta(days=1), "08:00")
    assert sch.last_slot(DAILY, at(MON, "08:00")) == at(MON, "08:00")
    assert sch.is_due(DAILY, at(MON, "08:05"), last_run=None)
    assert not sch.is_due(DAILY, at(MON, "08:05"), last_run=at(MON, "08:00").isoformat())


def test_daily_catch_up_window():
    # бот был выключен в 8:00 — в 11:00 доброе утро ещё уместно, в 13:00 уже нет
    assert sch.is_due(DAILY, at(MON, "11:00"), last_run=None)
    assert not sch.is_due(DAILY, at(MON, "13:00"), last_run=None)


def test_weekly_catches_up_later_in_the_week():
    assert sch.last_slot(WEEKLY, at(MON + dt.timedelta(days=2), "10:00")) == at(MON, "09:00")
    assert sch.is_due(WEEKLY, at(MON + dt.timedelta(days=2), "10:00"), last_run=at(MON - dt.timedelta(days=7), "09:00").isoformat())
    assert not sch.is_due(WEEKLY, at(MON, "08:59"), last_run=at(MON - dt.timedelta(days=7), "09:00").isoformat())
    assert not sch.is_due(WEEKLY, at(MON, "12:00"), last_run=at(MON, "09:00").isoformat())


def test_first_start_does_not_fire_weekly_backlog_older_than_slot():
    # нет записи о запуске — считаем, что не запускалось; сработает один раз на ближайший прошедший слот
    assert sch.is_due(WEEKLY, at(MON, "09:30"), last_run=None)


def test_config_in_repo_has_her_three_tasks():
    tasks = {t["id"]: t for t in sch.load_tasks()}
    assert tasks["morning"]["at"] == "08:00" and tasks["morning"]["kind"] == "daily"
    assert tasks["reel-radar"]["weekday"] == 0 and tasks["reel-radar"]["kind"] == "weekly"
    assert tasks["corrections-review"]["kind"] == "weekly"
    for t in tasks.values():
        assert sch.prompt_for(t).strip(), t["id"]


async def test_gateway_runs_due_task_once_and_delivers_to_owner(tmp_path):
    prompts = tmp_path / "runtime" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "morning.md").write_text("Собери утреннее сообщение.", encoding="utf-8")
    cfg = tmp_path / "runtime" / "schedule.json"
    cfg.write_text(json.dumps([{**DAILY, "prompt": "runtime/prompts/morning.md"}]), encoding="utf-8")
    router = FakeRouter(answer="Доброе утро!")
    g = make_gateway(tmp_path, router=router)
    bot = FakeBot()
    g.attach(bot)

    started = await g.check_schedule(now=at(MON, "08:01"))
    assert started == ["morning"]
    await g.schedule_tasks_done()
    assert router.jobs and router.jobs[0][0] == OWNER
    assert "Собери утреннее сообщение." in router.jobs[0][1].prompt
    assert any("Доброе утро!" in m["text"] for m in bot.sent)
    assert await g.check_schedule(now=at(MON, "08:30")) == []          # второй раз не запускает
    state = json.loads((tmp_path / "state" / "schedule.json").read_text(encoding="utf-8"))
    assert state["morning"] == at(MON, "08:00").isoformat()


async def test_no_owner_no_runs(tmp_path):
    g = make_gateway(tmp_path, owner_id=None)
    g.attach(FakeBot())
    assert await g.check_schedule(now=at(MON, "08:01")) == []


async def test_scheduled_task_runs_isolated_with_its_own_timeout(tmp_path):
    """P1.4: фон не продолжает её разговор; P1.3: предел времени задаётся в schedule.json."""
    prompts = tmp_path / "runtime" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "morning.md").write_text("Собери утреннее сообщение.", encoding="utf-8")
    (tmp_path / "runtime" / "schedule.json").write_text(json.dumps(
        [{**DAILY, "prompt": "runtime/prompts/morning.md", "timeout_min": 20}]), encoding="utf-8")
    router = FakeRouter(answer="Доброе утро!")
    g = make_gateway(tmp_path, router=router)
    g.attach(FakeBot())
    await g.check_schedule(now=at(MON, "08:01"))
    await g.schedule_tasks_done()
    job = router.jobs[0][1]
    assert job.context == "isolated"
    assert job.timeout_sec == 20 * 60


async def test_scheduled_task_without_timeout_uses_router_default(tmp_path):
    prompts = tmp_path / "runtime" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "morning.md").write_text("Собери утреннее сообщение.", encoding="utf-8")
    (tmp_path / "runtime" / "schedule.json").write_text(json.dumps(
        [{**DAILY, "prompt": "runtime/prompts/morning.md"}]), encoding="utf-8")
    router = FakeRouter(answer="Доброе утро!")
    g = make_gateway(tmp_path, router=router)
    g.attach(FakeBot())
    await g.check_schedule(now=at(MON, "08:01"))
    await g.schedule_tasks_done()
    assert router.jobs[0][1].timeout_sec is None


def test_final_line_for_timeout_is_human():
    from types import SimpleNamespace

    from integrations.telegram.gateway import _final_line
    reporter = SimpleNamespace(clock=lambda: 100.0, started=40.0)
    line = _final_line(SimpleNamespace(status="timeout"), reporter)
    assert "времени" in line and "timeout" not in line
