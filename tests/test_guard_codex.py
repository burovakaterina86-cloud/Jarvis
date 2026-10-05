"""Guard для Codex (P4.1b): вход хука Codex → decide() → всегда JSON-ответ.

Входы — как записал живой Codex 0.157.0 (docs/CODEX_RESEARCH.md): shell приходит как `Bash` с
`tool_input.command`, правки файлов — как `apply_patch` с текстом патча в `tool_input.command`.
Запрет у Codex работает только JSON-ом (`permissionDecision: deny`), код 2 он не слушает, а упавший
хук пропускает вызов — поэтому адаптер отвечает JSON-ом всегда и любую ошибку превращает в запрет.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "runtime" / "policy.yaml"

spec = importlib.util.spec_from_file_location("jarvis_guard_codex", REPO / ".claude" / "hooks" / "guard.py")
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)

BOT = {"JARVIS_TASK_ID": "t-codex"}       # бот задаёт номер задачи → полный режим


@pytest.fixture
def root(tmp_path):
    (tmp_path / "state" / "secrets").mkdir(parents=True)
    return tmp_path


def bash(command, cwd=None):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
            "cwd": cwd, "session_id": "s", "turn_id": "t", "tool_use_id": "u"}


def patch(*lines, cwd=None):
    text = "\n".join(["*** Begin Patch", *lines, "*** End Patch"])
    return {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": text},
            "cwd": cwd, "session_id": "s"}


def deny_reason(event, root, env):
    return guard.codex_decision(event, root=root, policy_path=POLICY, env=env)


# ---------- перевод apply_patch ----------

def test_patch_paths_are_extracted():
    ev = patch("*** Add File: a/new.md", "+x", "*** Update File: b.md", "@@", "-1", "+2",
               "*** Delete File: c.md", "*** Update File: d.md", "*** Move to: e.md")
    got = [(e["tool_name"], e["tool_input"].get("file_path") or e["tool_input"].get("command"))
           for e in guard.codex_events(ev)]
    assert got == [("Write", "a/new.md"), ("Edit", "b.md"), ("Bash", "rm c.md"), ("Edit", "d.md"), ("Write", "e.md")]


def test_patch_without_files_is_a_refusal(root):
    assert deny_reason(patch("+висит без файла"), root, BOT)


# ---------- полный режим (бот) ----------

@pytest.mark.parametrize("event", [
    bash("Get-Content .env"),
    bash("git push --force origin main"),
    patch("*** Update File: .claude/hooks/guard.py", "@@", "+x"),
    patch("*** Add File: runtime/x.py", "+x"),
    patch("*** Delete File: drafts/old.md"),                 # удаление → кнопка; Approvals нет → отказ
    patch("*** Add File: ../../outside.txt", "+x"),          # вне папки → кнопка → отказ
    patch("*** Update File: CLAUDE.md", "@@", "+x"),          # свои правила → кнопка → отказ
])
def test_bot_mode_refuses(event, root):
    event["cwd"] = str(root)
    assert deny_reason(event, root, BOT)


@pytest.mark.parametrize("event", [
    bash("Get-ChildItem -Name"),
    bash("python -m integrations.visuals.build essa-ai/content/x"),
    patch("*** Add File: essa-ai/content/x/post.md", "+текст"),
    patch("*** Update File: memory/a.md", "@@", "-1", "+2"),
])
def test_bot_mode_allows_ordinary_work(event, root):
    event["cwd"] = str(root)
    assert deny_reason(event, root, BOT) is None


# ---------- режим разработки (её собственные сессии Codex) ----------

def test_dev_mode_without_task_id_keeps_only_hard_denials(root):
    assert deny_reason(bash("Get-Content .env"), root, {})
    assert deny_reason(bash("git push --force origin main"), root, {})
    ev = patch("*** Update File: .claude/hooks/guard.py", "@@", "+x", cwd=str(root))
    assert deny_reason(ev, root, {}) is None
    assert deny_reason(patch("*** Delete File: drafts/old.md", cwd=str(root)), root, {}) is None


def test_blocked_line_says_codex(root):
    deny_reason(bash("Get-Content .env"), root, BOT)
    line = json.loads((root / "state" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert line["type"] == "blocked" and line["runtime"] == "codex" and line["task_id"] == "t-codex"


# ---------- канарейка: мост проверяет, что хук жив и Codex ему доверяет ----------

def test_canary_is_refused_and_leaves_a_mark(root):
    reason = deny_reason(bash("Get-Content JARVIS_HOOK_CANARY"), root, BOT)
    assert reason and "canary" in reason.lower()
    mark = json.loads((root / "state" / "codex_canary.json").read_text(encoding="utf-8"))
    assert mark["ts"] and mark["task_id"] == "t-codex"


# ---------- сам скрипт: всегда JSON и всегда exit 0 ----------

def _run(guard_copy, data: bytes, env=None):
    import os
    full = {k: v for k, v in os.environ.items() if k != "JARVIS_TASK_ID"}
    full.update(env or {})
    return subprocess.run([sys.executable, str(guard_copy), "--runtime", "codex"], input=data,
                          capture_output=True, timeout=60, env=full)


def test_script_denies_with_json_and_exit0(guard_copy):
    r = _run(guard_copy, json.dumps(bash("Get-Content .env")).encode("utf-8"), BOT)
    assert r.returncode == 0
    out = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "JARVIS Guard" in out["permissionDecisionReason"]


def test_script_allows_silently(guard_copy):
    r = _run(guard_copy, json.dumps(bash("Get-ChildItem")).encode("utf-8"), BOT)
    assert r.returncode == 0 and r.stdout.strip() == b""


def test_script_garbage_is_a_json_refusal(guard_copy):
    r = _run(guard_copy, b"not json{", BOT)
    assert r.returncode == 0
    assert json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_project_hooks_file_points_to_codex_runtime():
    hooks = json.loads((REPO / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    entry = hooks["hooks"]["PreToolUse"][0]
    cmd = entry["hooks"][0]["command"]
    assert entry["matcher"] in (".*", "*") and "guard.py" in cmd and "--runtime codex" in cmd


def test_agent_cannot_touch_codex_hooks():
    d = guard.decide({"tool_name": "Write", "tool_input": {"file_path": ".codex/hooks.json", "content": "{}"}},
                     policy=guard.load_policy(POLICY), root=REPO, env={})
    assert d.action == "deny" and d.kind == "protected"
