"""Слияние выдачи скраперов в один пул кандидатов.

Порт `pool.py` из агента: те же правила, но чистые функции, пороги и стоп-слова из паспорта.
Поддержаны три схемы: boolean-search (scraping_solutions), memo23 reels search, apify reel-scraper.

Кратность к норме автора (`x`) — просмотры ÷ медиана просмотров автора (минимум 5 рилсов в
файле `authors*`). К числу подписчиков не привязываемся: ищем ролики выше обычного уровня
самого автора.
"""
from __future__ import annotations

import collections
import datetime as dt
import re
import statistics
from typing import Any, Iterable

MIN_REELS_FOR_MEDIAN = 5

#: Мусорные шаблоны ниши (экзамены, розыгрыши, «день 137/365», похудение).
JUNK = re.compile(
    r"(CA\s?(INTER|FOUNDATION)|UPSC|NEET|JEE|CAT\s?20|semester|exam|syllabus|day\s?\d{1,3}\s?/\s?365"
    r"|365\s?day|giveaway|#dink|kitten|weight loss|glp-1)", re.I)
#: Призыв «напиши слово»: comment/drop/type/reply/DM + слово.
CTA = re.compile(
    r"\b(comment|drop|type|reply|dm)\b\s*(me\s*)?[\"“”'‘’]?[A-Za-z0-9]{2,}[\"“”'‘’]?"
    r"|comment below|pinned comment", re.I)
NON_EN_WORDS = re.compile(
    r"\b(que|para|você|comenta|mando|kommentiere|dich|tumhare|karte|agar|bhai|pra|seu|como|los|las|und|mit"
    r"|voor|ik|kaise|hai|nahi)\b", re.I)
CYRILLIC = re.compile("[Ѐ-ӿ]")
OTHER_SCRIPTS = re.compile("[؀-ۿऀ-ॿ぀-ヿ一-鿿가-힯฀-๿]")
LATIN = re.compile("[A-Za-z]")
#: Русский призыв: глагол + «слово X» или слово в кавычках («пиши «монтаж»», «напиши слово тренд»).
CTA_RU = re.compile(
    r"(?:напиш\w*|пиш\w*|комментир\w*|оставь\w*|оставляй\w*)[^.!?\n]{0,40}?"
    r"(?:слово\s+[«\"“]?[\wЁё-]{3,}|[«\"“][\wЁё -]{2,}[»\"”])", re.I)

SLOT_ORDER = ["воронка", "аутлаер", "горячее", "воронка-600", "запас"]


def caption_lang_ok(caption: str, langs: Iterable[str] = ("en",)) -> bool:
    """Эвристика по подписи под языки рынка (`en`, `ru`). Только предварительная:
    язык речи проверяется по расшифровке, подпись часто не совпадает с речью."""
    langs = set(langs)
    if OTHER_SCRIPTS.search(caption):
        return False
    if CYRILLIC.search(caption):
        return "ru" in langs
    if not LATIN.search(caption):
        return True  # пустая подпись или одни эмодзи — решает расшифровка
    return "en" in langs and len(NON_EN_WORDS.findall(caption)) < 2


def has_cta(caption: str) -> bool:
    return bool(CTA.search(caption) or CTA_RU.search(caption))


def _parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _num(item: dict[str, Any], *keys: str) -> int:
    """Первое неотрицательное число из перечисленных полей (скрытые лайки приходят как -1)."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return 0


def normalize(item: dict[str, Any], src: str, now: dt.datetime) -> dict[str, Any] | None:
    code = item.get("shortCode")
    when = _parse_time(item.get("publishedAt") or item.get("takenAt") or item.get("timestamp"))
    if not code or when is None:
        return None
    return {
        "code": code,
        "url": f"https://www.instagram.com/reel/{code}/",
        "age": (now - when).days,
        "C": _num(item, "commentCount", "commentsCount"),
        "L": _num(item, "likeCount", "likesCount"),
        "V": _num(item, "viewCount", "playCount", "videoPlayCount"),
        "U": item.get("username") or item.get("ownerUsername"),
        "cap": (item.get("caption") or "").strip(),
        "src": {src},
        "x": None,
        "med": None,
    }


def _apply_author_norm(rows: list[dict[str, Any]]) -> None:
    by_author: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_author[row["U"]].append(row)
    for group in by_author.values():
        if len(group) < MIN_REELS_FOR_MEDIAN:
            continue
        median = statistics.median(r["V"] for r in group)
        if not median:
            continue
        for row in group:
            row["x"] = round(row["V"] / median, 1)
            row["med"] = median


def slot_of(row: dict[str, Any], *, threshold: int, fallback: int) -> str:
    funnel_fallback = max(1, round(fallback * 0.25))
    if row["cta"] and (row["C"] >= threshold or (row["r_pct"] >= 1 and row["C"] >= round(threshold * 0.3))):
        return "воронка"
    if row["cta"] and (row["C"] >= fallback or (row["r_pct"] >= 1 and row["C"] >= funnel_fallback)):
        return "воронка-600"
    if (row["x"] or 0) >= 3:
        return "аутлаер"
    if row["C"] >= 1000 or row["r_pct"] >= 1 or row["V"] >= 300_000:
        return "горячее"
    return "запас"


def build_pool(raw: dict[str, list[dict[str, Any]]], *, seen: Iterable[str] = (),
               now: dt.datetime | None = None, window_days: int = 14,
               threshold: int = 1000, fallback: int = 600,
               stop_words: Iterable[str] = (), langs: Iterable[str] = ("en",)) -> list[dict[str, Any]]:
    """`raw` — {источник: строки датасета}. Источники с префиксом `authors` дают норму автора.

    Возвращает свежие рилсы без повторов и мусора, отсортированные по слоту и силе цифр.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    seen = set(seen)
    stops = [w.lower() for w in stop_words if w]
    pool: dict[str, dict[str, Any]] = {}
    for src, items in raw.items():
        rows = [r for r in (normalize(x, src, now) for x in items) if r]
        if src.startswith("authors"):
            _apply_author_norm(rows)
        for row in rows:
            known = pool.get(row["code"])
            if known is None:
                pool[row["code"]] = row
                continue
            known["src"] |= row["src"]
            if row["x"] is not None:
                known["x"], known["med"] = row["x"], row["med"]

    fresh = []
    for row in pool.values():
        row["src"] = sorted(row["src"])
        row["cta"] = has_cta(row["cap"])
        row["r_pct"] = round(100 * row["C"] / row["V"], 2) if row["V"] else 0
        cap_low = row["cap"].lower()
        row["junk"] = bool(JUNK.search(row["cap"])) or any(w in cap_low for w in stops)
        row["en"] = caption_lang_ok(row["cap"], langs)
        row["repeat"] = row["code"] in seen
        if row["age"] <= window_days and row["en"] and not row["repeat"] and not row["junk"]:
            fresh.append(row)
    for row in fresh:
        row["slot"] = slot_of(row, threshold=threshold, fallback=fallback)
    fresh.sort(key=lambda r: (SLOT_ORDER.index(r["slot"]), -(r["r_pct"] * 100_000 + r["C"] * 50 + r["V"])))
    return fresh


def review_text(pool: list[dict[str, Any]]) -> str:
    """Строки для беглого просмотра: всё, кроме слота «запас»."""
    lines = []
    for r in pool:
        if r["slot"] == "запас":
            continue
        cap = re.sub(r"\s+", " ", r["cap"])[:260]
        lines.append(f"[{r['code']}] {r['slot']} | {r['age']}d | C={r['C']} V={r['V']} x={r['x']} | @{r['U']} | {cap}")
    return "\n".join(lines)


def slot_counts(pool: list[dict[str, Any]]) -> dict[str, int]:
    return dict(collections.Counter(r["slot"] for r in pool))


# ---------- карусели ----------

def build_carousel_pool(items: list[dict[str, Any]], *, seen: Iterable[str] = (),
                        now: dt.datetime | None = None, window_days: int = 14,
                        threshold: int = 1000, fallback: int = 300,
                        stop_words: Iterable[str] = (),
                        langs: Iterable[str] = ("en",)) -> tuple[list[dict[str, Any]], int]:
    """Карусели = посты типа Sidecar. Порог 1000 комментариев, при нехватке — запасной.

    Возвращает (список по убыванию комментариев, применённый порог).
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    seen = set(seen)
    stops = [w.lower() for w in stop_words if w]
    found: dict[str, dict[str, Any]] = {}
    for x in items:
        if (x.get("type") or "").lower() != "sidecar":
            continue
        code = x.get("shortCode")
        when = _parse_time(x.get("timestamp") or x.get("takenAt") or x.get("publishedAt"))
        if not code or when is None or code in seen or code in found:
            continue
        cap = (x.get("caption") or "").strip()
        if (now - when).days > window_days or not caption_lang_ok(cap, langs):
            continue
        if JUNK.search(cap) or any(w in cap.lower() for w in stops):
            continue
        found[code] = {"code": code, "url": f"https://www.instagram.com/p/{code}/", "age": (now - when).days,
                       "C": _num(x, "commentsCount", "commentCount"), "L": _num(x, "likesCount", "likeCount"),
                       "U": x.get("ownerUsername") or x.get("username"), "cap": cap,
                       "slides": len(x.get("childPosts") or x.get("images") or []),
                       "cta": has_cta(cap)}
    rows = sorted(found.values(), key=lambda r: -r["C"])
    top = [r for r in rows if r["C"] >= threshold]
    if len(top) >= 3:
        return top, threshold
    return [r for r in rows if r["C"] >= fallback], fallback
