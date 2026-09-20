"""Черновики навыков и помощников: проверка, активация, удаление.

Шов: `runtime.activation` — «папка drafts/ → проверенный перенос в .claude/».
Активацию делает этот модуль по нажатию владелицы; агенту запись в .claude/skills|agents
запрещена Guard'ом (интеграционный тест в конце файла).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from runtime import activation

REPO = Path(__file__).resolve().parents[1]

SKILL_FM = ("---\nname: {name}\ndescription: {desc}\nwhen_to_use: {when}\n---\n\n"
            "# {name}\n\nШаги.\n")
AGENT_FM = ("---\nname: {name}\ndescription: {desc}\ntools: Read, Grep\nmodel: sonnet\n---\n\n"
            "Ты помощник.\n")


def make_skill(root, name="post-checker", desc="Проверяет пост.", when="Когда нужен разбор.",
               test_md="Сценарий.\n\nРезультат: passed\n"):
    folder = root / "drafts" / "skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(SKILL_FM.format(name=name, desc=desc, when=when),
                                     encoding="utf-8")
    if test_md is not None:
        (folder / "TEST.md").write_text(test_md, encoding="utf-8")
    return folder


def make_agent(root, name="researcher", desc="Ищет факты и источники."):
    folder = root / "drafts" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(AGENT_FM.format(name=name, desc=desc), encoding="utf-8")
    return path


# ---------------------------------------------------------------- список


def test_list_drafts_reports_kind_description_and_test_result(tmp_path):
    make_skill(tmp_path, "post-checker", desc="Проверяет пост перед публикацией.")
    make_skill(tmp_path, "bad-skill", test_md="Сценарий.\n\nРезультат: failed\n")
    make_agent(tmp_path, "researcher", desc="Ищет факты и источники.")

    found = {(d.kind, d.name): d for d in activation.list_drafts(tmp_path)}
    assert set(found) == {("skill", "post-checker"), ("skill", "bad-skill"),
                          ("agent", "researcher")}
    assert found[("skill", "post-checker")].description == "Проверяет пост перед публикацией."
    assert found[("skill", "post-checker")].test_status == "passed"
    assert found[("skill", "bad-skill")].test_status == "failed"
    assert found[("agent", "researcher")].test_status == "none"


def test_test_status_comes_from_the_result_line_only(tmp_path):
    """Слово «пройден» в рассказе о прогоне — не результат. Результат — строка формата."""
    make_skill(tmp_path, "loose", test_md="Сценарий почти пройден, но я не дописал.\n")
    make_skill(tmp_path, "strict",
               test_md="Сначала не проходило.\n\nРезультат: passed\n")
    found = {d.name: d.test_status for d in activation.list_drafts(tmp_path)}
    assert found == {"loose": "none", "strict": "passed"}


def test_list_drafts_on_empty_project_is_empty(tmp_path):
    assert activation.list_drafts(tmp_path) == []


# ---------------------------------------------------------------- проверка


def test_validate_accepts_good_draft(tmp_path):
    make_skill(tmp_path)
    make_agent(tmp_path)
    assert activation.validate("skill", "post-checker", tmp_path) == []
    assert activation.validate("agent", "researcher", tmp_path) == []


@pytest.mark.parametrize("name", ["Post Checker", "post_checker", "ПостЧекер", "-post", "post-"])
def test_validate_rejects_bad_name(tmp_path, name):
    problems = activation.validate("skill", name, tmp_path)
    assert problems and any("имя" in p for p in problems)


def test_validate_rejects_path_traversal(tmp_path):
    make_skill(tmp_path)
    for name in ("../post-checker", r"..\post-checker", "sub/post-checker"):
        problems = activation.validate("skill", name, tmp_path)
        assert problems and any("имя" in p for p in problems)


def test_validate_rejects_missing_frontmatter(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "SKILL.md").write_text("# post-checker\n\nБез шапки.\n", encoding="utf-8")
    problems = activation.validate("skill", "post-checker", tmp_path)
    assert problems and any("frontmatter" in p for p in problems)


def test_validate_rejects_too_long_description(tmp_path):
    make_skill(tmp_path, desc="а" * 1500, when="б" * 100)
    problems = activation.validate("skill", "post-checker", tmp_path)
    assert problems and any("1536" in p for p in problems)


def test_validate_rejects_name_mismatch_and_missing_file(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "SKILL.md").write_text(SKILL_FM.format(name="другое", desc="Д.", when="К."),
                                     encoding="utf-8")
    assert any("name" in p for p in activation.validate("skill", "post-checker", tmp_path))
    assert any("нет черновика" in p for p in activation.validate("skill", "no-such", tmp_path))


def test_validate_allows_relative_paths_in_documentation(tmp_path):
    """Черновик — документ: упоминание пути в тексте не делает его побегом из песочницы."""
    folder = make_skill(tmp_path)
    (folder / "helper.md").write_text("Сравни с ../../essa-ai/VOICE.md и запиши вывод.\n",
                                      encoding="utf-8")
    assert activation.validate("skill", "post-checker", tmp_path) == []


def test_validate_rejects_symlinks(tmp_path):
    folder = make_skill(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("чужое", encoding="utf-8")
    try:
        (folder / "link.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("симлинки в этой системе не создаются без прав администратора")
    assert any("ссылк" in p for p in activation.validate("skill", "post-checker", tmp_path))


def test_validate_rejects_too_long_name(tmp_path):
    name = "a" * 65
    make_skill(tmp_path, name)
    problems = activation.validate("skill", name, tmp_path)
    assert problems and any("имя" in p for p in problems)
    assert activation.validate("skill", "a" * 64, tmp_path) != problems


def test_validate_rejects_name_taken_by_live_skill_in_other_case(tmp_path):
    """На Windows .claude/skills/Post-Checker и post-checker — один и тот же путь."""
    make_skill(tmp_path)
    live = tmp_path / ".claude" / "skills" / "Post-Checker"
    live.mkdir(parents=True)
    (live / "SKILL.md").write_text("старый навык", encoding="utf-8")
    problems = activation.validate("skill", "post-checker", tmp_path)
    assert problems and any("уже есть" in p for p in problems)


def test_validate_rejects_unknown_kind(tmp_path):
    assert activation.validate("hook", "post-checker", tmp_path)


# ---------------------------------------------------------------- активация


def test_activate_moves_skill_and_removes_draft(tmp_path):
    make_skill(tmp_path)
    target = activation.activate("skill", "post-checker", tmp_path)
    assert target == tmp_path / ".claude" / "skills" / "post-checker" / "SKILL.md"
    assert target.is_file()
    assert "name: post-checker" in target.read_text(encoding="utf-8")
    assert not (tmp_path / "drafts" / "skills" / "post-checker").exists()
    assert (tmp_path / ".claude" / "skills" / "post-checker" / "TEST.md").is_file()


def test_activate_moves_agent(tmp_path):
    make_agent(tmp_path)
    target = activation.activate("agent", "researcher", tmp_path)
    assert target == tmp_path / ".claude" / "agents" / "researcher.md"
    assert target.is_file()
    assert not (tmp_path / "drafts" / "agents" / "researcher.md").exists()


def test_activate_refuses_invalid_draft(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "SKILL.md").write_text("без шапки", encoding="utf-8")
    with pytest.raises(activation.ActivationError):
        activation.activate("skill", "post-checker", tmp_path)
    assert (folder / "SKILL.md").is_file()          # черновик на месте
    assert not (tmp_path / ".claude" / "skills" / "post-checker").exists()


def test_activate_refuses_to_overwrite_existing(tmp_path):
    make_skill(tmp_path)
    live = tmp_path / ".claude" / "skills" / "post-checker"
    live.mkdir(parents=True)
    (live / "SKILL.md").write_text("старый навык", encoding="utf-8")
    with pytest.raises(activation.ActivationError):
        activation.activate("skill", "post-checker", tmp_path)
    assert (live / "SKILL.md").read_text(encoding="utf-8") == "старый навык"


def test_activate_leaves_nothing_behind_when_the_move_breaks(tmp_path, monkeypatch):
    make_skill(tmp_path)

    def boom(src, dst):
        raise OSError("диск устал")

    monkeypatch.setattr(activation.os, "replace", boom)
    with pytest.raises(activation.ActivationError):
        activation.activate("skill", "post-checker", tmp_path)
    assert list((tmp_path / ".claude" / "skills").iterdir()) == []      # ни половины, ни мусора
    assert (tmp_path / "drafts" / "skills" / "post-checker" / "SKILL.md").is_file()


def test_discard_removes_draft_only(tmp_path):
    make_skill(tmp_path)
    make_agent(tmp_path)
    assert activation.discard("skill", "post-checker", tmp_path) is True
    assert not (tmp_path / "drafts" / "skills" / "post-checker").exists()
    assert activation.discard("agent", "researcher", tmp_path) is True
    assert activation.discard("agent", "researcher", tmp_path) is False
    with pytest.raises(activation.ActivationError):
        activation.discard("skill", "../secrets", tmp_path)


def test_ensure_dirs_creates_agents_folder_before_first_agent(tmp_path):
    activation.ensure_dirs(tmp_path)
    assert (tmp_path / ".claude" / "agents").is_dir()
    assert (tmp_path / "drafts" / "skills").is_dir()
    assert (tmp_path / "drafts" / "agents").is_dir()


# ---------------------------------------------------------------- Guard


GUARD = REPO / ".claude" / "hooks" / "guard.py"


def _guard_exit(tool: str, **tool_input):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event).encode("utf-8"),
                          capture_output=True, cwd=str(REPO))
    return proc.returncode, proc.stderr.decode("utf-8", "replace")


def test_guard_forbids_agent_writing_into_claude_skills_and_agents():
    """Активация — только через activation.py по кнопке; сам агент туда не пишет."""
    for path in (".claude/skills/новый/SKILL.md", ".claude/agents/researcher.md"):
        code, reason = _guard_exit("Write", file_path=path, content="x")
        assert code == 2, f"Guard пропустил запись в {path}"
        assert "JARVIS Guard" in reason
    code, _ = _guard_exit("Write", file_path="drafts/skills/новый/SKILL.md", content="x")
    assert code == 0, "черновик агент писать может"


# ---------------------------------------------------------------- базовые агенты


BASE_AGENTS = ["researcher", "competitor-analyst", "strategist", "copywriter",
               "reels-producer", "reviewer"]


def base_agent_file(name: str) -> tuple[str, Path]:
    """Где базовая роль лежит сейчас: черновиком или уже включённой.

    Владелица включает базовых помощников кнопкой, и активация переносит файл из
    `drafts/agents/` в `.claude/agents/`. Это правильное поведение продукта, поэтому
    роль проверяем там, где она реально лежит, и требуем ровно одно место из двух.
    """
    draft = REPO / "drafts" / "agents" / f"{name}.md"
    live = REPO / ".claude" / "agents" / f"{name}.md"
    assert draft.is_file() or live.is_file(), f"базовой роли {name} нет ни в drafts/, ни в .claude/"
    assert not (draft.is_file() and live.is_file()), \
        f"роль {name} лежит и черновиком, и включённой — активация не убрала черновик"
    return ("draft", draft) if draft.is_file() else ("live", live)


def test_base_agent_drafts_are_shipped_and_valid(tmp_path):
    # лишнего в drafts/agents/ быть не должно: там только ещё не включённые базовые роли
    drafts = REPO / "drafts" / "agents"
    extra = sorted(p.stem for p in drafts.glob("*.md")) if drafts.is_dir() else []
    assert set(extra) <= set(BASE_AGENTS), f"в drafts/agents/ лишние файлы: {extra}"

    copy = tmp_path / "drafts" / "agents"
    copy.mkdir(parents=True)
    for name in BASE_AGENTS:
        path = base_agent_file(name)[1]
        (copy / f"{name}.md").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        assert activation.validate("agent", name, tmp_path) == [], name


def test_base_agent_roles_and_minimal_tools():
    import yaml

    meta = {}
    for name in BASE_AGENTS:
        text = base_agent_file(name)[1].read_text(encoding="utf-8")
        meta[name] = yaml.safe_load(text.split("---\n")[1])
    # история 55: researcher и reviewer — только чтение, без записи и без shell
    for name in ("researcher", "reviewer"):
        tools = meta[name]["tools"]
        assert "Write" not in tools and "Edit" not in tools and "Bash" not in tools
    assert "browser" in meta["researcher"]["tools"]
    assert "screenshot" in meta["competitor-analyst"]["tools"]
    assert "VOICE.md" in meta["copywriter"]["description"]
    assert "STRATEGY.md" in meta["strategist"]["description"]


# ---------------------------------------------------------------- Telegram


from tests.test_telegram import (OWNER, FakeBot, FakeCallback,  # noqa: E402
                                 FakeContext, FakeUpdate, make_gateway)


async def test_new_draft_is_announced_once_with_buttons(tmp_path):
    make_skill(tmp_path, desc="Проверяет пост перед публикацией.")
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)

    assert [d.name for d in await g.check_drafts()] == ["post-checker"]
    assert await g.check_drafts() == []            # второй опрос молчит

    text = bot.sent[-1]["text"]
    assert "Новый навык post-checker" in text
    assert "Проверяет пост перед публикацией." in text
    assert "Тест: пройден" in text
    labels = [b.text for row in bot.sent[-1]["reply_markup"].inline_keyboard for b in row]
    assert labels == ["Активировать", "Посмотреть", "Удалить черновик"]


async def test_failed_test_is_shown_and_agent_draft_called_помощник(tmp_path):
    make_skill(tmp_path, "bad-skill", test_md="Сценарий.\n\nРезультат: failed\n")
    make_agent(tmp_path, "researcher", desc="Ищет факты.")
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    await g.check_drafts()
    texts = [m["text"] for m in bot.sent]
    assert any("Тест: не пройден" in t for t in texts)
    assert any("Новый помощник researcher" in t for t in texts)


async def test_watch_drafts_polls_on_interval_without_waiting(tmp_path):
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            make_skill(tmp_path)          # черновик появился между опросами
        if len(waits) >= 3:
            raise StopAsyncIteration

    with pytest.raises(StopAsyncIteration):
        await g.watch_drafts(sleep=fake_sleep)
    assert waits == [10.0, 10.0, 10.0]
    assert [d.name for d in await g.check_drafts()] == []   # уже объявлен в цикле
    assert any("post-checker" in m["text"] for m in g.bot.sent)


async def test_activate_button_moves_draft_into_claude(tmp_path):
    make_skill(tmp_path)
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    cb = FakeCallback(g.draft_callback_data("skill", "post-checker", "on"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext())
    assert (tmp_path / ".claude" / "skills" / "post-checker" / "SKILL.md").is_file()
    assert not (tmp_path / "drafts" / "skills" / "post-checker").exists()
    assert "включ" in cb.edits[-1]["text"].lower()
    assert cb.edits[-1].get("reply_markup") is None


async def test_activate_button_reports_refusal_and_keeps_draft(tmp_path):
    folder = make_skill(tmp_path)
    (folder / "SKILL.md").write_text("без шапки", encoding="utf-8")
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    cb = FakeCallback(g.draft_callback_data("skill", "post-checker", "on"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext())
    assert "frontmatter" in cb.edits[-1]["text"]
    assert (folder / "SKILL.md").is_file()


async def test_show_button_sends_the_file(tmp_path):
    make_skill(tmp_path)
    g = make_gateway(tmp_path)
    bot = FakeBot()
    g.attach(bot)
    cb = FakeCallback(g.draft_callback_data("skill", "post-checker", "show"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=cb), FakeContext(bot=bot))
    assert [d["filename"] for d in bot.documents] == ["post-checker-SKILL.md",
                                                      "post-checker-TEST.md"]
    assert b"name: post-checker" in bot.documents[0]["document"]
    assert b"passed" in bot.documents[1]["document"]
    assert (tmp_path / "drafts" / "skills" / "post-checker").is_dir()


async def test_discard_asks_before_deleting(tmp_path):
    make_skill(tmp_path)
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    ask = FakeCallback(g.draft_callback_data("skill", "post-checker", "rm"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=ask), FakeContext())
    assert (tmp_path / "drafts" / "skills" / "post-checker").is_dir()   # ещё не удалён
    labels = [b.text for row in ask.edits[-1]["reply_markup"].inline_keyboard for b in row]
    assert labels == ["Да, удалить", "Отмена"]

    yes = FakeCallback(g.draft_callback_data("skill", "post-checker", "rm2"))
    await g.on_callback(FakeUpdate(OWNER, callback_query=yes), FakeContext())
    assert not (tmp_path / "drafts" / "skills" / "post-checker").exists()
    assert "удалил" in yes.edits[-1]["text"].lower()


async def test_stranger_cannot_activate_a_draft(tmp_path):
    make_skill(tmp_path)
    g = make_gateway(tmp_path)
    g.attach(FakeBot())
    data = g.draft_callback_data("skill", "post-checker", "on")
    cb = FakeCallback(data, user_id=999999)
    await g.on_callback(FakeUpdate(999999, callback_query=cb), FakeContext())
    assert (tmp_path / "drafts" / "skills" / "post-checker").is_dir()
