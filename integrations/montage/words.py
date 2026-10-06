"""Распознавание речи через Groq (whisper-large-v3): слова с таймкодами и расшифровка по фразам для поиска повторов.

Ключ — только из переменной окружения GROQ_API_KEY и только через стандартный ввод curl (в аргументах его видно в
списке процессов). Лимит Groq — 20 запросов в минуту: между фразами пауза 3,2 с, пустой ответ там, где есть звук, —
ошибка запроса, повторяем. Слова, начало которых за длительностью файла, выбрасываются сразу (распознаватель
выдумывает текст на месте тишины).
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import config

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3"
MIN_PAUSE_PHRASE = 320   # мс: фраза кончается на паузе от 320 мс
PHRASE_PAD = 0.15
PHRASE_MIN = 0.6
RATE_SLEEP = 3.2


class AsrError(RuntimeError):
    pass


def duration(path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.decode().strip())


def to_wav(src, wav, start: float | None = None, end: float | None = None) -> None:
    args = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-to", f"{end:.3f}"]
    args += ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    subprocess.run(args, check=True)


def _request(wav: Path, words: bool = True, tries: int = 4) -> dict:
    key = config.groq_key()
    if not key:
        raise AsrError("нет ключа Groq (GROQ_API_KEY или GROQ_KEY) в окружении")
    cfg = f'header = "Authorization: Bearer {key}"\n'
    cmd = ["curl", "-sS", "--max-time", "600", "--config", "-", URL, "-F", f"model={MODEL}", "-F", "language=ru",
           "-F", "response_format=verbose_json", "-F", f"file=@{wav}"]
    if words:
        cmd[-2:-2] = ["-F", "timestamp_granularities[]=word"]
    last = ""
    for _ in range(tries):
        r = subprocess.run(cmd, input=cfg.encode(), capture_output=True)
        try:
            doc = json.loads(r.stdout)
            if doc.get("text") is not None and "error" not in doc:
                return doc
            last = str(doc.get("error", doc))[:200]
        except Exception:
            last = (r.stderr or r.stdout)[:200].decode("utf-8", "replace")
        time.sleep(4)
    raise AsrError(f"Groq не ответил после {tries} попыток: {last}")


def transcribe_words(src, out_json=None) -> list[dict]:
    """Слова всего файла: [{word, start, end}]; слова за концом файла отброшены."""
    dur = duration(src)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        to_wav(src, wav)
        doc = _request(wav)
    words = [w for w in doc.get("words", []) if float(w["start"]) <= dur]
    if out_json:
        Path(out_json).write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return words


def parse_mark(text: str) -> list[tuple[float, float, int]]:
    """Окна пауз из вывода `roughcut --silence mark`: (начало, конец, длина паузы мс)."""
    wins = []
    for line in text.splitlines():
        m = re.match(r"\s*([\d.]+)\s*-\s*([\d.]+)\s+пауза (\d+) мс", line)
        if m:
            wins.append((float(m[1]), float(m[2]), int(m[3])))
    return wins


def split_phrases(wins, dur: float) -> list[list[float]]:
    """Фраза = речь между окнами пауз ≥ 320 мс; фраза короче 600 мс присоединяется к соседней."""
    cuts = [w for w in wins if w[2] >= MIN_PAUSE_PHRASE]
    segs, start = [], 0.0
    for a, b, _ in cuts:
        if a - start > 0.05:
            segs.append([start, a])
        start = b
    if dur - start > 0.05:
        segs.append([start, dur])
    merged: list[list[float]] = []
    for s in segs:
        if merged and (s[1] - s[0] < PHRASE_MIN or merged[-1][1] - merged[-1][0] < PHRASE_MIN):
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return merged


def transcribe_phrases(src, mark_text: str, out_json=None, progress=print) -> list[dict]:
    """Каждая фраза — отдельным запросом (цельная расшифровка прячет повторы: декодер глотает повтор фразы)."""
    dur = duration(src)
    res = []
    for i, (a, b) in enumerate(split_phrases(parse_mark(mark_text), dur)):
        A, B = max(0.0, a - PHRASE_PAD), min(dur, b + PHRASE_PAD)
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "p.wav"
            to_wav(src, wav, A, B)
            doc = None
            for _ in range(3):
                doc = _request(wav)
                time.sleep(RATE_SLEEP)
                if (doc.get("text") or "").strip():
                    break
        text = (doc.get("text") or "").strip()
        words = [[round(w["start"] + A, 2), round(w["end"] + A, 2), w["word"]] for w in doc.get("words", []) if w["start"] <= B - A]
        res.append({"i": i, "start": round(A, 2), "end": round(B, 2), "text": text,
                    "ends_sentence": text.endswith((".", "!", "?")) and not text.endswith(("..", "…")), "words": words})
        progress(f"{i:2d} {A:6.2f}-{B:6.2f} {text}")
    if out_json:
        Path(out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
