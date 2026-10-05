"""P2.0: какие возможности Claude Code реально работают в `claude -p` по подписке.

Ворота для независимого ревьюера (P2.2) и прав субагентов в Guard (P2.3): что здесь не
подтвердилось — не используем. Каждая проверка — короткий запуск на дешёвой модели во временной
папке, с тем же окружением, что у моста (`claude_bridge.build_env`).

    .venv\\Scripts\\python.exe tests\\smoke_cli_capabilities.py      # таблица результатов
    .venv\\Scripts\\python.exe -m pytest -q -m smoke tests/smoke_cli_capabilities.py

Хук проверки 4 пишет только имена полей входа и имя инструмента — не значения.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.claude_bridge import build_env  # noqa: E402

MODEL = "haiku"
TIMEOUT = 300
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict", "problems"],
          "properties": {"verdict": {"type": "string", "enum": ["pass", "fix", "fail"]},
                         "problems": {"type": "array", "items": {"type": "string"}}}}

KEYS_HOOK = '''import json, sys
event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
out = {"tool": event.get("tool_name"), "keys": sorted(event),
       "agent_type": event.get("agent_type") if isinstance(event.get("agent_type"), str) else None}
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(out) + "\\n")
'''


def _claude(args: list[str], prompt: str, cwd: Path) -> dict:
    exe = shutil.which("claude")
    if not exe:
        pytest.skip("claude не найден в PATH")
    proc = subprocess.run([exe, "-p", "--output-format", "json", "--model", MODEL,
                           "--permission-mode", "dontAsk", "--max-turns", "6", *args],
                          input=prompt.encode("utf-8"), capture_output=True, cwd=str(cwd),
                          env=build_env(), timeout=TIMEOUT)
    text = proc.stdout.decode("utf-8", "replace").strip()
    try:
        return json.loads(text.splitlines()[-1]) if text else {"_stderr": proc.stderr.decode("utf-8", "replace")[-500:]}
    except ValueError:
        return {"_raw": text[-500:], "_stderr": proc.stderr.decode("utf-8", "replace")[-500:]}


def check_allowed_tools(tmp: Path) -> tuple[bool, str]:
    (tmp / "note.txt").write_text("кодовое слово: ГРАНАТ\n", encoding="utf-8")
    res = _claude(["--allowedTools", "Read", "Grep", "Glob"],
                  "Сначала прочитай note.txt и назови кодовое слово. Потом создай файл out.txt "
                  "с текстом hi инструментом Write. Ответь коротко.", tmp)
    read_ok = "ГРАНАТ" in str(res.get("result", ""))
    wrote = (tmp / "out.txt").exists()
    return (read_ok and not wrote,
            f"чтение разрешено: {'да' if read_ok else 'НЕТ'}; запись прошла: {'ДА' if wrote else 'нет'}")


def check_json_schema(tmp: Path) -> tuple[bool, str]:
    res = _claude(["--json-schema", json.dumps(SCHEMA)],
                  "Проверь работу. Задача: «скажи привет». Результат: «привет». Дай вердикт.", tmp)
    data = res.get("structured_output")
    where = "structured_output"
    if data is None:
        where = "result"
        try:
            data = json.loads(res.get("result") or "")
        except ValueError:
            data = None
    ok = isinstance(data, dict) and data.get("verdict") in ("pass", "fix", "fail") \
        and isinstance(data.get("problems"), list)
    return ok, f"поле {where}: {json.dumps(data, ensure_ascii=False)[:120] if data else 'нет JSON'}"


def check_no_session_persistence(tmp: Path) -> tuple[bool, str]:
    res = _claude(["--no-session-persistence"], "Ответь одним словом: да.", tmp)
    sid = res.get("session_id")
    if not sid:
        return False, f"нет session_id в ответе: {str(res)[:200]}"
    saved = list((Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    return not saved, f"файл сессии на диске: {'ЕСТЬ' if saved else 'нет'}"


def check_subagent_identity_in_hook(tmp: Path) -> tuple[bool, str]:
    (tmp / "note.txt").write_text("первое слово записки\n", encoding="utf-8")
    hook, log = tmp / "keys_hook.py", tmp / "keys.jsonl"
    hook.write_text(KEYS_HOOK, encoding="utf-8")
    py = Path(sys.executable).as_posix()
    settings = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": f'"{py}" "{hook.as_posix()}" "{log.as_posix()}"'}]}]}}
    (tmp / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    _claude(["--settings", str(tmp / "settings.json"), "--allowedTools", "Agent", "Task", "Read"],
            "Вызови инструмент Agent с subagent_type general-purpose и поручи ему прочитать note.txt "
            "и назвать первое слово. Сам файл не читай. Ответь словом, которое он вернул.", tmp)
    if not log.exists():
        return False, "хук не вызывался"
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    tools = [r["tool"] for r in rows]
    sub = [r for r in rows if r["tool"] == "Read"]
    id_keys = sorted({k for r in sub for k in r["keys"] if "agent" in k})
    main = [r for r in rows if r["tool"] == "Agent"]
    main_keys = sorted({k for r in main for k in r["keys"] if "agent" in k})
    ok = bool(sub) and bool(id_keys) and bool(main) and not main_keys   # главного от субагента отличить можно
    detail = (f"вызовы: {tools}; поля с 'agent' у Read субагента: {id_keys or 'нет'}; "
              f"у главного агента: {main_keys or 'нет'}")
    if sub and sub[0].get("agent_type"):
        detail += f"; agent_type={sub[0]['agent_type']}"
    if sub:
        detail += f"; все поля входа: {sub[0]['keys']}"
    return ok, detail


CHECKS = [
    ("--allowedTools ограничивает инструменты", check_allowed_tools),
    ("--json-schema даёт структурированный ответ", check_json_schema),
    ("--no-session-persistence не пишет сессию", check_no_session_persistence),
    ("хук видит, какой субагент вызвал инструмент", check_subagent_identity_in_hook),
]


@pytest.mark.smoke
@pytest.mark.parametrize("title,check", CHECKS, ids=[c[0] for c in CHECKS])
def test_cli_capability(title, check, tmp_path):
    ok, detail = check(tmp_path)
    assert ok, detail


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for title, check in CHECKS:
        with tempfile.TemporaryDirectory(prefix="jarvis-p20-") as d:
            try:
                ok, detail = check(Path(d))
            except subprocess.TimeoutExpired:
                ok, detail = False, f"таймаут {TIMEOUT} с"
        print(f"{'ЕСТЬ' if ok else 'НЕТ '} | {title} | {detail}", flush=True)
