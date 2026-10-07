"""Ограниченный просмотр идей из существующей недели: без записи и сети."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEEKS = ROOT / "essa-ai" / "content-plan" / "weeks"


def inspect_week(week_dir: Path, *, limit: int = 3) -> dict:
    if not 1 <= limit <= 20:
        raise ValueError("Количество идей должно быть от 1 до 20")
    folder = Path(week_dir).resolve()
    if folder.parent != WEEKS.resolve():
        raise ValueError("Можно смотреть только неделю внутри папки weeks")
    path = (folder / "reels.json").resolve()
    if path.parent != folder:
        raise ValueError("Файл плана находится за пределами недели")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Не удалось прочитать план недели: отсутствует файл или неверный JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("План недели должен быть JSON-объектом")
    days = data.get("days", [])
    if isinstance(days, dict):
        days = list(days.values())
    if not isinstance(days, list):
        raise ValueError("В плане days должен быть списком или объектом")
    ideas = []
    for day in days:
        if not isinstance(day, dict) or not isinstance(day.get("reels", []), list):
            raise ValueError("Неверный формат дня или списка reels")
        for reel in day.get("reels", []):
            if not isinstance(reel, dict):
                raise ValueError("Идея должна быть объектом")
            item = {"date": str(day.get("date", "")), "title": str(reel.get("title_ru") or reel.get("title") or "")}
            for key in ("hook", "why_recommended", "url", "scenario_ru"):
                if isinstance(reel.get(key), str):
                    item[key] = reel[key]
            ideas.append(item)
            if len(ideas) >= limit:
                return {"week": str(data.get("week", folder.name)), "ideas": ideas, "status": "ok"}
    return {"week": str(data.get("week", folder.name)), "ideas": ideas, "status": "ok" if ideas else "empty"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Посмотреть идеи существующей недели")
    parser.add_argument("--week", required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[\w-]+", args.week) or args.week in (".", ".."):
            raise ValueError("Укажи имя недели, а не путь")
        result = inspect_week(WEEKS / args.week, limit=args.limit)
    except ValueError as exc:
        print(str(exc))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
