"""SessionStart: additionalContext из двух частей (обе необязательные).

1. MEMORY.md больше 5 KB -> «сожми MEMORY.md».
2. Журнал ошибок (runtime/errorlog.py): ошибки агента, которые уже повторялись, -> «не повторяй».

Вход: JSON SessionStart на stdin.
Выход: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
или ничего. Хук не защитный: любая ошибка -> exit 0 без эффекта.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hookutil  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MEMORY_LIMIT_BYTES = 5 * 1024


def memory_note(root):
    memory = Path(root) / "MEMORY.md"
    if not memory.is_file():
        return None
    size = memory.stat().st_size
    if size <= MEMORY_LIMIT_BYTES:
        return None
    return (
        f"MEMORY.md занимает {size / 1024:.1f} KB (лимит 5 KB): сожми MEMORY.md. "
        "Оставь 20–50 важнейших фактов одной строкой каждый, подробности перенеси в "
        "memory/decisions|projects|people/ по правилу .claude/rules/memory.md, "
        "затем коротко сообщи владелице, что перенесено."
    )


def errors_note(root):
    """Памятка из журнала ошибок. Сбой чтения журнала не должен мешать остальному."""
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from runtime import errorlog
        return errorlog.digest(index_path=Path(root) / "state" / "errors_index.json") or None
    except Exception:
        return None


def handle(event, root):
    notes = [n for n in (memory_note(root), errors_note(root)) if n]
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n\n".join(notes)}}


def main(stdin=None, stdout=None, root=ROOT):
    return _hookutil.run(handle, stdin, stdout, root=root)


if __name__ == "__main__":
    _hookutil.setup_streams()
    sys.exit(main())
