"""Одна точка входа сборки карусели: данные слайдов из `slides.json` → PNG.

    python -m integrations.visuals.build <папка комплекта> [slides.json]

`slides.json` лежит в папке комплекта (по умолчанию `<папка>/slides.json`):
`{"slides": [{…поля build_carousel_slide…}, …], "style": "STYLE_01"}` — `style`
необязателен, без него порядок тёмных и светлых берёт `tokens.alternating_styles`.
Относительные пути к её файлам (`photo`, `screenshot`, `screens`) считаются от
папки `slides.json`. Правка одного слова — правка JSON и та же команда.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

from . import kit, templates

#: Имя файла данных слайдов в папке комплекта.
SLIDES_FILE = "slides.json"

#: Поля, которые ставит сборка, а не данные слайда.
BUILD_OWNED = frozenset({"index", "total", "notes"})

#: Код выхода: вёрстка собрана, но хоть один заказанный PNG не снят.
#: 2 — ошибка данных или аргументов, 0 — все PNG на месте.
EXIT_NOT_RENDERED = 3


def slide_fields() -> frozenset:
    """Поля слайда, которые принимает `build_carousel_slide`."""
    params = inspect.signature(templates.build_carousel_slide).parameters
    return frozenset(params) - BUILD_OWNED


def _resolve(value: Any, base: Path) -> Any:
    """Относительный путь к её файлу — от папки `slides.json`."""
    if isinstance(value, dict):
        return {**value, "src": _resolve(value.get("src"), base)} if "src" in value else value
    if isinstance(value, str) and value:
        path = Path(value)
        return path if path.is_absolute() else base / path
    return value


def load_slides(slides_json: str | Path) -> tuple[list[dict[str, Any]], str | None]:
    """Прочитать и проверить данные слайдов. Неизвестное поле — `ValueError`."""
    slides_json = Path(slides_json)
    data = json.loads(slides_json.read_text(encoding="utf-8"))
    slides = data.get("slides") if isinstance(data, dict) else None
    if not isinstance(slides, list) or not slides:
        raise ValueError(f'{slides_json}: нужен непустой список "slides"')
    allowed = slide_fields()
    base = slides_json.parent
    out = []
    for i, slide in enumerate(slides, start=1):
        unknown = sorted(set(slide) - allowed)
        if unknown:
            raise ValueError(f"слайд {i}: неизвестные поля {', '.join(unknown)}")
        slide = dict(slide)
        for key in kit.ASSET_FIELDS:
            if slide.get(key):
                slide[key] = _resolve(slide[key], base)
        for key in kit.ASSET_LIST_FIELDS:
            value = slide.get(key)
            if value:
                items = [value] if isinstance(value, str) else list(value)
                slide[key] = [_resolve(item, base) for item in items]
        out.append(slide)
    return out, data.get("style")


def build(kit_dir: str | Path, slides_json: str | Path | None = None) -> list[kit.VisualItem]:
    """Собрать карусель комплекта из `slides.json`: вёрстка и снимки в `visuals/`."""
    kit_dir = Path(kit_dir)
    slides, style = load_slides(slides_json or kit_dir / SLIDES_FILE)
    return kit.build_kit_visuals(kit_dir, carousel_slides=slides, style=style)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not 1 <= len(argv) <= 2:
        print(__doc__)
        return 2
    try:
        items = build(*argv)
    except (OSError, ValueError) as exc:
        print(f"сборка не началась: {exc}")
        return 2
    print(kit.report(items))
    missing = [item for item in items if not item.result.ok]
    if missing:
        print(f"PNG не сняты: {len(missing)} из {len(items)} — картинок нет, есть только вёрстка:")
        for item in missing:
            print(f"  {item.png_path.name} — не снят: {item.result.error}")
        return EXIT_NOT_RENDERED
    return 0


if __name__ == "__main__":
    sys.exit(main())
