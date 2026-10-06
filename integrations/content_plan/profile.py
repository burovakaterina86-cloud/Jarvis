"""Паспорт агента: `essa-ai/content-plan/profile.json`.

Факты о ней и её нише в паспорт кладёт первый запуск (опрос + 10 рилсов). Пока в обязательных
полях стоит метка `[ЗАПОЛНИ: …]`, сбор отказывается и называет поля — ничего не выдумывает.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "essa-ai" / "content-plan"
PROFILE_PATH = DATA_DIR / "profile.json"
HISTORY_PATH = DATA_DIR / "history.json"
WEEKS_DIR = DATA_DIR / "weeks"

PLACEHOLDER_MARK = "[ЗАПОЛНИ"

DEFAULTS: dict[str, Any] = {
    "stop_words": [],
    "not_niche": [],
    "seed_authors": [],
    "memo23_queries": [],
    "memo23_cta_queries": [],
    "boolean_query_en": "",
    "comments_threshold": 1000,
    "comments_fallback": 600,
    "carousel_threshold": 1000,
    "carousel_fallback": 300,
    "window_days": 14,
    "reels_per_week": 3,
    "plan_reels": 9,
    "carousels_per_week": 2,
    "lead_magnets_per_week": 2,
    "podcast_per_week": 1,
    "reserve_topics": 10,
    "no_speech_reels": False,
    "market_langs": ["en"],
    "budget_usd": 6.0,
    "accent": "#FFD84D",
    "mode": "эконом",
}

#: Поля, без которых собирать план нельзя.
REQUIRED = ("niche", "audience", "tags", "memo23_queries", "boolean_query_en")


class ProfileError(Exception):
    """Паспорт не готов: нет файла, битый JSON или остались [ЗАПОЛНИ]."""


@dataclass
class Profile:
    data: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:  # profile.plan_reels
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(name) from None


def _is_empty(value: Any) -> bool:
    if isinstance(value, str):
        return not value.strip() or PLACEHOLDER_MARK in value
    if isinstance(value, dict):
        return all(_is_empty(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return not value or any(isinstance(v, str) and PLACEHOLDER_MARK in v for v in value)
    return value is None


def missing_fields(data: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED if _is_empty(data.get(key))]


def load_profile(path: str | Path = PROFILE_PATH, *, require: bool = True) -> Profile:
    path = Path(path)
    if not path.is_file():
        raise ProfileError(f"нет паспорта: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"паспорт не читается как JSON: {exc}") from exc
    if require:
        missing = missing_fields(raw)
        if missing:
            raise ProfileError("в паспорте не заполнено: " + ", ".join(missing))
    data = {**DEFAULTS, **raw}
    return Profile(data)
