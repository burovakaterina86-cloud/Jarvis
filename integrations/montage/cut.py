"""Первый заход: чистовик из сырого дубля (вендорный roughcut.py автора + порог для её записи)."""
from __future__ import annotations

import os
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
    env = dict(os.environ)
    env["ROUGHCUT_FLOOR_DB"] = str(floor_db)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


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
