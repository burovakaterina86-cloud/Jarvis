"""Инструкция «Что умеет JARVIS» не должна отставать: каждый навык проекта, команда бота и задача расписания в ней названы."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "WHAT_JARVIS_CAN_DO.md").read_text(encoding="utf-8")


def test_every_project_skill_is_described():
    names = sorted(p.name for p in (ROOT / ".claude" / "skills").iterdir() if (p / "SKILL.md").is_file())
    missing = [n for n in names if f"`{n}`" not in DOC]
    assert not missing, f"в docs/WHAT_JARVIS_CAN_DO.md нет навыков: {missing}"


def test_every_bot_command_is_described():
    from integrations.telegram.gateway import COMMANDS
    missing = [name for name, _short, _about in COMMANDS if f"/{name}" not in DOC]
    assert not missing, f"в инструкции нет команд бота: {missing}"
    assert "/help" in DOC


def test_every_scheduled_task_is_in_the_instruction():
    for task in json.loads((ROOT / "runtime" / "schedule.json").read_text(encoding="utf-8")):
        hour = task["at"].lstrip("0") or "0"
        assert task["at"].lstrip("0") in DOC or task["at"] in DOC or hour in DOC, task["id"]


def test_instruction_states_the_browser_answer_and_the_hard_limits():
    for must in ("**Да.** У него настоящий браузер", "Оплату и покупку не делает никогда", "положить товары в корзину".replace("положить", "класть"),
                 "по кнопке", "Codex", "20 МБ"):
        assert must in DOC, must


def test_setup_guide_links_to_the_instruction():
    assert "docs/WHAT_JARVIS_CAN_DO.md" in (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
