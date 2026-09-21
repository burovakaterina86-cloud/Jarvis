"""Конвейер текста: textwriter → humaniser → сверка с VOICE → финал.

Швы из спецификации, «История 1 — конвейер текста»:
её контракт `content brief → textwriter → humaniser → VOICE/preflight → final`,
пять запретов `humaniser`, порядок источников при конфликте
и видимая отметка о проходе в папке комплекта.

Ожидаемые значения берутся из её файлов `essa-ai/SKILL_*.md` — источника истины
переноса, — а не из текста навыка, который этот тест и проверяет.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
ESSA = ROOT / "essa-ai"

# Её формулировка запрета, из `SKILL_humaniser.md`: «REWRITER НЕ ИМЕЕТ ПРАВА».
BAN_HEADINGS = {"humaniser": "НЕ ИМЕЕТ ПРАВА:", "textwriter": "НЕЛЬЗЯ:"}
# Пять неприкосновенных полей — из спецификации, «История 1».
FIVE_FIELDS = ["FUNNEL_STAGE", "FUNCTION", "BELIEF_BEFORE", "MAIN_IDEA", "CTA"]


def _skill(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _agent(name):
    return (ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")


def _source(name):
    return (ESSA / f"SKILL_{name}.md").read_text(encoding="utf-8")


def _bullets_after(text, heading):
    """Пункты списка `- …` после строки с заголовком, до конца списка."""
    tail = text.split(heading, 1)[1]
    items = []
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].rstrip(";."))
        elif items and line:
            break
    return items


def _numbered_after(text, heading):
    """Пункты нумерованного списка после строки с заголовком."""
    tail = text.split(heading, 1)[1]
    items = []
    for raw in tail.splitlines():
        line = raw.strip()
        m = re.match(r"\d+\.\s+(.*)", line)
        if m:
            items.append(m.group(1).rstrip(";."))
        elif items and line and raw[:1].isspace():
            items[-1] += " " + line  # продолжение того же шага
        elif items and line:
            break
    return items


def _steps(text, heading):
    """Шаги инструкции как отдельные элементы — чтобы проверять порядок шагов,
    а не порядок слов в одной строке схемы."""
    return _numbered_after(text, heading)


@pytest.mark.parametrize("name", ["humaniser", "textwriter"])
def test_bans_transferred_verbatim_from_her_file(name):
    source_bans = _bullets_after(_source(name), BAN_HEADINGS[name])
    assert len(source_bans) >= 5, "список запретов в её файле не разобрался"
    skill = _skill(name)
    for ban in source_bans:
        assert ban in skill, f"{name}: потерян запрет из essa-ai — {ban}"


def test_humaniser_keeps_five_bans_from_spec():
    """Пять полей, которые humaniser менять не вправе, — из её же списка запретов."""
    source_bans = _bullets_after(_source("humaniser"), BAN_HEADINGS["humaniser"])
    skill = _skill("humaniser")
    for field in FIVE_FIELDS:
        matching = [b for b in source_bans if field in b]
        assert matching, f"в essa-ai нет запрета про {field}"
        for ban in matching:
            assert ban in skill, f"потерян запрет про {field}: {ban}"


@pytest.mark.parametrize("name", ["humaniser", "textwriter"])
def test_source_priority_matches_her_file(name):
    """Приоритет источников при конфликте — её порядок, пункт в пункт."""
    source_order = _numbered_after(_source(name), "Приоритет:")
    assert len(source_order) >= 5, "приоритет в её файле не разобрался"
    assert _numbered_after(_skill(name), "Приоритет:") == source_order


@pytest.mark.parametrize("name", ["humaniser", "textwriter"])
def test_both_passes_name_her_source_priority(name):
    text = _skill(name)
    order = [text.index(x) for x in ("текущий запрос", "11_DECISION_LOG.md",
                                     "VOICE.md", "07_CONTENT_RULES.md")]
    assert order == sorted(order), f"{name}: порядок источников нарушен"


def test_textwriter_hands_off_to_next_pass():
    """Первый проход обязан передать текст второму — её же строкой."""
    handoff = "Перед выдачей передай текст в обязательный следующий pass: `humaniser`."
    assert handoff in _source("textwriter"), "её формулировка передачи изменилась"
    assert handoff in _skill("textwriter")


def _pipeline_contract():
    contract = "content brief → textwriter → humaniser → VOICE/preflight → final"
    assert contract in _source("humaniser"), "контракт конвейера в essa-ai изменился"
    return contract


def test_copywriting_calls_both_passes_as_separate_steps():
    text = _skill("copywriting")
    assert _pipeline_contract() in text
    steps = _steps(text, "её контракт")
    assert len(steps) >= 3, "конвейер в copywriting не разложен на шаги"
    first = next(i for i, s in enumerate(steps) if "textwriter" in s)
    second = next(i for i, s in enumerate(steps) if "humaniser" in s)
    assert first < second, "humaniser должен идти отдельным шагом после textwriter"
    assert any("VOICE" in s for s in steps[second + 1:]), "сверка с VOICE — после очистки"


def test_copywriting_forbids_single_pass_writing():
    """Утверждение должно ловить именно запрет, а не упоминание «в один проход»."""
    text = _skill("copywriting")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if "в один проход" in s]
    assert sentences, "запрет однопроходной записи не найден"
    assert all(re.search(r"\b(не|нельзя)\b", s) for s in sentences), sentences


def test_copywriter_agent_calls_pipeline_as_separate_steps():
    text = _agent("copywriter")
    steps = _steps(text, "## Как работать")
    first = next(i for i, s in enumerate(steps) if "textwriter" in s)
    second = next(i for i, s in enumerate(steps) if "humaniser" in s)
    assert first < second, "помощник обязан звать humaniser отдельным шагом после textwriter"
    assert any("VOICE" in s for s in steps[second + 1:]), "сверка с VOICE — после очистки"


def test_pass_leaves_visible_mark_in_content_folder():
    for text in (_skill("humaniser"), _skill("copywriting")):
        assert "<!-- pipeline: textwriter → humaniser → VOICE — пройден" in text


def test_failed_pass_still_reaches_owner_with_honest_mark():
    """Отказ — не запрет на выдачу: текст доходит, но с честной пометкой."""
    for text in (_skill("humaniser"), _skill("copywriting")):
        mark = re.search(r"<!-- pipeline: humaniser НЕ пройден — (.+?)-->", text)
        assert mark, "нет пометки о непройденной очистке"
        assert "причина" in mark.group(1), "пометка обязана назвать причину"
        fallback = [s for s in re.split(r"(?<=[.!?])\s+", text) if "НЕ пройден" in s or "не выполнен" in s]
        assert any("доходит до владелицы" in s for s in fallback), \
            "не сказано, что текст всё равно доходит до владелицы"
