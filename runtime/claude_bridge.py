"""Мост к Claude Code: один ход `claude -p` и разбор stream-json.

Ничего не знает про Telegram. Думает Claude Code по подписке владелицы;
Python только запускает процесс, передаёт промпт через stdin и разбирает поток.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from runtime import events

ROOT = Path(__file__).resolve().parents[1]
TURN_PROMPT_FILE = ROOT / "runtime" / "jarvis-turn.md"
SETTINGS_FILE = ROOT / "runtime" / "jarvis-settings.json"
MAX_TURNS = 60
STREAM_LIMIT = 32 * 1024 * 1024

# Переменные, которые не должны попасть в окружение claude: всё служебное окружение
# родительской сессии Claude Code (иначе дочерний claude уходит на хост-авторизацию
# вместо подписки владелицы — D02) и Telegram-секреты.
_ENV_DROP_PREFIX = ("CLAUDE", "ANTHROPIC", "TELEGRAM")
_ENV_KEEP = {"CLAUDE_CODE_GIT_BASH_PATH"}  # нужен claude на Windows


@dataclass
class TurnResult:
    text: str
    session_id: str | None
    new_session: bool
    cost_usd: float | None
    status: str  # ok | stopped | rate_limited | auth_required | error
    error: str | None = None


_running: dict[str, asyncio.subprocess.Process] = {}
_stopped: set[str] = set()


def build_env(base: dict | None = None) -> dict:
    """Окружение дочернего claude: всё из base, кроме CLAUDE*/ANTHROPIC*/TELEGRAM*
    (исключение — _ENV_KEEP). JARVIS_* и остальное окружение процесса передаётся как есть."""
    src = dict(os.environ if base is None else base)
    return {k: v for k, v in src.items()
            if k.upper() in _ENV_KEEP or not k.upper().startswith(_ENV_DROP_PREFIX)}


def build_args(session_id: str | None) -> list[str]:
    args = ["-p", "--output-format", "stream-json", "--verbose"]
    if session_id:
        args += ["--resume", session_id]
    args += ["--permission-mode", "dontAsk",
             "--append-system-prompt-file", str(TURN_PROMPT_FILE),
             "--settings", str(SETTINGS_FILE),
             "--max-turns", str(MAX_TURNS)]
    return args


def default_claude_cmd() -> list[str]:
    exe = shutil.which("claude")
    if not exe:
        raise FileNotFoundError("claude не найден в PATH")
    return [exe]


async def _call(cb, event):
    if cb is None:
        return
    try:
        r = cb(event)
        if inspect.isawaitable(r):
            await r
    except Exception:  # колбэк владельца не должен ронять ход
        pass


def _short(s, n=500):
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[:n] + "…"


def _log_event(ev: dict, sid: str | None, task: str) -> None:
    """Переводит событие stream-json в словарь events.jsonl."""
    t, sub = ev.get("type"), ev.get("subtype")
    agent = "subagent" if ev.get("parent_tool_use_id") else "jarvis"
    base = {"session": ev.get("session_id") or sid, "agent": agent, "task": task}
    content = (ev.get("message") or {}).get("content") or []
    if t == "assistant":
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "text":
                events.emit("assistant_message", text=_short(block.get("text", "")), **base)
            elif block.get("type") == "tool_use":
                events.emit("tool_use", tool=block.get("name"), **base)
    elif t == "user":
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                events.emit("tool_result", tool_use_id=block.get("tool_use_id"),
                            is_error=bool(block.get("is_error")), **base)
    elif t == "result":
        failed = bool(ev.get("is_error")) or (sub not in (None, "success"))
        events.emit("result", cost=ev.get("total_cost_usd"), duration=ev.get("duration_ms"),
                    subtype=sub, **{**base, "status": "failed" if failed else "done",
                                    "progress": 1.0})
    elif t == "system" and sub == "api_retry":
        events.emit("error", subtype="api_retry", error=ev.get("error"),
                    error_status=ev.get("error_status"), attempt=ev.get("attempt"), **base)
    elif t == "rate_limit_event":
        info = ev.get("rate_limit_info") or {}
        if info.get("status") not in (None, "allowed", "allowed_warning"):
            events.emit("error", subtype="rate_limit", resets_at=info.get("resetsAt"), **base)


class _Outcome:
    def __init__(self):
        self.session_id = None
        self.result = None
        self.texts: list[str] = []
        self.api_error = None
        self.resets_at = None
        self.activity = False
        self.returncode = None
        self.stderr = ""


async def _run_once(prompt, session_id, on_event, run_id, task, env, claude_cmd, cwd) -> _Outcome:
    cmd = list(claude_cmd) + build_args(session_id)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=str(cwd), env=env, limit=STREAM_LIMIT, **kwargs)
    _running[run_id] = proc
    out = _Outcome()

    async def feed():
        try:
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    async def drain_err():
        data = await proc.stderr.read()
        out.stderr = data.decode("utf-8", "replace")[-4000:]

    feeder = asyncio.create_task(feed())
    err_task = asyncio.create_task(drain_err())
    try:
        while True:
            try:
                raw = await proc.stdout.readline()
            except (ValueError, asyncio.LimitOverrunError):
                continue
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            _absorb(out, ev)
            _log_event(ev, out.session_id or session_id, task)
            await _call(on_event, ev)
        out.returncode = await proc.wait()
        await asyncio.gather(feeder, err_task, return_exceptions=True)
    finally:
        _running.pop(run_id, None)
    return out


def _absorb(out: _Outcome, ev: dict) -> None:
    t, sub = ev.get("type"), ev.get("subtype")
    if ev.get("session_id") and (t == "result" or (t == "system" and sub == "init")):
        out.session_id = ev["session_id"]
    if t in ("assistant", "user"):
        out.activity = True
        if t == "assistant" and not ev.get("parent_tool_use_id"):
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    out.texts.append(block.get("text", ""))
    elif t == "result":
        out.result = ev
    elif t == "system" and sub == "api_retry" and ev.get("error") in ("rate_limit", "authentication_failed"):
        out.api_error = ev["error"]
    elif t == "rate_limit_event":
        info = ev.get("rate_limit_info") or {}
        if info.get("status") == "rejected":
            out.api_error = "rate_limit"
            out.resets_at = info.get("resetsAt")


_OVERFLOW_MARKERS = ("prompt is too long", "context window", "context length",
                     "maximum context", "context_length_exceeded")


def _is_overflow(out: _Outcome) -> bool:
    res = out.result or {}
    # Только служебные каналы: фраза «context window» в ответе агента — не переполнение.
    blob = " ".join([str(res.get("result") or ""), out.stderr]).lower()
    return any(m in blob for m in _OVERFLOW_MARKERS)


def _overflow_prompt(prompt: str) -> str:
    return ("[JARVIS] Предыдущий разговор переполнил контекст, поэтому начат новый. "
            "Если нужно, загляни в memory/episodes за итогами прошлой сессии. "
            "Сводка последней задачи — сообщение владелицы, на которое нужно ответить:\n\n"
            + prompt)


def _human_rate_limit(resets_at) -> str:
    try:
        from datetime import datetime
        when = datetime.fromtimestamp(float(resets_at)).strftime("%H:%M")
        return f"Лимит подписки Claude исчерпан, продолжу в {when}."
    except (TypeError, ValueError, OverflowError, OSError):
        return "Лимит подписки Claude исчерпан, продолжу, когда он обновится."


def _AUTH_MARKERS(blob: str) -> bool:  # noqa: N802
    return any(m in blob for m in ("failed to authenticate", "oauth session expired",
                                   "invalid api key", "please run /login", "authentication_failed",
                                   "credentials are invalid"))


AUTH_TEXT ="Нужно заново войти в Claude на компьютере: открой терминал и выполни claude, затем /login."


def _to_result(out: _Outcome, session_id_in: str | None, run_id: str | None = None) -> TurnResult:
    sid = out.session_id or session_id_in
    new = sid is not None and sid != session_id_in
    res = out.result or {}
    cost = res.get("total_cost_usd")
    if run_id in _stopped:
        return TurnResult("Остановлено.", sid, new, cost, "stopped", "stopped")
    if out.api_error == "rate_limit" and not (out.result and not res.get("is_error")):
        return TurnResult(_human_rate_limit(out.resets_at), sid, new, cost, "rate_limited", "rate_limit")
    failed = out.result is None or res.get("is_error") or res.get("subtype") not in (None, "success")
    blob = " ".join([str(res.get("result") or ""), out.stderr]).lower()
    if failed and (out.api_error == "authentication_failed" or _AUTH_MARKERS(blob)):
        return TurnResult(AUTH_TEXT, sid, new, cost, "auth_required", "authentication_failed")
    text = res.get("result") if isinstance(res.get("result"), str) else "\n\n".join(out.texts)
    ok = out.result is not None and not res.get("is_error") and res.get("subtype") in (None, "success")
    if ok:
        return TurnResult(text or "", sid, new, cost, "ok", None)
    return TurnResult(text or "", sid, new, cost, "error",
                      _short((text or out.stderr or f"exit {out.returncode}").strip(), 1000))


async def run_turn(prompt: str, session_id: str | None = None, on_event=None, *,
                   run_id: str | None = None, task: str = "", env: dict | None = None,
                   claude_cmd: list[str] | None = None, cwd: str | Path | None = None) -> TurnResult:
    """Выполняет один ход Claude Code. Никогда не бросает исключений — ошибка в TurnResult."""
    run_id = run_id or uuid.uuid4().hex
    child_env = build_env(env)
    cwd = cwd or ROOT
    _stopped.discard(run_id)
    try:
        cmd = claude_cmd or default_claude_cmd()
        out = await _run_once(prompt, session_id, on_event, run_id, task, child_env, cmd, cwd)
        res = _to_result(out, session_id, run_id)
        if session_id and res.status == "error" and out.activity:
            # Ход уже вызывал инструменты: повтор мог бы повторить внешнее действие.
            res.error = res.error or "turn_failed"
            res.text = (res.text or "") + (
                "\n\nХод оборвался уже после вызова инструментов, поэтому я не повторяю его сам — "
                "часть действий могла выполниться. Скажи, что делать дальше, или начни заново "
                "командой /new.")
            return res
        if session_id and res.status == "error" and _is_overflow(out):
            # Контекст переполнен: новая сессия со сводкой последней задачи.
            events.emit("error", subtype="context_overflow", session=session_id, task=task)
            out = await _run_once(_overflow_prompt(prompt), None, on_event, run_id, task,
                                  child_env, cmd, cwd)
            res = _to_result(out, None, run_id)
            res.new_session = True
        elif session_id and res.status == "error" and not out.activity:
            # resume не удался (сессия повреждена/истекла) — один повтор без него.
            events.emit("error", subtype="resume_failed", session=session_id, task=task,
                        error=_short(out.stderr.strip(), 300))
            out = await _run_once(prompt, None, on_event, run_id, task, child_env, cmd, cwd)
            res = _to_result(out, None, run_id)
            res.new_session = True
        return res
    except Exception as exc:  # noqa: BLE001
        events.emit("error", error=_short(repr(exc)), task=task, session=session_id, status="failed")
        return TurnResult("", session_id, False, None, "error", _short(repr(exc)))
    finally:
        _stopped.discard(run_id)


def stop(run_id: str) -> bool:
    """Убивает дерево процесса хода. True, если ход был запущен."""
    proc = _running.get(run_id)
    if proc is None:
        return False
    _stopped.add(run_id)
    if proc.returncode is not None:
        return True
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass
    return True
