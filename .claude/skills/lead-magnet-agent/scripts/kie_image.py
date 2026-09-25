"""Картинка для лидмагнита через kie.ai (GPT Image 2): задача → опрос → скачивание.

Ключ — `KIE_API_KEY` в `.env` (вписывает владелица). Значение не печатается.
Запуск из корня JARVIS:

    .venv/Scripts/python .claude/skills/lead-magnet-agent/scripts/kie_image.py \
        "промпт" essa-ai/content/lead-magnets/<папка>/images/cover.png --ratio 3:4 --res 2K

Каждый запуск тратит кредиты kie.ai — генерируй только то, что есть в «Карте визуала».
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "https://api.kie.ai"
MODEL = "gpt-image-2-text-to-image"


class KieError(Exception):
    """kie.ai не отдал картинку: нет ключа, нет кредитов, отказ модели, таймаут."""


def require_key(env: dict[str, str] | None = None) -> str:
    if env is None:
        sys.path.insert(0, str(ROOT))
        from integrations.radar.keys import load_dotenv

        load_dotenv()
        env = os.environ
    key = env.get("KIE_API_KEY")
    if not key:
        raise KieError("нет ключа KIE_API_KEY в .env")
    return key


def task_body(prompt: str, aspect_ratio: str = "3:4", resolution: str = "2K") -> dict:
    return {"model": MODEL, "input": {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": resolution}}


def http_api(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise KieError(f"kie.ai ответил {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e


def http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def generate(prompt: str, dest: Path, *, key: str, aspect_ratio: str = "3:4", resolution: str = "2K",
             api=http_api, download=http_download, sleep=time.sleep, timeout_s: int = 300) -> Path:
    created = api("POST", "/api/v1/jobs/createTask", key, task_body(prompt, aspect_ratio, resolution))
    task_id = (created.get("data") or {}).get("taskId")
    if created.get("code") != 200 or not task_id:
        raise KieError(f"задача не создана: {created.get('msg') or created}")

    waited = 0
    while waited <= timeout_s:
        info = api("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}", key).get("data") or {}
        state = info.get("state")
        if state == "success":
            urls = json.loads(info.get("resultJson") or "{}").get("resultUrls") or []
            if not urls:
                raise KieError("задача выполнена, но ссылки на картинку нет")
            download(urls[0], dest)
            return dest
        if state == "fail":
            raise KieError(f"генерация не удалась: {info.get('failMsg') or info.get('failCode')}")
        sleep(5)
        waited += 5
    raise KieError(f"не дождался картинки за {timeout_s} с")


def main() -> int:
    p = argparse.ArgumentParser(description="Картинка через kie.ai GPT Image 2")
    p.add_argument("prompt")
    p.add_argument("dest", type=Path)
    p.add_argument("--ratio", default="3:4")
    p.add_argument("--res", default="2K", choices=["1K", "2K", "4K"])
    a = p.parse_args()
    try:
        out = generate(a.prompt, a.dest, key=require_key(), aspect_ratio=a.ratio, resolution=a.res)
    except KieError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
