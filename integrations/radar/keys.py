"""Ключи — только именами: `APIFY_TOKEN`, `GROQ_KEY`. Значения не читаем в лог и не печатаем."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Подхватить `.env` в окружение, не перекрывая заданное снаружи.

    Та же семантика, что у бота (`integrations.telegram.gateway.load_env`): владелица
    вписывает ключи в `.env`, а радар должен их видеть и из Telegram, и из терминала.
    Значения никуда не печатаются.
    """
    path = path or ROOT / ".env"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


class KeysError(Exception):
    """Нет нужного ключа в окружении."""


def require_keys(env: dict[str, str] | None = None) -> tuple[str, str]:
    """Вернуть (apify_token, groq_key) или бросить `KeysError` с именами недостающих."""
    if env is None:
        load_dotenv()
        env = os.environ
    apify = env.get("APIFY_TOKEN")
    groq = env.get("GROQ_KEY") or env.get("GROQ_API_KEY")
    missing = [name for name, val in (("APIFY_TOKEN", apify), ("GROQ_KEY", groq)) if not val]
    if missing:
        raise KeysError("нет ключей в окружении: " + ", ".join(missing))
    return apify, groq
