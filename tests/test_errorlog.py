"""Журнал ошибок: запись один раз с причиной, счётчик повторов, маскировка секретов, памятка агенту."""
import importlib.util
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime import errorlog
from runtime.redact import redact

TOKEN = "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "session_start.py"


def index():
    return json.loads(errorlog.INDEX_PATH.read_text(encoding="utf-8"))


def journal():
    return [json.loads(x) for x in errorlog.ERRORS_PATH.read_text(encoding="utf-8").splitlines()]


def boom(n):
    raise ValueError(f"файл C:\\tmp\\f{n}.png не найден, код {n}")


def caught(n=1):
    try:
        boom(n)
    except ValueError as exc:
        return exc


def test_same_error_with_other_numbers_is_one_entry_with_count():
    a = errorlog.record("gateway", caught(1), task_id="t1")
    b = errorlog.record("gateway", caught(2), task_id="t2")
    assert a == b
    assert index()[a]["count"] == 2
    rows = journal()
    assert len(rows) == 2 and rows[0]["type"] == "ValueError"
    assert "boom" in rows[0]["trace"]          # трассировка с функцией, где упало
    assert rows[1]["ctx"] == {"task_id": "t2"}


def test_different_source_or_message_is_different_entry():
    assert errorlog.record("a", caught()) != errorlog.record("b", caught())
    assert errorlog.record("a", message="один") != errorlog.record("a", message="другой")


def test_secrets_never_reach_disk():
    errorlog.record("tg", message=f"POST https://api.telegram.org/bot{TOKEN}/getUpdates failed",
                    api_key="sk-abcdefghijklmnopqrstuvwxyz123456")
    raw = errorlog.ERRORS_PATH.read_text(encoding="utf-8") + errorlog.INDEX_PATH.read_text(encoding="utf-8")
    assert "AAHdqTcv" not in raw and "sk-abcdef" not in raw


def test_record_never_raises_when_path_is_unwritable(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(errorlog, "ERRORS_PATH", blocker / "sub" / "errors.jsonl")
    assert errorlog.record("x", caught()) is None


def test_journal_rotates(monkeypatch):
    monkeypatch.setattr(errorlog, "MAX_BYTES", 10)
    errorlog.record("x", message="первая")
    errorlog.record("x", message="вторая")
    assert errorlog.ERRORS_PATH.with_name("errors.1.jsonl").exists()


# ---------- памятка агенту ----------

def agent_error(msg="отказ: запись в защищённое место", times=2):
    for _ in range(times):
        fp = errorlog.record("tool:Write", message=msg, kind="agent")
    return fp


def test_digest_lists_only_repeated_agent_errors():
    agent_error()
    errorlog.record("tool:Read", message="разовая", kind="agent")
    errorlog.record("gateway", caught(), kind="bot")
    errorlog.record("gateway", caught(), kind="bot")
    text = errorlog.digest()
    assert "tool:Write" in text and "×2" in text
    assert "разовая" not in text and "ValueError" not in text and "boom" not in text


def test_digest_empty_without_repeats():
    errorlog.record("tool:Read", message="разовая", kind="agent")
    assert errorlog.digest() == ""


def test_digest_shows_hint_and_hides_old_and_fixed():
    fp = agent_error()
    data = index()
    data[fp]["hint"] = "пиши в drafts/"
    errorlog.INDEX_PATH.write_text(json.dumps(data), encoding="utf-8")
    assert "делай так: пиши в drafts/" in errorlog.digest()
    later = datetime.now(timezone.utc) + timedelta(days=30)
    assert errorlog.digest(now=later) == ""
    assert errorlog.main(["fixed", fp]) == 0
    assert errorlog.digest() == ""
    errorlog.record("tool:Write", message="отказ: запись в защищённое место", kind="agent")
    assert "tool:Write" in errorlog.digest()      # вернулась — снова в памятке


def test_digest_limit_orders_by_frequency():
    for i in range(12):
        for _ in range(2 + (i == 5) * 3):
            errorlog.record("tool:X", message=f"ошибка-{'abcdefghijkl'[i]}", kind="agent")
    lines = errorlog.digest(limit=3).splitlines()
    assert len(lines) == 4 and "×5" in lines[1]


# ---------- logging ----------

@pytest.fixture
def test_logger():
    log = logging.getLogger("jarvis.testlog")
    log.setLevel(logging.INFO)
    stream = io.StringIO()
    handlers = [errorlog.ErrorJournalHandler(), logging.StreamHandler(stream)]
    for h in handlers:
        h.addFilter(errorlog.RedactFilter())
        log.addHandler(h)
    yield log, stream
    for h in handlers:
        log.removeHandler(h)


def test_logging_warning_with_traceback_goes_to_journal(test_logger):
    log, _ = test_logger
    try:
        boom(7)
    except ValueError:
        log.warning("не удалось скачать файл", exc_info=True)
    log.info("обычная строка")
    rows = journal()
    assert len(rows) == 1
    assert rows[0]["source"] == "jarvis.testlog" and "не найден" in rows[0]["trace"]


def test_logging_redacts_token_in_message_args_and_traceback(test_logger):
    log, stream = test_logger
    try:
        raise RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMessage")
    except RuntimeError:
        log.warning("сбой %s", f"bot{TOKEN}", exc_info=True)
    assert "AAHdqTcv" not in stream.getvalue()
    assert "AAHdqTcv" not in errorlog.ERRORS_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("text", [
    f"https://api.telegram.org/bot{TOKEN}/getUpdates",
    "Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==",
    "authorization=Token abcdef123",
])
def test_redact_covers_token_in_url_and_authorization(text):
    out = redact(text)
    assert "AAHdqTcv" not in out and "dXNlcjpw" not in out and "abcdef123" not in out


# ---------- хук начала сессии ----------

def test_session_start_hook_injects_digest(tmp_path):
    agent_error()
    spec = importlib.util.spec_from_file_location("jarvis_session_start", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "errors_index.json").write_text(errorlog.INDEX_PATH.read_text(encoding="utf-8"),
                                                          encoding="utf-8")
    out = io.StringIO()
    assert mod.main(stdin=io.StringIO("{}"), stdout=out, root=tmp_path) == 0
    assert "tool:Write" in json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]


# ---------- мост: ошибка инструмента становится ошибкой агента ----------

def test_bridge_records_tool_error_as_agent_error(monkeypatch):
    from runtime import claude_bridge, events
    monkeypatch.setattr(events, "EVENTS_PATH", errorlog.ERRORS_PATH.with_name("events.jsonl"))
    out = claude_bridge._Outcome()
    use = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "x"}}]}}
    res = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": True,
         "content": [{"type": "text", "text": "JARVIS Guard: отказ — запись в защищённое место"}]}]}}
    claude_bridge._log_event(use, "s", "task", out, "id1")
    claude_bridge._log_event(res, "s", "task", out, "id1")
    row = journal()[0]
    assert row["kind"] == "agent" and row["source"] == "tool:Write" and "Guard" in row["message"]
