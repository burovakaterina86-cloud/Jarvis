"""Настоящий клиент Apify — используется только при живом прогоне (есть ключ).

Актор `apify/instagram-reel-scraper` (apify.com/apify/instagram-reel-scraper),
запуск синхронно с выдачей датасета: `run-sync-get-dataset-items`. Вход —
`username` (список), `resultsLimit`, `onlyPostsNewerThan`; выход — по одному
объекту на рилс с полями `shortCode`, `caption`, `hashtags`, `timestamp`,
`likesCount`, `videoViewCount`, `videoPlayCount`, `commentsCount`, `videoUrl`,
`url`, `ownerUsername`.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

ACTOR = "apify~instagram-reel-scraper"
BASE_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"


class ApifyApiClient:
    def __init__(self, token: str, base_url: str = BASE_URL):
        self._token = token
        self._base = base_url

    def fetch_reels(self, username: str, results_limit: int, newer_than: str) -> list[dict[str, Any]]:
        payload = {
            "username": [username],
            "resultsLimit": results_limit,
            "onlyPostsNewerThan": newer_than,
        }
        url = f"{self._base}?token={self._token}"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
