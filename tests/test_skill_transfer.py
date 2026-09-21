"""Перенос её адаптеров `essa-ai/SKILL_*.md` в навыки JARVIS.

Швы из спецификации, «История 3 — перенос её скиллов»: смысл и правила взяты
из её файлов дословно, `present` не переносится, существующие навыки JARVIS
не дублируются вслепую, а `create-skill` выдаёт новый навык в её же виде.

Ожидаемые значения берутся из её файлов в `essa-ai/`, а не из текста навыка,
который этот тест и проверяет.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
ESSA = ROOT / "essa-ai"

# Переносятся два адаптера; `present` (презентации) — намеренно нет.
TRANSFERRED = ["reels", "content-engine"]
# Пары «её навык ↔ существующий навык JARVIS про то же самое».
PAIRS = {"reels": "reels-script", "content-engine": "content-plan"}
# Шаг контракта, который был про порт в ChatGPT, а не про ремесло: он не переносится.
CHATGPT_ONLY = "CAPABILITY_MAPPING.md"


def _skill(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _source(name):
    return (ESSA / f"SKILL_{name}.md").read_text(encoding="utf-8")


def _field(text, key):
    m = re.search(rf"^- {key}: (.+)$", text, re.M)
    assert m, f"в её файле нет поля {key}"
    return m.group(1).strip()


def _bullets_after(text, heading):
    tail = text.split(heading, 1)[1]
    items = []
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line:
            break
    return items


def _numbered_after(text, heading):
    tail = text.split(heading, 1)[1]
    items = []
    for raw in tail.splitlines():
        line = raw.strip()
        m = re.match(r"\d+\.\s+(.*)", line)
        if m:
            items.append(m.group(1).strip())
        elif items and line and raw[:1].isspace():
            items[-1] += " " + line
        elif items and line:
            break
    return items


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


@pytest.mark.parametrize("name", TRANSFERRED)
def test_purpose_transferred_from_her_file(name):
    purpose = _field(_source(name), "purpose")
    assert purpose.rstrip(".") in _skill(name), f"{name}: потеряно назначение из essa-ai"


@pytest.mark.parametrize("name", TRANSFERRED)
def test_activation_triggers_transferred_from_her_file(name):
    triggers = [t.strip("`") for t in _bullets_after(_source(name), "## Activation")]
    assert len(triggers) >= 4, "список активации в её файле не разобрался"
    skill = _skill(name)
    for trigger in triggers:
        assert trigger in skill, f"{name}: потерян триггер из essa-ai — {trigger}"


@pytest.mark.parametrize("name", TRANSFERRED)
def test_execution_contract_transferred_verbatim(name):
    steps = _numbered_after(_source(name), "## ChatGPT execution contract")
    assert len(steps) >= 6, "контракт в её файле не разобрался"
    assert any(CHATGPT_ONLY in s for s in steps), \
        "шаг про перенос в ChatGPT исчез из её файла — исключение больше не осознанное"
    skill = _skill(name)
    for step in steps:
        if CHATGPT_ONLY in step:
            continue
        assert step.rstrip(".") in skill, f"{name}: потерян шаг контракта — {step}"


@pytest.mark.parametrize("name", TRANSFERRED)
def test_skill_names_her_file_as_source_of_truth(name):
    assert f"essa-ai/SKILL_{name}.md" in _skill(name), \
        f"{name}: не назван источник истины в essa-ai"


@pytest.mark.parametrize("name", TRANSFERRED)
def test_pair_says_who_calls_whom(name):
    """Ни одна пара не дублируется вслепую: направление вызова названо словами,
    и названо в порядке «кто → кого»."""
    partner = PAIRS[name]
    pair = [s for s in _sentences(_skill(name))
            if name in s and partner in s and "вызыва" in s]
    assert pair, f"{name}: не сказано, кто кого вызывает в паре с {partner}"
    caller_first = [s for s in pair if s.index(name) < s.index(partner)]
    assert caller_first, f"{name}: направление вызова с {partner} не прочитывается"


@pytest.mark.parametrize("name", TRANSFERRED)
def test_pair_does_not_copy_partner_format(name):
    """Где навыки про одно и то же — ссылка, а не второй экземпляр формата."""
    partner_text = _skill(PAIRS[name])
    # Формат партнёра — это его шаблоны в блоках кода и перечень файлов комплекта.
    signature = re.findall(r"```.*?```", partner_text, re.S)
    signature += [l.strip() for l in partner_text.splitlines()
                  if re.match(r"- `[\w-]+\.md`", l.strip())]
    assert signature, f"у {PAIRS[name]} не разобрался формат"
    skill = _skill(name)
    for piece in signature:
        assert piece not in skill, f"{name}: формат {PAIRS[name]} скопирован, а не вызван"


def test_create_skill_template_repeats_her_adapter_shape():
    """Новый навык, который агент напишет сам, должен ложиться в вид её адаптеров:
    назначение, когда применять, приоритет источников, что запрещено менять."""
    adapter, rules = _source("reels"), _source("textwriter")
    assert "- purpose:" in adapter and "## Activation" in adapter, \
        "вид её адаптера изменился"
    assert "Приоритет:" in rules and "НЕЛЬЗЯ:" in rules, \
        "её разделы приоритета и запретов изменились"

    text = _skill("create-skill")
    template = text.split("## Формат `SKILL.md`", 1)[1].split("## Формат `TEST.md`", 1)[0]
    for part in ("Назначение", "Activation", "Приоритет", "НЕЛЬЗЯ"):
        assert part in template, f"в шаблоне create-skill нет раздела {part}"


def test_create_skill_keeps_quarantine_in_drafts():
    text = _skill("create-skill")
    assert "drafts/skills/" in text
    assert ".claude/skills/` тебе запрещено" in text


def test_present_skill_not_transferred():
    """Про презентации в задаче владелицы нет ни слова — адаптер остаётся в essa-ai."""
    assert (ESSA / "SKILL_present.md").is_file(), "её файл про презентации исчез"
    assert not (SKILLS / "present").exists(), "навык present перенесён, хотя не просили"
