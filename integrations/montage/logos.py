"""Настоящие SVG-логотипы: поиск и скачивание из двух открытых каталогов, которыми пользуется Даша.

Её решение 2026-10-06: JARVIS берёт логотипы сам. Поэтому — узкий и безопасный путь, а не «любой файл из интернета»:
- источники только два и только по HTTPS: `glincker/thesvg` (5000+ логотипов) и `gilbarbara/logos`
  (хосты `api.github.com`, `raw.githubusercontent.com`); любой другой адрес — отказ;
- имя — только `[a-z0-9-]`, путь строится кодом, а не берётся из ответа сайта;
- файл — только SVG до 200 КБ без скриптов, внешних ссылок, `foreignObject`, DOCTYPE/ENTITY;
- кладётся в `outbox/montage/logos/` (вне защищённой `integrations/`, вне git); откуда взят — в `_sources.json`.

    python -m integrations.montage.logos search notion
    python -m integrations.montage.logos fetch notion [--as имя]
    python -m integrations.montage.logos list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config

CACHE = config.LOGO_CACHE
ALLOWED_HOSTS = {"api.github.com", "raw.githubusercontent.com"}
MAX_BYTES = 200 * 1024
SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{0,60}$")
THESVG = "glincker/thesvg"
GILBARBARA = "gilbarbara/logos"
INDEX_TTL = 24 * 3600


class LogoError(RuntimeError):
    """Логотип не получен; текст — для владелицы."""


def check_url(url: str) -> str:
    m = re.match(r"^https://([^/]+)/", url)
    if not m or m.group(1) not in ALLOWED_HOSTS:
        raise LogoError(f"адрес не из разрешённых источников логотипов: {url[:80]}")
    return url


def _get(url: str, opener=urllib.request.urlopen, limit: int = MAX_BYTES) -> bytes:
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-montage-logos"})
    with opener(req, timeout=30) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise LogoError(f"файл больше {limit // 1024} КБ — не логотип")
    return data


def sanitize_svg(data: bytes) -> bytes:
    """Пропускает только чистый SVG: без скриптов, внешних ссылок и сущностей. Иначе LogoError."""
    low = data.lower()
    for bad in (b"<!doctype", b"<!entity", b"<script", b"<foreignobject", b"javascript:", b"<iframe", b"<image", b"@import"):
        if bad in low:
            raise LogoError(f"в SVG есть запрещённое: {bad.decode()}")
    if re.search(rb"\son[a-z]+\s*=", low):
        raise LogoError("в SVG есть обработчики событий (on…=)")
    if re.search(rb"(?:xlink:)?href\s*=\s*[\"'](?!#)", low):
        raise LogoError("в SVG есть внешние ссылки (href)")
    if re.search(rb"url\(\s*[\"']?(?!#)", low):
        raise LogoError("в SVG есть внешние url(…)")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise LogoError(f"это не SVG: {e}") from e
    if not root.tag.endswith("svg"):
        raise LogoError("корневой элемент не <svg>")
    return data


def candidates(slug: str) -> list[tuple[str, str]]:
    """(источник, адрес) в порядке попыток. Путь строится из проверенного имени."""
    if not SLUG.match(slug):
        raise LogoError(f"имя «{slug}» не годится: только латиница, цифры и дефис (например, google-calendar)")
    raw = "https://raw.githubusercontent.com"
    return [(THESVG, f"{raw}/{THESVG}/main/public/icons/{slug}/default.svg"),
            (THESVG, f"{raw}/{THESVG}/main/public/icons/{slug}/color.svg"),
            (GILBARBARA, f"{raw}/{GILBARBARA}/main/logos/{slug}.svg"),
            (GILBARBARA, f"{raw}/{GILBARBARA}/main/logos/{slug}-icon.svg")]


def fetch(slug: str, as_name: str | None = None, dest: Path | None = None, opener=urllib.request.urlopen) -> Path:
    name = as_name or slug
    if not SLUG.match(name):
        raise LogoError(f"имя «{name}» не годится: только латиница, цифры и дефис")
    dest = Path(dest) if dest else CACHE
    dest.mkdir(parents=True, exist_ok=True)
    errors = []
    for source, url in candidates(slug):
        try:
            data = sanitize_svg(_get(url, opener))
        except urllib.error.HTTPError as e:
            errors.append(f"{source}: {e.code}")
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            raise LogoError(f"нет связи с GitHub: {e}") from e
        except LogoError as e:
            errors.append(f"{source}: {e}")
            continue
        out = dest / f"{name}.svg"
        out.write_bytes(data)
        _remember(dest, name, url)
        return out
    raise LogoError(f"логотип «{slug}» не найден ({'; '.join(errors)}). Поищи имя: python -m integrations.montage.logos search {slug}")


def _remember(dest: Path, name: str, url: str) -> None:
    f = dest / "_sources.json"
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        doc = {}
    doc[name] = url
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def _tree(repo: str, path: str, opener) -> list[str]:
    url = f"https://api.github.com/repos/{repo}/git/trees/main:{path}"
    doc = json.loads(_get(url, opener, limit=4 * 1024 * 1024))
    return [x["path"] for x in doc.get("tree", [])]


def index(opener=urllib.request.urlopen, dest: Path | None = None, refresh: bool = False) -> dict:
    """Имена логотипов обоих каталогов (кэш на сутки): {"thesvg": [...], "gilbarbara": [...]}."""
    dest = Path(dest) if dest else CACHE
    f = dest / "_index.json"
    if not refresh and f.exists() and time.time() - f.stat().st_mtime < INDEX_TTL:
        return json.loads(f.read_text(encoding="utf-8"))
    doc = {"thesvg": _tree(THESVG, "public/icons", opener),
           "gilbarbara": [p[:-4] for p in _tree(GILBARBARA, "logos", opener) if p.endswith(".svg")]}
    dest.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def search(query: str, opener=urllib.request.urlopen, dest: Path | None = None) -> list[str]:
    q = query.lower().strip()
    idx = index(opener, dest)
    seen, out = set(), []
    for key in ("thesvg", "gilbarbara"):
        for n in idx[key]:
            if q in n.lower() and n not in seen:
                seen.add(n)
                out.append(n)
    return sorted(out, key=lambda n: (n != q, len(n), n))[:40]


def available() -> list[str]:
    names = {p.stem for p in (config.ASSETS / "logos").glob("*.svg")}
    if CACHE.exists():
        names |= {p.stem for p in CACHE.glob("*.svg")}
    return sorted(names)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="integrations.montage.logos", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search"); p.add_argument("query")
    p = sub.add_parser("fetch"); p.add_argument("slug"); p.add_argument("--as", dest="as_name")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            print("\n".join(available()))
        elif a.cmd == "search":
            hits = search(a.query)
            print("\n".join(hits) if hits else "ничего не нашлось")
        else:
            path = fetch(a.slug, a.as_name)
            print(f"готово: {path}")
        return 0
    except LogoError as e:
        print("ОШИБКА:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
