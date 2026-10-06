"""Громкость: −14 LUFS, пик −1 dBTP, в два прохода (замер → исправление). Последним шагом, на файле, который уедет зрителю.

Порядок «рез → проверка речи → ускорение → оформление → громкость» обязателен: после оформления HyperFrames/Chrome
громкость уезжала на 1 дБ, поэтому меряем и приводим именно финальный файл. `linear=true` молча откатывается в
динамический режим, если пик не помещается под −1 dBTP («дыхание» громкости) — режим проверяется и возвращается.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from . import config


@dataclass
class LoudResult:
    input_i: float
    input_tp: float
    input_lra: float
    mode: str
    out_i: float | None = None
    out_tp: float | None = None

    @property
    def linear(self) -> bool:
        return self.mode == "linear"


def _json(stderr: str, last: bool = False) -> dict:
    blocks = re.findall(r"\{.*?\}", stderr, re.S)
    if not blocks:
        raise RuntimeError("ffmpeg не вернул замер громкости:\n" + stderr[-600:])
    return json.loads(blocks[-1] if last else blocks[0])


def measure(src, chain: str = config.LOUD_CHAIN) -> dict:
    af = f"{chain},loudnorm=I={config.LOUD_I}:TP={config.LOUD_TP}:print_format=json" if chain else f"loudnorm=I={config.LOUD_I}:TP={config.LOUD_TP}:print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", af, "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8")
    return _json(r.stderr)


def second_pass_filter(m: dict, chain: str = config.LOUD_CHAIN) -> str:
    ln = (f"loudnorm=I={config.LOUD_I}:TP={config.LOUD_TP}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json")
    return f"{chain},{ln}" if chain else ln


def crest_limit() -> float:
    """Сколько дБ пик может быть выше средней громкости, чтобы линейный режим влез: цель пика − цель громкости (13 дБ)."""
    return config.LOUD_TP - config.LOUD_I


def limiter_for(input_i: float, input_tp: float, margin: float = 0.8) -> float | None:
    """Потолок лимитера (линейная амплитуда), при котором пик после подъёма до цели уложится под −1 dBTP.
    None — пик и так укладывается, либо нужен потолок ниже допустимого для alimiter (0,0625): тогда режим останется dynamic."""
    if input_tp - input_i <= crest_limit() - 0.3:
        return None
    lin = 10 ** ((input_i + crest_limit() - margin) / 20)
    return round(lin, 4) if lin >= 0.0625 else None


def fit_peaks(src, chain: str, m: dict) -> tuple[str, dict]:
    """Тихая запись с большим запасом по пику не влезает в linear: подрезаем пики ровно настолько, насколько нужно, и меряем заново."""
    lin = limiter_for(float(m["input_i"]), float(m["input_tp"]))
    if lin is None:
        return chain, m
    chain2 = f"{chain},alimiter=limit={lin}:attack=3:release=60:level=disabled"
    return chain2, measure(src, chain2)


def normalize(src, out, chain: str = config.LOUD_CHAIN) -> LoudResult:
    """Видео не перекодируется (-c:v copy); звук AAC 128k/48 кГц; -shortest, иначе AAC удлиняет файл на 100 мс."""
    m = measure(src, chain)
    chain, m = fit_peaks(src, chain, m)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-c:v", "copy", "-af", second_pass_filter(m, chain), "-c:a", "aac",
                        "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("громкость не применилась:\n" + r.stderr[-800:])
    done = _json(r.stderr, last=True)
    res = LoudResult(float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"]), done.get("normalization_type", "?"))
    after = measure(out, chain="")
    res.out_i, res.out_tp = float(after["input_i"]), float(after["input_tp"])
    return res


def durations_match(a, b, tol: float = 0.05) -> bool:
    """Заморозка: длительность до и после шага не должна меняться больше чем на кадр-два."""
    def d(p):
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).decode())
    return abs(d(a) - d(b)) <= tol
