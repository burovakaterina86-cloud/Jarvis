"""Сгенерированные картинки для лидмагнитов и каруселей: сначала Codex, потом kie.ai.

    python -m integrations.visuals.imagegen "промпт" <путь.png> [--ratio 3:4] [--res 2K] [--only codex|kie]

Порядок — её решение 2026-09-25:
1. **Codex** (`codex exec` + встроенный навык `$imagegen`, модель gpt-image) — в рамках её подписки
   ChatGPT Plus, отдельно не платим. Картинки едят лимит Codex в 3-5 раз быстрее текста.
2. **kie.ai** (GPT Image 2, ключ `KIE_API_KEY` в `.env`) — если у Codex кончился лимит или он не
   сработал. Платно, кредитами kie.ai.

Печатает путь и кто нарисовал; если пришлось уйти на kie.ai — причину в stderr.
Текст на картинках не заказывай: надписи накладываются вёрсткой.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KIE_BASE = "https://api.kie.ai"
KIE_MODEL = "gpt-image-2-text-to-image"
CODEX_TIMEOUT_S = 600


class ImageGenError(Exception):
    """Картинку получить не удалось."""


class CodexLimit(ImageGenError):
    """У Codex кончился лимит подписки."""


@dataclass
class Result:
    path: Path
    provider: str  # "codex" | "kie"
    note: str = ""  # почему не Codex, если ушли на kie.ai


# --- Codex ---

def codex_prompt(prompt: str, filename: str, aspect_ratio: str) -> str:
    return (
        f"Use $imagegen to generate exactly one image. Aspect ratio {aspect_ratio}, high resolution.\n"
        f"Image description:\n{prompt}\n\n"
        f"Save the final PNG as {filename} in the current working directory. "
        "Do not create any other files. Reply with only the saved file path."
    )


def parse_codex_events(output: str) -> tuple[str | None, str | None]:
    """Из JSONL `codex exec --json` — (thread_id, текст ошибки или None). Не-JSON строки пропускаем."""
    thread, error = None, None
    for line in output.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "thread.started":
            thread = ev.get("thread_id")
        elif ev.get("type") == "error" and ev.get("message"):
            error = error or ev["message"]
        elif ev.get("type") == "turn.failed":
            error = error or (ev.get("error") or {}).get("message") or "turn failed"
    return thread, error


def run_codex(cmd: list[str], cwd: Path) -> tuple[int, str]:
    exe = shutil.which(cmd[0])
    if not exe:
        raise ImageGenError("codex не установлен")
    try:
        p = subprocess.run([exe, *cmd[1:]], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=CODEX_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise ImageGenError(f"codex не ответил за {CODEX_TIMEOUT_S} с") from e
    return p.returncode, p.stdout


def generate_codex(prompt: str, dest: Path, aspect_ratio: str = "3:4", *,
                   run=run_codex, home: Path | None = None) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "workspace-write",
           "-C", str(dest.parent), "--json", codex_prompt(prompt, dest.name, aspect_ratio)]
    _, output = run(cmd, dest.parent)
    thread, error = parse_codex_events(output)
    if error and "usage limit" in error.lower():
        raise CodexLimit(error)
    if dest.is_file():
        return dest
    # Codex мог оставить картинку у себя: ~/.codex/generated_images/<thread>/
    gen_dir = (home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")) / "generated_images"
    if thread and (gen_dir / thread).is_dir():
        pngs = sorted((gen_dir / thread).glob("*.png"), key=lambda p: p.stat().st_mtime)
        if pngs:
            shutil.copyfile(pngs[-1], dest)
            return dest
    raise ImageGenError(f"codex не отдал картинку: {error or 'файла нет'}")


# --- kie.ai ---

def require_kie_key(env: dict[str, str] | None = None) -> str:
    if env is None:
        from integrations.radar.keys import load_dotenv

        load_dotenv()
        env = os.environ
    key = env.get("KIE_API_KEY")
    if not key:
        raise ImageGenError("нет ключа KIE_API_KEY в .env")
    return key


def kie_task_body(prompt: str, aspect_ratio: str = "3:4", resolution: str = "2K") -> dict:
    return {"model": KIE_MODEL, "input": {"prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": resolution}}


def kie_http(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(KIE_BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ImageGenError(f"kie.ai ответил {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e


def http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def generate_kie(prompt: str, dest: Path, aspect_ratio: str = "3:4", resolution: str = "2K", *,
                 key: str | None = None, api=kie_http, download=http_download, sleep=time.sleep,
                 timeout_s: int = 300) -> Path:
    key = key or require_kie_key()
    created = api("POST", "/api/v1/jobs/createTask", key, kie_task_body(prompt, aspect_ratio, resolution))
    task_id = (created.get("data") or {}).get("taskId")
    if created.get("code") != 200 or not task_id:
        raise ImageGenError(f"kie.ai: задача не создана: {created.get('msg') or created}")

    waited = 0
    while waited <= timeout_s:
        info = api("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}", key).get("data") or {}
        state = info.get("state")
        if state == "success":
            urls = json.loads(info.get("resultJson") or "{}").get("resultUrls") or []
            if not urls:
                raise ImageGenError("kie.ai: задача выполнена, но ссылки на картинку нет")
            download(urls[0], dest)
            return dest
        if state == "fail":
            raise ImageGenError(f"kie.ai: генерация не удалась: {info.get('failMsg') or info.get('failCode')}")
        sleep(5)
        waited += 5
    raise ImageGenError(f"kie.ai: не дождался картинки за {timeout_s} с")


# --- порядок ---

def generate(prompt: str, dest: Path, aspect_ratio: str = "3:4", resolution: str = "2K", *,
             only: str | None = None, codex=generate_codex, kie=generate_kie) -> Result:
    dest = Path(dest)
    note = ""
    if only != "kie":
        try:
            return Result(codex(prompt, dest, aspect_ratio), "codex")
        except CodexLimit as e:
            note = f"у Codex кончился лимит подписки ({e})"
        except ImageGenError as e:
            note = f"Codex не сработал: {e}"
        if only == "codex":
            raise ImageGenError(note)
    try:
        return Result(kie(prompt, dest, aspect_ratio, resolution), "kie", note)
    except ImageGenError as e:
        raise ImageGenError("; ".join(filter(None, [note, str(e)]))) from e


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # консоль Windows по умолчанию не UTF-8
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Картинка: Codex по подписке, запасной — kie.ai")
    p.add_argument("prompt")
    p.add_argument("dest", type=Path)
    p.add_argument("--ratio", default="3:4")
    p.add_argument("--res", default="2K", choices=["1K", "2K", "4K"])
    p.add_argument("--only", choices=["codex", "kie"])
    a = p.parse_args()
    try:
        r = generate(a.prompt, a.dest, a.ratio, a.res, only=a.only)
    except ImageGenError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1
    if r.note:
        print(f"kie.ai вместо Codex: {r.note}", file=sys.stderr)
    print(f"{r.path} ({r.provider})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
