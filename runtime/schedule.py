"""Задачи по расписанию внутри бота — её решение 2026-09-25 («бери все три»).

Бот и так раз в 10 секунд опрашивает черновики и почтовый ящик; тем же циклом он проверяет
`runtime/schedule.json`. Задача «пора», если её последний прошедший слот ещё не выполнялся:
пропущенное из-за выключенного компьютера **догоняется** при первом же опросе после включения
(идея «проверка вместо сна до HH:MM» — из учебного jarvis-kit, `core/schedule.py`).
Ежедневной задаче можно ограничить догон (`catch_up_hours`): «доброе утро» в 15:00 не нужно.

Время — местное время компьютера. Когда что запускалось — `state/schedule.json`.
Задача — обычный ход Claude от имени владелицы: промпт из файла, ответ бот присылает ей в Telegram.

Формат задачи в `runtime/schedule.json`:
`{"id", "kind": "daily"|"weekly", "at": "HH:MM", "weekday": 0-6 (пн=0, для weekly),
  "catch_up_hours": N (необязательно), "timeout_min": N (необязательно; иначе
  JARVIS_TASK_TIMEOUT_SEC), "prompt": "путь к .md от корня"}`.
Задача идёт в изолированном контексте: без истории её чата и не меняя его сессию.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("runtime") / "schedule.json"
STATE = Path("state") / "schedule.json"


def _hhmm(value: str) -> dt.time:
    h, m = value.strip().split(":")
    return dt.time(int(h), int(m))


def last_slot(task: dict, now: dt.datetime) -> dt.datetime:
    """Последний момент по расписанию, который уже наступил (≤ now)."""
    t = _hhmm(task["at"])
    slot = dt.datetime.combine(now.date(), t)
    if task["kind"] == "daily":
        return slot if slot <= now else slot - dt.timedelta(days=1)
    if task["kind"] == "weekly":
        back = (now.weekday() - int(task["weekday"])) % 7
        slot -= dt.timedelta(days=back)
        return slot if slot <= now else slot - dt.timedelta(days=7)
    raise ValueError(f"неизвестный вид расписания: {task['kind']!r}")


def is_due(task: dict, now: dt.datetime, last_run: str | None) -> bool:
    slot = last_slot(task, now)
    if last_run:
        try:
            if dt.datetime.fromisoformat(last_run) >= slot:
                return False
        except ValueError:
            pass
    window = task.get("catch_up_hours")
    if window is not None and now - slot > dt.timedelta(hours=float(window)):
        return False
    return True


def load_tasks(root: Path | str = ROOT) -> list[dict]:
    path = Path(root) / CONFIG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [t for t in data if isinstance(t, dict) and t.get("enabled", True)]


def prompt_for(task: dict, root: Path | str = ROOT) -> str:
    try:
        return (Path(root) / task["prompt"]).read_text(encoding="utf-8")
    except (OSError, KeyError):
        return ""


def load_state(root: Path | str = ROOT) -> dict:
    try:
        data = json.loads((Path(root) / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict, root: Path | str = ROOT) -> None:
    path = Path(root) / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def due_tasks(now: dt.datetime, root: Path | str = ROOT) -> list[tuple[dict, dt.datetime]]:
    """Что пора запустить сейчас: (задача, её слот)."""
    state = load_state(root)
    return [(t, last_slot(t, now)) for t in load_tasks(root) if is_due(t, now, state.get(t["id"]))]
