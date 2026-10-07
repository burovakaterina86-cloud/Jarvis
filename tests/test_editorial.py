"""Редакционная карусель по её эталону «стиль 2» (2026-09-25): без браузера."""
import re

import pytest

from integrations.visuals import editorial as ed


def test_accent_is_violet_never_orange():
    html = ed.build_slide({"type": "statement", "hook": "Тебе не нужно\n[[изучать нейросети]]"}, 2, 6, "dark")
    assert ed.THEMES["dark"]["accent"] in html
    assert "#FF955E" not in html.upper() and "ORANGE" not in html.upper()
    assert '<span class="acc">изучать нейросети</span>' in html


def test_backgrounds_alternate_dark_light_by_default():
    themes = [ed.theme_for({}, i) for i in range(1, 7)]
    assert themes == ["dark", "light", "dark", "light", "dark", "light"]
    assert ed.theme_for({"bg": "light"}, 1) == "light"


def test_photo_slide_is_full_bleed_with_text_over_shade(tmp_path):
    img = tmp_path / "me.png"
    img.write_bytes(b"x")
    html = ed.build_slide({"type": "photo", "hook": "Хук", "photo": str(img)}, 1, 6, "dark")
    assert 'class="bg-photo"' in html and "object-fit: cover" in html
    assert 'class="shade"' in html


def test_missing_photo_is_reported_not_silent(tmp_path):
    notes = []
    ed.build_slide({"type": "photo", "hook": "Хук", "photo": str(tmp_path / "nope.png")}, 1, 6, "dark", notes)
    assert any("nope.png" in n for n in notes)


def test_steps_draw_numbered_plates_with_arrows():
    html = ed.build_slide({"type": "steps", "hook": "Как", "steps": [
        {"title": "Сначала - [[задача]]"}, {"title": "Потом - [[процесс]]", "text": "пояснение"}]}, 3, 6, "light")
    assert html.count('class="step-plate"') == 2
    assert html.count('class="arrow-down"') == 1
    assert ">01<" in html and ">02<" in html


def test_cards_and_compare_render_their_blocks():
    cards = ed.build_slide({"type": "cards", "hook": "Что", "cards": [
        {"title": "Словечки", "icon": "doc"}, {"title": "Шутки", "icon": "spark"}]}, 3, 6, "dark")
    assert cards.count('class="card"') == 2 and "<svg" in cards
    cmp_ = ed.build_slide({"type": "compare", "hook": "Было", "rows": [["Дружелюбный тон", "На «ты»"]]}, 4, 6, "light")
    assert 'class="was"' in cmp_ and 'class="now"' in cmp_


def test_headline_size_fits_longest_line():
    small = ed.fit_headline(["ОЧЕНЬ ДЛИННАЯ СТРОКА ЗАГОЛОВКА"], 944, 120)
    big = ed.fit_headline(["КОРОТКО"], 944, 120)
    assert big == 120 and small < 120
    assert small * ed.CAPS_ADVANCE * len("ОЧЕНЬ ДЛИННАЯ СТРОКА ЗАГОЛОВКА") <= 944


def test_rhythm_check_flags_repeats_and_two_photos_in_a_row():
    slides = [{"type": "photo"}, {"type": "photo"}, {"type": "text"}, {"type": "text"}]
    problems = ed.rhythm_problems(slides)
    assert any("1-2" in p and "фото" in p for p in problems)
    assert any("3-4" in p for p in problems)
    assert ed.rhythm_problems([{"type": "photo"}, {"type": "statement"}, {"type": "steps"}]) == []


def test_unknown_type_is_an_error():
    with pytest.raises(ValueError):
        ed.build_slide({"type": "blob", "hook": "x"}, 1, 1, "dark")


def test_arrows_and_alert_have_real_icons_not_the_dot_fallback():
    for name in ("arrow-down", "arrow-right", "alert"):
        assert templates_dot() not in ed._icon(name, 40, "#fff")


def templates_dot():
    from integrations.visuals import templates
    return templates.ICONS[templates.DEFAULT_STEP_ICON]


def test_canvas_class_does_not_clash_with_block_classes():
    # 2026-09-25: холст с классом «cards» подхватывал сетку .cards и ломал слайд пополам
    html = ed.build_slide({"type": "cards", "hook": "x", "cards": [{"title": "a"}]}, 1, 1, "dark")
    assert 'class="canvas k-cards"' in html and 'class="canvas cards"' not in html


def test_focus_value_cannot_break_out_of_the_style_attribute():
    from integrations.visuals.editorial import _focus
    assert _focus("70% 30%", "50% 50%") == "70% 30%" and _focus(None, "50% 15%") == "50% 15%"
    assert _focus("left top", "x") == "left top" and _focus("-10px 20.5%", "x") == "-10px 20.5%"
    for bad in ('50%;background:url(//evil/x)', '50%" onerror="x', "50% 20%;}</style><script>", "url(x)"):
        assert _focus(bad, "DEFAULT") == "DEFAULT"
