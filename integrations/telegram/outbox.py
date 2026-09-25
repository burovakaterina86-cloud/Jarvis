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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def outbox_dir(root: Path | str = ROOT) -> Path:
    return Path(root) / "state" / "outbox"


def post(root: Path | str, text: str, files: list[str] | None = None) -> Path:
    """Положить письмо. Файлы — пути внутри папки JARVIS, их пришлёт бот."""
    folder = outbox_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    body = text.rstrip() + "\n"
    for f in files or []:
        body += f"\n📎 {f}"
    path = folder / f"{stamp}.md"
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def pending(root: Path | str = ROOT) -> list[Path]:
    return sorted(outbox_dir(root).glob("*.md"))


def mark_sent(path: Path) -> None:
    sent = path.parent / "sent"
    sent.mkdir(exist_ok=True)
    path.replace(sent / path.name)


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
