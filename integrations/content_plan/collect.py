"""Сбор: запросы из облака тегов → акторы Apify → сырые файлы недели.

Деньги списываются заранее, по числу запрошенных результатов (`apify.estimate`): упёрлись в
потолок — `BudgetExceeded`, актор не запускается. Сырые данные в чат не выводятся — только в
`raw/`; дальше их читают `pool` и `digest`.

Порядок фильтров из инструкции агента: цифры → убрать стопроцентно чужое → расшифровать всё
оставшееся → отбор по тексту. Тему по подписи не судим.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .apify import ActorClient, UsdBudget, estimate
from .pool import JUNK

MEMO23 = "memo23~instagram-reels-search-scraper"
BOOLEAN = "scraping_solutions~instagram-boolean-search-scraper-posts-reels"
REEL_SCRAPER = "apify~instagram-reel-scraper"
POST_SCRAPER = "apify~instagram-post-scraper"
TRANSCRIBER = "steadyfetch~instagram-reel-transcript-scraper"

MAX_AUTHORS = 40
AUTHOR_REELS = 12
MEMO23_PER_QUERY = 60
BOOLEAN_LIMIT = 60
TRANSCRIBE_CHUNK = 40
#: Автор попадает в слой, если у него есть рилс с таким числом комментариев или просмотров.
DISCOVER_COMMENTS = 300
DISCOVER_VIEWS = 100_000


@dataclass
class Source:
    name: str                 # имя файла: raw/<префикс>_<name>.json
    actor: str
    payload: dict[str, Any]
    results: int              # сколько результатов запрошено — по этому считаем цену

    @property
    def cost(self) -> float:
        return estimate(self.actor, self.results)


def _iso_days_ago(today: dt.date, days: int) -> str:
    return (today - dt.timedelta(days=days)).isoformat()


TRIAL_QUERIES = 8
TRIAL_PER_QUERY = 40
#: Фильтры считаются на стороне актора ДО оплаты: непрошедшие рилсы не списываются.
SEARCH_MIN_COMMENTS = 100


def search_sources(profile: Any, today: dt.date, *, trial: bool = False) -> list[Source]:
    """Живой поиск memo23 (булевы запросы: AND/OR/NOT, слова целиком) и второй булев поиск (scraping_solutions).

    `trial` — пробная выдача первого запуска (≈ $0,4 за сбор): 8 запросов по 30 результатов.
    """
    queries = list(profile.memo23_queries) + list(profile.memo23_cta_queries)
    per_query = MEMO23_PER_QUERY
    if trial:
        # поровну из обычных и воронок, чтобы в пробе были и те и другие
        plain, cta = list(profile.memo23_queries), list(profile.memo23_cta_queries)
        queries = plain[:TRIAL_QUERIES - min(len(cta), 2)] + cta[:2]
        per_query = TRIAL_PER_QUERY
    sources = []
    if queries:
        sources.append(Source("memo23", MEMO23,
                              {"queries": queries, "maxResultsPerQuery": per_query,
                               "englishOnly": list(profile.market_langs) == ["en"],
                               "oldestPostDate": _iso_days_ago(today, profile.window_days),
                               "minimumComments": SEARCH_MIN_COMMENTS,
                               "hashtagFeedType": "recent", "searchCoverage": "comprehensive"},
                              len(queries) * per_query))
    if profile.boolean_query_en:
        sources.append(Source("boolean", BOOLEAN,
                              {"searchQuery": profile.boolean_query_en, "resultsLimit": BOOLEAN_LIMIT,
                               "contentType": "reels_only", "hashtagFeedType": "recent",
                               "searchCoverage": "efficient",
                               "oldestPostDate": _iso_days_ago(today, profile.window_days),
                               "minimumComments": 300}, BOOLEAN_LIMIT))
    return sources


def discover_authors(rows: list[dict[str, Any]], seed: list[str], cap: int = MAX_AUTHORS) -> list[str]:
    """Слой авторов: её список (обязательно) + авторы из поиска с сильными цифрами. Мусор не берём."""
    authors = [a for a in dict.fromkeys(seed) if a]
    found: dict[str, int] = {}
    for x in rows:
        user = x.get("username") or x.get("ownerUsername")
        if not user or user in authors or JUNK.search(x.get("caption") or ""):
            continue
        comments = max(x.get("commentCount") or 0, x.get("commentsCount") or 0)
        views = max(x.get("viewCount") or 0, x.get("playCount") or 0, x.get("videoPlayCount") or 0)
        if comments >= DISCOVER_COMMENTS or views >= DISCOVER_VIEWS:
            found[user] = max(found.get(user, 0), comments * 50 + views)
    extra = sorted(found, key=lambda u: -found[u])
    return (authors + extra)[:max(cap, len(authors))]


def authors_source(authors: list[str], today: dt.date, window_days: int) -> Source:
    return Source("authors", REEL_SCRAPER,
                  {"username": authors, "resultsLimit": AUTHOR_REELS, "skipPinnedPosts": True},
                  len(authors) * AUTHOR_REELS)


def _save(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def _run(source: Source, client: ActorClient, budget: UsdBudget, raw_dir: Path, prefix: str) -> int:
    budget.charge(source.cost)
    items = client.run(source.actor, source.payload)
    _save(raw_dir / f"{prefix}_{source.name}.json", items)
    return len(items)


def collect_reels(profile: Any, client: ActorClient, budget: UsdBudget, week_dir: Path,
                  today: dt.date, *, prefix: str = "reels", trial: bool = False) -> dict[str, int]:
    """Поиск + слой авторов (в пробе слоя авторов нет). Возвращает {источник: сколько строк пришло}."""
    raw_dir = week_dir / "raw"
    counts: dict[str, int] = {}
    discovered: list[dict[str, Any]] = []
    for source in search_sources(profile, today, trial=trial):
        counts[source.name] = _run(source, client, budget, raw_dir, prefix)
        discovered += json.loads((raw_dir / f"{prefix}_{source.name}.json").read_text(encoding="utf-8"))
    authors = [] if trial else discover_authors(discovered, list(profile.seed_authors))
    if authors:
        counts["authors"] = _run(authors_source(authors, today, profile.window_days), client, budget, raw_dir, prefix)
        (week_dir / "authors.json").write_text(json.dumps(authors, ensure_ascii=False, indent=1), encoding="utf-8")
    return counts


def collect_carousels(profile: Any, client: ActorClient, budget: UsdBudget, week_dir: Path,
                      today: dt.date, authors: list[str]) -> int:
    """Карусели: посты авторов за окно; фильтр Sidecar и порог — в `pool.build_carousel_pool`."""
    source = Source("authors", POST_SCRAPER,
                    {"username": authors, "resultsLimit": AUTHOR_REELS,
                     "onlyPostsNewerThan": _iso_days_ago(today, profile.window_days)},
                    len(authors) * AUTHOR_REELS)
    return _run(source, client, budget, week_dir / "raw", "carousels")


def transcribe(codes: list[str], client: ActorClient, budget: UsdBudget, week_dir: Path,
               *, include_on_screen: bool = False) -> int:
    """Расшифровка пачками; результат сохраняем сразу — повторно актор текст не отдаёт."""
    done = 0
    for i in range(0, len(codes), TRANSCRIBE_CHUNK):
        chunk = codes[i:i + TRANSCRIBE_CHUNK]
        source = Source(f"{i // TRANSCRIBE_CHUNK + 1:02d}", TRANSCRIBER,
                        {"reelUrls": [f"https://www.instagram.com/reel/{c}/" for c in chunk],
                         "includeOnScreenText": include_on_screen, "maxRunSeconds": 1500}, len(chunk))
        done += _run(source, client, budget, week_dir / "raw", "transcripts")
    return done


#: Картинки слайдов берём только с серверов Instagram: адреса приходят из чужих данных (недоверенный контент).
SLIDE_HOSTS = ("cdninstagram.com", "fbcdn.net")


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def download_slides(week_dir: Path, codes: list[str], *, fetch=_fetch_bytes) -> dict[str, int]:
    """Слайды выбранных каруселей → raw/carousels/<код>/NN.jpg. Ссылки Instagram протухают за часы — качать сразу."""
    raw_dir = week_dir / "raw"
    wanted, saved = set(codes), {}
    for path in sorted(raw_dir.glob("carousels_*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            code = item.get("shortCode")
            if code not in wanted or code in saved:
                continue
            urls = []
            for kid in item.get("childPosts") or item.get("images") or []:
                url = kid.get("displayUrl") if isinstance(kid, dict) else kid
                if url:
                    urls.append(url)
            if not urls and item.get("displayUrl"):
                urls = [item["displayUrl"]]
            folder = raw_dir / "carousels" / code
            folder.mkdir(parents=True, exist_ok=True)
            ok = 0
            for i, url in enumerate(urls, 1):
                host = (urlparse(url).hostname or "").lower()
                if not host.endswith(SLIDE_HOSTS):
                    continue
                try:
                    (folder / f"{i:02d}.jpg").write_bytes(fetch(url))
                    ok += 1
                except OSError:
                    continue
            saved[code] = ok
    return saved
