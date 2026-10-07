"""Настройки конвейера монтажа: числа, измеренные на её записи, и поиск внешних инструментов.

Каждое число здесь — результат замера (`docs/errors.md`), а не вкус. Менять — только с новым замером.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VENDOR = HERE / "vendor" / "montage_pipeline"
ASSETS = HERE / "assets"
TEMPLATES = HERE / "templates"
DATA = HERE / "data"
OUTBOX = ROOT / "outbox"
LOGO_CACHE = OUTBOX / "montage" / "logos"   # сюда JARVIS скачивает логотипы (integrations/ ему закрыта)

# --- первый заход (рез) ---
# Её запись громкая (p75 огибающей около −22 дБ): каноничный порог упирается в −30 дБ и режет хвосты слов
# (19 из 30 резов на слышимом хвосте). На −42 дБ — 0 из 24; шум комнаты около −52 дБ.
FLOOR_DB = -42.0
SPEED = 1.3          # ускорение — последним шагом, после проверки речи
FPS = 30

# --- очистка шума (её выбор: мягкий вариант №2, 2026-10-06) ---
DENOISE_FILTER = "afftdn=nr=10:nf=-40"   # шум −7 дБ; сильный anlmdn потерял слово и звучит «под водой»
DENOISE_AUTO_BELOW_DB = 25.0             # режим auto: чистим, если голос над фоном меньше (у «10 систем» 28,7 — не нужно, у «монтаж» 17,8 — нужно)
DENOISE_MIN_SIMILARITY = 0.97            # проверка речи до/после очистки
DENOISE_MAX_LOST_WORDS = 1
DENOISE_MAX_CHANGED_WORDS = 2             # слова, распознанные иначе (число ↔ слово, «я»): не потеря речи

# --- субтитры ---
SUB_MAX_CHARS = 24   # длиннее — строка ломается на две, нижняя падает на макушку
SUB_Y = 1730         # нижний край строки от верха кадра: ниже плеч (~1640), выше нижней панели Instagram (1760)
SUB_HIGHLIGHT = "&H004DD3FF"
SUB_FONT = "Golos Text"
SUB_PRESET = "quiet"
SUB_OUTLINE = r"\bord7\3c&H000000&\3a&H00&"   # плотная чёрная обводка: читается и на оранжевом, и на белой футболке

# --- безопасные зоны Reels (кадр 1080×1920) ---
SAFE_TOP = 115          # шапка Instagram
SAFE_BOTTOM_UI = 1760   # нижняя панель, закрыта всегда
SAFE_CAPTION = 1248     # ниже может перекрыть подпись к посту
SAFE_SIDE = 64
RIGHT_BUTTONS_X = 930   # колонка кнопок справа (y от ~1000 до 1760)

# --- раскладка ---
PANEL_H = 790           # верхняя панель сплита
SPLIT_SHIFT = 560       # на сколько спикер сдвинут вниз в сплите
BAND_SHIFT = 230        # то же в «полосе» с плашкой над головой

# --- громкость: цепочка и цель ---
# Голос над фоном у неё ~29 дБ (у автора эталона 40+), поэтому мягкий компрессор 2:1. Тяжёлая цепочка (3:1) ухудшает запас.
LOUD_CHAIN = ("highpass=f=100,"
              "acompressor=threshold=0.1:ratio=2:attack=5:release=150:makeup=1,"
              "alimiter=limit=0.35:attack=3:release=60:level=disabled")
LOUD_I, LOUD_TP = -14.0, -1.0

# --- палитра оформления (её выбор 2026-10-06: оранжевый фон, карточки как в варианте B) ---
PALETTE = {"bg": "#D97757", "ink": "#0E0D0C", "cream": "#F3EDE6"}


def _load_env() -> None:
    """Подхватить файл окружения проекта, как делают бот и радар (значения никуда не печатаются)."""
    try:
        from integrations.radar.keys import load_dotenv
        load_dotenv(only=("GROQ_API_KEY", "GROQ_KEY"))
    except Exception:
        pass


def groq_key() -> str | None:
    """Ключ Groq: `GROQ_API_KEY` или `GROQ_KEY` (так он назван в окружении бота). Только из окружения."""
    _load_env()
    return os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_KEY") or None


def child_env(extra: dict | None = None) -> dict:
    """Окружение для дочерних скриптов (ffmpeg, vendor): без секретов, кроме ключа Groq — вендорные
    roughcut/captions ждут именно GROQ_API_KEY."""
    from runtime import secretenv
    key = groq_key()
    env = secretenv.scrub()
    if key:
        env["GROQ_API_KEY"] = key
    env.update(extra or {})
    return env


def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None


def find_browser() -> str:
    """Chromium-совместимый браузер для покадрового рендера (Edge на Windows, Chrome — запасной)."""
    env = os.environ.get("MONTAGE_BROWSER")
    cands = [env,
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             shutil.which("msedge"), shutil.which("google-chrome"), shutil.which("chromium")]
    found = _first_existing(cands)
    if not found:
        raise FileNotFoundError("не найден браузер (Edge/Chrome); путь можно задать в MONTAGE_BROWSER")
    return found


def find_puppeteer() -> str:
    """Папка puppeteer-core: ставится вместе с `npm i -g hyperframes` (или путь в MONTAGE_PUPPETEER)."""
    env = os.environ.get("MONTAGE_PUPPETEER")
    cands = [env]
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30, shell=os.name == "nt").stdout.strip()
        if root:
            cands += [Path(root) / "hyperframes" / "node_modules" / "puppeteer-core", Path(root) / "puppeteer-core"]
    except Exception:
        pass
    found = _first_existing(cands)
    if not found:
        raise FileNotFoundError("не найден puppeteer-core: поставь `npm i -g hyperframes` или задай MONTAGE_PUPPETEER")
    return found


def require_tools() -> list[str]:
    """Чего не хватает на машине (пустой список — всё есть). Не бросает исключений."""
    missing = []
    for t in ("ffmpeg", "ffprobe", "curl", "node"):
        if not shutil.which(t):
            missing.append(t)
    if not groq_key():
        missing.append("GROQ_API_KEY (или GROQ_KEY) в окружении")
    try:
        find_browser()
    except FileNotFoundError:
        missing.append("браузер Edge/Chrome")
    try:
        find_puppeteer()
    except FileNotFoundError:
        missing.append("puppeteer-core (npm i -g hyperframes)")
    return missing
