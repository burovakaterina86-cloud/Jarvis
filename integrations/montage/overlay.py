"""Сцены второго захода: спецификация → одна HTML-страница (все сцены) + timeline.json.

Страница анимируется функцией `render(t)` из templates/overlay.js (детерминированно, без таймеров), покадровый
снимок делает `render.py`. Вид — утверждённый ею 2026-10-06: оранжевый фон, белые карточки (раскладка «B»),
хук по центру с объёмным логотипом, чипы «нажимаются» курсором на произносимых словах.
"""
from __future__ import annotations

import base64
import html as _html
import json
from pathlib import Path

from . import config, custom, icons
from .spec import Resolved, logo_path

P = config.PALETTE
CLAY, INK, CREAM = P["bg"], P["ink"], P["cream"]


def _url(path: Path) -> str:
    return "file:///" + Path(path).resolve().as_posix()


def _logo(name: str) -> str:
    return _url(logo_path(name))


def _mask() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode((config.ASSETS / "claude-icon.svg").read_bytes()).decode()


def num(v) -> str:
    """Число в атрибут: приводим к float, чтобы из поля спецификации нельзя было вставить разметку."""
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise ValueError(f"в сцене ожидалось число, а пришло {str(v)[:40]!r}") from e
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"в сцене ожидалось конечное число, а пришло {str(v)[:40]!r}")
    return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else repr(f)


def attr(s) -> str:
    """Текст в значение атрибута в кавычках."""
    return _html.escape(str(s), quote=True)


def esc(s: str) -> str:
    return _html.escape(str(s), quote=False).replace("&lt;br&gt;", "<br>")


def logo3d(size: int, depth: int = 14) -> str:
    """Объёмный логотип: стопка смещённых слоёв-экструзия + светлая грань + блик + мягкая тень (всё из одной маски)."""
    layers = ""
    for k in range(depth, 0, -1):
        s = int(120 - k * 2.2)
        layers += (f"<div class=m style='transform:translate({k * .9}px,{k * 1.1}px);"
                   f"background:rgb({s + 40},{max(s - 40, 20)},{max(s - 60, 10)})'></div>")
    face = "<div class=m style='background:linear-gradient(145deg,#FFFFFF 0%,#FFE9DC 45%,#F2B79B 100%)'></div>"
    shine = "<div class=m style='background:linear-gradient(160deg,rgba(255,255,255,.9) 0%,rgba(255,255,255,0) 40%)'></div>"
    shadow = (f"<div class=m style='transform:translate({depth * 1.4}px,{depth * 1.9}px);background:#000;"
              f"opacity:.35;filter:blur(18px)'></div>")
    return f"<div style='position:relative;width:{size}px;height:{size}px'>{shadow}{layers}{face}{shine}</div>"


PANEL_BG = f"<div class=abs style='left:0;top:0;width:1080px;height:{config.PANEL_H}px;background:{CLAY}'></div>"
ARROW = "<div class=arrow>→</div>"
PF = "font-family:PF,serif;font-style:italic;font-weight:600"


# ---------------------------------------------------------------- сплит
def hook_html(d: dict) -> str:
    size = num(d.get("size", 150))
    lines = ""
    for ln in d["lines"]:
        segs = ""
        for seg in ln:
            if seg.get("logo3d"):
                segs += f"<div class=lg style='width:210px;height:170px;margin-top:-4px'>{logo3d(190, 14)}</div>"
                continue
            style = []
            if seg.get("color") == "ink":
                style.append(f"color:{INK}")
            if seg.get("italic"):
                style.append(f"{PF};letter-spacing:0")
                if "color" not in seg:
                    style.append(f"color:{INK}")
            segs += f"<span style='{';'.join(style)}'>{esc(seg['t'].strip())}</span>"
        lines += (f"<div class=hl style='display:flex;align-items:center;justify-content:center;gap:.22em'>{segs}</div>")
    return (f"{PANEL_BG}<div class=abs style='left:0;right:0;top:150px;text-align:center;font-size:{size}px;font-weight:900;"
            f"line-height:1.08;letter-spacing:-3px;color:#fff;white-space:nowrap'>{lines}</div>")


def chip_html(c: dict) -> str:
    if c.get("arrow"):
        return ARROW
    img = f"<img src='{_logo(c['logo'])}'>" if c.get("logo") else (icons.icon_svg(c["icon"], 44) if c.get("icon") else "")
    return f"<div class=chip data-t='{num(c['t'])}'><div class=ring></div>{img}<span>{esc(c['text'])}</span></div>"


def step_html(d: dict) -> str:
    n = int(num(d["n"]))
    segs = "".join(f"<div class=seg data-i='{i}'><div class=fill></div></div>" for i in range(1, 11))
    chips = "".join(chip_html(c) for c in d.get("chips", []))
    return (f"{PANEL_BG}<div class='abs segs' style='left:70px;top:150px;display:flex;gap:8px'>{segs}</div>"
            f"<div class='abs card' style='left:70px;right:70px;top:215px;padding:48px 56px 50px'>"
            f"<div style='display:flex;align-items:center;gap:30px'>"
            f"<div class='numc tile' style='width:130px;height:130px;min-width:130px;background:{CLAY};font-size:{80 if n < 10 else 60}px;border-radius:65px'>{num(n)}</div>"
            f"<div class=ttl style='font-size:76px;font-weight:900;line-height:1.04'>{esc(d['title'])}</div></div>"
            f"<div class=chips style='display:flex;flex-wrap:wrap;gap:16px;margin-top:38px'>{chips}</div></div>"
            f"<div class=cur><svg width='64' height='64' viewBox='0 0 24 24'><path d='M4 2 L4 19 L8.6 14.8 L11.6 21.5 L14.2 20.3 L11.3 13.8 L17.5 13.4 Z' "
            f"fill='#fff' stroke='#0E0D0C' stroke-width='1.4' stroke-linejoin='round'/></svg></div>")


# ---------------------------------------------------------------- полноэкранные
PHONE = {"header": "Claude · утренняя сводка", "logo": "claude", "user": "Собери сводку на сегодня",
         "intro": "Вот твой день на одной странице.", "sub": "Главное за ночь:", "input": "Reply to Claude",
         "rows": [{"logo": "google-calendar", "bold": "Календарь", "text": "встречи на день"},
                  {"logo": "gmail", "bold": "Почта", "text": "важное и ждёт ответа"},
                  {"logo": "google-news", "bold": "Новости", "text": "главное за ночь"}]}


def _full(inner: str) -> str:
    return f"<div class=fsbg style='background:{CLAY}'></div>{inner}"


def phone_html(d: dict) -> str:
    d = {**PHONE, **d}
    rows = "".join(
        f"<div class=prow style='display:flex;gap:22px;align-items:center;margin:20px 0'><img src='{_logo(r['logo'])}' style='width:58px;height:58px'>"
        f"<div style='font-size:34px;line-height:1.2'><b>{esc(r['bold'])}</b> → {esc(r['text'])}</div></div>" for r in d["rows"])
    return _full(
        f"<div class='abs hd' style='left:0;right:0;top:165px;display:flex;justify-content:center;align-items:center;gap:20px;font-size:56px;font-weight:900;color:#fff'>"
        f"<img src='{_logo(d['logo'])}' style='width:76px;height:76px'>{esc(d['header'])}</div>"
        f"<div class='abs ph' style='left:190px;top:300px;width:700px;height:930px;border-radius:78px;background:#1a1918;border:9px solid #3a3836;"
        f"box-shadow:0 30px 70px rgba(0,0,0,.4);color:#EDE8E1;padding:62px 40px 30px'>"
        f"<div style='display:flex;justify-content:flex-end'><div class=bub style='background:#2c2a28;border-radius:32px;padding:22px 30px;font-size:34px'>{esc(d['user'])}</div></div>"
        f"<div class=prow style='font-size:36px;margin:44px 0 22px'>{esc(d['intro'])}</div>"
        f"<div class=prow style='font-size:32px;opacity:.7;margin-bottom:8px'>{esc(d['sub'])}</div>{rows}"
        f"<div class=abs style='left:36px;right:36px;bottom:36px;height:120px;border-radius:40px;background:#262422;color:#8d8780;font-size:32px;padding:26px 34px'>{esc(d['input'])}</div></div>")


def week_html(d: dict) -> str:
    days = d.get("days", ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"])
    cells = ""
    for i, day in enumerate(days):
        col, row = (i % 3, i // 3) if i < 6 else (1, 2)
        cells += (f"<div class='abs card wk' style='left:{75 + col * 320}px;top:{350 + row * 300}px;width:290px;height:270px;border-radius:30px;padding:26px'>"
                  f"<div style='font-size:52px;font-weight:900;color:{CLAY}'>{esc(day)}</div>"
                  f"<div style='margin-top:20px;height:14px;border-radius:7px;background:#E6DFD6'></div>"
                  f"<div style='margin-top:14px;height:14px;width:80%;border-radius:7px;background:#E6DFD6'></div>"
                  f"<div style='margin-top:16px;height:14px;width:60%;border-radius:7px;background:#E6DFD6'></div>"
                  f"<div style='margin-top:30px;font-size:26px;font-weight:700;opacity:.5'>{esc(d.get('card_text', 'пост твоим голосом'))}</div></div>")
    return _full(
        f"<div class='abs hd' style='left:0;right:0;top:175px;text-align:center;font-size:98px;font-weight:900;color:#fff;letter-spacing:-2px;white-space:nowrap'>"
        f"<span class='tt tt1' data-t='{num(d['t_a'])}'>{esc(d.get('title_a', '1 текст'))}</span> → "
        f"<span class='tt tt2' style='{PF};color:{INK}' data-t='{num(d['t_b'])}'>{esc(d.get('title_b', '7 постов'))}</span></div>{cells}")


def money_html(d: dict) -> str:
    rows = "".join(
        f"<div class=mrow data-t='{num(r['t'])}' style='display:flex;align-items:center;gap:26px;padding:26px 8px;border-bottom:3px solid #EEE7DE'>"
        f"<div class='tick tile' style='width:62px;height:62px;border-radius:31px;background:#E6DFD6;font-size:34px'>✓</div>"
        f"<div style='font-size:50px;font-weight:800'>{esc(r['text'])}</div></div>" for r in d["rows"])
    return _full(
        f"<div class='abs hd' style='left:0;right:0;top:190px;text-align:center;font-size:92px;font-weight:900;color:#fff;letter-spacing:-2px'>"
        f"<span style='{PF};color:{INK}'>{esc(d.get('title_italic', 'Клод'))}</span> {esc(d.get('title_rest', 'читает почту'))}</div>"
        f"<div class='abs card t1' style='left:200px;top:400px;width:260px;height:260px;border-radius:64px;display:flex;align-items:center;justify-content:center'><img src='{_logo(d.get('left', 'claude'))}' style='width:150px'></div>"
        f"<div class='abs card t2' style='left:620px;top:400px;width:260px;height:260px;border-radius:64px;display:flex;align-items:center;justify-content:center'><img src='{_logo(d.get('right', 'gmail'))}' style='width:150px'></div>"
        f"<div class='abs line' style='left:470px;top:526px;width:140px;height:8px;border-radius:4px;background:{INK}'></div>"
        f"<div class='abs dot' style='left:454px;top:514px;width:32px;height:32px;border-radius:16px;background:#fff;border:6px solid {INK}'></div>"
        f"<div class='abs card list' style='left:130px;top:790px;width:820px;padding:20px 50px'>{rows}</div>")


def pipe_html(d: dict) -> str:
    items = d["items"]
    cells = ""
    for i, nm in enumerate(items[:10]):
        col, row = i % 2, i // 2
        cells += (f"<div class='abs card prw' style='left:{64 + col * 482}px;top:{370 + row * 128}px;width:470px;height:108px;border-radius:28px;"
                  f"display:flex;align-items:center;gap:16px;padding:0 22px'><span style='font-size:32px;font-weight:900;color:{CLAY}'>{i + 1:02d}</span>"
                  f"<span style='font-size:28px;font-weight:800;white-space:nowrap'>{esc(nm)}</span></div>")
    return _full(
        f"<div class='abs hd' style='left:0;right:0;top:170px;text-align:center;font-size:92px;font-weight:900;color:#fff;letter-spacing:-2px'>"
        f"{esc(d.get('title_pre', 'Пайплайн '))}<span style='{PF};color:{INK}'>{esc(d.get('title_italic', 'всех систем'))}</span></div>{cells}")


# ---------------------------------------------------------------- плашки над головой (полоса)
def _pillwrap(inner: str, top: int) -> str:
    return f"<div class='abs pillwrap' style='left:0;right:0;top:{top}px;display:flex;justify-content:center'>{inner}</div>"


def pill_html(d: dict) -> str:
    img = f"<img src='{_logo(d['logo'])}' style='width:62px'>" if d.get("logo") else (icons.icon_svg(d["icon"], 56) if d.get("icon") else "")
    return _pillwrap(f"<div class=pill style='background:#fff;border-radius:60px;padding:20px 42px;font-size:46px;font-weight:900;display:flex;gap:18px;"
                     f"align-items:center;box-shadow:0 10px 30px rgba(0,0,0,.3)'>{img}{esc(d['text'])}</div>", 150)


def cta_html(d: dict) -> str:
    logo = f"<img src='{_logo(d['logo'])}' style='width:84px'>" if d.get("logo") else ""
    stroke = "-webkit-text-stroke:7px rgba(14,13,12,.85);paint-order:stroke fill"
    return _pillwrap(
        f"<div class=pill style='text-align:center'><div class=ct1 style='font-size:40px;font-weight:900;color:#fff;{stroke}'>{esc(d['top'])}</div>"
        f"<div class=big style='position:relative;display:inline-flex;align-items:center;gap:20px;margin-top:10px;background:#fff;border-radius:80px;padding:8px 52px;"
        f"font-size:92px;font-weight:900;box-shadow:0 12px 34px rgba(0,0,0,.35)'><div class=ring2></div>{esc(d['code'])}{logo}</div>"
        f"<div class=ct3 style='font-size:34px;font-weight:900;color:#fff;margin-top:12px;-webkit-text-stroke:6px rgba(14,13,12,.85);paint-order:stroke fill'>{esc(d['bottom'])}</div></div>", 135)


def custom_html(d: dict) -> str:
    layout = d.get("layout", "full")
    base = {"full": f"<div class=fsbg style='background:{CLAY}'></div>", "split": PANEL_BG, "band": ""}[layout]
    if d.get("bg") is False:
        base = ""
    return base + d["html_final"]


BUILDERS = {"custom": custom_html, "hook": hook_html, "step": step_html, "phone": phone_html, "week": week_html, "money": money_html,
            "pipe": pipe_html, "pill": pill_html, "cta": cta_html}
JS_TYPE = {"step": "panel"}   # тип сцены в overlay.js


def build(res: Resolved, out_dir: Path) -> dict:
    """Пишет overlay.html и timeline.json в out_dir. Возвращает timeline."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    body, meta = "", []
    for sc in res.scenes:
        sid = sc.id
        body += f"<div class=scene id='{attr(sid)}'>{BUILDERS[sc.type](sc.data)}</div>"
        m = {"id": sid, "type": JS_TYPE.get(sc.type, sc.type), "start": sc.start, "end": sc.end}
        if sc.type == "step":
            m["n"] = sc.data["n"]
        if sc.type == "cta":
            m["press"] = sc.data["press_t"]
        meta.append(m)
    tpl = (config.TEMPLATES / "template.html").read_text(encoding="utf-8")
    page = (tpl.replace("%%FONT%%", _url(config.ASSETS / "fonts" / "GolosText-Variable.ttf"))
            .replace("%%FONTPF%%", _url(config.ASSETS / "fonts" / "PlayfairDisplay-Italic-Variable.ttf"))
            .replace("%%MASK%%", _mask()).replace("%%CLAY%%", CLAY).replace("%%INK%%", INK).replace("%%CREAM%%", CREAM)
            .replace("%%SCENES%%", body).replace("%%DATA%%", json.dumps({"scenes": meta}, ensure_ascii=False))
            .replace("%%JS%%", (config.TEMPLATES / "overlay.js").read_text(encoding="utf-8")))
    (out_dir / "overlay.html").write_text(page, encoding="utf-8")
    warnings = [f"{sc.id}: {w}" for sc in res.scenes if sc.type == "custom" for w in custom.safe_warnings(sc.data["html_final"])]
    tl = {"scenes": meta, "dur": res.duration, "warnings": warnings,
          "split": [list(w) for w in res.windows("split")],
          "band": [list(w) for w in res.windows("band")],
          "full": [list(w) for w in res.windows("full")]}
    (out_dir / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    return tl
