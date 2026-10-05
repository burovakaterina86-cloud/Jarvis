"""P4.1a: что реально работает в Codex CLI на её компьютере — ворота для codex_bridge и Guard для Codex.

Повторяет исследование docs/CODEX_RESEARCH.md живыми короткими прогонами `codex exec` во временных
папках (тратит немного её лимита ChatGPT). Что здесь не подтвердилось — не используем.

    .venv\\Scripts\\python.exe tests\\smoke_codex_capabilities.py      # таблица результатов
    .venv\\Scripts\\python.exe -m pytest -q -m smoke tests/smoke_codex_capabilities.py

Хуки проверок пишут только имя инструмента; флаг `--dangerously-bypass-hook-trust` — только здесь,
для временных хуков временной папки. В Jarvis хукам доверяет владелица сама (`/hooks`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

TIMEOUT = 400
PY = Path(sys.executable).as_posix()

HOOK = '''import json, sys
log, how = sys.argv[1], sys.argv[2]
event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
open(log, "a", encoding="utf-8").write(json.dumps({"tool": event.get("tool_name")}) + "\\n")
if how == "json":
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": "deny", "permissionDecisionReason": "smoke"}}))
elif how == "exit2":
    sys.stderr.write("smoke\\n"); sys.exit(2)
elif how == "crash":
    raise RuntimeError("smoke")
'''


def _codex(args: list[str], prompt: str, cwd: Path) -> tuple[list[dict], str]:
    exe = shutil.which("codex")
    if not exe:
        pytest.skip("codex не найден в PATH")
    proc = subprocess.run([exe, *args, "-"], input=prompt.encode("utf-8"), capture_output=True,
                          cwd=str(cwd), timeout=TIMEOUT)
    events = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events, proc.stderr.decode("utf-8", "replace")


def _messages(events) -> list[str]:
    return [e["item"]["text"] for e in events
            if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]


def _thread(events) -> str | None:
    return next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None)


def _repo(tmp: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=str(tmp), capture_output=True)
    return tmp


BASE = ["exec", "--json", "--ephemeral", "--disable", "plugins", "--skip-git-repo-check"]


def check_events(tmp: Path):
    events, _ = _codex(BASE, "Ответь одним словом: да", tmp)
    kinds = [e.get("type") for e in events]
    ok = kinds[:1] == ["thread.started"] and "turn.completed" in kinds and any(_messages(events))
    return ok, f"события: {kinds}"


def check_read_only_via_config(tmp: Path):
    events, _ = _codex(BASE + ["-c", 'sandbox_mode="read-only"'],
                       "Создай файл out.txt с текстом hi. Ответь коротко.", tmp)
    wrote = (tmp / "out.txt").exists()
    return not wrote, f"-c sandbox_mode=read-only: запись {'ПРОШЛА' if wrote else 'не прошла'}"


def check_output_schema(tmp: Path):
    schema = tmp / "schema.json"
    schema.write_text(json.dumps({"type": "object", "additionalProperties": False, "required": ["verdict"],
                                  "properties": {"verdict": {"type": "string", "enum": ["pass", "fix", "fail"]}}}),
                      encoding="utf-8")
    events, _ = _codex(BASE + ["--output-schema", str(schema)], "Задача: скажи привет. Результат: привет. Вердикт?", tmp)
    try:
        data = json.loads((_messages(events) or [""])[-1])
    except ValueError:
        data = None
    return isinstance(data, dict) and data.get("verdict") in ("pass", "fix", "fail"), f"последний ответ: {data}"


def check_developer_instructions(tmp: Path):
    events, _ = _codex(BASE + ["-c", 'developer_instructions="Отвечай ровно одним словом: КАПИБАРА"'],
                       "Как дела?", tmp)
    text = " ".join(_messages(events))
    return "КАПИБАРА" in text, f"ответ: {text[:60]}"


def check_disable_plugins(tmp: Path):
    events, _ = _codex(BASE, "Ответь: да", tmp)
    text = " ".join(_messages(events)).lower()
    return "superpowers" not in text and any(_messages(events)), f"ответ без её плагинов: {text[:60]}"


def check_resume(tmp: Path):
    first, _ = _codex(["exec", "--json", "--disable", "plugins", "--skip-git-repo-check"],
                      "Запомни слово ЛИМОН. Ответь: ок", tmp)
    tid = _thread(first)
    if not tid:
        return False, "нет thread_id"
    second, _ = _codex(["exec", "resume", tid, "--json", "--disable", "plugins", "--skip-git-repo-check"],
                       "Какое слово я просила запомнить? Одним словом.", tmp)
    text = " ".join(_messages(second))
    return "ЛИМОН" in text.upper(), f"thread {tid[:8]}…, ответ: {text[:40]}"


def _hook_run(tmp: Path, how: str, extra: tuple = ()):
    repo = _repo(tmp)
    (repo / ".codex").mkdir(exist_ok=True)
    (repo / "hook.py").write_text(HOOK, encoding="utf-8")
    log = repo / "log.jsonl"
    cmd = f"{PY} {(repo / 'hook.py').as_posix()} {log.as_posix()} {how}"
    (repo / ".codex" / "hooks.json").write_text(json.dumps(
        {"hooks": {"PreToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": cmd, "timeout": 30}]}]}}),
        encoding="utf-8")
    _codex(["exec", "--json", "--ephemeral", "--disable", "plugins", *extra, "-s", "workspace-write",
            "--dangerously-bypass-hook-trust", "-C", str(repo)],
           "Создай файл note.txt с текстом hi. Ответь коротко.", repo)
    calls = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    return calls, (repo / "note.txt").exists()


def check_hook_json_deny(tmp: Path):
    calls, wrote = _hook_run(tmp, "json")
    return calls > 0 and not wrote, f"хук вызван {calls} раз, запись {'ПРОШЛА' if wrote else 'запрещена'}"


def check_hook_exit2_is_not_a_deny(tmp: Path):
    calls, wrote = _hook_run(tmp, "exit2")
    return calls > 0 and wrote, f"(ожидаем, что код 2 НЕ запрещает) вызовов {calls}, запись {'прошла' if wrote else 'запрещена'}"


def check_hook_crash_is_fail_open(tmp: Path):
    calls, wrote = _hook_run(tmp, "crash")
    return calls > 0 and wrote, f"(ожидаем fail-open) вызовов {calls}, запись {'прошла' if wrote else 'запрещена'}"


def check_ignore_user_config_drops_hooks(tmp: Path):
    calls, wrote = _hook_run(tmp, "json", extra=("--ignore-user-config",))
    return calls == 0, f"(ожидаем: без её настроек папка недоверенная — хук не вызван) вызовов {calls}"


CHECKS = [
    ("exec --json: события", check_events),
    ("-c sandbox_mode=read-only не даёт писать", check_read_only_via_config),
    ("--output-schema: ответ по схеме", check_output_schema),
    ("developer_instructions: свои инструкции", check_developer_instructions),
    ("--disable plugins: без её плагинов", check_disable_plugins),
    ("exec resume: продолжение сессии", check_resume),
    ("хук: JSON-запрет работает", check_hook_json_deny),
    ("хук: код 2 не запрещает (известно)", check_hook_exit2_is_not_a_deny),
    ("хук: падение пропускает (известно)", check_hook_crash_is_fail_open),
    ("--ignore-user-config отключает хуки (известно)", check_ignore_user_config_drops_hooks),
]


@pytest.mark.smoke
@pytest.mark.parametrize("title,check", CHECKS, ids=[c[0] for c in CHECKS])
def test_codex_capability(title, check, tmp_path):
    ok, detail = check(tmp_path)
    assert ok, detail


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for title, check in CHECKS:
        with tempfile.TemporaryDirectory(prefix="jarvis-codex-") as d:
            try:
                ok, detail = check(Path(d))
            except subprocess.TimeoutExpired:
                ok, detail = False, f"таймаут {TIMEOUT} с"
        print(f"{'ДА ' if ok else 'НЕТ'} | {title} | {detail}", flush=True)
