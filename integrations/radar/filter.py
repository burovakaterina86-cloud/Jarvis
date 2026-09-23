"""Шаг 3: фильтр по ключевым словам ниши — подпись и хэштеги (Apify bio не отдаёт).

Матч по границе слова, регистр не важен, работает и для кириллицы — как в
методе upstream (`config/keywords.txt` там, список `keywords` в конфиге здесь).
"""
from __future__ import annotations

import re
from typing import Any, Iterable


def _haystack(reel: dict[str, Any]) -> str:
    caption = str(reel.get("caption") or "")
    hashtags = " ".join(reel.get("hashtags") or [])
    return " ".join(part for part in (caption, hashtags) if part).lower()


def matches_keywords(reel: dict[str, Any], keywords: Iterable[str]) -> bool:
    text = _haystack(reel)
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        pattern = r"(?<!\w)" + re.escape(kw.lower()) + r"(?!\w)"
        if re.search(pattern, text, flags=re.UNICODE):
            return True
    return False


def filter_relevant(reels: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    """Без ключевых слов фильтр не сужает — считаем, что она ещё не задала нишу."""
    keywords = [k for k in keywords if k and k.strip()]
    if not keywords:
        return list(reels)
    return [r for r in reels if matches_keywords(r, keywords)]
