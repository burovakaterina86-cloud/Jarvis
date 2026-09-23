"""Шаг 1 метода (переработан по её решению): рилсы по готовому списку конкурентов.

Источник данных — Apify, актор `apify/instagram-reel-scraper` (официальный,
оплата за результат от $1 за 1000 рилсов, бесплатный план даёт $5/мес — её выбор
вместо платного HikerAPI из upstream-метода). Подписки эталонного аккаунта не
сканируем: она дала готовый список конкурентов, идём прямо по нему.

Форма выхода актора (apify.com/apify/instagram-reel-scraper, снято 2026-09-23):
`shortCode`, `caption`, `hashtags`, `timestamp`, `likesCount`, `videoViewCount`,
`videoPlayCount`, `commentsCount`, `videoUrl`, `url`, `ownerUsername`. Bio автора
актор не отдаёт — фильтр по ключевым словам (`filter.py`) идёт по caption и hashtags.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .budget import RequestBudget


class ApifyClient(Protocol):
    """Подменяемый клиент — тесты подставляют fake с готовыми ответами актора."""

    def fetch_reels(self, username: str, results_limit: int, newer_than: str) -> list[dict[str, Any]]: ...


def _cutoff_str(days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).date().isoformat()


def _taken_at(reel: dict[str, Any]) -> datetime:
    value = reel.get("timestamp")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"нет даты timestamp в рилсе {reel.get('shortCode')}")


def fetch_recent_reels(client: ApifyClient, budget: RequestBudget, usernames: list[str],
                        window_days: int, per_account: int, now: datetime | None = None
                        ) -> list[dict[str, Any]]:
    """Рилсы каждого аккаунта её списка за окно, топ `per_account` по просмотрам.

    Потолок трат считается в числе запрошенных рилсов (так тарифицирует Apify):
    `budget.spend(per_account)` перед каждым вызовом актора.
    """
    newer_than = _cutoff_str(window_days, now)
    cutoff = now or datetime.now(timezone.utc)
    cutoff = cutoff - timedelta(days=window_days)
    out: list[dict[str, Any]] = []
    for username in usernames:
        budget.spend(per_account)
        reels = client.fetch_reels(username, per_account, newer_than)
        fresh = [r for r in reels if _taken_at(r) >= cutoff]
        fresh.sort(key=lambda r: r.get("videoPlayCount") or r.get("videoViewCount") or 0,
                   reverse=True)
        out.extend(fresh[:per_account])
    return out


def fetch_own_top(client: ApifyClient, budget: RequestBudget, username: str,
                   window_days: int, fetch_limit: int, top: int,
                   now: datetime | None = None) -> list[dict[str, Any]]:
    """Её собственный топ рилсов за окно (по умолчанию 30 дней) — для сверки."""
    newer_than = _cutoff_str(window_days, now)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window_days)
    budget.spend(fetch_limit)
    reels = client.fetch_reels(username, fetch_limit, newer_than)
    fresh = [r for r in reels if _taken_at(r) >= cutoff]
    fresh.sort(key=lambda r: r.get("videoPlayCount") or r.get("videoViewCount") or 0,
               reverse=True)
    return fresh[:top]
