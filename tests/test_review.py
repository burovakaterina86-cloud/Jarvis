"""Независимая проверка результата (P2.2, аудит 2026-10-05). Шов — фейковый claude: в режиме
`--json-schema` он отвечает вердиктами по очереди из FAKE_REVIEW_VERDICTS."""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime import claude_bridge, events, review, spec

REPO = Path(__file__).resolve().parents[1]
FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude" / "fake_claude.py")]


def job_res(files=(), status="ok", context="chat", plan=None, text="Готово."):
    job = SimpleNamespace(prompt="да, делай", context=context, spec=plan, task_id="t1")
    res = SimpleNamespace(status=status, files=list(files), text=text, structured=None)
    return job, res


@pytest.mark.parametrize("files,plan,expected", [
    (["essa-ai/content/2026-10-05-x/post.md"], None, True),
    (["integrations/visuals/new.py"], None, True),
    ([], {"task_id": "p", "text": "план"}, True),
    (["memory/decisions/a.md"], None, False),
    ([], None, False),
])
def test_needs_review_only_for_substantial_turns(files, plan, expected):
    job, res = job_res(files, plan=plan)
    assert review.needs_review(job, res, env={}) is expected


def test_no_review_for_schedule_errors_or_when_switched_off():
    job, res = job_res(["essa-ai/content/x/post.md"], context="isolated")
    assert not review.needs_review(job, res, env={})
    job, res = job_res(["essa-ai/content/x/post.md"], status="error")
    assert not review.needs_review(job, res, env={})
    job, res = job_res(["essa-ai/content/x/post.md"])
    assert not review.needs_review(job, res, env={"JARVIS_REVIEW": "off"})


def test_prompt_has_task_plan_files_answer_and_tests_only():
    job, res = job_res(["essa-ai/content/x/post.md"], plan={"task_id": "p", "text": "**Готово, когда:** 7 папок"},
                       text="Сделал 7 папок.")
    prompt = review.build_prompt(job, res, tests="5 passed")
    for part in ("да, делай", "7 папок", "essa-ai/content/x/post.md", "Сделал 7 папок.", "5 passed"):
        assert part in prompt
    assert "session" not in prompt.lower()


def test_long_answer_is_cut():
    job, res = job_res(text="я" * 10000)
    assert len(review.build_prompt(job, res)) < 5000


def test_reviewer_settings_are_read_only_with_guard():
    s = json.loads(review.SETTINGS.read_text(encoding="utf-8"))
    assert s["permissions"]["allow"] == ["Read", "Glob", "Grep", "StructuredOutput"]
    assert s["permissions"]["defaultMode"] == "dontAsk"
    assert set(s["hooks"]) == {"PreToolUse"}
    cmd = s["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "guard.py" in cmd and "--mode" not in cmd
    assert review.OPTIONS.persist is False and review.OPTIONS.json_schema == review.SCHEMA


def test_reviewer_command_line_is_fresh_and_read_only():
    args = claude_bridge.build_args(None, review.OPTIONS)
    assert "--resume" not in args and "--no-session-persistence" in args
    assert args[args.index("--settings") + 1] == str(review.SETTINGS)
    assert args[args.index("--append-system-prompt-file") + 1] == str(review.PROMPT)
    assert json.loads(args[args.index("--json-schema") + 1]) == review.SCHEMA
    assert "--no-session-persistence" not in claude_bridge.build_args(None)   # обычный ход не меняется


def test_annotate_texts():
    assert review.annotate("Готово.", {"verdict": "pass", "rounds": 1}).endswith("✅ Перепроверил себя — всё в порядке.")
    assert "после правок" in review.annotate("x", {"verdict": "pass", "rounds": 2})
    t = review.annotate("x", {"verdict": "fix", "rounds": 2, "problems": ["нет отметки"]})
    assert "⚠️" in t and "нет отметки" in t
    assert "не вышло" in review.annotate("x", {"verdict": None, "error": "лимит"})


# ---------- в очереди ----------

@pytest.fixture
def router(tmp_path, monkeypatch):
    from runtime import sessions, task_router
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(task_router, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(spec, "SPECS_DIR", tmp_path / "specs")
    env = {**os.environ, "FAKE_CLAUDE_SCENARIO": "ledger", "FAKE_CLAUDE_LOG": str(tmp_path / "calls.jsonl"),
           "FAKE_REVIEW_COUNTER": str(tmp_path / "review-count.txt"), "JARVIS_REVIEW": "on"}
    r = task_router.TaskRouter(env=env, claude_cmd=FAKE, budget_path=tmp_path / "budget.json",
                               git_status=lambda: set(), tests_runner=lambda: "12 passed")
    r.tmp = tmp_path
    return r


async def _run(router, verdicts, chat=1):
    from runtime import task_router
    router.env = {**router.env, "FAKE_REVIEW_VERDICTS": verdicts}
    job = task_router.Job(prompt="сделай пост")
    router.submit(chat, job)
    res = await asyncio.wait_for(job.result, 30)
    calls = [json.loads(x) for x in (router.tmp / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    return job, res, [c for c in calls if "argv" in c]


def _is_review(call):
    return "--json-schema" in call["argv"]


async def test_pass_on_first_review(router):
    job, res, calls = await _run(router, "pass")
    assert [_is_review(c) for c in calls] == [False, True]
    assert res.review["verdict"] == "pass" and res.review["rounds"] == 1
    assert res.text.endswith("✅ Перепроверил себя — всё в порядке.")
    rv = calls[1]["argv"]
    assert "--resume" not in rv and "--no-session-persistence" in rv
    assert rv[rv.index("--settings") + 1].endswith("reviewer-settings.json")
    assert calls[1]["env_jarvis"]["JARVIS_TASK_ID"] == job.task_id


async def test_fix_goes_back_to_worker_then_passes(router):
    job, res, calls = await _run(router, "fix,pass")
    assert [_is_review(c) for c in calls] == [False, True, False, True]
    fix = calls[2]
    assert fix["argv"][fix["argv"].index("--resume") + 1] == "sess-new-0001"   # сессия исполнителя
    assert "нет отметки pipeline" in fix["stdin_tail"]
    assert res.review == {"verdict": "pass", "rounds": 2, "problems": [], "checked": ["essa-ai/content/x/post.md"]}
    assert "после правок" in res.text


async def test_two_failed_rounds_reach_the_owner_with_problems(router):
    job, res, calls = await _run(router, "fix,fix,pass")
    assert [_is_review(c) for c in calls] == [False, True, False, True]   # третьего круга нет
    assert res.review["verdict"] == "fix" and res.review["rounds"] == 2
    assert "⚠️" in res.text and "круг 2" in res.text
    assert res.status == "ok"


async def test_fail_verdict_is_not_sent_back(router):
    job, res, calls = await _run(router, "fail")
    assert [_is_review(c) for c in calls] == [False, True]
    assert "не то, что просили" in res.text


async def test_broken_review_does_not_break_the_answer(router):
    job, res, calls = await _run(router, "broken")
    assert res.status == "ok" and "не вышло" in res.text


async def test_ledger_records_review(router):
    job, res, _ = await _run(router, "fix,pass")
    rows = [json.loads(x) for x in (router.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    verdicts = [r for r in rows if r["type"] == "review_verdict"]
    assert [v["verdict"] for v in verdicts] == ["fix", "pass"]
    assert all(v["task_id"] == job.task_id for v in verdicts)
    done = [r for r in rows if r["type"] == "task_done"][0]
    assert done["review_verdict"] == "pass" and done["review_rounds"] == 2


async def test_switched_off_means_one_call(router):
    router.env = {**router.env, "JARVIS_REVIEW": "off"}
    job, res, calls = await _run(router, "fix")
    assert len(calls) == 1 and res.review is None


async def test_tests_run_only_when_code_changed(router):
    seen = []
    router.tests_runner = lambda: seen.append(1) or "ok"
    await _run(router, "pass")              # сценарий ledger меняет только .md
    assert seen == []


def test_foreign_git_changes_are_not_attributed_to_the_bot():
    from runtime.task_router import own_changes
    after = {"essa-ai/content/x/post.md", "integrations/montage/README.md",
             ".claude/skills/reel-montage/SKILL.md", "tests/test_montage_subs.py"}
    assert own_changes(set(), after) == {"essa-ai/content/x/post.md"}
    assert own_changes({"essa-ai/content/x/post.md"}, after) == set()
