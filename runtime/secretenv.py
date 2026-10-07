"""Секреты и окружение дочерних процессов.

Бот держит в своём окружении всё из `.env` (токен Telegram, ключи Apify, Groq, kie.ai…). Дочерним процессам
(Claude, Codex, node/Edge, ffmpeg, фоновые работы) это не нужно: ключи сервисов модули JARVIS берут из `.env`
сами и только свои (`lookup`). Раньше дочерний процесс наследовал ВСЕ ключи — любой запущенный им код мог их
прочитать и отправить. Теперь `scrub` убирает из окружения всё, что похоже на секрет.

    scrub(env)        — копия окружения без секретов (по имени переменной)
    lookup(*names)    — значение ключа из окружения или `.env`; ничего не кладёт в `os.environ`
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROP_PREFIX = ("CLAUDE", "ANTHROPIC", "TELEGRAM")
KEEP = {"CLAUDE_CODE_GIT_BASH_PATH"}      # нужен claude на Windows; это путь, а не секрет
_SECRET = re.compile(r"TOKEN|SECRET|PASSW|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE|CREDENTIAL|AUTH|(?:^|_)KEY$", re.IGNORECASE)


def is_secret_name(name: str) -> bool:
    upper = name.upper()
    if upper in KEEP:
        return False
    return upper.startswith(DROP_PREFIX) or bool(_SECRET.search(name))


def scrub(env=None) -> dict:
    """Копия окружения (по умолчанию `os.environ`) без переменных, похожих на секреты."""
    src = dict(os.environ if env is None else env)
    return {k: v for k, v in src.items() if not is_secret_name(k)}


def _from_dotenv(name_set: set[str], path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        if key in name_set:
            found.setdefault(key, value.strip().strip('"').strip("'"))
    return found


def lookup(*names: str, environ=None, dotenv: Path | None = None) -> str | None:
    """Первое непустое значение из `names`: сначала окружение, потом `.env`. В `os.environ` не пишет."""
    environ = os.environ if environ is None else environ
    for name in names:
        if environ.get(name):
            return environ[name]
    from_file = _from_dotenv(set(names), dotenv or ROOT / ".env")
    for name in names:
        if from_file.get(name):
            return from_file[name]
    return None
