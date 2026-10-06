"""Покадровый рендер оверлея: Node + puppeteer-core + Edge/Chrome. Кадры — прозрачные PNG 1080×1920."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import config

MJS = config.TEMPLATES / "render.mjs"


def env_for(html: Path, frames: Path, dur: float, fps: int = config.FPS, t0=None, t1=None) -> dict:
    env = dict(os.environ)
    env.update(MONTAGE_PUPPETEER=config.find_puppeteer(), MONTAGE_BROWSER=config.find_browser(), MONTAGE_HTML=str(Path(html).resolve()),
               MONTAGE_FRAMES=str(Path(frames).resolve()), MONTAGE_FPS=str(fps), MONTAGE_DUR=str(dur))
    if t0 is not None:
        env["MONTAGE_T0"] = str(t0)
    if t1 is not None:
        env["MONTAGE_T1"] = str(t1)
    return env


def render_frames(work: Path, dur: float, fps: int = config.FPS, t0=None, t1=None, progress=print) -> Path:
    """work/overlay.html → work/frames/00001.png … Возвращает папку с кадрами."""
    work = Path(work)
    frames = work / "frames"
    if frames.exists() and t0 is None:
        shutil.rmtree(frames)
    proc = subprocess.Popen(["node", str(MJS)], env=env_for(work / "overlay.html", frames, dur, fps, t0, t1), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    tail = []
    for line in proc.stdout:
        tail.append(line.rstrip())
        if line.startswith(("кадр", "готово")):
            progress(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError("рендер кадров упал:\n" + "\n".join(tail[-12:]))
    return frames
