"""Редакционная карусель 1080×1350 по её эталону «стиль 2».

    python -m integrations.visuals.editorial <папка комплекта> [slides.json]

Её решение 2026-09-25 (после «слайд первый ужасен… почему всегда одинаковая структура»):
- эталон — `essa-ai/visual_references/карусель стиль 2/`: крупный узкий заголовок капсом (Oswald), текст — Open Sans,
  акцент **фиолетовый** (оранжевого нет — её `SKILL_carousel-instagram.md` §19–§20);
- фоны тёмный / светлый **чередуются**;
- плашки, стрелки, иконки; воздуха не слишком много (кроме обложки-хука);
- её фото — на первом и последнем слайде, **на весь кадр**, текст поверх затемнения.

Типы слайдов — её «visual types» из §14: `photo`, `statement`, `text`, `steps`, `cards`,
`compare`. Акцент в любом тексте — `[[слова]]`, полужирный в теле — `**слова**`.
Перед сборкой — проверка ритма (§14): два фото подряд и одинаковый тип рядом — в отчёт.
После сборки — общий лист `visuals/contact-sheet.png` для проверки всей карусели (§17).

Формат `slides.json`: `{"slides": [{"type": …, "label": …, "hook": …, …}, …]}`;
у слайда можно задать `"bg": "dark"|"light"`, иначе фон чередуется с тёмного.
"""
from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path

from . import render, templates, tokens

W, H = tokens.CANVAS["carousel"]
PAD_X, PAD_TOP, PAD_BOTTOM = 68, 60, 72
INNER = W - 2 * PAD_X

#: Шрифты те же два (её DESIGN.md), но заголовку нужен вес 800 — как в её эталоне.
#: Её решение 2026-09-25: заголовки — Oswald, текст — Open Sans.
FONTS_URL = ("https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700"
             "&family=Open+Sans:wght@400;600;700&display=swap")

#: Средняя ширина знака Oswald 600 капсом в долях кегля (с запасом).
CAPS_ADVANCE = 0.52

P, C = tokens.PALETTE, tokens.CAROUSEL_PALETTE
THEMES = {
    "dark": {
        "bg": f"linear-gradient(160deg, {P['BG_DARK_SECONDARY']} 0%, {P['BG_DARK_PRIMARY']} 55%, #16131F 100%)",
        "text": P["TEXT_ON_DARK"], "muted": P["TEXT_MUTED_DARK"],
        "accent": C["VIOLET"], "accent2": P["VIOLET_PRIMARY"],
        "plate": "rgba(255,255,255,0.045)", "plate_border": "rgba(167,123,255,0.45)",
        "num_bg": "#3A2A6B", "rule": "rgba(167,123,255,0.55)",
    },
    "light": {
        "bg": f"linear-gradient(160deg, {P['BG_LIGHT_PRIMARY']} 0%, {P['BG_LIGHT_SECONDARY']} 100%)",
        "text": P["TEXT_ON_LIGHT"], "muted": P["TEXT_MUTED_LIGHT"],
        "accent": P["VIOLET_STRONG"], "accent2": P["VIOLET_PRIMARY"],
        "plate": "#FFFFFF", "plate_border": "rgba(89,45,226,0.35)",
        "num_bg": P["VIOLET_PRIMARY"], "rule": "rgba(89,45,226,0.45)",
    },
}

TYPES = ("photo", "statement", "text", "steps", "cards", "compare")
PHOTO_TYPES = {"photo"}


def theme_for(slide: dict, index: int) -> str:
    """Её правило: тёмный и светлый по очереди, начиная с тёмного; `bg` у слайда главнее."""
    return slide.get("bg") or ("dark" if index % 2 == 1 else "light")


def fit_headline(lines: list[str], width: int, max_size: int, min_size: int = 44) -> int:
    """Кегль, при котором самая длинная строка встаёт в ширину целиком."""
    longest = max((len(re.sub(r"\[\[|\]\]", "", l)) for l in lines), default=1)
    return max(min_size, min(max_size, int(width / (CAPS_ADVANCE * longest))))


def _rich(text: str) -> str:
    """`[[акцент]]` → фиолетовый, `**жирный**` → полужирный, `\\n` → перенос."""
    t = escape(str(text))
    t = re.sub(r"\[\[(.+?)\]\]", r'<span class="acc">\1</span>', t, flags=re.S)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    return t.replace("\n", "<br>")


#: Свои line-иконки редакционной карусели сверх общего набора `templates.ICONS`.
EXTRA_ICONS = {
    "arrow-down": '<path d="M12 4v15"/><path d="M6 13l6 6 6-6"/>',
    "arrow-right": '<path d="M4 12h15"/><path d="M13 6l6 6-6 6"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6"/><path d="M12 16.5v.5"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
}


def _icon(name: str, size: int, color: str) -> str:
    path = (EXTRA_ICONS.get(name) or templates.ICONS.get(name)
            or templates.ICONS[templates.DEFAULT_STEP_ICON])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')


def _header(index: int, total: int, label: str) -> str:
    return (f'<div class="head"><span class="cnt"><b>{index:02d}</b> / {total:02d}</span>'
            f'<span class="line"></span><span class="lbl">{escape(label.upper())}</span></div>')


def _headline(hook: str, width: int, max_size: int) -> str:
    lines = str(hook).split("\n")
    size = fit_headline(lines, width, max_size)
    return f'<h1 style="font-size:{size}px">{_rich(hook)}</h1>'


def _photo_src(path: str, notes: list) -> str | None:
    p = Path(path)
    if not p.is_file():
        notes.append(f"нет файла фото: {path}")
        return None
    return p.resolve().as_uri()


def build_slide(slide: dict, index: int, total: int, theme: str, notes: list | None = None) -> str:
    notes = notes if notes is not None else []
    kind = slide.get("type", "text")
    if kind not in TYPES:
        raise ValueError(f"тип слайда {kind!r} не из её §14; допустимы: {', '.join(TYPES)}")
    t = THEMES["dark" if kind == "photo" else theme]
    label = slide.get("label", "")
    head = "" if slide.get("header") is False else _header(index, total, label)
    body = f'<p class="body">{_rich(slide["body"])}</p>' if slide.get("body") else ""
    rule = '<div class="rule"></div>'
    parts = []

    if kind == "photo":
        src = _photo_src(slide.get("photo", ""), notes)
        focus = slide.get("focus", "70% 30%")
        # сдвиг и приближение кадра: человек уходит вправо, текст не ложится на лицо (её §11)
        zoom, shift = float(slide.get("zoom", 1)), float(slide.get("shift_x", 0))
        move = f"transform:scale({zoom}) translateX({shift}%);" if zoom != 1 or shift else ""
        img = f'<img class="bg-photo" src="{src}" style="object-position:{focus};{move}">' if src else ""
        col = int(INNER * slide.get("text_width", 0.60))
        size = 118 if index == 1 else 96
        cta = (f'<div class="plate cta">{_icon(slide.get("cta_icon", "check"), 56, t["accent"])}'
               f'<div>{_rich(slide["cta"])}</div></div>') if slide.get("cta") else ""
        parts.append(f'{img}<div class="shade"></div>{head}'
                     f'<div class="photo-col" style="width:{col}px">{_headline(slide["hook"], col, size)}'
                     f'{rule}{body}</div>{cta}')
    elif kind == "statement":
        parts.append(f'{head}<div class="center">{_headline(slide["hook"], INNER, 150)}{rule}{body}</div>')
    elif kind == "text":
        summary = ""
        if slide.get("summary"):
            a, _, b = str(slide["summary"]).partition("\n")
            summary = (f'<div class="plate summary">{_icon(slide.get("summary_icon", "alert"), 60, t["accent"])}'
                       f'<div class="sep"></div><div>{_rich(a)}<br><span class="acc">{_rich(b)}</span></div></div>')
        parts.append(f'{head}<div class="fill">{_headline(slide["hook"], INNER, 112)}{body}{rule}{summary}</div>')
    elif kind == "steps":
        items = []
        for i, st in enumerate(slide["steps"], 1):
            if i > 1:
                items.append(f'<div class="arrow-down">{_icon("arrow-down", 44, t["accent"])}</div>')
            sub = f'<div class="st-text">{_rich(st["text"])}</div>' if st.get("text") else ""
            items.append(f'<div class="step-plate"><div class="num">{i:02d}</div>'
                         f'<div><div class="st-title">{_rich(st["title"])}</div>{sub}</div></div>')
        top = _headline(slide["hook"], INNER, 84) if slide.get("hook") else ""
        parts.append(f'{head}<div class="fill">{top}<div class="steps">{"".join(items)}</div></div>')
    elif kind == "cards":
        cards = "".join(
            f'<div class="card">{_icon(c.get("icon", "spark"), 64, t["accent"])}'
            f'<div class="c-title">{_rich(c["title"])}</div>'
            + (f'<div class="c-text">{_rich(c["text"])}</div>' if c.get("text") else "") + "</div>"
            for c in slide["cards"])
        parts.append(f'{head}<div class="fill">{_headline(slide["hook"], INNER, 96)}{body}'
                     f'<div class="cards">{cards}</div></div>')
    elif kind == "compare":
        was, now = slide.get("columns", ["Было", "Стало"])
        rows = "".join(f'<div class="was">{_rich(a)}</div><div class="to">{_icon("arrow-right", 36, t["accent"])}</div>'
                       f'<div class="now">{_rich(b)}</div>' for a, b in slide["rows"])
        parts.append(f'{head}<div class="fill">{_headline(slide["hook"], INNER, 96)}{body}'
                     f'<div class="compare"><div class="ch">{escape(was)}</div><div></div>'
                     f'<div class="ch acc">{escape(now)}</div>{rows}</div></div>')

    return _document(f"{index:02d}", "".join(parts), t, kind)


def _document(title: str, inner: str, t: dict, kind: str) -> str:
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:#000; }}
.canvas {{ width:{W}px; height:{H}px; position:relative; overflow:hidden; background:{t['bg']}; color:{t['text']};
  font-family:'Open Sans', sans-serif; padding:{PAD_TOP}px {PAD_X}px {PAD_BOTTOM}px; display:flex; flex-direction:column; }}
.acc {{ color:{t['accent']}; }}
b {{ font-weight:700; }}
.head {{ display:flex; align-items:center; gap:26px; font-size:28px; position:relative; z-index:3; flex:none; }}
.cnt {{ font-family:'Oswald'; font-weight:500; color:{t['muted']}; letter-spacing:.02em; }}
.cnt b {{ color:{t['accent']}; }}
.line {{ flex:1; height:2px; background:{t['rule']}; opacity:.6; }}
.lbl {{ font-size:22px; letter-spacing:.2em; color:{t['muted']}; }}
h1 {{ font-family:'Oswald', sans-serif; font-weight:600; text-transform:uppercase; line-height:.96;
  letter-spacing:-.005em; }}
.rule {{ width:150px; height:8px; border-radius:4px; background:linear-gradient(90deg,{t['accent2']},{t['accent']}); margin:38px 0 34px; flex:none; }}
.body {{ font-size:39px; line-height:1.36; }}
.center {{ flex:1; display:flex; flex-direction:column; justify-content:center; }}
.fill {{ flex:1; display:flex; flex-direction:column; justify-content:space-evenly; padding-top:24px; }}
.fill > h1 {{ margin-bottom:6px; }}
.fill > .rule {{ margin:10px 0; }}
.plate {{ background:{t['plate']}; border:2px solid {t['plate_border']}; border-radius:28px; }}
.summary {{ display:flex; align-items:center; gap:32px; padding:34px 40px; font-size:36px; line-height:1.3; font-weight:600; }}
.summary .sep {{ width:2px; align-self:stretch; background:{t['plate_border']}; }}
.steps {{ display:flex; flex-direction:column; flex:1; justify-content:center; }}
.step-plate {{ display:flex; align-items:center; gap:34px; padding:30px 38px; border-radius:28px; background:{t['plate']};
  border:2px solid {t['plate_border']}; }}
.num {{ flex:none; width:92px; height:92px; border-radius:50%; background:{t['num_bg']}; color:#fff; display:flex;
  align-items:center; justify-content:center; font-family:'Oswald'; font-weight:600; font-size:40px;
  border:2px solid {t['accent']}; }}
.st-title {{ font-family:'Oswald'; font-weight:600; text-transform:uppercase; font-size:58px; line-height:1; }}
.st-text {{ font-size:32px; line-height:1.3; margin-top:10px; color:{t['muted']}; }}
.arrow-down {{ display:flex; justify-content:center; padding:10px 0; }}
.cards {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
.card {{ background:{t['plate']}; border:2px solid {t['plate_border']}; border-radius:28px; padding:36px 32px; min-height:250px;
  display:flex; flex-direction:column; gap:20px; }}
.c-title {{ font-family:'Oswald'; font-weight:600; text-transform:uppercase; font-size:46px; line-height:1.02; }}
.c-text {{ font-size:30px; line-height:1.3; color:{t['muted']}; }}
.compare {{ display:grid; grid-template-columns:1fr 56px 1.25fr; gap:18px 10px; align-items:stretch; }}
.ch {{ font-family:'Oswald'; font-weight:600; text-transform:uppercase; font-size:30px; letter-spacing:.12em; color:{t['muted']}; }}
.was {{ padding:24px 26px; border-radius:22px; background:{t['plate']}; color:{t['muted']}; font-size:30px; line-height:1.28;
  text-decoration:line-through; text-decoration-color:{t['plate_border']}; display:flex; align-items:center; }}
.to {{ display:flex; align-items:center; justify-content:center; }}
.now {{ padding:24px 26px; border-radius:22px; background:{t['plate']}; border:2px solid {t['accent']}; font-size:31px;
  line-height:1.28; font-weight:600; display:flex; align-items:center; }}
/* воздуха не слишком много (её слово 2026-09-25): блоки растягиваются на свободную высоту */
.k-cards .cards {{ flex:1; grid-auto-rows:1fr; margin-top:34px; }}
.k-cards .card {{ justify-content:center; }}
.k-cards .c-title {{ font-size:54px; }}
.k-cards .c-text {{ font-size:33px; }}
.k-compare .compare {{ flex:1; grid-template-rows:auto; grid-auto-rows:1fr; margin-top:26px; }}
.k-compare .was, .k-compare .now {{ font-size:35px; padding:28px 30px; }}
.k-compare .fill, .k-cards .fill {{ justify-content:flex-start; }}
.k-statement .body, .k-text .body {{ font-size:43px; line-height:1.34; }}
.k-text .summary {{ font-size:40px; padding:40px 44px; }}
.k-text h1 {{ margin-bottom:34px; }}
.bg-photo {{ position:absolute; inset:0; width:100%; height:100%; object-fit: cover; z-index:0; }}
.shade {{ position:absolute; inset:0; z-index:1; background:
  linear-gradient(90deg, rgba(13,16,21,.92) 0%, rgba(13,16,21,.78) 36%, rgba(13,16,21,.18) 64%, rgba(13,16,21,0) 80%),
  linear-gradient(0deg, rgba(13,16,21,.55) 0%, rgba(13,16,21,0) 30%),
  linear-gradient(180deg, rgba(13,16,21,.6) 0%, rgba(13,16,21,0) 14%); }}
.photo-col {{ position:relative; z-index:2; margin-top:auto; margin-bottom:auto; }}
.photo-col .body {{ font-size:38px; }}
.cta {{ position:relative; z-index:2; display:flex; align-items:center; gap:28px; padding:30px 36px; font-size:36px;
  line-height:1.3; font-weight:600; background:rgba(13,16,21,.72); flex:none; }}
</style></head><body><div class="canvas k-{kind}">{inner}</div></body></html>"""


def rhythm_problems(slides: list[dict]) -> list[str]:
    """Её §14: не два фото подряд, не один и тот же тип на соседних слайдах."""
    out = []
    for i in range(1, len(slides)):
        a, b = slides[i - 1].get("type", "text"), slides[i].get("type", "text")
        if a in PHOTO_TYPES and b in PHOTO_TYPES:
            out.append(f"слайды {i}-{i + 1}: два фото подряд")
        elif a == b:
            out.append(f"слайды {i}-{i + 1}: одинаковый тип «{a}» рядом")
    return out


def _contact_sheet(pngs: list[Path], out: Path) -> render.RenderResult:
    cells = "".join(f'<img src="{p.resolve().as_uri()}">' for p in pngs)
    cols = 3
    rows = -(-len(pngs) // cols)
    cw = 360
    ch = round(cw * H / W)
    page = out.with_suffix(".html")
    page.write_text(f"""<!doctype html><html><body style="margin:0;background:#888">
<div style="display:grid;grid-template-columns:repeat({cols},{cw}px);gap:16px;padding:16px">
<style>img{{width:{cw}px;height:{ch}px;display:block}}</style>{cells}</div></body></html>""", encoding="utf-8")
    return render.render_image(page, out, cols * cw + (cols + 1) * 16, rows * ch + (rows + 1) * 16)


def build(folder: Path, data_file: Path | None = None) -> int:
    folder = Path(folder)
    data_file = Path(data_file) if data_file else folder / "slides.json"
    data = json.loads(data_file.read_text(encoding="utf-8"))
    slides = data["slides"]
    out = folder / "visuals"
    out.mkdir(parents=True, exist_ok=True)
    total = len(slides)
    for p in rhythm_problems(slides):
        print(f"ритм: {p}")
    pngs, failed = [], 0
    for i, slide in enumerate(slides, 1):
        slide = dict(slide)
        if slide.get("photo") and not Path(slide["photo"]).is_absolute():
            slide["photo"] = str((data_file.parent / slide["photo"]).resolve())
        notes: list = []
        html = build_slide(slide, i, total, theme_for(slide, i), notes)
        page = out / f"slide-{i:02d}.html"
        page.write_text(html, encoding="utf-8")
        res = render.render_image(page, out / f"slide-{i:02d}.png")
        state = "готов" if res.ok else f"НЕ СНЯТ ({res.error})"
        failed += 0 if res.ok else 1
        print(f"slide-{i:02d}.png — {slide.get('type', 'text')}, {theme_for(slide, i)}, {state}")
        for n in notes + res.warnings:
            print(f"  · {n}")
        if res.ok:
            pngs.append(res.png_path)
    if pngs:
        sheet = _contact_sheet(pngs, out / "contact-sheet.png")
        print(f"contact-sheet.png — {'готов' if sheet.ok else 'не снят'}")
    return 3 if failed else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    return build(Path(args[0]), Path(args[1]) if len(args) > 1 else None)


if __name__ == "__main__":
    sys.exit(main())
