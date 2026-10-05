"""Сессии Claude Code по чатам: state/sessions.json = {"<chat_id>": "<session_id>"}.

Запись атомарная: временный файл + os.replace.
Когда владелица писала в чат последний раз — `state/session_activity.json` = {"<chat_id>": epoch}
(по нему мост решает, начать ли свежую сессию после паузы, P3.1).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_PATH = ROOT / "state" / "sessions.json"
ACTIVITY_PATH = None   # None — рядом с SESSIONS_PATH (тест, подменивший его, изолирует и активность)

_lock = threading.Lock()


def _load(path=None) -> dict:
    try:
        data = json.loads(Path(path or SESSIONS_PATH).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict, path=None) -> None:
    path = Path(path or SESSIONS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get(chat_id) -> str | None:
    with _lock:
        return _load().get(str(chat_id))


def set(chat_id, sid: str) -> None:  # noqa: A001 — имя из контракта
    with _lock:
        data = _load()
        data[str(chat_id)] = sid
        _save(data)


def reset(chat_id) -> None:
    with _lock:
        data = _load()
        if data.pop(str(chat_id), None) is not None:
            _save(data)


def _activity_path() -> Path:
    return Path(ACTIVITY_PATH) if ACTIVITY_PATH else Path(SESSIONS_PATH).with_name("session_activity.json")


def last_active(chat_id) -> float | None:
    """Когда в чате был последний ход владелицы (epoch); None — не записано."""
    with _lock:
        value = _load(_activity_path()).get(str(chat_id))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def touch(chat_id, now: float) -> None:
    with _lock:
        path = _activity_path()
        data = _load(path)
        data[str(chat_id)] = now
        _save(data, path)
