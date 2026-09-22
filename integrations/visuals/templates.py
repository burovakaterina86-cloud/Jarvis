"""Вёрстка трёх видов картинок ESSA.AI.

Структура и классы взяты из её собственной вёрстки
`essa-ai/visual_references/design-code-studio_essa_ai-v1.html`
(там превью в масштабе 320×400; здесь тот же язык на экспортном холсте).

Источники правил — по видам:
- карусель: `essa-ai/SKILL_carousel-instagram.md` §5–§12 + `DESIGN.md` §10–§11;
- обложка поста: `essa-ai/POST_COVERS.md` §17 +
  `visual_references/обложки на посты/SKILL_cover-post-katerina_SHORT.md`;
- фон сторис: `DESIGN.md` §18 «REELS — VISUAL SYSTEM».

Ни одного значения не придумано: всё, что попадает в CSS, приходит из `tokens`.
"""
import re
from html import escape
from pathlib import Path

from . import tokens

P = tokens.PALETTE

#: Оранжевый акцент второго эталона (reference/5..9.webp), DESIGN.md §3 от
#: 2026-09-22. Им красятся: ключевое слово заголовка, отбивка под текстовой
#: колонкой, обводка акцентной плашки, отрезки цепочки и рукописные пометки.
O = tokens.ACCENT["ORANGE_ACCENT"]

#: Куда ложатся рукописные пометки. Порядок — как в её слайдах: первая сверху
#: справа от заголовка, вторая снизу слева под текстом, третья — правее середины.
HAND_SLOTS = ("top-right", "bottom-left", "mid-right", "top-left")

#: Служебные пометки функции слайда (07_CONTENT_RULES §5–§6 и §13 её адаптера).
#: В кадр не попадают никогда: в первом рендере в плашку-рубрику утекло
#: слово «внимание» — это была внутренняя пометка, а не рубрика владелицы.
SERVICE_MARKS = frozenset(
    {
        "внимание", "узнавание", "проблема", "расширение проблемы", "конфликт",
        "слом", "слом шаблона", "новое убеждение", "новая парадигма", "механизм",
        "механизм / proof", "примеры", "фреймворк", "вывод", "инсайт",
        "бренд + cta", "бренд", "cta",
        "attention", "identification", "problem", "problem expansion", "conflict",
        "pattern interrupt", "new belief", "new paradigm", "examples", "framework",
        "insight", "mechanism", "mechanism / proof", "proof", "brand idea",
        "brand anchoring + cta", "hook",
    }
)

#: Иконки — простые геометрические line-icons (DESIGN.md §15), inline SVG.
#: Внешних картиночных файлов и иконочных шрифтов нет.
ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M9 12h6M9 16h6"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="M10 8l6 4-6 4z"/>',
    # Шестерёнка: обод, втулка и восемь зубцов. Без обода спицы из центра
    # читались как солнце, а не как шестерня её эталона.
    "gear": '<circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="6.4"/>'
            '<path d="M12 2.4v2.4M12 19.2v2.4M2.4 12h2.4M19.2 12h2.4'
            'M5.2 5.2l1.7 1.7M17.1 17.1l1.7 1.7M18.8 5.2l-1.7 1.7M6.9 17.1l-1.7 1.7"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    "spark": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
    # Песочные часы: две воронки, сходящиеся перемычкой в середине сетки.
    # Прежний путь рисовал две несвязанные дуги — в кадре это выглядело
    # как два обломка (её рендер carousel-04).
    "hourglass": '<path d="M7 3 L17 3 M7 21 L17 21"/>'
                 '<path d="M8.5 3 L8.5 6 L12 12 L15.5 6 L15.5 3"/>'
                 '<path d="M8.5 21 L8.5 18 L12 12 L15.5 18 L15.5 21"/>',
    "bolt": '<path d="M13 2L5 13h6l-1 9 8-11h-6z"/>',
    "image": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/>'
             '<path d="M4 18l5-5 4 4 3-3 4 4"/>',
    "chart": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "question": '<circle cx="12" cy="12" r="9"/><path d="M9 9.5a3 3 0 1 1 3 3V14"/>'
                '<path d="M12 17.5h.01"/>',
    "flask": '<path d="M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M9 3h6"/>',
    "map": '<path d="M9 4L3 7v13l6-3 6 3 6-3V4l-6 3z"/><path d="M9 4v13M15 7v13"/>',
    "dot": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/>',
}

#: Иконка шага по умолчанию: в её эталоне под каждым кружком иконка есть
#: всегда. Имя не дали и по подписи ничего не узналось — ставим нейтральный
#: геометрический маркер (DESIGN.md §15), а не пустое место.
DEFAULT_STEP_ICON = "dot"

#: Подбор иконки по смыслу подписи, когда имя не задано (G16).
#: Раньше во всём ряду стоял один и тот же кружок `dot` — ряд выходил
#: одинаковым (её рендер carousel-07). Словарь ведёт только к уже имеющимся
#: иконкам `ICONS`: ничего нового не рисуется и не выдумывается.
#: Порядок важен — первое совпадение выигрывает, поэтому узкие темы стоят
#: раньше широких.
ICON_HINTS = (
    ("play", ("монтаж", "видео", "рилс", "reels", "ролик", "съёмк", "съемк")),
    ("image", ("дизайн", "обложк", "визуал", "фото", "картинк", "изображ", "баннер")),
    ("doc", ("текст", "пост", "копирайт", "сценар", "промт", "гайд", "докумен",
             "файл", "стать", "подпис", "письм", "конспект")),
    ("check", ("провер", "контрол", "результат", "готов", "качеств", "сама")),
    ("clock", ("врем", "час", "минут", "срок", "сколько", "долго", "быстре")),
    ("hourglass", ("ждать", "ожидан", "дедлайн", "откладыва", "потом")),
    ("search", ("поиск", "ищеш", "иска", "найд", "выбер", "выбор", "разбер")),
    ("gear", ("процесс", "систем", "настрой", "автоматиз", "инструмент",
              "механизм", "шаблон", "повторя")),
    ("chart", ("цифр", "статист", "аналит", "охват", "рост", "метрик", "smm",
               "соцсет", "блог", "аккаунт", "отчёт", "отчет")),
    ("flask", ("тест", "эксперимент", "пробу", "гипотез")),
    ("bolt", ("энерг", "сразу", "мгновен", "разгон", "ускор")),
    ("map", ("задач", "план", "шаг", "маршрут", "воронк", "путь", "карт")),
    ("question", ("вопрос", "зачем", "почему", "что-нибудь", "непонят")),
    ("spark", ("нейросет", "нейронк", "ai", "идея", "идеи", "мастерск", "новое")),
)


def pick_icon(caption: str) -> str:
    """Имя иконки по смыслу подписи — только из её же словаря `ICONS`.

    Ничего не подошло — нейтральный маркер: это честнее, чем подставить
    иконку про другое.
    """
    text = str(caption or "").casefold().replace("ё", "е")
    for name, keys in ICON_HINTS:
        for key in keys:
            if key.replace("ё", "е") in text:
                return name
    return DEFAULT_STEP_ICON


#: Стрелка между карточками — её знак из эталонных слайдов. Служит и
#: разделителем в тексте слайда (`auto_blocks`).
ARROW = "→"

#: Нарисованная стрелка между карточками потока (G17): не тонкая палочка и не
#: типографский знак, а заметная дуга с открытым наконечником — как оранжевые
#: дуги в `reference/8.webp`.
FLOW_ARROW = (
    '<svg class="flow-arrow-svg" viewBox="0 0 48 34" fill="none" stroke="currentColor" '
    'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 28C13 8 31 5 43 19"/>'
    '<path d="M31 15L43 19L41 6"/></svg>'
)

#: Рисованная стрелка от рукописной пометки к тому, что она комментирует
#: (её слайды 5..9): изогнутая дуга и открытый наконечник, inline SVG.
HAND_ARROW = (
    '<svg class="hand-arrow" viewBox="0 0 64 86" fill="none" stroke="currentColor" '
    'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M54 6C28 16 10 36 14 68"/>'
    '<path d="M5 55l9 15 15-8"/></svg>'
)

#: Средняя ширина знака Roboto Condensed Bold в верхнем регистре, в долях кегля.
#: Замерена в браузере: «ВОЗВРАЩЁННОЕ» — 190.4 px при 27 px на 12 знаков.
#: По ней считается кегль подписи потока, чтобы длинное слово вставало в строку.
CONDENSED_CAPS_ADVANCE = 0.59

#: Нижняя граница этого кегля: мельче подпись на карточке уже не читается.
MIN_FLOW_TITLE = 18

#: Ник в шапке слайда — из её вёрстки.
NICKNAME = "@studio_essa_ai"

#: Фирменные элементы обложки — из SKILL_cover-post-katerina_SHORT.md.
COVER_PILL = "МОЙ ПОДХОД"
COVER_MICROTEXT = "ТЕСТИРУЮ / АНАЛИЗИРУЮ / УЛУЧШАЮ"

#: Оформление разрешённых стилей карусели.
#: Ключи — только из `tokens.STYLES`; цвета — только из `tokens.PALETTE`.
STYLE_SURFACES = {
    # §7: dark graphite, white, violet/lavender accents.
    "STYLE_01": {
        "bg": P["BG_DARK_PRIMARY"],
        "surface": P["BG_DARK_SECONDARY"],
        "text": P["TEXT_ON_DARK"],
        "muted": P["TEXT_MUTED_DARK"],
        "accent": P["VIOLET_PRIMARY"],
        "accent_soft": P["VIOLET_SOFT"],
    },
    # §8: light / lavender base, graphite text, violet accents.
    "STYLE_02_LIGHT": {
        "bg": P["BG_LIGHT_PRIMARY"],
        "surface": P["BG_LIGHT_SECONDARY"],
        "text": P["TEXT_ON_LIGHT"],
        "muted": P["TEXT_MUTED_LIGHT"],
        "accent": P["VIOLET_PRIMARY"],
        "accent_soft": P["VIOLET_STRONG"],
    },
    # §9: dark-variant того же editorial.
    "STYLE_02_DARK": {
        "bg": P["BG_DARK_SECONDARY"],
        "surface": P["BG_DARK_PRIMARY"],
        "text": P["TEXT_ON_DARK"],
        "muted": P["TEXT_MUTED_DARK"],
        "accent": P["VIOLET_PRIMARY"],
        "accent_soft": P["VIOLET_SOFT"],
    },
}


def _rgba(hex_color: str, alpha: float) -> str:
    """Полупрозрачный вариант её же цвета — новых цветов не появляется."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _glow(hex_color: str, alpha: float) -> str:
    """Локальное свечение (DESIGN.md §14): круг гаснет ровно на краю блока.

    `closest-side` обязателен: при размере по умолчанию круг не успевает стать
    прозрачным и в кадре видна прямоугольная граница блока.
    """
    return (
        f"radial-gradient(circle closest-side, {_rgba(hex_color, alpha)} 0%, transparent 100%)"
    )


def _t(value) -> str:
    return escape(str(value), quote=True)


def _scale(name: str) -> tuple:
    s = tokens.TYPE_SCALE[name]
    return s["size"], s["line_height"]


def _document(title: str, width: int, height: int, css: str, body: str) -> str:
    """Страница-холст: ровно один кадр нужного размера, без полей и прокрутки."""
    head = tokens.FONTS["HEADLINE"]
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{_t(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{tokens.GOOGLE_FONTS_URL}" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: {P["BG_DARK_PRIMARY"]}; }}
  body {{ font-family: {tokens.font_stack("BODY")}; -webkit-font-smoothing: antialiased; }}
  .canvas {{
    width: {width}px; height: {height}px;
    position: relative; overflow: hidden;
    display: flex; flex-direction: column;
    padding: {tokens.SAFE_ZONE}px;
  }}
  .headline {{ font-family: '{head}', {tokens.FALLBACK_STACK};
               font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]}; }}
{css}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _lines(text: str, limit: int = 0) -> list:
    """Строки как их разбила владелица: по переводу строки."""
    out = [line.strip() for line in str(text).split("\n") if line.strip()]
    return out[:limit] if limit else out


def _quotes(text: str) -> str:
    """Прямые кавычки → типографские лапки, как в её слайдах («ЧТО БЫ ЕЩЁ…»)."""
    out, opened = [], False
    for ch in text:
        if ch == '"':
            out.append("“" if not opened else "”")
            opened = not opened
        else:
            out.append(ch)
    return "".join(out)


def _rubric(label: str) -> str:
    """Рубрика шапки — только слово владелицы.

    Служебная пометка функции слайда в кадр не попадает: рубрики просто нет.
    """
    clean = str(label or "").strip()
    return "" if clean.casefold() in SERVICE_MARKS else clean


def _icon(name: str, size: int, stroke: str) -> str:
    """Иконка — inline SVG из `ICONS`. Незнакомое имя — иконки нет."""
    path = ICONS.get(str(name or "").strip())
    if not path:
        return ""
    return (
        f'<svg class="icon" viewBox="0 0 24 24" width="{size}" height="{size}" '
        f'fill="none" stroke="{stroke}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


def _image_block(kind: str, path, caption: str, notes: list) -> str:
    """Картинка владелицы: её файл или честная строка о том, что файла нет.

    Заглушку не рисуем и чужого не подставляем (таск 05, пп. 5 и 7).
    """
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        notes.append(f"{kind}: файла нет — {p}; слайд собран без него")
        return f"<!-- {kind}: файла нет — {_t(p)} -->"
    notes.append(f"{kind}: {p.name}")
    alt = _t(caption or p.name)
    return f'<img class="{kind}-img" src="{_t(p.name)}" alt="{alt}">'


def _mark_accent(line: str, words) -> str:
    """Ключевое слово заголовка — оранжевым (G11, её слайды 5..9).

    Красится ровно слово из данных слайда, а не строка целиком и не догадка:
    не нашли слова в строке — строка остаётся белой.
    """
    out = _t(line)
    for word in words:
        w = str(word or "").strip()
        if not w:
            continue
        idx = line.casefold().find(w.casefold())
        if idx < 0:
            continue
        before, mid, after = line[:idx], line[idx:idx + len(w)], line[idx + len(w):]
        out = f'{_t(before)}<span class="accent">{_t(mid)}</span>{_t(after)}'
        break
    return out


def _hand_html(handwritten) -> str:
    """Рукописные пометки: две-три на слайд, оранжевые, со стрелкой к тому,
    что комментируют (её слова 2026-09-22 и слайды 5..9).

    Текст приходит данными: строка — одна пометка, список — несколько.
    Место можно задать явно (`{"text": …, "at": "bottom-left"}`), не задали —
    слоты раздаются по порядку её слайдов.
    """
    if not handwritten:
        return ""
    items = [handwritten] if isinstance(handwritten, (str, dict)) else list(handwritten)
    parts = []
    for i, item in enumerate(items):
        data = item if isinstance(item, dict) else {"text": item}
        text = str(data.get("text", "")).strip()
        if not text:
            continue
        slot = data.get("at") or HAND_SLOTS[i % len(HAND_SLOTS)]
        parts.append(
            f'<div class="hand-note at-{_t(slot)}">'
            f'<span class="hand-text">{_t(text)}</span>'
            f'{HAND_ARROW}</div>'
        )
    return "".join(parts)


def _steps_html(steps: list, icon_size: int, stroke: str) -> str:
    """Цепочка шагов: кружки с номерами, иконка, подпись, пояснение.

    Соединение — короткие отрезки *между* кружками (G12). Сквозной линии нет:
    прежняя проходила сквозь цифры и читалась как перечёркивание.
    """
    cells = []
    for i, step in enumerate(steps, start=1):
        if i > 1:
            cells.append('<div class="step-link"></div>')
        icon = _icon(step.get("icon", ""), icon_size, stroke) or _icon(
            pick_icon(step.get("caption", "")), icon_size, stroke
        )
        note = step.get("note", "")
        cells.append(
            f'<div class="step">'
            f'<div class="step-dot headline">{_t(i)}</div>'
            f'<div class="step-icon">{icon}</div>'
            f'<div class="step-caption">{_t(step.get("caption", ""))}</div>'
            + (f'<div class="step-note">{_t(note)}</div>' if note else "")
            + "</div>"
        )
    return '<div class="steps"><div class="steps-row">' + "".join(cells) + "</div></div>"


def _flow_html(flow: list, icon_size: int, stroke: str, accent_stroke: str) -> str:
    """Поток карточек со стрелками; последняя залита акцентом."""
    parts = []
    last = len(flow) - 1
    for i, card in enumerate(flow):
        if i:
            parts.append(f'<div class="flow-arrow">{FLOW_ARROW}</div>')
        accent = " accent" if i == last and card.get("accent", True) else ""
        pen = accent_stroke if accent else stroke
        icon = _icon(card.get("icon", ""), icon_size, pen) or _icon(
            pick_icon(card.get("title", "")), icon_size, pen
        )
        note = card.get("note", "")
        parts.append(
            f'<div class="flow-card{accent}">{icon}'
            f'<div class="flow-title headline">{_t(card.get("title", ""))}</div>'
            + (f'<div class="flow-note">{_t(note)}</div>' if note else "")
            + "</div>"
        )
    return '<div class="flow">' + "".join(parts) + "</div>"


def _cards_html(cards: list, icon_size: int, stroke: str, accent_stroke: str) -> str:
    """Сетка карточек со скруглением.

    Под карточками нет пояснений — ряд становится компактным (`cards compact`):
    пустая коробка на треть холста была дефектом её рендера carousel-03,
    а не воздухом (G16).
    """
    columns = 2 if len(cards) <= 4 else 3
    dense = any(str(c.get("note", "")).strip() for c in cards)
    cells = []
    for card in cards:
        accent = " accent" if card.get("accent") else ""
        pen = accent_stroke if accent else stroke
        icon = _icon(card.get("icon", ""), icon_size, pen) or _icon(
            pick_icon(card.get("title", "")), icon_size, pen
        )
        note = card.get("note", "")
        cells.append(
            f'<div class="card{accent}">{icon}'
            f'<div class="card-title headline">{_t(card.get("title", ""))}</div>'
            + (f'<div class="card-note">{_t(note)}</div>' if note else "")
            + "</div>"
        )
    klass = "cards" if dense else "cards compact"
    return (
        f'<div class="{klass}" style="grid-template-columns: repeat({columns}, 1fr);">'
        + "".join(cells)
        + "</div>"
    )


#: Правая сцена из её скринов (G18, `reference/5.webp`): один-три снимка лежат
#: стопкой, каждый чуть повёрнут и сдвинут. Слоты заданы явно, чтобы стопка
#: была предсказуемой, а не случайной.
SCREEN_SLOTS = (
    {"top": "0%", "right": "6%", "rot": -7},
    {"top": "30%", "right": "18%", "rot": -4},
    {"top": "60%", "right": "6%", "rot": -9},
)


def _screens_html(screens, notes: list) -> str:
    """Карточки-скрины правой сцены: её файлы, ничего не подставляется.

    Смысл снимков не разбирается — это фактура. Снимок не увеличивается
    (`.screen-img` живёт в потолках `max-width`/`max-height`), чтобы мелкий
    текст на нём не становился читаемым крупно.
    """
    if not screens:
        return ""
    items = [screens] if isinstance(screens, (str, Path, dict)) else list(screens)
    cards = []
    for item in items[: len(SCREEN_SLOTS)]:
        data = item if isinstance(item, dict) else {"src": item}
        img = _image_block("screen", data.get("src"), "скрин владелицы", notes)
        if not img or img.startswith("<!--"):
            continue
        cards.append(f'<div class="screen-card s{len(cards) + 1}">{img}</div>')
    if not cards:
        return ""
    return (
        f'<div class="screens n{len(cards)}"><div class="screens-glow"></div>'
        + "".join(cards)
        + "</div>"
    )


def auto_blocks(text: str) -> dict:
    """Графика из данных слайда: её же разделители в тексте.

    `→` — поток карточек, `·` — сетка карточек, «1. … 2. …» — цепочка шагов.
    Ничего не придумывается: подписи берутся из текста слайда.
    """
    raw = str(text or "").strip()
    if not raw:
        return {}
    if ARROW in raw or "->" in raw:
        parts = [p.strip() for p in raw.replace("->", ARROW).split(ARROW) if p.strip()]
        if len(parts) >= 2:
            return {"flow": [{"title": p} for p in parts]}
    if "·" in raw:
        parts = [p.strip() for p in raw.split("·") if p.strip()]
        if len(parts) >= 2:
            return {"cards": [{"title": p} for p in parts]}
    numbered = re.findall(r"(?:^|\s)(\d)\.\s*([^\d]+?)(?=\s\d\.|$)", raw)
    if len(numbered) >= 2:
        return {"steps": [{"caption": t.strip(" ·.")} for _, t in numbered]}
    return {}


def build_carousel_slide(
    hook: str,
    body: str = "",
    label: str = "",
    index: int = 1,
    total: int = 1,
    style: str = tokens.DEFAULT_STYLE,
    role: str = "cover",
    accent_word="",
    thesis: str = "",
    footer_thesis: str = "",
    steps: list = None,
    flow: list = None,
    cards: list = None,
    summary: str = "",
    handwritten: str = "",
    photo=None,
    screenshot=None,
    screens=None,
    notes: list = None,
) -> str:
    """Слайд карусели 1080×1350 по её второму эталону (`reference/5–9.webp`).

    Зоны: шапка `NN / NN` + тонкая линия + короткая метка справа, заголовок с
    оранжевым ключевым словом, текстовая колонка, оранжевая отбивка, тело с
    графикой или предметной сценой справа, плашка-сноска, подвал.

    `accent_word` — слово (или список слов) заголовка, которое красится
    оранжевым; не задано — заголовок белый целиком. Догадок нет.
    `handwritten` — рукописные пометки: строка или список; каждая ложится со
    своей изогнутой стрелкой, на любом слайде, а не только на крайних.
    `summary` — плашка-сноска: первая строка белая, вторая сиреневая.
    `thesis` больше не рисуется: двухстрочный тезис в шапке она назвала
    хаотичным (2026-09-22), параметр остался только ради старых вызовов.
    `steps` / `flow` / `cards` — графические блоки; не переданы — собираются из
    текста слайда (`auto_blocks`). `photo` и `screenshot` — файлы владелицы:
    файла нет → слайд собирается без него, а в `notes` ложится строка об этом.
    `screens` — список её скринов (один-три) для правой сцены: они ложатся
    стопкой под наклоном, текст уходит в левую колонку. Пути приходят данными
    слайда, сами не подбираются.
    `style` — только из `tokens.STYLES` (§5).
    """
    if style not in tokens.STYLES:
        raise ValueError(
            f"стиль {style!r} не разрешён; допустимы {', '.join(tokens.STYLES)} "
            "(SKILL_carousel-instagram.md §5)"
        )
    s = STYLE_SURFACES[style]
    w, h = tokens.CANVAS["carousel"]
    if notes is None:
        notes = []
    hook_size, hook_lh = _scale("hook" if role == "cover" else "slide_title")
    body_size, body_lh = _scale("body")
    label_size, label_lh = _scale("label")
    micro_size, micro_lh = _scale("micro")
    # Кружки, иконки и подписи цепочки — в пропорциях её reference/1.webp:
    # кружок примерно вчетверо крупнее подписи, иконка вдвое.
    dot = round(label_size * 4)
    # G17: иконки крупнее, чем были (2.2 — они терялись в карточке) и с
    # собственной подсветкой (`.icon` ниже).
    icon_size = round(label_size * 3.0)
    gap = tokens.SAFE_ZONE // 2
    inner = w - 2 * tokens.SAFE_ZONE
    #: Скриншот владелицы занимает тело слайда, но не выдавливает плашку
    #: и подвал: потолок — половина холста.
    shot_max_h = round(h * 0.45)
    # Объём набирается слоями, как в её примерах (reference/2.webp, 3.webp):
    # светлая обводка по верхнему краю, тёмная по нижнему, мягкая тень под блоком.
    # G17: к трём слоям добавлены внутренняя подсветка сверху и короткая
    # контактная тень снизу — без них плашка читалась как плоский прямоугольник.
    depth = (
        f'inset 0 2px 0 {_rgba(s["text"], 0.16)}, '
        f'inset 0 -2px 0 {_rgba(P["BG_DARK_PRIMARY"], 0.55)}, '
        f'inset 0 20px 44px -20px {_rgba(s["text"], 0.16)}, '
        f'0 24px 48px {_rgba(P["BG_DARK_PRIMARY"], 0.55)}, '
        f'0 6px 14px {_rgba(P["BG_DARK_PRIMARY"], 0.45)}'
    )
    node_glow = f'0 0 64px {_rgba(s["accent"], 0.55)}'
    #: Собственная подсветка иконки (G17): она светится, а не лежит плашмя.
    icon_glow = f'drop-shadow(0 0 14px {_rgba(s["accent"], 0.55)})'

    if not (steps or flow or cards):
        derived = auto_blocks(body)
        steps = derived.get("steps")
        flow = derived.get("flow")
        cards = derived.get("cards")
        if derived:
            body = ""

    # Кегль подписи потока: чем больше карточек в ряду, тем уже карточка.
    # Самое длинное слово обязано встать в строку — иначе браузер ломает его
    # пополам («ВОЗВРАЩЁН/НОЕ» в её рендере carousel-04).
    flow_gap = 8
    #: Потолок ряда карточек — треть холста (её reference/3.webp).
    flow_cap = round(h / 3)
    flow_pad = gap // 2
    flow_title_size = label_size
    if flow:
        n = len(flow)
        card_w = (inner - 2 * flow_gap * (n - 1) - label_size * (n - 1)) / n
        # box-sizing: border-box — рамка съедает ширину наравне с полями
        content_w = card_w - 2 * flow_pad - 2 * tokens.BORDER_WIDTH
        longest = max(
            (len(word) for c in flow for word in str(c.get("title", "")).split()),
            default=1,
        )
        flow_title_size = max(
            MIN_FLOW_TITLE,
            min(label_size, int(content_w / (CONDENSED_CAPS_ADVANCE * longest))),
        )

    css = f"""
  .canvas {{ background: {s["bg"]}; color: {s["text"]}; }}
  .glow {{ position: absolute; border-radius: 50%; pointer-events: none;
           width: 900px; height: 900px; top: -300px; right: -260px;
           background: {_glow(s["accent"], 0.28)}; }}
  .glow-2 {{ position: absolute; border-radius: 50%; pointer-events: none;
             width: 760px; height: 760px; bottom: -320px; left: -280px;
             background: {_glow(P["LAVENDER"], 0.18)}; }}
  /* Шапка её второго эталона: `02 / 09`, тонкая линия через слайд, короткая
     метка справа. Двухстрочного тезиса тут больше нет — он был «хаотично». */
  .header {{ position: relative; z-index: 2; display: flex; align-items: center;
             gap: 28px; }}
  .header-count {{ font-size: {label_size}px; line-height: {label_lh};
                   letter-spacing: 0.04em; white-space: nowrap; }}
  .header-num {{ color: {O}; }}
  .header-total {{ color: {s["muted"]}; margin-left: 10px; }}
  .header-line {{ flex: 1; height: 1px; background: {_rgba(s["text"], 0.45)}; }}
  .header-label {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {micro_size}px;
                   line-height: {micro_lh}; letter-spacing: 0.18em; white-space: nowrap;
                   text-transform: uppercase; color: {s["muted"]}; }}
  .hero {{ position: relative; z-index: 2; margin-top: {gap}px; max-width: 78%;
           font-size: {hook_size}px; line-height: {hook_lh};
           letter-spacing: -0.01em; text-transform: uppercase; color: {s["text"]};
           margin-bottom: {gap // 2}px; }}
  .hero-line {{ display: block; }}
  .hero .accent, .hero em {{ font-style: normal; color: {O}; }}
  .lead {{ position: relative; z-index: 2; font-weight: {tokens.FONT_WEIGHTS["BODY"]};
           font-size: {body_size}px; line-height: {body_lh}; color: {s["text"]};
           margin-top: {gap // 2}px; max-width: {inner}px; }}
  /* Оранжевая отбивка под текстовой колонкой — держит низ колонки (её 5..9). */
  .rule-accent {{ position: relative; z-index: 2; width: 150px; height: 8px;
                  border-radius: 4px; background: {O}; margin-top: {gap // 2}px; }}
  /* Текст слева, предметная сцена справа — её раскладка со скриншотом. */
  .canvas.scene .hero, .canvas.scene .lead {{ max-width: 56%; }}
  .canvas.bottom-note {{ padding-bottom: {round(h * 0.19)}px; }}
  .stage {{ position: relative; z-index: 2; flex: 1; display: flex;
            flex-direction: column; justify-content: center; gap: {gap}px;
            margin-top: {gap // 2}px; padding-bottom: {gap // 2}px; }}
  /* Графики нет — вертикаль между заголовком и подвалом не оставляем дырой:
     заголовок сам занимает тело слайда. */
  .hero.fill {{ flex: 1; display: flex; flex-direction: column; justify-content: center; }}
  .steps {{ position: relative; flex: 1; display: flex;
            flex-direction: column; justify-content: center; }}
  /* Соединение цепочки — отрезки между кружками, а не черта сквозь цифры:
     сквозная линия читалась как перечёркивание (её замечание 2026-09-22). */
  .step-link {{ flex: 0 0 auto; width: 56px; height: 8px; border-radius: 4px;
                background: {O}; margin-top: {dot // 2 - 4}px; align-self: flex-start;
                box-shadow: 0 0 16px {_rgba(O, 0.55)}; }}
  .steps-row {{ position: relative; display: flex; justify-content: space-between;
                align-items: flex-start; gap: 16px; }}
  .step {{ flex: 1; text-align: center; }}
  .step-dot {{ width: {dot}px; height: {dot}px; border-radius: 50%;
               margin: 0 auto; background: {s["accent_soft"]}; color: {P["TEXT_ON_LIGHT"]};
               font-size: {label_size + 8}px; line-height: {dot}px;
               box-shadow: {node_glow}, inset 0 3px 0 {_rgba(P["TEXT_ON_DARK"], 0.55)},
                 inset 0 -4px 0 {_rgba(P["BG_DARK_PRIMARY"], 0.22)}; }}
  .step-icon {{ margin: 76px auto 26px; height: {icon_size}px; }}
  .step-caption {{ font-family: '{tokens.FONTS["HEADLINE"]}', {tokens.FALLBACK_STACK};
                   font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]};
                   font-size: {label_size + 8}px; line-height: 1.15; color: {s["text"]};
                   min-height: {round((label_size + 8) * 1.15 * 2)}px; }}
  .step-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 38px;
                color: {s["muted"]}; }}
  /* Тело слайда занимает вертикаль от подзаголовка до нижней плашки: ряд
     растёт, пока не упрётся в её пропорцию из reference/3.webp — карточка
     не выше трети холста. Дальше лишнее уходит в отступы вокруг ряда. */
  .flow {{ flex: 1; max-height: {flow_cap}px;
           display: flex; align-items: stretch; gap: {flow_gap}px; }}
  /* Карточка потока — в пропорции её reference/3.webp: около четверти холста
     по высоте. Это нижняя граница, а не растяжка: текст длиннее — карточка выше. */
  /* min-width: 0 — иначе длинное слово («ВОЗВРАЩЁННОЕ») не даёт карточке
     сузиться и ряд вылезает за правый край холста. */
  .flow-card {{ flex: 1 1 0; min-width: 0; overflow-wrap: break-word;
                display: flex; flex-direction: column; justify-content: center;
                border-radius: {tokens.RADIUS["card"]}px;
                background: {s["surface"]}; border: {tokens.BORDER_WIDTH}px solid
                {_rgba(s["accent"], 0.28)}; padding: {gap}px {flow_pad}px;
                box-shadow: {depth}; }}
  .flow-card.accent {{ background: {P["LAVENDER"]}; border-color: {O};
                       box-shadow: {node_glow}; }}
  .flow-card.accent .flow-title, .flow-card.accent .flow-note {{ color: {P["TEXT_ON_LIGHT"]}; }}
  /* Кегль подписи потока — базовый label: на четырёх карточках длинное слово
     («ВОЗВРАЩЁННОЕ») должно вставать в строку, а не ломаться переносом. */
  .flow-title {{ font-size: {flow_title_size}px; line-height: 1.15; margin-top: 18px;
                 text-transform: uppercase; color: {s["text"]}; }}
  .flow-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 14px;
                color: {s["muted"]}; }}
  /* G17: между карточками — рисованная дуга, а не типографская стрелка. */
  .flow-arrow {{ align-self: center; flex: 0 0 auto; color: {O};
                 width: {label_size * 2}px; height: {round(label_size * 1.4)}px; }}
  .flow-arrow-svg {{ width: 100%; height: 100%;
                     filter: drop-shadow(0 0 12px {_rgba(O, 0.45)}); }}
  .icon {{ filter: {icon_glow}; }}
  .cards {{ flex: 1; display: grid; gap: 16px; grid-auto-rows: 1fr; }}
  .card {{ border-radius: {tokens.RADIUS["card"]}px; background: {s["surface"]};
           border: {tokens.BORDER_WIDTH}px solid {_rgba(s["accent"], 0.28)};
           padding: {gap // 2}px; box-shadow: {depth};
           display: flex; flex-direction: column; justify-content: center; }}
  .card.accent {{ background: {P["LAVENDER"]}; border-color: {O};
                  box-shadow: {node_glow}; }}
  .card.accent .card-title, .card.accent .card-note {{ color: {P["TEXT_ON_LIGHT"]}; }}
  .card-title {{ font-size: {label_size + 3}px; line-height: 1.15; margin-top: 16px;
                 text-transform: uppercase; color: {s["text"]}; }}
  .card-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 10px;
                color: {s["muted"]}; }}
  /* G16: под карточками нет пояснений — ряд компактный, а не коробка на треть
     холста (её carousel-03: пять пустых плашек во весь экран). */
  .cards.compact {{ flex: 0 0 auto; grid-auto-rows: auto; }}
  .cards.compact .card {{ flex-direction: row; align-items: center; gap: 18px;
                          padding: {gap // 3}px {gap // 2}px; }}
  .cards.compact .card .icon {{ flex: 0 0 auto; }}
  .cards.compact .card-title {{ margin-top: 0; }}
  /* Скриншот — предметная сцена правой половины, как в её 5, 6 и 9 слайдах:
     не блок посреди колонки, а картинка, уходящая к краю холста. */
  .shot {{ position: absolute; z-index: 1; right: 0; bottom: {round(h * 0.16)}px;
           width: 56%; display: flex; justify-content: flex-end; align-items: center; }}
  .shot-img {{ display: block; max-width: 100%; max-height: {shot_max_h}px;
               width: auto; height: auto;
               object-fit: contain; border-radius: {tokens.RADIUS["card"]}px;
               border: {tokens.BORDER_WIDTH}px solid {_rgba(s["accent"], 0.38)};
               box-shadow: 0 0 64px {_rgba(s["accent"], 0.35)}; }}
  /* G18: правая сцена из её скринов — стопка карточек под наклоном, как
     карточки-скриншоты в reference/5.webp. Сцена занимает правую половину,
     текст — левую (`canvas.screens-scene`). */
  .screens {{ position: absolute; z-index: 1; top: {round(h * 0.20)}px; right: 0;
              width: {round(w * 0.52)}px; height: {round(h * 0.68)}px; }}
  .screens-glow {{ position: absolute; inset: -8%; border-radius: 50%;
                   background: {_glow(s["accent"], 0.30)}; }}
  .screen-card {{ position: absolute; padding: 10px;
                  border-radius: {tokens.RADIUS["card"]}px; background: {s["surface"]};
                  border: {tokens.BORDER_WIDTH}px solid {_rgba(s["text"], 0.14)};
                  box-shadow: {depth}; }}
  /* Снимок не увеличивается: потолки по ширине и высоте плюс `width: auto` —
     мелкий текст на нём остаётся мелким, это фактура, а не документ. */
  .screen-img {{ display: block; max-width: {round(w * 0.40)}px;
                 max-height: {round(h * 0.34)}px; width: auto; height: auto;
                 border-radius: {tokens.RADIUS["chip"]}px; }}
  .screen-card.s1 {{ top: {SCREEN_SLOTS[0]["top"]}; right: {SCREEN_SLOTS[0]["right"]};
                     z-index: 1; transform: rotate({SCREEN_SLOTS[0]["rot"]}deg); }}
  .screen-card.s2 {{ top: {SCREEN_SLOTS[1]["top"]}; right: {SCREEN_SLOTS[1]["right"]};
                     z-index: 2; transform: rotate({SCREEN_SLOTS[1]["rot"]}deg); }}
  .screen-card.s3 {{ top: {SCREEN_SLOTS[2]["top"]}; right: {SCREEN_SLOTS[2]["right"]};
                     z-index: 3; transform: rotate({SCREEN_SLOTS[2]["rot"]}deg); }}
  /* Стопка раскладывается по числу снимков: один — по центру сцены, два —
     в разбег, три — лесенкой. Иначе одинокий снимок висит в верхнем углу. */
  .screens.n1 .s1 {{ top: 22%; right: 9%; }}
  .screens.n2 .s1 {{ top: 0%; }}
  .screens.n2 .s2 {{ top: 36%; }}
  .canvas.screens-scene .hero, .canvas.screens-scene .lead {{ max-width: 46%; }}
  .portrait {{ position: absolute; z-index: 1; right: 0; bottom: 0;
               width: {inner // 2 + tokens.SAFE_ZONE}px; height: {h - 2 * tokens.SAFE_ZONE}px;
               display: flex; align-items: flex-end; justify-content: flex-end; }}
  .portrait-img {{ max-width: 100%; max-height: 100%; object-fit: contain;
                   -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 22%,
                     #000 100%), linear-gradient(270deg, #000 0%, #000 62%, transparent 100%);
                   -webkit-mask-composite: source-in;
                   mask-image: linear-gradient(180deg, transparent 0%, #000 22%, #000 100%),
                     linear-gradient(270deg, #000 0%, #000 62%, transparent 100%);
                   mask-composite: intersect; }}
  /* Плашка-сноска её слайда 04: оранжевый кружок `!`, вертикальная черта,
     первая строка белая, вторая сиреневая. */
  .summary {{ position: relative; z-index: 2; display: flex; align-items: center;
              gap: {gap // 2}px; border-radius: {tokens.RADIUS["card"]}px;
              background: {s["surface"]};
              border: {tokens.BORDER_WIDTH}px solid {_rgba(s["text"], 0.10)};
              padding: {gap // 2}px {gap}px; margin: {gap}px 0 {gap // 2}px;
              box-shadow: {depth}; }}
  .summary-mark {{ flex: 0 0 auto; width: {icon_size + 18}px; height: {icon_size + 18}px;
                   border-radius: 50%; border: {tokens.BORDER_WIDTH}px solid {O};
                   color: {O}; font-size: {label_size + 6}px;
                   line-height: {icon_size + 14}px; text-align: center; }}
  .summary-divider {{ flex: 0 0 auto; width: {tokens.BORDER_WIDTH}px;
                      height: {icon_size + 18}px; background: {_rgba(s["text"], 0.22)}; }}
  .summary-line {{ font-weight: {tokens.FONT_WEIGHTS["BODY"]}; font-size: {label_size + 4}px;
                   line-height: 1.45; color: {s["text"]}; }}
  .summary-line.accent {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
                          color: {P["VIOLET_SOFT"]}; }}
  .footer {{ position: relative; z-index: 2; display: flex; align-items: flex-end;
             justify-content: space-between; gap: {gap}px; min-height: {micro_size}px; }}
  .footer-thesis {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {micro_size}px;
                    line-height: 1.5; letter-spacing: 0.16em; text-transform: uppercase;
                    color: {s["muted"]}; }}
  /* Рукописные пометки: оранжевые, под наклоном, с рисованной стрелкой
     к тому, что комментируют. Их две-три на слайд (её слайды 5..9). */
  .hand-note {{ position: absolute; z-index: 4; display: flex; align-items: flex-start;
                width: {round(inner * 0.36)}px;
                font-family: '{tokens.HAND_FONT}', {tokens.HAND_FALLBACK};
                font-size: {hook_size // 2}px; line-height: 1.15; color: {O}; }}
  .hand-text {{ display: block; }}
  .hand-arrow {{ flex: 0 0 auto; width: {round(hook_size * 0.6)}px;
                 height: {round(hook_size * 0.8)}px; }}
  .at-top-right {{ top: {round(h * 0.12)}px; right: {gap}px; justify-content: flex-end; }}
  .at-top-right .hand-text {{ transform: rotate(-7deg); }}
  .at-top-right .hand-arrow {{ order: 2; margin-top: -8px; transform: scaleX(-1); }}
  .at-bottom-left {{ bottom: {round(h * 0.02)}px; left: {gap}px; }}
  .at-bottom-left .hand-text {{ transform: rotate(-6deg); }}
  .at-bottom-left .hand-arrow {{ order: 2; margin-top: 4px; }}
  .at-mid-right {{ top: {round(h * 0.47)}px; right: {gap}px; justify-content: flex-end; }}
  .at-mid-right .hand-text {{ transform: rotate(-8deg); }}
  .at-mid-right .hand-arrow {{ order: 2; margin-top: -6px; transform: scaleX(-1); }}
  .at-top-left {{ top: {round(h * 0.12)}px; left: {gap}px; }}
  .at-top-left .hand-text {{ transform: rotate(-5deg); }}
  .at-top-left .hand-arrow {{ order: 2; margin-top: 4px; }}
"""

    rubric = _rubric(label)
    header_html = (
        '<div class="header-count headline">'
        f'<span class="header-num">{index:02d}</span>'
        f'<span class="header-total">/ {total:02d}</span></div>'
        '<div class="header-line"></div>'
    )
    if rubric:
        header_html += f'<div class="header-label">{_t(rubric)}</div>'
    words = [accent_word] if isinstance(accent_word, str) else list(accent_word or [])
    hero_lines = _lines(hook) or [str(hook)]
    hero_html = "".join(
        f'<div class="hero-line">{_mark_accent(_quotes(line), words)}</div>'
        for line in hero_lines
    )
    lead_lines = _lines(body)
    lead_html = (
        '<p class="lead">' + "<br>".join(_t(line) for line in lead_lines) + "</p>"
        if lead_lines
        else ""
    )

    stroke, accent_stroke = s["accent_soft"], P["VIOLET_STRONG"]
    stage = []
    if steps:
        stage.append(_steps_html(steps, icon_size, stroke))
    if flow:
        stage.append(_flow_html(flow, icon_size, stroke, accent_stroke))
    if cards:
        stage.append(_cards_html(cards, icon_size, stroke, accent_stroke))
    portrait = _image_block("portrait", photo, "фото владелицы", notes)
    # сцена — это её правая половина: портрет или скриншот
    portrait_html = f'<div class="portrait">{portrait}</div>' if portrait else ""
    shot = _image_block("shot", screenshot, "скриншот владелицы", notes)
    shot_html = f'<div class="shot">{shot}</div>' if shot else ""
    screens_html = _screens_html(screens, notes)
    scene = " scene" if shot_html else ""
    if screens_html:
        scene += " screens-scene"
    hand_html = _hand_html(handwritten)
    # низ занят пометкой — оставляем ей место, а не кладём поверх текста
    if "at-bottom-left" in hand_html:
        scene += " bottom-note"

    stage_html = f'<div class="stage">{"".join(stage)}</div>' if stage else ""
    hero_fill = "" if (stage or shot_html or portrait_html) else " fill"

    summary_html = ""
    if summary:
        lines = _lines(summary, 2) or [str(summary)]
        rows = "".join(
            f'<div class="summary-line{" accent" if i else ""}">{_t(line)}</div>'
            for i, line in enumerate(lines)
        )
        summary_html = (
            '<div class="summary">'
            '<div class="summary-mark">!</div>'
            '<div class="summary-divider"></div>'
            f'<div class="summary-body">{rows}</div></div>'
        )

    markup = f"""<div class="canvas{scene}" id="slide">
  <div class="glow"></div>
  <div class="glow-2"></div>
  {portrait_html}
  {shot_html}
  {screens_html}
  <div class="header">{header_html}</div>
  <div class="hero headline{hero_fill}">{hero_html}</div>
  {lead_html}
  <div class="rule-accent"></div>
  {stage_html}
  {hand_html}
  {summary_html}
  <div class="footer">
    <div class="footer-thesis">{"<br>".join(_t(l) for l in _lines(footer_thesis, 2))}</div>
  </div>
</div>"""
    return _document(f"Слайд {index}", w, h, css, markup)


def build_post_cover(
    hook: str,
    subtitle: str = "",
    pill: str = COVER_PILL,
    microtext: str = COVER_MICROTEXT,
) -> str:
    """Обложка поста 1080×1350 в STYLE_02_LIGHT.

    По `SKILL_cover-post-katerina_SHORT.md`: светлый lavender-фон, graphite-текст,
    один violet-акцент, много воздуха, pill и microtext — её фирменные элементы.
    Место под фото справа оставлено пустым: фото подставляет владелица.
    """
    s = STYLE_SURFACES["STYLE_02_LIGHT"]
    w, h = tokens.CANVAS["cover"]
    hook_size, hook_lh = _scale("hook")
    body_size, body_lh = _scale("body")
    label_size, label_lh = _scale("label")
    micro_size, micro_lh = _scale("micro")

    css = f"""
  .canvas {{ background: {s["bg"]}; color: {s["text"]}; }}
  .glow {{ position: absolute; width: 760px; height: 760px; border-radius: 50%;
           top: -220px; right: -260px; pointer-events: none;
           background: {_glow(P["LAVENDER"], 0.55)}; }}
  .arc {{ position: absolute; width: 520px; height: 520px; border-radius: 50%;
          border: 2px solid {_rgba(s["accent"], 0.38)}; bottom: -180px; right: -140px;
          pointer-events: none; }}
  .pill-row {{ position: relative; z-index: 2; display: flex; align-items: center; gap: 24px; }}
  .pill {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {label_size}px;
           line-height: {label_lh}; letter-spacing: 0.12em; text-transform: uppercase;
           color: {s["accent_soft"]}; background: {_rgba(s["accent"], 0.16)};
           border: 2px solid {_rgba(s["accent"], 0.38)}; border-radius: 999px;
           padding: 12px 32px; }}
  .thin-line {{ flex: 1; height: 2px; background: {_rgba(s["accent"], 0.38)}; }}
  .hook-area {{ position: relative; z-index: 2; flex: 1; display: flex;
                flex-direction: column; justify-content: center; max-width: 640px; }}
  .hook {{ font-size: {hook_size}px; line-height: {hook_lh}; letter-spacing: -0.01em;
           color: {s["text"]}; }}
  .hook em {{ font-style: normal; color: {s["accent"]}; }}
  .subtitle {{ font-weight: {tokens.FONT_WEIGHTS["BODY"]}; font-size: {body_size}px;
               line-height: {body_lh}; color: {s["muted"]}; margin-top: 32px; }}
  .microtext {{ position: relative; z-index: 2; font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
                font-size: {micro_size}px; line-height: {micro_lh}; letter-spacing: 0.14em;
                text-transform: uppercase; color: {s["muted"]}; }}
  .photo-slot {{ position: absolute; z-index: 1; right: 0; bottom: 0;
                 width: 440px; height: 900px;
                 background: linear-gradient(180deg, transparent 0%, {_rgba(P["LAVENDER"], 0.45)} 100%); }}
"""
    subtitle_html = f'<p class="subtitle">{_t(subtitle)}</p>' if subtitle else ""
    markup = f"""<div class="canvas" id="cover">
  <div class="glow"></div>
  <div class="photo-slot"></div>
  <div class="arc"></div>
  <div class="pill-row">
    <span class="pill">{_t(pill)}</span>
    <span class="thin-line"></span>
  </div>
  <div class="hook-area">
    <div class="hook headline">{_t(hook)}</div>
    {subtitle_html}
  </div>
  <div class="microtext">{_t(microtext)}</div>
</div>"""
    return _document("Обложка поста", w, h, css, markup)


def build_story_background(key_phrase: str, caption: str = "") -> str:
    """Фон сторис 1080×1920 по `DESIGN.md` §18.

    Крупный текст, одно сообщение на сцену, один key phrase.
    Палитра §18: graphite, white, violet, lavender.
    """
    w, h = tokens.CANVAS["story"]
    hook_size, hook_lh = _scale("hook")
    body_size, body_lh = _scale("body")
    micro_size, micro_lh = _scale("micro")

    css = f"""
  .canvas {{ background: {P["BG_DARK_PRIMARY"]}; color: {P["TEXT_ON_DARK"]}; }}
  .glow {{ position: absolute; width: 900px; height: 900px; border-radius: 50%;
           top: -300px; left: -260px; pointer-events: none;
           background: {_glow(P["VIOLET_PRIMARY"], 0.35)}; }}
  .glow-2 {{ position: absolute; width: 640px; height: 640px; border-radius: 50%;
             bottom: -280px; right: -220px; pointer-events: none;
             background: {_glow(P["LAVENDER"], 0.22)}; }}
  .key-area {{ position: relative; z-index: 2; flex: 1; display: flex;
               flex-direction: column; justify-content: center; }}
  .key {{ font-size: {hook_size}px; line-height: {hook_lh}; letter-spacing: -0.01em;
          color: {P["TEXT_ON_DARK"]}; }}
  .key em {{ font-style: normal; color: {P["VIOLET_SOFT"]}; }}
  .accent-line {{ width: 120px; height: 8px; border-radius: 4px;
                  background: {P["VIOLET_PRIMARY"]}; margin-bottom: 48px; }}
  .caption {{ font-weight: {tokens.FONT_WEIGHTS["BODY"]}; font-size: {body_size}px;
              line-height: {body_lh}; color: {P["TEXT_MUTED_DARK"]}; margin-top: 40px; }}
  .nickname {{ position: relative; z-index: 2; font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
               font-size: {micro_size}px; line-height: {micro_lh}; letter-spacing: 0.08em;
               color: {P["TEXT_MUTED_DARK"]}; }}
"""
    caption_html = f'<p class="caption">{_t(caption)}</p>' if caption else ""
    markup = f"""<div class="canvas" id="story">
  <div class="glow"></div>
  <div class="glow-2"></div>
  <div class="key-area">
    <div class="accent-line"></div>
    <div class="key headline">{_t(key_phrase)}</div>
    {caption_html}
  </div>
  <div class="nickname">{_t(NICKNAME)}</div>
</div>"""
    return _document("Фон сторис", w, h, css, markup)
