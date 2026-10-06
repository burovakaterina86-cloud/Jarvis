"""Конвейер монтажа рилса: дубль → чистовик → субтитры → оформление → громкость → outbox/<имя>.mp4.

    python -m integrations.montage.run check
    python -m integrations.montage.run plan <дубль> [--drop 29.6-31.4]
    python -m integrations.montage.run phrases <дубль> --work <папка>        # расшифровка по фразам: искать повторы
    python -m integrations.montage.run make <дубль> --spec <spec.json> [--drop ОТ-ДО ...] [--name имя]
    python -m integrations.montage.run remake --work <папка> --spec <spec.json> [--name имя]   # правка оформления без реза

Человек в петле на двух местах: список выбросов (`--drop`) и швы (`work/seams/`). Остальное — детерминированно.
Рабочая папка — `outbox/montage/<имя>/` (внутри папки JARVIS: запись без кнопки).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from . import compose, config, cut, loudness, overlay, render, spec as specmod, subs, words


def slug_of(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower(), flags=re.U).strip("-")
    return s or time.strftime("reel-%Y%m%d-%H%M")


def check() -> list[str]:
    return config.require_tools()


def _log(msg: str) -> None:
    print(msg, flush=True)


def make(src, spec_path, name: str | None = None, drops=(), keep_frames: bool = False, speed: float = config.SPEED,
         floor_db: float = config.FLOOR_DB, work: Path | None = None, redo_cut: bool = True) -> dict:
    missing = check()
    if missing:
        raise RuntimeError("не хватает: " + ", ".join(missing))
    work = Path(work) if work else config.OUTBOX / "montage" / slug_of(name or Path(src).stem)
    work.mkdir(parents=True, exist_ok=True)
    clip, words_json = work / "chistovik.mp4", work / "words.json"
    summary: dict = {"work": str(work)}

    # 1. первый заход
    if redo_cut or not clip.exists():
        _log("1/7 рез по энергии звука…")
        rep = cut.build(src, clip, drops=drops, speed=speed, floor_db=floor_db, seams_dir=work / "seams")
        summary["cut"] = {"floor_db": rep.floor_db, "cuts": rep.cuts, "removed_s": rep.removed_s}
    dur = words.duration(clip)
    summary["duration_s"] = round(dur, 2)

    # 2. слова чистовика с таймкодами
    if redo_cut or not words_json.exists():
        _log("2/7 слова с таймкодами…")
        words.transcribe_words(clip, words_json)
    wl = json.loads(words_json.read_text(encoding="utf-8"))

    # 3. спецификация → якоря на слова
    _log("3/7 спецификация…")
    sp = specmod.load(spec_path)
    res = specmod.resolve(sp, wl, dur)
    (work / "spec.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")

    # 4. субтитры
    _log("4/7 субтитры…")
    raw = subs.make_ass(clip, work / "captions.ass")
    changed = subs.finalize(raw, work / "subs.ass", res.fixes, res.context_fixes, y=sp.get("sub_y", config.SUB_Y))
    summary["subs_fixed_events"] = changed
    (work / "subs.txt").write_text("\n".join(f"{t:6.1f}  {x}" for t, x in subs.texts(work / "subs.ass")), encoding="utf-8")

    # 5. сцены + 6. кадры
    _log("5/7 сцены…")
    overlay.build(res, work)
    _log("6/7 кадры анимации…")
    render.render_frames(work, dur, progress=_log)

    # 7. сборка + громкость
    _log("7/7 сборка и громкость…")
    composite = work / "composite.mp4"
    compose.compose(clip, work, composite)
    out_name = slug_of(name or Path(src).stem)
    final = config.OUTBOX / f"{out_name}.mp4"
    lr = loudness.normalize(composite, final)
    if not loudness.durations_match(composite, final, tol=0.06):
        raise RuntimeError("после громкости длительность разошлась больше чем на кадр-два — заморозка нарушена")
    summary["loudness"] = {"in_lufs": lr.input_i, "out_lufs": lr.out_i, "out_tp": lr.out_tp, "mode": lr.mode}
    if not lr.linear:
        summary["warning"] = "громкость в режиме dynamic (пик не помещается под −1 dBTP) — возможно «дыхание»"
    if not keep_frames:
        shutil.rmtree(work / "frames", ignore_errors=True)
    summary["file"] = str(final)
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="integrations.montage.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("plan"); p.add_argument("src"); p.add_argument("--drop", action="append", default=[])
    p = sub.add_parser("phrases"); p.add_argument("src"); p.add_argument("--work", required=True)
    for nm in ("make", "remake"):
        p = sub.add_parser(nm)
        if nm == "make":
            p.add_argument("src")
            p.add_argument("--drop", action="append", default=[])
        else:
            p.add_argument("--work", required=True)
        p.add_argument("--spec", required=True)
        p.add_argument("--name")
        p.add_argument("--keep-frames", action="store_true")
        if nm == "make":
            p.add_argument("--work")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            miss = check()
            print("всё на месте" if not miss else "не хватает: " + ", ".join(miss))
            return 0 if not miss else 1
        if a.cmd == "plan":
            print(cut.plan(a.src, a.drop).summary())
            return 0
        if a.cmd == "phrases":
            work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
            mark = cut.mark(a.src)
            (work / "mark.txt").write_text(mark, encoding="utf-8")
            words.transcribe_phrases(a.src, mark, work / "phrases.json")
            return 0
        if a.cmd == "make":
            s = make(a.src, a.spec, a.name, a.drop, a.keep_frames, work=Path(a.work) if a.work else None)
        else:
            s = make(None, a.spec, a.name, (), a.keep_frames, work=Path(a.work), redo_cut=False)
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    except (specmod.SpecError, RuntimeError, FileNotFoundError, words.AsrError) as e:
        print("ОШИБКА:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
