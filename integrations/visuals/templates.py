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
import math
import re
from html import escape
from pathlib import Path

from . import tokens

P = tokens.PALETTE

#: Палитра каруселей — её `18_CAROUSEL_VISUAL_SYSTEM.md` §3. Обложка поста и
#: сторис остаются на `PALETTE`: её система написана про карусели и презентации.
C = tokens.CAROUSEL_PALETTE

#: Оранжевый акцент — её §3 «Главный акцент: тёплый оранжевый / apricot orange».
#: Им красятся: ключевое слово заголовка, отбивка под текстовой колонкой,
#: обводка акцентной плашки, отрезки цепочки и рукописные пометки.
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
    ("image", ("дизайн", "обложк", "визуал", "фото", "картинк", "изображ", "баннер",
               "оформл", "макет", "вёрстк", "верстк")),
    ("doc", ("текст", "пост", "копирайт", "промт", "гайд", "докумен",
             "файл", "стать", "подпис", "письм", "конспект")),
    ("check", ("провер", "контрол", "результат", "готов", "качеств", "сама")),
    ("clock", ("врем", "час", "минут", "срок", "сколько", "долго", "быстре")),
    ("hourglass", ("ждать", "ожидан", "дедлайн", "откладыва", "потом")),
    ("search", ("поиск", "ищеш", "иска", "найд", "выбер", "выбор", "разбер")),
    ("gear", ("процесс", "систем", "настрой", "автоматиз", "инструмент",
              "механизм", "шаблон", "повторя")),
    ("chart", ("цифр", "статист", "аналит", "охват", "рост", "метрик", "smm",
               "соцсет", "блог", "аккаунт", "отчёт", "отчет", "публик", "выклад")),
    ("flask", ("тест", "эксперимент", "пробу", "гипотез")),
    ("bolt", ("энерг", "сразу", "мгновен", "разгон", "ускор")),
    ("map", ("задач", "план", "шаг", "маршрут", "воронк", "путь", "карт",
             "сценар", "раскадров")),
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


def _next_icon(caption: str, taken: set) -> str:
    """Следующая по смыслу иконка, которой в этом ряду ещё нет."""
    text = str(caption or "").casefold().replace("ё", "е")
    for name, keys in ICON_HINTS:
        if name in taken:
            continue
        if any(key.replace("ё", "е") in text for key in keys):
            return name
    for name in ICONS:
        if name not in taken and name != DEFAULT_STEP_ICON:
            return name
    return DEFAULT_STEP_ICON


def pick_icons(captions, taken=()) -> list:
    """Иконки для ряда блоков: по смыслу подписи и **без повторов** (таск 11 п.6).

    Её §8 TYPE C — цепочка одинаковых блоков, различаются они иконкой. Две
    одинаковые иконки из пяти (её рендер carousel-06) убивают весь смысл ряда,
    поэтому совпадение разводится: сначала следующей подходящей по смыслу
    подписи, потом просто другой иконкой из её же словаря `ICONS`.
    Ничего нового не рисуется.

    `taken` — имена, уже занятые данными слайда (`icon` задан явно).
    """
    used = {str(name) for name in taken if name}
    out = []
    for caption in captions:
        name = pick_icon(caption)
        if name in used:
            name = _next_icon(caption, used)
        used.add(name)
        out.append(name)
    return out


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

#: Та же дуга, но сверху вниз — для вертикальной цепочки финального слайда
#: (таск 11 п.7: «четыре пункта цепочкой сверху вниз со стрелками»).
CHAIN_ARROW = (
    '<svg class="chain-arrow-svg" viewBox="0 0 34 48" fill="none" stroke="currentColor" '
    'stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M8 4C28 14 30 30 16 44"/>'
    '<path d="M20 31L16 44L29 41"/></svg>'
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

#: Нижняя граница кегля заголовка обложки. Ниже её §4 («заголовок — важнейший
#: элемент», 30–50% площади) перестаёт выполняться: строка садится до размера
#: второго уровня, и обложка теряет силу.
MIN_HERO_SIZE = 56

#: Запас на межбуквенный интервал и знаки шире средней ширины (цифры, «Ш»,
#: запятые с пробелом). `CONDENSED_CAPS_ADVANCE` — средняя ширина знака, а
#: строка почти никогда не средняя: без запаса самая длинная строка обложки
#: перескакивает на следующую и её §18 ломается седьмой строкой.
HERO_FIT_SAFETY = 1.06

#: Ник в шапке слайда — из её вёрстки.
NICKNAME = "@studio_essa_ai"

#: Фирменные элементы обложки — из SKILL_cover-post-katerina_SHORT.md.
COVER_PILL = "МОЙ ПОДХОД"
COVER_MICROTEXT = "ТЕСТИРУЮ / АНАЛИЗИРУЮ / УЛУЧШАЮ"

#: Оформление разрешённых стилей карусели.
#: Ключи — только из `tokens.STYLES`; цвета — только из `tokens.PALETTE`.
#: Ключи поверхностей: `bg` и `deep` — два конца фонового градиента (§3
#: «чёрный → тёмный фиолетовый»), `plate` и `plate_border` — плашки §13,
#: `accent` / `accent_soft` — muted violet §3, `fill` — заливка акцентного узла.
STYLE_SURFACES = {
    # §3: основной фон #0D0D10 / #111115, основной текст #F5F3F0.
    "STYLE_01": {
        "bg": C["BG_BASE"],
        "deep": C["BG_DEEP"],
        "surface": C["BG_RAISED"],
        "plate": tokens.PLATE["BASE"],
        "plate_border": C["VIOLET_DEEP"],
        "text": C["TEXT"],
        "muted": C["TEXT_MUTED"],
        "accent": C["VIOLET_DEEP"],
        "accent_soft": C["VIOLET_LIGHT"],
        "fill": C["VIOLET_DEEP"],
    },
    # Светлый полюс чередования (её слова 2026-09-21: «чередуем тёмный
    # и светлый»). Светлых значений её новая система не задаёт — они остаются
    # из DESIGN.md, а акценты приходят из её §3.
    "STYLE_02_LIGHT": {
        "bg": P["BG_LIGHT_PRIMARY"],
        "deep": P["BG_LIGHT_SECONDARY"],
        "surface": P["BG_LIGHT_SECONDARY"],
        "plate": P["BG_LIGHT_SECONDARY"],
        "plate_border": C["VIOLET_DEEP"],
        "text": P["TEXT_ON_LIGHT"],
        "muted": P["TEXT_MUTED_LIGHT"],
        "accent": C["VIOLET_DEEP"],
        "accent_soft": C["VIOLET_DEEP"],
        "fill": C["VIOLET_DEEP"],
    },
    # §3: третий её фон #17151A — dark-variant того же editorial.
    "STYLE_02_DARK": {
        "bg": C["BG_RAISED"],
        "deep": C["BG_DEEP"],
        "surface": C["BG_BASE"],
        "plate": tokens.PLATE["RAISED"],
        "plate_border": C["VIOLET_DEEP"],
        "text": C["TEXT"],
        "muted": C["TEXT_MUTED"],
        "accent": C["VIOLET_DEEP"],
        "accent_soft": C["VIOLET_LIGHT"],
        "fill": C["VIOLET_DEEP"],
    },
}


def pick_composition(
    photo=None, screenshot=None, screens=None, steps=None, flow=None, cards=None,
    apps=None, chain=None,
) -> str:
    """Тип композиции по тому, что несёт слайд (§8, §17).

    Её правило: «Не использовать одну сетку на всех слайдах». Тип задаётся
    данными слайда явно; не задан — выводится отсюда, чтобы девять слайдов
    не оказались девятью одинаковыми сетками.

    A — её портрет; B — один объект с экраном; C — последовательность шагов;
    D — несколько интерфейсных карточек или ряд плашек; E — только текст.
    """
    many = screens if isinstance(screens, (list, tuple)) else ([screens] if screens else [])
    if photo:
        return "A"
    # Корпус телефона с сеткой приложений — такой же объект её §8 TYPE B,
    # как и встроенный скрин: на холсте стоит устройство, а не типографика.
    if screenshot or apps or len(many) == 1:
        return "B"
    if steps or flow or chain:
        return "C"
    if len(many) > 1 or cards:
        return "D"
    return "E"


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


def _document(
    title: str, width: int, height: int, css: str, body: str, padding: str = ""
) -> str:
    """Страница-холст: ровно один кадр нужного размера, без полей и прокрутки.

    `padding` — поля холста. У карусели они её собственные и несимметричные
    (§1: слева/справа 55–70, сверху 45–60, снизу 60–80); у обложки и сторис
    остаётся общий safe zone DESIGN.md §11.
    """
    head = tokens.FONTS["HEADLINE"]
    padding = padding or f"{tokens.SAFE_ZONE}px"
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
    padding: {padding};
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


#: Картинки правой сцены — те, что размываются всегда (G19).
#: Её фото (`portrait`) сюда не входит: оно должно читаться.
BLURRED_KINDS = ("screen", "shot")


def _image_block(kind: str, path, caption: str, notes: list) -> str:
    """Картинка владелицы: её файл или честная строка о том, что файла нет.

    Заглушку не рисуем и чужого не подставляем (таск 05, пп. 5 и 7).

    Скрины правой сцены размываются здесь и всегда: размытие стоит прямо
    на элементе, данными слайда не выключается (G19, её слова 2026-09-22).
    """
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        notes.append(f"{kind}: файла нет — {p}; слайд собран без него")
        return f"<!-- {kind}: файла нет — {_t(p)} -->"
    notes.append(f"{kind}: {p.name}")
    alt = _t(caption or p.name)
    blur = (
        f' style="filter: blur({tokens.SCREEN_BLUR}px);"'
        if kind in BLURRED_KINDS
        else ""
    )
    return f'<img class="{kind}-img" src="{_t(p.name)}" alt="{alt}"{blur}>'


#: Корпуса, в которые встраивается её скрин (§8 TYPE B). Ничего третьего:
#: телефон и экран ноутбука — те объекты, что названы в её же списке.
DEVICE_KINDS = ("laptop", "phone")
DEFAULT_DEVICE = "laptop"


def _device_html(kind: str, img: str) -> str:
    """Её скрин внутри корпуса устройства (§8 TYPE B).

    «Не использовать плоский screenshot, лежащий прямоугольником поверх фона.
    Screenshot должен быть встроен в физический объект или композицию.»
    Поэтому снимок никогда не кладётся на холст сам: он всегда живёт внутри
    `.device-screen` — экрана телефона или ноутбука, стоящего в перспективе.

    Корпус рисуется CSS: ни одного придуманного изображения здесь нет,
    картинка — только её файл.
    """
    kind = kind if kind in DEVICE_KINDS else DEFAULT_DEVICE
    extra = (
        '<div class="device-notch"></div>'
        if kind == "phone"
        else '<div class="device-hinge"></div>'
    )
    base = '<div class="device-base"></div>' if kind == "laptop" else ""
    return (
        f'<div class="device {kind}">'
        f'<div class="device-body">'
        f'<div class="device-screen">{img}<div class="device-glare"></div></div>'
        f"{extra}</div>{base}</div>"
    )


def _wrap_words(lines: list, limit: int) -> list:
    """Строки второго уровня — не длиннее её нормы (§5: 4–8 слов в строке).

    Текст владелицы не переписывается: он только переносится. Её собственные
    переводы строки остаются границами, длинная строка делится по словам.
    """
    out = []
    for line in lines:
        words = line.split()
        if len(words) <= limit:
            out.append(line)
            continue
        # делим на примерно равные куски, чтобы не осталось строки из одного слова
        chunks = math.ceil(len(words) / limit)
        size = math.ceil(len(words) / chunks)
        out.extend(
            " ".join(words[i:i + size]) for i in range(0, len(words), size)
        )
    return out


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


def _words(text: str) -> list:
    """Слова строки без регистра и знаков — чтобы сравнивать смысл, а не набор
    кавычек, переводов строк и вопросительных знаков."""
    low = re.sub(r"[^\w\s]+", " ", str(text or ""), flags=re.UNICODE).casefold()
    return low.split()


def _echoes(note: list, said: list) -> bool:
    """Пометка пересказывает то, что на слайде уже написано?

    Да — если все её слова встречаются в тексте слайда по порядку:
    «что не хочу делать руками» внутри «что я больше не хочу делать руками».
    Своё слово хотя бы одно («сохранённого много» против «у тебя куча
    сохранённого») — это уже комментарий, а не повтор.
    """
    if not note:
        return False
    rest = iter(said)
    return all(word in rest for word in note)


def _hand_html(handwritten, said=()) -> str:
    """Рукописные пометки: две-три на слайд, оранжевые, со стрелкой к тому,
    что комментируют (её слова 2026-09-22 и слайды 5..9).

    Пометка приходит **своим полем** данных слайда и больше ниоткуда
    (G20, её слова: «пометки отдельно пиши»). Поля нет — пометок на слайде нет:
    молчаливого повтора заголовка вёрстка не делает.

    Текст приходит данными: строка — одна пометка, список — несколько.
    Место можно задать явно (`{"text": …, "at": "bottom-left"}`), не задали —
    слоты раздаются по порядку её слайдов.

    `said` — то, что на слайде уже написано (заголовок, лид). Пометка, которая
    это повторяет, не рисуется: у неё пометка — комментарий сбоку
    («сохранённого много», «инструменты ≠ система»), а не второй заголовок.
    """
    if not handwritten:
        return ""
    spoken = [w for w in (_words(s) for s in said) if w]
    items = [handwritten] if isinstance(handwritten, (str, dict)) else list(handwritten)
    parts = []
    for item in items:
        data = item if isinstance(item, dict) else {"text": item}
        text = str(data.get("text", "")).strip()
        if not text:
            continue
        if any(_echoes(_words(text), s) for s in spoken):
            continue
        slot = data.get("at") or HAND_SLOTS[len(parts) % len(HAND_SLOTS)]
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
    auto = pick_icons(
        [s.get("caption", "") for s in steps],
        taken=[s.get("icon") for s in steps],
    )
    cells = []
    for i, step in enumerate(steps, start=1):
        if i > 1:
            cells.append('<div class="step-link"></div>')
        icon = _icon(step.get("icon", ""), icon_size, stroke) or _icon(
            auto[i - 1], icon_size, stroke
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
    auto = pick_icons(
        [c.get("title", "") for c in flow],
        taken=[c.get("icon") for c in flow],
    )
    parts = []
    last = len(flow) - 1
    for i, card in enumerate(flow):
        if i:
            parts.append(f'<div class="flow-arrow">{FLOW_ARROW}</div>')
        accent = " accent" if i == last and card.get("accent", True) else ""
        pen = accent_stroke if accent else stroke
        icon = _icon(card.get("icon", ""), icon_size, pen) or _icon(
            auto[i], icon_size, pen
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


def _chain_html(chain: list, icon_size: int, stroke: str) -> str:
    """Вертикальная цепочка со стрелками (таск 11 п.7).

    Её §19: финальный слайд — «3–4 коротких пункта». Пункты в нём не строки
    текста, а шаги, идущие сверху вниз: между блоками оранжевая стрелка
    её же рисунка. Перечёркивания нет — стрелка стоит **между** блоками,
    как отрезки горизонтальной цепочки (G12).
    """
    items = [c if isinstance(c, dict) else {"title": c} for c in chain]
    auto = pick_icons(
        [i.get("title", "") for i in items],
        taken=[i.get("icon") for i in items],
    )
    parts = []
    for i, item in enumerate(items):
        if i:
            parts.append(f'<div class="chain-arrow">{CHAIN_ARROW}</div>')
        icon = _icon(item.get("icon", ""), icon_size, stroke) or _icon(
            auto[i], icon_size, stroke
        )
        parts.append(
            f'<div class="chain-item">{icon}'
            f'<div class="chain-title">{_t(item.get("title", ""))}</div></div>'
        )
    return '<div class="chain">' + "".join(parts) + "</div>"


def _apps_html(count: int, icon_size: int, stroke: str) -> str:
    """Сетка плиток приложений внутри корпуса телефона (таск 11 п.9).

    Её §20: «слишком много приложений → смартфон с набором приложений».
    Плитка — блок её же плашки с одной line-иконкой из `ICONS`; ни одного
    чужого логотипа, ни одного сгенерированного изображения, ни одной
    подписи. Смысл кадра — «их много», а не «вот эти конкретные».
    """
    names = list(ICONS)
    tiles = "".join(
        f'<div class="app-tile">{_icon(names[i % len(names)], icon_size, stroke)}</div>'
        for i in range(max(0, int(count)))
    )
    return f'<div class="app-grid">{tiles}</div>' if tiles else ""


#: Правая сцена из её скринов (G18, `reference/5.webp`): один-три снимка лежат
#: стопкой, каждый чуть повёрнут и сдвинут. Слоты заданы явно, чтобы стопка
#: была предсказуемой, а не случайной.
#: §8 TYPE D: карточки в перспективе, на разных уровнях, частично перекрываются
#: и становятся темнее вдали. `kind` — корпус, в котором лежит снимок (§8 TYPE B:
#: плоских прямоугольников в кадре не бывает вовсе).
SCREEN_SLOTS = (
    {"top": "2%", "right": "2%", "rot": -6, "yaw": -18, "kind": "laptop"},
    {"top": "34%", "right": "22%", "rot": -3, "yaw": -12, "kind": "phone"},
    {"top": "62%", "right": "4%", "rot": -8, "yaw": -22, "kind": "phone"},
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
        slot = SCREEN_SLOTS[len(cards)]
        kind = str(data.get("device") or slot["kind"])
        cards.append(
            f'<div class="screen-card s{len(cards) + 1}">'
            + _device_html(kind, img)
            + "</div>"
        )
    if not cards:
        return ""
    return f'<div class="screens n{len(cards)}">' + "".join(cards) + "</div>"


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
    chain: list = None,
    summary: str = "",
    summary_accent: bool = False,
    handwritten: str = "",
    photo=None,
    portrait_width: float = 0,
    screenshot=None,
    screens=None,
    apps=0,
    device: str = "",
    composition: str = "",
    header: bool = True,
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
    текста слайда (`auto_blocks`). `chain` — те же блоки, но вертикальной
    цепочкой со стрелками сверху вниз (её §19, финальный слайд).
    `summary_accent` — акцентная оранжевая обводка плашки-вывода (§13 + §8 TYPE D).
    `header` — верхняя панель §7; на обложке её можно снять (§18 «минимум
    мелкого текста»), на внутренних слайдах она остаётся.
    `portrait_width` — доля ширины кадра под портрет, только внутри её §8
    TYPE A (40–55%); не задана — рабочее значение `tokens.PORTRAIT_WIDTH`.
    `apps` — число плиток приложений в корпусе телефона (§20; вместо скрина,
    которого нет). `photo` и `screenshot` — файлы владелицы:
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
    if composition and composition not in tokens.COMPOSITION_TYPES:
        raise ValueError(
            f"тип композиции {composition!r} не из её §8; допустимы "
            f"{', '.join(tokens.COMPOSITION_TYPES)}"
        )
    s = STYLE_SURFACES[style]
    w, h = tokens.CANVAS["carousel"]
    if notes is None:
        notes = []
    m = tokens.CAROUSEL_MARGIN
    pad = f'{m["top"]}px {m["right"]}px {m["bottom"]}px {m["left"]}px'
    lo_portrait, hi_portrait = tokens.PORTRAIT_WIDTH_RANGE
    portrait_frac = float(portrait_width or tokens.PORTRAIT_WIDTH)
    if not lo_portrait <= portrait_frac <= hi_portrait:
        raise ValueError(
            f"портрет на {portrait_frac:.0%} кадра — её §8 TYPE A держит человека "
            f"в правых {lo_portrait:.0%}–{hi_portrait:.0%}"
        )
    hook_size, hook_lh = _scale("hook" if role == "cover" else "slide_title")
    body_size, body_lh = _scale("body")
    label_size, label_lh = _scale("label")
    micro_size, micro_lh = _scale("micro")
    #: §4: заголовок занимает 30–50% площади слайда.
    hero_min = round(h * tokens.HEADLINE_AREA_RANGE[0])
    hero_max = round(h * tokens.HEADLINE_AREA_RANGE[1])
    # Кружки, иконки и подписи цепочки — в пропорциях её reference/1.webp:
    # кружок примерно вчетверо крупнее подписи, иконка вдвое.
    dot = round(label_size * 4)
    # G17: иконки крупнее, чем были (2.2 — они терялись в карточке) и с
    # собственной подсветкой (`.icon` ниже).
    icon_size = round(label_size * 3.0)
    gap = m["top"] // 2
    inner = w - m["left"] - m["right"]
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

    if not (steps or flow or cards or chain):
        derived = auto_blocks(body)
        steps = derived.get("steps")
        flow = derived.get("flow")
        cards = derived.get("cards")
        if derived:
            body = ""

    # Кегль подписи потока: чем больше карточек в ряду, тем уже карточка.
    # Самое длинное слово обязано встать в строку — иначе браузер ломает его
    # пополам («ОФОРМЛЕН/ИЕ» в её рендере carousel-06).
    flow_gap = 8
    #: Потолок ряда карточек — треть холста (её reference/3.webp).
    flow_cap = round(h / 3)
    flow_pad = gap // 2
    #: Ширина рисованной стрелки между карточками — ровно та, что стоит в CSS
    #: `.flow-arrow`. Раньше в расчёт уходила половина этой ширины, ряд считался
    #: шире, чем есть, и кегль выходил завышенным — оттуда и разрыв слова.
    #: Стрелка вдвое уже прежней: на ряде из пяти блоков четыре широкие стрелки
    #: съедали 216 px, карточка не добирала до «ОФОРМЛЕНИЕ», и слово ломалось
    #: пополам (её рендер carousel-06). Дуга читается и в этой ширине.
    flow_arrow_w = round(label_size * 1.2)
    flow_title_size = label_size
    if flow:
        n = len(flow)
        card_w = (inner - (flow_arrow_w + 2 * flow_gap) * (n - 1)) / n
        # box-sizing: border-box — рамка съедает ширину наравне с полями
        content_w = card_w - 2 * flow_pad - 2 * tokens.BORDER_WIDTH
        longest = max(
            (len(word) for c in flow for word in str(c.get("title", "")).split()),
            default=1,
        )
        flow_title_size = max(
            MIN_FLOW_TITLE,
            min(
                label_size,
                int(content_w / (CONDENSED_CAPS_ADVANCE * HERO_FIT_SAFETY * longest)),
            ),
        )

    # --- что стоит на слайде: графика слева, предметная сцена справа ---------
    # Считается до CSS: от этого зависит ширина колонки заголовка и текста.
    # §12 ИКОНКИ: только белые или светло-фиолетовые, штрих одной толщины
    stroke, accent_stroke = s["accent_soft"], C["TEXT"]
    stage = []
    if steps:
        stage.append(_steps_html(steps, icon_size, stroke))
    if flow:
        stage.append(_flow_html(flow, icon_size, stroke, accent_stroke))
    if cards:
        stage.append(_cards_html(cards, icon_size, stroke, accent_stroke))
    if chain:
        stage.append(_chain_html(chain, round(label_size * 1.6), stroke))
    kind = composition or pick_composition(
        photo=photo, screenshot=screenshot, screens=screens,
        steps=steps, flow=flow, cards=cards, apps=apps, chain=chain,
    )
    portrait = _image_block("portrait", photo, "фото владелицы", notes)
    # сцена — это её правая половина: портрет, скриншот или корпус устройства
    portrait_html = f'<div class="portrait">{portrait}</div>' if portrait else ""
    shot = _image_block("shot", screenshot, "скриншот владелицы", notes)
    shot_kind = device or DEFAULT_DEVICE
    shot_html = (
        f'<div class="shot {shot_kind}-shot">'
        f"{_device_html(shot_kind, shot)}</div>"
        if shot and not shot.startswith("<!--")
        else ""
    )
    if not shot_html and apps:
        tiles = _apps_html(
            tokens.APP_GRID_TILES if apps is True else apps,
            round(label_size * 1.4),
            stroke,
        )
        if tiles:
            shot_html = f'<div class="shot">{_device_html("phone", tiles)}</div>'
    screens_html = _screens_html(screens, notes)
    scene = " scene" if shot_html else ""
    if screens_html:
        scene += " screens-scene"
    if portrait_html:
        scene += " portrait-scene"
        if role == "cover":
            scene += " cover-scene"

    #: §8 TYPE A: портрет занимает правые 40–55% кадра, текст и плашка живут
    #: в своей колонке слева. Не хватает места — уменьшается колонка текста,
    #: а не портрет (таск 11 п.1–2).
    portrait_w = round(w * portrait_frac)
    portrait_fade = round((1 - tokens.PORTRAIT_FADE) * 100)
    #: Колонка текста упирается в левый край портрета: пересечения нет по
    #: разметке, а не на глаз.
    text_col = w - portrait_w - m["left"]
    #: Заголовку можно зайти в мягкую кромку выреза — там фон, а не человек;
    #: дальше начинается непрозрачная часть кадра, и туда текст не идёт.
    portrait_solid = w - portrait_w + round(portrait_w * tokens.PORTRAIT_FADE)

    #: Ширина колонки заголовка — по тому, что стоит справа.
    if portrait_html:
        hero_w = portrait_solid - m["left"]
    elif screens_html:
        hero_w = round(inner * 0.46)
    elif shot_html:
        hero_w = round(inner * 0.56)
    elif role == "cover":
        # §18: слева крупный headline, мелкого текста нет — колонка шире.
        hero_w = round(inner * 0.88)
    else:
        hero_w = round(inner * 0.78)

    hero_lines = _lines(hook) or [str(hook)]
    lo_cover, hi_cover = tokens.COVER_HEADLINE_LINES
    if role == "cover" and len(hero_lines) > hi_cover:
        raise ValueError(
            f"заголовок обложки в {len(hero_lines)} строк; её §18 держит "
            f"{lo_cover}–{hi_cover} — разбей строки иначе"
        )
    #: Кегль заголовка подбирается под колонку: каждая строка обязана встать
    #: целиком, иначе браузер добавляет свою — и на обложке появляется седьмая
    #: строка сверх её §18 (её рендер carousel-01). Подбор только уменьшает
    #: и работает только там, где строки разбиты автором: одиночный заголовок
    #: переносится браузером, и подгонять под него нечего.
    #: `hero_room` — кегль, при котором строка ещё физически влезает в колонку;
    #: `hero_fit` — он же с запасом на знаки шире средних. Подбор идёт по
    #: запасу, а обратный подъём под §5 — по физическому пределу: иначе
    #: округление запаса отнимает у заголовка последний пиксель.
    hero_room = hook_size
    if len(hero_lines) > 1:
        longest_line = max(len(line) for line in hero_lines)
        hero_room = int(hero_w / (CONDENSED_CAPS_ADVANCE * longest_line))
        hero_fit = int(hero_room / HERO_FIT_SAFETY)
        hook_size = max(MIN_HERO_SIZE, min(hook_size, hero_fit))
    #: Заголовок не подходит вплотную к верхней линии: панели на обложке нет,
    #: и без её отступа заголовок садится прямо на поле (§18).
    hero_top = gap if header else round(h * 0.06)
    #: §5: второй уровень меньше заголовка в 2,5–4 раза — считается от
    #: заголовка (уже подобранного), а не берётся из шкалы вслепую, и всё
    #: равно остаётся внутри её рабочего диапазона body.
    lo_body, hi_body = tokens.TYPE_SCALE["body"]["range"]
    #: §5: второй уровень меньше заголовка в 2,5–4 раза, а ниже своей шкалы он
    #: не опускается — значит заголовку рядом с текстом нужно хотя бы 2,5 кегля
    #: body. Поднимаем, но только в пределах колонки: её же пример из §4
    #: («5. НА КОНТЕНТ ВСЁ РАВНО…» во всю ширину) сам идёт ниже этой границы,
    #: а разорванная строка — дефект, который она уже называла.
    if body:
        hook_size = max(
            hook_size,
            min(hero_room, math.ceil(lo_body * tokens.BODY_RATIO_RANGE[0])),
        )
    lead_size = min(
        hi_body,
        max(lo_body, math.floor(hook_size / tokens.BODY_RATIO_RANGE[0])),
    )
    #: Плашка-вывод в колонке рядом с портретом уже, чем во всю ширину, и её
    #: строка обязана в эту колонку встать: иначе плашка вырастает вниз и
    #: уезжает за нижнее поле. Кегль считается по самой длинной строке вывода.
    summary_size = label_size + 4
    if portrait_html and summary:
        #: Средняя ширина знака Open Sans Regular в долях кегля — замерено
        #: в браузере на её же строке вывода.
        plate_text = text_col - 2 * gap - (icon_size + 18) - 2 * gap
        longest_row = max((len(r) for r in (_lines(summary, 2) or [summary])), default=1)
        summary_size = max(micro_size, min(summary_size, int(plate_text / (0.50 * longest_row))))

    css = f"""
  /* §10 СВЕТ: «Фон не должен быть просто чёрным». Должно ощущаться
     пространство: фон — мягкий градиент её §3 («чёрный → тёмный фиолетовый»),
     а не плоская заливка; угол даёт ощущение стены и угла помещения.
     §14 ДЕКОР: абстрактных кружков и случайных blobs здесь нет — они убраны. */
  .canvas#slide {{ color: {s["text"]};
    background: linear-gradient(152deg, {s["bg"]} 0%, {s["deep"]} 46%,
      {_rgba(C["VIOLET_DEEP"], 0.16)} 100%), {s["deep"]}; }}
  /* Направленный тёплый свет и мягкое фиолетовое отражение: два наклонных
     луча, а не пятна. Форма — полоса под углом, как свет из окна. */
  .light {{ position: absolute; inset: 0; z-index: 0; pointer-events: none;
            background:
              linear-gradient(118deg, {_rgba(C["ORANGE_DEEP"], 0.20)} 0%,
                {_rgba(C["ORANGE_DEEP"], 0.05)} 22%, transparent 42%),
              linear-gradient(292deg, {_rgba(C["VIOLET"], 0.16)} 0%,
                transparent 38%); }}
  /* §10 «размытая поверхность»: дальний план — стол или пол под контентом. */
  .surface {{ position: absolute; z-index: 0; left: 0; right: 0; bottom: 0;
              height: {round(h * 0.26)}px; pointer-events: none;
              filter: blur(70px);
              background: linear-gradient(180deg, transparent 0%,
                {_rgba(s["deep"], 0.0)} 30%, {_rgba(C["VIOLET_DEEP"], 0.09)} 100%); }}
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
  /* §4: заголовок — важнейший элемент, занимает 30–50% площади слайда. */
  /* Короткий заголовок не висит вверху зарезервированной полосы, а стоит
     в её середине: иначе под одной строкой остаётся дыра на треть холста. */
  .hero {{ position: relative; z-index: 2; margin-top: {hero_top}px; max-width: {hero_w}px;
           min-height: {hero_min}px; max-height: {hero_max}px;
           display: flex; flex-direction: column; justify-content: center;
           font-size: {hook_size}px; line-height: {hook_lh};
           letter-spacing: -0.01em; text-transform: uppercase; color: {s["text"]};
           margin-bottom: {gap // 2}px; }}
  .hero-line {{ display: block; }}
  .hero .accent, .hero em {{ font-style: normal; color: {O}; }}
  .lead {{ position: relative; z-index: 2; font-weight: {tokens.FONT_WEIGHTS["BODY"]};
           font-size: {lead_size}px; line-height: {body_lh}; color: {s["text"]};
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
  .step-link {{ flex: 0 0 auto; width: 48px; height: 8px; border-radius: 4px;
                background: {O}; align-self: center;
                box-shadow: 0 0 16px {_rgba(O, 0.55)}; }}
  .steps-row {{ position: relative; display: flex; justify-content: space-between;
                align-items: stretch; gap: 16px; }}
  /* §8 TYPE C: «одинаковые компактные блоки — тёмный фон, тонкая violet border,
     минималистичная line icon»; стрелки между ними оранжевые. */
  .step {{ flex: 1; text-align: center; padding: {gap // 2}px {gap // 3}px;
           border-radius: {tokens.PLATE_RADIUS}px; background: {s["plate"]};
           border: 1px solid {s["plate_border"]}; box-shadow: {depth};
           display: flex; flex-direction: column; align-items: center; }}
  .step-dot {{ width: {dot}px; height: {dot}px; border-radius: 50%;
               margin: 0 auto; background: {s["fill"]}; color: {C["TEXT"]};
               font-size: {label_size + 8}px; line-height: {dot}px;
               box-shadow: {node_glow}, inset 0 3px 0 {_rgba(P["TEXT_ON_DARK"], 0.55)},
                 inset 0 -4px 0 {_rgba(P["BG_DARK_PRIMARY"], 0.22)}; }}
  .step-icon {{ margin: {gap // 2}px auto {gap // 3}px; height: {icon_size}px; }}
  .step-caption {{ font-family: '{tokens.FONTS["HEADLINE"]}', {tokens.FALLBACK_STACK};
                   font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]};
                   font-size: {label_size + 8}px; line-height: 1.15; color: {s["text"]};
                   min-height: {round((label_size + 8) * 1.15 * 2)}px; }}
  .step-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 20px;
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
  /* §13 ИНФОРМАЦИОННЫЕ ПЛАШКИ: её фон, скругление 20–28 и тонкая violet-обводка.
     Плашка не должна читаться как стандартный UI card — отсюда мягкая тень
     и слои по краю, а не ровный прямоугольник. */
  .flow-card {{ flex: 1 1 0; min-width: 0; overflow-wrap: break-word;
                display: flex; flex-direction: column; justify-content: center;
                border-radius: {tokens.PLATE_RADIUS}px;
                background: {s["plate"]}; border: 1px solid
                {s["plate_border"]}; padding: {gap}px {flow_pad}px;
                box-shadow: {depth}; }}
  .flow-card.accent {{ background: {s["fill"]}; border-color: {O};
                       box-shadow: {node_glow}; }}
  .flow-card.accent .flow-title, .flow-card.accent .flow-note {{ color: {C["TEXT"]}; }}
  /* Кегль подписи потока — базовый label: на четырёх карточках длинное слово
     («ВОЗВРАЩЁННОЕ») должно вставать в строку, а не ломаться переносом. */
  .flow-title {{ font-size: {flow_title_size}px; line-height: 1.15; margin-top: 18px;
                 text-transform: uppercase; color: {s["text"]}; }}
  .flow-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 14px;
                color: {s["muted"]}; }}
  /* G17: между карточками — рисованная дуга, а не типографская стрелка. */
  .flow-arrow {{ align-self: center; flex: 0 0 auto; color: {O};
                 width: {flow_arrow_w}px; height: {round(label_size * 1.4)}px; }}
  .flow-arrow-svg {{ width: 100%; height: 100%;
                     filter: drop-shadow(0 0 12px {_rgba(O, 0.45)}); }}
  .icon {{ filter: {icon_glow}; }}
  .cards {{ flex: 1; display: grid; gap: 16px; grid-auto-rows: 1fr; }}
  .card {{ border-radius: {tokens.PLATE_RADIUS}px; background: {s["plate"]};
           border: 1px solid {s["plate_border"]};
           padding: {gap // 2}px; box-shadow: {depth};
           display: flex; flex-direction: column; justify-content: center; }}
  .card.accent {{ background: {s["fill"]}; border-color: {O};
                  box-shadow: {node_glow}; }}
  .card.accent .card-title, .card.accent .card-note {{ color: {C["TEXT"]}; }}
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
  /* §19 ФИНАЛЬНЫЙ СЛАЙД: «3–4 коротких пункта». Пункты идут цепочкой сверху
     вниз, между ними — та же рисованная оранжевая стрелка, что и в её
     горизонтальной цепочке. Сквозной линии нет: она читалась бы как
     перечёркивание (её замечание 2026-09-22). */
  .chain {{ flex: 0 0 auto; display: flex; flex-direction: column;
            align-items: stretch; }}
  .chain-item {{ display: flex; align-items: center; gap: {gap // 2}px;
                 border-radius: {tokens.PLATE_RADIUS}px; background: {s["plate"]};
                 border: 1px solid {s["plate_border"]};
                 padding: {gap // 3}px {gap // 2}px; box-shadow: {depth}; }}
  .chain-item .icon {{ flex: 0 0 auto; }}
  .chain-title {{ font-family: '{tokens.FONTS["HEADLINE"]}', {tokens.FALLBACK_STACK};
                  font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]};
                  font-size: {label_size + 2}px; line-height: 1.15;
                  text-transform: uppercase; color: {s["text"]};
                  overflow-wrap: break-word; }}
  .chain-arrow {{ flex: 0 0 auto; align-self: flex-start; color: {O};
                  margin-left: {gap // 2 + icon_size // 2}px;
                  width: {round(label_size * 1.2)}px;
                  height: {round(label_size * 1.5)}px; }}
  .chain-arrow-svg {{ width: 100%; height: 100%;
                      filter: drop-shadow(0 0 12px {_rgba(O, 0.45)}); }}
  /* §20: «слишком много приложений → смартфон с набором приложений».
     Плитки — её же line-иконки в её же плашке; ни одного чужого логотипа. */
  /* Ширина задана числом: корпус телефона меряется по содержимому
     (`width: max-content`), а сетка из долей внутри max-content схлопнулась бы
     в ноль — как и любой `1fr` без опоры. */
  .app-grid {{ width: {round(w * 0.30)}px; display: grid; grid-template-columns:
                 repeat({tokens.APP_GRID_COLUMNS}, 1fr); gap: 14px; padding: 22px 20px; }}
  .app-tile {{ aspect-ratio: 1; display: flex; align-items: center;
               justify-content: center; border-radius: 18px;
               background: {s["plate"]};
               border: 1px solid {_rgba(C["VIOLET"], 0.22)}; }}
  /* §8 TYPE B: «Не использовать плоский screenshot, лежащий прямоугольником
     поверх фона. Screenshot должен быть встроен в физический объект». Поэтому
     её снимок всегда лежит внутри корпуса — телефона или экрана ноутбука,
     стоящего в перспективе. Корпус нарисован CSS: изображений не сочиняем. */
  .shot {{ position: absolute; z-index: 1; right: {m["right"] // 3}px;
           top: {round(h * 0.32)}px; width: 54%;
           display: flex; justify-content: flex-end; align-items: center; }}
  .device {{ position: relative; perspective: 1800px; width: 100%; }}
  .device-body {{ position: relative; transform-style: preserve-3d;
                  width: max-content; margin-left: auto;
                  transform: rotateY(-17deg) rotateX(6deg) rotateZ(-1.5deg);
                  background: linear-gradient(145deg, {C["BG_RAISED"]} 0%,
                    {C["BG_DEEP"]} 100%);
                  border: 1px solid {_rgba(C["TEXT"], 0.12)};
                  box-shadow: {depth}, 0 0 90px {_rgba(C["VIOLET_DEEP"], 0.30)}; }}
  .device-screen {{ position: relative; overflow: hidden;
                    background: {C["BG_DEEP"]};
                    box-shadow: inset 0 0 0 1px {_rgba(C["TEXT"], 0.10)}; }}
  /* Снимок не растягивается под корпус — корпус обнимает снимок. Её решение
     «скрин это фактура, не раздувай мелкий текст» корпусом не отменяется. */
  .device-screen img {{ display: block; width: auto; height: auto;
                        object-fit: contain;
                        max-width: {round(w * 0.42)}px;
                        max-height: {round(h * 0.34)}px; }}
  /* Блик стекла — тонкая наклонная полоса, а не фигура (§14). */
  .device-glare {{ position: absolute; inset: 0; pointer-events: none;
                   background: linear-gradient(118deg, {_rgba(C["TEXT"], 0.14)} 0%,
                     transparent 34%); }}
  .device.laptop .device-body {{ border-radius: 18px; padding: 16px 16px 22px; }}
  .device.laptop .device-screen {{ border-radius: 8px; }}
  .device-hinge {{ position: absolute; left: 50%; bottom: 7px; width: 92px;
                   height: 5px; margin-left: -46px; border-radius: 3px;
                   background: {_rgba(C["TEXT"], 0.22)}; }}
  /* Основание ноутбука: та же перспектива, корпус не висит в воздухе. */
  .device-base {{ height: 16px; margin: -4px auto 0; width: 112%;
                  transform: rotateY(-17deg) rotateX(6deg) rotateZ(-1.5deg);
                  border-radius: 0 0 16px 16px;
                  background: linear-gradient(180deg, {C["BG_RAISED"]} 0%,
                    {C["BG_DEEP"]} 100%);
                  box-shadow: 0 26px 50px {_rgba(C["BG_DEEP"], 0.75)}; }}
  .device.phone .device-body {{ border-radius: 54px; padding: 14px;
                                width: max-content; margin-left: auto; }}
  .device.phone .device-screen {{ border-radius: 42px; }}
  /* Телефон вертикальный: под него потолок ноутбука не годится. Корпус встаёт
     во всю правую половину и уходит за нижний край — её §8 TYPE B прямо
     просит объект в перспективе, а не марку посреди пустого поля. */
  .shot .device.phone .device-screen img {{ max-width: {round(w * 0.40)}px;
                                            max-height: {round(h * 0.50)}px; }}
  .canvas.scene .shot.phone-shot {{ top: {round(h * 0.28)}px; }}
  .device-notch {{ position: absolute; top: 24px; left: 50%; width: 104px;
                   height: 20px; margin-left: -52px; border-radius: 999px;
                   background: {C["BG_DEEP"]}; z-index: 2; }}
  /* §8 TYPE D: несколько интерфейсных карточек в перспективе, на разных
     уровнях, частично перекрываются и темнеют вдали. */
  .screens {{ position: absolute; z-index: 1; top: {round(h * 0.18)}px;
              right: {m["right"] // 4}px;
              width: {round(w * 0.54)}px; height: {round(h * 0.70)}px; }}
  .screen-card {{ position: absolute; width: {round(w * 0.40)}px; }}
  .screen-card.s1 {{ top: {SCREEN_SLOTS[0]["top"]}; right: {SCREEN_SLOTS[0]["right"]};
                     z-index: 1; transform: rotate({SCREEN_SLOTS[0]["rot"]}deg)
                     scale(0.92); filter: brightness(0.66) blur(1.6px); }}
  .screen-card.s2 {{ top: {SCREEN_SLOTS[1]["top"]}; right: {SCREEN_SLOTS[1]["right"]};
                     z-index: 2; transform: rotate({SCREEN_SLOTS[1]["rot"]}deg)
                     scale(0.82); filter: brightness(0.82); }}
  .screen-card.s3 {{ top: {SCREEN_SLOTS[2]["top"]}; right: {SCREEN_SLOTS[2]["right"]};
                     z-index: 3; transform: rotate({SCREEN_SLOTS[2]["rot"]}deg)
                     scale(0.78); filter: brightness(1); }}
  /* Одна карточка активна — оранжевая обводка (её §8 TYPE D). */
  .screen-card.live .device-body {{ border-color: {O};
                                    box-shadow: {depth}, 0 0 70px {_rgba(O, 0.45)}; }}
  /* Стопка раскладывается по числу снимков: один — по центру сцены. */
  .screens.n1 .s1 {{ top: 20%; right: 6%; filter: brightness(1); }}
  .screens.n2 .s1 {{ top: 0%; }}
  .screens.n2 .s2 {{ top: 40%; }}
  .canvas.screens-scene .hero, .canvas.screens-scene .lead {{ max-width: 46%; }}
  /* §8 TYPE A: человек занимает правые 40–55% кадра. Колонка портрета стоит
     у правого края и её ширина задана числом, а не «половиной с полем»:
     от неё же считается, сколько остаётся тексту. «Фото может уходить за
     границу кадра» — поэтому по высоте портрет не ужимается. */
  .portrait {{ position: absolute; z-index: 1; right: 0; bottom: 0;
               width: {portrait_w}px; height: {round(h * 0.86)}px;
               display: flex; align-items: flex-end; justify-content: flex-end; }}
  /* Кромка выреза узкая: она растворяет край в фоне, а не съедает треть
     портрета (до таска 11 маска гасила всё левее 62% — фото читалось мелким). */
  /* Кадр заполняет колонку целиком и уходит за нижний край — её §8 TYPE A
     это прямо разрешает. `contain` оставлял сверху пустую треть, и портрет
     читался мелким: именно это она и назвала («сделай фото масштабнее»). */
  .portrait-img {{ width: 100%; height: 100%; object-fit: cover;
                   object-position: 50% 6%;
                   -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 14%,
                     #000 100%), linear-gradient(270deg, #000 0%, #000 {portrait_fade}%,
                     transparent 100%);
                   -webkit-mask-composite: source-in;
                   mask-image: linear-gradient(180deg, transparent 0%, #000 14%, #000 100%),
                     linear-gradient(270deg, #000 0%, #000 {portrait_fade}%, transparent 100%);
                   mask-composite: intersect; }}
  /* Текст и плашка живут в своей колонке: портрет им не сосед, а стена.
     Не хватает места — ужимается колонка текста, а не человек (таск 11 п.1). */
  .canvas.portrait-scene .lead, .canvas.portrait-scene .summary,
  .canvas.portrait-scene .stage, .canvas.portrait-scene .footer,
  .canvas.portrait-scene .rule-accent {{ max-width: {text_col}px; }}
  /* Плашка-сноска её слайда 04: оранжевый кружок `!`, вертикальная черта,
     первая строка белая, вторая сиреневая. */
  .summary {{ position: relative; z-index: 2; display: flex; align-items: center;
              gap: {gap // 2}px; border-radius: {tokens.PLATE_RADIUS}px;
              background: {s["plate"]};
              border: 1px solid {s["plate_border"]};
              padding: {gap // 2}px {gap}px; margin: {gap}px 0 {gap // 2}px;
              box-shadow: {depth}; }}
  /* §13 допускает тонкую обводку, §8 TYPE D — оранжевый outline на активном
     блоке: плашка-вывод может звучать громче остальных (таск 11 п.8). */
  .summary.accent {{ border-color: {tokens.ACCENT["ORANGE_ACCENT"]};
                     box-shadow: {depth}, 0 0 60px {_rgba(O, 0.30)}; }}
  .summary-mark {{ flex: 0 0 auto; width: {icon_size + 18}px; height: {icon_size + 18}px;
                   border-radius: 50%; border: {tokens.BORDER_WIDTH}px solid {O};
                   color: {O}; font-size: {label_size + 6}px;
                   line-height: {icon_size + 14}px; text-align: center; }}
  .summary-divider {{ flex: 0 0 auto; width: {tokens.BORDER_WIDTH}px;
                      height: {icon_size + 18}px; background: {_rgba(s["text"], 0.22)}; }}
  .summary-line {{ font-weight: {tokens.FONT_WEIGHTS["BODY"]}; font-size: {summary_size}px;
                   line-height: 1.45; color: {s["text"]}; }}
  .summary-line.accent {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
                          color: {s["accent_soft"]}; }}
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
  /* На обложке справа стоит человек: пометка над его лицом нечитаема. Уводим
     её в свободную левую колонку под заголовком — там §18 и просит «минимум
     мелкого текста», а места ровно столько, сколько нужно одной строке. */
  .canvas.cover-scene .at-top-right {{ top: {round(h * 0.50)}px; right: auto;
                                       left: {m["left"]}px;
                                       justify-content: flex-start; }}
  .canvas.cover-scene .at-top-right .hand-arrow {{ transform: none; }}
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
    #: §18 «Минимум мелкого текста»: обложка может обойтись без верхней панели.
    #: На внутренних слайдах §7 её оставляет — снимается она только по просьбе.
    header_block = f'<div class="header">{header_html}</div>' if header else ""
    words = [accent_word] if isinstance(accent_word, str) else list(accent_word or [])
    hero_lines = _lines(hook) or [str(hook)]
    hero_html = "".join(
        f'<div class="hero-line">{_mark_accent(_quotes(line), words)}</div>'
        for line in hero_lines
    )
    lead_lines = _wrap_words(_lines(body), tokens.BODY_WORDS_PER_LINE[1])
    lead_html = (
        '<p class="lead">' + "<br>".join(_t(line) for line in lead_lines) + "</p>"
        if lead_lines
        else ""
    )

    # Пометка — комментарий сбоку, а не повтор того, что на слайде уже
    # написано: сверяем со всем текстом кадра, а не только с заголовком.
    said = [hook, body, summary]
    said += [str(s.get("caption", "")) for s in (steps or [])]
    said += [str(c.get("title", "")) for c in (flow or []) + (cards or [])]
    said += [
        str(c.get("title", "") if isinstance(c, dict) else c) for c in (chain or [])
    ]
    hand_html = _hand_html(handwritten, said=said)
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
        loud = " accent" if summary_accent else ""
        summary_html = (
            f'<div class="summary{loud}">'
            '<div class="summary-mark">!</div>'
            '<div class="summary-divider"></div>'
            f'<div class="summary-body">{rows}</div></div>'
        )

    markup = f"""<div class="canvas{scene} type-{kind.lower()}" id="slide" data-composition="{kind}">
  <div class="light"></div>
  <div class="surface"></div>
  {portrait_html}
  {shot_html}
  {screens_html}
  {header_block}
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
    return _document(f"Слайд {index}", w, h, css, markup, padding=pad)


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
