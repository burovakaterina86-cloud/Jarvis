"""Очистка шума в дубле: необязательный шаг ДО реза, с проверкой речи и откатом.

Её выбор 2026-10-06 после прослушивания трёх вариантов на дубле «монтаж»: №2 — мягкий `afftdn` (шум −7 дБ, голос над фоном
19,7 → 26,4 дБ). Сильный `anlmdn` дал запас 38,8 дБ, но потерял слово и звучит «под водой» — не берём.

Режимы: `auto` (по умолчанию) — чистим, только если голос над фоном меньше порога `config.DENOISE_AUTO_BELOW_DB`
(записи про 10 систем с запасом 28,7 дБ чистка не нужна); `on` — всегда; `off` — никогда.
Правило автора: любой шаг над звуком проверяется повторным распознаванием. Не прошёл (слова пропали или речь разошлась) —
исходный звук остаётся, причина — в отчёте; обходить проверку флагами нельзя.
"""
from __future__ import annotations

import array
import difflib
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import config, words as wordsmod

MODES = ("auto", "on", "off")


@dataclass
class DenoiseReport:
    mode: str
    applied: bool
    reason: str
    headroom_before: float | None = None
    headroom_after: float | None = None
    similarity: float | None = None
    changed_words: list[str] = field(default_factory=list)
    source: Path | None = None        # что идёт в рез: очищенный файл или исходный

    def asdict(self) -> dict:
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}


def headroom_db(path) -> float:
    """Голос над фоном: p75 − p10 огибающей (окно 20 мс, шаг 10 мс) — как в замерах журнала (J12)."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    s = array.array("h")
    s.frombytes(raw)
    win, hop, env = 320, 160, []
    for i in range(0, len(s) - win, hop):
        rms = math.sqrt(sum(v * v for v in s[i:i + win]) / win)
        env.append(20 * math.log10(max(1e-9, rms) / 32768))
    env.sort()
    n = len(env)
    return env[int(0.75 * n)] - env[int(0.10 * n)]


def should_clean(mode: str, headroom: float) -> tuple[bool, str]:
    if mode not in MODES:
        raise ValueError(f"режим очистки: {', '.join(MODES)}")
    if mode == "off":
        return False, "выключена"
    if mode == "on":
        return True, "включена явно"
    if headroom < config.DENOISE_AUTO_BELOW_DB:
        return True, f"голос над фоном {headroom:.1f} дБ < {config.DENOISE_AUTO_BELOW_DB:g} дБ — шумная запись"
    return False, f"голос над фоном {headroom:.1f} дБ — запись чистая, очистка не нужна"


def norm_tokens(ws) -> list[str]:
    return re.findall(r"\w+", " ".join(w["word"] if isinstance(w, dict) else w for w in ws).lower().replace("ё", "е"))


def speech_ok(before: list[str], after: list[str]) -> tuple[bool, float, list[str]]:
    """Речь цела: совпадение не ниже порога и пропало не больше допустимого числа слов (число и слово-число — не потеря: журнал J06)."""
    sm = difflib.SequenceMatcher(None, before, after)
    changed = [w for tag, i1, i2, _, _ in sm.get_opcodes() if tag in ("delete", "replace") for w in before[i1:i2]]
    lost = len(before) - len(after)
    # потеря слов — отказ всегда; а на коротком отрывке одно-два иначе распознанных слова не должны ронять процент (ratio)
    ok = lost <= config.DENOISE_MAX_LOST_WORDS and (sm.ratio() >= config.DENOISE_MIN_SIMILARITY or len(changed) <= config.DENOISE_MAX_CHANGED_WORDS)
    return ok, sm.ratio(), changed


def clean_audio(src, dst) -> Path:
    """Видео без перекодирования, звук — мягкий afftdn и AAC 256k (звук потом режется и меряется как обычный)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "copy", "-af", config.DENOISE_FILTER, "-c:a", "aac",
                        "-b:a", "256k", str(dst)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("очистка шума не применилась:\n" + r.stderr[-600:])
    return Path(dst)


def run(src, work, mode: str = "auto", transcribe=wordsmod.transcribe_words) -> DenoiseReport:
    """Возвращает отчёт; `report.source` — файл для реза (очищенный или исходный). Распознавание подменяется в тестах."""
    src, work = Path(src), Path(work)
    h0 = headroom_db(src)
    go, why = should_clean(mode, h0)
    if not go:
        return DenoiseReport(mode, False, why, h0, None, None, [], src)
    cleaned = clean_audio(src, work / "denoised.mov")
    before, after = norm_tokens(transcribe(src)), norm_tokens(transcribe(cleaned))
    ok, ratio, changed = speech_ok(before, after)
    h1 = headroom_db(cleaned)
    if not ok:
        return DenoiseReport(mode, False, f"очистка отменена: речь разошлась (совпадение {ratio:.3f}, слов {len(before)}→{len(after)}); остался исходный звук",
                             h0, h1, ratio, changed, src)
    return DenoiseReport(mode, True, why, h0, h1, ratio, changed, cleaned)
