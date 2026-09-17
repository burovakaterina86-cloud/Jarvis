"""PostToolUse: запись в память -> additionalContext «сообщи владелице: 🧠 запомнил».

Вход: JSON PostToolUse на stdin (tool_name, tool_input.file_path|notebook_path, tool_response).
Молчит, если запись не состоялась (ошибка в tool_response).
Выход: {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
или ничего. Хук не защитный: любая ошибка -> exit 0 без эффекта.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hookutil  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
MEMORY_FILES = ("MEMORY.md",)
MEMORY_DIRS = ("memory", "essa-ai/knowledge")


def memory_rel_path(file_path, root):
    """Путь относительно корня (с '/'), если это файл памяти; иначе None."""
    root = Path(root).resolve()
    p = Path(file_path)
    p = (p if p.is_absolute() else root / p).resolve()
    root_parts = [os.path.normcase(x) for x in root.parts]
    parts = list(p.parts)
    if [os.path.normcase(x) for x in parts[: len(root_parts)]] != root_parts:
        return None
    rel_parts = parts[len(root_parts):]
    rel = "/".join(rel_parts)
    key = os.path.normcase(rel).replace("\\", "/")
    if any(key == os.path.normcase(n) for n in MEMORY_FILES):
        return rel
    if any(key.startswith(os.path.normcase(d).replace("\\", "/") + "/") for d in MEMORY_DIRS):
        return rel
    return None


def write_succeeded(tool_response):
    """Запись состоялась? Ошибку узнаём по tool_response (строка или словарь)."""
    if isinstance(tool_response, str):
        return not tool_response.lstrip().lower().startswith("error")
    if isinstance(tool_response, dict):
        if tool_response.get("success") is False:
            return False
        if tool_response.get("error") or tool_response.get("is_error"):
            return False
    return True


def handle(event, root):
    if event.get("tool_name") not in WRITE_TOOLS:
        return None
    if not write_succeeded(event.get("tool_response")):
        return None
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return None
    rel = memory_rel_path(file_path, root)
    if rel is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"Ты записал в память ({rel}). В ответе владелице добавь отдельной строкой: "
                f"«🧠 запомнил: <что, коротко> ({rel})»."
            ),
        }
    }


def main(stdin=None, stdout=None, root=ROOT):
    return _hookutil.run(handle, stdin, stdout, root=root)


if __name__ == "__main__":
    _hookutil.setup_streams()
    sys.exit(main())
