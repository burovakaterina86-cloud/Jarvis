"""Навыки, забранные с чужого публичного репозитория.

Реестр владелицы — `essa-ai/AGENTOS_CHATGPT_CORE.md`, ссылки `raw:` с зафиксированным
коммитом. Проверяем три вещи, ради которых таск и делался: у каждого записано
происхождение с тем самым коммитом; в каждом сказано, что её файлы и правила JARVIS
главнее upstream; ничего исполняемого из интернета в репозитории нет.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"

COMMIT = "3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802"
UPSTREAM = [
    "instagram-superpower",
    "topic-monitor",
    "threads-content",
    "transcript",
    "agentos-content",
]


def _read(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", UPSTREAM)
def test_upstream_skill_records_origin_with_commit(name):
    """Владелица должна видеть, что это не наше и откуда именно взялось."""
    text = _read(name)
    assert "## Происхождение" in text
    assert (
        f"https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/{COMMIT}"
        f"/skills/{name}/SKILL.md" in text
    ), "нужна pinned-ссылка с коммитом из её реестра"
    assert "дата забора: 2026-09-21" in text


@pytest.mark.parametrize("name", UPSTREAM)
def test_upstream_skill_subordinates_itself_to_her_files(name):
    """При расхождении побеждают её файлы и правила JARVIS, а не upstream."""
    text = _read(name)
    assert "## Главнее upstream" in text
    assert "essa-ai/" in text
    assert ".claude/rules/" in text
    assert "побеждают её файлы и правила JARVIS" in text
    # публикация, отправка и оплата — только через кнопку владелицы
    assert "«Подтвердить»" in text


@pytest.mark.parametrize("name", UPSTREAM)
def test_upstream_skill_marks_what_it_cannot_do_here(name):
    """Скрипты и ключи upstream не переносились — навык обязан сказать это видимо."""
    text = _read(name)
    assert "> **Не подключено:**" in text


@pytest.mark.parametrize("name", UPSTREAM)
def test_no_executables_came_from_the_internet(name):
    """Из интернета берём только SKILL.md: ни скриптов, ни бинарников, ни конфигов."""
    files = sorted(p.name for p in (SKILLS / name).rglob("*") if p.is_file())
    assert files == ["SKILL.md"], f"лишние файлы в навыке {name}: {files}"


@pytest.mark.parametrize("name", UPSTREAM)
def test_upstream_skill_keeps_its_own_name_in_frontmatter(name):
    text = _read(name)
    _, fm, _body = text.split("---\n", 2)
    meta = yaml.safe_load(fm)
    assert meta["name"] == name
