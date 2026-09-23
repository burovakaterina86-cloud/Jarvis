"""Шаги 5-6 метода: видео → звук (ffmpeg) → расшифровка Groq Whisper.

Apify уже отдаёт `videoUrl` в самом рилсе — отдельного шага «медиа по коду»
(как в HikerAPI-варианте upstream) не нужно. Скачивание и извлечение звука
вынесены в подменяемые функции: тесты проверяют оркестрацию на фейковых
клиентах и фейковых download/extract, не гоняют настоящий ffmpeg и сеть.
"""
from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

Downloader = Callable[[str, Path], Path]
AudioExtractor = Callable[[Path, Path], Path]


class GroqClient(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


def default_download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)  # nosec - публичный videoUrl из Apify
    return dest


def default_extract_audio(video_path: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libopus", "-b:a", "64k",
         str(dest)],
        check=True, capture_output=True,
    )
    return dest


def transcribe_top(groq_client: GroqClient, reels: list[dict[str, Any]], out_dir: Path,
                    download: Downloader | None = None,
                    extract_audio: AudioExtractor | None = None) -> dict[str, str]:
    """Для каждого рилса: `videoUrl` → видео → звук → текст. Возвращает `{shortCode: transcript}`.

    Успех транскрипции проверяется тем, что `groq_client.transcribe` не бросил
    исключение (реальный клиент бросает его при HTTP-коде не 200) — не grep по тексту.

    `download`/`extract_audio` без явного значения берутся из модуля по имени в
    момент вызова (не как значение по умолчанию параметра) — так тест может
    подменить `transcribe.default_download` через `monkeypatch.setattr` и это
    сработает даже без прямой передачи аргумента.
    """
    download = download or default_download
    extract_audio = extract_audio or default_extract_audio
    out_dir.mkdir(parents=True, exist_ok=True)
    transcripts: dict[str, str] = {}
    for reel in reels:
        code = reel["shortCode"]
        video_path = download(reel["videoUrl"], out_dir / f"{code}.mp4")
        audio_path = extract_audio(video_path, out_dir / f"{code}.opus")
        text = groq_client.transcribe(audio_path)
        transcripts[code] = text
        (out_dir / f"{code}.txt").write_text(text, encoding="utf-8")
        video_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)
    return transcripts
