"""Токены дизайн-системы ESSA.AI.

Единственный источник — файлы владелицы, ничего не придумано:
- палитра и начертания: `essa-ai/DESIGN.md` §COLOR BASE, §TYPOGRAPHY
  (продублированы в `essa-ai/POST_COVERS.md` и §10 `SKILL_carousel-instagram.md`);
- типографическая шкала и safe zone: `essa-ai/DESIGN.md` §10, §11;
- холсты: `essa-ai/DESIGN.md` §11 (1080×1350) и §18 (1080×1920);
- подключение шрифтов — строка `<link>` из её же вёрстки
  `essa-ai/visual_references/design-code-studio_essa_ai-v1.html`.

Если `DESIGN.md` обновится — правится этот файл, а не разметка.
"""

#: Core palette — 12 цветов, DESIGN.md §COLOR BASE.
PALETTE = {
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

#: Supporting color — используется редко и не как второй фирменный акцент.
OPTIONAL = {"COOL_BLUE_OPTIONAL": "#7ABAE6"}

#: Роли начертаний, DESIGN.md §TYPOGRAPHY. Третий фирменный шрифт запрещён.
FONTS = {
    "HEADLINE": "Roboto Condensed",  # Bold — заголовки, hooks, крупные цифры
    "BODY": "Open Sans",             # Regular — основной текст
    "SUPPORT": "Open Sans",          # SemiBold — подзаголовки, labels
}

#: Семейства, которые разрешено подключать как текстовые. Ровно два.
FONT_FAMILIES = ("Roboto Condensed", "Open Sans")

#: Рукописная подпись — отдельное решение владелицы (2026-09-21: «моя фишка:
#: рукописный тезис»). В её собственной вёрстке
#: `visual_references/design-code-studio_essa_ai-v1.html` это `Marck Script`
#: со стеком `cursive` и цветом VIOLET_SOFT. Используется ровно на одну строку
#: и текстовым шрифтом системы не является.
HAND_FONT = "Marck Script"
HAND_FALLBACK = "cursive"

#: Начертания, которые используются в вёрстке.
FONT_WEIGHTS = {"HEADLINE": 700, "BODY": 400, "SUPPORT": 600}

#: Google Fonts — строка из её собственной вёрстки, целиком, вместе с Marck Script.
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Roboto+Condensed:wght@400;700"
    "&family=Open+Sans:wght@400;600;700"
    "&family=Marck+Script"
    "&display=swap"
)

#: Хост, по которому проверяется доступность шрифтов.
GOOGLE_FONTS_HOST = "fonts.googleapis.com"

#: Стек подстановки — ровно тот, что стоит в её вёрстке: `sans-serif`.
FALLBACK_STACK = "sans-serif"

#: Холсты. DESIGN.md §11 и §18.
CANVAS = {
    "carousel": (1080, 1350),
    "cover": (1080, 1350),
    "story": (1080, 1920),
}

#: Safe zone 72–88 px, базовый ориентир 80 px (DESIGN.md §11).
SAFE_ZONE = 80
SAFE_ZONE_RANGE = (72, 88)

#: Типографическая шкала карусели, DESIGN.md §10.
#: Значения — середина её рабочих диапазонов, сами диапазоны рядом.
TYPE_SCALE = {
    # line_height — верх её диапазона 0.92–1.02: ниже единицы строки с
    # выносными («у», «р», «д», «Щ») накладываются друг на друга.
    "hook": {"range": (88, 120), "size": 104, "line_height": 1.02},
    # size — верх её диапазона: в присланных эталонных слайдах заголовок
    # занимает две строки во всю ширину, а не треть кадра.
    "slide_title": {"range": (60, 84), "size": 84, "line_height": 1.08},
    "body": {"range": (34, 42), "size": 38, "line_height": 1.42},
    "label": {"range": (24, 30), "size": 27, "line_height": 1.2},
    "micro": {"range": (22, 24), "size": 24, "line_height": 1.3},
}

#: Нижняя граница межстрочного расстояния для кириллицы.
#: При line-height < 1 выносные элементы строки задевают соседнюю.
MIN_LINE_HEIGHT = 1.0

#: Карточки и плашки, DESIGN.md §14: рабочий radius 16–28 px, рамки 1–2 px.
RADIUS_RANGE = (16, 28)
RADIUS = {"card": 24, "chip": 20, "pill": 999}
BORDER_WIDTH = 2

#: Стили карусели, разрешённые §5 SKILL_carousel-instagram.md.
STYLES = ("STYLE_01", "STYLE_02_LIGHT", "STYLE_02_DARK")

#: Тёмный и светлый полюса чередования (её слайды: тёмный/светлый попеременно,
#: первый и последний — тёмные, с фото).
DARK_STYLE = "STYLE_01"
LIGHT_STYLE = "STYLE_02_LIGHT"

#: Выбор стиля по функции материала, §6 того же файла.
DEFAULT_STYLE = "STYLE_02_LIGHT"


def alternating_styles(total: int) -> tuple:
    """Порядок стилей на всю карусель: тёмный и светлый попеременно.

    Задаётся один раз на карусель, а не подбирается для каждого слайда.
    Первый и последний слайды — тёмные: это слайды с её фото.
    """
    if total <= 0:
        return ()
    seq = [DARK_STYLE if i % 2 == 0 else LIGHT_STYLE for i in range(total)]
    seq[-1] = DARK_STYLE
    return tuple(seq)


def font_stack(role: str) -> str:
    """CSS-стек для роли: фирменный шрифт плюс её же `sans-serif`."""
    return f"'{FONTS[role]}', {FALLBACK_STACK}"
