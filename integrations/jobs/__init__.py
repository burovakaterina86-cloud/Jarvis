"""Фоновые работы: долгое выполняет сам бот, а не ход агента.

Зачем (её жалоба 2026-10-06): процесс, запущенный «в фоне» из хода агента, умирает вместе с ходом, а ждать его
внутри хода — значит держать весь чат. Теперь агент не запускает долгое сам: он ставит работу в очередь командой

    python -m integrations.jobs submit --title "Сборка рилса" --file outbox/reel.mp4 --done "Ролик собран" -- \\
        -m integrations.montage.run remake --work outbox/montage/reel --spec outbox/montage/reel/spec.json

и сразу заканчивает ход. Бот (`integrations/jobs/runner.py`) сам запускает процесс, следит за ним и по окончании
присылает ей результат через почтовый ящик (`state/outbox`). Чат всё это время свободен.

Запросы лежат в `jobs/requests/<id>.json` (туда агент писать может), состояние и журналы — в `state/jobs/` (только бот).
Запускается ТОЛЬКО то, что в белом списке модулей: произвольные команды через эту дверь не пройдут.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUESTS = ROOT / "jobs" / "requests"
STATE = ROOT / "state" / "jobs"

#: Что можно запускать в фоне. Модуль целиком из этого списка, любые его аргументы — на совести модуля (argparse).
ALLOWED_MODULES = ("integrations.montage.run", "integrations.content_plan", "integrations.site_builder",
                   "integrations.radar")
MAX_ARG_LEN = 600
MAX_ARGS = 40
MAX_FILES = 6
PROTECTED_PREFIXES = ("state/", ".git", ".env", "runtime/", ".claude/", "integrations/")
_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def validate(req: dict, root: Path = ROOT) -> list[str]:
    """Список проблем в запросе (пусто — можно запускать). Проверяется и при подаче, и ботом перед запуском."""
    problems: list[str] = []
    if not isinstance(req, dict):
        return ["запрос должен быть объектом"]
    title = req.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 120:
        problems.append("title: нужна короткая строка до 120 знаков")
    argv = req.get("argv")
    if not isinstance(argv, list) or len(argv) < 2 or not all(isinstance(a, str) for a in argv):
        return problems + ["argv: список строк вида [\"-m\", \"модуль\", аргументы…]"]
    if len(argv) > MAX_ARGS or any(len(a) > MAX_ARG_LEN or "\n" in a or "\x00" in a for a in argv):
        problems.append("argv: слишком длинный или с переводом строки")
    if argv[0] != "-m":
        problems.append("argv[0] должен быть -m: произвольный код в фоне запускать нельзя")
    elif not _MODULE_RE.match(argv[1]) or argv[1] not in ALLOWED_MODULES:
        problems.append(f"модуль {argv[1]!r} не из белого списка: {', '.join(ALLOWED_MODULES)}")
    files = req.get("files", [])
    if not isinstance(files, list) or len(files) > MAX_FILES or not all(isinstance(f, str) for f in files):
        problems.append(f"files: список путей, не больше {MAX_FILES}")
    else:
        for f in files:
            full = (Path(root) / f).resolve()          # «..» схлопываются здесь, поэтому проверяем путь после разбора
            try:
                norm = full.relative_to(Path(root).resolve()).as_posix()
            except ValueError:
                problems.append(f"файл вне папки JARVIS: {f}")
                continue
            if norm.lower().startswith(PROTECTED_PREFIXES) or ".env" in norm.lower():
                problems.append(f"файл из защищённого места: {f}")
    for key in ("done", "fail"):
        if key in req and (not isinstance(req[key], str) or len(req[key]) > 500):
            problems.append(f"{key}: строка до 500 знаков")
    return problems


def submit(title: str, argv: list[str], files: list[str] | None = None, done: str = "", fail: str = "",
           root: Path = ROOT) -> tuple[str, list[str]]:
    """Положить запрос. Возвращает (id, проблемы); при проблемах файл не создаётся."""
    req = {"title": title, "argv": argv, "files": files or [], "done": done, "fail": fail}
    problems = validate(req, root)
    if problems:
        return "", problems
    job_id = uuid.uuid4().hex[:10]
    folder = Path(root) / "jobs" / "requests"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{job_id}.json").write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
    return job_id, []


def read_states(root: Path = ROOT) -> list[dict]:
    """Состояния всех работ, новые последними (для `status` и для быстрой полосы)."""
    out = []
    for path in sorted((Path(root) / "state" / "jobs").glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda r: r.get("queued_at", 0))
