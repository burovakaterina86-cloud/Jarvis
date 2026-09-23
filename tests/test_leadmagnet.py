"""Вёрстка лид-магнита: `lead-magnet.json` → PDF.

Контракт данных — `.autopilot/2026-09-23-lead-magnets--wip/contract.md`.
Швы: сборка из маленького JSON даёт PDF, пустые клетки таблицы — поля для
записи, неверные данные — код 2, цвета берутся из `tokens.py`, вывод в трубу
не падает.
"""
import json
import subprocess
import sys

import pytest

from integrations.visuals import leadmagnet, render, tokens

MINIMAL = {
    "title": "AI-аудит контент-рутины",
    "subtitle": "Найди, что можно снять с себя за неделю",
    "author": "Катерина Бурова · ESSA.AI",
    "intro": ["Короткий абзац о том, зачем этот аудит."],
    "sections": [
        {
            "heading": "Разложи процесс",
            "body": ["Абзац про то, как разложить рутину на шаги."],
            "table": {
                "columns": ["Процесс", "Часов в неделю", "Итог"],
                "rows": [["Монтаж", "", ""], ["Тексты", "3", ""]],
            },
            "checklist": ["Выпиши все процессы", "Отметь ручные"],
            "note": "Короткий нюанс от неё.",
            "handwritten": "сохраняю много",
        }
    ],
    "cta": {"text": "Хочешь разбор своей рутины — напиши", "keyword": "АУДИТ"},
}


def _write(tmp_path, data=MINIMAL, name="lead-magnet.json"):
    kit_dir = tmp_path / "ai-audit"
    kit_dir.mkdir()
    (kit_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return kit_dir


# --- данные: контракт -------------------------------------------------------


def test_missing_required_field_is_data_error(tmp_path):
    data = dict(MINIMAL)
    del data["title"]
    kit_dir = _write(tmp_path, data)
    with pytest.raises(ValueError, match="title"):
        leadmagnet.load_data(kit_dir / "lead-magnet.json")


def test_unknown_top_level_field_is_data_error(tmp_path):
    data = {**MINIMAL, "extra": 1}
    kit_dir = _write(tmp_path, data)
    with pytest.raises(ValueError, match="extra"):
        leadmagnet.load_data(kit_dir / "lead-magnet.json")


def test_broken_json_is_data_error(tmp_path):
    kit_dir = tmp_path / "ai-audit"
    kit_dir.mkdir()
    (kit_dir / "lead-magnet.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(ValueError):
        leadmagnet.load_data(kit_dir / "lead-magnet.json")


def test_missing_file_is_data_error(tmp_path):
    with pytest.raises(ValueError):
        leadmagnet.load_data(tmp_path / "нет-такого.json")


def test_bad_background_is_data_error(tmp_path):
    data = {**MINIMAL, "background": "purple"}
    kit_dir = _write(tmp_path, data)
    with pytest.raises(ValueError, match="background"):
        leadmagnet.load_data(kit_dir / "lead-magnet.json")


def test_optional_fields_are_optional(tmp_path):
    data = {
        "title": "Заголовок",
        "subtitle": "Подзаголовок",
        "author": "Автор",
        "sections": [{"heading": "Раздел"}],
    }
    kit_dir = _write(tmp_path, data)
    loaded = leadmagnet.load_data(kit_dir / "lead-magnet.json")
    assert loaded["sections"][0]["heading"] == "Раздел"


def test_cli_bad_data_exits_2(tmp_path):
    data = dict(MINIMAL)
    del data["author"]
    kit_dir = _write(tmp_path, data)
    assert leadmagnet.main([str(kit_dir)]) == leadmagnet.EXIT_DATA_ERROR


def test_cli_wrong_argc_exits_2(tmp_path):
    assert leadmagnet.main([]) == leadmagnet.EXIT_DATA_ERROR
    assert leadmagnet.main(["a", "b"]) == leadmagnet.EXIT_DATA_ERROR


# --- цвета из tokens.py, не свои ------------------------------------------


def test_dark_palette_comes_from_tokens():
    c = leadmagnet._palette("dark")
    assert c["bg"] == tokens.CAROUSEL_PALETTE["BG_DEEP"]
    assert c["accent"] == tokens.CAROUSEL_PALETTE["ORANGE"]
    assert c["plate"] == tokens.PLATE["BASE"]


def test_light_palette_comes_from_tokens():
    c = leadmagnet._palette("light")
    assert c["bg"] == tokens.PALETTE["BG_LIGHT_PRIMARY"]
    assert c["text"] == tokens.PALETTE["TEXT_ON_LIGHT"]
    assert c["accent"] == tokens.CAROUSEL_PALETTE["ORANGE_DEEP"]


def test_html_uses_only_tokens_hex_colors():
    import re

    html = leadmagnet.render_html(MINIMAL)
    allowed = {
        v.upper()
        for source in (tokens.PALETTE, tokens.OPTIONAL, tokens.ACCENT, tokens.CAROUSEL_PALETTE, tokens.PLATE)
        for v in source.values()
    }
    found = {m.upper() for m in re.findall(r"#[0-9A-Fa-f]{6}\b", html)}
    assert found <= allowed


# --- пустые клетки таблицы — поле для записи -------------------------------


def test_empty_table_cell_renders_as_fill_line():
    html = leadmagnet.render_html(MINIMAL)
    assert 'class="fillable"' in html
    assert 'class="fill-line"' in html


def test_filled_table_cell_renders_as_text():
    html = leadmagnet.render_html(MINIMAL)
    assert ">3<" in html
    assert "Монтаж" in html


def test_table_and_note_block_avoid_page_break():
    html = leadmagnet.render_html(MINIMAL)
    assert "break-inside: avoid" in html
    assert ".table-block" in html
    assert ".note-plate" in html


# --- сборка PDF --------------------------------------------------------------


@pytest.mark.skipif(
    render._playwright_module() is None, reason="нет playwright — PDF не проверяем"
)
def test_build_produces_multi_page_pdf(tmp_path):
    kit_dir = _write(tmp_path)
    result = leadmagnet.build(kit_dir)
    assert result.ok, result.error
    assert result.pdf_path.is_file()
    raw = result.pdf_path.read_bytes()
    assert raw.startswith(b"%PDF")
    # число объектов /Page — минимум обложка + один раздел + cta
    assert raw.count(b"/Type /Page") >= 2 or raw.count(b"/Type/Page") >= 2


@pytest.mark.skipif(
    render._playwright_module() is None, reason="нет playwright — CLI не проверяем"
)
def test_cli_exit_0_and_writes_pdf_named_after_folder(tmp_path):
    kit_dir = _write(tmp_path)
    code = leadmagnet.main([str(kit_dir)])
    assert code == 0
    assert (kit_dir / "ai-audit.pdf").is_file()


def test_no_playwright_returns_exit_3(tmp_path, monkeypatch):
    monkeypatch.setattr(leadmagnet, "_playwright_module", lambda: None)
    kit_dir = _write(tmp_path)
    code = leadmagnet.main([str(kit_dir)])
    assert code == leadmagnet.EXIT_NOT_RENDERED


# --- вывод в трубу не падает -------------------------------------------------


def test_cli_output_survives_pipe(tmp_path):
    data = dict(MINIMAL)
    del data["author"]
    kit_dir = _write(tmp_path, data)
    proc = subprocess.run(
        [sys.executable, "-m", "integrations.visuals.leadmagnet", str(kit_dir)],
        capture_output=True,
    )
    assert proc.returncode == leadmagnet.EXIT_DATA_ERROR
    # не падает при декодировании кириллицы из трубы
    proc.stdout.decode("utf-8")
