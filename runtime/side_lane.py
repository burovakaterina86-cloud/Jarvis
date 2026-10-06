"""Быстрая полоса: короткий вопрос, пока идёт долгая задача, получает ответ сразу.

Её жалоба 2026-10-06: «если пишу следом вопрос, он не может сразу ответить». Очередь чата — одна активная задача, всё
остальное ждало. Теперь вопрос-в-пути (короткий, со знаком вопроса или «ты здесь», «как там», «что с…») идёт в
отдельную очередь `side` параллельно основной задаче: свой лёгкий ход только на чтение (настройки проверяющего),
без истории, ≤ 6 шагов. Он не знает хода основной задачи изнутри — ему даёт срез Python: что за задача, её последние
шаги из журнала, фоновые работы. Просьба что-то СДЕЛАТЬ в быструю полосу не попадает: модель отвечает «ОЧЕРЕДЬ», и бот
ставит сообщение в обычную очередь.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from runtime import review, task_state
from runtime.claude_bridge import TurnOptions

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "runtime" / "prompts" / "side-lane.md"
TIMEOUT_SEC = 120
MAX_QUESTION_LEN = 160
RECENT_STEPS = 8
OPTIONS = TurnOptions(settings=review.SETTINGS, prompt_file=PROMPT, max_turns=6, persist=False, read_only=True,
                      browser=False)

_STARTERS = ("ты здесь", "ты тут", "что с ", "как там", "как дела", "как идёт", "как идет", "сколько ещё", "сколько еще",
             "сколько осталось", "когда будет", "когда готов", "где ", "что делаешь", "что происходит", "что сейчас",
             "готово", "долго ещё", "долго еще", "статус", "что по ", "работаешь", "живой", "алло", "эй")


def looks_like_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or t.startswith("/") or len(t) > MAX_QUESTION_LEN or "\n" in t.strip():
        return False
    return t.endswith("?") or t.startswith(_STARTERS)


def wants_queue(answer: str) -> bool:
    """Модель увидела просьбу сделать работу, а не вопрос: ответ — одно слово ОЧЕРЕДЬ."""
    return bool(re.match(r"^\s*ОЧЕРЕДЬ\b", answer or "", re.I))


def _recent_steps(events_path: Path, task_id: str) -> list[str]:
    try:
        lines = events_path.read_text(encoding="utf-8", errors="replace").splitlines()[-600:]
    except OSError:
        return []
    steps = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("task_id") != task_id and ev.get("task") is None:
            continue
        kind = ev.get("type")
        if kind == "assistant_message" and ev.get("text") and (ev.get("task_id") in (None, task_id)):
            steps.append("сказал: " + re.sub(r"\s+", " ", str(ev["text"]))[:160])
        elif kind == "tool_use" and ev.get("task_id") == task_id:
            steps.append("инструмент " + str(ev.get("tool") or "?"))
    return steps[-RECENT_STEPS:]


def context(root: Path, chat_id) -> str:
    """Срез «что сейчас происходит» для быстрого ответа."""
    root = Path(root)
    events_path = root / "state" / "events.jsonl"
    lines = ["## Что сейчас происходит"]
    try:
        snap = task_state.snapshot(events_path, chat=chat_id)
    except Exception:  # noqa: BLE001 — срез не должен ронять ответ
        snap = {"active": None, "queued": []}
    active = snap.get("active")
    if active:
        lines.append(f"Основная задача: «{active.get('task', '?')}», состояние: {active.get('state')}, с {active.get('since', '')[11:19]} UTC.")
        steps = _recent_steps(events_path, active.get("task_id", ""))
        if steps:
            lines.append("Последние шаги: " + "; ".join(steps))
    else:
        lines.append("Основной задачи сейчас нет.")
    if snap.get("queued"):
        lines.append("В очереди: " + ", ".join(f"«{t.get('task', '?')}»" for t in snap["queued"][:4]))
    try:
        from integrations.jobs import read_states
        jobs = [j for j in read_states(root) if j.get("status") in ("queued", "running")]
    except Exception:  # noqa: BLE001
        jobs = []
    if jobs:
        lines.append("Фоновые работы (их ведёт бот, чат они не держат): "
                     + "; ".join(f"«{j['title']}» — {'идёт' if j['status'] == 'running' else 'ждёт очереди'}" for j in jobs))
    return "\n".join(lines)


def build_prompt(root: Path, chat_id, question: str) -> str:
    return f"{context(root, chat_id)}\n\n## Вопрос владелицы\n{question.strip()}"
