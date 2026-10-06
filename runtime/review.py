"""Независимая проверка результата (аудит 2026-10-05, P2.2).

Исполнитель не решает сам, что задача готова. После существенного хода (был план, появился
комплект в `essa-ai/content/` или изменился код) мост запускает отдельный процесс `claude -p`:
без истории исполнителя (`--no-session-persistence`, без `--resume`), только чтение
(`runtime/reviewer-settings.json` + Guard), роль из `runtime/prompts/review.md`, вердикт по схеме.
На вход — только запрос, план, список файлов, ответ исполнителя и результаты тестов.
`fix` → замечания уходят исполнителю в его сессию → повторная проверка; не больше MAX_ROUNDS.

Возможности CLI, на которых это стоит, проверены живым прогоном (P2.0, `tests/smoke_cli_capabilities.py`).
Выключатель — переменная JARVIS_REVIEW=off.
"""
from __future__ import annotations

import os
from pathlib import Path

from runtime.claude_bridge import TurnOptions

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "runtime" / "reviewer-settings.json"
PROMPT = ROOT / "runtime" / "prompts" / "review.md"
MAX_ROUNDS = 2
MAX_TURNS = 25
ANSWER_LIMIT = 3000
TESTS_LIMIT = 3000
FILES_LIMIT = 60

CONTENT_PREFIX = "essa-ai/content/"
CODE_SUFFIXES = (".py", ".js", ".ts", ".ps1", ".sh")

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "problems", "checked"],
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fix", "fail"]},
        "problems": {"type": "array", "items": {"type": "string"}},
        "checked": {"type": "array", "items": {"type": "string"}},
    },
}

OPTIONS = TurnOptions(settings=SETTINGS, prompt_file=PROMPT, max_turns=MAX_TURNS,
                      json_schema=SCHEMA, persist=False, read_only=True, browser=False)


def enabled(env=None) -> bool:
    return str((env if env is not None else os.environ).get("JARVIS_REVIEW", "on")).lower() not in ("off", "0", "no")


def code_changed(files) -> list[str]:
    return [f for f in files or [] if f.lower().endswith(CODE_SUFFIXES)]


def needs_review(job, res, env=None) -> bool:
    """Существенный ход чата: был план, комплект или код. Расписание и простые ответы — нет."""
    if not enabled(env) or getattr(res, "status", "") != "ok" or getattr(job, "context", "chat") != "chat":
        return False
    files = getattr(res, "files", None) or []
    return bool(getattr(job, "spec", None)) or any(f.startswith(CONTENT_PREFIX) for f in files) \
        or bool(code_changed(files))


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n…(обрезано)"


def build_prompt(job, res, tests: str | None = None) -> str:
    """Свежий контекст для проверяющего: без рассуждений исполнителя."""
    parts = ["Проверь результат работы по правилам из системного промпта.", "",
             "## Сообщение владелицы в этом ходе", _cut(job.prompt, 2000)]
    plan = getattr(job, "spec", None)
    if plan:
        parts += ["", "## Согласованный план (по нему проверяй «Готово, когда»)", _cut(plan.get("text", ""), 6000)]
    files = list(res.files or [])
    parts += ["", "## Изменённые файлы (пути от корня проекта)"]
    parts += [f"- {f}" for f in files[:FILES_LIMIT]] or ["- (нет)"]
    if len(files) > FILES_LIMIT:
        parts.append(f"- …и ещё {len(files) - FILES_LIMIT}")
    parts += ["", "## Итоговый ответ исполнителя владелице", _cut(res.text, ANSWER_LIMIT)]
    if tests is not None:
        parts += ["", "## Результаты тестов (хвост вывода)", _cut(tests, TESTS_LIMIT)]
    return "\n".join(parts)


def fix_prompt(verdict: dict) -> str:
    problems = verdict.get("problems") or ["(проверяющий не уточнил)"]
    return ("[Независимая проверка JARVIS] Проверяющий нашёл проблемы в твоём результате:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nИсправь их в тех же файлах (ничего не публикуй и не отправляй), затем ответь владелице "
              "заново полным итогом: что сделано и где лежит.")


def parse(res) -> dict | None:
    data = getattr(res, "structured", None)
    if getattr(res, "status", "") != "ok" or not isinstance(data, dict):
        return None
    if data.get("verdict") not in ("pass", "fix", "fail") or not isinstance(data.get("problems"), list):
        return None
    return {"verdict": data["verdict"], "problems": [str(p) for p in data["problems"]],
            "checked": [str(c) for c in data.get("checked") or []]}


def annotate(text: str, review: dict, by: str | None = None) -> str:
    """Строка для владелицы под ответом исполнителя (`by` — кто проверял, если не Claude)."""
    verdict, rounds = review.get("verdict"), review.get("rounds", 1)
    if verdict == "pass":
        tail = "✅ Перепроверил себя — всё в порядке" + (" (после правок)." if rounds > 1 else ".")
    elif verdict in ("fix", "fail"):
        problems = review.get("problems") or []
        head = "вышло не то, что просили" if verdict == "fail" else "остались замечания"
        tail = f"⚠️ Перепроверил себя — {head}:\n" + "\n".join(f"- {p}" for p in problems[:5])
    else:
        tail = f"⚠️ Перепроверить себя не вышло: {review.get('error') or 'нет вердикта'}."
    if by:
        tail = tail.replace("Перепроверил себя", f"Меня перепроверил {by}", 1)
    return ((text or "").rstrip() + "\n\n" + tail).strip()
