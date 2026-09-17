"""Общее для хуков памяти: разбор transcript и обёртка main (не хук сам по себе).

Разбор пропускает служебные записи: `isMeta` (вставки хуков и системные напоминания)
и `isSidechain` (ход субагента) — они не ход владелицы и не работа главного агента.
"""
import json
import sys

FILE_FIELDS = ("file_path", "notebook_path")


def text_of(content):
    """Текст сообщения: строка или склейка текстовых блоков; None, если текста нет."""
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p) or None
    return None


def iter_entries(path):
    """Записи transcript без служебных (isMeta / isSidechain) и без битых строк."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("isMeta") or entry.get("isSidechain"):
                continue
            yield entry


def last_turn(path):
    """Последний ход владелицы: (request, result, files, tool_uses)."""
    request = result = None
    files, tool_uses = [], 0
    for entry in iter_entries(path):
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            text = text_of(content)
            if text:  # новое сообщение владелицы -> ход начинается заново
                request, result, files, tool_uses = text, None, [], 0
        elif entry.get("type") == "assistant" and isinstance(content, list):
            text = text_of(content)
            if text:
                result = text
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses += 1
                    inp = block.get("input") or {}
                    for field in FILE_FIELDS:
                        if inp.get(field) and inp[field] not in files:
                            files.append(inp[field])
    return request, result, files, tool_uses


def run(handle, stdin=None, stdout=None, **kwargs):
    """Общая обёртка main: хуки памяти не защитные — любая ошибка даёт exit 0 без эффекта."""
    try:
        event = json.loads((stdin or sys.stdin).read())
        result = handle(event, **kwargs)
        if result:
            (stdout or sys.stdout).write(json.dumps(result, ensure_ascii=False))
    except Exception:
        pass
    return 0


def setup_streams():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
