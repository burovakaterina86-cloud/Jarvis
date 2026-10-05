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

import importlib.util
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
    ("PreToolUse", "сборка карусели python -m integrations.visuals.build — пропуск",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "PowerShell",
      "tool_input": {"command": r".venv\Scripts\python.exe -m integrations.visuals.build essa-ai\content\x"}}, 0),
    ("PreToolUse", "помощник reviewer пишет файл — отказ (права роли)",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION, "agent_id": "a1",
      "agent_type": "reviewer", "tool_name": "Write",
      "tool_input": {"file_path": "essa-ai/content/x/post.md", "content": "x"}}, 2),
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


DEV_SETTINGS = ROOT / ".claude" / "settings.json"

# режим разработки (guard.py --mode dev из .claude/settings.json, ADR 0012): только жёсткие запреты
DEV_CASES: list[tuple[str, dict, int]] = [
    ("чтение .env — отказ",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Read", "tool_input": {"file_path": ".env"}}, 2),
    ("git push --force — отказ",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}, 2),
    ("правка runtime/policy.yaml — пропуск (разработка)",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Edit", "tool_input": {"file_path": "runtime/policy.yaml",
                                          "old_string": "a", "new_string": "b"}}, 0),
    ("git push — пропуск (спросит сам Claude Code)",
     {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
      "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, 0),
]


BIG_READ_KB = 150  # больше порога big_read.max_kb (100) в runtime/policy.yaml


def big_read_results(root: Path) -> list[tuple[str, str, str]]:
    """Заслон больших файлов — через `guard.decide`, а не запуском хука.

    Живой guard.py на ответ «ask» отправил бы владелице запрос в Telegram, поэтому
    здесь решение берётся у чистой функции. Возвращает (случай, ждали, получили).
    """
    spec = importlib.util.spec_from_file_location(
        "jarvis_guard_selfcheck", ROOT / ".claude" / "hooks" / "guard.py")
    guard = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = guard  # dataclass ищет свой модуль в sys.modules
    spec.loader.exec_module(guard)
    policy = guard.load_policy(ROOT / "runtime" / "policy.yaml")
    root = Path(root)
    big = root / "essa-ai" / "big-selfcheck.md"
    big.parent.mkdir(parents=True, exist_ok=True)
    line = b"big read selfcheck line\n"
    big.write_bytes(line * (BIG_READ_KB * 1024 // len(line) + 1))
    cases = [
        (f"чтение файла {BIG_READ_KB} КБ целиком — подтверждение", {}, "ask"),
        (f"чтение куска файла {BIG_READ_KB} КБ — пропуск", {"offset": 1, "limit": 20}, "allow"),
    ]
    out = []
    for title, extra, expected in cases:
        event = {"hook_event_name": "PreToolUse", "session_id": SELFCHECK_SESSION,
                 "tool_name": "Read", "tool_input": {"file_path": str(big), **extra}}
        out.append((title, expected, guard.decide(event, policy, root, env={}).action))
    return out


GIT_BASH_GUESSES = [r"C:\Program Files\Git\bin\bash.exe",
                    r"C:\Program Files (x86)\Git\bin\bash.exe",
                    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/bin/bash.exe")]


def _is_wsl_bash(path: str) -> bool:
    """bash.exe из System32/WindowsApps — это WSL: путей Windows он не видит."""
    low = str(path).replace("/", "\\").lower()
    return "\\windows\\system32\\" in low or "\\windowsapps\\" in low


def find_bash() -> str | None:
    """Тот же bash, которым Claude Code запускает хуки на Windows — Git Bash.

    Раньше брался первый `bash` из PATH, а на этой машине это `C:\\Windows\\System32\\bash.exe`
    (WSL), где `.venv/Scripts/python.exe` не существует. Claude Code берёт
    CLAUDE_CODE_GIT_BASH_PATH или bash рядом с git.exe; так же делаем и здесь. WSL — никогда.
    """
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env and Path(env).is_file():
        return env
    candidates = []
    git = shutil.which("git")
    if git:  # <Git>\cmd\git.exe или <Git>\mingw64\bin\git.exe → <Git>\bin\bash.exe
        git_path = Path(git).resolve()
        candidates += [str(p / "bin" / "bash.exe") for p in git_path.parents[:3]]
    found = shutil.which("bash")
    if found and not _is_wsl_bash(found):
        candidates.append(found)
    candidates += GIT_BASH_GUESSES
    for guess in candidates:
        if Path(guess).is_file() and not _is_wsl_bash(guess):
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
        print("НЕ НАЙДЕН Git Bash: хуки Claude Code на Windows запускаются через него, "
              "а bash из System32 — это WSL, путей проекта он не видит. "
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
        dev_cmds = commands(json.loads(DEV_SETTINGS.read_text(encoding="utf-8")), "PreToolUse")
        if not dev_cmds:
            print(f"[dev] НЕТ КОМАНДЫ PreToolUse в {DEV_SETTINGS.name}")
            bad += 1
        for title, payload, expected in DEV_CASES:
            for command in dev_cmds:
                code, _, err = run_hook(bash, command, payload, sandbox)
                mark = "ok" if code == expected else f"НЕ ТО (ждали {expected})"
                print(f"[dev] {title}: exit {code} — {mark}")
                if code != expected:
                    bad += 1
                    if err:
                        print(f"    stderr: {err[:300]}")
        for title, expected, actual in big_read_results(sandbox):
            mark = "ok" if actual == expected else f"НЕ ТО (ждали {expected})"
            print(f"[decide] {title}: {actual} — {mark}")
            if actual != expected:
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
