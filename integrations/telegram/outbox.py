"""Почтовый ящик бота: письмо владелице от задачи, которую никто не просил в чате.

Задача по расписанию (например, понедельничный рилс-радар) не может написать в Telegram сама —
отвечает только бот. Поэтому она кладёт письмо файлом в `state/outbox/`, а бот, пока запущен,
раз в `DRAFT_POLL_INTERVAL` секунд забирает письма и присылает их владелице
(текст + файлы из строк `📎 <путь>`), после чего переносит письмо в `state/outbox/sent/`.
Письмо, которое не ушло (Telegram отказал), остаётся и уходит на следующем опросе.

    python -m integrations.telegram.outbox "текст" [путь/к/файлу ...]

Адресат всегда один — владелица (`TELEGRAM_OWNER_ID`): чужим людям отсюда не пишется.
"""
from __future__ import annotations

import datetime as dt
import sys
import json
import os
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def outbox_dir(root: Path | str = ROOT) -> Path:
    return Path(root) / "state" / "outbox"


def _valid_task(task_id) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(task_id or "")))


def _cancelled(root, task_id) -> bool:
    return _valid_task(task_id) and (outbox_dir(root) / "cancelled-tasks" / f"{task_id}.json").exists()


def cancel_tasks(root, task_ids: set[str]) -> None:
    folder = outbox_dir(root) / "cancelled-tasks"
    folder.mkdir(parents=True, exist_ok=True)
    for task_id in task_ids:
        if _valid_task(task_id):
            (folder / f"{task_id}.json").write_text('{"cancelled": true}', encoding="utf-8")


def post(root: Path | str, text: str, files: list[str] | None = None) -> Path:
    """Положить письмо. Файлы — пути внутри папки JARVIS, их пришлёт бот."""
    folder = outbox_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    body = text.rstrip() + "\n"
    for f in files or []:
        body += f"\n📎 {f}"
    path = folder / f"{stamp}.md"
    if path.exists():
        path = folder / f"{stamp}_{uuid.uuid4().hex[:8]}.md"
    task_id = os.environ.get("JARVIS_TASK_ID", "")
    if _valid_task(task_id):
        path.with_suffix(".meta.json").write_text(json.dumps({"task_id": task_id}), encoding="utf-8")
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def pending(root: Path | str = ROOT) -> list[Path]:
    result = []
    for path in sorted(outbox_dir(root).glob("*.md")):
        metadata = path.with_suffix(".meta.json")
        if metadata.exists():
            try:
                task_id = json.loads(metadata.read_text(encoding="utf-8"))["task_id"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if _cancelled(root, task_id):
                folder = path.parent / "cancelled"
                folder.mkdir(exist_ok=True)
                path.replace(folder / path.name)
                metadata.replace(folder / metadata.name)
                continue
        result.append(path)
    return result


def discard(path: Path) -> None:
    """Сохранить отменённое письмо вне очереди, включая его метаданные."""
    folder = path.parent / "cancelled"
    folder.mkdir(exist_ok=True)
    for source in (path, path.with_suffix(".meta.json")):
        if source.exists():
            source.replace(folder / source.name)


def cancel_pending(root) -> None:
    for path in pending(root):
        discard(path)


def is_cancelled(root, path: Path) -> bool:
    if not path.exists():
        return True
    metadata = path.with_suffix(".meta.json")
    if not metadata.exists():
        return False
    try:
        return _cancelled(root, json.loads(metadata.read_text(encoding="utf-8"))["task_id"])
    except (OSError, ValueError, KeyError, TypeError):
        return True


def mark_sent(path: Path) -> None:
    sent = path.parent / "sent"
    sent.mkdir(exist_ok=True)
    path.replace(sent / path.name)
    metadata = path.with_suffix(".meta.json")
    if metadata.exists():
        metadata.replace(sent / metadata.name)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    print(post(ROOT, args[0], args[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
