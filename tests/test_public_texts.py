"""Правило публичных текстов проверяется по журналу хода, а не по словам модели (её жалоба 2026-10-07)."""
import json

import pytest

from runtime import events, public_texts

REL = "essa-ai/content/2026-10-07-obyasni.md"


@pytest.mark.parametrize("name", ["carousels.json", "strategy.json"])
def test_actual_weekly_json_requires_pipeline(tmp_path, name):
    rel = "essa-ai/content-plan/weeks/test/" + name
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text('{"pipeline": "humaniser НЕ пройден"}', encoding="utf-8")
    assert public_texts.check([rel], "test", root=tmp_path, events_path=tmp_path / "events")
    assert "В JSON" in public_texts.fix_prompt([rel + ": нет прохода"])


@pytest.mark.parametrize("shell", ["powershell -Command", "pwsh -NoProfile -Command", "bash -lc"])
def test_completed_codex_shell_read_is_recognized(shell):
    item = {"type": "command_execution", "status": "completed", "exit_code": 0,
            "command": shell + " 'Get-Content .agents/skills/humaniser/SKILL.md'"}
    assert public_texts.codex_evidence(item) == [("Read", ".agents/skills/humaniser/SKILL.md")]
    item["command"] = shell + " 'Get-Content .agents/skills/humaniser/SKILL.md; echo other'"
    assert public_texts.codex_evidence(item) == []
MARK = "<!-- pipeline: textwriter → humaniser → VOICE — пройден 2026-10-07 -->"
GOOD = [("Read", "C:/p/.claude/skills/textwriter/SKILL.md"), ("Write", "C:/p/" + REL),
        ("Read", "C:/p/.claude/skills/humaniser/SKILL.md"), ("Edit", "C:/p/" + REL)]


@pytest.mark.parametrize("rel,expected", [
    (REL, True), ("essa-ai/content/2026-10-07-x/post.md", True), ("essa-ai/content/2026-10-07-x/reels.md", True),
    ("essa-ai/content/2026-10-07-x/sources.md", False), ("essa-ai/content/radar-2026-10-05/radar.md", False),
    ("essa-ai/content/radar-2026-10-05/transcripts/a.md", False), ("essa-ai/VOICE.md", False),
    ("essa-ai/content/2026-10-07-x/status", False), ("outbox/a.md", False),
])
def test_what_counts_as_a_public_text(rel, expected):
    assert public_texts.is_public_text(rel) is expected


def test_both_passes_and_mark_are_ok():
    assert public_texts.check_file(REL, f"текст\n\n{MARK}\n", GOOD) == []


def test_honest_not_passed_mark_is_a_violation_even_with_good_log():
    text = "текст\n<!-- pipeline: humaniser НЕ пройден — проходы не запускались -->"
    problems = public_texts.check_file(REL, text, GOOD)
    assert any("прямо написано" in p for p in problems)


def test_mark_without_the_passes_in_the_log_is_a_lie():
    """Модель поставила отметку «пройден», но навыки за ход не открывала."""
    problems = public_texts.check_file(REL, f"текст\n{MARK}", [("Write", "C:/p/" + REL)])
    assert problems == [f"{REL}: за ход не открыт навык textwriter"]


def test_humaniser_must_come_after_textwriter():
    tools = [("Read", ".claude/skills/humaniser/SKILL.md"), ("Read", ".claude/skills/textwriter/SKILL.md"),
             ("Write", REL)]
    assert any("humaniser" in p for p in public_texts.check_file(REL, f"т\n{MARK}", tools))


def test_file_must_be_saved_after_humaniser():
    tools = [("Read", ".claude/skills/textwriter/SKILL.md"), ("Write", REL), ("Read", ".claude/skills/humaniser/SKILL.md")]
    assert any("после humaniser файл не сохранялся" in p for p in public_texts.check_file(REL, f"т\n{MARK}", tools))


def test_subagent_or_skill_call_counts_as_a_pass():
    tools = [("Agent", "general-purpose: textwriter pass"), ("Skill", "humaniser"), ("Write", REL)]
    assert public_texts.check_file(REL, f"т\n{MARK}", tools) == []


def test_week_json_has_the_same_pipeline_requirement(tmp_path):
    rel = "essa-ai/content-plan/weeks/x/reels.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pipeline": "humaniser НЕ пройден", "days": []}), encoding="utf-8")
    assert public_texts.check([rel], "task", root=tmp_path)


def test_missing_public_text_is_a_problem(tmp_path):
    assert public_texts.check([REL], "task", root=tmp_path)


def test_successful_codex_reads_and_writes_are_pipeline_evidence(tmp_path):
    rel = "essa-ai/content-plan/weeks/x/reels.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pipeline": "textwriter → humaniser → VOICE — пройден 2026-10-07"}), encoding="utf-8")
    items = [{"type": "command_execution", "status": "completed", "exit_code": 0,
              "command": f"Get-Content .agents/skills/{name}/SKILL.md"} for name in ("textwriter", "humaniser")]
    items.append({"type": "file_change", "status": "completed", "changes": [{"path": rel}]})
    log = tmp_path / "events.jsonl"
    rows = [{"type": "pipeline_evidence", "task_id": "t", "operation": op, "path": target, "success": True}
            for item in items for op, target in public_texts.codex_evidence(item)]
    log.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    assert public_texts.check([rel], "t", tmp_path, log) == []
    items[0]["exit_code"] = 1
    assert public_texts.codex_evidence(items[0]) == []


def test_check_reads_the_turn_from_the_journal(tmp_path):
    (tmp_path / "essa-ai" / "content").mkdir(parents=True)
    (tmp_path / REL).write_text(f"текст\n{MARK}\n", encoding="utf-8")
    log = tmp_path / "events.jsonl"
    rows = [{"type": "tool_use", "task_id": "t1", "tool": t, "summary": s} for t, s in GOOD]
    rows.append({"type": "tool_use", "task_id": "other", "tool": "Read", "summary": "x"})
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert public_texts.check([REL], "t1", tmp_path, log) == []
    assert public_texts.check([REL], "t2", tmp_path, log)           # у другой задачи проходов не было
    assert public_texts.check(["outbox/a.md"], "t2", tmp_path, log) == []   # не публичный текст — не проверяем


def test_fix_prompt_names_every_step_and_the_real_skill_files():
    p = public_texts.fix_prompt(["a: нет"], ".agents/skills")
    assert ".agents/skills/textwriter/SKILL.md" in p and ".agents/skills/humaniser/SKILL.md" in p and "pipeline:" in p
    assert "Ничего не выдумывай" in p and "НЕ пройден" not in public_texts.warning(["a: x"]).replace("НЕ прошёл", "")


# ---------- роутер: нарушение → исправляющий ход → предупреждение, если не помогло ----------

from tests.test_router_codex import router  # noqa: E402,F401


async def _run(router, monkeypatch, tmp_path, *, fixed_ok):
    from runtime import claude_bridge, task_router
    (tmp_path / "essa-ai" / "content").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(public_texts, "ROOT", tmp_path)
    monkeypatch.setattr(task_router.public_texts, "check",
                        lambda files, task_id, root=None, events_path=None: public_texts.check_file(
                            REL, "текст\n<!-- pipeline: humaniser НЕ пройден -->", []) if not fixed_ok.get("done") else [])
    calls = []

    async def fake_timed(self, key, job, prompt, sid, limit, **kw):
        calls.append(prompt)
        fixed_ok["done"] = fixed_ok.get("works", False)
        return claude_bridge.TurnResult("Исправил.", "sid", False, 0.01, "ok")

    monkeypatch.setattr(task_router.TaskRouter, "_timed", fake_timed)
    job = task_router.Job(prompt="сделай сценарий", task="сценарий")
    job.runtime_used = "claude"
    res = claude_bridge.TurnResult("Сценарий готов, он прошёл textwriter и humaniser.", "sid", False, 0.01, "ok",
                                   files=[REL])
    return await router._enforce_public_texts("1", job, res, 60), calls


async def test_skipped_passes_trigger_a_fix_turn(router, monkeypatch, tmp_path):
    state = {"works": True}
    res, calls = await _run(router, monkeypatch, tmp_path, fixed_ok=state)
    assert len(calls) == 1 and "textwriter/SKILL.md" in calls[0]
    assert res.text == "Исправил." and "⚠️" not in res.text


async def test_if_the_fix_does_not_help_the_owner_is_warned_honestly(router, monkeypatch, tmp_path):
    res, calls = await _run(router, monkeypatch, tmp_path, fixed_ok={"works": False})
    assert len(calls) == 1 and "⚠️" in res.text and "НЕ прошёл" in res.text and REL in res.text
    assert res.acceptance == "needs_changes"


# ---------- правила хука и призыва реально подключены ----------

from pathlib import Path  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def test_hook_and_cta_rules_exist_and_are_routed_everywhere_the_agent_looks():
    rules = (REPO / "essa-ai" / "HOOKS_AND_CTA.md").read_text(encoding="utf-8")
    assert len(rules.encode("utf-8")) < 30 * 1024               # читается целиком (лимит чтения — 30 КБ)
    for must in ("кодовое слово", "Чек-лист перед сдачей", "PIPE", "WS2", "без приветствия"):
        assert must in rules
    assert "HOOKS_AND_CTA.md" in (REPO / "essa-ai" / "INDEX.md").read_text(encoding="utf-8")
    assert "HOOKS_AND_CTA.md" in (REPO / ".claude" / "skills" / "reels-script" / "SKILL.md").read_text(encoding="utf-8")
    assert "HOOKS_AND_CTA.md" in (REPO / "runtime" / "jarvis-turn.md").read_text(encoding="utf-8")
    assert "HOOKS_AND_CTA.md" in (REPO / ".claude" / "rules" / "public-texts.md").read_text(encoding="utf-8")
    assert (REPO / "essa-ai" / "HOOKS_AND_CTA_SOURCES.md").is_file()


def test_the_loophole_that_let_the_bot_skip_the_passes_is_closed():
    rule = (REPO / ".claude" / "rules" / "public-texts.md").read_text(encoding="utf-8")
    assert "Пропускать проход нельзя" in rule and "Никогда не пиши в ответе" in rule
    assert "честная пометка `humaniser НЕ пройден" not in rule
