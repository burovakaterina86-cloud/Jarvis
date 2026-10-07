"""Шаги 5-6 метода: видео → звук (ffmpeg) → расшифровка Groq Whisper.

Apify отдаёт в рилсе и `videoUrl`, и отдельный `audioUrl`. Берём звук: Instagram
часто отдаёт по `videoUrl` DASH-дорожку без звука (VP9, одна видеодорожка), и тогда
ffmpeg вытаскивать нечего — это вскрыл первый живой прогон 2026-09-23. `videoUrl` —
только запасной путь, если `audioUrl` нет. Скачивание и извлечение звука
вынесены в подменяемые функции: тесты проверяют оркестрацию на фейковых
клиентах и фейковых download/extract, не гоняют настоящий ffmpeg и сеть.
"""
from __future__ import annotations

import re
import subprocess
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Callable, Protocol

Downloader = Callable[[str, Path], Path]
AudioExtractor = Callable[[Path, Path], Path]


class GroqClient(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


DOWNLOAD_HOSTS = ("cdninstagram.com", "fbcdn.net", "instagram.com", "apify.com", "apifyusercontent.com")
DOWNLOAD_TIMEOUT_SEC = 60
MAX_MEDIA_BYTES = 300 * 1024 * 1024
FFMPEG_TIMEOUT_SEC = 300
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def check_media_url(url: str) -> None:
    """Адрес ролика приходит из ответа Apify, то есть от третьей стороны: только https и только хосты Instagram и
    Apify (граница по точке: `evilcdninstagram.com` не подходит). `file://` скопировал бы локальный файл, а звук
    ушёл бы в Groq."""
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not any(host == d or host.endswith("." + d) for d in DOWNLOAD_HOSTS):
        raise ValueError(f"адрес ролика не из Instagram/Apify: {host or url[:40]}")


def default_download(url: str, dest: Path) -> Path:
    check_media_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SEC) as resp, open(dest, "wb") as out:  # nosec - хост проверен
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MEDIA_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError("ролик больше 300 МБ")
            out.write(chunk)
    return dest


def default_extract_audio(video_path: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libopus", "-b:a", "64k",
         str(dest)],
        check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_SEC,
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
        code = str(reel.get("shortCode") or "")
        if not _CODE_RE.match(code):     # код идёт в имя файла: пути вроде «../x» отсекаем
            failed[code[:40] or "?"] = "некорректный shortCode"
            continue
        src = reel.get("audioUrl") or reel.get("videoUrl")
        media_path = out_dir / f"{code}.media"
        audio_path = out_dir / f"{code}.opus"
        # Один ролик не должен стоить всего прогона (Apify уже оплачен): любой сбой этого ролика — в failed.md.
        try:
            if not src:
                raise ValueError("нет ссылки на ролик")
            media_path = download(src, media_path)
            extract_audio(media_path, audio_path)
            text = groq_client.transcribe(audio_path)
        except subprocess.CalledProcessError as exc:
            failed[code] = f"ffmpeg: код {exc.returncode}"
            continue
        except Exception as exc:  # noqa: BLE001
            failed[code] = f"{type(exc).__name__}: {str(exc)[:80]}"
            continue
        finally:   # хвосты `.media`/`.opus` не оставляем ни при успехе, ни при сбое
            media_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
        transcripts[code] = text
        (out_dir / f"{code}.txt").write_text(text, encoding="utf-8")
    if failed:
        lines = ["# Не расшифрованы", ""] + [f"- {c} — {why}" for c, why in failed.items()]
        (out_dir / "failed.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        if not transcripts:
            # Не вышло ни одного — это уже не случайный ролик, а системная поломка.
            raise RuntimeError(f"ни один ролик не расшифрован ({len(failed)} из {len(reels)})")
    return transcripts
