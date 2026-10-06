"""CLI для агента: python -m integrations.jobs <submit|status>

submit  --title "…" [--file путь]… [--done "текст"] [--fail "текст"] -- -m модуль аргументы…
        ставит работу в очередь бота и возвращается сразу; после этого ход надо ЗАКОНЧИТЬ — результат бот пришлёт сам
status  что сейчас в работе и чем закончились последние работы

Коды выхода: 0 — готово, 2 — запрос не прошёл проверку.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import read_states, submit

LABELS = {"queued": "ждёт очереди", "running": "идёт", "done": "готово", "failed": "не получилось",
          "interrupted": "прервана"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="integrations.jobs")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--title", required=True)
    s.add_argument("--file", action="append", default=[], dest="files")
    s.add_argument("--done", default="")
    s.add_argument("--fail", default="")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.command == "status":
        states = read_states()
        if not states:
            print("фоновых работ не было")
        for st in states[-8:]:
            age = int(time.time() - st.get("queued_at", time.time()))
            print(f"{st['id']} | {LABELS.get(st['status'], st['status'])} | {st['title']} | {age // 60} мин назад")
        return 0
    cmd = [c for c in args.cmd if c != "--"] if args.cmd and args.cmd[0] == "--" else args.cmd
    job_id, problems = submit(args.title, cmd, args.files, args.done, args.fail)
    if problems:
        for p in problems:
            print("✗", p, file=sys.stderr)
        return 2
    print(f"поставлено в фон: {job_id}. Бот сам запустит и пришлёт результат; закончи ход, ничего не жди.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
