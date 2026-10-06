"""Сборка: чистовик + анимированный оверлей (PNG-последовательность) + субтитры сверху всего.

Раскладка кадра по окнам времени из timeline.json:
  split — спикер сдвинут вниз на SPLIT_SHIFT (под панелью сверху);
  band  — спикер сдвинут вниз на BAND_SHIFT на оранжевой полосе (место под плашку над головой, ниже шапки Instagram);
  иначе — спикер на весь кадр (полноэкранные визуалы закрывают его своим непрозрачным фоном).
Звук копируется как есть: громкость — отдельный последний шаг.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config


def _enable(windows) -> str:
    return "+".join(f"between(t,{a},{b})" for a, b in windows) or "0"


def filter_graph(tl: dict, subs_name: str = "subs.ass", fonts_dir: str = "fonts") -> str:
    dur = tl["dur"]
    bg = config.PALETTE["bg"].lstrip("#")
    fc = [
        f"color=c=0x{bg}:s=1080x1920:r={config.FPS}:d={dur + 1}[ob]",
        f"[ob][0:v]overlay=0:{config.BAND_SHIFT}:shortest=1[band]",
        f"color=c=black:s=1080x1920:r={config.FPS}:d={dur + 1}[bk]",
        f"[bk][0:v]overlay=0:{config.SPLIT_SHIFT}:shortest=1[sb]",
        f"[0:v][band]overlay=0:0:enable='{_enable(tl['band'])}'[v1]",
        f"[v1][sb]overlay=0:0:enable='{_enable(tl['split'])}'[v2]",
        "[v2][1:v]overlay=0:0:shortest=1[v3]",
        f"[v3]subtitles={subs_name}:fontsdir={fonts_dir}[out]",
    ]
    return ";".join(fc)


def compose(clip, work: Path, out, crf: int = 18) -> Path:
    """work содержит timeline.json, subs.ass, frames/. Результат — видео без финальной громкости."""
    work = Path(work)
    tl = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
    fonts = config.ASSETS / "fonts"
    # относительные пути для фильтра subtitles (двоеточие диска ломает граф), запуск из work
    rel_fonts = _rel(fonts, work)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(Path(clip).resolve()), "-framerate", str(config.FPS), "-i", "frames/%05d.png",
           "-filter_complex", filter_graph(tl, "subs.ass", rel_fonts), "-map", "[out]", "-map", "0:a", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", str(tl["dur"]),
           "-movflags", "+faststart", str(Path(out).resolve())]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("сборка ролика упала:\n" + r.stderr[-1200:])
    return Path(out)


def _rel(path: Path, start: Path) -> str:
    import os
    return os.path.relpath(path, start).replace("\\", "/")
