"""CLI: python -m integrations.site_builder <init|check|pack> <имя>

init   создаёт outbox/sites/<имя>/ с assets/ и движком в scroll-engine/ (ничего не перезаписывает)
check  статическая проверка index.html: viewport, lang, alt у картинок, локальные ссылки, внешние
       скрипты, абсолютные пути компьютера, prefers-reduced-motion, размер
pack   архив outbox/sites/<имя>.zip без ключей, журналов и служебных файлов; предупреждает про 45 МБ

Коды выхода: 0 — готово, 2 — ошибка в имени или найдены проблемы, 3 — архив слишком большой для Telegram.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "outbox" / "sites"
ENGINE = ROOT / ".claude" / "skills" / "site-builder" / "vendor" / "scroll-engine"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$")
TELEGRAM_LIMIT = 45 * 1024 * 1024
SKIP_PARTS = {".DS_Store", "__pycache__", "node_modules", ".git"}
SKIP_SUFFIXES = {".log", ".pyc"}
ALLOWED_EXTERNAL = ("fonts.googleapis.com", "fonts.gstatic.com")
LINK_RE = re.compile(r"""(?:src|href|poster)\s*=\s*["']([^"'#?]+)""", re.I)


def site_dir(name: str) -> Path:
    if not NAME_RE.match(name):
        raise ValueError("имя сайта — латиница, цифры, дефис и подчёркивание, 2–40 знаков")
    return SITES / name


def cmd_init(name: str) -> int:
    folder = site_dir(name)
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    target = folder / "scroll-engine"
    target.mkdir(exist_ok=True)
    for f in sorted(ENGINE.glob("site-builder.*")):
        dst = target / f.name
        if not dst.exists():
            shutil.copy(f, dst)
    print(f"готово: {folder.relative_to(ROOT).as_posix()}/ (assets/, scroll-engine/site-builder.js, site-builder.css); "
          "дальше напиши index.html")
    return 0


def _files(folder: Path):
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not (SKIP_PARTS & set(p.parts)) and p.suffix not in SKIP_SUFFIXES and not p.name.startswith(".env"):
            yield p


def check_site(folder: Path) -> list[str]:
    problems = []
    index = folder / "index.html"
    if not index.is_file():
        return ["нет index.html"]
    html = index.read_text(encoding="utf-8", errors="replace")
    if not re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I):
        problems.append("нет <meta name=\"viewport\"> — на телефоне сайт развалится")
    if not re.search(r"<html[^>]+lang=", html, re.I):
        problems.append("у <html> нет lang")
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        if not re.search(r"\balt\s*=", tag, re.I):
            problems.append("картинка без alt: " + tag[:60])
    if re.search(r"[A-Za-z]:\\|file:///", html):
        problems.append("в index.html путь с твоего компьютера (C:\\ или file:///): на другом месте не откроется")
    texts = html
    for f in folder.rglob("*.css"):
        texts += f.read_text(encoding="utf-8", errors="replace")
    if "prefers-reduced-motion" not in texts and "reduced-motion" not in texts:
        problems.append("нет обработки prefers-reduced-motion (спокойный режим для тех, кому плохо от движения)")
    for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, re.I):
        host = re.sub(r"^(?:https?:)?//", "", src).split("/")[0].lower()
        if src.startswith(("http://", "https://", "//")) and host not in ALLOWED_EXTERNAL:
            problems.append(f"внешний скрипт {src}: сайт зависит от чужого сервера")
    for link in LINK_RE.findall(html):
        if link.startswith(("data:", "mailto:", "tel:", "javascript:", "http://", "https://", "//")):
            continue
        if not (folder / link.lstrip("/")).exists():
            problems.append(f"файла нет: {link}")
    size = sum(p.stat().st_size for p in _files(folder))
    if size > TELEGRAM_LIMIT:
        problems.append(f"сайт весит {size / 1048576:.0f} МБ — в Telegram архивом не отправить (лимит ~45 МБ)")
    return problems


def cmd_check(name: str) -> int:
    problems = check_site(site_dir(name))
    for item in problems:
        print("✗", item)
    print("проблем нет" if not problems else f"проблем: {len(problems)}")
    return 0 if not problems else 2


def cmd_pack(name: str) -> int:
    folder = site_dir(name)
    if not (folder / "index.html").is_file():
        print("нечего упаковывать: нет index.html", file=sys.stderr)
        return 2
    out = folder.with_suffix(".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in _files(folder):
            zf.write(f, f.relative_to(folder).as_posix())
    size = out.stat().st_size
    print(f"{out.relative_to(ROOT).as_posix()}: {size / 1048576:.1f} МБ")
    if size > TELEGRAM_LIMIT:
        print("архив больше ~45 МБ: Telegram его не примет; предложи отдать без тяжёлых видео", file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="integrations.site_builder")
    parser.add_argument("command", choices=["init", "check", "pack"])
    parser.add_argument("name")
    args = parser.parse_args(argv)
    try:
        return {"init": cmd_init, "check": cmd_check, "pack": cmd_pack}[args.command](args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
