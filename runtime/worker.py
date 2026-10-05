"""Кто работает в чате — Claude или Codex — и известные лимиты подписок (аудит P4.1e/f).

Codex — запасной исполнитель: включается её кнопкой, когда у Claude кончился лимит, или командой /codex;
в момент сброса лимита Claude бот возвращается к нему сам (единственный автоматический шаг) и говорит
об этом. Всё хранится файлами, чтобы переживать перезапуск бота:

    state/runtime.json   {chat: {"runtime": "codex", "until": epoch|null, "since": epoch, "announce": bool}}
    state/limits.json    {"claude": {...}, "codex": {...}}  — последние известные лимиты
    state/offers/<chat>.json   — предложение «Продолжить в Codex / Подождать» до нажатия кнопки
    state/deferred.json  [{chat, at, prompt, task}] — «Подождать»: запустить в Claude в момент сброса
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
RUNTIMES = ("claude", "codex")


def _read(name: str, default):
    try:
        data = json.loads((Path(STATE_DIR) / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write(name: str, data) -> None:
    path = Path(STATE_DIR) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def session_key(chat, runtime: str) -> str:
    """Сессии Claude и Codex разные: у Codex свой ключ в sessions.json."""
    return str(chat) if runtime == "claude" else f"{chat}:{runtime}"


def switch(chat, runtime: str, until: float | None = None, now: float | None = None) -> None:
    if runtime not in RUNTIMES:
        raise ValueError(f"неизвестный исполнитель: {runtime!r}")
    data = _read("runtime.json", {})
    if runtime == "claude":
        data.pop(str(chat), None)
    else:
        data[str(chat)] = {"runtime": runtime, "until": until, "since": time.time() if now is None else now}
    _write("runtime.json", data)


def active(chat, now: float | None = None) -> tuple[str, bool]:
    """(исполнитель, только что вернулись к Claude — сказать владелице)."""
    now = time.time() if now is None else now
    data = _read("runtime.json", {})
    entry = data.get(str(chat))
    if not isinstance(entry, dict):
        return "claude", False
    if entry.get("announce"):
        data.pop(str(chat), None)
        _write("runtime.json", data)
        return "claude", True
    until = entry.get("until")
    if until is not None and now >= float(until):
        data[str(chat)] = {"runtime": "claude", "announce": True}
        _write("runtime.json", data)
        return active(chat, now)
    return entry.get("runtime", "claude"), False


def current(chat) -> dict:
    """Для /status: без побочных эффектов."""
    entry = _read("runtime.json", {}).get(str(chat))
    return entry if isinstance(entry, dict) and entry.get("runtime") == "codex" else {"runtime": "claude"}


# ---------- лимиты ----------

def save_limits(runtime: str, info: dict) -> None:
    data = _read("limits.json", {})
    data[runtime] = {**info, "ts": time.time()}
    _write("limits.json", data)


def limits() -> dict:
    return _read("limits.json", {})


def _hhmm(epoch) -> str:
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "?"


def describe_limits(data: dict | None = None, now: float | None = None) -> str:
    data = limits() if data is None else data
    now = time.time() if now is None else now
    lines = []
    claude = data.get("claude") or {}
    if claude:
        reset = claude.get("resets_at")
        if claude.get("status") == "rejected" and (reset is None or float(reset) > now):
            lines.append(f"Claude: лимит исчерпан до {_hhmm(reset)}" if reset else "Claude: лимит исчерпан")
        elif claude.get("status") == "allowed_warning":
            lines.append("Claude: лимит на исходе" + (f" (сброс в {_hhmm(reset)})" if reset else ""))
        else:
            lines.append("Claude: лимит в порядке")
    codex = data.get("codex") or {}
    parts = []
    for key, label in (("primary", "5 ч"), ("secondary", "неделя")):
        window = codex.get(key) or {}
        if "used_percent" in window:
            parts.append(f"{label} — {window['used_percent']:g}%" +
                         (f" (сброс в {_hhmm(window['resets_at'])})" if key == "primary" and window.get("resets_at") else ""))
    if parts:
        lines.append("Codex: " + ", ".join(parts) + " израсходовано")
    return "\n".join(lines)


# ---------- предложение переключиться и отложенные задачи ----------

def save_offer(chat, offer: dict) -> None:
    _write(f"offers/{chat}.json", offer)


def load_offer(chat) -> dict | None:
    data = _read(f"offers/{chat}.json", {})
    return data or None


def drop_offer(chat) -> None:
    (Path(STATE_DIR) / "offers" / f"{chat}.json").unlink(missing_ok=True)


def defer(chat, at: float, prompt: str, task: str) -> None:
    items = _read("deferred.json", [])
    items.append({"chat": str(chat), "at": float(at), "prompt": prompt, "task": task})
    _write("deferred.json", items)


def due_deferred(now: float | None = None) -> list[dict]:
    """Задачи, которым пора; забираются из очереди (второй раз не вернутся)."""
    now = time.time() if now is None else now
    items = _read("deferred.json", [])
    due = [d for d in items if float(d.get("at", 0)) <= now]
    if due:
        _write("deferred.json", [d for d in items if d not in due])
    return due
