"""Проверка, что команды хуков из runtime/jarvis-settings.json реально исполняются.

Claude Code запускает хуки через Git Bash (`bash -c "<команда>"`), подставляя
$CLAUDE_PROJECT_DIR, и отдаёт им событие JSON на stdin. Этот скрипт делает то же
самое вручную: так видно, работает ли bash-форма команд на Windows, даже когда
сам `claude` недоступен (например, истёк вход).

Запуск:  .venv\\Scripts\\python.exe scripts\\check_hooks.py
Выход:   0 — все случаи как ожидалось, 1 — есть расхождения.

Рабочие файлы проекта скрипт не трогает: хуки и политика копируются во временный корень,
и `CLAUDE_PROJECT_DIR` указывает туда же. Поэтому отказы Guard пишутся во временный
`state/events.jsonl`, а эпизод PreCompact — во временный `memory/episodes/`; настоящий
журнал бота никто не перезаписывает, даже если бот сейчас работает. На `.venv` во временном
корне ставится junction (`mklink /J`) — исполняется тот же python, что и в бою.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "runtime" / "jarvis-settings.json"
SELFCHECK_SESSION = "hook-selfcheck"

# событие → (номер хука в списке matcher'ов, JSON на stdin, ожидаемый код возврата)
CASES: list[tuple[str, str, dict, int]] = [
    ("PreToolUse", "чтение essa-ai/PROFILE.md — пропуск",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Read", "tool_input": {"file_path": "essa-ai/PROFILE.md"}}, 0),
    ("PreToolUse", "чтение .env — отказ",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Read", "tool_input": {"file_path": ".env"}}, 2),
    ("PreToolUse", "запись в runtime/jarvis-settings.json — отказ",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Write", "tool_input": {"file_path": "runtime/jarvis-settings.json",
                                           "content": "{}"}}, 2),
    ("PostToolUse", "запись в MEMORY.md — напоминание",
     {"hook_event_name": "PostToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Write", "tool_input": {"file_path": "MEMORY.md", "content": "x"},
      "tool_response": {"success": True}}, 0),
    ("Stop", "нет транскрипта — молчит",
     {"hook_event_name": "Stop", "session_id": SELFCHECK_SESSION,
      "stop_hook_active": False, "transcript_path": str(ROOT / "state" / "нет-такого.jsonl")}, 0),
    ("PreCompact", "эпизод без транскрипта",
     {"hook_event_name": "PreCompact", "session_id": SELFCHECK_SESSION, "trigger": "manual",
      "transcript_path": str(ROOT / "state" / "нет-такого.jsonl")}, 0),
    ("SessionStart", "подсказка о размере MEMORY.md",
     {"hook_event_name": "SessionStart", "session_id": SELFCHECK_SESSION,
      "source": "startup"}, 0),
]


def find_bash() -> str | None:
    """Тот же bash, которым Claude Code запускает хуки на Windows."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env and Path(env).is_file():
        return env
    found = shutil.which("bash")
    if found:
        return found
    for guess in (r"C:\Program Files\Git\bin\bash.exe",
                  r"C:\Program Files (x86)\Git\bin\bash.exe",
                  str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/bin/bash.exe")):
        if Path(guess).is_file():
            return guess
    return None


def commands(settings: dict, event: str) -> list[str]:
    out = []
    for group in settings.get("hooks", {}).get(event, []):
        for hook in group.get("hooks", []):
            if hook.get("type") == "command" and hook.get("command"):
                out.append(hook["command"])
    return out


def make_sandbox() -> tuple[Path, bool]:
    """Временный корень с копией хуков и политики. True — удалось подставить .venv junction."""
    sandbox = Path(tempfile.mkdtemp(prefix="jarvis-hooks-"))
    shutil.copytree(ROOT / ".claude" / "hooks", sandbox / ".claude" / "hooks",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (sandbox / "runtime").mkdir()
    for name in ("policy.yaml", "jarvis-settings.json"):
        shutil.copy2(ROOT / "runtime" / name, sandbox / "runtime" / name)
    for name in ("MEMORY.md", "CLAUDE.md", "SOUL.md", "GOALS.md"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, sandbox / name)
    (sandbox / "essa-ai").mkdir()
    (sandbox / "essa-ai" / "PROFILE.md").write_text("профиль для проверки\n", encoding="utf-8")
    linked = subprocess.run(["cmd", "/c", "mklink", "/J", str(sandbox / ".venv"),
                             str(ROOT / ".venv")], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode == 0
    return sandbox, linked


def drop_sandbox(sandbox: Path) -> None:
    """Junction снимаем отдельно: рекурсивное удаление по нему ушло бы в настоящий .venv."""
    subprocess.run(["cmd", "/c", "rmdir", str(sandbox / ".venv")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(sandbox, ignore_errors=True)


def run_hook(bash: str, command: str, payload: dict, root: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    done = subprocess.run(
        [bash, "-c", command], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(root), env=env, timeout=120)
    dec = lambda b: b.decode("utf-8", "replace").strip()  # noqa: E731
    return done.returncode, dec(done.stdout), dec(done.stderr)


def main() -> int:
    bash = find_bash()
    if bash is None:
        print("НЕ НАЙДЕН bash: хуки Claude Code на Windows запускаются через Git Bash. "
              "Поставь Git for Windows или задай CLAUDE_CODE_GIT_BASH_PATH.")
        return 1
    print(f"bash: {bash}")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    sandbox, linked = make_sandbox()
    print(f"временный корень: {sandbox}")
    if not linked:
        print("НЕ УДАЛОСЬ подставить .venv (mklink /J) — хуки не найдут python, "
              "проверка недостоверна.")
        drop_sandbox(sandbox)
        return 1
    bad = 0
    try:
        for event, title, payload, expected in CASES:
            cmds = commands(settings, event)
            if not cmds:
                print(f"[{event}] {title}: НЕТ КОМАНДЫ в {SETTINGS.name}")
                bad += 1
                continue
            for command in cmds:
                code, out, err = run_hook(bash, command, payload, sandbox)
                mark = "ok" if code == expected else f"НЕ ТО (ждали {expected})"
                print(f"[{event}] {title}: exit {code} — {mark}")
                for label, text in (("stdout", out), ("stderr", err)):
                    if text:
                        print(f"    {label}: {text[:300]}")
                if code != expected:
                    bad += 1
    finally:
        drop_sandbox(sandbox)
    print("\nИТОГ:", "все команды хуков исполняются как задумано"
          if not bad else f"расхождений: {bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
