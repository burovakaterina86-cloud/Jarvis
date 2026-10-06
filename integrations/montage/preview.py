"""Быстрый просмотр оформления: кадры на выбранных секундах без шестиминутной сборки (≈ 20 секунд).

Нужен для правила «новое оформление — сначала на выбор» и для проверки своих сцен `custom`: JARVIS присылает ей
кадры, она говорит «да» или что поправить, и только потом идёт полная сборка. Субтитры в просмотр не входят.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config, overlay, render
from . import spec as specmod


def _zone(tl: dict, t: float) -> str:
    for zone in ("split", "band", "full"):
        if any(a <= t < b for a, b in tl[zone]):
            return zone
    return "plain"


def _sh(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("просмотр не собрался:\n" + r.stderr[-800:])


def frames(work, spec_path, times, progress=lambda m: None) -> Path:
    """Кадры оформления на секундах `times` → work/preview/<t>.png и лист work/preview.png. Возвращает путь к листу."""
    work = Path(work)
    clip, words_json = work / "chistovik.mp4", work / "words.json"
    if not clip.exists() or not words_json.exists():
        raise RuntimeError(f"в {work} нет chistovik.mp4 и words.json — сначала `make` (или `phrases` + рез)")
    from . import words as wordsmod
    dur = wordsmod.duration(clip)
    res = specmod.resolve(specmod.load(spec_path), json.loads(words_json.read_text(encoding="utf-8")), dur)
    pv = work / "preview"
    pv.mkdir(exist_ok=True)
    tl = overlay.build(res, pv)
    if tl.get("warnings"):
        progress("за безопасной зоной: " + "; ".join(tl["warnings"]))
    outs = []
    for t in times:
        k = round(t * config.FPS)
        render.render_frames(pv, dur, t0=k / config.FPS, t1=(k + 1) / config.FPS, progress=progress)
        ov = pv / "frames" / f"{k + 1:05d}.png"
        base = pv / f"base_{k}.png"
        _sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(clip), "-frames:v", "1", str(base)])
        zone = _zone(tl, t)
        out = pv / f"t{str(t).replace('.', '_')}.png"
        bg = config.PALETTE["bg"].lstrip("#")
        if zone == "split":
            fc = f"color=c=black:s=1080x1920[bk];[bk][0:v]overlay=0:{config.SPLIT_SHIFT}[b];[b][1:v]overlay=0:0"
        elif zone == "band":
            fc = f"color=c=0x{bg}:s=1080x1920[bk];[bk][0:v]overlay=0:{config.BAND_SHIFT}[b];[b][1:v]overlay=0:0"
        else:
            fc = "[0:v][1:v]overlay=0:0"
        _sh(["ffmpeg", "-v", "error", "-y", "-i", str(base), "-i", str(ov), "-filter_complex", fc, "-frames:v", "1", str(out)])
        outs.append(out)
    sheet = work / "preview.png"
    n = len(outs)
    args = ["ffmpeg", "-v", "error", "-y"]
    for o in outs:
        args += ["-i", str(o)]
    chain = "".join(f"[{i}:v]scale=360:-1[s{i}];" for i in range(n)) + "".join(f"[s{i}]" for i in range(n)) + f"hstack=inputs={n}" if n > 1 else "[0:v]scale=360:-1"
    _sh(args + ["-filter_complex", chain, "-frames:v", "1", str(sheet)])
    return sheet
