"""Субтитры: ASS из расшифровки чистовика (captions.py автора) → правка слов распознавателя → положение и обводка.

Текст берётся из распознавания и не придумывается: правятся отдельные слова (одно слово → одно слово, число слов и
тайминги подсветки не меняются). Замены — из `data/word_fixes.json` (типовые ошибки на её темах), из спецификации
ролика (`fixes`, `context_fixes`). Контекстная замена «предыдущее|слово»: нужна, когда одно и то же короткое слово
(«к») правится только в одном месте.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from . import config

CAPTIONS = config.VENDOR / "captions.py"
TAG = re.compile(r"\{[^}]*\}")
EDGE = ".,!?:;«»\"'()—-"


def default_fixes() -> dict:
    p = config.DATA / "word_fixes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def make_ass(clip, out_ass, max_chars: int = config.SUB_MAX_CHARS) -> Path:
    """captions.py --ass-only: строки ≤ max_chars, подсветка звучащего слова. Возвращает путь к .ass."""
    out_ass = Path(out_ass)
    tmp_video = out_ass.with_suffix(".mp4")      # captions.py кладёт .ass рядом с «выходом» и ничего не жжёт
    cmd = [sys.executable, str(CAPTIONS), str(clip), "--preset", config.SUB_PRESET, "--fontsdir", str(config.ASSETS / "fonts"),
           "--font", config.SUB_FONT, "--highlight", config.SUB_HIGHLIGHT, "--max-chars", str(max_chars), "--ass-only", "-o", str(tmp_video)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("captions.py упал:\n" + (r.stdout + r.stderr)[-800:])
    if not out_ass.exists():
        raise RuntimeError(f"captions.py не создал {out_ass}")
    return out_ass


def fix_tokens(text: str, fixes: dict, context: dict | None = None) -> str:
    """Правка слов одного события Dialogue. Знаки и теги подсветки сохраняются."""
    context = context or {}
    toks = text.split(" ")
    prev = ""
    for i, t in enumerate(toks):
        plain = TAG.sub("", t).strip()
        core = plain.strip(EDGE)
        key_ctx = f"{prev}|{core.lower()}"
        if plain and plain in fixes:                 # ключ со знаками («почты,») — точное совпадение
            toks[i] = t.replace(plain, fixes[plain], 1)
        else:
            new_core = None
            if key_ctx in context:
                new_core = context[key_ctx]
            elif core in fixes:
                new_core = fixes[core]
            elif core.lower() in fixes:
                new_core = fixes[core.lower()]
            if new_core is not None and core:
                toks[i] = t.replace(core, new_core, 1)
        prev = core.lower()                          # контекст — слова распознавателя, до правок
    return " ".join(toks)


def finalize(ass_in, ass_out, fixes: dict | None = None, context: dict | None = None, y: int = config.SUB_Y) -> int:
    """Применяет правки и ставит каждому событию положение (нижний край строки на y) и плотную обводку.
    Возвращает число изменённых событий."""
    allfix = {**default_fixes(), **(fixes or {})}
    n = 0
    out = []
    for line in Path(ass_in).read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("Dialogue"):
            head = line.split(",", 9)
            fixed = fix_tokens(head[9], allfix, context)
            n += fixed != head[9]
            head[9] = "{\\an2\\pos(540,%d)%s}" % (y, config.SUB_OUTLINE) + fixed
            line = ",".join(head)
        out.append(line)
    Path(ass_out).write_text("".join(out), encoding="utf-8")
    return n


def texts(ass_path) -> list[tuple[float, str]]:
    """Читаемый список (время начала, текст строки) — показать владелице на правку слов."""
    res, last = [], None
    for line in Path(ass_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue"):
            p = line.split(",", 9)
            plain = TAG.sub("", p[9]).strip()
            if plain != last:
                h, m, s = p[1].split(":")
                res.append((round(int(h) * 3600 + int(m) * 60 + float(s), 1), plain))
                last = plain
    return res
