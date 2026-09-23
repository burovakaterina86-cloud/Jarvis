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
    | {c.upper() for c in tokens.CAROUSEL_PALETTE.values()}
    | {c.upper() for c in tokens.PLATE.values()}
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

#: Короткие имена трёх холстов — идентификаторы для parametrize.
CANVAS_IDS = ("carousel", "cover", "story")


# id задаётся явно: без него pytest берёт идентификатором саму вёрстку и кладёт
# её в PYTEST_CURRENT_TEST — а переменная окружения Windows обрывается на 32767
# знаках, и тест падает ещё до запуска.
@pytest.mark.parametrize("html", [CAROUSEL, COVER, STORY], ids=CANVAS_IDS)
def test_no_invented_colors(html):
    assert _hexes(html) <= ALLOWED_HEX, _hexes(html) - ALLOWED_HEX


@pytest.mark.parametrize("html", [CAROUSEL, COVER, STORY], ids=CANVAS_IDS)
def test_no_third_typeface(html):
    assert _families(html) <= set(tokens.FONT_FAMILIES), _families(html)
    assert tokens.GOOGLE_FONTS_URL in html


@pytest.mark.parametrize(
    "html,kind",
    [(CAROUSEL, "carousel"), (COVER, "cover"), (STORY, "story")],
    ids=CANVAS_IDS,
)
def test_canvas_size_matches_her_files(html, kind):
    w, h = tokens.CANVAS[kind]
    assert f"width: {w}px" in html and f"height: {h}px" in html


def test_carousel_uses_her_type_scale_and_safe_zone():
    assert f"font-size: {tokens.TYPE_SCALE['hook']['size']}px" in CAROUSEL
    # у карусели поля свои (её §1), общий safe zone остался за обложкой и сторис
    assert f"padding: {tokens.SAFE_ZONE}px" in COVER


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
    # G17: между карточками рисованная дуга, а не типографский знак `→`;
    # сам `ARROW` остался разделителем в тексте слайда (`auto_blocks`)
    assert html.count('class="flow-arrow"') == 2
    assert html.count(templates.FLOW_ARROW) == 2
    assert html.count('class="flow-card') == 3
    assert 'class="flow-card accent"' in html
    assert f'background: {templates.STYLE_SURFACES["STYLE_01"]["fill"]}' in html


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
    # §12 ИКОНКИ: белые или светло-фиолетовые
    assert tokens.CAROUSEL_PALETTE["VIOLET_LIGHT"] in DENSE


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
            r"background: linear-gradient\(152deg, (#[0-9A-Fa-f]{6})",
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
    assert f'background: {templates.STYLE_SURFACES["STYLE_01"]["fill"]}' in accent
    assert re.search(r"box-shadow: 0 0 \d+px", accent)  # свечение вокруг узла
    assert 'class="card accent"' in GRID


def test_canvas_keeps_a_background_glow_behind_the_content():
    # §14 отменил пятно-blob; глубина за контентом осталась — её даёт
    # направленный свет §10, а не круг
    assert "linear-gradient" in _rule(GRID, ".light")
    assert 'class="light"' in GRID


def test_stage_fills_the_vertical_between_hero_and_footer():
    # тело слайда забирает вертикаль между заголовком и подвалом; сами блоки
    # при этом высотой по содержимому — вертикаль уходит в отступы вокруг них
    for selector in (".stage", ".steps"):
        assert "flex: 1" in _rule(GRID, selector), selector
    # безопасные поля при этом на месте — по её §1
    m = tokens.CAROUSEL_MARGIN
    assert f'padding: {m["top"]}px {m["right"]}px {m["bottom"]}px {m["left"]}px' in GRID


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
    # §8 TYPE B: скрин живёт внутри корпуса, а не лежит прямоугольником
    assert 'class="device-screen"' in html and f'src="{shot.name}"' in html
    rule = _rule(html, ".device-screen")
    assert f"border-radius: {tokens.PLATE_RADIUS}px" not in rule  # это экран, не плашка
    assert "overflow: hidden" in rule
    # объём корпуса: мягкая тень и подсветка, а не плоский прямоугольник
    assert re.search(r"box-shadow: .*0 0 \d+px", _rule(html, ".device-body"))
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

ORANGE = "#FF955E"


def test_orange_is_her_measured_accent_and_not_a_core_color():
    # 2026-09-22 она прислала точное значение сама: §3 её системы каруселей.
    # Прежний тон #FB9D5B был замером пипеткой по reference/5,7,8,9.webp.
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
    assert tokens.CAROUSEL_PALETTE["VIOLET_LIGHT"] in _rule(
        SECOND, ".summary-line.accent"
    )


def test_the_screenshot_becomes_the_scene_on_the_right(tmp_path):
    shot = tmp_path / "экран.png"
    shot.write_bytes(b"png")
    html = templates.build_carousel_slide(
        hook="Скрин", body="Слева текст.", screenshot=shot, notes=[]
    )
    assert 'class="canvas scene type-b"' in html
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


#: Второй кадр владелицы (2026-09-23): ¾, взгляд в сторону, тёмный фон.
PORTRAIT_2 = (
    Path(__file__).resolve().parents[1] / "essa-ai" / "photo" / "katerina-portrait-2.jpg"
)


def test_the_dark_wall_dissolves_and_her_lit_face_stays(tmp_path):
    # Её §9: «человек не должен постоянно смотреть в камеру». Второй кадр снят
    # на тёмной стене, светлая заливка на нём не срабатывает — проверяем, что
    # у второго способа стена уходит в прозрачность, а освещённое лицо нет.
    if render._playwright_module() is None:
        pytest.skip("вырезаем браузером: питоновского playwright нет")
    assert PORTRAIT_2.is_file(), PORTRAIT_2
    out = cutout.make_dark_fade(PORTRAIT_2, tmp_path / "fade.png")
    assert out is not None and out.is_file()
    probe = cutout.alpha_probe(out)
    assert probe["top_left"] < 24, probe
    assert probe["top_right"] < 24, probe
    assert probe["center"] > 200, probe
    # исходник владелицы не тронут
    assert PORTRAIT_2.suffix == ".jpg" and PORTRAIT_2.stat().st_size > 0


def test_cutout_says_plainly_when_the_browser_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    assert cutout.make_cutout(PORTRAIT, tmp_path / "cut.png") is None


# --- G16–G18: объём и предметная сцена из её скринов (2026-09-22) ------------
# Ожидаемое — из её слов («делай объемнее плашки, иконки и стрелки», «скрины
# приложи как на референсе было на слайд») и из reference/5.webp и 8.webp,
# а не из кода под тестом.

#: Её четыре скрина, присланные 2026-09-22. Лежат в её папке, только читаются.
SCREENS_DIR = Path(__file__).resolve().parents[1] / "essa-ai" / "photo" / "screens"
HER_SCREENS = [
    SCREENS_DIR / "files-list.png",
    SCREENS_DIR / "project-menu.png",
    SCREENS_DIR / "deck-preview.jpg",
]


def _measure(html, tmp_path, name, js):
    """Померить готовый кадр в браузере — там же, где его увидит владелица."""
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
        value = page.evaluate(js)
        browser.close()
    return value


# --- G16: карточка без пояснения не занимает треть холста --------------------

ROLES = ("Монтажёр", "Дизайнер", "Копирайтер", "Сценарист", "SMM")


def test_a_row_of_cards_without_notes_does_not_eat_a_third_of_the_canvas(tmp_path):
    # её carousel-03: пять плашек с одним словом растянулись на пол-слайда
    bare = templates.build_carousel_slide(
        hook="А теперь ты ещё",
        cards=[{"title": t} for t in ROLES],
        style="STYLE_01",
    )
    assert 'class="cards compact"' in bare
    _, h = tokens.CANVAS["carousel"]
    height = _measure(
        bare, tmp_path, "bare-cards",
        "() => document.querySelector('.cards').getBoundingClientRect().height",
    )
    assert height <= h / 3, f"ряд без пояснений занял {height:.0f} px из {h}"


def test_a_row_of_cards_with_notes_still_fills_the_body():
    # пояснения есть — карточка снова полноценная коробка, ряд занимает тело
    dense = templates.build_carousel_slide(
        hook="Одно сообщество",
        cards=[{"title": "Видео", "note": "склейки"}, {"title": "Тексты", "note": "посты"}],
    )
    assert 'class="cards"' in dense and "cards compact" not in dense
    assert "flex: 1" in _rule(dense, ".cards")


# --- G16: иконки в ряду различаются ------------------------------------------

def test_icons_are_picked_by_the_meaning_of_her_caption():
    # имя иконки не задано — берётся по смыслу подписи из её же словаря ICONS
    assert templates.pick_icon("Монтаж роликов") == "play"
    assert templates.pick_icon("Тексты и посты") == "doc"
    assert templates.pick_icon("Проверяю результат сама") == "check"
    assert templates.pick_icon("Сколько времени это занимало") == "clock"
    # ничего не подошло — честный нейтральный маркер, а не иконка про другое
    assert templates.pick_icon("Ыыы") == templates.DEFAULT_STEP_ICON
    for name, _keys in templates.ICON_HINTS:
        assert name in templates.ICONS, name


def test_a_row_of_different_captions_gets_different_icons():
    html = templates.build_carousel_slide(
        hook="Четыре шага",
        steps=[
            {"caption": "Что за задача"},
            {"caption": "Как делаю сейчас, по шагам"},
            {"caption": "Что из этого повторяется"},
            {"caption": "Проверяю результат сама"},
        ],
    )
    drawn = {p for p in templates.ICONS.values() if p in html}
    assert len(drawn) >= 3, "ряд снова вышел одинаковым"
    assert templates.ICONS[templates.DEFAULT_STEP_ICON] not in drawn


# --- G17: объём плашек, иконок и стрелок -------------------------------------

def test_plates_have_a_lit_top_a_dark_bottom_and_an_inner_glow():
    card = _rule(GRID, ".card")
    assert "inset 0 2px 0" in card                       # светлая кромка сверху
    assert "inset 0 -2px 0" in card                      # тёмная снизу
    assert re.search(r"inset 0 20px 44px -20px", card)   # внутренняя подсветка
    assert re.search(r"0 24px 48px", card)               # мягкая тень
    assert re.search(r"0 6px 14px", card)                # короткая контактная тень


def test_icons_are_bigger_than_the_caption_and_glow():
    label = tokens.TYPE_SCALE["label"]["size"]
    size = int(re.search(r'class="icon" viewBox="0 0 24 24" width="(\d+)"', GRID).group(1))
    assert size >= label * 2.5, "иконка всё ещё мельче её эталона"
    assert "drop-shadow" in _rule(GRID, ".icon")


def test_the_arrow_between_cards_is_a_drawn_arc_not_a_stick():
    html = templates.build_carousel_slide(
        hook="Механизм", body="Задача → Процесс → Контроль", style="STYLE_01"
    )
    assert templates.FLOW_ARROW in html
    assert "C" in templates.FLOW_ARROW, "дуга, а не прямая палочка"
    assert templates.FLOW_ARROW.count("<path") == 2, "нет открытого наконечника"
    assert float(re.search(r'stroke-width="([\d.]+)"', templates.FLOW_ARROW).group(1)) >= 3
    assert tokens.ACCENT["ORANGE_ACCENT"] in _rule(html, ".flow-arrow")
    assert "drop-shadow" in _rule(html, ".flow-arrow-svg")


def test_the_handwritten_arrow_is_thick_enough_to_be_seen():
    width = float(re.search(r'stroke-width="([\d.]+)"', templates.HAND_ARROW).group(1))
    assert width >= 3


# --- G18: предметная сцена из её скринов -------------------------------------

def test_her_screens_lie_tilted_in_a_stack_on_the_right():
    notes = []
    html = templates.build_carousel_slide(
        hook="У тебя куча сохранённого",
        body="Промты.\nГайды.",
        screens=HER_SCREENS,
        style="STYLE_01",
        notes=notes,
    )
    assert html.count('class="screen-card') == 3
    assert len(notes) == 3 and all(n.startswith("screen:") for n in notes)
    # каждый снимок повёрнут, и повороты разные — это стопка, а не колонка
    tilts = {
        a for a in re.findall(r"transform: rotate\((-?[\d.]+)deg\)", _css(html))
        if abs(float(a)) >= 3
    }
    assert len(tilts) >= 3, "скрины лежат без наклона или под одним углом"
    # текст ушёл в левую половину, сцена — правая
    assert "screens-scene" in html
    text_width = int(
        re.search(
            r"max-width: (\d+)%",
            _rule(html, ".canvas.screens-scene .hero, .canvas.screens-scene .lead"),
        ).group(1)
    )
    assert text_width <= 50
    assert "position: absolute" in _rule(html, ".screens")


def test_a_screen_is_texture_and_is_never_enlarged():
    # её слова: «на смысл скринов не смотри» — но и не раздувай их так, чтобы
    # мелкий текст читался крупно: снимок не растягивается выше своего размера
    html = templates.build_carousel_slide(hook="Скрины", screens=HER_SCREENS, notes=[])
    # снимок живёт в экране корпуса и не вырастает больше него
    img = _rule(html, ".device-screen img")
    assert "width: auto" in img and "height: auto" in img
    assert "max-width" in img and "max-height" in img
    card = _rule(html, ".screen-card")
    assert "width:" in card
    assert "scale(0." in _css(html)  # дальние карточки ещё и мельче


def test_the_rendered_screens_stay_inside_the_canvas_and_their_own_size(tmp_path):
    import shutil as _shutil

    html = templates.build_carousel_slide(
        hook="У тебя куча\nсохранённого",
        accent_word="сохранённого",
        body="Промты.\nГайды.",
        screens=HER_SCREENS,
        index=2, total=9, style="STYLE_01", notes=[],
    )
    for src in HER_SCREENS:
        _shutil.copyfile(src, tmp_path / src.name)
    w, h = tokens.CANVAS["carousel"]
    measured = _measure(
        html, tmp_path, "screens",
        """() => [...document.querySelectorAll('.screen-img')].map(i => {
             // getBoundingClientRect у повёрнутой карточки — габарит, а не размер
             // самой картинки: свой размер берём из offsetWidth
             const r = i.getBoundingClientRect();
             return [i.offsetWidth, i.offsetHeight, i.naturalWidth,
                     r.left, r.right, r.bottom];
        })""",
    )
    assert len(measured) == 3
    for width, height, natural, left, right, bottom in measured:
        assert width <= natural + 1, "снимок раздут крупнее оригинала"
        assert left >= w * 0.40, "сцена залезла в текстовую колонку"
        assert right <= w + 1 and bottom <= h, "скрин вылез за холст"
        assert height > 0


def test_kit_carries_a_whole_list_of_screens_next_to_the_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    items = kit.build_kit_visuals(
        tmp_path / "комплект",
        carousel_slides=[{"hook": "Скрины", "screens": HER_SCREENS}],
    )
    out = tmp_path / "комплект" / kit.VISUALS_DIR
    for src in HER_SCREENS:
        assert (out / src.name).is_file(), src.name
    html = items[0].html_path.read_text(encoding="utf-8")
    for src in HER_SCREENS:
        assert f'src="{src.name}"' in html


# --- G19: скрины размыты ------------------------------------------------------
# Ожидаемое — из её слов 2026-09-22 («делай скрины размытыми») и из таска 09:
# скрин узнаётся как интерфейс, но ни одна надпись не читается.

def test_every_screen_of_the_scene_is_blurred_by_default(tmp_path):
    html = templates.build_carousel_slide(hook="Скрины", screens=HER_SCREENS, notes=[])
    imgs = re.findall(r"<img class=\"screen-img\"[^>]*>", html)
    assert len(imgs) == 3
    assert all(f"blur({tokens.SCREEN_BLUR}px)" in img for img in imgs)
    # степень названа в токенах, а не числом внутри разметки
    assert tokens.SCREEN_BLUR >= 6

    shot = tmp_path / "скрин.png"
    shot.write_bytes(b"")
    single = templates.build_carousel_slide(hook="Скрин", screenshot=shot, notes=[])
    assert f"blur({tokens.SCREEN_BLUR}px)" in re.search(
        r"<img class=\"shot-img\"[^>]*>", single
    ).group(0)


def test_slide_data_cannot_turn_the_blur_off():
    off = templates.build_carousel_slide(
        hook="Скрины",
        screens=[{"src": s, "blur": False, "filter": "none"} for s in HER_SCREENS],
        notes=[],
    )
    assert off.count(f"blur({tokens.SCREEN_BLUR}px)") == 3
    assert "filter: none" not in off


# --- G20: пометки пишутся отдельно -------------------------------------------
# Её слова: «пометки отдельно пиши». У неё это комментарий сбоку
# («сохранённого много», «инструменты ≠ система»), а не повтор заголовка.

def test_a_slide_without_the_field_has_no_handwritten_notes():
    html = templates.build_carousel_slide(
        hook="Ты эксперт\nв своём деле",
        body="Ты годами учился.",
        index=2, total=9, notes=[],
    )
    assert 'class="hand-note' not in html


def test_a_note_repeating_the_headline_or_the_lead_is_not_drawn():
    # её слайд 06: обе пометки были пересказом заголовка и лида
    html = templates.build_carousel_slide(
        hook="Вопрос не «что мне выучить»",
        body="Вопрос: «что я больше\nне хочу делать руками?»",
        handwritten=[
            "что мне выучить",
            "что не хочу делать руками",
            "инструменты ≠ система",
        ],
        index=6, total=9, notes=[],
    )
    assert html.count('class="hand-note') == 1
    assert "инструменты ≠ система" in html
    assert "что мне выучить</span>" not in html

    # её слайд 07: пометка повторяла подпись шага, которая тут же и стоит
    chain = templates.build_carousel_slide(
        hook="Задача → Процесс → Нейросеть → Контроль",
        steps=[{"caption": "Что за задача"}, {"caption": "Проверяю результат сама"}],
        handwritten=["проверяю результат сама"],
        index=7, total=9, notes=[],
    )
    assert 'class="hand-note' not in chain


# --- G21 / D03–D05: её дизайн-система каруселей ------------------------------
# `essa-ai/18_CAROUSEL_VISUAL_SYSTEM.md`, прислана 2026-09-22 целиком.
# Значения ниже переписаны из её файла руками, раздел за разделом.

HER_CAROUSEL_PALETTE = {
    "BG_DEEP": "#0D0D10",
    "BG_BASE": "#111115",
    "BG_RAISED": "#17151A",
    "TEXT": "#F5F3F0",
    "TEXT_MUTED": "#C9C6C3",
    "TEXT_DIM": "#A8A5A5",
    "ORANGE": "#FF955E",
    "ORANGE_WARM": "#FF9D66",
    "ORANGE_DEEP": "#F58C54",
    "VIOLET": "#A77BFF",
    "VIOLET_DEEP": "#8B63DA",
    "VIOLET_LIGHT": "#C2A5FF",
}


def test_her_carousel_palette_is_taken_from_her_file_verbatim():
    # §3 ЦВЕТОВАЯ СИСТЕМА
    assert tokens.CAROUSEL_PALETTE == HER_CAROUSEL_PALETTE
    # оранжевый карусели — из её §3, а не прежний снятый пипеткой тон
    assert tokens.ACCENT["ORANGE_ACCENT"] == "#FF955E"


def test_plate_colors_and_radius_come_from_her_section_13():
    # §13 ИНФОРМАЦИОННЫЕ ПЛАШКИ: #18171E / #211E29, radius 20–28
    assert tokens.PLATE == {"BASE": "#18171E", "RAISED": "#211E29"}
    assert tokens.PLATE_RADIUS_RANGE == (20, 28)
    lo, hi = tokens.PLATE_RADIUS_RANGE
    assert lo <= tokens.PLATE_RADIUS <= hi


def test_carousel_margins_are_inside_her_section_1_ranges():
    # §1 ФОРМАТ: слева/справа 55–70, сверху 45–60, снизу 60–80
    assert tokens.CAROUSEL_MARGIN_RANGE == {
        "top": (45, 60), "right": (55, 70), "bottom": (60, 80), "left": (55, 70),
    }
    for side, (lo, hi) in tokens.CAROUSEL_MARGIN_RANGE.items():
        assert lo <= tokens.CAROUSEL_MARGIN[side] <= hi, side


def test_headline_area_and_second_level_ratio_are_her_numbers():
    # §4: заголовок 30–50% площади слайда; §5: второй уровень меньше в 2,5–4 раза
    assert tokens.HEADLINE_AREA_RANGE == (0.30, 0.50)
    assert tokens.BODY_RATIO_RANGE == (2.5, 4.0)
    assert tokens.BODY_WORDS_PER_LINE == (4, 8)


def test_five_composition_types_exist():
    # §8 КОМПОЗИЦИЯ: A photo, B object/device, C diagram, D ui chaos, E typographic
    assert tokens.COMPOSITION_TYPES == ("A", "B", "C", "D", "E")


# --- D04: §14 — фоновых пятен нет, есть пространство и направленный свет ------

SYSTEM = templates.build_carousel_slide(
    hook="1. У тебя куча\nсохранённого",
    accent_word="сохранённого",
    body="Промты и гайды копятся, а ясности от этого не прибавляется совсем.",
    label="Признак 1",
    index=2, total=9, style="STYLE_01", role="slide",
    handwritten=["сохранённого много", "ясности мало"],
    summary="Вроде нейросеть помогла.\nНо ручная работа никуда не исчезла.",
)

SYSTEM_PLATES = templates.build_carousel_slide(
    hook="Плашки",
    cards=[{"title": "Раз"}, {"title": "Два"}],
    flow=[{"title": "А"}, {"title": "Б"}],
    summary="Первая строка.\nВторая строка.",
    index=4, total=9, style="STYLE_01",
)


def test_no_abstract_circles_or_blobs_in_the_background():
    # §14 ДЕКОР: «Не использовать: абстрактные кружки; случайные blobs»
    assert 'class="glow"' not in SYSTEM
    assert 'class="glow-2"' not in SYSTEM


def test_background_gives_space_and_warm_directional_light():
    # §10 СВЕТ: фон не просто чёрный, ощущается пространство и направленный свет
    canvas = _rule(SYSTEM, ".canvas#slide")
    assert "linear-gradient" in canvas  # чёрный → тёмный фиолетовый (§3)
    assert tokens.CAROUSEL_PALETTE["BG_DEEP"] in canvas
    beam = _rule(SYSTEM, ".light")
    assert "linear-gradient" in beam and "border-radius: 50%" not in beam
    assert 'class="light"' in SYSTEM
    # §10 «размытая поверхность»: дальний план размыт
    assert "blur(" in _rule(SYSTEM, ".surface")
    assert 'class="surface"' in SYSTEM


def test_slide_has_three_layers_background_content_foreground():
    # §11 ГЛУБИНА: минимум три визуальных слоя
    zs = {
        int(re.search(r"z-index: (-?\d+)", _rule(SYSTEM, sel)).group(1))
        for sel in (".light", ".hero", ".hand-note")
    }
    assert len(zs) >= 3


# --- D05: §8 TYPE B — скрин внутри корпуса устройства, в перспективе ---------


def _with_shot(tmp_path, **kw):
    shot = tmp_path / "экран.png"
    shot.write_bytes(b"png")
    return templates.build_carousel_slide(
        hook="Скрин", body="Слева текст.", screenshot=shot, notes=[], **kw
    )


def test_a_screenshot_never_lies_flat_it_sits_in_a_device_body(tmp_path):
    # §8 TYPE B: «Не использовать плоский screenshot, лежащий прямоугольником
    # поверх фона. Screenshot должен быть встроен в физический объект»
    html = _with_shot(tmp_path)
    assert 'class="device' in html
    assert "perspective:" in _rule(html, ".device")
    body = _rule(html, ".device-body")
    assert "rotateY(" in body
    assert "overflow: hidden" in _rule(html, ".device-screen")
    # корпус — не рамка вокруг пустоты: скрин лежит внутри него
    assert re.search(r'<div class="device-screen">\s*<img', html)


def test_the_device_kind_comes_from_the_slide_and_both_bodies_exist(tmp_path):
    laptop = _with_shot(tmp_path, device="laptop")
    phone = _with_shot(tmp_path, device="phone")
    assert 'class="device laptop"' in laptop
    assert 'class="device-base"' in laptop  # у ноутбука есть основание с петлёй
    assert 'class="device phone"' in phone
    assert 'class="device-notch"' in phone


def test_blur_of_her_screens_survives_the_device_body(tmp_path):
    # G19 принято отдельно и корпусом не отменяется
    assert f"blur({tokens.SCREEN_BLUR}px)" in _with_shot(tmp_path)


def test_every_screen_of_the_stack_also_gets_a_body(tmp_path):
    files = []
    for name in ("a.png", "b.png"):
        f = tmp_path / name
        f.write_bytes(b"png")
        files.append(f)
    html = templates.build_carousel_slide(
        hook="Хаос", screens=files, index=5, total=9, style="STYLE_01", notes=[]
    )
    assert html.count('class="device-screen"') == 2
    # §8 TYPE D: дальние карточки темнее
    assert "brightness(" in _css(html)


# --- §1, §4, §5, §13: числа её системы ---------------------------------------


def test_carousel_margins_are_her_section_1_and_not_the_common_safe_zone():
    m = tokens.CAROUSEL_MARGIN
    assert (
        f'padding: {m["top"]}px {m["right"]}px {m["bottom"]}px {m["left"]}px'
        in _css(SYSTEM)
    )
    assert f"padding: {tokens.SAFE_ZONE}px" not in _css(SYSTEM)


def test_headline_takes_between_a_third_and_a_half_of_the_slide():
    h = tokens.CANVAS["carousel"][1]
    lo, hi = tokens.HEADLINE_AREA_RANGE
    hero = _rule(SYSTEM, ".hero")
    assert f"min-height: {round(h * lo)}px" in hero
    assert f"max-height: {round(h * hi)}px" in hero


def test_second_level_text_is_another_face_and_2_5_to_4_times_smaller():
    hero_size = int(re.search(r"font-size: (\d+)px", _rule(SYSTEM, ".hero")).group(1))
    lead_size = int(re.search(r"font-size: (\d+)px", _rule(SYSTEM, ".lead")).group(1))
    lo, hi = tokens.BODY_RATIO_RANGE
    assert lo <= hero_size / lead_size <= hi
    assert tokens.FONTS["BODY"] != tokens.FONTS["HEADLINE"]


def test_a_long_line_of_her_text_is_broken_at_her_word_limit():
    # §5: 4–8 слов в строке
    lead = re.search(r'<p class="lead">(.*?)</p>', SYSTEM, re.S).group(1)
    for line in lead.split("<br>"):
        assert len(re.sub(r"<[^>]+>", " ", line).split()) <= tokens.BODY_WORDS_PER_LINE[1]


def test_plates_use_her_section_13_colors_and_radius():
    for selector in (".summary", ".flow-card", ".card"):
        rule = _rule(SYSTEM_PLATES, selector)
        assert f"border-radius: {tokens.PLATE_RADIUS}px" in rule, selector
        assert tokens.PLATE["BASE"] in rule, selector
        assert tokens.CAROUSEL_PALETTE["VIOLET_DEEP"] in rule, selector


def test_icons_are_white_or_light_violet_line_icons():
    # §12 ИКОНКИ: одинаковая толщина штриха, белые или светло-фиолетовые
    strokes = set(
        re.findall(r'<svg class="icon"[^>]*stroke="(#[0-9A-Fa-f]{6})"', SYSTEM_PLATES)
    )
    assert strokes <= {
        tokens.CAROUSEL_PALETTE["TEXT"],
        tokens.CAROUSEL_PALETTE["VIOLET_LIGHT"],
    }, strokes
    widths = set(
        re.findall(r'<svg class="icon"[^>]*stroke-width="([\d.]+)"', SYSTEM_PLATES)
    )
    assert len(widths) == 1


# --- §8 / §17: пять типов композиции и ритм карусели -------------------------


def test_composition_type_is_written_into_the_slide():
    assert 'data-composition="E"' in SYSTEM  # только текст и плашка
    assert "type-e" in SYSTEM


def test_composition_type_is_derived_from_what_the_slide_carries(tmp_path):
    f = tmp_path / "s.png"
    f.write_bytes(b"png")

    def kind(**kw):
        html = templates.build_carousel_slide(hook="X", notes=[], **kw)
        return re.search(r'data-composition="([A-E])"', html).group(1)

    assert kind(photo=f) == "A"
    assert kind(screenshot=f) == "B"
    assert kind(steps=[{"caption": "раз"}, {"caption": "два"}]) == "C"
    assert kind(cards=[{"title": "раз"}, {"title": "два"}]) == "D"
    assert kind(body="Просто текст.") == "E"


def test_a_given_type_wins_over_the_derived_one():
    html = templates.build_carousel_slide(hook="X", body="текст", composition="C")
    assert 'data-composition="C"' in html
    with pytest.raises(ValueError):
        templates.build_carousel_slide(hook="X", composition="Z")


def test_nine_slides_do_not_end_up_as_nine_identical_grids(tmp_path, monkeypatch):
    # §17 РИТМ КАРУСЕЛИ: «Не делать девять одинаковых слайдов»
    monkeypatch.setattr(render, "_playwright_module", lambda: None)
    shot = tmp_path / "s.png"
    shot.write_bytes(b"png")
    slides = [
        {"hook": "Обложка", "photo": shot},
        {"hook": "Скрины", "screenshot": shot},
        {"hook": "Текст", "body": "Одна мысль на слайд."},
        {"hook": "Схема", "steps": [{"caption": "раз"}, {"caption": "два"}]},
        {"hook": "Ряд", "cards": [{"title": "раз"}, {"title": "два"}]},
        {"hook": "Текст 2", "body": "Ещё одна мысль."},
        {"hook": "Поток", "flow": [{"title": "А"}, {"title": "Б"}]},
        {"hook": "Текст 3", "body": "И ещё одна."},
        {"hook": "Финал", "photo": shot},
    ]
    items = kit.build_kit_visuals(tmp_path / "k", carousel_slides=slides)
    kinds = {
        re.search(
            r'data-composition="([A-E])"', i.html_path.read_text(encoding="utf-8")
        ).group(1)
        for i in items
    }
    assert len(kinds) >= 3, kinds


def test_skill_teaches_her_carousel_visual_system():
    # навык обязан называть её файл и то, что он отменил
    text = SKILL.read_text(encoding="utf-8")
    assert "ESSA_PRESENTATION_STYLE.md" in text  # её файл, таск 12 п.4
    for mark in ("CAROUSEL_PALETTE", "CAROUSEL_MARGIN", "PLATE", "composition"):
        assert mark in text, mark
    assert "blobs" in text  # §14: пятен в фоне нет
    assert "корпуса" in text and "перспективе" in text  # §8 TYPE B


# --- Таск 11: дефекты карусели «7 признаков» (её слова 2026-09-22) -----------
# Ожидаемое — из её §8 TYPE A/B/C, §13, §18 и из девяти пунктов таска,
# а не из кода под тестом.

HER_PORTRAIT = (
    Path(__file__).resolve().parents[1] / "essa-ai" / "photo"
    / "katerina-portrait-cutout.png"
)

#: Подписи цепочки её слайда 06 — дословно из storyboard.md.
HER_FLOW = ("сценарий", "текст", "оформление", "монтаж", "публикация")

#: Четыре пункта её финального слайда — дословно из storyboard.md.
HER_CHAIN = (
    "что действительно нужно делать",
    "что можно убрать",
    "что отдать нейросети",
    "что оставить человеку",
)


def _carry_portrait(tmp_path):
    if not HER_PORTRAIT.is_file():
        pytest.skip("портрета владелицы нет на диске")
    dst = tmp_path / HER_PORTRAIT.name
    dst.write_bytes(HER_PORTRAIT.read_bytes())
    return dst


def _with_portrait(tmp_path, **kw):
    """Её финальный слайд: портрет, вертикальная цепочка и плашка-вывод."""
    return templates.build_carousel_slide(
        hook="Иногда проблема\nне в том, что\nу тебя не та\nнейросеть.",
        accent_word="не та",
        body="Проблема в том, что никто\nне разобрал сам процесс:",
        chain=[{"title": t} for t in HER_CHAIN],
        summary="Сохрани карусель и посмотри:\nкакой процесс сейчас самый хаотичный?",
        summary_accent=True,
        photo=_carry_portrait(tmp_path),
        index=9, total=9, style="STYLE_01", role="slide", notes=[],
        **kw,
    )


# п.1 — плашка и портрет не пересекаются, считается по разметке

def test_the_plate_and_the_portrait_never_overlap_on_the_final_slide(tmp_path):
    html = _with_portrait(tmp_path)
    boxes = _measure(
        html, tmp_path, "final-slide",
        "() => ['.summary', '.portrait'].map(s => {"
        "const r = document.querySelector(s).getBoundingClientRect();"
        "return [r.left, r.top, r.right, r.bottom];})",
    )
    plate, portrait = boxes
    overlap_x = min(plate[2], portrait[2]) - max(plate[0], portrait[0])
    overlap_y = min(plate[3], portrait[3]) - max(plate[1], portrait[1])
    assert overlap_x <= 0 or overlap_y <= 0, (
        f"плашка {plate} налезла на портрет {portrait}"
    )


# п.2 — §8 TYPE A: человек занимает правые 40–55% кадра

def test_her_portrait_takes_the_forty_to_fifty_five_percent_of_her_type_a(tmp_path):
    w = tokens.CANVAS["carousel"][0]
    lo, hi = tokens.PORTRAIT_WIDTH_RANGE
    for frac in (lo, tokens.PORTRAIT_WIDTH, hi):
        html = _with_portrait(tmp_path, portrait_width=frac)
        width = _measure(
            html, tmp_path, f"portrait-{frac}",
            "() => document.querySelector('.portrait-img').getBoundingClientRect().width",
        )
        assert lo <= width / w <= hi, f"портрет занял {width / w:.0%} кадра"
    with pytest.raises(ValueError):
        _with_portrait(tmp_path, portrait_width=hi + 0.2)


def test_the_soft_edge_of_the_cutout_does_not_eat_the_portrait(tmp_path):
    # вырез растворяется в фоне узкой кромкой, а не третью кадра
    html = _with_portrait(tmp_path)
    rule = _rule(html, ".portrait-img")
    starts = [int(x) for x in re.findall(r"#000 (\d+)%, transparent 100%", rule)]
    assert starts and min(starts) >= 100 - round(tokens.PORTRAIT_FADE * 100) - 1, rule


# п.3 и п.4 — §18: заголовок 4–6 строк, не вплотную к верху, панели нет

HER_COVER_HOOK = (
    "7 признаков,\nчто тебе нужна\nне новая\nнейросеть,\nа нормальный\nпроцесс"
)


def _cover(tmp_path, **kw):
    return templates.build_carousel_slide(
        hook=HER_COVER_HOOK,
        accent_word=["нормальный", "процесс"],
        photo=_carry_portrait(tmp_path),
        handwritten="не про инструменты",
        index=1, total=9, style="STYLE_01", role="cover", notes=[],
        **kw,
    )


def test_the_cover_headline_stays_within_her_four_to_six_lines(tmp_path):
    html = _cover(tmp_path, header=False)
    lines = _measure(
        html, tmp_path, "cover-lines",
        "() => {const hero = document.querySelector('.hero');"
        "const lh = parseFloat(getComputedStyle(hero).lineHeight);"
        "return [...hero.querySelectorAll('.hero-line')]"
        ".reduce((n, el) => n + Math.round(el.getBoundingClientRect().height / lh), 0);}",
    )
    lo, hi = tokens.COVER_HEADLINE_LINES
    assert lo <= lines <= hi, f"обложка встала в {lines} строк"


def test_the_cover_headline_does_not_touch_the_top_line(tmp_path):
    html = _cover(tmp_path, header=False)
    h = tokens.CANVAS["carousel"][1]
    top = _measure(
        html, tmp_path, "cover-top",
        "() => document.querySelector('.hero').getBoundingClientRect().top",
    )
    assert top >= tokens.CAROUSEL_MARGIN["top"] + round(h * 0.05), f"заголовок в {top}px"


def test_the_cover_may_go_without_the_top_panel():
    # §18 «Минимум мелкого текста»; на внутренних слайдах панель остаётся
    bare = templates.build_carousel_slide(hook="Обложка", header=False, index=1, total=9)
    assert 'class="header"' not in bare
    inner = templates.build_carousel_slide(
        hook="Признак", label="Признак 1", index=2, total=9
    )
    assert 'class="header"' in inner and "признак 1" in inner.lower()


# п.5 — блок цепочки не рвёт слово пополам

def test_a_long_word_in_a_chain_block_is_never_broken_in_half(tmp_path):
    html = templates.build_carousel_slide(
        hook="5. На контент всё равно\nуходит слишком много\nвремени",
        flow=[{"title": t} for t in HER_FLOW],
        index=6, total=9, style="STYLE_01", role="slide",
    )
    rows = _measure(
        html, tmp_path, "flow-titles",
        "() => [...document.querySelectorAll('.flow-title')].map(el => {"
        "const lh = parseFloat(getComputedStyle(el).lineHeight);"
        "return [el.textContent, Math.round(el.getBoundingClientRect().height / lh),"
        " el.scrollWidth <= el.clientWidth];})",
    )
    for text, count, fits in rows:
        assert count == 1, f"«{text}» разорвано на {count} строки"
        assert fits, f"«{text}» не поместилось в блок"


# п.6 — в цепочке из пяти блоков пять разных иконок

def test_five_blocks_of_her_chain_get_five_different_icons():
    html = templates.build_carousel_slide(
        hook="5. На контент",
        flow=[{"title": t} for t in HER_FLOW],
        style="STYLE_01",
    )
    drawn = [p for p in templates.ICONS.values() if p in html]
    assert len(drawn) == len(HER_FLOW), f"разных иконок {len(drawn)} на {len(HER_FLOW)}"
    picked = templates.pick_icons(HER_FLOW)
    assert picked == list(dict.fromkeys(picked))


# п.7 — вертикальная цепочка со стрелками

def test_the_final_slide_is_built_as_a_vertical_chain_with_arrows(tmp_path):
    html = _with_portrait(tmp_path)
    assert 'class="chain"' in html
    assert html.count('class="chain-arrow"') == len(HER_CHAIN) - 1
    assert "flex-direction: column" in _rule(html, ".chain")
    tops = _measure(
        html, tmp_path, "chain",
        "() => [...document.querySelectorAll('.chain-item')]"
        ".map(el => el.getBoundingClientRect().top)",
    )
    assert tops == sorted(tops) and len(set(tops)) == len(HER_CHAIN), tops


# п.8 — плашка-вывод умеет оранжевую обводку (§13 + §8 TYPE D)

def test_the_conclusion_plate_can_take_her_orange_outline():
    plain = templates.build_carousel_slide(hook="X", summary="Раз.\nДва.")
    assert 'class="summary"' in plain
    loud = templates.build_carousel_slide(
        hook="X", summary="Раз.\nДва.", summary_accent=True
    )
    assert 'class="summary accent"' in loud
    assert tokens.ACCENT["ORANGE_ACCENT"] in _rule(loud, ".summary.accent")


# п.9 — слайд 03 получает объект: корпус телефона с сеткой плиток приложений

def test_the_phone_carries_a_grid_of_app_tiles_and_not_a_screenshot():
    html = templates.build_carousel_slide(
        hook="2. Для одной задачи\nу тебя уже несколько\nприложений",
        body="Одно пишет.\nВторое оформляет.",
        apps=tokens.APP_GRID_TILES,
        index=3, total=9, style="STYLE_01", role="slide",
    )
    assert 'data-composition="B"' in html          # §8 TYPE B, не типографика 04
    assert 'class="device phone"' in html
    assert html.count('class="app-tile"') == tokens.APP_GRID_TILES
    assert "<img" not in html                      # ни скриншота, ни картинки
    drawn = {p for p in templates.ICONS.values() if p in html}
    assert len(drawn) >= 8, f"плитки собрались из {len(drawn)} иконок"


# --- Таск 12: навык знает всё, что умеет вёрстка -----------------------------
# Ожидаемое — из таска 12: п.3 (поля слайда ровно по коду), п.1 (её порядок
# работы дословно), п.4 (ссылка на её дизайн-систему), п.2 (точка входа).

import inspect

#: Поля, которые ставит сборка, а не данные слайда.
BUILD_OWNED = {"index", "total", "notes"}


def _skill_field_table():
    text = SKILL.read_text(encoding="utf-8")
    section = text.split("## Поля слайда", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `(\w+)`", section, flags=re.M))


def test_skill_lists_exactly_the_fields_build_carousel_slide_takes():
    accepted = set(inspect.signature(templates.build_carousel_slide).parameters) - BUILD_OWNED
    listed = _skill_field_table()
    assert accepted - listed == set(), "навык молчит о полях"
    assert listed - accepted == set(), "навык называет полей, которых нет"


def test_skill_carries_her_order_of_work_word_for_word():
    text = SKILL.read_text(encoding="utf-8")
    for step in (
        "1. проанализируй смысл;",
        "2. разбей материал на слайды;",
        "3. придумай отдельную визуальную метафору для каждого слайда;",
        "4. составь storyboard;",
        "5. проверь, чтобы композиции и визуальные объекты не повторялись.",
    ):
        assert step in text, step
    assert "какой кадр или объект лучше всего показывает эту мысль без текста?" in text
    assert "essa-ai/content/2026-09-23-7-priznakov/storyboard.md" in text
    assert "-m integrations.visuals.build" in text

def test_build_entry_point_assembles_a_kit_from_slides_json(tmp_path, monkeypatch):
    import json

    from integrations.visuals import build

    def snapped(html_path, out_png, width, height):   # движок снимка есть и снял
        return render.RenderResult(ok=True, html_path=html_path, png_path=out_png,
                                   width=width, height=height, engine="fake")

    monkeypatch.setattr(render, "render_image", snapped)
    kit_dir = tmp_path / "2026-09-24-test"
    (kit_dir / "assets").mkdir(parents=True)
    (kit_dir / "assets" / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (kit_dir / "slides.json").write_text(json.dumps({"slides": [
        {"hook": "Первый\nслайд", "accent_word": "слайд", "header": False},
        {"hook": "Второй", "label": "Признак 1", "body": "Раз · два · три",
         "screens": ["assets/shot.png"]},
    ]}, ensure_ascii=False), encoding="utf-8")

    assert build.main([str(kit_dir)]) == 0

    visuals = kit_dir / "visuals"
    htmls = sorted(p.name for p in visuals.glob("carousel-*.html"))
    assert htmls == ["carousel-01.html", "carousel-02.html"]
    second = (visuals / "carousel-02.html").read_text(encoding="utf-8")
    assert "Второй" in second and "shot.png" in second
    assert (visuals / "shot.png").is_file()   # путь от папки slides.json, файл рядом с вёрсткой

def test_build_entry_point_fails_loudly_when_png_was_not_taken(tmp_path, monkeypatch, capsys):
    import json

    from integrations.visuals import build

    monkeypatch.setattr(render, "_playwright_module", lambda: None)   # движка снимка нет
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    (kit_dir / "slides.json").write_text(json.dumps({"slides": [
        {"hook": "Первый"}, {"hook": "Второй"},
    ]}, ensure_ascii=False), encoding="utf-8")

    code = build.main([str(kit_dir)])

    assert code not in (0, 2)
    assert code == build.EXIT_NOT_RENDERED
    out = capsys.readouterr().out
    assert "carousel-01.png" in out and "carousel-02.png" in out
    assert "не снят" in out

def test_build_exits_zero_when_its_output_goes_to_a_pipe(tmp_path):
    """JARVIS запускает сборку с перехваченным выводом: консоль Windows в cp1251
    не должна ронять уже собранный комплект."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    (kit_dir / "slides.json").write_text(json.dumps({"slides": [
        {"hook": "Первый", "header": False, "handwritten": "инструменты ≠ система"},
    ]}, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "cp1251", "PYTHONUTF8": "0"}

    proc = subprocess.run(
        [sys.executable, "-m", "integrations.visuals.build", str(kit_dir)],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
    )

    assert proc.returncode in (0, 3), proc.stderr.decode("utf-8", "replace")[-500:]
    assert b"carousel-01.png" in proc.stdout


# --- таск 13: фон по её слову и все три вида одной командой -----------------


def _fake_snap(monkeypatch):
    def snapped(html_path, out_png, width, height):
        return render.RenderResult(ok=True, html_path=html_path, png_path=out_png,
                                   width=width, height=height, engine="fake")
    monkeypatch.setattr(render, "render_image", snapped)


def _backgrounds(kit_dir):
    return [
        re.search(r"\.canvas#slide \{[^}]*?linear-gradient\(152deg, (#[0-9A-Fa-f]{6})",
                  p.read_text(encoding="utf-8")).group(1)
        for p in sorted((kit_dir / "visuals").glob("carousel-*.html"))
    ]


@pytest.mark.parametrize("mode", [None, "dark", "alternate"])
def test_background_follows_her_word_and_is_dark_without_it(mode, tmp_path, monkeypatch):
    # Её ответ: «если попрошу чередовать, то делаем светлую темную, если попрошу
    # в темной значитт все темное». Поля нет — тёмный: все её эталоны тёмные.
    import json

    from integrations.visuals import build

    _fake_snap(monkeypatch)
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    data = {"slides": [{"hook": f"Слайд {i}"} for i in range(1, 5)]}
    if mode:
        data["background"] = mode
    (kit_dir / "slides.json").write_text(json.dumps(data, ensure_ascii=False),
                                         encoding="utf-8")

    assert build.main([str(kit_dir)]) == 0

    backs = _backgrounds(kit_dir)
    light = tokens.PALETTE["BG_LIGHT_PRIMARY"]
    if mode == "alternate":
        assert backs[1] == light and backs[0] != light
    else:
        assert light not in backs


def test_unknown_background_word_is_a_data_error(tmp_path, capsys):
    import json

    from integrations.visuals import build

    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    (kit_dir / "slides.json").write_text(json.dumps(
        {"slides": [{"hook": "Раз"}], "background": "pink"}), encoding="utf-8")
    assert build.main([str(kit_dir)]) == 2


def test_one_command_builds_carousel_cover_and_story(tmp_path, monkeypatch):
    import json

    from integrations.visuals import build

    _fake_snap(monkeypatch)
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    (kit_dir / "slides.json").write_text(json.dumps({
        "slides": [{"hook": "Первый"}, {"hook": "Второй"}],
        "cover": {"hook": "Обложка\nпоста", "subtitle": "подзаголовок"},
        "story": {"key_phrase": "Фраза сторис", "caption": "подпись"},
    }, ensure_ascii=False), encoding="utf-8")

    assert build.main([str(kit_dir)]) == 0

    visuals = kit_dir / "visuals"
    for name in ("carousel-01", "carousel-02", "cover", "story"):
        assert (visuals / f"{name}.html").is_file(), name
    assert "Фраза сторис" in (visuals / "story.html").read_text(encoding="utf-8")
    assert "Обложка" in (visuals / "cover.html").read_text(encoding="utf-8")


# --- таск 13: пометки и их стрелки — внутри её полей §1 ----------------------
#: Её §1: слева и справа 55–70, сверху 45–60, снизу 60–80. Берём нижние границы.
SECTION_1_MIN = {"left": 55, "right": 55, "top": 45, "bottom": 60}

_HAND_BOXES_JS = """() => [...document.querySelectorAll('.hand-note, .hand-arrow')]
  .map(e => { const b = e.getBoundingClientRect();
    return {cls: e.getAttribute('class'), left: b.left, right: b.right,
            top: b.top, bottom: b.bottom}; })"""


def _in_browser(html, tmp_path, name, js):
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
        out = page.evaluate(js)
        browser.close()
    return out


def _outside_margins(boxes):
    w, h = tokens.CANVAS["carousel"]
    m = SECTION_1_MIN
    return [
        b["cls"] for b in boxes
        if b["left"] < m["left"] or b["right"] > w - m["right"]
        or b["top"] < m["top"] or b["bottom"] > h - m["bottom"]
    ]


@pytest.mark.parametrize("slot", ["top-right", "bottom-left", "mid-right", "top-left"])
def test_handwritten_note_and_its_arrow_stay_inside_her_margins(slot, tmp_path):
    html = templates.build_carousel_slide(
        hook="Заголовок\nв две строки", body="Текст слайда.", label="Признак 4",
        index=5, total=9, style="STYLE_01",
        handwritten={"text": "ещё один сервис?", "at": slot},
    )
    boxes = _in_browser(html, tmp_path, slot, _HAND_BOXES_JS)
    assert len(boxes) == 2
    assert _outside_margins(boxes) == []


# --- таск 13: её §8 TYPE D — UI-хаос, нарисованный вёрсткой ------------------
#: Её слова со слайда 02 «7 признаков»: «Промты. Гайды. Подборки сервисов.
#: Полезные Reels.» — подписи карточек берутся из данных слайда, не из скринов.
SAVED = ["Промты", "Гайды", "Подборки сервисов", "Полезные Reels"]

_CHAOS_JS = """() => [...document.querySelectorAll('.ui-card')].map(e => {
  const b = e.getBoundingClientRect(); const cs = getComputedStyle(e);
  return {top: b.top, bottom: b.bottom, left: b.left, right: b.right,
          z: +cs.zIndex, filter: cs.filter, border: cs.borderTopColor,
          active: e.classList.contains('active'), text: e.innerText.trim()}; })"""


def test_type_d_draws_ui_cards_from_the_slide_words(tmp_path):
    html = templates.build_carousel_slide(
        hook="1. У тебя куча\nсохранённого", body="Текст слайда.", label="Признак 1",
        index=2, total=9, style="STYLE_01", ui_cards=SAVED,
    )
    assert 'data-composition="D"' in html
    chaos = html[html.index('class="ui-chaos'):]
    assert "<img" not in chaos.split("</section>")[0]      # не скриншоты
    cards = _in_browser(html, tmp_path, "chaos", _CHAOS_JS)
    assert sorted(c["text"] for c in cards) == sorted(SAVED)
    active = [c for c in cards if c["active"]]
    assert len(active) == 1
    assert active[0]["border"] == "rgb(255, 149, 94)"      # её оранжевый #FF955E
    # разные уровни глубины: активная сверху, дальние — темнее и размыты
    assert active[0]["z"] == max(c["z"] for c in cards)
    far = [c for c in cards if not c["active"]]
    assert all("brightness" in c["filter"] and "blur" in c["filter"] for c in far)
    # частично перекрываются: соседние по вертикали карточки заходят друг на друга
    by_top = sorted(cards, key=lambda c: c["top"])
    assert all(a["bottom"] > b["top"] for a, b in zip(by_top, by_top[1:]))
    # на разных уровнях: карточки не стоят в одну колонку
    assert len({round(c["left"]) for c in cards}) >= 3


# --- таск 13: «7 признаков» целиком — воздух и поля на всех девяти ----------
PRIZNAKOV = Path(__file__).resolve().parents[1] / "essa-ai" / "content" / "2026-09-23-7-priznakov"

#: Пустота — строки холста между шапкой и нижним полем, где не стоит ничего
#: (заголовок меряется по строкам, а не по зарезервированной полосе), плюс
#: зазор между строками заголовка и тем, что идёт под ним в колонке.
_KIT_EMPTY_JS = """([mb, mt]) => {
  const r = e => e.getBoundingClientRect();
  const H = document.querySelector('#slide').getBoundingClientRect().height;
  const head = document.querySelector('.header');
  const start = head ? r(head).bottom : mt, end = H - mb;
  const sel = '.hero-line, .lead, .rule-accent, .stage > *, .summary, .hand-note,'
            + ' .device-body, .ui-card, .screen-card, .portrait-img';
  const iv = [...document.querySelectorAll(sel)].map(r)
    .filter(b => b.height > 0).map(b => [Math.max(b.top, start), Math.min(b.bottom, end)])
    .filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  let covered = 0, cur = null;
  for (const [a, b] of iv) {
    if (!cur || a > cur[1]) { if (cur) covered += cur[1] - cur[0]; cur = [a, b]; }
    else cur[1] = Math.max(cur[1], b);
  }
  if (cur) covered += cur[1] - cur[0];
  const lines = [...document.querySelectorAll('.hero-line')];
  const heroBottom = Math.max(...lines.map(x => r(x).bottom));
  const next = [...document.querySelectorAll('.lead, .stage, .summary')]
    .map(r).filter(b => b.height > 0 && b.top >= heroBottom - 1).map(b => b.top);
  const heroGap = next.length ? Math.min(...next) - heroBottom : 0;
  return {uncovered: (end - start) - covered, heroGap: heroGap};
}"""


@pytest.fixture(scope="module")
def priznakov_pages(tmp_path_factory, request):
    from integrations.visuals import build

    mp = pytest.MonkeyPatch()
    mp.setattr(render, "render_image", lambda html_path, out_png, width, height:
               render.RenderResult(ok=True, html_path=html_path, png_path=out_png,
                                   width=width, height=height, engine="fake"))
    out = tmp_path_factory.mktemp("priznakov")
    items = build.build(out, PRIZNAKOV / "slides.json")
    mp.undo()
    return {i.html_path.stem: (i.html_path.read_text(encoding="utf-8"), i.html_path.parent)
            for i in items if i.kind == "carousel"}


def test_priznakov_is_all_dark_and_has_four_kinds_with_02_and_05_as_type_d(priznakov_pages):
    pages = [priznakov_pages[f"carousel-{i:02d}"][0] for i in range(1, 10)]
    kinds = [re.search(r'data-composition="(\w)"', p).group(1) for p in pages]
    assert len(set(kinds)) >= 4, kinds
    assert kinds[1] == "D" and kinds[4] == "D", kinds
    assert all(tokens.PALETTE["BG_LIGHT_PRIMARY"] not in p.split("</style>")[0]
               .split(".canvas#slide")[1].split("}")[0] for p in pages)
    assert "<img" not in pages[1].split('class="ui-chaos')[1].split("</section>")[0]


@pytest.mark.parametrize("n", range(1, 10))
def test_priznakov_slide_has_no_air_and_notes_inside_margins(n, priznakov_pages, tmp_path):
    name = f"carousel-{n:02d}"
    html, visuals = priznakov_pages[name]   # меряем рядом с её файлами — скрины грузятся
    tmp_path = visuals
    m = tokens.CAROUSEL_MARGIN
    _, h = tokens.CANVAS["carousel"]
    assert _outside_margins(_in_browser(html, tmp_path, name, _HAND_BOXES_JS)) == []
    js = f"() => ({_KIT_EMPTY_JS})([{m['bottom']}, {m['top']}])"
    got = _in_browser(html, tmp_path, name + "-air", js)
    empty = got["uncovered"] + got["heroGap"]
    assert empty <= MAX_EMPTY_SHARE * h, f"{name}: пустоты {got} из {h}"
