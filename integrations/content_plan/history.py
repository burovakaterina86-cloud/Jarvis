"""История планов: `essa-ai/content-plan/history.json`. Повторы убираются по кодам и по темам."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .profile import HISTORY_PATH

EMPTY: dict[str, Any] = {"reel_codes": [], "carousel_codes": [], "code_words": [], "weeks": []}


def load_history(path: str | Path = HISTORY_PATH) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, json.JSONDecodeError) as exc:   # битый файл молча отключал проверку повторов
        from runtime import errorlog
        errorlog.record("content_plan.history", exc, file=path.name)
        data = {}
    return {**{k: list(v) for k, v in EMPTY.items()}, **data}


def seen_codes(history: dict[str, Any]) -> set[str]:
    return set(history.get("reel_codes", [])) | set(history.get("carousel_codes", []))


def append_week(history: dict[str, Any], *, week: str, reel_codes: list[str], carousel_codes: list[str],
                code_words: list[str], reel_topics: list[str], carousel_topics: list[str],
                lead_magnets: list[str] | None = None, podcast: str = "", stories: str = "") -> dict[str, Any]:
    """Дописать неделю. Повторный вызов с той же `week` заменяет запись, а не дублирует."""
    out = {**history}
    out["reel_codes"] = sorted(set(history.get("reel_codes", [])) | set(reel_codes))
    out["carousel_codes"] = sorted(set(history.get("carousel_codes", [])) | set(carousel_codes))
    out["code_words"] = sorted(set(history.get("code_words", [])) | set(code_words))
    weeks = [w for w in history.get("weeks", []) if w.get("week") != week]
    weeks.append({"week": week, "reel_topics": reel_topics, "carousel_topics": carousel_topics,
                  "lead_magnets": lead_magnets or [], "podcast": podcast, "stories": stories})
    out["weeks"] = weeks
    return out


def save_history(history: dict[str, Any], path: str | Path = HISTORY_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
