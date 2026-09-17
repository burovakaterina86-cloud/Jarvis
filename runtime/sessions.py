"""Сессии Claude Code по чатам: state/sessions.json = {"<chat_id>": "<session_id>"}.

Запись атомарная: временный файл + os.replace.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_PATH = ROOT / "state" / "sessions.json"

_lock = threading.Lock()


def _load() -> dict:
    try:
        data = json.loads(Path(SESSIONS_PATH).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    path = Path(SESSIONS_PATH)
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
