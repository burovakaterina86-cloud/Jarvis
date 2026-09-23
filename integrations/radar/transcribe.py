"""Шаги 5-6 метода: видео → звук (ffmpeg) → расшифровка Groq Whisper.

Apify отдаёт в рилсе и `videoUrl`, и отдельный `audioUrl`. Берём звук: Instagram
часто отдаёт по `videoUrl` DASH-дорожку без звука (VP9, одна видеодорожка), и тогда
ffmpeg вытаскивать нечего — это вскрыл первый живой прогон 2026-09-23. `videoUrl` —
только запасной путь, если `audioUrl` нет. Скачивание и извлечение звука
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
    failed: dict[str, str] = {}
    for reel in reels:
        code = reel["shortCode"]
        src = reel.get("audioUrl") or reel["videoUrl"]
        media_path = download(src, out_dir / f"{code}.media")
        audio_path = out_dir / f"{code}.opus"
        try:
            extract_audio(media_path, audio_path)
        except subprocess.CalledProcessError as exc:
            # Один битый ролик не должен стоить всего прогона: помечаем и идём дальше.
            failed[code] = f"ffmpeg: код {exc.returncode}"
            media_path.unlink(missing_ok=True)
            continue
        text = groq_client.transcribe(audio_path)
        transcripts[code] = text
        (out_dir / f"{code}.txt").write_text(text, encoding="utf-8")
        media_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)
    if failed:
        lines = ["# Не расшифрованы", ""] + [f"- {c} — {why}" for c, why in failed.items()]
        (out_dir / "failed.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        if not transcripts:
            # Не вышло ни одного — это уже не случайный ролик, а системная поломка.
            raise RuntimeError(f"ни один ролик не расшифрован ({len(failed)} из {len(reels)})")
    return transcripts
