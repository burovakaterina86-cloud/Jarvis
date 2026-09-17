"""PreCompact: итог задачи одной строкой в memory/episodes/YYYY-MM.jsonl.

Вход: JSON PreCompact на stdin (session_id, trigger, transcript_path).
Выход: ничего (информационный хук, компактизацию не блокирует).
Строка: {"date", "session", "trigger", "request", "result", "files"} — по последнему
ходу владелицы; служебные записи transcript и ходы субагентов не учитываются.
Хук не защитный: любая ошибка -> exit 0 без эффекта.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hookutil  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MAX_TEXT = 500
MAX_FILES = 20


def summarize(transcript_path):
    """(последний запрос владелицы, последний текст агента, файлы этого хода)."""
    request, result, files, _ = _hookutil.last_turn(transcript_path)
    cut = lambda s: s[:MAX_TEXT] if s else s  # noqa: E731
    return cut(request), cut(result), files[:MAX_FILES]


def episode(event, root, now=None):
    """Собрать и дописать строку эпизода; вернуть записанную запись."""
    now = now or datetime.now(timezone.utc).astimezone()
    request, result, files = None, None, []
    path = event.get("transcript_path")
    if path and Path(path).is_file():
        request, result, files = summarize(path)
    record = {
        "date": now.isoformat(timespec="seconds"),
        "session": event.get("session_id"),
        "trigger": event.get("trigger"),
        "request": request,
        "result": result,
        "files": files,
    }
    out = Path(root) / "memory" / "episodes" / f"{now:%Y-%m}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def handle(event, root, now=None):
    episode(event, root, now=now)
    return None  # PreCompact ничего не печатает


def main(stdin=None, stdout=None, root=ROOT, now=None):
    return _hookutil.run(handle, stdin, stdout, root=root, now=now)


if __name__ == "__main__":
    _hookutil.setup_streams()
    sys.exit(main())
