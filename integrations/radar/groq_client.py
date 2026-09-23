"""Настоящий клиент транскрипции Groq Whisper — используется только при живом прогоне."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"


class GroqApiClient:
    def __init__(self, api_key: str, url: str = GROQ_URL):
        self._key = api_key
        self._url = url

    def transcribe(self, audio_path: Path) -> str:
        boundary = "----jarvis-radar"
        audio_bytes = audio_path.read_bytes()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{MODEL}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{audio_path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            self._url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        # Успех — по HTTP 200, не по grep текста ответа (урок upstream).
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Groq вернул {exc.code}: {exc.reason}") from exc
        return data.get("text", "")
