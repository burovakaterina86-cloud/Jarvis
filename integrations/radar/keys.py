"""Ключи — только именами: `APIFY_TOKEN`, `GROQ_KEY`. Значения не читаем в лог и не печатаем."""
from __future__ import annotations

import os
from pathlib import Path

from runtime import secretenv

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None, *, only) -> None:
    """Подхватить из `.env` в окружение ТОЛЬКО ключи `only`, не перекрывая заданное снаружи.

    Владелица вписывает ключи в `.env`, а модуль должен их видеть и из Telegram, и из терминала. Раньше сюда
    загружалось всё содержимое файла (токен Telegram и чужие ключи тоже) и через окружение уходило в
    дочерние процессы: node, Edge, ffmpeg, Codex. Значения никуда не печатаются.
    """
    names = set(only)
    path = Path(path) if path else ROOT / ".env"
    for key, value in secretenv._from_dotenv(names, path).items():
        os.environ.setdefault(key, value)


class KeysError(Exception):
    """Нет нужного ключа в окружении."""


def require_keys(env: dict[str, str] | None = None) -> tuple[str, str]:
    """Вернуть (apify_token, groq_key) или бросить `KeysError` с именами недостающих."""
    if env is None:
        load_dotenv(only=("APIFY_TOKEN", "GROQ_KEY", "GROQ_API_KEY"))
        env = os.environ
    apify = env.get("APIFY_TOKEN")
    groq = env.get("GROQ_KEY") or env.get("GROQ_API_KEY")
    missing = [name for name, val in (("APIFY_TOKEN", apify), ("GROQ_KEY", groq)) if not val]
    if missing:
        raise KeysError("нет ключей в окружении: " + ", ".join(missing))
    return apify, groq
