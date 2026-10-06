"""Таск 14: картинки в основном сценарии content-plan, проверка хуков, зеркало навыков.

Ожидаемые значения — из тикета 14 и AGENTS.md, а не из проверяемого кода.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_check_hooks():
    spec = importlib.util.spec_from_file_location("check_hooks", ROOT / "scripts" / "check_hooks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- content-plan: шаг оформления картинок ---

CONTENT_PLAN = ROOT / ".claude" / "skills" / "content-plan" / "SKILL.md"


def _paragraphs(text: str) -> list[str]:
    return [p for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]


def test_content_plan_calls_carousel_skill_and_build_command():
    text = CONTENT_PLAN.read_text(encoding="utf-8")
    assert "carousel-instagram" in text
    # карусель — редакционной сборкой в её «стиле 2» (2026-09-25), с картой ритма
    assert "-m integrations.visuals.editorial" in text
    assert "slides.json" in text and "карта ритма" in text.lower()
    # обложка поста и сторис — пока старой сборкой
    assert "-m integrations.visuals.build" in text
    # обложка поста и фон сторис — тем же навыком
    assert "обложка поста" in text.lower() and "фон сторис" in text.lower()


def test_content_plan_gives_texts_even_when_build_fails():
    text = CONTENT_PLAN.read_text(encoding="utf-8")
    hits = [p for p in _paragraphs(text) if "код выхода" in p.lower()]
    assert hits, "нет правила про код выхода сборки"
    rule = hits[0]
    assert "не 0" in rule and "картинок нет" in rule
    assert "тексты" in rule.lower() and "всё равно" in rule
    # формулировки кодов живут в carousel-instagram — здесь ссылка, а не копия
    assert "carousel-instagram/SKILL.md" in rule
    assert "PNG не сняты" not in text


def test_content_plan_reply_says_where_pictures_are():
    text = CONTENT_PLAN.read_text(encoding="utf-8").replace("\r\n", "\n")
    reply = text.split("## Шаг 9. Ответ в Telegram", 1)[1].split("\n## ", 1)[0]
    assert "visuals/" in reply


def test_content_plan_still_publishes_nothing():
    text = CONTENT_PLAN.read_text(encoding="utf-8")
    assert "Ничего не публикует" in text and "не публикуешь сам" in text


# --- рендер на чистой установке ---

def test_playwright_is_a_declared_dependency():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "playwright==1.63.0" in [r.strip() for r in reqs]  # версия из `pip show playwright`
    setup = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
    assert "python -m playwright install chromium" in setup


# --- зеркало навыков .agents/skills/ ---
# Правило зеркала взято из уже синхронизированных папок: пути `.claude/` → `.Codex/`,
# `CLAUDE.md` → `AGENTS.md`, концы строк не важны (core.autocrlf). `autopilot` — чужой
# навык со своими путями установки (~/.claude/skills), его зеркало — дословная копия.

SKILLS = ROOT / ".claude" / "skills"
MIRROR = ROOT / ".agents" / "skills"
VERBATIM = {"autopilot"}


def _files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def _mirrored(skill: str, data: bytes) -> bytes:
    data = data.replace(b"\r\n", b"\n")
    if skill in VERBATIM:
        return data
    return data.replace(b".claude", b".Codex").replace(b"CLAUDE.md", b"AGENTS.md")


@pytest.mark.parametrize("skill", sorted(p.name for p in SKILLS.iterdir() if p.is_dir()))
def test_skill_matches_its_mirror(skill):
    src, dst = SKILLS / skill, MIRROR / skill
    assert dst.is_dir(), f"нет зеркала .agents/skills/{skill}"
    assert _files(dst) == _files(src)
    stale = [rel for rel in sorted(_files(src))
             if _mirrored(skill, (src / rel).read_bytes())
             != (dst / rel).read_bytes().replace(b"\r\n", b"\n")]
    assert not stale, f"зеркало устарело: {stale}"


def test_mirror_has_no_orphans():
    assert {p.name for p in MIRROR.iterdir() if p.is_dir()} <= {p.name for p in SKILLS.iterdir()}


# --- проверка хуков: заслон больших файлов через decide ---

def test_check_hooks_covers_big_read_through_decide(tmp_path):
    check_hooks = _load_check_hooks()
    results = check_hooks.big_read_results(tmp_path)
    # её решение 2026-10-06 (external.big_read: auto): файл >100 КБ целиком и кусок проходят без кнопки
    assert [actual for _title, _expected, actual in results] == ["allow", "allow"]
    assert all(expected == actual for _title, expected, actual in results)


# --- проверка хуков: bash как у Claude Code (Git Bash), а не WSL из System32 ---

def _fake_git(tmp_path: Path) -> Path:
    git_root = tmp_path / "Git"
    (git_root / "cmd").mkdir(parents=True)
    (git_root / "bin").mkdir()
    (git_root / "cmd" / "git.exe").write_bytes(b"")
    bash = git_root / "bin" / "bash.exe"
    bash.write_bytes(b"")
    return bash


def test_find_bash_skips_wsl_and_takes_git_bash(tmp_path, monkeypatch):
    check_hooks = _load_check_hooks()
    git_bash = _fake_git(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_GIT_BASH_PATH", raising=False)
    paths = {"bash": r"C:\Windows\System32\bash.exe",
             "git": str(tmp_path / "Git" / "cmd" / "git.exe")}
    monkeypatch.setattr(check_hooks.shutil, "which", lambda name: paths.get(name))
    assert Path(check_hooks.find_bash()) == git_bash


def test_find_bash_refuses_when_only_wsl_bash(tmp_path, monkeypatch):
    check_hooks = _load_check_hooks()
    monkeypatch.delenv("CLAUDE_CODE_GIT_BASH_PATH", raising=False)
    monkeypatch.setattr(check_hooks.shutil, "which",
                        lambda name: r"C:\Windows\System32\bash.exe" if name == "bash" else None)
    monkeypatch.setattr(check_hooks, "GIT_BASH_GUESSES", [str(tmp_path / "нет" / "bash.exe")])
    assert check_hooks.find_bash() is None
