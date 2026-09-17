"""Stop: после настоящей задачи один раз напомнить про урок / решение / алгоритм.

Вход: JSON Stop на stdin (stop_hook_active, transcript_path, last_assistant_message).
Выход: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
или ничего. Не срабатывает при stop_hook_active=true (нет зацикливания) и на
коротких ходах (< MIN_TOOL_USES вызовов инструментов с последнего сообщения
владелицы; служебные записи transcript и ходы субагентов не считаются).
Хук не защитный: любая ошибка -> exit 0 без эффекта.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hookutil  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MIN_TOOL_USES = 3

REMINDER = (
    "Задача завершена. Молча проверь: был ли в ней урок или решение, которое пригодится "
    "потом? Если да — сохрани коротко в memory/decisions/ по правилу .claude/rules/memory.md. "
    "Был ли повторяемый алгоритм, которого нет в навыках? Если да — предложи владелице "
    "оформить его навыком через create-skill (сам не создавай без её согласия). "
    "Последним сообщением снова дай итоговый ответ владелице целиком (плюс строка «🧠 запомнил», "
    "если что-то сохранил). Если сохранять нечего — просто повтори итоговый ответ без комментариев."
)


def tool_uses_in_last_turn(transcript_path):
    """Число tool_use главного агента после последнего сообщения владелицы."""
    return _hookutil.last_turn(transcript_path)[3]


def handle(event, root):
    if event.get("stop_hook_active"):
        return None
    path = event.get("transcript_path")
    if not path or not Path(path).is_file():
        return None
    if tool_uses_in_last_turn(path) < MIN_TOOL_USES:
        return None
    return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": REMINDER}}


def main(stdin=None, stdout=None, root=ROOT):
    return _hookutil.run(handle, stdin, stdout, root=root)


if __name__ == "__main__":
    _hookutil.setup_streams()
    sys.exit(main())
