"""Ключи — только именами: `APIFY_TOKEN`, `GROQ_KEY`. Значения не читаем в лог и не печатаем."""
from __future__ import annotations

import os


class KeysError(Exception):
    """Нет нужного ключа в окружении."""


def require_keys(env: dict[str, str] | None = None) -> tuple[str, str]:
    """Вернуть (apify_token, groq_key) или бросить `KeysError` с именами недостающих."""
    env = os.environ if env is None else env
    apify = env.get("APIFY_TOKEN")
    groq = env.get("GROQ_KEY") or env.get("GROQ_API_KEY")
    missing = [name for name, val in (("APIFY_TOKEN", apify), ("GROQ_KEY", groq)) if not val]
    if missing:
        raise KeysError("нет ключей в окружении: " + ", ".join(missing))
    return apify, groq
