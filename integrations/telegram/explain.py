"""Человеческое объяснение запроса на подтверждение (её просьба 2026-10-06).

Guard присылает «правка собственных правил: .claude/rules/memory.md» — для неё это шифр. Здесь тот же запрос
превращается в: что хочу сделать, что это за файл и за что он отвечает, чем это грозит и как ответить.
"""
from __future__ import annotations

import re

# (шаблон пути, что это за файл). Первое совпадение выигрывает.
FILES = [
    (r"(^|/)CLAUDE\.md$", "главная памятка JARVIS: как он себя ведёт и куда смотрит, когда начинает работу"),
    (r"(^|/)SOUL\.md$", "его характер и тон общения с тобой"),
    (r"(^|/)GOALS\.md$", "твои цели и приоритеты, по которым он выбирает темы"),
    (r"(^|/)MEMORY\.md$", "его короткая память о тебе: важные факты и твои решения"),
    (r"(^|/)AGENTS\.md$", "памятка для Codex — запасного исполнителя"),
    (r"\.claude/rules/safety", "правила безопасности: что он делает сам, а что только с твоего «да»"),
    (r"\.claude/rules/approvals", "правила подтверждений: как он спрашивает тебя перед важным"),
    (r"\.claude/rules/memory", "правила памяти: что он запоминает и куда записывает"),
    (r"\.claude/rules/delegation", "правила работы с помощниками: когда он зовёт их на подзадачи"),
    (r"\.claude/rules/", "одно из его правил поведения"),
    (r"\.claude/skills/([^/]+)", "навык «\\1» — готовый способ делать повторяющуюся работу"),
    (r"\.agents/skills/([^/]+)", "копия навыка «\\1» для Codex"),
    (r"\.claude/agents/([^/]+)", "помощник «\\1» — отдельная роль для подзадач"),
    (r"\.codex/agents/([^/]+)", "копия помощника «\\1» для Codex"),
    (r"\.claude/hooks/", "его защита: проверки, которые не дают ему сделать лишнее"),
    (r"\.claude/settings", "настройки Claude Code: права и подключённые проверки"),
    (r"(^|/)runtime/policy\.yaml$", "таблица разрешений: что можно без вопросов, а что нельзя"),
    (r"(^|/)runtime/", "внутренности бота: то, как он принимает сообщения и запускает работу"),
    (r"(^|/)integrations/", "программы бота: Telegram, радар, картинки"),
    (r"(^|/)\.env", "секретные ключи (токены) — их он не должен трогать"),
    (r"memory/corrections\.md", "журнал твоих поправок"),
    (r"memory/", "его долгая память: решения, проекты, люди"),
    (r"drafts/", "черновики навыков и помощников, ждущие твоего решения"),
    (r"essa-ai/content/", "готовые материалы: посты, карусели, сценарии"),
    (r"essa-ai/", "материалы про ESSA.AI: аудитория, продукты, голос"),
    (r"inbox/", "файлы, которые ты присылала в Telegram"),
    (r"state/", "служебные записи бота"),
]


def describe_path(path: str) -> str:
    norm = str(path or "").replace("\\", "/")
    for pattern, text in FILES:
        m = re.search(pattern, norm)
        if m:
            return m.expand(text) if m.groups() else text
    return ""


def _short(value, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def _target(tool_input: dict) -> str:
    for key in ("file_path", "path", "notebook_path"):
        if isinstance(tool_input.get(key), str):
            return tool_input[key]
    return ""


def _file_block(path: str) -> str:
    if not path:
        return ""
    what = describe_path(path)
    return f"Файл: {path}" + (f"\nЭто {what}." if what else "")


def build(level: str, tool: str, summary: str, details: dict) -> str:
    """Текст сообщения с кнопками «Подтвердить / Отклонить»."""
    details = details if isinstance(details, dict) else {}
    kind = details.get("kind") or ""
    tin = details.get("tool_input") if isinstance(details.get("tool_input"), dict) else {}
    mark = "💸" if level == "MONEY" else "🌐"
    path = _target(tin)
    parts: list[str] = []

    if kind == "self_modify":
        parts.append("Хочу изменить свои собственные правила.")
        parts.append(_file_block(path))
        text = " ".join(str(tin.get(k) or "") for k in ("new_string", "content") if isinstance(tin.get(k), str))
        if text.strip():
            parts.append(f"Что хочу записать: «{_short(text)}»")
        parts.append("Если согласишься, я дальше буду вести себя по-другому. Не уверена — отклони, и я объясню, зачем это.")
    elif kind == "write_outside_root":
        parts.append("Хочу сохранить файл за пределами своей папки.")
        parts.append(_file_block(path))
        parts.append("Обычно это нужно, если ты просила положить что-то в другое место. Не просила — отклони.")
    elif kind == "run_script":
        parts.append("Хочу запустить программу на твоём компьютере.")
        parts.append(f"Команда: {_short(tin.get('command'))}")
        parts.append("Она не из проверенных мест, поэтому спрашиваю. Если не понимаешь, зачем, — отклони.")
    elif kind == "big_read":
        parts.append("Хочу прочитать очень большой файл целиком.")
        parts.append(_file_block(path))
        parts.append("Это съест много лимита. Если нужен только кусок, лучше отклонить, и я прочитаю часть.")
    elif kind == "unknown_tool":
        parts.append(f"Хочу воспользоваться инструментом «{tool}», которого не знаю.")
        parts.append("Побочных действий я не жду, но Guard такого ещё не видел. Нажми «Отклонить», если сомневаешься.")
    else:
        parts.append(summary)
        block = _file_block(path)
        if block:
            parts.append(block)
        if tin.get("command"):
            parts.append(f"Команда: {_short(tin['command'])}")
        parts.append("Не поняла, зачем это, — отклони, и я объясню.")

    parts.append("Можно, я это сделаю?")
    return f"{mark} " + "\n\n".join(p for p in parts if p)
