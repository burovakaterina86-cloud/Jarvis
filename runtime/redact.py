"""Маскировка секретов и безопасная сводка вызова инструмента — для журналов JARVIS.

В журнал не попадают значения ключей, токенов и паролей (по шаблонам: значения из `.env`
не читаются), содержимое записываемых файлов, адреса с параметрами и набранный в браузере текст.

Публично: `redact(text) -> str`, `redact_obj(obj)`, `tool_summary(tool, tool_input) -> str`.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

MASK = "***"
SUMMARY_LIMIT = 200

_KEY = r"(?:token|secret|password|passwd|pwd|api[_-]?key|apikey|access[_-]?key|auth|client[_-]?secret)"
_PATTERNS = [
    # Bearer <токен>
    (re.compile(r"(?i)(\bbearer\s+)[^\s'\"]+"), r"\1" + MASK),
    # key=value, key: value, "key": "value"
    (re.compile(r"(?i)(\b[\w-]*" + _KEY + r"[\w-]*[\"']?\s*[:=]\s*[\"']?)[^\s'\"&,;}]+"), r"\1" + MASK),
    # известные форматы ключей
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), MASK),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), MASK),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}"), MASK),            # токен Telegram-бота
    (re.compile(r"\bapify_api_[A-Za-z0-9]{16,}"), MASK),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), MASK),                   # Groq
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),                     # AWS
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), MASK),                 # Google
    # длинная непрозрачная строка из букв и цифр (без «/» и «.», чтобы не задеть пути)
    (re.compile(r"(?<![\w/.-])(?=[A-Za-z0-9+=_-]*\d)(?=[A-Za-z0-9+=_-]*[A-Za-z])[A-Za-z0-9+=_-]{40,}(?![\w/.-])"), MASK),
]

_FILE_FIELDS = ("file_path", "notebook_path", "path")
_URL_FIELDS = ("url",)


def redact(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact_obj(obj):
    """Копия структуры, где каждая строка прошла `redact`."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj


def _short(text: str, limit: int = SUMMARY_LIMIT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def _host(url: str) -> str:
    try:
        return urlsplit(str(url)).netloc or "?"
    except ValueError:
        return "?"


def tool_summary(tool: str, tool_input) -> str:
    """Что за объект затронул вызов — без содержимого, параметров адреса и набранного текста."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    if tool in ("Bash", "PowerShell"):
        return _short(redact(str(inp.get("command") or "")))
    if tool in ("Agent", "Task"):
        return _short(f"{inp.get('subagent_type') or 'general'}: {inp.get('description') or ''}".strip())
    if tool == "Skill":
        return _short(str(inp.get("skill") or inp.get("command") or ""))
    if tool == "WebSearch":
        return _short(redact(str(inp.get("query") or "")), 100)
    for field in _URL_FIELDS:
        if inp.get(field):
            return _host(inp[field])
    if tool in ("Grep", "Glob"):
        where = inp.get("path") or inp.get("glob") or ""
        return _short(redact(f"{inp.get('pattern') or ''} {where}".strip()))
    for field in _FILE_FIELDS:
        if isinstance(inp.get(field), str) and inp[field]:
            return _short(inp[field])
    if tool.startswith("mcp__playwright__") and inp.get("element"):
        return _short(redact(str(inp["element"])), 100)
    return _short("ключи: " + ", ".join(sorted(map(str, inp))) if inp else "")
