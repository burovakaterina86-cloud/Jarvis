"""Своя сцена (`type: custom`): JARVIS сам рисует новый экран или плашку HTML-ом, не трогая защищённый код.

HTML — данные от агента, поэтому он проходит через сито: только вёрстка и стили. Скриптов, обработчиков событий, ссылок
в интернет и подгрузки чужого нет; картинки — только `<img src="{{logo:имя}}">` или `url({{logo:имя}})` (настоящий SVG из каталога), шрифты уже подключены (Golos Text — `font-family:G`,
Playfair Italic — `font-family:PF`). Значки: `{{icon:mic}}` или `{{icon:mic|56}}` (список — `icons.NAMES`); без эмодзи. Страница рисуется с анимацией по атрибутам:

    data-a="pop|rise|fade"  data-d="0.3"  data-dur="0.4"   — появление (задержка от начала сцены, длительность, с)
    data-word="корень"                                       — «нажать» элемент на этом слове речи (станет data-t)
    data-t="37.5"                                            — «нажать» в явное время (с)

Кадр 1080×1920. Содержимое — в безопасной зоне: сверху ≥ 115 px, снизу ≤ 1248 px, по бокам ≥ 64 px (`safe_warnings`).
"""
from __future__ import annotations

import re

from . import config, icons
from .spec import SpecError, find_word, logo_path

LAYOUTS = {"full", "split", "band"}
FORBIDDEN_TAGS = ("script", "iframe", "object", "embed", "link", "meta", "base", "form", "input", "button", "video", "audio",
                  "canvas", "frame", "frameset")
MAX_HTML = 60_000


def sanitize(html: str) -> str:
    if len(html) > MAX_HTML:
        raise SpecError(f"HTML сцены больше {MAX_HTML // 1000} КБ — упрости")
    low = html.lower()
    for tag in FORBIDDEN_TAGS:
        if re.search(rf"<\s*{tag}\b", low):
            raise SpecError(f"в HTML сцены нельзя <{tag}> (логотипы — <img src=\"{{{{logo:имя}}}}\">, свои значки — внутренний <svg>)")
    if re.search(r"\son[a-z]+\s*=", low):
        raise SpecError("в HTML сцены нельзя обработчики событий (on…=)")
    if "javascript:" in low or "@import" in low or "<!--" in low and "-->" not in low:
        raise SpecError("в HTML сцены нельзя javascript:, @import и незакрытые комментарии")
    if re.search(r"(?:src|href|action|poster)\s*=\s*(?:[\"']\s*(?!#|\{\{)|(?![\"'])(?!#|\{\{))", low):
        raise SpecError("в HTML сцены нельзя внешние адреса (src/href): логотипы — {{logo:имя}}")
    if re.search(r"url\(\s*(?:[\"']\s*(?!#|\{\{)|(?![\"'])(?!#|\{\{))", low):
        raise SpecError("в стилях сцены нельзя url(…) на внешнее: логотипы — {{logo:имя}}")
    if re.search(r"https?://|//[a-z0-9.-]+\.[a-z]{2,}", low):
        raise SpecError("в HTML сцены нельзя адреса в интернет")
    return html


def process(html: str, words: list[dict], start: float) -> str:
    """Сито → подстановка логотипов `{{logo:имя}}` → `data-word` становится `data-t` со временем из речи."""
    html = re.sub(r"<!--.*?-->", "", sanitize(html), flags=re.S)      # комментарии — не вёрстка: подсказки в них не должны срабатывать

    def logo(m):
        return logo_path(m.group(1)).resolve().as_uri()

    html = re.sub(r"\{\{logo:([a-z0-9\-]+)\}\}", logo, html)
    try:
        html = icons.fill_placeholders(html)
    except ValueError as e:
        raise SpecError(f"сцена custom: {e}") from e
    if "{{" in html:
        raise SpecError("в HTML сцены остались неразобранные {{…}}: допустимо только {{logo:имя}} и {{icon:имя}}")

    def word(m):
        stem = m.group(2)
        t = find_word(words, stem, start)
        if t is None:
            raise SpecError(f"сцена custom: в речи после {start} с нет слова «{stem}» (data-word)")
        return f"data-t={m.group(1)}{t}{m.group(1)}"

    return re.sub(r"data-word=([\"'])([^\"']+)\1", lambda m: word(m), html)


def safe_warnings(html: str) -> list[str]:
    """Что в вёрстке вылезает из безопасной зоны Instagram. Смотрим только элементы верхнего уровня:
    координаты вложенных элементов считаются от родителя, а не от кадра."""
    from html.parser import HTMLParser

    void = {"br", "img", "hr", "input", "meta", "link", "circle", "rect", "path", "line", "ellipse", "polygon", "polyline", "stop"}
    out: list[str] = []

    class P(HTMLParser):
        depth = 0

        def _check(self, attrs):
            style = dict(attrs).get("style") or ""
            g = lambda k: (re.search(rf"(?:^|;)\s*{k}\s*:\s*(-?\d+)px", style) or [None, None])[1]
            top, left, w, h = g("top"), g("left"), g("width"), g("height")
            if top is not None and 0 < int(top) < config.SAFE_TOP and not (w and int(w) >= 1000):
                out.append(f"top:{top}px — под шапкой Instagram (< {config.SAFE_TOP})")
            if top is not None and h is not None and int(h) < 1900 and int(top) + int(h) > config.SAFE_CAPTION + 2:
                out.append(f"низ {int(top) + int(h)}px — ниже {config.SAFE_CAPTION} (зона подписи)")
            if left is not None and w is not None and int(w) < 1000 and (int(left) < config.SAFE_SIDE - 1 or int(left) + int(w) > 1080 - config.SAFE_SIDE + 1):
                out.append(f"left:{left}px width:{w}px — ближе {config.SAFE_SIDE}px к краю")

        def handle_starttag(self, tag, attrs):
            if self.depth == 0:
                self._check(attrs)
            if tag not in void:
                self.depth += 1

        def handle_startendtag(self, tag, attrs):
            if self.depth == 0:
                self._check(attrs)

        def handle_endtag(self, tag):
            if tag not in void and self.depth > 0:
                self.depth -= 1

    P().feed(html)
    return out
