"""Спецификация ролика: что на экране и когда. Читается из JSON, времена — числами или «якорями» на слова.

    {"title": "...", "scenes": [{"type": "hook", "start": 0, ...},
                                {"type": "step", "n": 1, "start": {"word": "первая"}, ...}, ...]}

Якорь слова: `{"word": "календар", "after": 5.0, "offset": 0.0}` — начало первого слова, которое начинается с этого
корня (регистр и знаки не важны), не раньше `after` секунд. Нет такого слова — `SpecError` с понятным текстом:
выдумывать время нельзя (правило автора: время берётся из измерений, а не из пересказа).

Сцены идут в порядке времени; конец сцены — `end` или начало следующей (у последней — длительность ролика).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config

SCENE_TYPES = {"hook", "step", "phone", "week", "money", "pipe", "pill", "cta"}
PANEL_TYPES = {"hook", "step"}      # сплит: панель сверху, спикер снизу
BAND_TYPES = {"pill", "cta"}        # полоса: спикер сдвинут вниз, плашка над головой
FULL_TYPES = {"phone", "week", "money", "pipe"}   # полноэкранные визуалы без спикера
MIN_SCENE = 0.6                     # короче — не успеет прочитаться


class SpecError(ValueError):
    """Спецификация не сходится с речью или схемой; текст — для владелицы."""


def norm_word(w: str) -> str:
    return w.lower().replace("ё", "е").strip(" .,!?:;«»\"'()-—")


def find_word(words: list[dict], stem: str, after: float = 0.0) -> float | None:
    stem = norm_word(stem)
    for w in words:
        if norm_word(w["word"]).startswith(stem) and float(w["start"]) >= after - 1e-9:
            return round(float(w["start"]), 2)
    return None


def resolve_time(anchor, words: list[dict], what: str = "") -> float:
    if isinstance(anchor, (int, float)):
        return round(float(anchor), 2)
    if isinstance(anchor, dict) and "word" in anchor:
        t = find_word(words, anchor["word"], float(anchor.get("after", 0.0)))
        if t is None:
            raise SpecError(f"{what}: в речи нет слова «{anchor['word']}»"
                            + (f" после {anchor['after']} с" if anchor.get("after") else "") + " — поправь якорь в спецификации")
        return round(t + float(anchor.get("offset", 0.0)), 2)
    raise SpecError(f"{what}: время должно быть числом или {{\"word\": ...}}, а не {anchor!r}")


def logo_path(name: str) -> Path:
    for p in (config.ASSETS / "logos" / f"{name}.svg", config.ASSETS / f"{name}.svg"):
        if p.exists():
            return p
    raise SpecError(f"нет логотипа «{name}» в integrations/montage/assets/logos — возьми настоящий SVG "
                    "из glincker/thesvg или gilbarbara/logos (модель логотипы не рисует)")


@dataclass
class Scene:
    type: str
    start: float
    end: float
    data: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        n = self.data.get("n")
        return f"{self.type}{n}" if n else f"{self.type}_{int(self.start * 100)}"


@dataclass
class Resolved:
    title: str
    duration: float
    scenes: list[Scene]
    fixes: dict
    context_fixes: dict

    def windows(self, types: set[str]) -> list[tuple[float, float]]:
        return [(s.start, s.end) for s in self.scenes if s.type in types]


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve(spec: dict, words: list[dict], duration: float) -> Resolved:
    raw = spec.get("scenes")
    if not raw:
        raise SpecError("в спецификации нет сцен")
    starts = []
    for i, sc in enumerate(raw):
        if sc.get("type") not in SCENE_TYPES:
            raise SpecError(f"сцена {i + 1}: неизвестный тип {sc.get('type')!r} (есть: {', '.join(sorted(SCENE_TYPES))})")
        starts.append(resolve_time(sc.get("start", 0), words, f"сцена {i + 1} ({sc['type']})"))
    for i in range(1, len(starts)):
        if starts[i] <= starts[i - 1]:
            raise SpecError(f"сцена {i + 1} ({raw[i]['type']}) начинается в {starts[i]} с — не позже предыдущей ({starts[i - 1]} с)")
    if starts[-1] >= duration:
        raise SpecError(f"последняя сцена начинается в {starts[-1]} с, а ролик длится {duration} с")
    scenes: list[Scene] = []
    for i, sc in enumerate(raw):
        end = resolve_time(sc["end"], words, f"конец сцены {i + 1}") if "end" in sc else (starts[i + 1] if i + 1 < len(raw) else duration)
        end = min(end, duration)
        if end - starts[i] < MIN_SCENE:
            raise SpecError(f"сцена {i + 1} ({sc['type']}) длится {end - starts[i]:.2f} с — короче {MIN_SCENE} с, не прочитается")
        data = {k: v for k, v in sc.items() if k not in {"type", "start", "end"}}
        if sc["type"] == "step":
            data = _resolve_chips(data, starts[i], end, words, i + 1)
        if sc["type"] == "cta":
            press = data.get("press", {"word": data.get("code", "клод")})
            try:
                data["press_t"] = resolve_time({**press, "after": press.get("after", starts[i])}, words, "нажатие в призыве")
            except SpecError:
                data["press_t"] = round(starts[i] + 0.6, 2)
        if sc["type"] == "money":
            data["rows"] = _resolve_rows(data.get("rows"), starts[i], end, words)
        if sc["type"] == "week":
            for k in ("a", "b"):
                w = data.get(f"word_{k}", "текст" if k == "a" else "пост")
                data[f"t_{k}"] = find_word(words, w, starts[i]) or round(starts[i] + 0.5, 2)
        for lg in _logos_in(sc):
            logo_path(lg)
        scenes.append(Scene(sc["type"], starts[i], end, data))
    return Resolved(spec.get("title", ""), duration, scenes, spec.get("fixes", {}), spec.get("context_fixes", {}))


def _logos_in(sc: dict):
    for k in ("logo", "left", "right"):
        if isinstance(sc.get(k), str):
            yield sc[k]
    for c in sc.get("chips", []) or []:
        if isinstance(c, dict) and c.get("logo"):
            yield c["logo"]
    for r in sc.get("rows", []) or []:
        if isinstance(r, dict) and r.get("logo"):
            yield r["logo"]
    for ln in sc.get("lines", []) or []:
        for seg in ln:
            if seg.get("logo3d"):
                yield seg["logo3d"]


def spread(a: float, b: float, n: int) -> list[float]:
    return [round(a + (b - a) * (i + 1) / (n + 1), 2) for i in range(n)]


def _resolve_chips(data: dict, a: float, b: float, words: list[dict], idx: int) -> dict:
    """Время «нажатия» каждого чипа: слово из речи, если оно внутри окна плашки, иначе равномерно по окну."""
    chips = [dict(c) for c in data.get("chips", [])]
    real = [c for c in chips if not c.get("arrow")]
    for c in real:
        if c.get("t") is not None:          # время задано явно — слово не ищем
            continue
        t = None
        if c.get("word"):
            t = find_word(words, c["word"], c.get("after", a + 0.3))
            if t is not None and not (a + 0.3 < t < b - 0.15):
                t = None
        c["t"] = t
    missing = [c for c in real if c.get("t") is None]
    for c, t in zip(missing, spread(a + 0.9, max(a + 1.0, b - 0.5), len(missing))):
        c["t"] = t
    data["chips"] = chips
    if "n" not in data:
        data["n"] = idx
    return data


def _resolve_rows(rows, a: float, b: float, words: list[dict]):
    rows = [dict(r) for r in (rows or [])]
    for i, r in enumerate(rows):
        t = find_word(words, r["word"], a) if r.get("word") else None
        r["t"] = t if t is not None and a <= t <= b else round(min(b - 0.2, a + 0.9 + 0.35 * i), 2)
    return rows
