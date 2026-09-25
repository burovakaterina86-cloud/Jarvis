"""Вёрстка интерактивного HTML-гайда: `lead-magnet.json` -> самодостаточный HTML.

Контракт данных — `.autopilot/2026-09-23-lead-magnets--wip/contract.md`.
Швы: сборка из маленького JSON даёт один файл без внешних ссылок (кроме
Google Fonts), палитра — её гайдовая, а не карусельная, формула итога
(Частота × Время × Раздражение) считается в браузере, самая тяжёлая строка
подсвечивается, страница не падает без localStorage, неверные данные — код 2.
"""
import json
import re
import subprocess
import sys

import pytest

from integrations.visuals import guide, render, tokens

MINIMAL = {
    "title": "AI-аудит контент-рутины",
    "subtitle": "Найди, что можно снять с себя за неделю",
    "author": "Катерина Бурова · ESSA.AI",
    "intro": ["Короткий абзац о том, зачем этот аудит."],
    "sections": [
        {
            "heading": "Восемь процессов",
            "body": ["Вот процессы, с которыми обычно сталкивается эксперт."],
            "table": {
                "columns": ["Процесс", "Часов за один раз", "Частота", "Раздражение (1–5)", "Итог"],
                "rows": [["Монтаж", "", "", "", ""], ["Видео", "", "", "", ""]],
            },
            "checklist": ["Впиши часы", "Впиши раздражение"],
            "note": "Короткий нюанс от неё.",
        }
    ],
    "cta": {"text": "Хочешь разбор своей рутины — напиши", "keyword": "АУДИТ"},
}


def _write(tmp_path, data=MINIMAL, name="lead-magnet.json"):
    kit_dir = tmp_path / "ai-audit"
    kit_dir.mkdir()
    (kit_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return kit_dir


# --- данные: тот же контракт, что у leadmagnet.py --------------------------


def test_missing_required_field_is_data_error(tmp_path):
    data = dict(MINIMAL)
    del data["title"]
    kit_dir = _write(tmp_path, data)
    with pytest.raises(ValueError, match="title"):
        guide.load_data(kit_dir / "lead-magnet.json")


def test_broken_json_is_data_error(tmp_path):
    kit_dir = tmp_path / "ai-audit"
    kit_dir.mkdir()
    (kit_dir / "lead-magnet.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(ValueError):
        guide.load_data(kit_dir / "lead-magnet.json")


def test_cli_bad_data_exits_2(tmp_path):
    data = dict(MINIMAL)
    del data["author"]
    kit_dir = _write(tmp_path, data)
    assert guide.main([str(kit_dir)]) == guide.EXIT_DATA_ERROR


def test_cli_wrong_argc_exits_2(tmp_path):
    assert guide.main([]) == guide.EXIT_DATA_ERROR
    assert guide.main(["a", "b"]) == guide.EXIT_DATA_ERROR


# --- один самодостаточный файл ----------------------------------------------


def test_cli_exit_0_and_writes_html_named_after_folder(tmp_path):
    kit_dir = _write(tmp_path)
    code = guide.main([str(kit_dir)])
    assert code == 0
    assert (kit_dir / "ai-audit.html").is_file()


def test_build_produces_one_file_without_external_links_except_fonts(tmp_path):
    kit_dir = _write(tmp_path)
    result = guide.build(kit_dir)
    assert result.ok, result.error
    html = result.html_path.read_text(encoding="utf-8")

    urls = re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
    allowed_hosts = ("fonts.googleapis.com", "fonts.gstatic.com")
    assert urls, "должна остаться хотя бы ссылка на Google Fonts"
    for url in urls:
        assert any(host in url for host in allowed_hosts), url

    # css и js — инлайн, не отдельные файлы
    assert "<style>" in html and "</style>" in html
    assert "<script>" in html and "</script>" in html
    assert not re.search(r'<link[^>]+rel="stylesheet"[^>]+href="(?!https://fonts)', html)
    assert '<script src="' not in html


def test_photo_embedded_as_base64_data_uri(tmp_path):
    kit_dir = _write(tmp_path, {**MINIMAL, "photo": "photo.png"})
    # 1x1 px png
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6360000002000155273def0000000049454e44ae426082"
    )
    (kit_dir / "photo.png").write_bytes(png_bytes)
    result = guide.build(kit_dir)
    assert result.ok, result.error
    html = result.html_path.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html


# --- палитра: её гайдовая, не карусельная -----------------------------------


def test_html_uses_her_guide_palette():
    html = guide.render_html(MINIMAL)
    for hex_color in guide.COLORS.values():
        if hex_color.startswith("#"):
            assert hex_color in html


def test_html_does_not_use_carousel_system():
    html = guide.render_html(MINIMAL)
    assert "Roboto Condensed" not in html
    assert "Open Sans" not in html
    for hex_color in tokens.CAROUSEL_PALETTE.values():
        assert hex_color.upper() not in html.upper()
    assert "Montserrat" in html


# --- таблица аудита: интерактивность ----------------------------------------


def test_audit_table_renders_inputs_and_selects():
    html = guide.render_html(MINIMAL)
    assert 'class="f-hours"' in html
    assert 'class="f-freq"' in html
    assert 'class="f-irritation"' in html
    assert 'class="f-total"' in html
    assert 'id="audit-clear"' in html


def test_non_audit_table_falls_back_to_static_fill_lines():
    data = {
        **MINIMAL,
        "sections": [
            {
                "heading": "Другая таблица",
                "table": {"columns": ["Колонка A", "Колонка B"], "rows": [["значение", ""]]},
            }
        ],
    }
    html = guide.render_html(data)
    assert 'class="fillable"' in html
    assert 'class="fill-line"' in html
    assert 'class="f-hours"' not in html


PLAYWRIGHT_REASON = "нет playwright — браузерные проверки пропущены"


@pytest.mark.skipif(render._playwright_module() is None, reason=PLAYWRIGHT_REASON)
def test_total_formula_computed_in_browser(tmp_path):
    sync_playwright = render._playwright_module()
    kit_dir = _write(tmp_path)
    result = guide.build(kit_dir)
    assert result.ok, result.error

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(result.html_path.resolve().as_uri())
        row = page.locator('.audit-row[data-row="1"]')
        row.locator(".f-hours").fill("5")
        row.locator(".f-freq").select_option("often")  # 3 — «несколько раз в неделю»
        row.locator(".f-irritation").select_option("4")
        total = row.locator(".f-total").inner_text()
        week = page.locator("#audit-hours-sum").inner_text()
        browser.close()
    assert total == "60"  # 3 (раз в неделю) × 5 (часов за раз) × 4 (раздражение)
    # часы в неделю — время за раз × частота, частота не считается дважды
    assert week == "15"


@pytest.mark.skipif(render._playwright_module() is None, reason=PLAYWRIGHT_REASON)
def test_heaviest_row_gets_highlighted(tmp_path):
    sync_playwright = render._playwright_module()
    kit_dir = _write(tmp_path)
    result = guide.build(kit_dir)
    assert result.ok, result.error

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(result.html_path.resolve().as_uri())

        light_row = page.locator('.audit-row[data-row="0"]')
        light_row.locator(".f-hours").fill("1")
        light_row.locator(".f-freq").select_option("rare")
        light_row.locator(".f-irritation").select_option("1")

        heavy_row = page.locator('.audit-row[data-row="1"]')
        heavy_row.locator(".f-hours").fill("10")
        heavy_row.locator(".f-freq").select_option("daily")
        heavy_row.locator(".f-irritation").select_option("5")

        heavy_class = heavy_row.get_attribute("class")
        light_class = light_row.get_attribute("class")
        winner = page.locator("#audit-winner-name").inner_text()
        browser.close()

    assert "is-max" in heavy_class
    assert "is-max" not in light_class
    assert winner == "Видео"


@pytest.mark.skipif(render._playwright_module() is None, reason=PLAYWRIGHT_REASON)
def test_page_survives_without_local_storage(tmp_path):
    sync_playwright = render._playwright_module()
    kit_dir = _write(tmp_path)
    result = guide.build(kit_dir)
    assert result.ok, result.error

    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # localStorage недоступен — как в приватном окне с заблокированными данными сайта.
        page.add_init_script(
            "Object.defineProperty(window, 'localStorage', "
            "{ get() { throw new DOMException('blocked'); } });"
        )
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(result.html_path.resolve().as_uri())
        row = page.locator('.audit-row[data-row="0"]')
        row.locator(".f-hours").fill("2")
        row.locator(".f-irritation").select_option("3")
        total = row.locator(".f-total").inner_text()
        browser.close()

    assert not errors, errors
    assert total == "0"  # частота не выбрана — итог 0, но страница не упала


# --- вывод в трубу не падает -------------------------------------------------


def test_cli_output_survives_pipe(tmp_path):
    data = dict(MINIMAL)
    del data["author"]
    kit_dir = _write(tmp_path, data)
    proc = subprocess.run(
        [sys.executable, "-m", "integrations.visuals.guide", str(kit_dir)],
        capture_output=True,
    )
    assert proc.returncode == guide.EXIT_DATA_ERROR
    proc.stdout.decode("utf-8")
