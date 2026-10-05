"""Мост к Codex (аудит P4.1d): один ход `codex exec --json`, разбор событий в `TurnResult`.

Тот же контракт, что у `claude_bridge.run_turn`, — роутеру всё равно, кто исполнитель. Codex — запасной
worker, пока у Claude кончился лимит (её кнопка). Возможности проверены живьём: docs/CODEX_RESEARCH.md,
tests/smoke_codex_capabilities.py.

- «Мозг» Jarvis (`CLAUDE.md` без `@`-импортов + SOUL/GOALS/MEMORY + jarvis-turn.md) — через
  `-c developer_instructions=…` одной строкой (TOML-строка = JSON-строка): свой `AGENTS.md` Codex читает
  сам, а у нас это заметки разработчика.
- Её `~/.codex/config.toml` грузим: в нём записано доверие к папке, без него Codex считает проект недоверенным —
  включает read-only и НЕ запускает проектные хуки (проверено живьём). Поэтому не `--ignore-user-config`, а
  `--disable plugins` (её плагины в фоновый ход не попадают); её MCP-сервер даёт только шум в stderr.
- Песочница `workspace-write` с сетью (интеграциям нужна сеть), `approval_policy="never"`: спрашивает не
  Codex, а Guard — хук `.codex/hooks.json` (`guard.py --runtime codex`) с кнопками владелицы.
- `codex.cmd` — пакетный файл npm: cmd.exe портит `%` и переводы строк в аргументах, поэтому запускаем
  `node …/@openai/codex/bin/codex.js` напрямую.
- Продолжение разговора — `codex exec resume <thread_id>` (у него нет `-s`/`-C`: песочница через `-c`,
  папка — рабочий каталог процесса).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from runtime import events
from runtime.claude_bridge import DEFAULT_OPTIONS, TURN_PROMPT_FILE, TurnOptions, TurnResult, build_env
from runtime.redact import tool_summary

ROOT = Path(__file__).resolve().parents[1]
STREAM_LIMIT = 32 * 1024 * 1024
BRAIN_FILES = ("CLAUDE.md", "SOUL.md", "GOALS.md", "MEMORY.md")
CODEX_NOTE = (
    "Ты — JARVIS и сейчас работаешь через Codex: это запасной исполнитель, пока у Claude Code кончился лимит. "
    "Правила те же. Навыки — в .agents/skills/, помощники — в .codex/agents/, правила безопасности и памяти — "
    ".claude/rules/*.md (читай нужное). Файл AGENTS.md в корне — заметки разработчика, не твои инструкции. "
    "Каждое действие проверяет JARVIS Guard; его отказ — не ошибка для обхода."
)
RATE_MARKERS = ("usage limit", "rate limit", "limit reached", "you've hit your", "too many requests", "quota")
AUTH_MARKERS = ("unauthorized", "401", "codex login", "not logged in", "authentication", "expired token")
RATE_TEXT = "Лимит подписки Codex исчерпан — сейчас продолжить в Codex не получится."
AUTH_TEXT = "Нужно заново войти в Codex на компьютере: в терминале выполни codex login."

_running: dict[str, asyncio.subprocess.Process] = {}
_stopped: set[str] = set()


def brain(prompt_file: Path | None = None) -> str:
    """Инструкции для Codex: «мозг» хода или промпт роли (проверяющий)."""
    if prompt_file is not None and Path(prompt_file) != TURN_PROMPT_FILE:
        return CODEX_NOTE + "\n\n" + Path(prompt_file).read_text(encoding="utf-8")
    parts = [CODEX_NOTE]
    for name in BRAIN_FILES:
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except OSError:
            continue
        parts.append("\n".join(line for line in text.splitlines() if not line.startswith("@")))
    parts.append(TURN_PROMPT_FILE.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def default_codex_cmd() -> list[str]:
    exe = shutil.which("codex")
    if not exe:
        raise FileNotFoundError("codex не найден в PATH")
    if exe.lower().endswith((".cmd", ".bat")):
        js = Path(exe).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if js.is_file() and node:
            return [node, str(js)]
    return [exe]


def build_args(session_id: str | None, options: TurnOptions = DEFAULT_OPTIONS,
               schema_path: Path | None = None) -> list[str]:
    head = ["exec", "resume", session_id] if session_id else ["exec"]
    sandbox = "read-only" if getattr(options, "read_only", False) else "workspace-write"
    args = head + ["--json", "--disable", "plugins",
                   "-c", f'sandbox_mode="{sandbox}"',
                   "-c", 'approval_policy="never"',
                   "-c", "sandbox_workspace_write.network_access=true",
                   "-c", "developer_instructions=" + json.dumps(brain(options.prompt_file), ensure_ascii=False)]
    args.append("--skip-git-repo-check")   # есть и у exec, и у exec resume
    if not options.persist:
        args.append("--ephemeral")
    if schema_path is not None:
        args += ["--output-schema", str(schema_path)]
    return args + ["-"]


def _rel(path: str, cwd) -> str:
    try:
        return Path(os.path.normpath(path)).relative_to(Path(os.path.normpath(cwd))).as_posix()
    except (ValueError, TypeError):
        return str(path).replace(chr(92), "/")


async def _call(cb, event):
    if cb is None:
        return
    try:
        r = cb(event)
        if inspect.isawaitable(r):
            await r
    except Exception:  # колбэк не должен ронять ход
        pass


_TOOL_OF_ITEM = {"command_execution": "Bash", "file_change": "apply_patch"}


async def run_turn(prompt: str, session_id: str | None = None, on_event=None, *,
                   run_id: str | None = None, task: str = "", env: dict | None = None,
                   codex_cmd: list[str] | None = None, cwd: str | Path | None = None,
                   task_id: str = "", options: TurnOptions = DEFAULT_OPTIONS, **_ignored) -> TurnResult:
    """Один ход Codex. Никогда не бросает исключений — ошибка в TurnResult (runtime="codex")."""
    run_id = run_id or uuid.uuid4().hex
    cwd = Path(cwd or ROOT)
    child_env = build_env(env)
    if task_id:
        child_env["JARVIS_TASK_ID"] = task_id   # хук Guard: есть номер задачи → полный режим
    _stopped.discard(run_id)
    schema_file = None
    base = {"session": session_id, "agent": "jarvis", "task": task, "task_id": task_id, "runtime": "codex"}
    thread, texts, files, tools, failure = session_id, [], [], 0, None
    try:
        if options.json_schema is not None:
            fd, name = tempfile.mkstemp(prefix="jarvis-schema-", suffix=".json")
            os.close(fd)
            schema_file = Path(name)
            schema_file.write_text(json.dumps(options.json_schema, ensure_ascii=False), encoding="utf-8")
        cmd = list(codex_cmd or default_codex_cmd()) + build_args(session_id, options, schema_file)
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {}
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd), env=child_env, limit=STREAM_LIMIT, **kwargs)
        _running[run_id] = proc
        try:
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        err_task = asyncio.create_task(proc.stderr.read())
        completed = False
        while True:
            try:
                raw = await proc.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError):
                continue
            if not raw:
                break
            try:
                ev = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind, item = ev.get("type"), ev.get("item") or {}
            if kind == "thread.started":
                thread = ev.get("thread_id") or thread
                base["session"] = thread
            elif kind == "item.started" and item.get("type") in _TOOL_OF_ITEM:
                tools += 1
                name = _TOOL_OF_ITEM[item["type"]]
                summary = tool_summary("Bash", {"command": item.get("command", "")}) if name == "Bash" else \
                    ", ".join(_rel(c.get("path", ""), cwd) for c in item.get("changes") or [])
                events.emit("tool_use", tool=name, summary=summary, **base)
                await _call(on_event, {"type": "assistant", "session_id": thread,
                                       "message": {"content": [{"type": "tool_use", "name": name}]}})
            elif kind == "item.started" and item.get("type") == "mcp_tool_call":
                tools += 1
                name = f"mcp__{item.get('server', '')}__{item.get('tool', '')}"
                events.emit("tool_use", tool=name, summary="", **base)
                await _call(on_event, {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name}]}})
            elif kind == "item.completed" and item.get("type") == "file_change":
                for change in item.get("changes") or []:
                    rel = _rel(change.get("path", ""), cwd)
                    if rel and rel not in files:
                        files.append(rel)
            elif kind == "item.completed" and item.get("type") == "agent_message":
                texts.append(item.get("text", ""))
                events.emit("assistant_message", text=str(item.get("text", ""))[:500], **base)
            elif kind == "turn.completed":
                completed = True
            elif kind == "turn.failed":
                failure = str((ev.get("error") or {}).get("message") or "turn.failed")
        returncode = await proc.wait()
        stderr = (await err_task).decode("utf-8", "replace")[-2000:]
    except Exception as exc:  # noqa: BLE001
        events.emit("error", error=repr(exc)[:500], status="failed", **base)
        return TurnResult("", session_id, False, None, "error", repr(exc)[:500], runtime="codex", attempts=0)
    finally:
        _running.pop(run_id, None)
        if schema_file is not None:
            schema_file.unlink(missing_ok=True)

    new = thread is not None and thread != session_id
    common = dict(tool_uses=tools, files=files, runtime="codex")
    if run_id in _stopped:
        _stopped.discard(run_id)
        return TurnResult("Остановлено.", thread, new, None, "stopped", "stopped", **common)
    blob = " ".join([failure or "", stderr if not completed else ""]).lower()
    if not completed and any(m in blob for m in RATE_MARKERS):
        events.emit("error", subtype="rate_limit", error=(failure or "")[:300], **base)
        return TurnResult(RATE_TEXT, thread, new, None, "rate_limited", "rate_limit", **common)
    if not completed and any(m in blob for m in AUTH_MARKERS):
        return TurnResult(AUTH_TEXT, thread, new, None, "auth_required", "authentication_failed", **common)
    text = texts[-1] if texts else ""
    if not completed or returncode not in (0, None):
        error = (failure or stderr.strip() or f"exit {returncode}")[:1000]
        events.emit("result", subtype="error", status="failed", progress=1.0, **base)
        return TurnResult(text, thread, new, None, "error", error, **common)
    events.emit("result", subtype="success", status="done", progress=1.0, **base)
    res = TurnResult(text, thread, new, None, "ok", None, **common)
    if options.json_schema is not None:
        try:
            data = json.loads(text)
            res.structured = data if isinstance(data, dict) else None
        except ValueError:
            res.structured = None
    return res


def stop(run_id: str) -> bool:
    """Убивает дерево процесса хода Codex. True, если ход был запущен."""
    proc = _running.get(run_id)
    if proc is None:
        return False
    _stopped.add(run_id)
    if proc.returncode is None:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    return True


# ---------- готовность: Guard отвечает и Codex ему доверяет (P4.1c) ----------

CANARY = "JARVIS_HOOK_CANARY"
TRUST_TTL_SEC = 6 * 3600
HOOK_BROKEN_TEXT = ("Codex не запускаю: Guard для Codex не отвечает ({why}). "
                    "Без проверки разрешений Codex подключать нельзя.")
TRUST_TEXT = ("Codex не запускаю: он ещё не доверяет хукам Jarvis, значит Guard в нём не работает.\n"
              "Как включить (один раз):\n"
              "1. Открой терминал в папке Jarvis.\n"
              "2. Запусти: codex\n"
              "3. Введи /hooks и подтверди хук «JARVIS Guard».\n"
              "4. Выйди из Codex и нажми «Продолжить в Codex» ещё раз.")


def _hook_command(root: Path) -> str | None:
    try:
        data = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        return data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def preflight_hook(root: Path | str = ROOT) -> tuple[bool, str]:
    """Канарейка без Codex: команда хука из .codex/hooks.json на заведомо запрещённом вызове обязана
    ответить JSON-запретом. Хук Codex fail-open — поэтому мост не запускает Codex, пока хук молчит."""
    root = Path(root)
    command = _hook_command(root)
    if not command:
        return False, "нет .codex/hooks.json с командой PreToolUse"
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(root),
             "tool_input": {"command": f"Get-Content {CANARY}"}}
    env = build_env()
    env["JARVIS_TASK_ID"] = "preflight"
    try:
        proc = subprocess.run(command.split(), input=json.dumps(event).encode("utf-8"), capture_output=True,
                              cwd=str(root), env=env, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        answer = json.loads(proc.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
        out = answer["hookSpecificOutput"]
        if out.get("permissionDecision") == "deny" and "canary" in str(out.get("permissionDecisionReason")):
            return True, ""
        return False, f"хук ответил не так: {out}"
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
        return False, f"хук не запустился: {type(exc).__name__}"


async def _trust_canary(root: Path, env: dict | None, codex_cmd: list[str] | None) -> bool:
    """Короткий ход Codex с командой-канарейкой: если Guard её увидел (оставил отметку) — хукам доверяют."""
    mark = root / "state" / "codex_canary.json"
    before = mark.stat().st_mtime if mark.exists() else 0.0
    child_env = build_env(env)
    child_env["JARVIS_TASK_ID"] = "trust-check"
    cmd = list(codex_cmd or default_codex_cmd()) + [
        "exec", "--json", "--ephemeral", "--disable", "plugins", "--skip-git-repo-check",
        "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
        f"Выполни в PowerShell ровно одну команду: Get-Content {CANARY} . Ответь одним словом."]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL, cwd=str(root), env=child_env)
        await asyncio.wait_for(proc.wait(), 300)
    except (OSError, asyncio.TimeoutError):
        return False
    return mark.exists() and mark.stat().st_mtime > before


async def ensure_ready(root: Path | str = ROOT, env: dict | None = None, codex_cmd: list[str] | None = None,
                       now: float | None = None) -> tuple[bool, str]:
    """(можно запускать Codex, причина отказа для владелицы)."""
    import time as _time
    root = Path(root)
    now = _time.time() if now is None else now
    ok, why = await asyncio.to_thread(preflight_hook, root)
    if not ok:
        return False, HOOK_BROKEN_TEXT.format(why=why)
    trust_file = root / "state" / "codex_trust.json"
    try:
        last = float(json.loads(trust_file.read_text(encoding="utf-8")).get("ts", 0))
    except (OSError, ValueError, AttributeError):
        last = 0.0
    if last and now - last < TRUST_TTL_SEC:   # нет записи — доверие ещё не проверяли
        return True, ""
    if not await _trust_canary(root, env, codex_cmd):
        return False, TRUST_TEXT
    trust_file.parent.mkdir(parents=True, exist_ok=True)
    trust_file.write_text(json.dumps({"ts": now}), encoding="utf-8")
    return True, ""


# ---------- лимиты Codex из файла сессии (P4.1f) ----------

def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def read_limits(thread_id: str, home: Path | str | None = None) -> dict | None:
    """Последние `rate_limits` из файла сессии Codex (`~/.codex/sessions/**/rollout-*<thread>.jsonl`)."""
    if not thread_id:
        return None
    base = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    files = sorted(base.rglob(f"*{thread_id}*.jsonl")) if base.is_dir() else []
    if not files:
        return None
    try:
        lines = files[-1].read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"rate_limits"' not in line:
            continue
        try:
            found = _find_key(json.loads(line), "rate_limits")
        except ValueError:
            continue
        if isinstance(found, dict):
            return {k: found[k] for k in ("primary", "secondary") if isinstance(found.get(k), dict)}
    return None
