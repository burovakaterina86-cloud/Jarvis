"""Картинки: токены дизайн-системы, вёрстка трёх видов, снимок браузером.

Ожидаемые значения взяты руками из файлов владелицы и здесь захардкожены:
`essa-ai/DESIGN.md` (палитра, шрифты, типографика, размеры),
`essa-ai/POST_COVERS.md`, `essa-ai/SKILL_carousel-instagram.md`.
Если код посчитает их иначе — тест обязан покраснеть.
"""
from integrations.visuals import tokens


# --- палитра и шрифты: 12 цветов и три начертания из DESIGN.md -------------

DESIGN_MD_PALETTE = {
    "BG_DARK_PRIMARY": "#0D1015",
    "BG_DARK_SECONDARY": "#292834",
    "BG_LIGHT_PRIMARY": "#F1F0FA",
    "BG_LIGHT_SECONDARY": "#ECE9FA",
    "TEXT_ON_DARK": "#F7F5FA",
    "TEXT_ON_LIGHT": "#14151A",
    "TEXT_MUTED_DARK": "#B8B4C2",
    "TEXT_MUTED_LIGHT": "#686775",
    "VIOLET_PRIMARY": "#7158E7",
    "VIOLET_STRONG": "#592DE2",
    "VIOLET_SOFT": "#9F87EC",
    "LAVENDER": "#C8BFE7",
}


def test_palette_matches_design_md():
    assert tokens.PALETTE == DESIGN_MD_PALETTE


def test_optional_color_is_separate_from_core():
    assert tokens.OPTIONAL["COOL_BLUE_OPTIONAL"] == "#7ABAE6"
    assert "COOL_BLUE_OPTIONAL" not in tokens.PALETTE


def test_three_typefaces_and_no_fourth():
    assert tokens.FONTS == {
        "HEADLINE": "Roboto Condensed",
        "BODY": "Open Sans",
        "SUPPORT": "Open Sans",
    }
    assert set(tokens.FONT_FAMILIES) == {"Roboto Condensed", "Open Sans"}


# --- вёрстка трёх видов ----------------------------------------------------

import re

import pytest

from integrations.visuals import templates

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
ALLOWED_HEX = (
    {c.upper() for c in tokens.PALETTE.values()}
    | {c.upper() for c in tokens.OPTIONAL.values()}
    | {c.upper() for c in tokens.ACCENT.values()}
)


def _hexes(html):
    return {m.group(0).upper() for m in HEX.finditer(html)}


def _families(html):
    return set(re.findall(r"'([A-Za-z ]+)',\s*sans-serif", html))


CAROUSEL = templates.build_carousel_slide(
    hook="Меньше лишней работы",
    body="Не больше ИИ, а меньше ручных шагов.",
    label="Шаг 01",
    index=1,
    total=7,
)
COVER = templates.build_post_cover(hook="Мой подход", subtitle="как я работаю")
STORY = templates.build_story_background(key_phrase="Одно сообщение на сцену")


@pytest.mark.parametrize("html", [CAROUSEL, COVER, STORY])
def test_no_invented_colors(html):
    assert _hexes(html) <= ALLOWED_HEX, _hexes(html) - ALLOWED_HEX


@pytest.mark.parametrize("html", [CAROUSEL, COVER, STORY])
def test_no_third_typeface(html):
    assert _families(html) <= set(tokens.FONT_FAMILIES), _families(html)
    assert tokens.GOOGLE_FONTS_URL in html


@pytest.mark.parametrize(
    "html,kind", [(CAROUSEL, "carousel"), (COVER, "cover"), (STORY, "story")]
)
def test_canvas_size_matches_her_files(html, kind):
    w, h = tokens.CANVAS[kind]
    assert f"width: {w}px" in html and f"height: {h}px" in html


def test_carousel_uses_her_type_scale_and_safe_zone():
    assert f"font-size: {tokens.TYPE_SCALE['hook']['size']}px" in CAROUSEL
    assert f"padding: {tokens.SAFE_ZONE}px" in CAROUSEL


def test_text_is_substituted_and_escaped():
    assert "Меньше лишней работы" in CAROUSEL
    assert "Не больше ИИ, а меньше ручных шагов." in CAROUSEL
    assert "Шаг 01" in CAROUSEL
    assert "Одно сообщение на сцену" in STORY
    risky = templates.build_post_cover(hook="<script>alert(1)</script>", subtitle="&")
    assert "<script>alert(1)</script>" not in risky
    assert "&lt;script&gt;" in risky


def test_only_allowed_carousel_styles():
    with pytest.raises(ValueError):
        templates.build_carousel_slide(hook="x", style="STYLE_03")
    for style in tokens.STYLES:
        templates.build_carousel_slide(hook="x", style=style)


# --- снимок браузером и шрифты --------------------------------------------

from pathlib import Path

from integrations.visuals import render


def _page(tmp_path):
    p = tmp_path / "slide.html"
    p.write_text(templates.build_story_background(key_phrase="тест"), encoding="utf-8")
    return p


def test_render_without_browser_does_not_raise_and_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    out = tmp_path / "slide.png"
    res = render.render_image(_page(tmp_path), out, 1080, 1920)
    assert res.ok is False
    assert res.png_path is None
    assert "playwright" in res.error.lower()
    assert res.width == 1080 and res.height == 1920
    # ход не роняется: есть готовый план для MCP-браузера
    assert res.mcp_plan and res.mcp_plan[0]["tool"].startswith("mcp__playwright__")
    assert any("browser_take_screenshot" == s["tool"].split("__")[-1] for s in res.mcp_plan)
    shot = [s for s in res.mcp_plan if s["tool"].endswith("take_screenshot")][0]
    # окно MCP-браузера не масштабируется — снимаем холст, а не вьюпорт
    assert shot["args"]["target"] == render.CANVAS_SELECTOR


def test_no_network_warns_which_font_is_substituted(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    monkeypatch.setattr(render, "_fonts_reachable", lambda timeout=None: False)
    res = render.render_image(_page(tmp_path), tmp_path / "s.png", 1080, 1920)
    joined = " ".join(res.warnings)
    assert "Roboto Condensed" in joined and "Open Sans" in joined
    assert tokens.FALLBACK_STACK in joined


def test_network_ok_means_no_font_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    monkeypatch.setattr(render, "_fonts_reachable", lambda timeout=None: True)
    res = render.render_image(_page(tmp_path), tmp_path / "s.png", 1080, 1920)
    assert res.warnings == []


def test_default_size_is_her_carousel_canvas(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    res = render.render_image(_page(tmp_path), tmp_path / "s.png")
    assert (res.width, res.height) == tokens.CANVAS["carousel"]


# --- комплект: три вида рядом с текстами ----------------------------------

from integrations.visuals import kit


def test_kit_lays_out_all_three_kinds(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    kit_dir = tmp_path / "2026-09-21-тема"
    kit_dir.mkdir()
    (kit_dir / "post.md").write_text("текст поста", encoding="utf-8")
    plan = kit.build_kit_visuals(
        kit_dir,
        carousel_slides=[
            {"hook": "Первый", "role": "cover"},
            {"hook": "Второй", "body": "пояснение", "role": "slide"},
        ],
        cover={"hook": "Мой подход"},
        story={"key_phrase": "Одно сообщение"},
    )
    kinds = {item.kind for item in plan}
    assert kinds == {"carousel", "cover", "story"}
    for item in plan:
        assert item.html_path.is_file()
        assert item.html_path.parent == kit_dir / "visuals"
        assert (item.width, item.height) == tokens.CANVAS[item.kind]
    # тексты комплекта на месте
    assert (kit_dir / "post.md").read_text(encoding="utf-8") == "текст поста"
    # PNG не создан без браузера, но каждый вид знает свой путь и план
    assert all(item.result.ok is False and item.png_path.suffix == ".png" for item in plan)


def test_kit_png_names_are_stable_and_ordered(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    plan = kit.build_kit_visuals(
        kit_dir,
        carousel_slides=[{"hook": "a"}, {"hook": "b"}, {"hook": "c"}],
        cover={"hook": "c"},
        story={"key_phrase": "s"},
    )
    names = [p.png_path.name for p in plan]
    assert names[:3] == ["carousel-01.png", "carousel-02.png", "carousel-03.png"]
    assert "cover.png" in names and "story.png" in names


@pytest.mark.skipif(
    render._playwright_module() is None, reason="нет playwright — снимок не проверяем"
)
def test_real_browser_makes_png_of_exact_size(tmp_path):
    out = tmp_path / "story.png"
    res = render.render_image(_page(tmp_path), out, 1080, 1920)
    assert res.ok, res.error
    assert out.is_file() and out.stat().st_size > 0


# --- навык carousel-instagram ---------------------------------------------

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "carousel-instagram" / "SKILL.md"


def test_skill_leads_the_render_and_serves_all_three_kinds():
    text = SKILL.read_text(encoding="utf-8")
    for kind in ("1080×1350", "1080×1920", "обложк", "сторис", "карусел"):
        assert kind in text, kind
    assert "render_image" in text and "build_kit_visuals" in text
    assert "browser_take_screenshot" in text


def test_skill_keeps_her_constraints():
    text = SKILL.read_text(encoding="utf-8")
    for style in tokens.STYLES:
        assert style in text, style
    assert "STYLE_03" in text  # прямо назван как запрещённый
    assert "textwriter" in text and "humaniser" in text
    assert "Третий фирменный шрифт" in text


def test_plan_uses_http_because_file_protocol_is_blocked(tmp_path):
    page = _page(tmp_path)
    plan = render.mcp_plan(page, tmp_path / "s.png", 1080, 1920, base_url="http://127.0.0.1:9")
    nav = plan[0]["args"]["url"]
    assert nav == "http://127.0.0.1:9/slide.html"
    assert not nav.startswith("file:")


def test_serve_hands_out_the_page_over_http(tmp_path):
    from urllib.request import urlopen

    _page(tmp_path)
    with render.serve(tmp_path) as base:
        body = urlopen(f"{base}/slide.html", timeout=5).read().decode("utf-8")
    assert "canvas" in body and tokens.GOOGLE_FONTS_URL in body


# --- плотность слайда: эталон владелицы (reference/1–4.webp) ---------------
# Ожидаемое берётся из её слайдов и DESIGN.md, а не из кода под тестом:
# шапка `03 | МОЯ ВОРОНКА` + тезис, заголовок, подзаголовок, тело с графикой,
# нижняя плашка-итог, подвал `03/08`.

DENSE = templates.build_carousel_slide(
    hook="5 шагов вместо 50 уроков",
    body="Не обязательно проходить всё. Достаточно 5 шагов.",
    label="Моя воронка",
    thesis="Маленькие шаги.\nБольшие изменения.",
    footer_thesis="Реальные люди. Реальные результаты.",
    summary="одна задача → реальный результат → больше уверенности",
    steps=[
        {"caption": "Выбери задачу", "note": "Из реальной жизни", "icon": "search"},
        {"caption": "Найди раздел", "note": "По карте проекта", "icon": "doc"},
        {"caption": "Посмотри", "note": "Короткие инструкции", "icon": "play"},
        {"caption": "Внедри", "note": "Сразу", "icon": "gear"},
        {"caption": "Получи результат", "note": "И двигайся дальше", "icon": "check"},
    ],
    index=3,
    total=8,
    style="STYLE_01",
    role="slide",
)


def test_slide_has_every_zone_of_her_reference():
    for zone in ("header", "hero", "lead", "stage", "summary", "footer"):
        assert f'class="{zone}' in DENSE, zone


def test_header_and_footer_carry_rubric_and_numbers():
    # второй эталон: счёт `03 / 08` и метка стоят в шапке, тезиса в шапке нет
    assert "МОЯ ВОРОНКА" in DENSE.upper()
    assert ">03<" in DENSE and "/ 08" in DENSE
    assert "МАЛЕНЬКИЕ ШАГИ." not in DENSE.upper()
    assert "РЕАЛЬНЫЕ ЛЮДИ." in DENSE.upper()


def test_service_function_mark_never_reaches_the_frame():
    # в первом рендере в плашку-рубрику утекла функция слайда «внимание»
    for mark in ("внимание", "новое убеждение", "pattern interrupt"):
        leaked = templates.build_carousel_slide(hook="x", label=mark, index=1, total=2)
        assert mark.upper() not in leaked.upper(), mark
    assert "МОЯ ВОРОНКА" in templates.build_carousel_slide(
        hook="x", label="Моя воронка"
    ).upper()


def test_no_line_height_below_one_so_descenders_do_not_overlap():
    # хвосты «у», «р», «д» задевали следующую строку при line-height < 1
    values = [float(v) for v in re.findall(r"line-height:\s*([0-9.]+);", DENSE)]
    assert values, "межстрочное расстояние не задано"
    assert min(values) >= tokens.MIN_LINE_HEIGHT, min(values)
    lo, hi = 0.92, 1.02  # DESIGN.md §10, Cover / Hook
    assert lo <= tokens.TYPE_SCALE["hook"]["line_height"] <= hi


def test_dark_and_light_alternate_and_ends_are_dark():
    seq = tokens.alternating_styles(9)
    assert len(seq) == 9
    assert seq[0] == "STYLE_01" and seq[-1] == "STYLE_01"
    assert seq[1] == "STYLE_02_LIGHT"
    assert all(a != b for a, b in zip(seq, seq[1:-1]))
    assert set(seq) <= set(tokens.STYLES)
    assert tokens.alternating_styles(8)[-1] == "STYLE_01"


def test_steps_chain_draws_circles_icons_captions_and_notes():
    # её слайд 1: кружки 1–5 на линии, под каждым иконка, подпись, пояснение
    assert DENSE.count('class="step-dot') == 5
    assert DENSE.count('class="step-note') == 5
    assert DENSE.count('class="step-link"') == 4
    assert DENSE.count("<svg") >= 5
    assert "Выбери задачу" in DENSE and "Из реальной жизни" in DENSE


def test_flow_cards_have_arrows_and_violet_accent_on_the_last():
    html = templates.build_carousel_slide(
        hook="Задача",
        flow=[
            {"title": "Задача", "icon": "doc"},
            {"title": "Сколько времени", "icon": "clock"},
            {"title": "Возвращённое время", "icon": "hourglass"},
        ],
    )
    assert html.count('class="flow-arrow"') == 2 and templates.ARROW in html
    assert html.count('class="flow-card') == 3
    assert 'class="flow-card accent"' in html
    assert f'background: {tokens.PALETTE["LAVENDER"]}' in html


def test_cards_grid_is_rounded_within_her_radius_range():
    html = templates.build_carousel_slide(
        hook="Одно сообщество",
        cards=[{"title": t} for t in ("Видео", "Тексты", "Визуал", "Результаты")],
    )
    assert html.count('class="card"') == 4
    assert "grid-template-columns: repeat(2, 1fr)" in html
    lo, hi = tokens.RADIUS_RANGE  # DESIGN.md §14
    assert lo <= tokens.RADIUS["card"] <= hi
    assert f'border-radius: {tokens.RADIUS["card"]}px' in html


def test_graphics_are_built_from_the_slide_text_when_not_given():
    # данные первого рендера: стрелки прямо в тексте слайда
    html = templates.build_carousel_slide(
        hook="Механизм", body="Задача → Процесс → Нейросеть → Контроль"
    )
    assert html.count('class="flow-card') == 4
    assert "Нейросеть" in html
    dotted = templates.build_carousel_slide(
        hook="А теперь ты ещё", body="монтажёр · дизайнер · копирайтер"
    )
    assert dotted.count('class="card"') == 3


def test_icons_are_inline_svg_without_files_or_icon_fonts():
    assert "<svg" in DENSE and "</svg>" in DENSE
    assert "<img" not in DENSE
    assert "url(" not in DENSE.split("</style>")[0].replace("fonts.googleapis.com", "")
    assert tokens.PALETTE["VIOLET_SOFT"] in DENSE


def test_handwritten_notes_are_hers_and_stand_on_any_slide():
    # второй эталон (2026-09-22): пометок две-три на каждом слайде, а не одна
    # подпись на крайних — прежнее правило снято её же словами
    first = templates.build_carousel_slide(
        hook="Как пользоваться", handwritten="Всё получится ♡", index=1, total=9
    )
    middle = templates.build_carousel_slide(
        hook="Середина", handwritten="Всё получится ♡", index=5, total=9
    )
    assert 'class="hand-note' in first and 'class="hand-note' in middle
    assert "Всё получится" in middle
    assert f"'{tokens.HAND_FONT}', {tokens.HAND_FALLBACK}" in first
    assert "Marck+Script" in tokens.GOOGLE_FONTS_URL


def test_her_photo_and_screenshot_are_honest_about_a_missing_file(tmp_path):
    notes = []
    without = templates.build_carousel_slide(
        hook="Обложка", photo=tmp_path / "нет-фото.png",
        screenshot=tmp_path / "нет-скрина.png", index=1, total=2, notes=notes,
    )
    assert "<img" not in without
    assert len(notes) == 2 and all("файла нет" in n for n in notes)

    real_photo = tmp_path / "портрет.png"
    real_photo.write_bytes(b"png")
    real_shot = tmp_path / "скрин.png"
    real_shot.write_bytes(b"png")
    notes2 = []
    with_files = templates.build_carousel_slide(
        hook="Обложка", photo=real_photo, screenshot=real_shot,
        index=1, total=2, notes=notes2,
    )
    assert 'src="портрет.png"' in with_files and 'src="скрин.png"' in with_files
    # скриншот встаёт целиком, без обрезки содержимого
    assert "object-fit: contain" in with_files
    assert all("файла нет" not in n for n in notes2)


def test_kit_sets_the_alternation_once_for_the_whole_carousel(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    plan = kit.build_kit_visuals(
        kit_dir, carousel_slides=[{"hook": f"с{i}"} for i in range(9)]
    )
    dark = templates.STYLE_SURFACES["STYLE_01"]["bg"]
    light = templates.STYLE_SURFACES["STYLE_02_LIGHT"]["bg"]
    backs = [
        re.search(
            r"\.canvas \{ background: (#[0-9A-Fa-f]{6})",
            item.html_path.read_text(encoding="utf-8"),
        ).group(1)
        for item in plan
        if item.kind == "carousel"
    ]
    assert set(backs) == {dark, light}
    assert backs[0] == dark and backs[-1] == dark and backs[1] == light


def test_kit_carries_her_files_next_to_the_layout_and_reports_a_missing_one(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    photo = tmp_path / "портрет.png"
    photo.write_bytes(b"png")
    plan = kit.build_kit_visuals(
        kit_dir,
        carousel_slides=[
            {"hook": "Первый", "photo": photo, "handwritten": "Всё получится ♡"},
            {"hook": "Второй", "photo": tmp_path / "нет.png"},
        ],
    )
    first, second = plan[0], plan[1]
    assert (kit_dir / "visuals" / "портрет.png").is_file()
    assert 'src="портрет.png"' in first.html_path.read_text(encoding="utf-8")
    assert any("файла нет" in n for n in second.notes)
    assert "файла нет" in kit.report(plan)


def test_skill_tells_how_dense_slide_is_assembled():
    text = SKILL.read_text(encoding="utf-8")
    for word in ("steps", "flow", "cards", "summary", "handwritten", "photo", "screenshot"):
        assert word in text, word
    assert tokens.HAND_FONT in text
    assert "alternating_styles" in text
    assert "служебн" in text.lower()


# --- G08: объём слоями и тело слайда без пустоты ---------------------------
# Её слова 2026-09-21: «не хватает объема и по прежнему слишком много воздуха».
# Объём в её примерах (reference/2.webp, 3.webp) набирается слоями, а не цветом.

def _css(html):
    return html.split("</style>")[0]


def _rule(html, selector):
    m = re.search(re.escape(selector) + r" \{(.*?)\}", _css(html), re.S)
    assert m, selector
    return m.group(1)


GRID = templates.build_carousel_slide(
    hook="Одно сообщество",
    cards=[
        {"title": "Видео", "icon": "play"},
        {"title": "Тексты", "icon": "doc"},
        {"title": "AI-мастерская", "icon": "spark", "accent": True},
        {"title": "Визуал", "icon": "image"},
    ],
    style="STYLE_01",
)


def test_cards_are_layered_not_flat_rectangles():
    card = _rule(GRID, ".card")
    assert "inset 0 2px 0" in card          # светлая обводка по верхнему краю
    assert "inset 0 -2px 0" in card         # тёмная по нижнему
    assert re.search(r"0 24px 48px", card)  # мягкая тень под карточкой
    assert "border" in card


def test_accent_node_glows_and_is_filled():
    accent = _rule(GRID, ".card.accent")
    assert f'background: {tokens.PALETTE["LAVENDER"]}' in accent
    assert re.search(r"box-shadow: 0 0 \d+px", accent)  # свечение вокруг узла
    assert 'class="card accent"' in GRID


def test_canvas_keeps_a_background_glow_behind_the_content():
    assert "radial-gradient" in _rule(GRID, ".glow")
    assert 'class="glow"' in GRID


def test_stage_fills_the_vertical_between_hero_and_footer():
    # тело слайда забирает вертикаль между заголовком и подвалом; сами блоки
    # при этом высотой по содержимому — вертикаль уходит в отступы вокруг них
    for selector in (".stage", ".steps"):
        assert "flex: 1" in _rule(GRID, selector), selector
    # безопасные поля при этом на месте
    assert f"padding: {tokens.SAFE_ZONE}px" in GRID


def test_a_slide_without_graphics_does_not_leave_a_hole_in_the_middle():
    plain = templates.build_carousel_slide(
        hook="Это неверная\nпостановка", index=5, total=9
    )
    assert 'class="hero headline fill"' in plain
    assert "flex: 1" in _rule(plain, ".hero.fill")
    assert 'class="stage"' not in plain


def test_every_step_gets_an_icon_and_a_connecting_line():
    # её эталон (reference/1.webp): под каждым кружком иконка, кружки на линии
    named = templates.build_carousel_slide(
        hook="Четыре шага",
        steps=[
            {"caption": "Выбери задачу", "note": "Из реальной жизни", "icon": "search"},
            {"caption": "Разбери процесс", "note": "Как делаю сейчас", "icon": "doc"},
            {"caption": "Отдай повторяемое", "note": "Нейросети", "icon": "gear"},
            {"caption": "Проверь сама", "note": "Контроль за тобой", "icon": "check"},
        ],
    )
    assert named.count('class="step-icon"><svg') == 4
    for path in (templates.ICONS["search"], templates.ICONS["check"]):
        assert path in named
    # имя иконки не дали — место под кружком всё равно не пустое
    unnamed = templates.build_carousel_slide(
        hook="Шаги", steps=[{"caption": "Раз"}, {"caption": "Два"}]
    )
    assert unnamed.count('class="step-icon"><svg') == 2
    assert templates.ICONS[templates.DEFAULT_STEP_ICON] in unnamed
    # отрезки лежат в самом ряду между кружками, а не чертой поверх цифр
    assert '<div class="steps-row"><div class="step"' in named
    assert "position: relative" in _rule(named, ".steps-row")


def test_step_captions_share_one_grid():
    one_and_two_lines = templates.build_carousel_slide(
        hook="Шаги",
        steps=[{"caption": "Выбери задачу"}, {"caption": "Разбери процесс шаг за шагом"}],
    )
    caption = _rule(one_and_two_lines, ".step-caption")
    assert re.search(r"min-height: \d+px", caption)


# --- доводка по её замечанию: карточки по содержимому, иконки целые ---------

def test_icon_paths_stay_inside_the_viewbox_and_the_hourglass_has_a_waist():
    # иконка живёт в сетке 24×24: координата за её пределами — сломанный путь
    for name, path in templates.ICONS.items():
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
        assert nums, name
        # абсолютные координаты и относительные смещения — всё внутри сетки
        assert all(abs(n) <= 25 for n in nums), name
    # песочные часы: верхняя и нижняя воронки сходятся перемычкой посередине,
    # иначе в кадре два несвязанных треугольника (её рендер carousel-04)
    pairs = re.findall(
        r"(-?\d+(?:\.\d+)?)[ ,](-?\d+(?:\.\d+)?)", templates.ICONS["hourglass"]
    )
    ys = [float(y) for _, y in pairs]
    assert any(11 <= y <= 13 for y in ys), "нет перемычки в середине"
    assert any(y <= 4 for y in ys) and any(y >= 20 for y in ys), "нет крышек"


def test_flow_row_grows_to_the_body_but_not_past_her_third_of_the_canvas():
    # тело слайда занимает вертикаль от подзаголовка до нижней плашки, но
    # карточка не выше трети холста — её пропорция из reference/3.webp
    html = templates.build_carousel_slide(
        hook="Не нужно знать всё",
        flow=[{"title": "Задача"}, {"title": "Как теперь"}, {"title": "Время"}],
        style="STYLE_01",
    )
    _, h = tokens.CANVAS["carousel"]
    flow = _rule(html, ".flow")
    assert "flex: 1" in flow
    assert f"max-height: {round(h / 3)}px" in flow
    assert "align-items: stretch" in flow
    assert "justify-content: center" in _rule(html, ".stage")


def test_her_screenshot_becomes_a_rounded_glowing_block_without_cropping(tmp_path):
    shot = tmp_path / "экран.png"
    shot.write_bytes(b"png")
    html = templates.build_carousel_slide(hook="Скрин", screenshot=shot, notes=[])
    assert 'class="shot-img"' in html and f'src="{shot.name}"' in html
    rule = _rule(html, ".shot-img")
    assert "object-fit: contain" in rule and "cover" not in rule
    assert f'border-radius: {tokens.RADIUS["card"]}px' in rule
    assert re.search(r"box-shadow: 0 0 \d+px", rule)
    assert "flex: 1" not in _rule(html, ".shot")


def test_long_flow_title_fits_the_card_instead_of_breaking_mid_word():
    # «ВОЗВРАЩЁННОЕ» в ряду из четырёх карточек ломалось посреди слова:
    # кегль подписи потока считается от ширины карточки и длины слова
    def size(html):
        return int(re.search(r"font-size: (\d+)px", _rule(html, ".flow-title")).group(1))

    long_row = templates.build_carousel_slide(
        hook="Поток",
        flow=[{"title": t} for t in
              ("Задача", "Сколько времени", "Как теперь", "Возвращённое время")],
    )
    short_row = templates.build_carousel_slide(
        hook="Поток", flow=[{"title": t} for t in ("Раз", "Два", "Три", "Итог")],
    )
    assert size(short_row) == tokens.TYPE_SCALE["label"]["size"]
    assert size(long_row) < size(short_row)


# --- тело слайда занимает вертикаль, а не висит по центру -------------------
#: Доля холста, которую разрешено занимать пустоте вокруг тела слайда.
#: Замер её образцового кадра (carousel-02, сетка карточек): 158 px из 1350,
#: то есть 11.7 %. Потолок взят с запасом на слайд без нижней плашки, где ряд
#: упирается в её пропорцию «карточка не выше трети холста».
MAX_EMPTY_SHARE = 0.20

#: Как меряем: от низа подзаголовка до верха тела и от низа тела до ближайшей
#: нижней границы (плашка-итог, рукописная строка или подвал).
_EMPTY_JS = """() => {
  const r = e => e.getBoundingClientRect();
  const stage = document.querySelector('.stage');
  const block = stage.children[0];
  const inner = [...block.children].filter(x => !x.classList.contains('steps-line'));
  const boxes = inner.length ? inner : [block];
  const top = Math.min(...boxes.map(x => r(x).top));
  const bottom = Math.max(...boxes.map(x => r(x).bottom));
  const lead = document.querySelector('.rule-accent')
            || document.querySelector('.lead') || document.querySelector('.hero');
  const below = document.querySelector('.summary')
             || document.querySelector('.footer');
  return (top - r(lead).bottom) + (r(below).top - bottom);
}"""


def _empty_px(html, tmp_path, name):
    sync_playwright = render._playwright_module()
    if sync_playwright is None:
        pytest.skip("меряем в браузере: питоновского playwright нет")
    page_path = tmp_path / f"{name}.html"
    page_path.write_text(html, encoding="utf-8")
    w, h = tokens.CANVAS["carousel"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto(page_path.resolve().as_uri())
        try:
            page.wait_for_function("document.fonts.ready", timeout=render.PAGE_TIMEOUT_MS)
        except Exception:  # noqa: BLE001
            pass
        empty = page.evaluate(_EMPTY_JS)
        browser.close()
    return empty


@pytest.mark.parametrize("name", ["cards", "steps", "flow"])
def test_body_fills_the_vertical_instead_of_hanging_in_the_middle(name, tmp_path):
    blocks = {
        "cards": {"cards": [
            {"title": "Монтажёр", "note": "склейки", "icon": "play"},
            {"title": "Дизайнер", "note": "обложки", "icon": "image"},
            {"title": "Копирайтер", "note": "посты", "icon": "doc"},
            {"title": "Сценарист", "note": "рилсы", "icon": "spark"},
        ]},
        "steps": {"steps": [
            {"caption": "Выбери\nзадачу", "note": "Из реальной жизни", "icon": "search"},
            {"caption": "Разбери\nпроцесс", "note": "Как делаю сейчас", "icon": "doc"},
            {"caption": "Отдай\nповторяемое", "note": "Нейросети", "icon": "gear"},
            {"caption": "Проверь\nсама", "note": "Контроль за тобой", "icon": "check"},
        ]},
        "flow": {"flow": [
            {"title": "Задача", "note": "как делала раньше", "icon": "doc"},
            {"title": "Сколько времени", "note": "это занимало", "icon": "clock"},
            {"title": "Как теперь", "note": "с нейросетью", "icon": "spark"},
            {"title": "Возвращённое время", "note": "твоя выгода", "icon": "hourglass"},
        ]},
    }[name]
    # окружение — как в её комплекте: под сеткой и цепочкой стоит плашка-итог,
    # под потоком последнего слайда — рукописная строка
    around = (
        {"handwritten": "Всё получится ♡"} if name == "flow"
        else {"summary": "одна задача → реальный результат → больше уверенности"}
    )
    html = templates.build_carousel_slide(
        hook="Не нужно знать всё",
        body="Нужно увидеть одну задачу, которая забирает время.",
        label="Моя воронка",
        index=4, total=4, style="STYLE_01", **blocks, **around,
    )
    _, h = tokens.CANVAS["carousel"]
    empty = _empty_px(html, tmp_path, name)
    assert empty <= MAX_EMPTY_SHARE * h, f"{name}: пустоты {empty:.0f} px из {h}"


# --- G09–G15: второй эталон владелицы (reference/5..9.webp), 2026-09-22 -------
# Ожидаемое взято из её пяти слайдов и её же слов, а не из кода под тестом:
# шапка `02 / 09` + тонкая линия + метка «ПРИЗНАК 1», оранжевое ключевое слово
# заголовка, рукописные пометки со стрелками, оранжевая отбивка, плашка-сноска.

SECOND = templates.build_carousel_slide(
    hook="1. У тебя куча\nсохранённого",
    accent_word="сохранённого",
    body="Промты.\nГайды.\nПодборки сервисов.",
    label="Признак 1",
    index=2,
    total=9,
    style="STYLE_01",
    role="slide",
    handwritten=["сохранённого много", "ясности мало"],
    summary="Вроде нейросеть помогла.\nНо ручная работа никуда не исчезла.",
)

ORANGE = "#FB9D5B"


def test_orange_is_her_measured_accent_and_not_a_core_color():
    # тон снят с её слайдов reference/5,7,8,9.webp: медиана заливки (251,157,91)
    assert tokens.ACCENT == {"ORANGE_ACCENT": ORANGE}
    assert ORANGE not in tokens.PALETTE.values()
    assert ORANGE not in tokens.OPTIONAL.values()


def test_header_is_a_count_a_thin_line_and_a_short_label():
    # G09: «нет тонких линий сверху» — её шапка: `02 / 09` ── ПРИЗНАК 1
    assert 'class="header-num' in SECOND and ">02<" in SECOND
    assert "/ 09" in SECOND
    assert 'class="header-line"' in SECOND
    assert "ПРИЗНАК 1" in SECOND.upper()
    line = _rule(SECOND, ".header-line")
    assert "flex: 1" in line
    assert int(re.search(r"height: (\d+)px", line).group(1)) <= 2
    assert f'color: {ORANGE}' in _rule(SECOND, ".header-num")


def test_the_chaotic_two_line_thesis_is_gone_from_the_header():
    # G10: «вот эти тезисы сверху смотрятся хаотично»
    noisy = templates.build_carousel_slide(
        hook="Заголовок", thesis="Маленькие шаги.\nБольшие изменения.", index=2, total=9
    )
    assert "header-thesis" not in noisy
    assert "МАЛЕНЬКИЕ ШАГИ." not in noisy.upper()


def test_one_key_word_of_the_headline_is_orange_not_the_whole_line():
    # G11: «оранжевым выделяем главное»
    assert '<span class="accent">сохранённого</span>' in SECOND
    assert SECOND.count('<span class="accent">') == 1
    assert "У тебя куча" in SECOND
    assert f'color: {ORANGE}' in _rule(SECOND, ".hero .accent, .hero em")
    plain = templates.build_carousel_slide(hook="Первая\nВторая", index=2, total=9)
    assert '<span class="accent">' not in plain


def test_the_chain_line_never_crosses_the_numbers():
    # G12: «где цифры прочерчена линия как будто перечеркнуто, так быть не должно»
    html = templates.build_carousel_slide(
        hook="Шаги",
        steps=[{"caption": "Раз"}, {"caption": "Два"}, {"caption": "Три"}],
    )
    assert "steps-line" not in html
    assert html.count('class="step-link"') == 2
    link = _rule(html, ".step-link")
    assert "position: absolute" not in link
    assert ORANGE in link


def test_thin_rules_and_accent_borders_are_orange():
    # G13: «линии тоже можно делать оранжевыми и обводки плашек»
    assert 'class="rule-accent"' in SECOND
    rule = _rule(SECOND, ".rule-accent")
    assert f"background: {ORANGE}" in rule
    assert int(re.search(r"width: (\d+)px", rule).group(1)) <= 240
    accented = templates.build_carousel_slide(
        hook="Ряд",
        cards=[{"title": "Раз"}, {"title": "Два", "accent": True}],
        style="STYLE_01",
    )
    assert f"border-color: {ORANGE}" in _rule(accented, ".card.accent")


def test_handwritten_notes_are_orange_slanted_and_carry_an_arrow():
    # G14: по две-три пометки на слайд, у каждой изогнутая стрелка
    assert SECOND.count('class="hand-note') == 2
    assert SECOND.count('class="hand-arrow"') == 2
    assert "сохранённого много" in SECOND and "ясности мало" in SECOND
    note = _rule(SECOND, ".hand-note")
    assert f"color: {ORANGE}" in note
    assert f"'{tokens.HAND_FONT}', {tokens.HAND_FALLBACK}" in note
    assert "rotate(" in _css(SECOND)
    # пометки стоят на любом слайде, а не только на первом и последнем
    middle = templates.build_carousel_slide(
        hook="Середина", handwritten=["поиск не решает хаос"], index=5, total=9
    )
    assert middle.count('class="hand-note') == 1


def test_footnote_plate_has_an_orange_bang_and_two_lines():
    # её слайд 04: кружок `!`, вертикальная черта, белая строка и сиреневая
    assert 'class="summary-mark"' in SECOND and ">!<" in SECOND
    assert 'class="summary-divider"' in SECOND
    assert SECOND.count('class="summary-line"') == 1
    assert SECOND.count('class="summary-line accent"') == 1
    assert "Вроде нейросеть помогла." in SECOND
    assert f'color: {ORANGE}' in _rule(SECOND, ".summary-mark")
    assert tokens.PALETTE["VIOLET_SOFT"] in _rule(SECOND, ".summary-line.accent")


def test_the_screenshot_becomes_the_scene_on_the_right(tmp_path):
    shot = tmp_path / "экран.png"
    shot.write_bytes(b"png")
    html = templates.build_carousel_slide(
        hook="Скрин", body="Слева текст.", screenshot=shot, notes=[]
    )
    assert 'class="canvas scene"' in html
    scene = _rule(html, ".canvas.scene .hero, .canvas.scene .lead")
    assert "max-width" in scene
    assert "position: absolute" in _rule(html, ".shot")


def test_skill_describes_the_second_reference():
    text = SKILL.read_text(encoding="utf-8")
    for word in ("accent_word", "hand-note", "ORANGE_ACCENT", "step-link"):
        assert word in text, word


# --- G15: её портрет без белого фона -----------------------------------------
# «Убери фон, раствори край» (2026-09-22). Проверяем не картинку на глаз, а то,
# что в сохранённом файле у краёв нет непрозрачного белого прямоугольника.

from integrations.visuals import cutout

PORTRAIT = Path(__file__).resolve().parents[1] / "essa-ai" / "photo" / "katerina-portrait.webp"


def test_cutout_drops_the_white_wall_and_keeps_the_face(tmp_path):
    if render._playwright_module() is None:
        pytest.skip("вырезаем браузером: питоновского playwright нет")
    assert PORTRAIT.is_file(), PORTRAIT
    out = cutout.make_cutout(PORTRAIT, tmp_path / "cut.png")
    assert out is not None and out.is_file()
    # читаем обратно уже сохранённый файл, а не то, что посчитал вырезатель
    probe = cutout.alpha_probe(out)
    assert probe["top_left"] < 24, probe
    assert probe["top_right"] < 24, probe
    assert probe["center"] > 230, probe
    # исходник владелицы не тронут
    assert PORTRAIT.suffix == ".webp" and PORTRAIT.stat().st_size > 0


def test_cutout_says_plainly_when_the_browser_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    assert cutout.make_cutout(PORTRAIT, tmp_path / "cut.png") is None
