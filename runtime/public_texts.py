"""Проверка правила публичных текстов (`.claude/rules/public-texts.md`): textwriter → humaniser — на деле, а не на слово.

Её жалоба 2026-10-07: бот написал в чате «текст прошёл textwriter и humaniser», а в самом файле стояла отметка
«humaniser НЕ пройден — проходы не запускались». Модель может и пропустить проход, и сказать, что он был. Поэтому
после хода бот сам сверяет по журналу `state/events.jsonl`, что за ход были:

  1. открыт навык textwriter,
  2. после него открыт навык humaniser,
  3. после этого файл с текстом был записан заново,
  4. и последней строкой файла стоит отметка `<!-- pipeline: textwriter → humaniser → VOICE — пройден ГГГГ-ММ-ДД -->`.

Нет — бот сам запускает исправляющий ход (`fix_prompt`), а если и он не помог — честно предупреждает владелицу
(`warning`), а не молчит и не соглашается с «всё в порядке».
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PREFIX = "essa-ai/content/"
# служебные файлы комплекта и радара — не публичный текст
NOT_PUBLIC_NAMES = {"sources.md", "radar.md", "briefs.md", "own-top.md", "readme.md", "status.md", "published.md"}
NOT_PUBLIC_PARTS = ("/radar-", "/transcripts/", "/visuals/")
MARK_OK = re.compile(r"<!--\s*pipeline:\s*textwriter\s*→\s*humaniser\s*→\s*VOICE\s*—\s*пройден\s+(\d{4}-\d{2}-\d{2})\s*-->\s*$")
EVENTS_TAIL_BYTES = 4 * 1024 * 1024
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
PASSES = ("textwriter", "humaniser")


def is_public_text(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    low = rel.lower()
    if not low.startswith(CONTENT_PREFIX) or not low.endswith(".md"):
        return False
    return Path(low).name not in NOT_PUBLIC_NAMES and not any(part in "/" + low for part in NOT_PUBLIC_PARTS)


def turn_tools(task_id: str, events_path: Path | None = None) -> list[tuple[str, str]]:
    """Инструменты хода по порядку: [(имя, краткое описание)]. Читаем хвост журнала, не весь файл."""
    from runtime import events
    path = Path(events_path or events.EVENTS_PATH)
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - EVENTS_TAIL_BYTES))
            raw = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        if task_id not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("task_id") == task_id and ev.get("type") == "tool_use":
            out.append((str(ev.get("tool") or ""), str(ev.get("summary") or "").replace("\\", "/")))
    return out


def _pass_index(tools: list[tuple[str, str]], name: str, start: int = 0) -> int | None:
    """Номер первого вызова, которым открыт навык `name` (чтение SKILL.md, Skill или субагент)."""
    for i in range(start, len(tools)):
        tool, summary = tools[i]
        low = summary.lower()
        if tool == "Read" and f"skills/{name}/skill.md" in low:
            return i
        if tool in ("Skill", "Agent", "Task") and name in low:
            return i
    return None


def _last_write(tools: list[tuple[str, str]], rel: str, after: int) -> int | None:
    found = None
    for i in range(after, len(tools)):
        tool, summary = tools[i]
        if tool in WRITE_TOOLS and summary.lower().endswith(rel.lower()):
            found = i
    return found


def check_file(rel: str, text: str, tools: list[tuple[str, str]]) -> list[str]:
    problems = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    last = lines[-1].strip() if lines else ""
    if "НЕ пройден" in last:
        problems.append(f"{rel}: в отметке прямо написано, что проход не сделан")
    elif not MARK_OK.search(last):
        problems.append(f"{rel}: нет отметки о проходе последней строкой")
    tw = _pass_index(tools, "textwriter")
    if tw is None:
        problems.append(f"{rel}: за ход не открыт навык textwriter")
        return problems
    hu = _pass_index(tools, "humaniser", tw + 1)
    if hu is None:
        problems.append(f"{rel}: после textwriter не открыт навык humaniser")
        return problems
    if _last_write(tools, rel, hu) is None:
        problems.append(f"{rel}: после humaniser файл не сохранялся — очищенный текст в него не попал")
    return problems


def check(files, task_id: str, root: Path = ROOT, events_path: Path | None = None) -> list[str]:
    """Нарушения правила по файлам, которые изменил ход. Пусто — всё в порядке (или публичных текстов не было)."""
    public = [f.replace("\\", "/") for f in files or [] if is_public_text(f)]
    if not public:
        return []
    tools = turn_tools(task_id, events_path)
    problems = []
    for rel in public:
        path = Path(root) / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        problems += check_file(rel, text, tools)
    return problems


def fix_prompt(problems: list[str], skills_dir: str = ".claude/skills") -> str:
    lines = ["[JARVIS] Бот проверил публичный текст по журналу хода и нашёл нарушение правила "
             "(.claude/rules/public-texts.md):", *[f"- {p}" for p in problems], "",
             "Исправь прямо сейчас, по шагам, ничего не пропуская:",
             f"1. Прочитай {skills_dir}/textwriter/SKILL.md и перепиши текст в файле по нему (живая форма, голос essa-ai/VOICE.md).",
             f"2. Прочитай {skills_dir}/humaniser/SKILL.md и пройди DETECTOR → REWRITER → CHECKER; сохрани очищенный текст в тот же файл.",
             "3. Для хука и призыва сверься с essa-ai/HOOKS_AND_CTA.md (если файла нет — скажи об этом владелице).",
             "4. Последней строкой файла поставь отметку: <!-- pipeline: textwriter → humaniser → VOICE — пройден "
             f"{date.today():%Y-%m-%d} -->",
             "Ничего не выдумывай от её имени. Отметку ставь, только если шаги 1–2 действительно сделаны. "
             "В ответе владелице коротко: что исправил."]
    return "\n".join(lines)


def warning(problems: list[str]) -> str:
    files = sorted({p.split(":", 1)[0] for p in problems})
    return ("\n\n⚠️ Этот текст НЕ прошёл обязательные проходы textwriter → humaniser, хотя я должен был это сделать. "
            "Снимать по нему пока не надо: " + ", ".join(files) + ". Скажи «прогони текст» — сделаю проходы заново.")
