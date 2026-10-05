"""Спецификация до исполнения (аудит 2026-10-05, P2.1).

Крупную неоднозначную задачу JARVIS начинает с плана из четырёх блоков (правило — в
`runtime/jarvis-turn.md`): «Сделаю / Готово, когда / Не делаю / Вопросы» — и ждёт её ответа.
План и работа — разные ходы, поэтому бот сам узнаёт план в ответе, хранит его для чата
(`state/specs/<chat>.json`) и прикрепляет к следующему ходу, где работа выполняется;
после него план уходит в `state/specs/done/<task_id плана>.json`. По плану проверяет ревьюер (P2.2).

Публично: `is_spec(text)`, `save(chat, task_id, text)`, `load(chat)`, `close(chat, executed_by)`.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = ROOT / "state" / "specs"
MAX_AGE_SEC = 24 * 3600   # старше суток план считается забытым
TEXT_LIMIT = 8000

# Блоки плана — заголовки в начале строки (допустимы маркеры, эмодзи, **жирный**).
_HEADINGS = ("сделаю", r"готово,?\s+когда", "не делаю")


def _heading(name: str) -> re.Pattern:
    return re.compile(r"(?mi)^[^\w\n]*" + name + r"[*_\s]*:")


_BLOCKS = [_heading(h) for h in _HEADINGS]


def is_spec(text) -> bool:
    """Ответ — план задачи: есть блоки «Сделаю», «Готово, когда» и «Не делаю» отдельными заголовками."""
    return isinstance(text, str) and all(b.search(text) for b in _BLOCKS)


def _path(chat) -> Path:
    return Path(SPECS_DIR) / f"{chat}.json"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def save(chat, task_id: str, text: str, now: float | None = None) -> None:
    """Новый план чата заменяет прежний (поправки владелицы → исправленный план)."""
    _write(_path(chat), {"task_id": task_id, "text": (text or "").strip()[:TEXT_LIMIT],
                         "created": time.time() if now is None else now})


def load(chat, now: float | None = None) -> dict | None:
    try:
        data = json.loads(_path(chat).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("text"):
        return None
    age = (time.time() if now is None else now) - float(data.get("created") or 0)
    return data if age <= MAX_AGE_SEC else None


def close(chat, executed_by: str) -> None:
    """План исполнен (или разговор ушёл дальше): в архив с номером хода-исполнителя."""
    data = load(chat)
    path = _path(chat)
    if data is None:
        path.unlink(missing_ok=True)
        return
    data["executed_by"] = executed_by
    _write(Path(SPECS_DIR) / "done" / f"{data['task_id']}.json", data)
    path.unlink(missing_ok=True)
