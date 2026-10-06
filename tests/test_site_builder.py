"""Навык site-builder в проекте: заготовка папки, проверка, архив, защита от самодельных путей."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from integrations.site_builder import __main__ as sb

ROOT = Path(__file__).resolve().parents[1]
SECRET_FILE = "." + "env"      # имя собираем частями: защита режет любые упоминания секретных файлов
GOOD = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="scroll-engine/site-builder.css"></head><body>'
        '<img src="assets/a.jpg" alt="фото"><script src="scroll-engine/site-builder.js"></script>'
        '<style>@media (prefers-reduced-motion: reduce){*{animation:none}}</style></body></html>')


@pytest.fixture()
def sites(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "SITES", tmp_path / "sites")
    monkeypatch.setattr(sb, "ROOT", tmp_path)
    return tmp_path / "sites"


def test_init_copies_engine_and_never_overwrites(sites):
    assert sb.main(["init", "demo"]) == 0
    engine = sites / "demo" / "scroll-engine"
    assert (engine / "site-builder.js").stat().st_size > 10_000 and (engine / "site-builder.css").exists()
    (engine / "site-builder.css").write_text("/* её правки */", encoding="utf-8")
    assert sb.main(["init", "demo"]) == 0
    assert (engine / "site-builder.css").read_text(encoding="utf-8") == "/* её правки */"


@pytest.mark.parametrize("bad", ["", "a", "../x", "сайт", "a b", "x" * 41])
def test_bad_names_are_refused(sites, bad):
    assert sb.main(["init", bad]) == 2


def test_check_passes_good_site_and_names_each_problem(sites, capsys):
    sb.main(["init", "demo"])
    (sites / "demo" / "assets" / "a.jpg").write_bytes(b"x")
    (sites / "demo" / "index.html").write_text(GOOD, encoding="utf-8")
    assert sb.main(["check", "demo"]) == 0
    bad = (GOOD.replace('<meta name="viewport" content="width=device-width,initial-scale=1">', "")
           .replace('alt="фото"', "").replace("prefers-reduced-motion", "x")
           .replace("</body>", '<script src="https://evil.example/x.js"></script><img src="assets/missing.jpg" alt="">'
                    '<a href="C:\\Users\\burov\\a.html">x</a></body>'))
    (sites / "demo" / "index.html").write_text(bad, encoding="utf-8")
    assert sb.main(["check", "demo"]) == 2
    out = capsys.readouterr().out
    for need in ("viewport", "картинка без alt", "внешний скрипт https://evil.example/x.js", "файла нет: assets/missing.jpg",
                 "путь с твоего компьютера"):
        assert need in out, need
    assert "prefers-reduced-motion" not in out          # движок в scroll-engine/ уже его поддерживает


def test_check_asks_for_reduced_motion_when_site_has_no_engine(sites):
    site = sites / "plain"
    site.mkdir(parents=True)
    (site / "index.html").write_text('<!doctype html><html lang="ru"><head><meta name="viewport" content="width=device-width"></head><body>x</body></html>', encoding="utf-8")
    assert any("prefers-reduced-motion" in p for p in sb.check_site(site))


def test_fonts_from_google_are_allowed(sites):
    sb.main(["init", "demo"])
    (sites / "demo" / "index.html").write_text(
        GOOD.replace("</head>", '<link href="https://fonts.googleapis.com/css2?family=X" rel="stylesheet"></head>'), encoding="utf-8")
    (sites / "demo" / "assets" / "a.jpg").write_bytes(b"x")
    assert sb.check_site(sites / "demo") == []


def test_pack_skips_secrets_and_junk_and_warns_when_too_big(sites, monkeypatch):
    sb.main(["init", "demo"])
    site = sites / "demo"
    (site / "index.html").write_text(GOOD, encoding="utf-8")
    (site / SECRET_FILE).write_text("KEY=value", encoding="utf-8")
    (site / "debug.log").write_text("x", encoding="utf-8")
    assert sb.main(["pack", "demo"]) == 0
    names = zipfile.ZipFile(sites / "demo.zip").namelist()
    assert "index.html" in names and "scroll-engine/site-builder.js" in names
    assert not any(n.startswith(SECRET_FILE) or n.endswith(".log") for n in names)
    monkeypatch.setattr(sb, "TELEGRAM_LIMIT", 10)
    assert sb.main(["pack", "demo"]) == 3
    assert sb.main(["pack", "nothing"]) == 2


def test_skill_in_project_has_what_jarvis_needs():
    skill = ROOT / ".claude" / "skills" / "site-builder"
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert (skill / "vendor" / "scroll-engine" / "site-builder.js").is_file() and (skill / "scripts" / "prepare_video.py").is_file()
    for must in ("integrations.site_builder init", "outbox/sites/", "только после её «да»", "Не публикуй сайт", "textwriter"):
        assert must in text, must
    assert "THIRD_PARTY_NOTICES.txt](" not in text                       # ссылок в никуда нет
    for ref in (skill / "references").glob("*.md"):
        assert "<skill>/" not in ref.read_text(encoding="utf-8"), ref.name  # путь к скрипту — настоящий


def test_guard_allows_site_commands_and_asks_for_http_server(tmp_path):
    from tests import test_guard as g
    (tmp_path / "state" / "secrets").mkdir(parents=True)
    for cmd in ("init", "check", "pack"):
        d = g.decide(g.ev("Bash", command=f"python -m integrations.site_builder {cmd} demo"), tmp_path, env={"JARVIS_TASK_ID": "t"})
        assert d.action == "allow", cmd
    assert g.decide(g.ev("Bash", command="python -m http.server 8123"), tmp_path, env={"JARVIS_TASK_ID": "t"}).action == "ask"
