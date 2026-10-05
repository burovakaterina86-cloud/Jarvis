"""Журнал событий JARVIS: одна JSON-строка на событие в state/events.jsonl.

Обязательные поля: ts, type, session, agent, task, status, progress; у событий хода — task_id.
Словарь type: user_message, assistant_message, tool_use, tool_result,
approval_request, approval_decision, blocked, result, error, task_done.
Строковые поля проходят `runtime.redact` — значения токенов и ключей в журнал не попадают.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime.redact import redact_obj

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "state" / "events.jsonl"
MAX_BYTES = 10 * 1024 * 1024  # ротация: events.jsonl -> events.1.jsonl

TYPES = {"user_message", "assistant_message", "tool_use", "tool_result", "approval_request",
         "approval_decision", "blocked", "result", "error", "task_done"}

_lock = threading.Lock()


def emit(type: str, **fields) -> dict:
    """Дописывает событие в журнал и возвращает записанный словарь. Не бросает исключений."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "type": type,
        "session": None,
        "agent": "jarvis",
        "task": "",
        "status": "working",
        "progress": None,
    }
    record.update(redact_obj(fields))
    record["type"] = type
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    path = Path(EVENTS_PATH)
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(path.with_name(path.stem + ".1" + path.suffix))
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        pass
    return record
