"""Поправки и незакрытые вопросы переживают следующий ход без смешения чатов."""
import json
from types import SimpleNamespace

from runtime import dialogue_context, task_router
from runtime.claude_bridge import TurnResult


def test_current_correction_replaces_old_one_without_other_chat(tmp_path):
    path = tmp_path / "memory" / "corrections.md"
    path.parent.mkdir()
    path.write_text("- 2026-10-01 [chat:1] [key:style] — объясняй подробно\n"
                    "- 2026-10-07 [chat:1] [key:style] — объясняй проще\n"
                    "- 2026-10-07 [chat:2] — чужой секретный сценарий\n", encoding="utf-8")
    text = dialogue_context.build(tmp_path, "1", "объясни сценарий")
    assert "объясняй проще" in text and "объясняй подробно" not in text and "чужой секретный" not in text
    assert len(text) <= 2400


def test_episode_records_real_blockers_and_acceptance():
    job = task_router.Job("сделай сценарий")
    job.chat = "1"
    job.spec = {"task_id": "plan", "text": "**Вопросы:**\nКакой продукт?"}
    res = TurnResult("Готово!", None, False, None, "ok", acceptance="needs_changes",
                     review={"verdict": "fix", "problems": ["нет источника"]})
    row = dialogue_context.episode(job, res)
    assert row["chat"] == "1" and row["acceptance"] == "needs_changes"
    assert row["blockers"] == ["нет источника"] and row["open_questions"] == "Какой продукт?"
    assert "Готово!" not in row["outcome"]


def test_brief_does_not_pick_other_chat_or_unknown_legacy(tmp_path, monkeypatch):
    path = tmp_path / "episodes" / "2026-10.jsonl"
    path.parent.mkdir()
    rows = [{"date": str(i), "context": "chat", "request": "запрос", "result": text, **extra}
            for i, text, extra in [(1, "свой", {"chat": "1"}), (2, "чужой", {"chat": "2"}), (3, "без чата", {})]]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    monkeypatch.setattr(task_router, "EPISODES_DIR", path.parent)
    router = task_router.TaskRouter(env={}, budget_path=tmp_path / "budget.json")
    job = task_router.Job("продолжим")
    job.chat = "1"
    text = router._brief_prompt(job, 9)
    assert "свой" in text and "чужой" not in text and "без чата" not in text
