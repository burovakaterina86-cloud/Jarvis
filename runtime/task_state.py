"""Состояния задачи и ответ на /status — по журналу `state/events.jsonl` (аудит 2026-10-05, P2.4).

    queued → running → (waiting_approval → running) → (review → running → review) →
    done | failed | timeout | stopped

Переходы пишет `task_router` событием `task_state` (с `chat`); «ждёт подтверждения» берётся из
`approval_request` / `approval_decision` Approvals API — в них есть `task_id`. Отдельной базы нет:
`snapshot` читает хвост журнала.

Публично: `emit(...)`, `snapshot(path, chat)`, `describe(snapshot)`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from runtime import events

STATES = ("queued", "running", "waiting_approval", "review", "done", "failed", "timeout", "stopped")
TERMINAL = {"done", "failed", "timeout", "stopped"}
TAIL_BYTES = 512 * 1024

LABELS = {"queued": "в очереди", "running": "работаю", "waiting_approval": "ждёт твоего подтверждения",
          "review": "на независимой проверке", "done": "готово", "failed": "ошибка",
          "timeout": "остановлено по времени", "stopped": "остановлено"}
VERDICTS = {"pass": "проверка пройдена", "fix": "остались замечания проверки", "fail": "проверка: сделано не то"}


def final_state(result_status: str) -> str:
    return {"ok": "done", "timeout": "timeout", "stopped": "stopped"}.get(result_status, "failed")


def emit(task_id: str, task: str, state: str, chat=None, **extra) -> None:
    if state not in STATES:
        raise ValueError(f"неизвестное состояние задачи: {state!r}")
    events.emit("task_state", task_id=task_id, task=task, state=state, status=state,
                chat=None if chat is None else str(chat), **extra)


def _tail_lines(path: Path) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[1:] if size > TAIL_BYTES else lines   # первая строка хвоста может быть обрезана


def snapshot(path, chat=None) -> dict:
    """{"active": задача в работе | None, "queued": [...], "last": последняя завершённая | None}."""
    tasks: dict[str, dict] = {}
    for line in _tail_lines(Path(path)):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        tid = row.get("task_id") if isinstance(row, dict) else None
        if not tid:
            continue
        kind, ts = row.get("type"), row.get("ts", "")
        if kind == "task_state" and row.get("state") in STATES:
            task = tasks.setdefault(tid, {"task_id": tid})
            task.update(task=row.get("task", task.get("task", "")), state=row["state"], since=ts,
                        chat=row.get("chat", task.get("chat")))
        elif tid in tasks and kind == "approval_request" and tasks[tid].get("state") not in TERMINAL:
            tasks[tid].update(state="waiting_approval", since=ts)
        elif tid in tasks and kind == "approval_decision" and tasks[tid].get("state") == "waiting_approval":
            tasks[tid].update(state="running", since=ts)
        elif tid in tasks and kind == "task_done":
            tasks[tid]["review_verdict"] = row.get("review_verdict")
    mine = [t for t in tasks.values() if chat is None or t.get("chat") == str(chat)]
    working = [t for t in mine if t.get("state") in ("running", "waiting_approval", "review")]
    finished = [t for t in mine if t.get("state") in TERMINAL]
    return {"active": max(working, key=lambda t: t.get("since", "")) if working else None,
            "queued": [t for t in mine if t.get("state") == "queued"],
            "last": max(finished, key=lambda t: t.get("since", "")) if finished else None}


def _when(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _ago(since: str, now: str | None) -> str:
    start = _when(since)
    end = _when(now) if now else datetime.now(timezone.utc)
    if not start or not end:
        return ""
    sec = max(0, int((end - start).total_seconds()))
    if sec < 60:
        return f"{sec} с"
    if sec < 3600:
        return f"{sec // 60} мин"
    return f"{sec // 3600} ч {sec % 3600 // 60} мин"


def describe(snap: dict, now: str | None = None) -> str:
    """Текст /status для владелицы."""
    lines = []
    active = snap.get("active")
    if active:
        ago = _ago(active.get("since", ""), now)
        lines.append(f"▶️ Сейчас: «{active.get('task') or 'задача'}» — {LABELS[active['state']]}"
                     + (f" ({ago})" if ago else ""))
    queued = snap.get("queued") or []
    if queued:
        names = ", ".join(f"«{q.get('task') or 'задача'}»" for q in queued[:3])
        lines.append(f"⏳ В очереди: {len(queued)} — {names}")
    if not lines:
        lines.append("Сейчас ничего не выполняю.")
    last = snap.get("last")
    if last:
        when = _when(last.get("since", ""))
        at = f" в {when.astimezone():%H:%M}" if when else ""
        verdict = VERDICTS.get(last.get("review_verdict") or "")
        lines.append(f"Последняя: «{last.get('task') or 'задача'}» — {LABELS[last['state']]}{at}"
                     + (f", {verdict}" if verdict else ""))
    return "\n".join(lines) if (active or queued or last) else "Сейчас ничего не выполняю."
