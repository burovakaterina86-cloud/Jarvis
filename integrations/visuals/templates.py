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
    "gear": '<circle cx="12" cy="12" r="3"/>'
            '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    "spark": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
    "hourglass": '<path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 0M8 21c0-5 8-5 8 0"/>',
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
#: всегда. Имя не дали или оно незнакомое — ставим нейтральный геометрический
#: маркер (DESIGN.md §15), а не пустое место.
DEFAULT_STEP_ICON = "dot"

#: Стрелка между карточками — её знак из эталонных слайдов.
ARROW = "→"

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


def _steps_html(steps: list, icon_size: int, stroke: str) -> str:
    """Цепочка шагов: кружки с номерами на линии, иконка, подпись, пояснение."""
    cells = []
    for i, step in enumerate(steps, start=1):
        icon = _icon(step.get("icon", ""), icon_size, stroke) or _icon(
            DEFAULT_STEP_ICON, icon_size, stroke
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
    return (
        '<div class="steps"><div class="steps-row">'
        '<div class="steps-line"></div>' + "".join(cells) + "</div></div>"
    )


def _flow_html(flow: list, icon_size: int, stroke: str, accent_stroke: str) -> str:
    """Поток карточек со стрелками; последняя залита акцентом."""
    parts = []
    last = len(flow) - 1
    for i, card in enumerate(flow):
        if i:
            parts.append(f'<div class="flow-arrow">{ARROW}</div>')
        accent = " accent" if i == last and card.get("accent", True) else ""
        icon = _icon(card.get("icon", ""), icon_size, accent_stroke if accent else stroke)
        note = card.get("note", "")
        parts.append(
            f'<div class="flow-card{accent}">{icon}'
            f'<div class="flow-title headline">{_t(card.get("title", ""))}</div>'
            + (f'<div class="flow-note">{_t(note)}</div>' if note else "")
            + "</div>"
        )
    return '<div class="flow">' + "".join(parts) + "</div>"


def _cards_html(cards: list, icon_size: int, stroke: str, accent_stroke: str) -> str:
    """Сетка карточек со скруглением."""
    columns = 2 if len(cards) <= 4 else 3
    cells = []
    for card in cards:
        accent = " accent" if card.get("accent") else ""
        icon = _icon(card.get("icon", ""), icon_size, accent_stroke if accent else stroke)
        note = card.get("note", "")
        cells.append(
            f'<div class="card{accent}">{icon}'
            f'<div class="card-title headline">{_t(card.get("title", ""))}</div>'
            + (f'<div class="card-note">{_t(note)}</div>' if note else "")
            + "</div>"
        )
    return (
        f'<div class="cards" style="grid-template-columns: repeat({columns}, 1fr);">'
        + "".join(cells)
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
    thesis: str = "",
    footer_thesis: str = "",
    steps: list = None,
    flow: list = None,
    cards: list = None,
    summary: str = "",
    handwritten: str = "",
    photo=None,
    screenshot=None,
    notes: list = None,
) -> str:
    """Слайд карусели 1080×1350 в плотности её эталона (`reference/1–4.webp`).

    Зоны: шапка `NN | РУБРИКА` + тезис, заголовок, подзаголовок, тело с графикой,
    нижняя плашка-итог, подвал `NN/NN`.

    `steps` / `flow` / `cards` — графические блоки; не переданы — собираются из
    текста слайда (`auto_blocks`). `photo` и `screenshot` — файлы владелицы:
    файла нет → слайд собирается без него, а в `notes` ложится строка об этом.
    Рукописная строка ставится только на первом и последнем слайде.
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
    dot = round(label_size * 3.5)
    icon_size = round(label_size * 2)
    gap = tokens.SAFE_ZONE // 2
    inner = w - 2 * tokens.SAFE_ZONE
    # Объём набирается слоями, как в её примерах (reference/2.webp, 3.webp):
    # светлая обводка по верхнему краю, тёмная по нижнему, мягкая тень под блоком.
    depth = (
        f'inset 0 2px 0 {_rgba(s["text"], 0.10)}, '
        f'inset 0 -2px 0 {_rgba(P["BG_DARK_PRIMARY"], 0.45)}, '
        f'0 24px 48px {_rgba(P["BG_DARK_PRIMARY"], 0.55)}'
    )
    node_glow = f'0 0 64px {_rgba(s["accent"], 0.55)}'

    if not (steps or flow or cards):
        derived = auto_blocks(body)
        steps = derived.get("steps")
        flow = derived.get("flow")
        cards = derived.get("cards")
        if derived:
            body = ""

    css = f"""
  .canvas {{ background: {s["bg"]}; color: {s["text"]}; }}
  .glow {{ position: absolute; border-radius: 50%; pointer-events: none;
           width: 900px; height: 900px; top: -300px; right: -260px;
           background: {_glow(s["accent"], 0.28)}; }}
  .glow-2 {{ position: absolute; border-radius: 50%; pointer-events: none;
             width: 760px; height: 760px; bottom: -320px; left: -280px;
             background: {_glow(P["LAVENDER"], 0.18)}; }}
  .header {{ position: relative; z-index: 2; display: flex; align-items: flex-start;
             justify-content: space-between; gap: {gap}px; }}
  .header-left {{ display: flex; align-items: center; gap: 20px; }}
  .header-num {{ font-size: {label_size}px; line-height: {label_lh};
                 color: {s["accent_soft"]}; }}
  .header-rule {{ width: {tokens.BORDER_WIDTH}px; height: {label_size}px;
                  background: {_rgba(s["text"], 0.38)}; }}
  .header-rubric {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {micro_size}px;
                    line-height: {micro_lh}; letter-spacing: 0.16em;
                    text-transform: uppercase; color: {s["muted"]}; }}
  .header-thesis {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {micro_size}px;
                    line-height: 1.5; letter-spacing: 0.16em; text-align: right;
                    text-transform: uppercase; color: {s["muted"]}; }}
  .hero {{ position: relative; z-index: 2; margin-top: {gap}px;
           font-size: {hook_size}px; line-height: {hook_lh};
           letter-spacing: -0.01em; text-transform: uppercase; color: {s["text"]};
           margin-bottom: {gap // 2}px; }}
  .hero .accent, .hero em {{ font-style: normal; color: {s["accent_soft"]}; }}
  .lead {{ position: relative; z-index: 2; font-weight: {tokens.FONT_WEIGHTS["BODY"]};
           font-size: {body_size}px; line-height: {body_lh}; color: {s["muted"]};
           margin-top: {gap // 2}px; max-width: {inner}px; }}
  .stage {{ position: relative; z-index: 2; flex: 1; display: flex;
            flex-direction: column; justify-content: center; gap: {gap}px;
            padding-bottom: {gap // 2}px; }}
  /* Графики нет — вертикаль между заголовком и подвалом не оставляем дырой:
     заголовок сам занимает тело слайда. */
  .hero.fill {{ flex: 1; display: flex; flex-direction: column; justify-content: center; }}
  .steps {{ position: relative; flex: 1; display: flex;
            flex-direction: column; justify-content: center; }}
  .steps-line {{ position: absolute; left: {dot // 2}px; right: {dot // 2}px;
                 top: {dot // 2 - 2}px; height: 4px; background: {_rgba(s["accent"], 0.55)}; }}
  .steps-row {{ position: relative; display: flex; justify-content: space-between;
                align-items: flex-start; gap: 16px; }}
  .step {{ flex: 1; text-align: center; }}
  .step-dot {{ width: {dot}px; height: {dot}px; border-radius: 50%;
               margin: 0 auto; background: {s["accent_soft"]}; color: {P["TEXT_ON_LIGHT"]};
               font-size: {label_size + 8}px; line-height: {dot}px;
               box-shadow: {node_glow}; }}
  .step-icon {{ margin: 44px auto 18px; height: {icon_size}px; }}
  .step-caption {{ font-family: '{tokens.FONTS["HEADLINE"]}', {tokens.FALLBACK_STACK};
                   font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]};
                   font-size: {label_size + 5}px; line-height: 1.15; color: {s["text"]};
                   min-height: {round((label_size + 5) * 1.15 * 2)}px; }}
  .step-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 14px;
                color: {s["muted"]}; }}
  .flow {{ flex: 1; display: flex; align-items: stretch; gap: 14px; }}
  .flow-card {{ flex: 1; border-radius: {tokens.RADIUS["card"]}px;
                background: {s["surface"]}; border: {tokens.BORDER_WIDTH}px solid
                {_rgba(s["accent"], 0.28)}; padding: {gap // 2}px;
                box-shadow: {depth}; }}
  .flow-card.accent {{ background: {P["LAVENDER"]}; border-color: {s["accent"]};
                       box-shadow: {node_glow}; }}
  .flow-card.accent .flow-title, .flow-card.accent .flow-note {{ color: {P["TEXT_ON_LIGHT"]}; }}
  .flow-title {{ font-size: {label_size + 3}px; line-height: 1.15; margin-top: 18px;
                 text-transform: uppercase; color: {s["text"]}; }}
  .flow-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 10px;
                color: {s["muted"]}; }}
  .flow-arrow {{ align-self: center; font-size: {label_size + 6}px; color: {s["accent_soft"]}; }}
  .cards {{ flex: 1; display: grid; gap: 16px; grid-auto-rows: 1fr; }}
  .card {{ border-radius: {tokens.RADIUS["card"]}px; background: {s["surface"]};
           border: {tokens.BORDER_WIDTH}px solid {_rgba(s["accent"], 0.28)};
           padding: {gap // 2}px; box-shadow: {depth};
           display: flex; flex-direction: column; justify-content: center; }}
  .card.accent {{ background: {P["LAVENDER"]}; border-color: {s["accent"]};
                  box-shadow: {node_glow}; }}
  .card.accent .card-title, .card.accent .card-note {{ color: {P["TEXT_ON_LIGHT"]}; }}
  .card-title {{ font-size: {label_size + 3}px; line-height: 1.15; margin-top: 16px;
                 text-transform: uppercase; color: {s["text"]}; }}
  .card-note {{ font-size: {micro_size}px; line-height: {micro_lh}; margin-top: 10px;
                color: {s["muted"]}; }}
  .shot {{ flex: 1; display: flex; justify-content: center; align-items: center; }}
  .shot-img {{ max-width: 100%; max-height: 560px; width: auto; height: auto;
               object-fit: contain; border-radius: {tokens.RADIUS["card"]}px;
               border: {tokens.BORDER_WIDTH}px solid {_rgba(s["accent"], 0.38)};
               box-shadow: 0 0 64px {_rgba(s["accent"], 0.35)}; }}
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
  .summary {{ position: relative; z-index: 2; display: flex; align-items: center;
              gap: 24px; border-radius: {tokens.RADIUS["card"]}px;
              background: {_rgba(s["accent"], 0.16)};
              border: {tokens.BORDER_WIDTH}px solid {_rgba(s["accent"], 0.38)};
              padding: {gap // 2}px {gap}px; margin-bottom: {gap // 2}px;
              box-shadow: {depth}; }}
  .summary-text {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {label_size}px;
                   line-height: {label_lh}; letter-spacing: 0.1em;
                   text-transform: uppercase; color: {s["accent_soft"]}; }}
  .footer {{ position: relative; z-index: 2; display: flex; align-items: flex-end;
             justify-content: space-between; gap: {gap}px; }}
  .footer-thesis {{ font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]}; font-size: {micro_size}px;
                    line-height: 1.5; letter-spacing: 0.16em; text-transform: uppercase;
                    color: {s["muted"]}; }}
  .footer-num {{ font-size: {micro_size}px; line-height: {micro_lh};
                 letter-spacing: 0.08em; color: {s["muted"]}; }}
  .hand {{ position: relative; z-index: 3; text-align: right;
           margin-bottom: {gap}px;
           font-family: '{tokens.HAND_FONT}', {tokens.HAND_FALLBACK};
           font-size: {hook_size // 2}px; line-height: 1.2; color: {s["accent_soft"]}; }}
"""

    rubric = _rubric(label)
    head_left = f'<span class="header-num headline">{index:02d}</span>'
    if rubric:
        head_left += (
            '<span class="header-rule"></span>'
            f'<span class="header-rubric">{_t(rubric)}</span>'
        )
    thesis_html = "<br>".join(_t(line) for line in _lines(thesis, 2))
    hero_lines = _lines(hook) or [str(hook)]
    hero_html = "<br>".join(
        _t(_quotes(line)) if i % 2 == 0 else f'<span class="accent">{_t(_quotes(line))}</span>'
        for i, line in enumerate(hero_lines)
    )
    lead_html = f'<p class="lead">{_t(body)}</p>' if body else ""

    stroke, accent_stroke = s["accent_soft"], P["VIOLET_STRONG"]
    stage = []
    if steps:
        stage.append(_steps_html(steps, icon_size, stroke))
    if flow:
        stage.append(_flow_html(flow, icon_size, stroke, accent_stroke))
    if cards:
        stage.append(_cards_html(cards, icon_size, stroke, accent_stroke))
    shot = _image_block("shot", screenshot, "скриншот владелицы", notes)
    if shot:
        stage.append(f'<div class="shot">{shot}</div>')
    stage_html = f'<div class="stage">{"".join(stage)}</div>' if stage else ""
    hero_fill = "" if stage else " fill"

    summary_html = ""
    if summary:
        summary_html = (
            f'<div class="summary">{_icon("bolt", icon_size, s["accent_soft"])}'
            f'<span class="summary-text">{_t(summary)}</span></div>'
        )

    portrait = _image_block("portrait", photo, "фото владелицы", notes)
    portrait_html = f'<div class="portrait">{portrait}</div>' if portrait else ""

    hand_html = ""
    if handwritten:
        if index == 1 or index == total:
            hand_html = f'<div class="hand">{_t(handwritten)}</div>'
        else:
            notes.append(
                f"рукописная строка только на первом и последнем слайде — "
                f"на {index}-м не ставлю"
            )

    markup = f"""<div class="canvas" id="slide">
  <div class="glow"></div>
  <div class="glow-2"></div>
  {portrait_html}
  <div class="header">
    <div class="header-left">{head_left}</div>
    <div class="header-thesis">{thesis_html}</div>
  </div>
  <div class="hero headline{hero_fill}">{hero_html}</div>
  {lead_html}
  {stage_html}
  {hand_html}
  {summary_html}
  <div class="footer">
    <div class="footer-thesis">{"<br>".join(_t(l) for l in _lines(footer_thesis, 2))}</div>
    <div class="footer-num headline">{index:02d}/{total:02d}</div>
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
