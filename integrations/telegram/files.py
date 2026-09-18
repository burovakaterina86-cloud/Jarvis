"""Файлы из Telegram: очистка имён, папка inbox/, статусы контент-комплектов.

Ничего не знает про Telegram API — только пути и содержимое на диске.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MAX_NAME = 100
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SPACES = re.compile(r"\s+")
# Зарезервированные имена устройств Windows: CON, PRN, AUX, NUL, COM1..9, LPT1..9
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}

CONTENT_DIR = Path("essa-ai") / "content"
PUBLISHED = CONTENT_DIR / "PUBLISHED.md"
_BUNDLE_RE = re.compile(r"essa-ai[/\\]content[/\\]([0-9A-Za-zА-Яа-яЁё._\-]+)")

DECISIONS = {
    "accepted": "Принято",
    "redo": "Переделать",
    "published": "Опубликовано",
}


def sanitize_name(name: str) -> str:
    """Безопасное имя файла: без путей, спецсимволов и имён устройств Windows."""
    name = (name or "").replace("\r", " ").replace("\n", " ")
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _BAD_CHARS.sub("_", name)
    name = _SPACES.sub("_", name).strip("._ ")
    if not name:
        return "file"
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED:
        name = "_" + name
    if len(name) > MAX_NAME:
        suffix = Path(name).suffix[:10]
        name = name[: MAX_NAME - len(suffix)] + suffix
    return name


def inbox_path(root: Path | str, name: str, when: dt.date | None = None) -> Path:
    """Путь inbox/YYYY-MM-DD/<очищенное имя> без перезаписи существующего файла."""
    day = (when or dt.date.today()).isoformat()
    folder = Path(root) / "inbox" / day
    clean = sanitize_name(name)
    candidate = folder / clean
    if not candidate.exists():
        return candidate
    stem, suffix = Path(clean).stem, Path(clean).suffix
    n = 1
    while (folder / f"{stem}-{n}{suffix}").exists():
        n += 1
    return folder / f"{stem}-{n}{suffix}"


def reserve_path(root: Path | str, name: str, when: dt.date | None = None,
                 attempts: int = 100) -> Path:
    """Занимает имя в inbox/ одной операцией (O_EXCL): два файла подряд не затрут друг друга."""
    day = (when or dt.date.today()).isoformat()
    folder = Path(root) / "inbox" / day
    folder.mkdir(parents=True, exist_ok=True)
    clean = sanitize_name(name)
    stem, suffix = Path(clean).stem, Path(clean).suffix
    for n in range(attempts):
        candidate = folder / (clean if n == 0 else f"{stem}-{n}{suffix}")
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise FileExistsError(f"не нашёл свободного имени для {clean} за {attempts} попыток")


def save_bytes(root: Path | str, name: str, data: bytes, when: dt.date | None = None) -> Path:
    path = reserve_path(root, name, when=when)
    path.write_bytes(data)
    return path


def find_content_bundle(text: str, root: Path | str = ROOT) -> str | None:
    """Имя папки комплекта, если ответ агента ссылается на существующий essa-ai/content/<папка>."""
    root = Path(root)
    for match in _BUNDLE_RE.finditer(text or ""):
        name = match.group(1)
        if name.upper().startswith("PUBLISHED"):
            continue
        if (root / CONTENT_DIR / name).is_dir():
            return name
    return None


def mark_content(root: Path | str, name: str, decision: str, when: dt.date | None = None,
                 note: str = "") -> str:
    """Пишет решение владелицы в <комплект>/status; «Опубликовано» — строку в PUBLISHED.md."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got {decision!r}")
    root = Path(root)
    bundle = root / CONTENT_DIR / sanitize_name(name)
    if not bundle.is_dir():
        raise FileNotFoundError(bundle)
    bundle.joinpath("status").write_text(decision + "\n", encoding="utf-8")
    if decision == "published":
        day = (when or dt.date.today()).isoformat()
        line = f"- {day} | {name} | {note or 'отмечено кнопкой в Telegram'}\n"
        published = root / PUBLISHED
        published.parent.mkdir(parents=True, exist_ok=True)
        with open(published, "a", encoding="utf-8") as fh:
            fh.write(line)
    return DECISIONS[decision]
