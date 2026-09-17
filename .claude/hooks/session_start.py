"""SessionStart: MEMORY.md больше 5 KB -> additionalContext «сожми MEMORY.md».

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


def handle(event, root):
    memory = Path(root) / "MEMORY.md"
    if not memory.is_file():
        return None
    size = memory.stat().st_size
    if size <= MEMORY_LIMIT_BYTES:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"MEMORY.md занимает {size / 1024:.1f} KB (лимит 5 KB): сожми MEMORY.md. "
                "Оставь 20–50 важнейших фактов одной строкой каждый, подробности перенеси в "
                "memory/decisions|projects|people/ по правилу .claude/rules/memory.md, "
                "затем коротко сообщи владелице, что перенесено."
            ),
        }
    }


def main(stdin=None, stdout=None, root=ROOT):
    return _hookutil.run(handle, stdin, stdout, root=root)


if __name__ == "__main__":
    _hookutil.setup_streams()
    sys.exit(main())
