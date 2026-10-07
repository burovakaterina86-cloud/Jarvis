"""Шаг 4: композитное ранжирование — rank_views + rank_comments + rank_er, меньше лучше.

Как в методе upstream (`4-rank-composite.py`): каждому рилсу назначается место
(0 — лучший) по трём метрикам отдельно, три места складываются, топ-K берётся
по возрастанию суммы. Поля — из формы выхода Apify (`apify.py`).
"""
from __future__ import annotations

from typing import Any


def _count(reel: dict[str, Any], *keys: str) -> int:
    """Счётчик из ответа Apify: None и отрицательные значения (Instagram прячет лайки как -1) считаем нулём."""
    for key in keys:
        value = reel.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return value
    return 0


def engagement_rate(reel: dict[str, Any]) -> float:
    views = _count(reel, "videoPlayCount", "videoViewCount")
    if not views:
        return 0.0
    return (_count(reel, "likesCount") + _count(reel, "commentsCount")) / views


def _places(reels: list[dict[str, Any]], key) -> dict[int, int]:
    order = sorted(range(len(reels)), key=lambda i: key(reels[i]), reverse=True)
    return {idx: place for place, idx in enumerate(order)}


def rank_composite(reels: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Копии рилсов, топ-K по композитному рангу (добавляет `_composite_rank`, `_er`)."""
    if not reels:
        return []
    by_views = _places(reels, lambda r: _count(r, "videoPlayCount", "videoViewCount"))
    by_comments = _places(reels, lambda r: _count(r, "commentsCount"))
    by_er = _places(reels, engagement_rate)
    scored = []
    for i, reel in enumerate(reels):
        item = dict(reel)
        item["_composite_rank"] = by_views[i] + by_comments[i] + by_er[i]
        item["_er"] = engagement_rate(reel)
        scored.append(item)
    scored.sort(key=lambda r: r["_composite_rank"])
    return scored[:top_k]
