"""Распознавание голосовых: faster-whisper локально, русский, VAD.

Модель грузится лениво и один раз (`JARVIS_WHISPER_MODEL`, по умолчанию `small`, int8/CPU).
ogg от Telegram декодируется встроенным в faster-whisper PyAV — внешний ffmpeg не нужен.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("jarvis.voice")

DEFAULT_MODEL = "small"
LANGUAGE = "ru"

_model = None
_model_lock = threading.Lock()


def model_name() -> str:
    return os.environ.get("JARVIS_WHISPER_MODEL", "").strip() or DEFAULT_MODEL


def get_model():
    """Ленивая загрузка модели: первый голосовой ждёт, дальше — мгновенно."""
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel  # импорт внутри: тесты модель не грузят
            name = model_name()
            log.info("загружаю модель распознавания %s", name)
            _model = WhisperModel(name, device="cpu", compute_type="int8")
        return _model


def _whisper(path: Path) -> str:
    segments, _info = get_model().transcribe(str(path), language=LANGUAGE, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments)


def transcribe(path: str | Path, transcriber=None) -> str | None:
    """Текст голосового или None, если распознать не удалось (пустой файл, сбой, тишина)."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        log.warning("голосовое не найдено или пустое: %s", path.name)
        return None
    try:
        text = (transcriber or _whisper)(path)
    except Exception as exc:  # noqa: BLE001 — владелице важен отказ, а не трассировка
        log.warning("распознавание не удалось: %s", type(exc).__name__, exc_info=True)
        return None
    text = (text or "").strip()
    return text or None
