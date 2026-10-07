"""Конвейер монтажа рилса: дубль → чистовик → субтитры → оформление → громкость → outbox/<имя>.mp4.

    python -m integrations.montage.run check
    python -m integrations.montage.run plan <дубль> [--drop 29.6-31.4]
    python -m integrations.montage.run phrases <дубль> --work <папка>        # расшифровка по фразам: искать повторы
    python -m integrations.montage.run prepare <дубль> [--drop ОТ-ДО ...] [--name имя] [--denoise auto|on|off]   # чистовик + слова → писать спецификацию
    python -m integrations.montage.run make <дубль> --spec <spec.json> [--drop ОТ-ДО ...] [--name имя]
    python -m integrations.montage.run preview --work <папка> --spec <spec.json> --at 4.5,12.9,62   # кадры оформления за ~20 с
    python -m integrations.montage.run remake --work <папка> --spec <spec.json> [--name имя]   # правка оформления без реза

Человек в петле на двух местах: список выбросов (`--drop`) и швы (`work/seams/`). Остальное — детерминированно.
Рабочая папка — `outbox/montage/<имя>/` (внутри папки JARVIS: запись без кнопки).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import compose, config, cut, denoise, loudness, overlay, preview, render, spec as specmod, subs, words


def slug_of(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower(), flags=re.U).strip("-")
    return s or time.strftime("reel-%Y%m%d-%H%M")


def check() -> list[str]:
    return config.require_tools()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _work_dir(src, name, work) -> Path:
    work = Path(work) if work else config.OUTBOX / "montage" / slug_of(name or Path(src).stem)
    work.mkdir(parents=True, exist_ok=True)
    return work


def prepare(src, name: str | None = None, drops=(), speed: float = config.SPEED, floor_db: float = config.FLOOR_DB,
            work: Path | None = None, denoise_mode: str = "auto") -> dict:
    """Шаги 1–2: чистовик 1080×1920 и слова с таймкодами **чистовика** (work/words.json). После этого пишется спецификация:
    якоря на слова и времена берутся из words.json, а не из сырого дубля (рез сдвигает время)."""
    missing = check()
    if missing:
        raise RuntimeError("не хватает: " + ", ".join(missing))
    work = _work_dir(src, name, work)
    clip = work / "chistovik.mp4"
    summary: dict = {"work": str(work)}
    _log("0/2 очистка шума (" + denoise_mode + ")…")
    dn = denoise.run(src, work, denoise_mode)
    summary["denoise"] = dn.asdict()
    _log("   " + dn.reason)
    _log("1/2 рез по энергии звука…")
    raw = work / "chistovik.raw.mp4"
    rep = cut.build(dn.source, raw, drops=drops, speed=speed, floor_db=floor_db, seams_dir=work / "seams")
    summary["cut"] = {"floor_db": rep.floor_db, "cuts": rep.cuts, "removed_s": rep.removed_s}
    summary["source_size"] = "x".join(map(str, cut.probe_size(raw)))
    if cut.to_canvas(raw, clip):
        _log("   кадр приведён к 1080×1920")
    summary["duration_s"] = round(words.duration(clip), 2)
    _log("2/2 слова с таймкодами…")
    wl = words.transcribe_words(clip, work / "words.json")
    (work / "words.txt").write_text(" ".join(f"{w['start']:.2f}:{w['word']}" for w in wl), encoding="utf-8")
    summary["words"] = len(wl)
    (work / "prepare.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def assemble(work, spec_path, name: str | None = None, keep_frames: bool = False) -> dict:
    """Шаги 3–7 по готовому чистовику и словам: спецификация → субтитры → сцены → кадры → сборка → громкость."""
    missing = check()
    if missing:
        raise RuntimeError("не хватает: " + ", ".join(missing))
    work = Path(work)
    clip, words_json = work / "chistovik.mp4", work / "words.json"
    if not clip.exists() or not words_json.exists():
        raise RuntimeError(f"в {work} нет chistovik.mp4 и words.json — сначала `prepare` (или `make`)")
    summary: dict = {"work": str(work)}
    dur = words.duration(clip)
    summary["duration_s"] = round(dur, 2)
    wl = json.loads(words_json.read_text(encoding="utf-8"))

    _log("3/7 спецификация…")
    sp = specmod.load(spec_path)
    res = specmod.resolve(sp, wl, dur)
    if Path(spec_path).resolve() != (work / "spec.json").resolve():       # копия спецификации в рабочую папку (если автор писал её там же — не трогаем)
        (work / "spec.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")

    _log("4/7 субтитры…")
    raw = subs.make_ass(clip, work / "captions.ass")
    summary["subs_fixed_events"] = subs.finalize(raw, work / "subs.ass", res.fixes, res.context_fixes, y=sp.get("sub_y", config.SUB_Y))
    (work / "subs.txt").write_text("\n".join(f"{t:6.1f}  {x}" for t, x in subs.texts(work / "subs.ass")), encoding="utf-8")

    _log("5/7 сцены…")
    tl = overlay.build(res, work)
    if tl.get("warnings"):
        summary["safe_zone_warnings"] = tl["warnings"]
    _log("6/7 кадры анимации…")
    render.render_frames(work, dur, progress=_log)

    _log("7/7 сборка и громкость…")
    composite = work / "composite.mp4"
    compose.compose(clip, work, composite)
    final = config.OUTBOX / f"{slug_of(name or work.name)}.mp4"
    lr = loudness.normalize(composite, final)
    if not loudness.durations_match(composite, final, tol=0.06):
        raise RuntimeError("после громкости длительность разошлась больше чем на кадр-два — заморозка нарушена")
    summary["loudness"] = {"in_lufs": lr.input_i, "out_lufs": lr.out_i, "out_tp": lr.out_tp, "mode": lr.mode}
    if not lr.linear:
        summary["warning"] = "громкость в режиме dynamic (пик не помещается под −1 dBTP) — возможно «дыхание»"
    if not keep_frames:
        shutil.rmtree(work / "frames", ignore_errors=True)
    composite.unlink(missing_ok=True)
    summary["file"] = str(final)
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def make(src, spec_path, name: str | None = None, drops=(), keep_frames: bool = False, speed: float = config.SPEED,
         floor_db: float = config.FLOOR_DB, work: Path | None = None, denoise_mode: str = "auto") -> dict:
    """Всё одной командой, если спецификация уже есть (рилс по готовому образцу)."""
    work = _work_dir(src, name, work)
    prep = prepare(src, name, drops, speed, floor_db, work, denoise_mode)
    out = assemble(work, spec_path, name or work.name, keep_frames)
    out["cut"], out["source_size"], out["denoise"] = prep["cut"], prep["source_size"], prep["denoise"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="integrations.montage.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("plan"); p.add_argument("src"); p.add_argument("--drop", action="append", default=[])
    p = sub.add_parser("phrases"); p.add_argument("src"); p.add_argument("--work", required=True)
    p = sub.add_parser("prepare"); p.add_argument("src"); p.add_argument("--drop", action="append", default=[]); p.add_argument("--name"); p.add_argument("--work")
    p.add_argument("--denoise", choices=denoise.MODES, default="auto")
    p = sub.add_parser("preview"); p.add_argument("--work", required=True); p.add_argument("--spec", required=True); p.add_argument("--at", required=True)
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
            p.add_argument("--denoise", choices=denoise.MODES, default="auto")
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
        if a.cmd == "preview":
            print(preview.frames(Path(a.work), a.spec, [float(x) for x in a.at.split(",")], progress=_log))
            return 0
        if a.cmd == "prepare":
            s = prepare(a.src, a.name, a.drop, work=Path(a.work) if a.work else None, denoise_mode=a.denoise)
        elif a.cmd == "make":
            s = make(a.src, a.spec, a.name, a.drop, a.keep_frames, work=Path(a.work) if a.work else None, denoise_mode=a.denoise)
        else:
            s = assemble(Path(a.work), a.spec, a.name, a.keep_frames)
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    except (specmod.SpecError, RuntimeError, FileNotFoundError, words.AsrError) as e:
        print("ОШИБКА:", e, file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, ValueError, OSError) as e:
        # ffmpeg/ffprobe упал, spec.json не разбирается, `--work` на другом диске (relpath) — понятная ошибка вместо трейсбека
        from runtime import errorlog
        errorlog.record("montage.run", e, cmd=getattr(a, "cmd", "?"))
        print(f"ОШИБКА: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
