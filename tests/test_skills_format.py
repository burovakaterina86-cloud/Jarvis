"""Формат навыков JARVIS, .mcp.json и команда integrations/browser/login.py.

Лимиты — из документации Claude Code (code.claude.com/docs/en/skills):
description + when_to_use ≤ 1536 символов, тело SKILL.md ≤ 500 строк.
Навык сборки `autopilot` принадлежит среде разработки и не проверяется.
"""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"
EXCLUDED = {"autopilot"}
REQUIRED = {
    "trend-radar", "competitor-research", "content-strategy", "content-plan",
    "copywriting", "reels-script", "repurpose-content", "browser-use",
}


def _skill_dirs():
    found = {p.name for p in SKILLS.iterdir() if p.is_dir()} if SKILLS.exists() else set()
    return sorted((found - EXCLUDED) | REQUIRED)


def _parse(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md должен начинаться с frontmatter"
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


def _read(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", _skill_dirs())
def test_skill_frontmatter_and_limits(name):
    assert (SKILLS / name / "SKILL.md").is_file(), f"нет навыка {name}"
    meta, body = _parse(name)
    assert isinstance(meta, dict)
    assert meta.get("name") == name
    desc = meta.get("description")
    when = meta.get("when_to_use")
    assert isinstance(desc, str) and desc.strip()
    assert isinstance(when, str) and when.strip()
    assert len(desc) + len(when) <= 1536
    assert len(body.splitlines()) <= 500
    assert "[ЗАПОЛНИ" not in desc  # описание — не шаблон


def test_content_plan_chain_storage_and_no_publishing():
    text = _read("content-plan")
    for step in ("GOALS.md", "STRATEGY.md", "PUBLISHED.md", "trend-radar",
                 "competitor-research", "content-strategy", "copywriting",
                 "reels-script", "Stories"):
        assert step in text, step
    assert "essa-ai/content/YYYY-MM-DD-<тема>/" in text
    for f in ("post.md", "carousel.md", "reels.md", "stories.md", "sources.md", "status"):
        assert f"`{f}`" in text, f
    assert "draft" in text
    assert "Не публикуй" in text


def test_content_plan_edge_rules():
    text = _read("content-plan")
    # история 34, 28, 35
    assert "прошлых материалов нет, опираюсь на STRATEGY.md и тренды" in text
    assert "[ЗАПОЛНИ" in text
    assert "гипотеза" in text


def test_browser_use_covers_errands():
    text = _read("browser-use")
    for tool in ("browser_snapshot", "browser_take_screenshot", "browser_navigate",
                 "browser_click", "browser_type"):
        assert tool in text, tool
    for topic in ("Корзина", "Билеты", "три варианта", "оплати сама", "Instagram",
                  "капч", "SMS", "нужен ты:", "/browser login"):
        assert topic in text, topic


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_skills_reference_rules_instead_of_copying_policy(name):
    """Политика живёт в .claude/rules/, навык на неё ссылается, а не пересказывает."""
    text = _read(name)
    if name == "browser-use":
        assert ".claude/rules/safety.md" in text
        assert ".claude/rules/approvals.md" in text
        assert ".claude/rules/untrusted-content.md" in text
    # уровни безопасности описаны в правилах, а не в каждом навыке
    assert "EXTERNAL" not in text or name == "browser-use"


def test_content_plan_forbids_publishing_explicitly():
    text = _read("content-plan")
    assert "не публикуешь сам" in text
    assert "инструментов публикации у тебя нет" not in text


def test_mcp_profile_path_matches_login_module():
    from integrations.browser import PROFILE_DIR, profile_path

    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    args = cfg["mcpServers"]["playwright"]["args"]
    assert "@playwright/mcp@latest" in args
    assert not any("dangerously" in str(a) for a in args)
    from_mcp = Path(args[args.index("--user-data-dir") + 1])
    assert from_mcp.is_absolute(), "путь профиля не должен зависеть от рабочей папки MCP"
    assert from_mcp == profile_path() == ROOT / PROFILE_DIR


def test_mcp_browser_matches_installed_browser():
    from integrations.browser.login import find_browser, mcp_browser_name

    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    args = cfg["mcpServers"]["playwright"]["args"]
    assert args[args.index("--browser") + 1] == mcp_browser_name(find_browser())


def _fake_browsers(tmp_path, *rel_paths):
    for rel in rel_paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")


def test_find_browser_prefers_edge_from_program_files(tmp_path):
    from integrations.browser.login import find_browser, mcp_browser_name

    _fake_browsers(tmp_path,
                   r"pf86\Microsoft\Edge\Application\msedge.exe",
                   r"pf\Google\Chrome\Application\chrome.exe")
    env = {"PROGRAMFILES": str(tmp_path / "pf"),
           "PROGRAMFILES(X86)": str(tmp_path / "pf86"),
           "LOCALAPPDATA": str(tmp_path / "local")}
    found = find_browser(env)
    assert found.name == "msedge.exe"
    assert mcp_browser_name(found) == "msedge"


def test_find_browser_falls_back_to_chrome_in_localappdata(tmp_path):
    from integrations.browser.login import find_browser, mcp_browser_name

    _fake_browsers(tmp_path, r"local\Google\Chrome\Application\chrome.exe")
    env = {"PROGRAMFILES": str(tmp_path / "pf"),
           "PROGRAMFILES(X86)": str(tmp_path / "pf86"),
           "LOCALAPPDATA": str(tmp_path / "local")}
    found = find_browser(env)
    assert found.name == "chrome.exe"
    assert mcp_browser_name(found) == "chrome"


def test_find_browser_missing_raises(tmp_path):
    from integrations.browser.login import find_browser

    env = {"PROGRAMFILES": str(tmp_path / "pf"), "LOCALAPPDATA": str(tmp_path / "local")}
    with pytest.raises(FileNotFoundError):
        find_browser(env)


def test_login_build_command():
    from integrations.browser.login import build_command, profile_path

    cmd = build_command("https://example.com", browser_path=Path(r"C:\edge\msedge.exe"))
    assert cmd[0] == str(Path(r"C:\edge\msedge.exe"))
    assert f"--user-data-dir={profile_path()}" in cmd
    assert cmd[-1] == "https://example.com"
    assert not any("headless" in a for a in cmd)


def test_login_rejects_non_http_url():
    from integrations.browser.login import build_command

    with pytest.raises(ValueError):
        build_command("file:///C:/Windows/win.ini", browser_path=Path(r"C:\edge\msedge.exe"))


def test_login_main_without_args_returns_2(capsys):
    from integrations.browser import login

    assert login.main([]) == 2


def test_login_main_waits_for_owner_confirmation(monkeypatch, capsys):
    """Окно может достаться уже запущенному браузеру — ждём Enter от владелицы."""
    from integrations.browser import login

    calls = {}
    monkeypatch.setattr(login.subprocess, "Popen", lambda cmd, **kw: calls.setdefault("cmd", cmd))
    monkeypatch.setattr(login, "find_browser", lambda env=None: Path(r"C:\edge\msedge.exe"))
    monkeypatch.setattr("builtins.input", lambda *a: calls.setdefault("waited", True) or "")
    assert login.main(["https://example.com"]) == 0
    assert calls["waited"] is True
    assert calls["cmd"][-1] == "https://example.com"
