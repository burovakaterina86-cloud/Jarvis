"""Сводка кандидатов с расшифровками — один текстовый файл для отбора по тексту.

На каждый рилс: цифры, подпись, речь (до 900 знаков — так экономим токены), текст на экране.
Расшифровки сохраняем сразу: актор не отдаёт повторно уже расшифрованное (`repeat`).
"""
from __future__ import annotations

import re
from typing import Any

SPEECH_LIMIT = 900
SCREEN_LIMIT = 500
CAPTION_LIMIT = 300


def merge_transcripts(batches: list[list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """По коду; при дублях берём запись, где есть текст или текст на экране."""
    out: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch:
            code = item.get("shortCode")
            if not code:
                continue
            has = bool((item.get("transcript") or "").strip() or item.get("onScreenText"))
            if code not in out or has:
                out[code] = item
    return out


def _on_screen(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("rawText") or " ".join(str(value.get(k) or "") for k in ("headline", "body", "cta"))
        return str(raw).strip()
    return str(value or "").strip()


def has_speech(item: dict[str, Any]) -> bool:
    return bool((item.get("transcript") or "").strip())


def build_digest(pool: list[dict[str, Any]], transcripts: dict[str, dict[str, Any]]) -> str:
    by_code = {r["code"]: r for r in pool}
    blocks = []
    for code, item in transcripts.items():
        row = by_code.get(code, {})
        cap = re.sub(r"\s+", " ", row.get("cap") or item.get("caption") or "")[:CAPTION_LIMIT]
        speech = (item.get("transcript") or "").strip()[:SPEECH_LIMIT] or "—"
        screen = _on_screen(item.get("onScreenText"))[:SCREEN_LIMIT] or "—"
        duration = round(item.get("durationSeconds") or 0)
        blocks.append(
            f"### {code} | https://www.instagram.com/reel/{code}/ | @{row.get('U') or item.get('ownerUsername')}"
            f" | {row.get('age')}d | comments={row.get('C')} views={row.get('V')} x_author={row.get('x')}"
            f" | lang={item.get('language')} | dur={duration}s | status={item.get('status')}\n"
            f"CAPTION: {cap}\nSPEECH: {speech}\nON-SCREEN: {screen}\n")
    return "\n".join(blocks)


SHORT_SPEECH = 280


def build_short(pool: list[dict[str, Any]], transcripts: dict[str, dict[str, Any]],
                langs: tuple[str, ...] = ("English", "Russian")) -> str:
    """Одна строка на рилс: код | автор | слот | цифры | язык | длительность | начало речи.

    Это то, что читает отбор: полная сводка (`reels_digest.txt`) слишком велика для одного чтения.
    Без речи или на другом языке — не попадают (их разбор идёт отдельным списком).
    """
    by_code = {r["code"]: r for r in pool}
    lines = []
    for code, item in transcripts.items():
        speech = re.sub(r"\s+", " ", (item.get("transcript") or "").strip())
        if not speech or item.get("language") not in langs:
            continue
        row = by_code.get(code, {})
        duration = round(item.get("durationSeconds") or 0)
        lines.append(f"{code}|@{row.get('U') or item.get('ownerUsername')}|{row.get('slot')}|"
                     f"C{row.get('C')} V{row.get('V')} x{row.get('x')}|{(item.get('language') or '')[:2]}|{duration}s|"
                     f"{speech[:SHORT_SPEECH]}")
    return "\n".join(lines)
