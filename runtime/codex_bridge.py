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
    if not session_id:
        args.append("--skip-git-repo-check")
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
