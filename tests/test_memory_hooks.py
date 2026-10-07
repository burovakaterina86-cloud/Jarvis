"""Шов хуков памяти: записанный JSON-вход хука -> JSON-выход / побочный эффект."""
import importlib.util
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / ".claude" / "hooks"
PY = sys.executable


def _load(name):
    spec = importlib.util.spec_from_file_location(f"jarvis_{name}", HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_main(mod, event, root):
    out = io.StringIO()
    raw = event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
    code = mod.main(stdin=io.StringIO(raw), stdout=out, root=root)
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None)


# --- memory_notice (PostToolUse) ---

def post(tool, root, rel, **extra):
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "s1",
        "cwd": str(root),
        "tool_name": tool,
        "tool_input": {"file_path": str(root / rel), **extra},
        "tool_response": {"filePath": str(root / rel), "type": "create"},
    }


@pytest.mark.parametrize("tool,rel", [
    ("Write", "MEMORY.md"),
    ("Edit", "memory/decisions/2026-09-17-cena.md"),
    ("MultiEdit", "memory/people/anna.md"),
    ("Write", "essa-ai/knowledge/brief.md"),
])
def test_memory_notice_gives_context_for_memory_paths(tmp_path, tool, rel):
    mod = _load("memory_notice")
    code, out = run_main(mod, post(tool, tmp_path, rel), tmp_path)
    assert code == 0
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert "🧠 запомнил" in spec["additionalContext"]
    assert rel in spec["additionalContext"]


@pytest.mark.parametrize("tool,rel", [
    ("Write", "drafts/skills/x/SKILL.md"),
    ("Write", "essa-ai/VOICE.md"),
    ("Write", "inbox/2026-09-17/memory.md"),
    ("Read", "MEMORY.md"),
    ("Edit", "memoryX/notes.md"),
])
def test_memory_notice_silent_for_other_paths_and_tools(tmp_path, tool, rel):
    mod = _load("memory_notice")
    assert run_main(mod, post(tool, tmp_path, rel), tmp_path) == (0, None)


def test_memory_notice_ignores_writes_outside_root(tmp_path):
    mod = _load("memory_notice")
    root = tmp_path / "jarvis"
    root.mkdir()
    event = post("Write", tmp_path, "memory/x.md")
    assert run_main(mod, event, root) == (0, None)


# --- capture_learning (Stop) ---

def _transcript(path, tool_uses):
    lines = [
        {"type": "user", "message": {"role": "user", "content": "старое сообщение"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "old", "name": "Read", "input": {}}]}},
        {"type": "user", "message": {"role": "user", "content": "Собери план постов на неделю"}},
    ]
    for i in range(tool_uses):
        lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "делаю"},
            {"type": "tool_use", "id": f"t{i}", "name": "Write",
             "input": {"file_path": f"C:/j/out{i}.md", "content": "x"}}]}})
        lines.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}]}})
    lines.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "План готов: out0.md"}]}})
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    return path


def stop(tmp_path, active=False, tool_uses=5):
    return {
        "hook_event_name": "Stop",
        "session_id": "s1",
        "transcript_path": str(_transcript(tmp_path / "t.jsonl", tool_uses)),
        "stop_hook_active": active,
        "last_assistant_message": "План готов: out0.md",
    }


def test_capture_learning_reminds_after_real_task(tmp_path):
    mod = _load("capture_learning")
    code, out = run_main(mod, stop(tmp_path), tmp_path)
    assert code == 0
    # формат Stop из документации Claude Code: decision=block + reason (additionalContext у Stop не заявлен)
    assert out["decision"] == "block" and "hookSpecificOutput" not in out
    assert "memory/decisions/" in out["reason"] and "create-skill" in out["reason"]


def test_capture_learning_silent_when_stop_hook_active(tmp_path):
    mod = _load("capture_learning")
    assert run_main(mod, stop(tmp_path, active=True), tmp_path) == (0, None)


def test_capture_learning_silent_for_trivial_turn(tmp_path):
    mod = _load("capture_learning")
    assert run_main(mod, stop(tmp_path, tool_uses=1), tmp_path) == (0, None)


def test_capture_learning_silent_without_transcript(tmp_path):
    mod = _load("capture_learning")
    event = stop(tmp_path)
    event["transcript_path"] = str(tmp_path / "missing.jsonl")
    assert run_main(mod, event, tmp_path) == (0, None)


# --- pre_compact (PreCompact) ---

def test_pre_compact_appends_valid_jsonl_line(tmp_path):
    mod = _load("pre_compact")
    event = {
        "hook_event_name": "PreCompact", "session_id": "s1", "trigger": "auto",
        "custom_instructions": None,
        "transcript_path": str(_transcript(tmp_path / "t.jsonl", 2)),
    }
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    for _ in range(2):
        assert mod.main(stdin=io.StringIO(json.dumps(event)), stdout=io.StringIO(),
                        root=tmp_path, now=now) == 0
    lines = (tmp_path / "memory" / "episodes" / "2026-09.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["session"] == "s1" and rec["trigger"] == "auto"
    assert rec["request"] == "Собери план постов на неделю"
    assert rec["result"] == "План готов: out0.md"
    assert rec["files"] == ["C:/j/out0.md", "C:/j/out1.md"]
    assert rec["date"].startswith("2026-09-17")


def test_pre_compact_writes_line_even_without_transcript(tmp_path):
    mod = _load("pre_compact")
    event = {"hook_event_name": "PreCompact", "session_id": "s2", "trigger": "manual",
             "transcript_path": str(tmp_path / "nope.jsonl")}
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert mod.main(stdin=io.StringIO(json.dumps(event)), stdout=io.StringIO(), root=tmp_path, now=now) == 0
    rec = json.loads((tmp_path / "memory" / "episodes" / "2026-10.jsonl").read_text(encoding="utf-8"))
    assert rec["session"] == "s2" and rec["request"] is None and rec["files"] == []


# --- session_start (SessionStart) ---

START = {"hook_event_name": "SessionStart", "session_id": "s1", "source": "startup"}


def test_session_start_asks_to_compress_big_memory(tmp_path):
    mod = _load("session_start")
    (tmp_path / "MEMORY.md").write_bytes(b"x" * 5121)
    code, out = run_main(mod, START, tmp_path)
    assert code == 0
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "сожми MEMORY.md" in out["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("size", [None, 5120])
def test_session_start_silent_for_small_or_missing_memory(tmp_path, size):
    mod = _load("session_start")
    if size is not None:
        (tmp_path / "MEMORY.md").write_bytes(b"x" * size)
    assert run_main(mod, START, tmp_path) == (0, None)


# --- ошибки: хуки не защитные, любое исключение -> exit 0 без эффекта ---

HOOK_NAMES = ["memory_notice", "capture_learning", "pre_compact", "session_start"]


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hook_exception_exits_zero_silently(tmp_path, name, monkeypatch):
    mod = _load(name)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "handle", boom)
    assert run_main(mod, {"hook_event_name": "X", "stop_hook_active": False}, tmp_path) == (0, None)


@pytest.mark.parametrize("name", HOOK_NAMES)
def test_hook_process_garbage_stdin_exits_zero(name):
    proc = subprocess.run([PY, str(HOOKS / f"{name}.py")], input="не json {",
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0
    assert proc.stdout == ""


# --- дозапрос ревью ---

@pytest.mark.parametrize("response", [
    {"success": False, "error": "File has not been read yet"},
    {"error": "EACCES: permission denied"},
    {"is_error": True, "content": "Error: string not found"},
    "Error: File has not been read yet. Read it first before writing to it.",
])
def test_memory_notice_silent_when_write_failed(tmp_path, response):
    mod = _load("memory_notice")
    event = post("Write", tmp_path, "MEMORY.md")
    event["tool_response"] = response
    assert run_main(mod, event, tmp_path) == (0, None)


def _meta_line(text):
    return {"type": "user", "isMeta": True, "message": {"role": "user", "content": text}}


def _sidechain_lines():
    return [
        {"type": "user", "isSidechain": True,
         "message": {"role": "user", "content": "подзадача для субагента"}},
        {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "sa", "name": "Write",
             "input": {"file_path": "C:/j/sub.md"}}]}},
    ]


def _transcript_with_inserts(path, tool_uses, after_pairs):
    """Вставка хука и ход субагента в середине хода владелицы (после after_pairs шагов)."""
    _transcript(path, tool_uses)
    lines = path.read_text(encoding="utf-8").splitlines()
    extra = [json.dumps(_meta_line("<system-reminder>подсказка хука</system-reminder>"),
                        ensure_ascii=False)]
    extra += [json.dumps(x, ensure_ascii=False) for x in _sidechain_lines()]
    cut = 3 + 2 * after_pairs
    path.write_text("\n".join(lines[:cut] + extra + lines[cut:]) + "\n", encoding="utf-8")
    return path


def test_capture_learning_ignores_meta_and_sidechain_entries(tmp_path):
    mod = _load("capture_learning")
    event = stop(tmp_path, tool_uses=3)
    event["transcript_path"] = str(_transcript_with_inserts(tmp_path / "t.jsonl", 3, after_pairs=2))
    code, out = run_main(mod, event, tmp_path)
    assert code == 0
    assert out is not None, "вставка хука не должна сбрасывать счёт хода владелицы"
    assert "memory/decisions/" in out["reason"]


def test_pre_compact_ignores_meta_and_sidechain_entries(tmp_path):
    mod = _load("pre_compact")
    event = {"hook_event_name": "PreCompact", "session_id": "s3", "trigger": "auto",
             "transcript_path": str(_transcript_with_inserts(tmp_path / "t.jsonl", 2, after_pairs=1))}
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert mod.main(stdin=io.StringIO(json.dumps(event)), stdout=io.StringIO(),
                    root=tmp_path, now=now) == 0
    rec = json.loads((tmp_path / "memory" / "episodes" / "2026-11.jsonl").read_text(encoding="utf-8"))
    assert rec["request"] == "Собери план постов на неделю"
    assert rec["files"] == ["C:/j/out0.md", "C:/j/out1.md"]


@pytest.mark.parametrize("tool_uses,expected", [(2, None), (3, "есть")])
def test_capture_learning_threshold_boundary(tmp_path, tool_uses, expected):
    mod = _load("capture_learning")
    code, out = run_main(mod, stop(tmp_path, tool_uses=tool_uses), tmp_path)
    assert code == 0
    assert (out is None) == (expected is None)


# --- scripts/check_context_size.py ---

CHECKER = REPO / "scripts" / "check_context_size.py"


def _fake_root(tmp_path, memory_bytes):
    for name, size in [("CLAUDE.md", 2000), ("SOUL.md", 500), ("GOALS.md", 500),
                       ("MEMORY.md", memory_bytes)]:
        (tmp_path / name).write_bytes(b"x" * size)
    return tmp_path


@pytest.mark.parametrize("memory_bytes,expected_code", [(5 * 1024, 0), (5 * 1024 + 1, 1)])
def test_check_context_size_exit_code(tmp_path, memory_bytes, expected_code):
    root = _fake_root(tmp_path, memory_bytes)
    proc = subprocess.run([PY, str(CHECKER), str(root)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == expected_code
    assert "MEMORY.md" in proc.stdout
