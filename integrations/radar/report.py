"""Результат прогона: `essa-ai/content/radar-YYYY-MM-DD/`.

Этот модуль пишет только механическую часть — таблицы и сырые данные, полями
из формы выхода Apify (`apify.py`). `briefs.md` из `briefs-input.json` пишет
агент через её конвейер `textwriter` → `humaniser` (правило JARVIS: язык решает
конвейер текста, не код), поэтому здесь его нет.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HOOK_MAX = 120


def hook(transcript: str) -> str:
    """Первая фраза расшифровки — до 120 символов, до первого знака конца предложения."""
    text = (transcript or "").strip()
    if not text:
        return ""
    for sep in (".", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx <= HOOK_MAX:
            return text[: idx + 1].strip()
    return text[:HOOK_MAX].strip()


def _link(reel: dict[str, Any]) -> str:
    if reel.get("url"):
        return reel["url"]
    code = reel.get("shortCode", "")
    return f"https://instagram.com/reel/{code}/" if code else "—"


def _code(reel: dict[str, Any]) -> str:
    return reel.get("shortCode", "")


def write_radar_md(path: Path, reels: list[dict[str, Any]], transcripts: dict[str, str]) -> None:
    lines = ["# Рилс-радар", "", "| Автор | Ссылка | Дата | Просмотры | Комментарии | ER | Хук |",
              "|---|---|---|---|---|---|---|"]
    for r in reels:
        author = r.get("ownerUsername", "?")
        code = _code(r)
        date = str(r.get("timestamp", ""))[:10]
        views = r.get("videoPlayCount") or r.get("videoViewCount") or 0
        comments = r.get("commentsCount", 0)
        er = f"{r.get('_er', 0):.2%}"
        h = hook(transcripts.get(code, "")) or "—"
        lines.append(f"| {author} | {_link(r)} | {date} | {views} | {comments} | {er} | {h} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_briefs_input(path: Path, reels: list[dict[str, Any]], transcripts: dict[str, str],
                        top_final: int) -> None:
    items = []
    for r in reels[:top_final]:
        code = _code(r)
        items.append({
            "code": code,
            "author": r.get("ownerUsername", ""),
            "link": _link(r),
            "views": r.get("videoPlayCount") or r.get("videoViewCount") or 0,
            "transcript": transcripts.get(code, ""),
        })
    path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_own_top_md(path: Path, own_reels: list[dict[str, Any]]) -> None:
    lines = ["# Её топ рилсов — сверка", "", "| Ссылка | Дата | Просмотры |", "|---|---|---|"]
    for r in own_reels:
        date = str(r.get("timestamp", ""))[:10]
        views = r.get("videoPlayCount") or r.get("videoViewCount") or 0
        lines.append(f"| {_link(r)} | {date} | {views} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
