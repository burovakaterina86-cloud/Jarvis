"""Недельный контент-план по расписанию: какая неделя, повторная трата, отказы, задание для Claude."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from runtime import schedule_jobs as jobs

ROOT = Path(__file__).resolve().parents[1]


def _root(tmp_path):
    (tmp_path / "runtime" / "prompts").mkdir(parents=True)
    shutil.copy(ROOT / "runtime" / "prompts" / "weekly-content-plan.md", tmp_path / "runtime" / "prompts")
    return tmp_path


def test_plan_week_is_next_monday_from_sunday_and_current_for_catch_up():
    assert jobs.plan_monday(dt.datetime(2026, 10, 11, 19, 0)) == dt.date(2026, 10, 12)   # воскресенье → завтра
    assert jobs.plan_monday(dt.datetime(2026, 10, 12, 10, 0)) == dt.date(2026, 10, 12)   # пн: пропущенное воскресенье
    assert jobs.plan_monday(dt.datetime(2026, 10, 13, 10, 0)) == dt.date(2026, 10, 12)
    assert jobs.plan_monday(dt.datetime(2026, 10, 14, 10, 0)) == dt.date(2026, 10, 19)   # ср: уже следующая


def test_success_returns_claude_task_with_week_folder(tmp_path):
    root = _root(tmp_path)
    calls = []
    out = jobs.content_plan(root, dt.datetime(2026, 10, 18, 19, 0), runner=lambda r, w: calls.append(w) or (0, "готово"))
    assert calls == ["essa-ai/content-plan/weeks/2026-10-19"]
    assert "essa-ai/content-plan/weeks/2026-10-19" in out.prompt and "2026-10-19" in out.prompt
    assert "{{" not in out.prompt and not out.text
    assert "📎 essa-ai/content-plan/weeks/2026-10-19/plan-2026-10-19.html" in out.prompt
    assert "history.json" in out.prompt and "не публикуй" in out.prompt.lower()


def test_existing_plan_is_not_collected_twice(tmp_path):
    root = _root(tmp_path)
    week = root / "essa-ai" / "content-plan" / "weeks" / "2026-10-12"
    week.mkdir(parents=True)
    (week / "plan-2026-10-12.html").write_text("<html></html>", encoding="utf-8")

    def boom(r, w):
        raise AssertionError("платный сбор не должен запускаться")

    out = jobs.content_plan(root, dt.datetime(2026, 10, 11, 19, 0), runner=boom)
    assert "уже собран" in out.text and not out.prompt


def test_failures_are_explained_to_owner_without_claude(tmp_path):
    root = _root(tmp_path)
    no_key = jobs.content_plan(root, dt.datetime(2026, 10, 11, 19, 0), runner=lambda r, w: (2, "нет ключа в окружении: APIFY_TOKEN"))
    assert "не начат" in no_key.text and "APIFY_TOKEN" in no_key.text and not no_key.prompt
    limit = jobs.content_plan(root, dt.datetime(2026, 10, 11, 19, 0), runner=lambda r, w: (3, "Apify HTTP 403"))
    assert "Settings → Limits" in limit.text and "STOPPED.md" in limit.text and not limit.prompt


def test_handler_is_registered():
    assert jobs.HANDLERS["content_plan"] is jobs.content_plan


def test_prompt_forbids_ad_hoc_python_and_names_allowed_commands(tmp_path):
    root = _root(tmp_path)
    out = jobs.content_plan(root, dt.datetime(2026, 10, 18, 19, 0), runner=lambda r, w: (0, "ok"))
    for must in ("никаких самодельных скриптов", "reels_short.txt", "integrations.content_plan show",
                 "integrations.content_plan check", "инструментом Write"):
        assert must in out.prompt, must


def test_guard_lets_plan_commands_through_but_asks_for_ad_hoc_python(tmp_path):
    from tests import test_guard as g
    root = tmp_path
    (root / "state" / "secrets").mkdir(parents=True)
    ok = [("Bash", {"command": f"python -m integrations.content_plan {cmd} essa-ai/content-plan/weeks/x"})
          for cmd in ("show", "check", "slides", "render", "weekly")]
    ok += [("Read", {"file_path": str(root / "essa-ai/content-plan/weeks/x/reels_short.txt")}),
           ("Write", {"file_path": str(root / "essa-ai/content-plan/weeks/x/reels.json"), "content": "{}"})]
    for tool, inp in ok:
        assert g.decide(g.ev(tool, **inp), root, env={"JARVIS_TASK_ID": "t"}).action == "allow", (tool, inp)
    adhoc = g.decide(g.ev("Bash", command="cd essa-ai/content-plan/weeks/x && python - <<'E'\nprint(1)\nE"), root,
                     env={"JARVIS_TASK_ID": "t"})
    assert adhoc.action == "ask"        # поэтому в задании сказано: самодельных скриптов не писать
