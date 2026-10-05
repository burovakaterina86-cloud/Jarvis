"""Мост к Codex (P4.1d) — шов: run_turn с фейковым codex, как test_bridge с фейковым claude."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from runtime import claude_bridge, codex_bridge, events, review

FAKE = [sys.executable, str(Path(__file__).parent / "fake_codex" / "fake_codex.py")]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "EVENTS_PATH", tmp_path / "events.jsonl")
    log = tmp_path / "calls.jsonl"
    env = {**os.environ, "FAKE_CODEX_LOG": str(log)}

    class F:
        tmp = tmp_path

        def calls(self):
            return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

        async def run(self, prompt="привет", session_id=None, scenario="ok", **kw):
            kw.setdefault("env", {**env, "FAKE_CODEX_SCENARIO": scenario})
            return await codex_bridge.run_turn(prompt, session_id, kw.pop("on_event", None),
                                               codex_cmd=FAKE, cwd=tmp_path, **kw)
    return F()


async def test_turn_parses_thread_text_tools_and_files(fake):
    res = await fake.run(task_id="t1")
    assert res.status == "ok" and res.session_id == "thread-new-0001" and res.new_session
    assert res.text == "Готово в Codex: пост в essa-ai/content/x/post.md"   # последнее сообщение, не все
    assert res.tool_uses == 2 and res.files == ["essa-ai/content/x/post.md"]
    assert res.runtime == "codex"


async def test_command_line_is_safe_and_brings_the_brain(fake):
    await fake.run(task_id="t1")
    call = fake.calls()[0]
    argv = call["argv"]
    assert argv[:2] == ["exec", "--json"] and argv[-1] == "-"
    assert "--ignore-user-config" not in argv              # иначе папка недоверенная: read-only и без хуков
    assert argv[argv.index("--disable") + 1] == "plugins"
    assert not any("dangerously" in a for a in argv)
    cfg = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    assert 'sandbox_mode="workspace-write"' in cfg and 'approval_policy="never"' in cfg
    instructions = next(c for c in cfg if c.startswith("developer_instructions="))
    text = json.loads(instructions.split("=", 1)[1])            # TOML-строка = JSON-строка, одной строкой
    assert "\n" not in instructions
    assert "JARVIS" in text and "AGENTS.md" in text and "SOUL" in text
    assert call["stdin_tail"].endswith("привет")
    assert call["env_jarvis"]["JARVIS_TASK_ID"] == "t1"


async def test_resume_uses_exec_resume(fake):
    res = await fake.run(session_id="thread-old", task_id="t2")
    argv = fake.calls()[0]["argv"]
    assert argv[:3] == ["exec", "resume", "thread-old"]
    assert res.session_id == "thread-old" and not res.new_session


async def test_reviewer_options_map_to_read_only_schema_ephemeral(fake):
    res = await fake.run(scenario="schema", options=review.OPTIONS)
    argv = fake.calls()[0]["argv"]
    cfg = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    assert 'sandbox_mode="read-only"' in cfg and "--ephemeral" in argv
    assert fake.calls()[0]["schema"] == review.SCHEMA
    assert not Path(argv[argv.index("--output-schema") + 1]).exists()   # временный файл убран
    instructions = json.loads(next(c for c in cfg if c.startswith("developer_instructions=")).split("=", 1)[1])
    assert "проверяющий" in instructions.lower()
    assert res.structured == {"verdict": "pass", "problems": [], "checked": ["post.md"]}   # последнее сообщение


async def test_rate_limit_and_auth_statuses(fake):
    res = await fake.run(scenario="rate_limit")
    assert res.status == "rate_limited" and "Codex" in res.text
    res = await fake.run(scenario="auth")
    assert res.status == "auth_required" and "codex login" in res.text


async def test_crash_is_an_error_not_an_exception(fake):
    res = await fake.run(scenario="crash")
    assert res.status == "error" and res.error


async def test_stop_kills_the_turn(fake):
    task = asyncio.create_task(fake.run(scenario="sleep", run_id="cx-stop"))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if fake.calls():
            break
    assert codex_bridge.stop("cx-stop") is True
    res = await asyncio.wait_for(task, 5)
    assert res.status == "stopped"


async def test_events_are_logged_with_runtime_and_task(fake):
    await fake.run(task_id="t9", task="пост")
    rows = [json.loads(x) for x in (fake.tmp / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    uses = [r for r in rows if r["type"] == "tool_use"]
    assert uses and all(r["runtime"] == "codex" and r["task_id"] == "t9" for r in uses)
    assert {u["tool"] for u in uses} == {"Bash", "apply_patch"}


async def test_status_card_gets_claude_like_events(fake):
    seen = []
    await fake.run(on_event=seen.append)
    tools = [b["name"] for ev in seen if ev.get("type") == "assistant"
             for b in ev["message"]["content"] if b.get("type") == "tool_use"]
    assert tools == ["Bash", "apply_patch"]


def test_brain_strips_claude_imports():
    text = codex_bridge.brain()
    assert "@SOUL.md" not in text and "SOUL — характер JARVIS" in text


def test_default_command_avoids_the_cmd_shim(monkeypatch, tmp_path):
    npm = tmp_path / "npm"
    js = npm / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    js.parent.mkdir(parents=True)
    js.write_text("// codex", encoding="utf-8")
    (npm / "codex.cmd").write_text("@echo off", encoding="utf-8")
    monkeypatch.setattr(codex_bridge.shutil, "which",
                        lambda name: str(npm / "codex.cmd") if name == "codex" else "C:/node/node.exe")
    assert codex_bridge.default_codex_cmd() == ["C:/node/node.exe", str(js)]


def test_turn_result_has_runtime_field():
    assert claude_bridge.TurnResult("", None, False, None, "ok").runtime == "claude"


# ---------- P4.1c: готовность Codex — Guard отвечает и Codex ему доверяет ----------

def _root_with_hooks(guard_copy, command=None):
    root = guard_copy.parents[2]
    (root / ".codex").mkdir(exist_ok=True)
    cmd = command or f"{Path(sys.executable).as_posix()} .claude/hooks/guard.py --runtime codex"
    (root / ".codex" / "hooks.json").write_text(json.dumps(
        {"hooks": {"PreToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": cmd}]}]}}),
        encoding="utf-8")
    return root


def test_preflight_passes_when_guard_answers(guard_copy):
    ok, why = codex_bridge.preflight_hook(_root_with_hooks(guard_copy))
    assert ok, why


def test_preflight_fails_on_broken_or_missing_hook(guard_copy, tmp_path):
    root = _root_with_hooks(guard_copy, command="python-нет-такого .claude/hooks/guard.py --runtime codex")
    ok, why = codex_bridge.preflight_hook(root)
    assert not ok and why
    ok, why = codex_bridge.preflight_hook(tmp_path / "пусто")
    assert not ok and "hooks.json" in why


async def test_ready_runs_trust_canary_once_and_caches(guard_copy, monkeypatch):
    root = _root_with_hooks(guard_copy)
    runs = []

    async def fake_trust(root_, env, codex_cmd):
        runs.append(1)
        (root_ / "state" / "codex_canary.json").write_text(json.dumps({"ts": "now"}), encoding="utf-8")
        return True

    monkeypatch.setattr(codex_bridge, "_trust_canary", fake_trust)
    assert (await codex_bridge.ensure_ready(root=root, now=1000.0)) == (True, "")
    assert (await codex_bridge.ensure_ready(root=root, now=1000.0 + 3600)) == (True, "")
    assert len(runs) == 1                                         # доверие проверено один раз за 6 ч
    await codex_bridge.ensure_ready(root=root, now=1000.0 + 7 * 3600)
    assert len(runs) == 2


async def test_not_trusted_gives_instructions(guard_copy, monkeypatch):
    root = _root_with_hooks(guard_copy)

    async def fake_trust(root_, env, codex_cmd):
        return False

    monkeypatch.setattr(codex_bridge, "_trust_canary", fake_trust)
    ok, why = await codex_bridge.ensure_ready(root=root, now=5.0)
    assert not ok and "/hooks" in why and "JARVIS Guard" in why


def test_read_limits_from_rollout(tmp_path):
    day = tmp_path / "sessions" / "2026" / "10" / "05"
    day.mkdir(parents=True)
    rows = [{"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                "primary": {"used_percent": 10.0, "window_minutes": 300, "resets_at": 1},
                "secondary": {"used_percent": 20.0, "window_minutes": 10080, "resets_at": 2}}}},
            {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                "primary": {"used_percent": 46.0, "window_minutes": 300, "resets_at": 3},
                "secondary": {"used_percent": 61.0, "window_minutes": 10080, "resets_at": 4}}}}]
    (day / "rollout-2026-10-05T10-00-00-thread-abc.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    got = codex_bridge.read_limits("thread-abc", home=tmp_path)
    assert got["primary"]["used_percent"] == 46.0 and got["secondary"]["used_percent"] == 61.0   # последнее
    assert codex_bridge.read_limits("нет-такого", home=tmp_path) is None
