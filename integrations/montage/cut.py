"""Первый заход: чистовик из сырого дубля (вендорный roughcut.py автора + порог для её записи)."""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config

ROUGHCUT = config.VENDOR / "roughcut.py"


@dataclass
class CutReport:
    text: str
    floor_db: float | None
    cuts: int | None
    removed_s: float | None
    result_s: float | None
    ok: bool

    def summary(self) -> str:
        return self.text.strip()


def _env(floor_db: float) -> dict:
    return config.child_env({"ROUGHCUT_FLOOR_DB": str(floor_db), "PYTHONIOENCODING": "utf-8"})


def _run(src, extra: list[str], floor_db: float, timeout: int = 1800) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(ROUGHCUT), str(src), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=_env(floor_db), timeout=timeout)


def parse_report(text: str, ok: bool = True) -> CutReport:
    def num(pat):
        m = re.search(pat, text)
        return float(m.group(1)) if m else None
    cuts = re.search(r"резов\s+(\d+)", text)
    return CutReport(text, num(r"порог тишины\s+(-?[\d.]+)"), int(cuts.group(1)) if cuts else None,
                     num(r"убрано\s+([\d.]+)"), num(r"станет\s+([\d.]+)"), ok)


def plan(src, drops=(), floor_db: float = config.FLOOR_DB) -> CutReport:
    """План реза без сборки (--dry-run): порог, число пауз и резов, аудит тишины."""
    r = _run(src, ["--dry-run", *_drop_args(drops)], floor_db)
    return parse_report(r.stdout + r.stderr, r.returncode == 0)


def mark(src, floor_db: float = config.FLOOR_DB) -> str:
    """Окна пауз (для расшифровки по фразам и поиска повторов). Возвращает текст вывода."""
    r = _run(src, ["--silence", "mark", "--dry-run"], floor_db)
    if r.returncode != 0:
        raise RuntimeError("roughcut mark упал:\n" + (r.stdout + r.stderr)[-800:])
    return r.stdout


def _drop_args(drops) -> list[str]:
    out: list[str] = []
    for d in drops:
        out += ["--drop", d if isinstance(d, str) else f"{d[0]}-{d[1]}"]
    return out


def build(src, out, drops=(), speed: float = config.SPEED, floor_db: float = config.FLOOR_DB, seams_dir=None) -> CutReport:
    """Чистовик: рез по энергии звука → проверка речи → ускорение (порядок обязателен). Упал аудит — исключение."""
    extra = ["-o", str(out), "--speed", str(speed), *_drop_args(drops)]
    if seams_dir:
        extra += ["--seams", str(seams_dir)]
    r = _run(src, extra, floor_db)
    text = r.stdout + r.stderr
    if r.returncode != 0:
        raise RuntimeError("первый заход не прошёл проверку (аудит по энергии или речь) — не обходим флагами:\n" + text[-1200:])
    return parse_report(text)


CANVAS = (1080, 1920)


def probe_size(path) -> tuple[int, int]:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                   "-of", "csv=p=0", str(path)]).decode().strip().split(",")
    return int(out[0]), int(out[1])


def canvas_filter(w: int, h: int) -> str | None:
    """Фильтр приведения к 1080×1920 (вертикаль 9:16): масштаб «чтобы закрыть кадр» и обрезка лишнего. None — уже подходит."""
    if (w, h) == CANVAS:
        return None
    if h <= w:
        raise RuntimeError(f"дубль {w}×{h} не вертикальный — рилс снимается вертикально (9:16)")
    return f"scale={CANVAS[0]}:{CANVAS[1]}:force_original_aspect_ratio=increase,crop={CANVAS[0]}:{CANVAS[1]},setsar=1"


def to_canvas(src, dst) -> bool:
    """Сырой чистовик → work/chistovik.mp4 нужного размера. Звук копируется, длительность не меняется. True — перекодировали."""
    src, dst = Path(src), Path(dst)
    flt = canvas_filter(*probe_size(src))
    if flt is None:
        src.replace(dst)
        return False
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", flt, "-c:v", "libx264", "-crf", "14", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dst)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("не удалось привести кадр к 1080×1920:\n" + r.stderr[-600:])
    src.unlink()
    return True
