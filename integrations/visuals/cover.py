"""Обложка поста 1080×1350 по её референсам и её скиллу `cover-post-katerina` (2026-09-25).

    python -m integrations.visuals.cover <папка комплекта> [cover.json]

Её слова: «обложки чередуем тёмная-светлая, с моим фото и просто с фото под пост подходящий по смыслу».
Язык — тот же, что у карусели «стиль 2» (`editorial.py`): Roboto Condensed капсом, фиолетовый акцент,
line-иконки; плюс её приметы обложки: плашка-таблетка с темой и линия, справа сверху
`ТЕСТИРУЮ / АНАЛИЗИРУЮ / УЛУЧШАЮ`, рукописный тезис терракотой, подпись капсом внизу, тонкие дуги,
узлы, сетка точек, плитки с иконками. Фото — справа, крупно, сливается с фоном (маска), без вырезки.

`cover.json`: `{"hook": "Строка\\n[[акцент]]", "pill": "тема", "hand": "рукописная\\nмысль из поста",
"support": "ПОДПИСЬ\\nВНИЗУ", "tag": "…" (иначе её строка), "icons": ["chat","doc","image"] (иначе без плиток),
"photo": "visuals/cover-photo.png", "photo_kind": "her"|"topic", "bg": "light"|"dark", "focus": "50% 20%"}`.
`bg` и `photo_kind` не заданы — чередуются относительно прошлой обложки (`essa-ai/content/.last-cover.json`).
Выход: `visuals/cover.png` (+ `.html`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import render, tokens
from .editorial import _icon, _rich, fit_headline

W, H = tokens.CANVAS["carousel"]
ROOT = Path(__file__).resolve().parents[2]
LAST = Path("essa-ai") / "content" / ".last-cover.json"
P, C = tokens.PALETTE, tokens.CAROUSEL_PALETTE
FONTS_URL = ("https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@700;800"
             "&family=Open+Sans:wght@400;600&family=Marck+Script&display=swap")
DEFAULT_TAG = "ТЕСТИРУЮ\nАНАЛИЗИРУЮ\nУЛУЧШАЮ"

THEMES = {
    "light": {
        "bg": "#F1EFFA", "bg2": "#E6E1F7", "text": P["TEXT_ON_LIGHT"], "muted": P["TEXT_MUTED_LIGHT"],
        "accent": P["VIOLET_STRONG"], "line": "rgba(113,88,231,0.55)", "hand": "#C4552A",
        "tile": "rgba(255,255,255,0.78)", "tile_border": "rgba(113,88,231,0.18)", "glow": "rgba(159,135,236,0.30)",
    },
    "dark": {
        "bg": "#0E0D14", "bg2": "#241C3F", "text": P["TEXT_ON_DARK"], "muted": P["TEXT_MUTED_DARK"],
        "accent": C["VIOLET"], "line": "rgba(167,123,255,0.55)", "hand": "#F08A4B",
        "tile": "rgba(255,255,255,0.06)", "tile_border": "rgba(167,123,255,0.30)", "glow": "rgba(113,88,231,0.42)",
    },
}


def next_choice(root: Path | str = ROOT) -> dict:
    """Чередование: светлая с её фото → тёмная с фото по смыслу → …"""
    try:
        last = json.loads((Path(root) / LAST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"bg": "light", "photo_kind": "her"}
    return {"bg": "dark" if last.get("bg") == "light" else "light",
            "photo_kind": "topic" if last.get("photo_kind") == "her" else "her"}


def remember_choice(root: Path | str, choice: dict) -> None:
    path = Path(root) / LAST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bg": choice["bg"], "photo_kind": choice["photo_kind"]}, ensure_ascii=False),
                    encoding="utf-8")


def _lines_html(text: str) -> str:
    return "<br>".join(_rich(line) for line in str(text).split("\n"))


def _decor(t: dict) -> str:
    """Тонкие дуги, узлы и вертикали — как в её референсах; ничего не объясняют, только держат сетку."""
    ln, ac = t["line"], t["accent"]
    return f"""<svg class="decor" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <path d="M640 60 C 820 20, 960 90, 1000 250" stroke="{ln}" stroke-width="2" fill="none"/>
  <circle cx="1000" cy="250" r="9" fill="{ac}"/>
  <circle cx="905" cy="100" r="13" stroke="{ac}" stroke-width="3" fill="none"/>
  <line x1="1068" y1="40" x2="1068" y2="160" stroke="{ln}" stroke-width="2"/>
  <path d="M140 1180 C 300 1300, 520 1320, 700 1280" stroke="{ln}" stroke-width="2" fill="none"/>
  <circle cx="300" cy="1262" r="11" stroke="{ac}" stroke-width="3" fill="none"/>
</svg>"""


def _dots(t: dict, beside_tiles: bool = False) -> str:
    """Сетка точек внизу слева; есть плитки — встаёт правее них, чтобы не налезать."""
    dots = "".join(f'<i style="left:{c * 26}px;top:{r * 26}px"></i>' for r in range(4) for c in range(4))
    style = ' style="left:430px;bottom:96px"' if beside_tiles else ""
    return f'<div class="dots"{style}>{dots}</div>'


def _tiles(icons: list, t: dict) -> str:
    """Плитки с иконками и связи между ними (её 1-й референс) — рисуются кодом."""
    pos = [(122, 0), (0, 150), (244, 150)][: len(icons)]
    tiles = "".join(
        f'<div class="tile" style="left:{x}px;top:{y}px">{_icon(name, 64, t["accent"])}</div>'
        for (x, y), name in zip(pos, icons))
    links = (f'<svg class="links" width="380" height="290"><path d="M60 150 V110 Q60 60 122 60 M306 150 V110 '
             f'Q306 60 244 60 M183 120 V200 M60 210 Q60 230 150 230 H183 H216 Q306 230 306 210" '
             f'stroke="{t["line"]}" stroke-width="2" fill="none"/><circle cx="183" cy="200" r="10" '
             f'stroke="{t["accent"]}" stroke-width="3" fill="{t["bg"]}"/></svg>')
    return f'<div class="tiles">{links}{tiles}</div>'


def _photo_src(path: str, notes: list) -> str | None:
    p = Path(path)
    if not p.is_file():
        notes.append(f"нет файла фото: {path}")
        return None
    return p.resolve().as_uri()


def build_cover(data: dict, theme: str, notes: list | None = None) -> str:
    notes = notes if notes is not None else []
    t = THEMES[theme]
    col = 610
    size = fit_headline(str(data["hook"]).split("\n"), col, 128)
    photo = ""
    if data.get("photo"):
        src = _photo_src(data["photo"], notes)
        if src:
            photo = (f'<img class="photo" src="{src}" style="object-position:{data.get("focus", "50% 15%")}">')
    pill = (f'<div class="top"><div class="pill">{_rich(data["pill"])}</div><div class="pill-line"></div>'
            f'<i class="node"></i></div>') if data.get("pill") else ""
    # с её фото справа строка «ТЕСТИРУЮ…» ложится на волосы — в её референсах с фото её нет
    tag = "" if data.get("photo_kind") == "her" else f'<div class="tag">{_lines_html(data.get("tag") or DEFAULT_TAG)}</div>'
    hand = f'<div class="hand">{_lines_html(data["hand"])}</div>' if data.get("hand") else ""
    support = f'<div class="support">{_lines_html(data["support"])}</div>' if data.get("support") else ""
    tiles = _tiles(data["icons"][:3], t) if data.get("icons") else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>cover</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet"><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:#000; }}
.canvas {{ width:{W}px; height:{H}px; position:relative; overflow:hidden; color:{t['text']}; font-family:'Open Sans',sans-serif;
  background: radial-gradient(circle at 85% 30%, {t['glow']} 0%, transparent 45%),
              radial-gradient(circle at 10% 95%, {t['glow']} 0%, transparent 35%),
              linear-gradient(160deg, {t['bg']} 0%, {t['bg2']} 100%); }}
.decor {{ position:absolute; inset:0; z-index:1; }}
.photo {{ position:absolute; right:0; bottom:0; width:66%; height:100%; object-fit:cover; z-index:2;
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 30%), linear-gradient(0deg, #000 85%, transparent 100%);
  mask-image: linear-gradient(90deg, transparent 0%, #000 30%); }}
.top {{ position:absolute; left:66px; top:78px; width:640px; z-index:3; display:flex; align-items:center; }}
.pill {{ flex:none; border:2px solid {t['line']}; border-radius:44px; padding:16px 32px;
  font-size:25px; font-weight:600; letter-spacing:.24em; text-transform:uppercase; }}
.pill-line {{ flex:1; height:2px; background:{t['line']}; margin:0 16px 0 22px; }}
.node {{ flex:none; width:16px; height:16px; border-radius:50%; background:{t['accent']}; }}
.tag {{ position:absolute; right:70px; top:82px; z-index:3; font-size:21px; letter-spacing:.3em; line-height:1.75; color:{t['muted']}; }}
.hero {{ position:absolute; left:66px; top:210px; width:{col}px; z-index:3; }}
h1 {{ font-family:'Roboto Condensed',sans-serif; font-weight:800; text-transform:uppercase; line-height:.95; font-size:{size}px;
  letter-spacing:-.01em; }}
.acc {{ color:{t['accent']}; }}
.hand {{ font-family:'Marck Script',cursive; color:{t['hand']}; font-size:58px; line-height:1.08; margin:34px 0 0 22px;
  transform:rotate(-6deg); transform-origin:left; white-space:nowrap; }}
.support {{ margin:64px 0 0 26px; padding-left:22px; border-left:2px solid {t['line']}; font-size:21px; letter-spacing:.3em;
  line-height:1.75; color:{t['muted']}; text-transform:uppercase; }}
.tiles {{ position:relative; width:380px; height:290px; margin-top:40px; transform:scale(.9); transform-origin:left top; }}
.links {{ position:absolute; left:0; top:0; }}
.tile {{ position:absolute; width:124px; height:120px; border-radius:22px; background:{t['tile']}; border:1.5px solid {t['tile_border']};
  display:flex; align-items:center; justify-content:center; box-shadow:0 18px 40px {t['glow']}; }}
.dots {{ position:absolute; left:66px; bottom:70px; width:100px; height:100px; z-index:3; }}
.dots i {{ position:absolute; width:7px; height:7px; border-radius:50%; background:{t['accent']}; opacity:.8; }}
</style></head><body><div class="canvas">{_decor(t)}{photo}{pill}{tag}
<div class="hero"><h1>{_rich(data['hook'])}</h1>{hand}{support}{tiles}</div>{_dots(t, beside_tiles=bool(tiles))}</div></body></html>"""


def build(folder: Path, data_file: Path | None = None, root: Path = ROOT) -> int:
    folder = Path(folder)
    data_file = Path(data_file) if data_file else folder / "cover.json"
    data = json.loads(data_file.read_text(encoding="utf-8"))
    choice = next_choice(root)
    choice = {"bg": data.get("bg") or choice["bg"], "photo_kind": data.get("photo_kind") or choice["photo_kind"]}
    if data.get("photo") and not Path(data["photo"]).is_absolute():
        data["photo"] = str((data_file.parent / data["photo"]).resolve())
    notes: list = []
    out = folder / "visuals"
    out.mkdir(parents=True, exist_ok=True)
    name = data.get("name", "cover")   # несколько вариантов в одной папке — разные имена
    page = out / f"{name}.html"
    page.write_text(build_cover(data, choice["bg"], notes), encoding="utf-8")
    res = render.render_image(page, out / f"{name}.png")
    print(f"{name}.png — {choice['bg']}, фото: {choice['photo_kind']}, {'готов' if res.ok else 'НЕ СНЯТ: ' + str(res.error)}")
    for n in notes + res.warnings:
        print(f"  · {n}")
    if res.ok:
        remember_choice(root, choice)
    return 0 if res.ok else 3


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
