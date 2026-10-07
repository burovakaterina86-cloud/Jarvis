"""Кто работает в чате и известные лимиты (P4.1e/f): state/runtime.json, state/limits.json."""
import json

import pytest

from runtime import worker


@pytest.fixture(autouse=True)
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "STATE_DIR", tmp_path)
    return tmp_path


def test_default_is_claude():
    assert worker.active("1", now=100.0) == ("claude", False)


def test_codex_until_reset_then_back_to_claude():
    worker.switch("1", "codex", until=200.0, now=100.0)
    assert worker.active("1", now=150.0) == ("codex", False)
    assert worker.active("1", now=201.0) == ("claude", True)       # вернулся — сообщить владелице
    assert worker.active("1", now=202.0) == ("claude", False)      # сообщаем один раз


def test_manual_codex_has_no_end():
    worker.switch("1", "codex", until=None, now=100.0)
    assert worker.active("1", now=10_000_000.0) == ("codex", False)
    worker.switch("1", "claude", now=200.0)
    assert worker.active("1", now=300.0) == ("claude", False)


def test_chats_are_independent():
    worker.switch("1", "codex", until=None)
    assert worker.active("2")[0] == "claude"


def test_unknown_runtime_is_rejected():
    with pytest.raises(ValueError):
        worker.switch("1", "gpt-какой-то")


def test_session_keys_differ_per_runtime():
    assert worker.session_key("1", "claude") == "1"
    assert worker.session_key("1", "codex") == "1:codex"


def test_limits_store(paths):
    worker.save_limits("claude", {"status": "rejected", "resets_at": 1789566847})
    worker.save_limits("codex", {"primary": {"used_percent": 46.0, "resets_at": 1789566847}})
    data = worker.limits()
    assert data["claude"]["status"] == "rejected" and "ts" in data["claude"]
    assert data["codex"]["primary"]["used_percent"] == 46.0
    assert json.loads((paths / "limits.json").read_text(encoding="utf-8"))["claude"]["resets_at"] == 1789566847


def test_pending_offer_round_trip():
    worker.save_offer("1", {"task": "пост", "prompt": "сделай пост", "resets_at": 300.0, "files": ["a.md"]})
    assert worker.load_offer("1")["task"] == "пост"
    worker.drop_offer("1")
    assert worker.load_offer("1") is None


def test_deferred_tasks():
    worker.defer("1", at=500.0, prompt="сделай пост", task="пост")
    assert worker.due_deferred(now=400.0) == []
    due = worker.due_deferred(now=600.0)
    assert [(d["chat"], d["task"]) for d in due] == [("1", "пост")]
    assert worker.due_deferred(now=700.0) == []                       # забирается один раз


def test_deferred_role_keeps_task_identity():
    scope = {'context': 'task', 'task_id': 'own-task', 'role': 'text', 'original': 'полное поручение'}
    worker.defer('1', at=0, prompt='продолжить', task='пост', scope=scope)
    item = worker.due_deferred(now=1)[0]
    assert all(item[key] == value for key, value in scope.items())


def test_describe_limits_for_status():
    text = worker.describe_limits({
        "claude": {"status": "rejected", "resets_at": 1789566847},
        "codex": {"primary": {"used_percent": 46.0, "resets_at": 1789566847},
                  "secondary": {"used_percent": 61.0, "resets_at": 1789830210}},
    }, now=1789560000)
    assert "У Claude лимит закончился, вернётся в" in text
    assert "У Codex израсходовано: 5 ч — 46%" in text and "неделя — 61%" in text
    assert worker.describe_limits({"claude": {"status": "allowed"}}) == "У Claude с лимитом всё хорошо"
