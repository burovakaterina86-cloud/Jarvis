"""Очередь ходов: FIFO на чат, одна активная задача на чат, одна браузерная глобально,
дневной бюджет запусков (JARVIS_DAILY_RUN_BUDGET, по умолчанию 100).

Предел времени на задачу — `Job.timeout_sec` или JARVIS_TASK_TIMEOUT_SEC (по умолчанию 45 мин):
по истечении ход останавливается, статус `timeout`, очередь идёт дальше.
Контекст задачи — `Job.context`: `chat` продолжает сессию чата, `isolated` идёт без истории
и сессию чата не трогает (задачи по расписанию).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from runtime import claude_bridge, events
from runtime import sessions as sessions_mod

ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = ROOT / "state" / "run_budget.json"
DEFAULT_DAILY_BUDGET = 100
DEFAULT_TASK_TIMEOUT_SEC = 2700
CONTEXTS = ("chat", "isolated")


@dataclass
class Job:
    prompt: str
    uses_browser: bool = False
    task: str = ""
    on_event: object = None   # callable(event: dict), sync или async
    on_done: object = None    # callable(TurnResult), sync или async
    result: asyncio.Future | None = field(default=None, repr=False)  # ставит submit
    timeout_sec: float | None = None  # None — TaskRouter.default_timeout
    context: str = "chat"             # chat | isolated

    def __post_init__(self):
        if self.context not in CONTEXTS:
            raise ValueError(f"неизвестный контекст задачи: {self.context!r}")


def _budget_from_env() -> int:
    try:
        return max(0, int(os.environ.get("JARVIS_DAILY_RUN_BUDGET", DEFAULT_DAILY_BUDGET)))
    except ValueError:
        return DEFAULT_DAILY_BUDGET


def _timeout_from_env() -> float:
    try:
        value = float(os.environ.get("JARVIS_TASK_TIMEOUT_SEC", DEFAULT_TASK_TIMEOUT_SEC))
    except ValueError:
        return DEFAULT_TASK_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TASK_TIMEOUT_SEC


def _human_duration(sec: float) -> str:
    return f"{sec:g} с" if sec < 60 else f"{sec / 60:g} мин"


def run_id_for(chat_id) -> str:
    return f"chat-{chat_id}"


class TaskRouter:
    def __init__(self, *, budget: int | None = None, budget_path: str | Path | None = None,
                 env: dict | None = None, claude_cmd: list[str] | None = None, sessions=None):
        self.budget = budget
        self.budget_path = Path(budget_path) if budget_path else BUDGET_PATH
        self.env = env
        self.claude_cmd = claude_cmd
        self.sessions = sessions or sessions_mod
        self.default_timeout = _timeout_from_env()
        self._queues: dict[str, deque] = {}
        self._active: dict[str, Job] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._browser_lock = asyncio.Lock()

    def submit(self, chat_id, job: Job) -> int:
        """Ставит job в очередь чата. Возвращает число задач впереди (0 — начнёт сразу).
        Вызывать из работающего event loop; итог — в job.result и job.on_done."""
        key = str(chat_id)
        loop = asyncio.get_running_loop()
        if job.result is None:
            job.result = loop.create_future()
        q = self._queues.setdefault(key, deque())
        position = len(q) + (1 if key in self._active else 0)
        q.append(job)
        events.emit("user_message", task=job.task, status="queued",
                    chat=key, position=position, session=self.sessions.get(key))
        worker = self._workers.get(key)
        if worker is None or worker.done():
            self._workers[key] = loop.create_task(self._worker(key))
        return position

    def pending(self, chat_id) -> int:
        key = str(chat_id)
        return len(self._queues.get(key, ())) + (1 if key in self._active else 0)

    def stop(self, chat_id) -> bool:
        """Останавливает активную задачу чата (очередь не трогает)."""
        return claude_bridge.stop(run_id_for(chat_id))

    async def _worker(self, key: str) -> None:
        q = self._queues[key]
        while q:
            job = q.popleft()
            self._active[key] = job
            try:
                res = await self._run(key, job)
            except Exception as exc:  # noqa: BLE001
                res = claude_bridge.TurnResult("Внутренняя ошибка моста.", None, False, None,
                                               "error", repr(exc)[:500])
            finally:
                self._active.pop(key, None)
            if not job.result.done():
                job.result.set_result(res)
            await _call(job.on_done, res)

    async def _run(self, key: str, job: Job):
        if job.uses_browser:
            async with self._browser_lock:
                return await self._run_turn(key, job)
        return await self._run_turn(key, job)

    async def _run_turn(self, key: str, job: Job):
        if not self._take_budget():
            limit = self._limit()
            events.emit("error", subtype="daily_budget_exceeded", task=job.task, status="failed")
            return claude_bridge.TurnResult(
                f"Дневной лимит запусков ({limit}) исчерпан — продолжу завтра "
                "или владелица может поднять JARVIS_DAILY_RUN_BUDGET.",
                self.sessions.get(key), False, None, "error", "daily_budget_exceeded")
        isolated = job.context == "isolated"
        sid = None if isolated else self.sessions.get(key)
        limit = job.timeout_sec or self.default_timeout
        run_id = run_id_for(key)
        turn = asyncio.ensure_future(claude_bridge.run_turn(
            job.prompt, sid, job.on_event, run_id=run_id, task=job.task, env=self.env,
            claude_cmd=self.claude_cmd))
        done, _ = await asyncio.wait({turn}, timeout=limit)
        if not done:
            # Останавливаем тем же путём, что /stop: дерево процесса, ход возвращает «stopped».
            claude_bridge.stop(run_id)
            res = await turn
        else:
            res = turn.result()
        # Ход, успевший закончиться сам в момент таймаута, сохраняет свой итог.
        if not done and res.status == "stopped":
            events.emit("error", subtype="timeout", task=job.task, status="failed",
                        timeout_sec=limit, session=res.session_id or sid)
            res.status, res.error = "timeout", "timeout"
            res.text = (f"Остановил задачу: она шла дольше {_human_duration(limit)}. "
                        "Часть действий могла выполниться — скажи, продолжать ли и с чего.")
        if res.status in ("rate_limited", "auth_required", "error"):
            self._refund_budget()  # неуспешный ход не тратит дневной лимит; таймаут — тратит
        if not isolated and res.session_id and res.session_id != sid:
            self.sessions.set(key, res.session_id)
        return res

    def _refund_budget(self) -> None:
        today = date.today().isoformat()
        try:
            data = json.loads(self.budget_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.get("date") != today or data.get("count", 0) <= 0:
            return
        self._write_budget(today, data["count"] - 1)

    def _write_budget(self, today: str, count: int) -> None:
        self.budget_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.budget_path.with_name(self.budget_path.name + ".tmp")
        tmp.write_text(json.dumps({"date": today, "count": count}), encoding="utf-8")
        os.replace(tmp, self.budget_path)

    def _limit(self) -> int:
        return self.budget if self.budget is not None else _budget_from_env()

    def _take_budget(self) -> bool:
        today = date.today().isoformat()
        try:
            data = json.loads(self.budget_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        count = data.get("count", 0) if data.get("date") == today else 0
        if count >= self._limit():
            return False
        self._write_budget(today, count + 1)
        return True


async def _call(cb, arg):
    if cb is None:
        return
    try:
        r = cb(arg)
        if inspect.isawaitable(r):
            await r
    except Exception:  # noqa: BLE001
        pass


_default: TaskRouter | None = None


def default_router() -> TaskRouter:
    global _default
    if _default is None:
        _default = TaskRouter()
    return _default


def submit(chat_id, job: Job) -> int:
    return default_router().submit(chat_id, job)


def stop(chat_id) -> bool:
    return default_router().stop(chat_id)
