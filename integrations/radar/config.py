"""Настройки рилс-радара: `essa-ai/radar/config.json`.

Ники — её факты. Пока она их не прислала, в конфиге стоят видимые метки
`[ЗАПОЛНИ: …]`, и прогон с ними отказывается, не начиная работу (`load_config`
бросает `ConfigError`, `__main__.main` превращает это в exit 2).

По её решению 2026-09-23: подписки эталонного аккаунта не сканируются, радар
идёт прямо по готовому списку конкурентов (`competitors`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "essa-ai" / "radar" / "config.json"

#: Подстрока метки незаполненного факта — используется и в essa-ai/, и здесь.
PLACEHOLDER_MARK = "[ЗАПОЛНИ"

#: Значения по умолчанию для необязательных полей конфига.
DEFAULTS = {
    "keywords": [],
    "window_days": 7,
    "own_window_days": 30,
    "own_fetch_limit": 30,
    "top_k": 25,
    "top_final": 15,
    "reels_per_account": 3,
    "max_requests_per_run": 200,
}

REQUIRED_FIELDS = ("own_username",)


class ConfigError(Exception):
    """Конфиг не готов к прогону: нет файла, битый JSON или остались [ЗАПОЛНИ]."""


@dataclass
class RadarConfig:
    own_username: str
    competitors: list[str]
    keywords: list[str]
    window_days: int
    own_window_days: int
    own_fetch_limit: int
    top_k: int
    top_final: int
    reels_per_account: int
    max_requests_per_run: int
    raw: dict[str, Any] = field(default_factory=dict)


def _placeholders(data: dict[str, Any]) -> list[str]:
    """Имена полей, которые всё ещё несут метку [ЗАПОЛНИ] — их и покажем в отказе."""
    found = []
    for key in REQUIRED_FIELDS:
        value = data.get(key)
        if not isinstance(value, str) or PLACEHOLDER_MARK in value or not value.strip():
            found.append(key)
    competitors = data.get("competitors") or []
    if not competitors:
        found.append("competitors")
    for i, comp in enumerate(competitors):
        if not isinstance(comp, str) or PLACEHOLDER_MARK in comp or not comp.strip():
            found.append(f"competitors[{i}]")
    return found


def load_config(path: str | Path) -> RadarConfig:
    """Прочитать и провалидировать конфиг. Метки [ЗАПОЛНИ] или битый JSON — `ConfigError`."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"нет файла настроек: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: битый JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: нужен объект JSON, а не {type(data).__name__}")

    missing = _placeholders(data)
    if missing:
        raise ConfigError(
            "в конфиге остались незаполненные факты (метки [ЗАПОЛНИ]): "
            + ", ".join(missing)
        )

    merged = {**DEFAULTS, **data}
    return RadarConfig(
        own_username=merged["own_username"],
        competitors=list(merged.get("competitors") or []),
        keywords=list(merged.get("keywords") or []),
        window_days=int(merged["window_days"]),
        own_window_days=int(merged["own_window_days"]),
        own_fetch_limit=int(merged["own_fetch_limit"]),
        top_k=int(merged["top_k"]),
        top_final=int(merged["top_final"]),
        reels_per_account=int(merged["reels_per_account"]),
        max_requests_per_run=int(merged["max_requests_per_run"]),
        raw=data,
    )
