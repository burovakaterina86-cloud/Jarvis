"""Картинки в папку комплекта — рядом с текстами.

Папка комплекта: `essa-ai/content/YYYY-MM-DD-<тема>/` с `post.md`, `carousel.md`,
`reels.md`, `stories.md`. Вёрстка и снимки ложатся в подпапку `visuals/`,
тексты не трогаются.

Обслуживаются все три вида сразу: слайды карусели, обложка поста и фон сторис.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import render, templates, tokens

#: Подпапка с вёрсткой и снимками внутри комплекта.
VISUALS_DIR = "visuals"


@dataclass
class VisualItem:
    """Одна картинка комплекта: вёрстка, целевой PNG и итог снимка."""

    kind: str          # carousel | cover | story
    html_path: Path
    png_path: Path
    width: int
    height: int
    result: render.RenderResult
    #: Что сказать владелице про этот кадр: какой её файл встал, какого нет.
    notes: list[str] = field(default_factory=list)


def _write(path: Path, html: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def _make(kind: str, name: str, html: str, out_dir: Path, notes=None) -> VisualItem:
    w, h = tokens.CANVAS[kind]
    html_path = _write(out_dir / f"{name}.html", html)
    png_path = out_dir / f"{name}.png"
    return VisualItem(
        kind=kind,
        html_path=html_path,
        png_path=png_path,
        width=w,
        height=h,
        result=render.render_image(html_path, png_path, w, h),
        notes=list(notes or []),
    )


#: Поля слайда, значение которых — файл владелицы (фото, скриншот).
ASSET_FIELDS = ("photo", "screenshot")


def _carry_assets(slide: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Её файлы ложатся рядом с вёрсткой: страница раздаётся по HTTP и видит
    только соседние файлы. Чужого не подставляем — нет файла, идём дальше."""
    data = dict(slide)
    for key in ASSET_FIELDS:
        src = data.get(key)
        if not src:
            continue
        src = Path(src)
        if src.is_file():
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / src.name
            if src.resolve() != dst.resolve():
                shutil.copyfile(src, dst)
            data[key] = dst
    return data


def build_kit_visuals(
    kit_dir: str | Path,
    carousel_slides: list[dict[str, Any]] | None = None,
    cover: dict[str, Any] | None = None,
    story: dict[str, Any] | None = None,
    style: str | None = None,
) -> list[VisualItem]:
    """Собрать вёрстку и снимки для комплекта.

    `carousel_slides` — словари с полями `build_carousel_slide`: `hook`, `body`,
    `label`, `role`, `thesis`, `footer_thesis`, `steps`, `flow`, `cards`,
    `summary`, `handwritten`, `photo`, `screenshot`.
    `cover` — `hook`, `subtitle`; `story` — `key_phrase`, `caption`.
    Вид без данных просто не строится; переданный — строится всегда.

    `style` не задан — порядок тёмных и светлых слайдов берётся один раз на всю
    карусель (`tokens.alternating_styles`), а не подбирается для каждого слайда.
    """
    out_dir = Path(kit_dir) / VISUALS_DIR
    items: list[VisualItem] = []

    slides = carousel_slides or []
    total = len(slides)
    order = tokens.alternating_styles(total) if style is None else (style,) * total
    for i, slide in enumerate(slides, start=1):
        data = _carry_assets(slide, out_dir)
        notes: list[str] = []
        kwargs = {k: v for k, v in data.items() if k != "style"}
        kwargs.setdefault("role", "cover" if i == 1 else "slide")
        html = templates.build_carousel_slide(
            index=i,
            total=total,
            style=data.get("style", order[i - 1]),
            notes=notes,
            **kwargs,
        )
        items.append(_make("carousel", f"carousel-{i:02d}", html, out_dir, notes))

    if cover:
        items.append(_make("cover", "cover", templates.build_post_cover(**cover), out_dir))

    if story:
        items.append(
            _make("story", "story", templates.build_story_background(**story), out_dir)
        )

    return items


def report(items: list[VisualItem]) -> str:
    """Короткая сводка для владелицы: что снято, что нет и почему."""
    lines = []
    for item in items:
        if item.result.ok:
            lines.append(f"{item.png_path.name} — {item.width}×{item.height}, готов")
        else:
            lines.append(
                f"{item.png_path.name} — не снят: {item.result.error}; "
                f"вёрстка: {item.html_path}"
            )
        for note in item.notes:
            lines.append(f"  · {note}")
        for w in item.result.warnings:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines)
