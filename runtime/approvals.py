"""Approvals API: локальный HTTP-сервис, через который Guard спрашивает владелицу.

Контракт (interfaces.md):
  POST http://127.0.0.1:<port>/approve, заголовок X-Jarvis-Token,
  тело {"level": "EXTERNAL|MONEY", "tool": str, "summary": str, "details": dict}
  -> 200 {"decision": "allow"|"deny", "reason": str}; без токена/с чужим -> 401.
Порт: <root>/state/approvals.port, токен: <root>/state/secrets/approvals.token (создаются в start).

Использование из Telegram-слоя (в его asyncio-цикле):
  srv = ApprovalsServer(); port = await srv.start(root)
  srv.on_request(cb)   # cb(request_id, level, tool, summary, details), sync или async
  srv.resolve(request_id, "allow"|"deny", reason="")
  await srv.stop()
"""
from __future__ import annotations

import asyncio
import copy
import getpass
import hmac
import inspect
import json
import logging
import os
import secrets
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from runtime.redact import redact_obj

log = logging.getLogger("jarvis.approvals")

HOST = "127.0.0.1"
LEVELS = ("EXTERNAL", "MONEY")
DECISIONS = ("allow", "deny")
# строго меньше общего срока Guard (approval_timeout_sec: 590): сервер отвечает deny раньше, чем Guard сдаётся
DEFAULT_TIMEOUT = 580.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, record: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        log.exception("не удалось записать %s", path.name)


def emit_event(root: Path, type: str, **fields) -> None:
    """Временная замена runtime.events.emit (таск 02): одна JSON-строка в state/events.jsonl."""
    record = {"ts": _now(), "type": type, "session": None, "agent": "jarvis", "task": "",
              "status": "working", "progress": None}
    record.update(redact_obj(fields))
    _append_jsonl(Path(root) / "state" / "events.jsonl", record)


JOURNAL_STR_LIMIT = 500


def _truncate(value):
    """Копия структуры, где каждая строка без секретов и обрезана до JOURNAL_STR_LIMIT символов.

    Владелица на кнопке видит запрос целиком; в журнал на диске значения токенов не попадают.
    """
    if isinstance(value, str):
        return redact_obj(value)[:JOURNAL_STR_LIMIT]
    if isinstance(value, dict):
        return {k: _truncate(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_truncate(v) for v in value]
    return value


def _restrict_to_owner(path: Path) -> bool:
    """Доступ к файлу только текущему пользователю. True — получилось."""
    try:
        if sys.platform == "win32":
            user = os.environ.get("USERNAME") or getpass.getuser()
            domain = os.environ.get("USERDOMAIN")
            account = f"{domain}\\{user}" if domain else user
            res = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:F"],
                                 capture_output=True, timeout=10, check=False)
            return res.returncode == 0
        os.chmod(path, 0o600)
        return True
    except Exception:
        return False


class ApprovalsServer:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = float(timeout)
        self.root: Path | None = None
        self.port: int | None = None
        self._token = ""
        self._callbacks: list = []
        self._pending: dict[str, asyncio.Future] = {}
        self._records: dict[str, dict] = {}
        self._cancelled_tasks: set[str] = set()
        self._tasks: set[asyncio.Future] = set()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    # ---------- публичный API ----------

    def on_request(self, callback) -> None:
        """callback(request_id, level, tool, summary, details); может быть корутинной функцией."""
        self._callbacks.append(callback)

    def resolve(self, request_id: str, decision: str, reason: str = "") -> bool:
        """Решение владелицы. False — запроса нет (уже решён, истёк или неизвестен)."""
        if decision not in DECISIONS:
            raise ValueError(f"decision must be allow|deny, got {decision!r}")
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return False
        fut.set_result((decision, reason or ""))
        return True

    @property
    def pending(self) -> list[str]:
        return [rid for rid, f in self._pending.items() if not f.done()]

    def pending_records(self, task_ids: set[str] | None = None) -> list[dict]:
        return [copy.deepcopy(self._records[rid]) for rid in self.pending
                if rid in self._records and (task_ids is None or self._records[rid]["task_id"] in task_ids)]

    def cancel_tasks(self, task_ids: set[str]) -> list[str]:
        self._cancelled_tasks.update(task_ids)
        ids = [r["request_id"] for r in self.pending_records(task_ids)]
        for rid in ids:
            self.resolve(rid, "deny", "stopped")
        return ids

    @property
    def addresses(self) -> list[tuple[str, int]]:
        """Фактические адреса привязки слушающих сокетов."""
        server = getattr(self._site, "_server", None)
        return [s.getsockname()[:2] for s in (server.sockets if server else [])]

    async def start(self, root) -> int:
        if self._runner is not None:
            raise RuntimeError("Approvals API уже запущен")
        self.root = Path(root)
        state = self.root / "state"
        secrets_dir = state / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        port_file = state / "approvals.port"
        port_file.unlink(missing_ok=True)  # пока нет нового порта — Guard отказывает

        self._token = secrets.token_urlsafe(32)
        token_file = secrets_dir / "approvals.token"
        token_file.unlink(missing_ok=True)
        # пустой файл -> права только владельцу -> потом содержимое
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        if not _restrict_to_owner(token_file):
            log.warning("не удалось ограничить права на %s", token_file.name)
            emit_event(self.root, "error", error="approvals_token_permissions",
                       reason="не удалось ограничить права на файл токена")
        token_file.write_text(self._token, encoding="utf-8")

        app = web.Application()
        app.router.add_post("/approve", self._handle)
        # handler_cancellation: закрытое Guard'ом соединение отменяет обработчик -> client_gone
        self._runner = web.AppRunner(app, handle_signals=False, handler_cancellation=True)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, HOST, 0)
        await self._site.start()
        self.port = self.addresses[0][1]

        tmp = port_file.with_suffix(".port.tmp")
        tmp.write_text(str(self.port), encoding="utf-8")
        os.replace(tmp, port_file)
        log.info("Approvals API слушает %s:%s", HOST, self.port)
        return self.port

    async def stop(self) -> None:
        if self.root is not None:
            (self.root / "state" / "approvals.port").unlink(missing_ok=True)
            (self.root / "state" / "secrets" / "approvals.token").unlink(missing_ok=True)
        for rid in self.pending:
            self.resolve(rid, "deny", "shutdown")
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = self._site = None
        self.port = None

    # ---------- HTTP ----------

    async def _handle(self, request: web.Request) -> web.Response:
        given = request.headers.get("X-Jarvis-Token", "")
        if not self._token or not hmac.compare_digest(given.encode("utf-8"), self._token.encode("utf-8")):
            return web.json_response({"decision": "deny", "reason": "unauthorized"}, status=401)
        try:
            body = await request.json()
            level, tool = body["level"], body["tool"]
            summary, details = body.get("summary", ""), body.get("details") or {}
            if level not in LEVELS or not isinstance(tool, str) or not isinstance(details, dict):
                raise ValueError
            summary = str(summary)
            task_id = body.get("task_id") if isinstance(body.get("task_id"), str) else None
        except Exception:
            return web.json_response({"decision": "deny", "reason": "bad_request"}, status=400)

        if task_id in self._cancelled_tasks:
            return web.json_response({"decision": "deny", "reason": "stopped"})
        rid = uuid.uuid4().hex[:12]
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._records[rid] = {"request_id": rid, "task_id": task_id, "level": level,
                              "tool": tool, "summary": summary, "details": redact_obj(details), "created_at": _now()}
        journal = self.root / "state" / "approvals.jsonl"
        _append_jsonl(journal, {"ts": _now(), "type": "request", "request_id": rid, "level": level,
                                "tool": tool, "summary": _truncate(summary), "details": _truncate(details),
                                "task_id": task_id})
        emit_event(self.root, "approval_request", status="waiting_approval", request_id=rid,
                   level=level, tool=tool, summary=summary, task_id=task_id)
        decision, reason = "deny", "client_gone"
        try:
            await self._notify(rid, level, tool, summary, details)
            try:
                decision, reason = await asyncio.wait_for(asyncio.shield(fut), self.timeout)
            except asyncio.TimeoutError:
                decision, reason = "deny", "timeout"
            return web.json_response({"decision": decision, "reason": reason})
        finally:
            # и при таймауте, и при обрыве соединения Guard'ом запрос больше не ждёт решения
            if not fut.done():
                fut.cancel()
            self._pending.pop(rid, None)
            self._records.pop(rid, None)
            _append_jsonl(journal, {"ts": _now(), "type": "decision", "request_id": rid,
                                    "decision": decision, "reason": reason, "tool": tool,
                                    "task_id": task_id})
            emit_event(self.root, "approval_decision", request_id=rid, tool=tool,
                       decision=decision, reason=reason, task_id=task_id)

    async def _notify(self, rid, level, tool, summary, details) -> None:
        # асинхронный подписчик запускается задачей: его ожидание не сдвигает таймаут решения
        for cb in list(self._callbacks):
            try:
                res = cb(rid, level, tool, summary, details)
                if inspect.isawaitable(res):
                    task = asyncio.ensure_future(res)
                    self._tasks.add(task)
                    task.add_done_callback(self._callback_done)
            except Exception:
                log.exception("ошибка подписчика on_request")

    def _callback_done(self, task: asyncio.Future) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("ошибка подписчика on_request: %r", task.exception())
