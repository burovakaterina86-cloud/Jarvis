# -*- coding: utf-8 -*-
"""Сборка HTML-страницы «Контент-план» из JSON недели (порт генератора агента).

    python -m integrations.content_plan render <папка_недели>

Читает reels.json, carousels.json, strategy.json (YouTube не берём — её решение 2026-10-06).
Пишет plan-<дата понедельника>.html: самодостаточная адаптивная страница (CSS/JS внутри, только
Google Fonts, без картинок). Письма и Word нет. Все строки из данных экранируются (html.escape).
Дизайн-система «Радар» — как у агента. Данные грузит init(); `render(папка)` — точка входа.
"""
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path

# ────────────────────────────── данные ──────────────────────────────

BASE = Path(".")


def _norm(o):
    """«@@автор» → «@автор» во всех строках."""
    if isinstance(o, str):
        return re.sub(r"@{2,}", "@", o)
    if isinstance(o, list):
        return [_norm(x) for x in o]
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    return o


def load(name):
    return _norm(json.loads((BASE / name).read_text(encoding="utf-8")))


REELS, CARS, YT, ST, PROFILE = {"days": []}, {"carousels": []}, {"topics": []}, {}, {}

# ── коды Instagram в видимом тексте → «рилс @автор» / «карусель @автор» ──
CODE_INFO = {}  # code → (вид, @автор); заполняет init()
CODE_FORMS = {  # падеж: (ед., мн.)
    "рилс": {"nom": ("рилс", "рилсы"), "gen": ("рилса", "рилсов"), "ins": ("рилсом", "рилсами"), "pre": ("рилсе", "рилсах")},
    "карусель": {"nom": ("карусель", "карусели"), "gen": ("карусели", "каруселей"), "ins": ("каруселью", "каруселями"),
                 "pre": ("карусели", "каруселях")},
}
CODE_NOUNS = {f for forms in CODE_FORMS.values() for pair in forms.values() for f in pair} | {"рилсу", "карусели"}
CODE_ONE = r"(?<![A-Za-z0-9_/.-])[A-Za-z0-9_-]{11}(?![A-Za-z0-9_-])"
CODE_RUN_RE = re.compile(rf"{CODE_ONE}(?:(?:, | и | или ){CODE_ONE})*")
CODE_KEYS = {"code", "reel", "reels", "carousel", "carousel_code", "lead_in_reel", "url"}  # здесь коды — ключи, не текст


def _at(a):
    return "@" + re.sub(r"^@+", "", a or "")


def human_codes(text):
    """«У Dc6YyibzPra в оригинале» → «У рилса @ritikgupta.ai в оригинале». Трогает только коды из словаря."""
    if not isinstance(text, str) or not CODE_INFO:
        return text

    def repl(m):
        run = m.group(0)
        codes = re.findall(CODE_ONE, run)
        if not any(c in CODE_INFO for c in codes):
            return run
        before = text[:m.start()]
        pw = re.search(r"([А-Яа-яЁё]+)\s$", before)
        prev = pw.group(1).lower() if pw else ""
        if prev in CODE_NOUNS:
            case = None
        elif prev in ("у", "из", "от", "для", "до", "без") or prev.endswith(("ого", "его")):
            case = "gen"
        elif prev in ("с", "со"):
            case = "ins"
        elif prev in ("в", "во", "о", "об"):
            case = "pre"
        else:
            case = "nom"
        kinds = {CODE_INFO[c][0] for c in codes if c in CODE_INFO}
        known = all(c in CODE_INFO for c in codes)
        if known and len(kinds) == 1 and len(codes) > 1:  # «рилсы @a, @b и @c»
            kind = kinds.pop()
            out = re.sub(CODE_ONE, lambda x: _at(CODE_INFO[x.group(0)][1]), run)
            out = (CODE_FORMS[kind][case][1] + " " + out) if case else out
        else:
            def one(x):
                c = x.group(0)
                if c not in CODE_INFO:
                    return c
                kind, a = CODE_INFO[c]
                return (CODE_FORMS[kind][case][0] + " " if case else "") + _at(a)
            out = re.sub(CODE_ONE, one, run)
        if not before.strip() or re.search(r"[.!?]\s*$", before):
            out = out[:1].upper() + out[1:]
        return out

    return CODE_RUN_RE.sub(repl, text)


def humanize(o, key=None):
    if key in CODE_KEYS and (isinstance(o, str) or (isinstance(o, list) and all(isinstance(x, str) for x in o))):
        return o
    if isinstance(o, str):
        return human_codes(o)
    if isinstance(o, list):
        return [humanize(x) for x in o]
    if isinstance(o, dict):
        return {k_: humanize(v, k_) for k_, v in o.items()}
    return o




def code_label(code):
    """Код рилса/карусели для случаев, когда он попадает в текст напрямую."""
    if code in CODE_INFO:
        kind, a = CODE_INFO[code]
        return f"{kind} {_at(a)}"
    return code

# ────────────────────────────── форматирование ──────────────────────────────

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WD_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def E(s):
    return html.escape("" if s is None else str(s), quote=True)


def D(s):
    return dt.date.fromisoformat(s)


def wd(s):
    return WD[D(s).weekday()]


def ddmm(s):
    x = D(s)
    return f"{x.day:02d}.{x.month:02d}"


def day_short(s):
    return f"{wd(s)} {ddmm(s)}"


def day_long(s):
    x = D(s)
    return f"{WD_FULL[x.weekday()]}, {x.day} {MONTHS[x.month - 1]}"


def num(n):
    return f"{n:,}".replace(",", " ") if isinstance(n, int) else E(n)


def dec(v, digits=1):
    s = f"{v:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def k(n):
    """131994 → «132 тыс.», 1350340 → «1,35 млн»."""
    if n is None:
        return "—"
    if n >= 1_000_000:
        return dec(n / 1e6, 2) + " млн"
    if n >= 1000:
        v = n / 1000
        return (dec(v, 1) if v < 100 else str(round(v))) + " тыс."
    return str(n)


def xfmt(x):
    if x is None:
        return None
    return f"×{round(x)}" if x >= 100 else "×" + dec(x, 1)


def mmss(sec):
    return f"{sec // 60}:{sec % 60:02d}" if sec else ""


def hms(s):
    if not s:
        return ""
    h, m, sec = s.split(":")
    return f"{int(h)}:{m}:{sec}" if int(h) else f"{int(m)}:{sec}"


def split_title(t):
    if " — " in t:
        a, b = t.rsplit(" — ", 1)
        return a, b
    return t, ""


def split_word(t):
    if " · " in t:
        a, b = t.rsplit(" · ", 1)
        return a, b
    return t, ""


def author(a):
    return "@" + re.sub(r"^@+", "", a or "")


def paras(text):
    parts = [p for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return "".join(f"<p>{E(p).replace(chr(10), '<br>')}</p>" for p in parts)


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«\"(])", (text or "").strip()) if s]


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def genitive(name):
    """Маргарита → Маргариты, Юлия → Юлии; остальное как есть."""
    if not name:
        return ""
    if name.endswith("я"):
        return name[:-1] + "и"
    if name.endswith("а"):
        return name[:-1] + ("и" if name[-2:-1] in "гкхжшщч" else "ы")
    return name


def chip(emoji, label, color="--muted", cls=""):
    return f'<span class="chip {cls}" style="--c:var({color})">{emoji} {E(label)}</span>'


def word(w, label="слово", cls=""):
    if not w:
        return ""
    return f'<span class="word {cls}"><i>{E(label)}</i>{E(w)}</span>'


def xcls(x):
    if x is None:
        return "x-none"
    return "x-hi" if x >= 10 else ("x-mid" if x >= 3 else "x-lo")


SLOT = {"воронка": ("🧲", "воронка", "--funnel"),
        "аутлаер": ("🚀", "аутлаер", "--outlier"),
        "сильный": ("💪", "сильный", "--strong")}
FMT = {"список": ("📋", "список"), "польза/инструкция": ("🛠", "инструкция"), "инструкция": ("🛠", "инструкция"),
       "теория": ("🧠", "теория"), "инсайт/мнение": ("💡", "инсайт"), "разбор ошибки": ("⚠️", "разбор ошибки"),
       "новость/тренд": ("📰", "тренд"), "разбор": ("🔍", "разбор")}
CAL_TYPE = {"Рилс": ("🎬", "--accent", "#reels"), "Сторис": ("📱", "--hot", "#stories"), "Карусель": ("🗂", "--outlier", "#carousels"),
            "Лид-магнит": ("🧲", "--funnel", "#telegram"), "Подкаст": ("🎙", "--tg", "#podcast"),
            "YouTube-видео": ("▶️", "--strong", "#youtube"), "Сторис-прогрев": ("🔥", "--hot", "#warmup")}


def lm_emoji(title, fmt=""):
    """Эмодзи-обложка лид-магнита по формату и названию (формат важнее)."""
    rules = ((("аудио",), "🎧"), (("промпт", "промт"), "🧾"), (("тест", "диагност"), "🧪"), (("чек-лист", "чеклист"), "✅"),
             (("трекер", "планер", "календар"), "🗓️"), (("практик", "челлендж", "протокол", "дней"), "🌅"),
             (("гайд", "инструкц"), "🧭"), (("шаблон", "текст"), "✍️"), (("аудит", "разбор"), "🔍"))
    for t in ((fmt or "").lower(), (title or "").lower()):
        for keys, e in rules:
            if any(x in t for x in keys):
                return e
    return "🧲"


# ────────────────────────────── индексы ──────────────────────────────

class _Nums(dict):
    """Числа шапки: нет данных — 0, а не падение."""
    def __missing__(self, key):
        return 0


def init(base):
    """Загрузить JSON недели и построить индексы. Вызывается перед сборкой страницы."""
    global BASE, REELS, CARS, YT, ST, PROFILE, CODE_INFO, ALL_REELS, N_REELS, ROUTES, BRIDGES
    global CAL_REEL_TITLE, LM_MAIN, LM_RES, POD, WARM, WARM_DATE, CAR_CHOSEN, DATES, WEEK_START
    global WEEK_TXT, YEAR, PRODUCT_ENTRY, PRODUCT_MAIN
    BASE = Path(base).resolve()
    REELS, CARS, ST = load("reels.json"), load("carousels.json"), load("strategy.json")
    YT = {"topics": [], "stats": {}}  # YouTube не берём
    PROFILE = {}
    for cand in (BASE.parent / "profile.json", BASE.parent.parent / "profile.json"):
        if cand.exists():
            PROFILE = _norm(json.loads(cand.read_text(encoding="utf-8")))
            break
    CODE_INFO = {}
    for _d in REELS.get("days", []):
        for _r in _d["reels"]:
            CODE_INFO[_r["code"]] = ("рилс", _r.get("author"))
    for _r in REELS.get("no_speech", []):
        CODE_INFO.setdefault(_r["code"], ("рилс", _r.get("author")))
    for _c in CARS.get("carousels", []) + CARS.get("rejected", []):
        CODE_INFO.setdefault(_c["code"], ("карусель", _c.get("author")))
    REELS, CARS, ST = humanize(REELS), humanize(CARS), humanize(ST)
    ST["numbers"] = _Nums(ST.get("numbers", {}))
    ALL_REELS = {}
    for day in REELS["days"]:
        for r in day["reels"]:
            ALL_REELS[r["code"]] = (r, day)
    N_REELS = len(ALL_REELS)
    stats, nums = REELS.get("stats", {}), ST["numbers"]
    for key, value in (("reels_unique", stats.get("collected", 0)), ("reels_fresh", stats.get("fresh", 0)),
                       ("reels_transcribed", stats.get("transcribed", 0)), ("reels_selected", N_REELS),
                       ("carousels_found", len(CARS.get("carousels", []))),
                       ("carousels_selected", len(CARS.get("carousels", []))),
                       ("comments_15_reels", sum(r.get("comments") or 0 for r, _ in ALL_REELS.values())),
                       ("views_15_reels", sum(r.get("views") or 0 for r, _ in ALL_REELS.values()))):
        nums.setdefault(key, value)   # числа шапки считает Python; стратег может не заполнять
    ROUTES = {x["reel"]: x for x in ST.get("routes", [])}
    BRIDGES = {}
    CAL_REEL_TITLE = {}
    for c in ST.get("calendar", []):
        for it in c["items"]:
            if it["type"] == "Рилс":
                CAL_REEL_TITLE[c["date"]] = split_word(it["title_ru"])[0]
    LM_MAIN = ST.get("lead_magnets", {}).get("main", [])
    LM_RES = ST.get("lead_magnets", {}).get("reserve", [])
    POD = ST.get("podcast", {})
    POD["outline_ru"] = [b if isinstance(b, dict) else {"block": f"{i}. {b}", "points": []}
                         for i, b in enumerate(POD.get("outline_ru", []), 1)]
    WARM = ST.get("stories_warmup", {})
    log = WARM.get("check_log") or []
    WARM["check_log"] = [v if isinstance(v, dict) else
                         {"version": i, "topic_ru": str(v), "checks": {}, "verdict": "принято" if i == len(log) else "переписать"}
                         for i, v in enumerate(log, 1)]
    WARM_DATE = WARM.get("date") or (WARM.get("days") or [None])[0]  # прогрев — один день
    CAR_CHOSEN = {c["code"]: c for c in ST.get("carousels", {}).get("chosen", [])}
    DATES = [c["date"] for c in ST.get("calendar", [])] or [d["date"] for d in REELS["days"]]
    WEEK_START = DATES[0]
    WEEK_TXT = re.sub(r"\s*\d{4}\s*$", "", ST.get("week", ""))
    YEAR = D(WEEK_START).year
    PRODUCT_ENTRY, PRODUCT_MAIN = _products()


def _products():
    """Продукт входа и основной продукт: strategy.json (product_entry_ru / product_main_ru) или profile.json → product."""
    entry, main_ = ST.get("product_entry_ru"), ST.get("product_main_ru")
    if not (entry and main_):
        parts = [re.sub(r"\s*\([^)]*\)\s*", " ", p).strip() for p in re.split(r"[;\n]", PROFILE.get("product", "")) if p.strip()]
        raw = [p for p in re.split(r"[;\n]", PROFILE.get("product", "")) if p.strip()]
        e_i = next((i for i, p in enumerate(raw) if "вход" in p or "$" in p or "₽" in p), None)
        if e_i is not None:
            entry = entry or parts[e_i]
            main_ = main_ or next((p for i, p in enumerate(parts) if i != e_i), "")
        elif parts:
            main_ = main_ or parts[0]
    cap = lambda s: (s[:1].upper() + s[1:]) if s else s
    return cap(entry or ""), cap(main_ or "")




def bot_note():
    """Строка про бота кодовых слов, пока он не подтверждён."""
    status = str(PROFILE.get("code_word_bot", ""))
    note = ST.get("lead_magnets", {}).get("note_ru", "") or ""
    m = re.search(r"[^.]*нужен бот[^.]*\.?", note)
    if m:
        return m.group(0).strip()
    if status.startswith("не подтвержд") or not PROFILE:
        return "Чтобы кодовые слова работали, нужен бот (ChatPlace или ManyChat): пока он не подключён, слова в комментариях никто не обработает."
    return ""


def short_reel(code):
    r, day = ALL_REELS[code]
    if r.get("recommended") and day["date"] in CAL_REEL_TITLE:
        return CAL_REEL_TITLE[day["date"]]
    main = split_title(r["title_ru"])[0]
    head = main.split(":")[0]
    return head if len(head) >= 12 else main


def reel_notes(code):
    notes = []
    if POD.get("lead_in_reel") == code and POD.get("note_ru"):
        notes.append(("🎙", "Подкаст", POD["note_ru"]))
    for lm in LM_MAIN + LM_RES:
        if code in (lm.get("reels") or []) and lm.get("reel_note_ru"):
            notes.append(("🧲", "Лид-магнит", lm["reel_note_ru"]))
    b = BRIDGES.get(code)
    if b and b.get("note_ru"):
        notes.append(("▶️", "YouTube-видео", b["note_ru"]))
    return notes


def reel_leads(code):
    if code in ROUTES:
        return ROUTES[code]["leads_to_ru"]
    for lm in LM_RES:
        if code in (lm.get("reels") or []):
            return f"запасной лид-магнит «{lm['title_ru']}»"
    return ""


# ────────────────────────────── HTML: блоки ──────────────────────────────

def sec_head(num_, emoji, eyebrow, title, lead=""):
    return (f'<div class="sec-head"><div class="icon" aria-hidden="true">{emoji}</div><div>'
            f'<div class="eyebrow">{num_} · {E(eyebrow)}</div><h2>{E(title)}</h2>'
            + (f'<p class="lead">{E(lead)}</p>' if lead else "") + "</div></div>")


def radar_svg():
    top_x = max((r for r, _ in ALL_REELS.values()), key=lambda r: r.get("x_author") or 0)
    top_c = max((r for r, _ in ALL_REELS.values()), key=lambda r: r.get("comments") or 0)
    top_v = max((r for r, _ in ALL_REELS.values()), key=lambda r: r.get("views") or 0)
    x_label = (xfmt(top_x["x_author"]) + " к норме") if top_x.get("x_author") else "аутлаеры"
    blips = [(262, 118, "#FFD84D", x_label),
             (128, 250, "#6FD3A0", "💬 " + k(top_c["comments"])),
             (286, 282, "#9FB4FF", "▶ " + k(top_v["views"]))]
    rings = "".join(f'<circle cx="200" cy="200" r="{r}" fill="none" stroke="#232A35" stroke-width="1"/>'
                    for r in (48, 96, 144, 190))
    ticks = "".join(
        f'<line x1="{200 + 184 * math.cos(math.radians(a)):.1f}" y1="{200 + 184 * math.sin(math.radians(a)):.1f}" '
        f'x2="{200 + 190 * math.cos(math.radians(a)):.1f}" y2="{200 + 190 * math.sin(math.radians(a)):.1f}" stroke="#3A4453"/>'
        for a in range(0, 360, 10))
    bl = ""
    for x, y, c, t in blips:
        bl += (f'<circle cx="{x}" cy="{y}" r="16" fill="{c}" opacity=".12" class="ping"/>'
               f'<circle cx="{x}" cy="{y}" r="5" fill="{c}"/>'
               f'<text x="{x + 12}" y="{y - 10}" fill="{c}" font-size="12" font-family="JetBrains Mono, Consolas, monospace">{E(t)}</text>')
    return f'''<svg class="radar" viewBox="0 0 400 400" role="img" aria-label="Радар недели">
<defs><linearGradient id="sw" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FFD84D" stop-opacity="0"/><stop offset="1" stop-color="#FFD84D" stop-opacity=".32"/></linearGradient>
<radialGradient id="rg" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#FFD84D" stop-opacity=".08"/><stop offset="1" stop-color="#FFD84D" stop-opacity="0"/></radialGradient></defs>
<circle cx="200" cy="200" r="190" fill="url(#rg)"/>{rings}{ticks}
<line x1="10" y1="200" x2="390" y2="200" stroke="#232A35"/><line x1="200" y1="10" x2="200" y2="390" stroke="#232A35"/>
<g class="sweep"><path d="M200 200 L200 10 A190 190 0 0 1 334.4 65.6 Z" fill="url(#sw)"/><line x1="200" y1="200" x2="334.4" y2="65.6" stroke="#FFD84D" stroke-opacity=".7"/></g>
{bl}<circle cx="200" cy="200" r="4" fill="#FFD84D"/></svg>'''


def unit_num(s):
    parts = str(s).split(" ", 1)
    return E(parts[0]) + (f"<small>{E(parts[1])}</small>" if len(parts) > 1 else "")


def hero():
    n = ST["numbers"]
    summary = "".join(f'<li><b>{i:02d}</b><p>{E(t)}</p></li>' for i, t in enumerate(ST.get("summary_ru", []), 1))
    chain = [(n["reels_unique"], "рилсов в пуле"), (n["reels_fresh"], "свежих"),
             (n["reels_transcribed"], "расшифровано"), (n["reels_selected"], "в плане")]
    ch = ""
    for i, (v, lbl) in enumerate(chain):
        if i:
            ch += '<div class="arr" aria-hidden="true">→</div>'
        ch += f'<div class="ct{" hot" if i == len(chain) - 1 else ""}"><b>{num(v)}</b><span>{E(lbl)}</span></div>'
    tiles = [(num(n["carousels_found"]), "каруселей", f'из {num(n["carousels_posts_collected"])} постов'),
             (unit_num(k(n["comments_15_reels"])), "комментариев", f'у {n["reels_selected"]} отобранных рилсов'),
             (unit_num(k(n["views_15_reels"])), "просмотров", "у тех же рилсов")]
    tl = "".join(f'<div class="tile"><b>{v}</b><span>{E(a)}</span><em>{E(b)}</em></div>' for v, a, b in tiles)
    inplan = [("🎬", plural(N_REELS, "рилс", "рилса", "рилсов"), "#reels"),
              ("🗂", plural(len(CARS['carousels']), "карусель", "карусели", "каруселей"), "#carousels"),
              *([("📱", "сторис в дни рилсов", "#stories")] if ST.get("stories_days") else []),
              ("🔥", "прогрев в сторис" + (f" · {wd(WARM_DATE)}" if WARM_DATE else ""), "#warmup"),
              ("🧲", plural(len(LM_MAIN), "лид-магнит", "лид-магнита", "лид-магнитов") + (f" + {len(LM_RES)} запасных" if LM_RES else ""), "#telegram"),
              ("🎙", "подкаст", "#podcast")]
    ip = "".join(f'<a class="pill-link" href="{h}">{e} {E(t)}</a>' for e, t, h in inplan)
    return f'''<header class="hero" id="top"><div class="hero-bg" aria-hidden="true"></div>
<div class="wrap hero-in"><div class="hero-text">
<div class="badge"><span class="dot"></span>Контент-план · для {E(genitive(ST.get("client", "")))}</div>
<h1>Контент-план<span>{E(WEEK_TXT)}</span></h1>
<ol class="summary">{summary}</ol></div>
<div class="hero-radar">{radar_svg()}</div></div>
<div class="wrap"><div class="eyebrow hero-eb">Как отбирали · {YEAR}</div><div class="chain">{ch}</div>
<div class="tiles">{tl}</div><div class="inplan">{ip}</div></div></header>'''


def nav():
    links = [("week", "Неделя"), ("reels", "Рилсы"), ("stories", "Сторис"), ("carousels", "Карусели"), ("warmup", "Прогрев"),
             ("telegram", "Telegram"), ("funnel", "Воронка"), ("nospeech", "Без речи"),
             ("how", "Как собрано")]
    ls = "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in links)
    return f'''<nav class="nav" aria-label="Разделы"><div class="wrap nav-in">
<a class="brand" href="#top"><span class="brand-dot"></span>{E(ddmm(DATES[0]))}–{E(ddmm(DATES[-1]))}</a>
<div class="nav-links">{ls}</div>
<a class="counter" href="#reels" title="Отмеченные рилсы">✅ Беру <b data-count>0</b><span>/{N_REELS}</span></a></div></nav>'''


def week():
    cols = ""
    for c in ST.get("calendar", []):
        items = ""
        for it in c["items"]:
            e, color, href = CAL_TYPE.get(it["type"], ("•", "--muted", "#top"))
            title, w = split_word(it["title_ru"])
            goto = f' data-goto-day="day-{c["date"]}"' if it["type"] == "Рилс" else ""
            items += (f'<a class="wk-item" href="{href}"{goto} style="--c:var({color})">'
                      f'<span class="wk-type">{e} {E(it["type"])}</span><span class="wk-title">{E(title)}</span>'
                      + (f'<span class="wk-word">{E(w)}</span>' if w else "") + "</a>")
        weekend = " weekend" if D(c["date"]).weekday() >= 5 else ""
        cols += (f'<div class="wk-day{weekend}"><div class="wk-head"><span class="wk-wd">{wd(c["date"])}</span>'
                 f'<span class="wk-date">{ddmm(c["date"])}</span><span class="wk-n">{len(c["items"])}</span></div>'
                 f'<div class="wk-items">{items}</div></div>')
    legend = "".join(f'<span class="lg" style="--c:var({v[1]})"><i></i>{v[0]} {E(t)}</span>' for t, v in CAL_TYPE.items() if t != "YouTube-видео")
    return f'''<section class="sec" id="week"><div class="wrap">
{sec_head("01", "🗓", "Календарь", "Неделя на ладони", "Что и когда выходит. Нажмите на карточку, чтобы перейти к деталям.")}
<div class="legend">{legend}</div><div class="wk-grid">{cols}</div></div></section>'''


def metric_bits(r):
    parts = r.get("metric_ru", "").split(" · ")
    c = v = age = None
    for p in parts:
        p = p.strip()
        if p.startswith("💬"):
            c = p.split(" ", 1)[1]
        elif p.startswith("▶"):
            v = p.split(" ", 1)[1]
        elif p:
            age = p
    return c, v, age


def reel_card(r, day):
    rec = bool(r.get("recommended"))
    code = r["code"]
    uid = re.sub(r"[^A-Za-z0-9]", "_", code)
    main, sub = split_title(r["title_ru"])
    se, sl, sc = SLOT.get(r.get("slot"), ("🏷", r.get("slot") or "", "--muted"))
    fe, fl = FMT.get(r.get("format"), ("🏷", r.get("format") or ""))
    chips = (chip("⭐", "Рекомендуем", "--accent", "star") if rec else "") + chip(se, sl, sc) + chip(fe, fl, "--muted")
    take = (f'<label class="take"><input type="checkbox" data-code="{E(code)}"><span class="box" aria-hidden="true"></span>'
            f'<span class="take-l">Беру</span></label>')
    c, v, age = metric_bits(r)
    x = xfmt(r.get("x_author"))
    dur = mmss(r.get("duration_sec"))
    route = ROUTES.get(code)
    w = route["cta_word_ru"] if route else r.get("cta_word_ru")
    orig_w = r.get("cta_word_ru")
    wblock = word(w) if w else '<span class="word none"><i>слово</i>без кодового слова</span>'
    if w and orig_w and w != orig_w:
        wblock += f'<span class="was">в оригинале ролика: {E(orig_w)}</span>'
    leads = reel_leads(code)
    leads_html = f'<div class="leads">→ {E(leads)}</div>' if leads else ""
    notes = ""
    b = BRIDGES.get(code)
    if b and b.get("new_ending_ru"):
        notes += f'<div class="note ending"><span class="note-h">🔁 Новая концовка → урок на YouTube</span><p>«{E(b["new_ending_ru"])}»</p></div>'
    for ne, nl, nt in reel_notes(code):
        notes += f'<div class="note"><span class="note-h">{ne} {E(nl)}</span><p>{E(nt)}</p></div>'
    shoot = "".join(f"<li>{E(s)}</li>" for s in sentences(r.get("shoot_notes")))
    pot = ""
    if r.get("lead_magnet_potential"):
        pot += f'<div class="pot"><b>🧲 Лид-магнит</b><p>{E(r["lead_magnet_potential"])}</p></div>'
    if r.get("youtube_potential"):
        pot += f'<div class="pot"><b>▶️ YouTube-видео</b><p>{E(r["youtube_potential"])}</p></div>'
    n_par = len([p for p in re.split(r"\n\s*\n", r.get("script_ru", "")) if p.strip()])
    actions = f'''<div class="actions">
<button class="btn primary" type="button" data-toggle="scr-{uid}" aria-expanded="false">📜 Сценарий <span class="btn-meta">{E(dur)}</span></button>
<button class="btn" type="button" data-copy="src-{uid}">📋 Скопировать</button>
<button class="btn" type="button" data-toggle="sh-{uid}" aria-expanded="false">🎥 Для съёмки</button>
{'<button class="btn" type="button" data-toggle="pt-' + uid + '" aria-expanded="false">✨ Потенциал</button>' if pot else ''}
<span class="spacer"></span><span class="by">{E(author(r.get("author")))}</span>
<a class="orig" href="{E(r.get("url"))}" target="_blank" rel="noopener">оригинал ↗</a></div>
<textarea class="src" id="src-{uid}" hidden>{E(r.get("script_ru"))}</textarea>
<div class="panel script" id="scr-{uid}" hidden><div class="panel-h">📜 Сценарий · {E(dur)} · {n_par} абз.</div>{paras(r.get("script_ru"))}
{'<p class="en"><b>Хук оригинала (EN):</b> ' + E(r["original_hook_en"]) + '</p>' if r.get("original_hook_en") else ''}</div>
<div class="panel" id="sh-{uid}" hidden><div class="panel-h">🎥 Для съёмки</div><ul class="shoot">{shoot}</ul></div>
{'<div class="panel" id="pt-' + uid + '" hidden><div class="panel-h">✨ Потенциал ролика</div>' + pot + '</div>' if pot else ''}'''

    if rec:
        mt = ""
        for val, lbl, cls in ((c, "комментариев", "big"), (v, "просмотров", ""), (x, "к норме автора", "acc" if x else ""),
                              (age, "в ленте", "")):
            if val:
                mt += f'<div class="m {cls}"><b>{unit_num(val) if lbl != "в ленте" else E(val)}</b><span>{E(lbl)}</span></div>'
        return f'''<article class="card reel rec" data-code="{E(code)}">
<div class="reel-top"><div class="chips">{chips}</div>{take}</div>
<div class="rec-body"><div class="rec-main">
<h4 class="reel-title big">{E(main)}</h4>{f'<p class="reel-sub">{E(sub)}</p>' if sub else ''}
<blockquote class="hook">«{E(r.get("hook_ru"))}»</blockquote>
<div class="why"><div class="why-h">⭐ Почему рекомендуем</div><p>{E(r.get("why_recommended"))}</p></div></div>
<aside class="rec-side"><div class="mgrid">{mt}</div>
<div class="side-word"><span class="lbl">Кодовое слово</span><div class="wline">{wblock}</div>{leads_html}</div></aside></div>
{notes}{actions}</article>'''
    mrow = " · ".join(filter(None, [f"💬 {c}" if c else "", f"▶ {v}" if v else "", f"⏱ {age}" if age else "",
                                    x or "", f"🎞 {dur}" if dur else ""]))
    return f'''<article class="card reel" data-code="{E(code)}">
<div class="reel-top"><div class="chips">{chips}</div>{take}</div>
<h4 class="reel-title">{E(main)}</h4>{f'<p class="reel-sub">{E(sub)}</p>' if sub else ''}
<div class="mrow">{E(mrow)}</div>
<blockquote class="hook">«{E(r.get("hook_ru"))}»</blockquote>
<div class="wline">{wblock}</div>{leads_html}
{notes}{actions}</article>'''


def reels_section():
    tabs = panels = ""
    for i, day in enumerate(REELS["days"]):
        pid = f'day-{day["date"]}'
        codes = ",".join(r["code"] for r in day["reels"])
        rec = next((r for r in day["reels"] if r.get("recommended")), None)
        rec_w = ROUTES.get(rec["code"], {}).get("cta_word_ru") if rec else ""
        tabs += (f'<button class="tab{" active" if i == 0 else ""}" type="button" role="tab" aria-selected="{str(i == 0).lower()}" '
                 f'data-target="{pid}" data-codes="{E(codes)}"><span class="tab-wd">{wd(day["date"])}</span>'
                 f'<span class="tab-date">{ddmm(day["date"])}</span><span class="tab-word">{E(rec_w or "")}</span>'
                 f'<span class="tab-count"></span></button>')
        ordered = sorted(day["reels"], key=lambda r: not r.get("recommended"))
        cards = "".join(reel_card(r, day) for r in ordered)
        panels += (f'<div class="day-panel{" active" if i == 0 else ""}" id="{pid}" role="tabpanel">'
                   f'<div class="day-head"><h3>{E(day_long(day["date"]))}</h3><span>{plural(len(day["reels"]), "рилс", "рилса", "рилсов")} · ⭐ рекомендуемый первым</span></div>'
                   f'<div class="reel-grid">{cards}</div></div>')
    return f'''<section class="sec" id="reels"><div class="wrap">
{sec_head("02", "🎬", "Instagram · рилсы", "Рилсы по дням", f"{plural(N_REELS, 'рилс', 'рилса', 'рилсов')}, по три на день. Первый в каждом дне рекомендуем, два других — замены. Отмечайте «Беру»: счётчик наверху, выбор сохраняется в браузере.")}
<div class="tabs" role="tablist">{tabs}</div>{panels}</div></section>'''


def slide_html(text, i, total, cta):
    t = text or ""
    cls = ""
    if i == 0:
        cls = " cover"
    elif i == total - 1:
        cls = " final"
    prompt = ""
    save = ""
    if "prompt.md:" in t:
        t, prompt = t.split("prompt.md:", 1)
        prompt = prompt.strip()
        if prompt.endswith("Сохрани 📌"):
            prompt = prompt[: -len("Сохрани 📌")].strip()
            save = '<span class="save">Сохрани 📌</span>'
    head = ""
    body = t.strip()
    m = re.match(r"^((?:ПОСТ\s*\d+\.\s*«[^»]+»\.)|(?:\d+\.\s[^.]{3,90}\.)|(?:ШАГ\s*\d+:[^.]+\.))\s*(.*)$", body, re.S)
    if m:
        head, body = m.group(1), m.group(2)

    def rich(s):
        s = E(s)
        s = re.sub(r"\[(.*?)\]", r'<span class="vnote">🖼 \1</span>', s)
        s = s.replace(" ✓ ", "<br>✓ ")
        if cta:
            s = s.replace(E(cta), f'<mark>{E(cta)}</mark>')
        return s

    ln = len(body) + len(head)
    if prompt:
        size = "s-md"
    elif ln < 80:
        size = "s-xl"
    elif ln < 150:
        size = "s-lg"
    else:
        size = "s-md" if ln < 380 else "s-sm"
    inner = ""
    if head:
        inner += f'<div class="sl-head">{rich(head)}</div>'
    if body:
        inner += f'<div class="sl-text">{rich(body)}</div>'
    if prompt:
        inner += f'<div class="sl-code"><div class="sl-bar"><i></i><i></i><i></i>prompt.md</div><div class="sl-pr">{E(prompt)}</div></div>'
    return (f'<div class="slide{cls} {size}"><div class="sl-top"><span>{i + 1:02d}/{total:02d} <span class="sl-more">· листайте ↓</span></span>{save}</div>'
            f'<div class="sl-body">{inner}</div></div>')


def carousel_card(cr):
    code = cr["code"]
    uid = re.sub(r"[^A-Za-z0-9]", "_", code)
    ch = CAR_CHOSEN.get(code)
    main, sub = split_title(cr["title_ru"])
    fe, fl = FMT.get(cr.get("format"), ("🏷", cr.get("format") or ""))
    chips = ""
    if ch:
        chips += chip("⭐", f"В плане · {day_short(ch['date'])}", "--accent", "star")
    chips += chip(fe, fl, "--muted") + chip("🗂", plural(cr.get('slides_count') or len(cr['slides_ru']), "слайд", "слайда", "слайдов"), "--outlier")
    age = cr.get("age_days")
    mrow = " · ".join(filter(None, [f"💬 {num(cr['comments'])}", f"♥ {num(cr['likes'])}" if cr.get("likes") else "",
                                    f"⏱ {dec(age, 1)} дн." if age is not None else "", xfmt(cr.get("x_author")) or ""]))
    w = ch["cta_word_ru"] if ch else cr.get("cta_word_ru")
    wb = word(w)
    if ch and cr.get("cta_word_ru") and ch["cta_word_ru"] != cr["cta_word_ru"]:
        wb += f'<span class="was">в оригинале: {E(cr["cta_word_ru"])}</span>'
    leads = f'<div class="leads">→ {E(ch["leads_to_ru"])}</div>' if ch else ""
    notes = ""
    for lm in LM_MAIN + LM_RES:
        if lm.get("carousel_code") == code and lm.get("carousel_note_ru"):
            notes += f'<div class="note"><span class="note-h">🧲 Правка под лид-магнит</span><p>{E(lm["carousel_note_ru"])}</p></div>'
    cb = ST.get("youtube", {}).get("carousel_bridge", {})
    if cb.get("carousel") == code:
        notes += f'<div class="note ending"><span class="note-h">▶️ Мост на YouTube-видео</span><p>{E(cb["line_ru"])}</p></div>'
    if cr.get("availability_note"):
        notes += f'<div class="note warn"><span class="note-h">⚠️ Доступ и правки</span><p>{E(cr["availability_note"])}</p></div>'
    why = ch["why_ru"] if ch else cr.get("why")
    total = len(cr["slides_ru"])
    slides = "".join(slide_html(s, i, total, cr.get("cta_word_ru")) for i, s in enumerate(cr["slides_ru"]))
    return f'''<article class="card car{' rec' if ch else ''}">
<div class="reel-top"><div class="chips">{chips}</div><a class="orig" href="{E(cr.get("url"))}" target="_blank" rel="noopener">{E(author(cr.get("author")))} · оригинал ↗</a></div>
<div class="car-grid"><div><h4 class="reel-title{' big' if ch else ''}">{E(main)}</h4>{f'<p class="reel-sub">{E(sub)}</p>' if sub else ''}
<div class="mrow">{E(mrow)}</div><blockquote class="hook">«{E(cr.get("hook_ru"))}»</blockquote></div>
<div class="car-side"><div class="why"><div class="why-h">{'⭐ Почему в плане' if ch else '💡 Чем сильна'}</div><p>{E(why)}</p></div>
<div class="wline">{wb}</div>{leads}</div></div>
<div class="slides-wrap"><div class="slides-h"><span>Слайды текстом</span><span class="hint">листайте →</span></div><div class="slides">{slides}</div></div>
{notes}
<div class="actions"><button class="btn" type="button" data-toggle="vn-{uid}" aria-expanded="false">🎨 Как оформить свою версию</button>
{'<button class="btn" type="button" data-toggle="lm-' + uid + '" aria-expanded="false">🧲 Лид-магнит</button>' if cr.get("lead_magnet_link") else ''}</div>
<div class="panel" id="vn-{uid}" hidden><div class="panel-h">🎨 Визуал</div><p>{E(cr.get("visual_notes"))}</p></div>
{'<div class="panel" id="lm-' + uid + '" hidden><div class="panel-h">🧲 Лид-магнит</div><p>' + E(cr["lead_magnet_link"]) + '</p></div>' if cr.get("lead_magnet_link") else ''}
</article>'''


def carousels_section():
    chosen = sorted([c for c in CARS["carousels"] if c["code"] in CAR_CHOSEN], key=lambda c: CAR_CHOSEN[c["code"]]["date"])
    others = [c for c in CARS["carousels"] if c["code"] not in CAR_CHOSEN]
    body = "".join(carousel_card(c) for c in chosen)
    if others:
        body += (f'<div class="subhead"><h3>Запасные карусели</h3>'
                 f'<p>{E(ST.get("carousels", {}).get("not_chosen_ru", ""))}</p></div>'
                 + "".join(carousel_card(c) for c in others))
    cal_days = ", ".join(day_short(CAR_CHOSEN[c["code"]]["date"]) for c in chosen)
    in_cal = f"{len(chosen)} в календаре ({cal_days})" if chosen else "в календарь не поставлены"
    return f'''<section class="sec" id="carousels"><div class="wrap">
{sec_head("03", "🗂", "Instagram · карусели", "Карусели", f"{plural(len(CARS['carousels']), 'карусель', 'карусели', 'каруселей')} недели, {in_cal}. Слайды переведены: только текст, без картинок оригинала.")}
<div class="stack">{body}</div></div></section>'''


def stories_section():
    """Сторис в дни рилсов: повторяют суть рилса, кадры по порядку (strategy.json → stories_days)."""
    days = ST.get("stories_days", [])
    if not days:
        return ""
    cards = ""
    for d in days:
        frames = ""
        for f in d.get("frames", []):
            extra = " · ".join(filter(None, [("🎥 " + f["visual_ru"]) if f.get("visual_ru") else "",
                                             ("🎛 " + f["sticker_ru"]) if f.get("sticker_ru") else ""]))
            frames += (f'<li><span class="dbadge">{E(f.get("n"))}</span><div><b>{E(f.get("kind"))}</b><p>{E(f.get("text_ru"))}</p>'
                       + (f'<p class="muted small">{E(extra)}</p>' if extra else "") + "</div></li>")
        rc = d.get("reel")
        reel_chip = (f'<span class="rchip">🎬 {E(short_reel(rc))} <em>{wd(ALL_REELS[rc][1]["date"])}</em></span>'
                     if rc in ALL_REELS else "")
        n = len(d.get("frames", []))
        cards += (f'<article class="card stories-day"><div class="reel-top"><div class="chips">'
                  f'{chip("📱", "Сторис · " + day_short(d["date"]), "--hot")}{chip("🗂", plural(n, "кадр", "кадра", "кадров"), "--muted")}'
                  f'</div>{word(d.get("cta_word_ru"))}</div>'
                  f'<h4 class="reel-title">{E(d.get("title_ru"))}</h4><div class="rchips">{reel_chip}</div>'
                  f'<ol class="reveal">{frames}</ol>'
                  + (f'<p class="muted small">{E(d["note_ru"])}</p>' if d.get("note_ru") else "") + "</article>")
    return (f'''<section class="sec" id="stories"><div class="wrap">
{sec_head("02+", "📱", "Instagram · сторис", "Сторис в дни рилсов", "Те же дни, что и рилсы: в сторис повторяется суть рилса. Кадры по порядку, снимается за 10–15 минут.")}
{cards}</div></section>''')


def warmup_section():
    w = WARM
    if not w:
        return ""
    reveal = ""
    n_stories = 0
    for s in w.get("what_to_reveal_ru", []):
        m = re.match(r"^Сторис\s+([\d–-]+)\s*:\s*(.*)$", s, re.S) or re.match(r"^(Пн|Вт|Ср|Чт|Пт|Сб|Вс):\s*(.*)$", s, re.S)
        dlab, rest = (m.group(1), m.group(2)) if m else ("•", s)
        nums = re.findall(r"\d+", dlab)
        if nums:
            n_stories = max(n_stories, int(nums[-1]))
        cut = min([i for i in (rest.find(". "), rest.find(": ")) if i > 0] or [0])
        if 0 < cut < 70:
            head, txt = rest[:cut], rest[cut + 2:]
        else:
            head, txt = "", rest
        head = head[:1].upper() + head[1:]
        txt = txt[:1].upper() + txt[1:]
        reveal += (f'<li><span class="dbadge">{E(dlab)}</span><div>'
                   + (f'<b>{E(head)}</b>' if head else "") + f'<p>{E(txt)}</p></div></li>')
    span = day_long(WARM_DATE) if WARM_DATE else ""
    same_day = [it["type"].lower() for c in ST.get("calendar", []) if c["date"] == WARM_DATE
                for it in c["items"] if it["type"] != "Сторис-прогрев"]
    if same_day:
        span += " · в этот день " + (", ".join(same_day[:-1]) + " и " if len(same_day) > 1 else "") + same_day[-1]
    con = w.get("connects_to", {})
    if isinstance(con, list):
        con = {"reels": con}
    links = "".join(f'<span class="rchip">🎬 {E(short_reel(c))} <em>{wd(ALL_REELS[c][1]["date"])}</em></span>'
                    for c in con.get("reels", []) if c in ALL_REELS)
    crit = []  # критерии берём из данных, в порядке появления
    for v in w.get("check_log", []):
        for cname in v.get("checks", {}):
            if cname not in crit:
                crit.append(cname)
    crit = crit or ["востребована", "глубже рилса", "неожиданный угол", "не банальна"]
    rows = ""
    for v in w.get("check_log", []):
        cells = ""
        for cname in crit:
            val = v.get("checks", {}).get(cname, "")
            st = "yes" if val.startswith("да") else ("no" if val.startswith("нет") else "part")
            mark = {"yes": "✓", "no": "✕", "part": "~"}[st]
            cells += f'<td><span class="ck {st}" title="{E(val)}">{mark}</span><span class="ck-t">{E(val)}</span></td>'
        ok = v.get("verdict") == "принято"
        rows += (f'<tr class="{"ok" if ok else ""}"><th><span class="ver">v{v.get("version")}</span>{E(v.get("topic_ru"))}</th>{cells}'
                 f'<td><span class="verdict {"ok" if ok else ""}">{E(v.get("verdict"))}</span></td></tr>')
    heads = "".join(f"<th>{E(c)}</th>" for c in crit)
    topic = w.get("topic_ru", "")
    t_head, t_rest = (topic.split(":", 1) + [""])[:2]
    return f'''<section class="sec" id="warmup"><div class="wrap">
{sec_head("04", "🔥", "Instagram · сторис", "Прогрев в сторис", "Люди приходят с рилсов за инструментом, а в сторис получают продолжение, которого нет в ленте.")}
<article class="warm"><div class="warm-top"><span class="chip hotchip">🔥 Прогрев · один день{f" · {plural(n_stories, 'сторис', 'сторис', 'сторис')}" if n_stories else ""}</span><span class="mono muted">{E(span)}</span></div>
<h3 class="warm-title">{E(t_head)}{':' if t_rest else ''}<span>{E(t_rest)}</span></h3>
<div class="warm-grid"><div class="wbox"><div class="lbl">🎯 Неожиданный угол</div><p>{E(w.get("angle_ru"))}</p></div>
<div class="wbox"><div class="lbl">📈 Почему сейчас</div><p>{E(w.get("why_ru"))}</p></div></div>
<div class="lbl">Что показать в сторис · по порядку</div><ol class="reveal">{reveal}</ol>
<div class="warm-leads"><div class="lbl">Куда ведёт</div><div class="rchips">{links}</div>
<div class="wline">{word(con.get("lead_magnet_code_word"), "финал")}<span class="muted small">{E(con.get("also_ru"))}</span></div></div>
<div class="checklog"><div class="lbl">Проверка темы: {plural(len(w.get("check_log", [])), "версия", "версии", "версий")} до «принято»</div>
<div class="tscroll"><table class="ctable"><thead><tr><th>Версия темы</th>{heads}<th>Итог</th></tr></thead><tbody>{rows}</tbody></table></div></div>
</article></div></section>'''


def source_rows(sources):
    out = ""
    for s in sources:
        x = xfmt(s.get("x"))
        med = f' · медиана {k(s["channel_median"])}' if s.get("channel_median") else ""
        out += (f'<div class="src"><span class="xb {xcls(s.get("x"))}">{E(x or "—")}</span>'
                f'<div class="src-main"><b>{E(s.get("channel"))}</b><span>{E(s.get("title"))}</span></div>'
                f'<div class="src-meta">▶ {E(k(s.get("views")))}{E(med)} · {E(hms(s.get("duration")))} · {E((s.get("lang") or "").upper())}</div>'
                f'<a class="orig" href="{E(s.get("url"))}" target="_blank" rel="noopener" aria-label="Открыть видео">↗</a></div>')
    return out


def youtube_section():
    ys = ST.get("youtube", {})
    ri = ys.get("recommended_index", 0)
    topics = YT["topics"]
    rt = topics[ri]
    tl = "".join(f'<li><span class="tn">{i:02d}</span><p>{E(o)}</p></li>' for i, o in enumerate(rt.get("outline_ru", []), 1))
    bridges = ""
    for b in ys.get("bridges", []):
        if b["reel"] not in ALL_REELS:
            continue
        bridges += (f'<div class="bridge{" rec-b" if b.get("recommended") else ""}"><div class="bridge-h">🎬 {E(short_reel(b["reel"]))}'
                    f' <em>{day_short(b["date"])}</em>{" ⭐" if b.get("recommended") else ""}</div><p>«{E(b.get("new_ending_ru"))}»</p></div>')
    cb = ys.get("carousel_bridge")
    if cb:
        ct = next((c for c in CARS["carousels"] if c["code"] == cb.get("carousel")), None)
        cname = split_title(ct["title_ru"])[0].split(":")[0] if ct else code_label(cb.get("carousel"))
        cdate = f' <em>{day_short(CAR_CHOSEN[cb["carousel"]]["date"])}</em>' if cb.get("carousel") in CAR_CHOSEN else ""
        bridges += f'<div class="bridge"><div class="bridge-h">🗂 {E(cname)}{cdate}</div><p>{E(cb.get("line_ru"))}</p></div>'
    other_links = {}
    for ln in ys.get("other_links_ru", []):
        m = re.match(r"^Тема\s+(\d+)\s*\([^)]*\):\s*(.*)$", ln)
        if m:
            other_links[int(m.group(1))] = m.group(2)
            continue
        m = re.match(r"^«([^»]+)»:\s*(.*)$", ln, re.S)  # «Название темы»: какие рилсы ведут
        if m:
            key = m.group(1).lower()[:24]
            for ti, tp in enumerate(topics):
                if ti != ri and tp.get("title_ru", "").lower().startswith(key) and ti not in other_links:
                    other_links[ti] = m.group(2)
                    break
    others = ""
    alt_n = 0
    for i, t in enumerate(topics):
        if i == ri:
            continue
        alt_n += 1
        mx = max((s.get("x") or 0 for s in t.get("sources", [])), default=0)
        ol = "".join(f"<li>{E(o)}</li>" for o in t.get("outline_ru", []))
        link = f'<div class="yt-link">🔗 {E(other_links[i])}</div>' if i in other_links else ""
        others += f'''<article class="card yt-mini"><div class="yt-mini-top"><span class="mono muted">Запасная тема {alt_n}</span><span class="xb {xcls(mx)}">макс {E(xfmt(mx))}</span></div>
<h4>{E(t["title_ru"])}</h4><p class="clamp">{E(t.get("angle_ru"))}</p>
<div class="yt-meta">📚 {plural(len(t.get("sources", [])), "источник", "источника", "источников")} · 🎬 {E(t.get("reel_bridge_hint"))}</div>{link}
<div class="actions"><button class="btn" type="button" data-toggle="yto-{i}" aria-expanded="false">🗺 План видео</button>
<button class="btn" type="button" data-toggle="yts-{i}" aria-expanded="false">📚 Источники</button></div>
<div class="panel" id="yto-{i}" hidden><ol class="plain">{ol}</ol><p class="muted small">{E(t.get("why_now"))}</p></div>
<div class="panel" id="yts-{i}" hidden>{source_rows(t.get("sources", []))}</div></article>'''
    trends = ""
    for i, t in enumerate(YT.get("trends_ru", []), 1):
        idx = t.find(": ")
        if 0 < idx < 110:
            rest = t[idx + 2:]
            rest = rest[:1].upper() + rest[1:]
            trends += f'<div class="trend"><span class="tn">{i:02d}</span><b>{E(t[:idx])}</b><p>{E(rest)}</p></div>'
        else:
            trends += f'<div class="trend"><span class="tn">{i:02d}</span><p>{E(t)}</p></div>'
    return f'''<section class="sec" id="youtube"><div class="wrap">
{sec_head("05", "▶️", "YouTube-видео", "YouTube-видео недели",f"{plural(len(topics), 'тема', 'темы', 'тем')} из {YT['stats'].get('videos_found')} видео и {YT['stats'].get('channels_checked')} каналов. Рекомендуемая стыкуется с рилсами и воронкой недели.")}
<article class="card yt-rec rec"><div class="reel-top"><div class="chips">{chip("⭐", "Рекомендуем", "--accent", "star")}{chip("▶️", "выход " + day_short(ys.get("release_date") or WEEK_START), "--strong")}</div></div>
<h3 class="yt-title">{E(ys.get("title_ru") or rt["title_ru"])}</h3><p class="yt-angle">{E(rt.get("angle_ru"))}</p>
<div class="yt-grid"><div><div class="lbl">🗺 План видео</div><ol class="timeline">{tl}</ol></div>
<div><div class="lbl">📈 Почему эта тема</div><p class="yt-why">{E(ys.get("why_ru"))}</p>
<div class="lbl">📚 Источники · ×N к медиане канала</div><div class="srcs">{source_rows(rt.get("sources", []))}</div>
<p class="muted small">{E(rt.get("why_now"))}</p></div></div>
<div class="lbl">🔗 Что ведёт на YouTube-видео</div><div class="bridges">{bridges}</div></article>
<div class="subhead"><h3>Ещё {plural(len(topics) - 1, "тема", "темы", "тем")}</h3><p>Запас на следующие недели или замена, если рекомендуемая не ложится.</p></div>
<div class="yt-others">{others}</div>
<div class="subhead"><h3>📰 Тенденции недели</h3><p>Что сейчас набирает в длинных YouTube-видео по темам недели.</p></div>
<div class="trends">{trends}</div></div></section>'''


LM_COLORS = [("#FFD84D", "#FF8A4C"), ("#FF8A4C", "#9FB4FF"), ("#6FD3A0", "#5EC8F2")]


def lm_box(lm, i):
    g1, g2 = LM_COLORS[i % len(LM_COLORS)]
    items = "".join(f"<li>{E(x)}</li>" for x in lm.get("contents_ru", []))
    reels = "".join(f'<span class="rchip">🎬 {E(short_reel(c))} <em>{wd(ALL_REELS[c][1]["date"])}</em></span>'
                    for c in lm.get("reels", []) if c in ALL_REELS)
    car = ""
    if lm.get("carousel_code") and lm["carousel_code"] in CAR_CHOSEN:
        cc = CAR_CHOSEN[lm["carousel_code"]]
        ct = next((c for c in CARS["carousels"] if c["code"] == lm["carousel_code"]), None)
        name = split_title(ct["title_ru"])[0].split(":")[0] if ct else code_label(lm["carousel_code"])
        car = f'<span class="rchip">🗂 {E(name)} <em>{wd(cc["date"])}</em></span>'
    date = day_short(lm["release_date"]) if lm.get("release_date") else "без даты"
    return f'''<article class="lm" style="--g1:{g1};--g2:{g2}">
<div class="lm-cover"><div class="lm-cover-top"><span class="lm-emoji">{lm_emoji(lm.get("title_ru", ""), lm.get("format"))}</span><span class="lm-format">{E(lm.get("format"))}</span></div>
<div class="lm-cover-word">{E(lm.get("code_word_ru"))}</div><div class="lm-cover-foot"><span>✈️ Telegram</span><span>{E(date)}</span></div></div>
<div class="lm-body"><h4>{E(lm.get("title_ru"))}</h4><p class="lm-promise">{E(lm.get("promise_ru"))}</p>
<div class="lbl">Что внутри</div><ul class="checks">{items}</ul>
<div class="lm-foot"><div class="wline">{word(lm.get("code_word_ru"), "слово", "funnel")}<span class="effort">⏳ {E(lm.get("effort"))}</span></div>
<div class="lbl">Кто ведёт</div><div class="rchips">{reels}{car}</div>
<p class="muted small">{E(lm.get("why_ru"))}</p></div></div></article>'''


def telegram_section():
    boxes = "".join(lm_box(lm, i) for i, lm in enumerate(LM_MAIN))
    res = ""
    for lm in LM_RES:
        reels = "".join(f'<span class="rchip">🎬 {E(short_reel(c))} <em>{wd(ALL_REELS[c][1]["date"])}</em></span>'
                        for c in lm.get("reels", []) if c in ALL_REELS)
        items = "".join(f"<li>{E(x)}</li>" for x in lm.get("contents_ru", []))
        uid = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]", "_", lm.get("code_word_ru") or "x")
        res += f'''<article class="card lm-res"><div class="reel-top"><div class="chips">{chip("🧲", "запасной", "--muted")}{chip("📦", lm.get("format") or "", "--muted")}</div>{word(lm.get("code_word_ru"), "слово", "funnel")}</div>
<h4>{lm_emoji(lm.get("title_ru", ""), lm.get("format"))} {E(lm.get("title_ru"))}</h4><p>{E(lm.get("promise_ru"))}</p>
<div class="rchips">{reels}<span class="effort">⏳ {E(lm.get("effort"))}</span></div>
<div class="actions"><button class="btn" type="button" data-toggle="res-{uid}" aria-expanded="false">✓ Что внутри</button></div>
<div class="panel" id="res-{uid}" hidden><ul class="checks">{items}</ul><p class="muted small">{E(lm.get("why_ru"))}</p></div></article>'''
    p = POD
    bars = ""
    for i in range(56):
        env = 0.35 + 0.65 * abs(math.sin(i / 55 * math.pi * 2.3 + 0.4))
        h = 14 + 86 * env * (0.45 + 0.55 * abs(math.sin(i * 1.7) * math.cos(i * 0.63)))
        bars += f'<i style="--h:{min(h, 100):.0f}%;--d:{(i % 9) * 0.11:.2f}s"></i>'
    blocks = ""
    for b in p.get("outline_ru", []):
        m = re.match(r"^(\d+)\.\s*(.*)$", b.get("block", ""))
        n_, t_ = (m.group(1), m.group(2)) if m else ("", b.get("block", ""))
        pts = "".join(f"<li>{E(x)}</li>" for x in b.get("points", []))
        blocks += f'<div class="pblock"><span class="tn">{E(n_.zfill(2))}</span><h5>{E(t_)}</h5><ul>{pts}</ul></div>'
    lead = p.get("lead_in_reel")
    lead_chip = (f'<span class="rchip">🎬 {E(short_reel(lead))} <em>{wd(ALL_REELS[lead][1]["date"])}</em></span>'
                 if lead in ALL_REELS else "")
    pod = f'''<article class="pod" id="podcast"><div class="pod-top"><div class="pod-icon">🎙</div>
<div class="chips">{chip("✈️", "Telegram", "--tg")}{chip("🎙", "Подкаст · " + day_short(p["release_date"]), "--tg") if p.get("release_date") else ""}{chip("⏱", p.get("duration_hint") or "", "--muted")}</div></div>
<h3 class="pod-title">{E(p.get("title_ru"))}</h3>
<div class="wave" aria-hidden="true">{bars}</div>
<p class="pod-why">{E(p.get("why_ru"))}</p>
<div class="lbl">План выпуска · {plural(len(p.get("outline_ru", [])), "блок", "блока", "блоков")}</div><div class="pblocks">{blocks}</div>
<div class="pod-cta"><div><div class="lbl">Концовка рилса</div><p>«{E(p.get("cta_line_ru"))}»</p></div>
<div class="pod-cta-side">{word(p.get("code_word_ru"), "слово", "tg")}<div class="rchips">{lead_chip}</div></div></div>
<p class="muted small">{E(p.get("note_ru"))}</p></article>'''
    return f'''<section class="sec" id="telegram"><div class="wrap">
{sec_head("06", "✈️", "Telegram", "Лид-магниты и подкаст", "Всё, что бот присылает по кодовому слову из комментариев.")}
<div class="lm-grid" style="--cols:{max(1, min(3, len(LM_MAIN)))}">{boxes}</div>
<div class="info"><span>ℹ️</span><p>{E(ST.get("lead_magnets", {}).get("note_ru"))}</p></div>
{'<div class="subhead"><h3>Запасные лид-магниты</h3><p>Добавьте, если возьмёте рилс, который на них ведёт, или найдётся время на ещё один материал.</p></div><div class="res-grid">' + res + '</div>' if res else ''}
<div class="subhead"><h3>🎙 Подкаст недели</h3></div>{pod}</div></section>'''


def route_reel(rt):
    """Рилс маршрута строго по полю routes[].reel (не по дате календаря).
    → (название, день рилса, вариант ли, название рекомендуемого рилса того же дня)."""
    code = rt.get("reel")
    if code not in ALL_REELS:
        return code_label(code), rt.get("date"), False, ""
    r, day = ALL_REELS[code]
    variant = not r.get("recommended")
    rec = next((x for x in day["reels"] if x.get("recommended")), None)
    rec_title = short_reel(rec["code"]) if (variant and rec) else ""
    return short_reel(code), day["date"], variant, rec_title


def funnel_section():
    rows = ""
    for rt in ST.get("routes", []):
        title, rdate, variant, rec_title = route_reel(rt)
        vnote = (f'<span class="fvar">вариант дня · вместо ⭐ «{E(rec_title)}»</span>' if variant and rec_title
                 else ('<span class="fvar">вариант дня</span>' if variant else ""))
        rows += (f'<div class="froute{" variant" if variant else ""}"><span class="fday">{day_short(rdate or rt["date"])}</span>'
                 f'<div class="fnode reelnode">🎬 {E(title)}{vnote}</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode wordnode">💬 {E(rt["cta_word_ru"])}</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode botnode">🤖 бот</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode getnode">🎁 {E(rt["leads_to_ru"])}</div></div>')
    for cc in ST.get("carousels", {}).get("chosen", []):
        ct = next((c for c in CARS["carousels"] if c["code"] == cc["code"]), None)
        name = split_title(ct["title_ru"])[0].split(":")[0] if ct else code_label(cc["code"])
        rows += (f'<div class="froute"><span class="fday">{day_short(cc["date"])}</span>'
                 f'<div class="fnode reelnode car">🗂 {E(name)}</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode wordnode">💬 {E(cc["cta_word_ru"])}</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode botnode">🤖 бот</div><span class="farr" aria-hidden="true"></span>'
                 f'<div class="fnode getnode">🎁 {E(cc["leads_to_ru"])}</div></div>')
    routes = ST.get("routes", [])
    words = " · ".join(E(r["cta_word_ru"]) + (" <i>(вариант)</i>" if route_reel(r)[2] else "") for r in routes)
    wt = WARM.get("topic_ru", "").split(":")[0]
    rdays = [route_reel(r)[1] or r["date"] for r in routes]
    lm_names = " · ".join(f"«{split_title(x.get('title_ru', ''))[0].split(':')[0]}»" for x in LM_MAIN)
    chain = [("🎬", "Рилс-воронка", plural(len(routes), "рилс", "рилса", "рилсов") + (f" {wd(min(rdays))}–{wd(max(rdays))}" if routes else ""), "--accent"),
             ("💬", "Слово → бот в Telegram", words, "--tg"),
             ("🧲", plural(len(LM_MAIN), "лид-магнит", "лид-магнита", "лид-магнитов"), lm_names, "--funnel"),
             ("🔥", "Прогрев в сторис" + (f" · {wd(WARM_DATE)}" if WARM_DATE else ""), wt, "--hot")]
    if PRODUCT_ENTRY:
        chain.append(("📘", PRODUCT_ENTRY, "последние сторис прогрева ведут сюда", "--accent"))
    if PRODUCT_MAIN:
        chain.append(("🏆", PRODUCT_MAIN, "следующий шаг после " + ("книги" if "книг" in PRODUCT_ENTRY.lower() else "первой покупки"), "--outlier"))
    ch = ""
    for i, (e, t, s, cc) in enumerate(chain):
        if i:
            ch += '<div class="carr" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 12h14m-5-6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
        ch += f'<div class="cstep" style="--c:var({cc})"><span class="cemo">{e}</span><b>{E(t)}</b><span>{s if i == 1 else E(s)}</span></div>'
    n_steps = len(chain)
    return f'''<section class="sec" id="funnel"><div class="wrap">
{sec_head("07", "🔗", "Схема", "Воронка недели", ("Путь человека от ролика к продукту «" + PRODUCT_MAIN + "»" if PRODUCT_MAIN else "Путь человека от ролика до покупки") + ": настоящие слова и материалы этой недели.")}
<div class="chainflow">{ch}</div>
<div class="subhead"><h3>Маршруты по дням</h3></div><div class="froutes">{rows}</div>
<div class="fmerge"><div class="fm-line" aria-hidden="true"></div>
<div class="fm-card warmc"><span class="cemo">🔥</span><div><b>Прогрев в сторис{" · " + E(day_short(WARM_DATE)) if WARM_DATE else ""} догревает все маршруты</b><p>{E(WARM.get("topic_ru"))}</p></div></div>
<div class="fm-two"><a class="fm-card podc" href="#podcast"><span class="cemo">🎙</span><div><b>Подкаст · {E(day_short(POD["release_date"])) if POD.get("release_date") else ""}</b><p>{E(POD.get("title_ru"))}</p></div></a>
</div></div>
</div></section>'''


def nospeech_section():
    ns = REELS.get("no_speech", [])
    if not ns:
        return ""
    rows = "".join(
        f'<tr><td class="mono">{E(author(r.get("author")))}</td><td>{E(r.get("topic_ru"))}</td>'
        f'<td class="mono num">{E(k(r.get("comments")))}</td><td class="mono num">{E(k(r.get("views")))}</td>'
        f'<td>{chip("✨", "вау", "--outlier") if r.get("wow") else ""}</td>'
        f'<td><a class="orig" href="{E(r.get("url"))}" target="_blank" rel="noopener">↗</a></td></tr>' for r in ns)
    return f'''<section class="sec" id="nospeech"><div class="wrap">
{sec_head("08", "🔇", "Instagram · без речи", "Рилсы без речи", f"{len(ns)} роликов, где смысл в картинке и титрах, а не в голосе. В план не брали.")}
<div class="ask">🙋 Снимаете такие? — скажите агенту, и со следующей недели они войдут в подборку.</div>
<div class="tscroll card flush"><table class="ntable"><thead><tr><th>Автор</th><th>О чём</th><th>💬</th><th>▶</th><th></th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
</div></section>'''


def bars(steps, color="--accent"):
    mx = max(v for _, v in steps) or 1
    out = ""
    for i, (lbl, v) in enumerate(steps):
        w = max(4, 100 * v / mx)
        last = " last" if i == len(steps) - 1 else ""
        out += (f'<div class="fb{last}"><div class="fb-l"><span>{E(lbl)}</span><b>{num(v)}</b></div>'
                f'<div class="fb-t"><i style="width:{w:.1f}%;--c:var({color})"></i></div></div>')
    return out


def how_section():
    n = ST["numbers"]
    rs = REELS.get("stats", {})
    cs = CARS.get("stats", {})
    cols = [
        ("🎬", "Рилсы", bars([("в пуле", n["reels_unique"]), ("свежих англоязычных", n["reels_fresh"]),
                            ("расшифровано", n["reels_transcribed"]), ("в плане", n["reels_selected"])]),
         f'без речи: {rs.get("no_speech", 0)} · отсеяно: {rs.get("rejected_total", 0)}'),
        ("🗂", "Карусели", bars([("постов собрано", n["carousels_posts_collected"]), ("каруселей", n["carousels_found"]),
                               (f'от {cs.get("threshold_used", "")} комментариев', n["carousels_passed_threshold"]),
                               ("отобрано", n["carousels_selected"])], "--outlier"),
         f'в календаре: {len(CAR_CHOSEN)} · отклонено с причиной: {len(CARS.get("rejected", []))}'),
    ]
    cc = "".join(f'<div class="card how-col"><div class="how-h"><span>{e}</span><b>{E(t)}</b></div>{b}<div class="how-foot">{E(f)}</div></div>'
                 for e, t, b, f in cols)
    rej = rs.get("rejected_by_reason", {})
    mx = max(rej.values()) if rej else 1
    rr = "".join(f'<div class="rb"><span class="rb-l">{E(r)}</span><div class="rb-t"><i style="width:{100 * v / mx:.1f}%"></i></div><b>{v}</b></div>'
                 for r, v in sorted(rej.items(), key=lambda x: -x[1]))
    return f'''<section class="sec" id="how"><div class="wrap">
{sec_head("09", "🧪", "Методика", "Как собрано", "Воронка отбора цифрами: сколько нашли, сколько прочитали, сколько дошло до плана.")}
<div class="how-grid">{cc}</div>
<div class="card rej"><div class="rej-h"><b>Почему рилсы не прошли</b><span class="mono">{rs.get("rejected_total", 0)} из {rs.get("transcribed", 0)} расшифрованных</span></div>{rr}</div>
</div></section>'''


CSS = r"""
:root{--bg:#0B0E13;--card:#12161D;--card2:#171C25;--line:#232A35;--line2:#2E3643;--text:#E8ECF2;--muted:#8A94A6;
--accent:#FFD84D;--funnel:#FF8A4C;--outlier:#6FD3A0;--strong:#9FB4FF;--tg:#5EC8F2;--hot:#FF8A4C;
--fh:"Unbounded","Segoe UI",system-ui,sans-serif;--ft:"Golos Text","Segoe UI",system-ui,sans-serif;--fm:"JetBrains Mono",Consolas,monospace;
--glow:0 0 0 1px #FFD84D55,0 10px 40px -10px #FFD84D33}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--ft);font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:inherit}
p{margin:0}
h1,h2,h3,h4,h5{margin:0;font-family:var(--fh);letter-spacing:-.015em}
button{font:inherit;color:inherit}
.wrap{max-width:1240px;margin:0 auto;padding-inline:24px}
.mono{font-family:var(--fm)}.muted{color:var(--muted)}.small{font-size:13.5px;line-height:1.5}
::selection{background:#FFD84D;color:#0B0E13}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* nav */
.nav{position:sticky;top:0;z-index:50;background:rgba(11,14,19,.8);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.nav-in{display:flex;align-items:center;gap:16px;height:60px}
.brand{display:flex;align-items:center;gap:10px;font-family:var(--fh);font-weight:600;font-size:14px;text-decoration:none;white-space:nowrap}
.brand-dot{width:10px;height:10px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
.nav-links{flex:1;display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;min-width:0}
.nav-links::-webkit-scrollbar{display:none}
.nav-links a{padding:8px 12px;border-radius:999px;font-size:14px;color:var(--muted);text-decoration:none;white-space:nowrap;transition:.2s}
.nav-links a:hover{color:var(--text);background:var(--card)}
.nav-links a.active{color:#0B0E13;background:var(--accent)}
.counter{display:flex;align-items:baseline;gap:6px;padding:8px 14px;border-radius:999px;border:1px solid var(--line2);background:var(--card);font-size:14px;text-decoration:none;white-space:nowrap}
.counter b{font-family:var(--fm);color:var(--accent);font-size:16px}.counter span{font-family:var(--fm);color:var(--muted);font-size:12px}
.counter.on{border-color:#FFD84D66;box-shadow:var(--glow)}

/* hero */
.hero{position:relative;padding-block:72px 24px;overflow:hidden}
.hero-bg{position:absolute;inset:0;pointer-events:none;
background:radial-gradient(640px 380px at 78% 26%,rgba(255,216,77,.10),transparent 70%),radial-gradient(520px 320px at 8% 0%,rgba(159,180,255,.08),transparent 70%)}
.hero-bg::after{content:"";position:absolute;inset:0;background-image:linear-gradient(#232A35 1px,transparent 1px),linear-gradient(90deg,#232A35 1px,transparent 1px);background-size:48px 48px;opacity:.28;-webkit-mask-image:radial-gradient(ellipse 70% 60% at 70% 25%,#000 10%,transparent 70%);mask-image:radial-gradient(ellipse 70% 60% at 70% 25%,#000 10%,transparent 70%)}
.hero-in{position:relative;display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,.65fr);gap:48px;align-items:center}
.badge{display:inline-flex;align-items:center;gap:10px;padding:8px 14px;border-radius:999px;border:1px solid var(--line2);background:rgba(18,22,29,.7);font-size:14px;color:var(--muted)}
.badge .dot{width:8px;height:8px;border-radius:50%;background:var(--outlier);box-shadow:0 0 10px var(--outlier)}
h1{font-weight:800;font-size:clamp(38px,6.2vw,86px);line-height:1.02;letter-spacing:-.03em;margin:24px 0 32px}
h1 span{display:block;color:var(--accent);text-shadow:0 0 40px rgba(255,216,77,.25)}
.summary{list-style:none;margin:0;padding:0;display:grid;gap:16px;max-width:760px}
.summary li{display:grid;grid-template-columns:40px 1fr;gap:12px;align-items:start}
.summary b{font-family:var(--fm);font-size:13px;color:var(--accent);padding-top:4px}
.summary p{font-size:17px;line-height:1.55;color:#C9D0DB}
.hero-radar{position:relative}
.radar{width:100%;max-width:420px;display:block;margin-left:auto}
.sweep{transform-origin:200px 200px;animation:spin 7s linear infinite}
.ping{transform-box:fill-box;transform-origin:center;animation:ping 2.4s ease-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes ping{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.2);opacity:0}}
.hero-eb{margin:56px 0 16px}
.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;gap:12px;align-items:stretch}
.ct{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px 24px}
.ct b{display:block;font-family:var(--fm);font-weight:700;font-size:clamp(30px,3.6vw,48px);line-height:1;letter-spacing:-.03em}
.ct span{display:block;margin-top:8px;color:var(--muted);font-size:14px}
.ct.hot{border-color:#FFD84D66;box-shadow:var(--glow);background:linear-gradient(180deg,#1A1A14,var(--card))}
.ct.hot b{color:var(--accent)}
.arr{display:grid;place-items:center;color:var(--muted);font-family:var(--fm);font-size:20px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 24px}
.tile b{display:block;font-family:var(--fm);font-weight:700;font-size:30px;line-height:1.1;letter-spacing:-.02em}
.tile b small{font-size:15px;color:var(--muted);margin-left:6px;font-weight:500;letter-spacing:0}
.tile span{display:block;margin-top:4px;font-size:15px}
.tile em{display:block;font-style:normal;color:var(--muted);font-size:13px}
.inplan{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}
.pill-link{padding:9px 16px;border-radius:999px;border:1px solid var(--line2);background:rgba(18,22,29,.6);text-decoration:none;font-size:14.5px;transition:.2s}
.pill-link:hover{border-color:var(--accent);color:var(--accent)}

/* sections */
.sec{padding-block:88px 8px;scroll-margin-top:60px}
.sec-head{display:flex;gap:20px;align-items:flex-start;margin-bottom:40px}
.icon{flex:none;width:64px;height:64px;border-radius:18px;background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line2);display:grid;place-items:center;font-size:32px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 12px 30px -12px rgba(0,0,0,.6)}
.eyebrow{font-family:var(--fm);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
h2{font-weight:700;font-size:clamp(28px,4vw,46px);line-height:1.08;letter-spacing:-.025em;margin:6px 0 10px}
.lead{color:var(--muted);max-width:760px;font-size:17px}
.subhead{margin:56px 0 20px}
.subhead h3{font-size:22px;font-weight:600}
.subhead p{color:var(--muted);margin-top:6px;max-width:820px;font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:24px}
.card.flush{padding:0}
.rec{box-shadow:var(--glow);border-color:#FFD84D4D}
.lbl{font-family:var(--fm);font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:24px 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px;min-width:0}
.chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;font-size:12.5px;font-weight:500;line-height:1.25;color:var(--c,var(--muted));background:color-mix(in srgb,var(--c,#8A94A6) 11%,transparent);border:1px solid color-mix(in srgb,var(--c,#8A94A6) 30%,transparent);white-space:nowrap}
.chip.star{background:var(--accent);color:#0B0E13;border-color:var(--accent);font-weight:600}
.word{display:inline-flex;align-items:center;gap:8px;font-family:var(--fm);font-weight:700;font-size:13.5px;letter-spacing:.08em;padding:5px 13px 5px 6px;border-radius:999px;background:var(--accent);color:#0B0E13;white-space:nowrap}
.word i{font-style:normal;font-weight:500;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;background:rgba(11,14,19,.14);padding:3px 8px;border-radius:999px}
.word.funnel{background:var(--funnel)}.word.tg{background:var(--tg)}
.word.none{background:var(--card2);color:var(--muted);border:1px dashed var(--line2);letter-spacing:.02em;font-weight:500;white-space:normal}
.word.none i{background:var(--line)}
.was{font-size:12.5px;color:var(--muted);font-family:var(--fm)}
.wline{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-top:16px}
.leads{margin-top:8px;color:#C9D0DB;font-size:14.5px}
.rchips{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.rchip{display:inline-flex;gap:6px;align-items:baseline;padding:6px 12px;border-radius:12px;background:var(--card2);border:1px solid var(--line);font-size:13.5px;line-height:1.35}
.rchip em{font-style:normal;font-family:var(--fm);font-size:11.5px;color:var(--muted)}
.effort{font-size:13.5px;color:var(--muted)}
.info{display:flex;gap:12px;margin-top:24px;padding:16px 20px;border-radius:16px;background:var(--card2);border:1px solid var(--line);color:#C9D0DB;font-size:14.5px}
.tscroll{overflow-x:auto}

/* week */
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:-16px 0 20px;font-size:13px;color:var(--muted)}
.lg{display:inline-flex;align-items:center;gap:6px}.lg i{width:8px;height:8px;border-radius:3px;background:var(--c)}
.wk-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px}
.wk-day{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:12px;display:flex;flex-direction:column;gap:8px;min-width:0}
.wk-day.weekend{background:linear-gradient(180deg,#141A1A,var(--card))}
.wk-head{display:flex;align-items:baseline;gap:8px;padding:4px 4px 8px;border-bottom:1px solid var(--line)}
.wk-wd{font-family:var(--fh);font-weight:700;font-size:20px}
.wk-date{font-family:var(--fm);font-size:12px;color:var(--muted)}
.wk-n{margin-left:auto;font-family:var(--fm);font-size:11px;color:var(--muted);border:1px solid var(--line2);border-radius:999px;padding:1px 7px}
.wk-items{display:flex;flex-direction:column;gap:8px}
.wk-item{display:flex;flex-direction:column;gap:6px;padding:10px 10px 11px;border-radius:12px;background:var(--card2);border:1px solid var(--line);border-left:3px solid var(--c);text-decoration:none;transition:.2s;min-width:0}
.wk-item:hover{border-color:var(--c);transform:translateY(-1px)}
.wk-type{font-family:var(--fm);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--c)}
.wk-title{font-size:13px;line-height:1.35;overflow-wrap:anywhere}
.wk-word{align-self:flex-start;font-family:var(--fm);font-size:10.5px;font-weight:700;letter-spacing:.05em;color:#0B0E13;background:var(--c);padding:2px 7px;border-radius:6px;overflow-wrap:anywhere}
.wk-item[style*="--hot"]{border-left-color:transparent;border-image:linear-gradient(var(--accent),var(--funnel)) 1 / 0 0 0 3px}

/* tabs */
.tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;padding:6px;border-radius:20px;background:var(--card);border:1px solid var(--line);margin-bottom:24px;position:sticky;top:68px;z-index:20;box-shadow:0 12px 30px -14px rgba(0,0,0,.8)}
.tab{position:relative;display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:10px;align-items:baseline;text-align:left;padding:10px 14px;border-radius:14px;border:1px solid transparent;background:transparent;cursor:pointer;transition:.2s}
.tab:hover{background:var(--card2)}
.tab-wd{font-family:var(--fh);font-weight:700;font-size:20px;grid-row:1/3;align-self:center}
.tab-date{font-family:var(--fm);font-size:12px;color:var(--muted)}
.tab-word{font-family:var(--fm);font-size:11px;color:var(--muted);letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tab-count{position:absolute;top:8px;right:10px;font-family:var(--fm);font-size:11px;color:var(--outlier)}
.tab.active{background:var(--card2);border-color:#FFD84D66;box-shadow:inset 0 0 0 1px #FFD84D22}
.tab.active .tab-wd,.tab.active .tab-word{color:var(--accent)}
.day-panel{display:none}.day-panel.active{display:block;animation:fade .35s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.day-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin:8px 0 16px}
.day-head h3{font-size:24px;font-weight:600}.day-head span{color:var(--muted);font-size:14px}
.reel-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.reel.rec{grid-column:1/-1}
.reel{display:flex;flex-direction:column;min-width:0;transition:border-color .2s,box-shadow .2s}
.reel.taken{border-color:var(--outlier);box-shadow:0 0 0 1px #6FD3A055,0 10px 40px -12px #6FD3A033}
.reel.rec.taken{box-shadow:0 0 0 1px #6FD3A077,0 10px 40px -10px #FFD84D33}
.reel-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.reel-title{font-weight:600;font-size:19px;line-height:1.3;margin-top:16px;overflow-wrap:anywhere}
.reel-title.big{font-size:clamp(21px,2.3vw,28px);line-height:1.22;letter-spacing:-.02em}
.reel-sub{margin-top:8px;color:var(--muted);font-size:14.5px}
.mrow{margin-top:12px;font-family:var(--fm);font-size:13px;color:#C9D0DB}
.hook{margin:16px 0 0;padding:12px 16px;border-left:3px solid var(--accent);background:linear-gradient(90deg,rgba(255,216,77,.07),transparent);border-radius:0 12px 12px 0;font-size:16.5px;line-height:1.5;color:#F3F5F8}
.rec .hook{font-size:18px}
.why{margin-top:16px;padding:14px 16px;border-radius:14px;background:var(--card2);border:1px solid var(--line)}
.why-h{font-size:13px;font-weight:600;color:var(--accent);margin-bottom:6px}
.why p{font-size:14.5px;color:#C9D0DB}
.rec-body{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:24px}
.rec-side{display:flex;flex-direction:column;gap:16px;margin-top:16px}
.mgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.m{background:var(--card2);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.m b{display:block;font-family:var(--fm);font-weight:700;font-size:24px;line-height:1.1;letter-spacing:-.02em;white-space:nowrap}
.m b small{font-size:13px;color:var(--muted);margin-left:4px;font-weight:500;letter-spacing:0}
.m span{font-size:12.5px;color:var(--muted)}
.m.big b{font-size:30px}
.m.acc b{color:var(--accent)}
.side-word{background:var(--card2);border:1px solid var(--line);border-radius:14px;padding:14px}
.side-word .lbl{margin:0 0 4px}.side-word .wline{margin-top:6px}
.take{display:inline-flex;align-items:center;gap:8px;padding:6px 12px 6px 7px;border-radius:999px;border:1px solid var(--line2);background:var(--card2);cursor:pointer;user-select:none;font-size:14px;font-weight:500;transition:.2s;white-space:nowrap}
.take input{position:absolute;opacity:0;width:1px;height:1px}
.take .box{width:22px;height:22px;border-radius:7px;border:1.5px solid var(--line2);display:grid;place-items:center;transition:.2s}
.take .box::after{content:"✓";font-size:14px;font-weight:700;color:#0B0E13;opacity:0}
.take:hover{border-color:var(--outlier)}
.take:has(input:checked){background:color-mix(in srgb,var(--outlier) 16%,transparent);border-color:var(--outlier);color:var(--outlier)}
.take input:checked+.box{background:var(--outlier);border-color:var(--outlier)}
.take input:checked+.box::after{opacity:1}
.take input:focus-visible+.box{outline:2px solid var(--accent);outline-offset:2px}
.note{margin-top:12px;padding:12px 16px;border-radius:14px;border:1px dashed var(--line2);font-size:14px;color:#C9D0DB}
.note-h{display:block;font-size:12.5px;font-weight:600;color:var(--text);margin-bottom:4px}
.note.ending{border-style:solid;border-color:#9FB4FF44;background:rgba(159,180,255,.06)}
.note.ending .note-h{color:var(--strong)}
.note.warn .note-h{color:var(--funnel)}
.actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:20px;padding-top:16px;border-top:1px solid var(--line)}
.spacer{flex:1}
.btn{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;border-radius:12px;border:1px solid var(--line2);background:var(--card2);cursor:pointer;font-size:14px;font-weight:500;transition:.2s;white-space:nowrap}
.btn:hover{border-color:var(--muted)}
.btn.primary{background:var(--text);color:#0B0E13;border-color:var(--text)}
.btn.primary:hover{background:#fff}
.btn.on{border-color:var(--accent);color:var(--accent)}
.btn.primary.on{background:var(--accent);border-color:var(--accent);color:#0B0E13}
.btn.ok{border-color:var(--outlier);color:var(--outlier)}
.btn-meta{font-family:var(--fm);font-size:12px;opacity:.7}
.by{font-family:var(--fm);font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
.orig{font-size:12.5px;color:var(--muted);text-decoration:none;white-space:nowrap;border-bottom:1px solid transparent}
.orig:hover{color:var(--text);border-bottom-color:var(--muted)}
.panel{margin-top:12px;padding:20px 22px;border-radius:16px;background:var(--card2);border:1px solid var(--line);animation:fade .3s ease}
.panel-h{font-family:var(--fm);font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.panel p+p{margin-top:12px}
.script p{font-size:16px;line-height:1.65;max-width:760px}
.script .en{margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-size:13.5px;color:var(--muted)}
.shoot{margin:0;padding-left:18px;display:grid;gap:8px;font-size:14.5px;color:#C9D0DB}
.shoot li::marker{color:var(--accent)}
.pot+.pot{margin-top:14px}.pot b{font-size:14px}.pot p{font-size:14.5px;color:#C9D0DB;margin-top:4px}
.src[hidden]{display:none}

/* carousels */
.stack{display:grid;gap:24px}.stack>*,.car,.slides-wrap,.lm-grid>*,.yt-others>*,.res-grid>*,.how-grid>*,.trends>*{min-width:0}
.car-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:24px}
.car-side .why{margin-top:16px}
.slides-wrap{margin-top:24px}
.slides-h{display:flex;justify-content:space-between;font-family:var(--fm);font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.slides{display:grid;grid-auto-flow:column;grid-auto-columns:280px;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:10px;scrollbar-width:thin;scrollbar-color:var(--line2) transparent}
.slide{scroll-snap-align:start;aspect-ratio:1/1;border-radius:16px;background:linear-gradient(160deg,#1B212C,#141820);border:1px solid var(--line2);padding:16px;display:flex;flex-direction:column;min-width:0;overflow:hidden;position:relative}
.slide.cover{background:radial-gradient(120% 90% at 100% 0%,rgba(255,216,77,.22),transparent 60%),linear-gradient(160deg,#20242B,#12161D);border-color:#FFD84D55}
.slide.final{background:radial-gradient(120% 90% at 0% 100%,rgba(255,138,76,.22),transparent 60%),linear-gradient(160deg,#1E1C1C,#12161D);border-color:#FF8A4C55}
.sl-top{display:flex;justify-content:space-between;font-family:var(--fm);font-size:11px;color:var(--muted);margin-bottom:10px}
.save{color:var(--accent)}
.sl-body{flex:1;overflow-y:auto;min-height:0;scrollbar-width:thin;scrollbar-color:var(--line2) transparent;padding-right:2px}
.sl-head{font-family:var(--fh);font-weight:600;font-size:14px;line-height:1.3;margin-bottom:8px;color:var(--accent)}
.sl-text{font-size:13px;line-height:1.45;color:#DDE2EA}
.s-xl .sl-text{font-family:var(--fh);font-weight:600;font-size:21px;line-height:1.28;color:var(--text)}
.s-lg .sl-text{font-family:var(--fh);font-weight:600;font-size:16px;line-height:1.33;color:var(--text)}
.sl-more{display:none;color:var(--accent)}.slide.more .sl-more{display:inline}
.slide.more .sl-body{-webkit-mask-image:linear-gradient(180deg,#000 calc(100% - 36px),transparent);mask-image:linear-gradient(180deg,#000 calc(100% - 36px),transparent)}
.s-sm .sl-text{font-size:12px}
.sl-code{margin-top:8px;border-radius:10px;border:1px solid var(--line2);background:#0D1016;overflow:hidden}
.sl-bar{display:flex;align-items:center;gap:5px;padding:6px 8px;border-bottom:1px solid var(--line);font-family:var(--fm);font-size:10px;color:var(--muted)}
.sl-bar i{width:7px;height:7px;border-radius:50%;background:var(--line2)}.sl-bar i:first-child{background:#FF8A4C99}.sl-bar i:nth-child(2){background:#FFD84D99}.sl-bar i:nth-child(3){background:#6FD3A099;margin-right:4px}
.sl-pr{padding:8px 10px;font-family:var(--fm);font-size:10.5px;line-height:1.5;color:#C9D0DB}
.vnote{display:block;margin:6px 0;font-family:var(--ft);font-weight:400;font-size:11.5px;line-height:1.4;font-style:italic;color:var(--muted);text-transform:none}
mark{background:var(--accent);color:#0B0E13;border-radius:4px;padding:0 4px;font-family:var(--fm);font-weight:700}

/* warmup */
.warm{position:relative;border-radius:24px;padding:32px;background:radial-gradient(900px 300px at 0% 0%,rgba(255,138,76,.10),transparent 60%),radial-gradient(700px 260px at 100% 0%,rgba(255,216,77,.08),transparent 60%),var(--card);border:1px solid var(--line);overflow:hidden}
.warm::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:linear-gradient(180deg,var(--accent),var(--funnel))}
.warm-top{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.hotchip{background:linear-gradient(90deg,var(--accent),var(--funnel));color:#0B0E13;border:0;font-weight:600}
.warm-title{font-weight:700;font-size:clamp(24px,3.2vw,38px);line-height:1.15;margin-top:18px;letter-spacing:-.02em}
.warm-title span{display:block;margin-top:8px;font-family:var(--ft);font-weight:500;font-size:clamp(17px,1.8vw,21px);color:#C9D0DB;letter-spacing:0;line-height:1.4}
.warm-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:24px}
.wbox{padding:18px 20px;border-radius:16px;background:rgba(23,28,37,.8);border:1px solid var(--line)}
.wbox .lbl{margin-top:0}.wbox p{font-size:15px;color:#C9D0DB}
.reveal{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.reveal li{display:flex;gap:12px;padding:16px;border-radius:16px;background:rgba(23,28,37,.8);border:1px solid var(--line)}
.dbadge{flex:none;width:38px;height:38px;border-radius:12px;display:grid;place-items:center;font-family:var(--fh);font-weight:700;font-size:13px;color:#0B0E13;background:linear-gradient(135deg,var(--accent),var(--funnel))}
.reveal b{display:block;font-size:15px;margin-bottom:4px}
.reveal p{font-size:14px;color:#C9D0DB}
.warm-leads .wline{margin-top:12px}
.checklog{margin-top:8px}
.ctable{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;min-width:760px}
.ctable th,.ctable td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.ctable thead th{font-family:var(--fm);font-weight:500;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.ctable tbody th{font-weight:500;width:230px;min-width:200px;color:#C9D0DB}
.ctable tr.ok th{color:var(--text)}
.ver{display:inline-block;font-family:var(--fm);font-size:11px;color:var(--muted);border:1px solid var(--line2);border-radius:6px;padding:0 5px;margin-right:8px}
.ck{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:6px;font-size:12px;font-weight:700;margin-right:6px;vertical-align:-4px}
.ck.yes{background:#6FD3A022;color:var(--outlier)}.ck.no{background:#FF8A4C22;color:var(--funnel)}.ck.part{background:#FFD84D22;color:var(--accent)}
.ck-t{color:var(--muted);font-size:12px}
.verdict{display:inline-block;font-family:var(--fm);font-size:11.5px;color:var(--funnel)}.verdict.ok{color:#0B0E13;background:var(--outlier);padding:2px 8px;border-radius:6px}

/* youtube */
.yt-rec{padding:32px}
.yt-title{font-weight:700;font-size:clamp(24px,3vw,36px);line-height:1.18;margin-top:18px;letter-spacing:-.02em}
.yt-angle{margin-top:14px;font-size:17px;color:#C9D0DB;max-width:900px}
.yt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:32px}
.timeline{list-style:none;margin:0;padding:0;position:relative}
.timeline::before{content:"";position:absolute;left:17px;top:10px;bottom:10px;width:2px;background:linear-gradient(var(--strong),var(--line))}
.timeline li{position:relative;display:grid;grid-template-columns:36px 1fr;gap:14px;padding:6px 0}
.tn{font-family:var(--fm);font-size:11.5px;font-weight:700;color:var(--muted)}
.timeline .tn{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:var(--card);border:1.5px solid var(--strong);color:var(--strong);position:relative;z-index:1}
.timeline li:first-child .tn{background:var(--strong);color:#0B0E13}
.timeline p{font-size:15px;padding-top:6px;color:#DDE2EA}
.yt-why{font-size:15px;color:#C9D0DB}
.srcs{display:grid;gap:8px;margin-bottom:12px}
.src{display:grid;grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:"x main link" "x meta link";column-gap:12px;row-gap:2px;align-items:center;padding:10px 12px;border-radius:14px;background:var(--card2);border:1px solid var(--line)}
.panel .src+.src{margin-top:8px}
.src .xb{grid-area:x}.src-main{grid-area:main;min-width:0}.src-meta{grid-area:meta;font-family:var(--fm);font-size:11.5px;color:var(--muted)}.src .orig{grid-area:link;font-size:16px}
.src-main b{font-size:14px;margin-right:8px}.src-main span{font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.xb{display:inline-grid;place-items:center;min-width:58px;padding:5px 8px;border-radius:10px;font-family:var(--fm);font-weight:700;font-size:13px;white-space:nowrap}
.x-hi{background:var(--accent);color:#0B0E13}.x-mid{background:#6FD3A022;color:var(--outlier);border:1px solid #6FD3A055}.x-lo,.x-none{background:var(--card);color:var(--muted);border:1px solid var(--line2)}
.bridges{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.bridge{padding:14px 16px;border-radius:14px;background:var(--card2);border:1px solid var(--line)}
.bridge.rec-b{border-color:#9FB4FF44}
.bridge-h{font-weight:600;font-size:14px;margin-bottom:6px}.bridge-h em{font-style:normal;font-family:var(--fm);font-size:11.5px;color:var(--muted)}
.bridge p{font-size:14px;color:#C9D0DB}
.yt-others{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.yt-mini{display:flex;flex-direction:column}
.yt-mini-top{display:flex;justify-content:space-between;align-items:center}
.yt-mini h4{font-weight:600;font-size:18px;line-height:1.3;margin-top:12px}
.yt-mini .clamp{margin-top:10px;font-size:14.5px;color:#C9D0DB;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.yt-meta{margin-top:12px;font-size:13.5px;color:var(--muted)}
.yt-link{margin-top:8px;font-size:13.5px;color:var(--strong)}
.yt-mini .actions{margin-top:auto;padding-top:16px}
.yt-mini .actions{border-top:0}
.plain{margin:0 0 12px;padding-left:20px;display:grid;gap:6px;font-size:14px;color:#C9D0DB}
.trends{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.trend{padding:18px 20px;border-radius:18px;background:var(--card);border:1px solid var(--line)}
.trend .tn{display:block;color:var(--strong);margin-bottom:8px}
.trend b{display:block;font-size:15px;line-height:1.35;margin-bottom:6px}
.trend p{font-size:14px;color:var(--muted)}

/* telegram */
.lm-grid{display:grid;grid-template-columns:repeat(var(--cols,3),minmax(0,1fr));gap:16px}
.lm{display:flex;flex-direction:column;border-radius:22px;background:var(--card);border:1px solid var(--line);overflow:hidden;min-width:0}
.lm-cover{position:relative;height:210px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;color:#0B0E13;background:
linear-gradient(135deg,var(--g1),var(--g2));overflow:hidden}
.lm-cover::before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(135deg,rgba(255,255,255,.09) 0 2px,transparent 2px 14px);pointer-events:none}
.lm-cover::after{content:"";position:absolute;left:0;top:0;bottom:0;width:18px;background:linear-gradient(90deg,rgba(0,0,0,.22),rgba(0,0,0,0))}
.lm-cover-top{position:relative;display:flex;justify-content:space-between;align-items:flex-start}
.lm-emoji{width:64px;height:64px;border-radius:18px;display:grid;place-items:center;font-size:36px;background:rgba(255,255,255,.35);box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 10px 20px -8px rgba(0,0,0,.35)}
.lm-format{font-family:var(--fm);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;background:rgba(11,14,19,.85);color:#fff;padding:4px 9px;border-radius:999px}
.lm-cover-word{position:relative;font-family:var(--fh);font-weight:800;font-size:clamp(24px,2.3vw,32px);letter-spacing:-.01em;line-height:1;overflow-wrap:anywhere}
.lm-cover-foot{position:relative;display:flex;justify-content:space-between;font-family:var(--fm);font-size:12px;font-weight:700;opacity:.8}
.lm-body{padding:22px;display:flex;flex-direction:column;flex:1}
.lm-body h4{font-weight:600;font-size:19px;line-height:1.3}
.lm-promise{margin-top:10px;font-size:15px;color:#C9D0DB}
.checks{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.checks li{position:relative;padding-left:28px;font-size:14px;line-height:1.45;color:#DDE2EA}
.checks li::before{content:"✓";position:absolute;left:0;top:1px;width:19px;height:19px;border-radius:6px;display:grid;place-items:center;font-size:11px;font-weight:700;background:#6FD3A022;color:var(--outlier)}
.lm-foot{margin-top:auto;padding-top:8px}
.lm-foot .small{margin-top:14px}
.res-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.lm-res{border-style:dashed}
.lm-res h4{font-weight:600;font-size:18px;line-height:1.3;margin:14px 0 8px}
.lm-res>p{font-size:14.5px;color:#C9D0DB;margin-bottom:12px}
.pod{margin-top:0;border-radius:24px;padding:32px;background:radial-gradient(800px 300px at 100% 0%,rgba(94,200,242,.12),transparent 60%),var(--card);border:1px solid #5EC8F233;scroll-margin-top:80px}
.pod-top{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.pod-icon{width:64px;height:64px;border-radius:18px;display:grid;place-items:center;font-size:34px;background:linear-gradient(135deg,#5EC8F2,#9FB4FF);box-shadow:0 10px 30px -10px #5EC8F288}
.pod-title{font-weight:700;font-size:clamp(22px,2.8vw,34px);line-height:1.2;margin-top:20px;letter-spacing:-.02em}
.wave{display:flex;align-items:center;gap:3px;height:72px;margin:24px 0}
.wave i{flex:1;min-width:2px;height:var(--h);border-radius:3px;background:linear-gradient(180deg,var(--tg),var(--strong));opacity:.85;animation:wave 1.6s ease-in-out infinite alternate;animation-delay:var(--d);transform-origin:center}
@keyframes wave{from{transform:scaleY(.35)}to{transform:scaleY(1)}}
.pod-why{font-size:15.5px;color:#C9D0DB;max-width:960px}
.pblocks{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.pblock{padding:16px 18px;border-radius:16px;background:var(--card2);border:1px solid var(--line)}
.pblock .tn{color:var(--tg)}
.pblock h5{font-weight:600;font-size:15px;line-height:1.3;margin:6px 0 8px}
.pblock ul{margin:0;padding-left:16px;display:grid;gap:4px;font-size:13.5px;color:#C9D0DB}
.pblock li::marker{color:var(--tg)}
.pod-cta{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:20px;align-items:center;margin-top:20px;padding:18px 20px;border-radius:16px;background:rgba(94,200,242,.07);border:1px solid #5EC8F233}
.pod-cta .lbl{margin-top:0}.pod-cta p{font-size:16px}
.pod-cta-side{display:flex;flex-direction:column;gap:10px;align-items:flex-start}
.pod>.small{margin-top:14px}

/* funnel */
.chainflow{display:flex;align-items:stretch}
.cstep{flex:1 1 0;display:flex;flex-direction:column;gap:6px;padding:18px 16px;border-radius:18px;background:var(--card);border:1px solid var(--line);min-width:0;position:relative}
.carr{flex:0 0 28px}
.cstep i{font-style:normal;font-weight:400;color:var(--muted)}
.fvar{display:block;margin-top:4px;font-size:12px;color:var(--accent);font-family:var(--fm);letter-spacing:.02em}
.froute.variant{border-style:dashed}
.cstep{border-top:3px solid var(--c)}
.cemo{font-size:28px;line-height:1}
.cstep b{font-size:15px;line-height:1.3}
.cstep span:last-child{font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.carr{display:grid;place-items:center;color:var(--muted)}
.froutes{display:grid;gap:10px}
.froute{display:grid;grid-template-columns:72px minmax(0,1.3fr) 28px minmax(0,.7fr) 28px auto 28px minmax(0,1.3fr);align-items:center;gap:0;padding:10px;border-radius:16px;background:var(--card);border:1px solid var(--line)}
.fday{font-family:var(--fm);font-size:12px;color:var(--muted);padding-left:6px}
.fnode{padding:10px 12px;border-radius:12px;background:var(--card2);border:1px solid var(--line);font-size:14px;line-height:1.35;min-width:0;overflow-wrap:anywhere}
.wordnode{font-family:var(--fm);font-weight:700;letter-spacing:.05em;color:#0B0E13;background:var(--accent);border-color:var(--accent);text-align:center}
.botnode{color:var(--tg);border-color:#5EC8F244;white-space:nowrap}
.getnode{border-color:#FF8A4C44;background:rgba(255,138,76,.07)}
.reelnode.car{border-color:#6FD3A044}
.farr{height:2px;margin:0 4px;background:var(--line2);position:relative}
.farr::after{content:"";position:absolute;right:-1px;top:-4px;border:5px solid transparent;border-left:7px solid var(--line2);border-right:0}
.fmerge{position:relative;margin-top:16px;display:grid;gap:12px}
.fm-card{display:flex;gap:16px;align-items:flex-start;padding:20px 22px;border-radius:18px;background:var(--card);border:1px solid var(--line);text-decoration:none}
.fm-card b{display:block;font-size:15px;margin-bottom:4px}.fm-card p{font-size:14.5px;color:#C9D0DB}
.warmc{border-color:transparent;background:linear-gradient(var(--card),var(--card)) padding-box,linear-gradient(90deg,var(--accent),var(--funnel)) border-box;border:1px solid transparent}
.fm-two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.podc{border-color:#5EC8F244}.ytc{border-color:#9FB4FF44}
.podc:hover,.ytc:hover{transform:translateY(-1px)}

/* no speech */
.ask{display:inline-flex;margin-bottom:16px;padding:12px 18px;border-radius:14px;background:rgba(111,211,160,.08);border:1px solid #6FD3A044;color:var(--outlier);font-size:15px}
.ntable{width:100%;border-collapse:collapse;font-size:14.5px;min-width:720px}
.ntable th{font-family:var(--fm);font-weight:500;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);text-align:left;padding:14px 16px;border-bottom:1px solid var(--line)}
.ntable td{padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top;color:#DDE2EA}
.ntable tr:last-child td{border-bottom:0}
.ntable td.mono{font-size:13px;color:var(--text);white-space:nowrap}
.ntable td.num{color:var(--accent)}

/* how */
.how-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.how-h{display:flex;align-items:center;gap:10px;margin-bottom:18px}.how-h span{font-size:24px}.how-h b{font-family:var(--fh);font-weight:600;font-size:18px}
.fb+.fb{margin-top:14px}
.fb-l{display:flex;justify-content:space-between;gap:12px;font-size:14px;color:#C9D0DB;margin-bottom:6px}
.fb-l b{font-family:var(--fm);color:var(--text)}
.fb.last .fb-l b{color:var(--accent)}
.fb-t{height:10px;border-radius:999px;background:var(--card2);overflow:hidden}
.fb-t i{display:block;height:100%;border-radius:999px;background:color-mix(in srgb,var(--c) 55%,#232A35)}
.fb.last .fb-t i{background:var(--c);box-shadow:0 0 12px var(--c)}
.how-foot{margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
.rej{margin-top:16px}
.rej-h{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin-bottom:18px}.rej-h b{font-family:var(--fh);font-weight:600;font-size:18px}.rej-h span{color:var(--muted);font-size:13px}
.rb{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr) 40px;gap:16px;align-items:center;padding:6px 0}
.rb-l{font-size:14px;color:#C9D0DB}
.rb-t{height:12px;border-radius:999px;background:var(--card2);overflow:hidden}
.rb-t i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#FF8A4C66,var(--funnel))}
.rb b{font-family:var(--fm);text-align:right}
.foot{padding-block:72px 48px;color:var(--muted);font-size:13.5px;text-align:center}
.foot b{font-family:var(--fh);font-weight:600;color:var(--text)}

@media (max-width:1100px){
.hero-in{grid-template-columns:1fr}.hero-radar{display:none}
.chain{grid-template-columns:1fr 1fr;}.arr{display:none}.tiles{grid-template-columns:1fr 1fr}
.wk-grid{grid-template-columns:1fr}.wk-day{display:grid;grid-template-columns:110px 1fr;gap:12px;align-items:start}
.wk-head{flex-direction:column;align-items:flex-start;gap:2px;border-bottom:0;border-right:1px solid var(--line);height:100%}.wk-n{margin-left:0;margin-top:6px}
.wk-items{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
.chainflow{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.carr{display:none}
.froute{grid-template-columns:64px minmax(0,1fr) 20px auto;row-gap:8px}
.froute .farr:nth-of-type(3){display:none}
.froute .botnode{display:none}.froute .farr:nth-of-type(4){display:none}
.froute .getnode{grid-column:2/-1}
.trends{grid-template-columns:1fr 1fr}.lm-grid{grid-template-columns:1fr 1fr}.reveal{grid-template-columns:1fr 1fr}
.how-grid{grid-template-columns:1fr}
}
@media (max-width:860px){
.rec-body,.car-grid,.yt-grid,.warm-grid,.pod-cta{grid-template-columns:1fr}
.reel-grid{grid-template-columns:1fr}.yt-others,.res-grid,.bridges,.fm-two{grid-template-columns:1fr}
.tabs{top:64px}.tab{grid-template-columns:1fr;padding:8px 10px}.tab-wd{grid-row:auto;font-size:17px}.tab-word{display:none}
.rb{grid-template-columns:1fr 40px}.rb-t{grid-column:1/-1;grid-row:2}
}
@media (max-width:640px){
.wrap{padding-inline:16px}
.nav-in{gap:8px;height:56px}.brand{display:none}.nav-links a{padding:7px 10px;font-size:13.5px}.counter{padding:7px 10px;font-size:13px}.counter span{display:none}
.hero{padding-block:40px 16px}h1{margin:18px 0 24px}.summary li{grid-template-columns:28px 1fr;gap:8px}.summary p{font-size:15.5px}
.hero-eb{margin-top:40px}.ct{padding:14px 16px}.tile{padding:14px 16px}.tile b{font-size:24px}
.sec{padding-block:64px 8px}.sec-head{gap:14px;margin-bottom:28px}.icon{width:48px;height:48px;font-size:24px;border-radius:14px}
.lead{font-size:15.5px}
.wk-day{grid-template-columns:1fr}.wk-head{flex-direction:row;align-items:baseline;gap:8px;border-right:0;border-bottom:1px solid var(--line)}
.ntable{min-width:0}.ntable thead{display:none}
.ntable tr{display:grid;grid-template-columns:auto auto 1fr auto auto;column-gap:14px;row-gap:6px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line)}
.ntable tr:last-child{border-bottom:0}.ntable td{padding:0;border:0!important}
.ntable td:nth-child(1){grid-row:1;grid-column:1/4}.ntable td:nth-child(5){grid-row:1;grid-column:4}.ntable td:nth-child(6){grid-row:1;grid-column:5}
.ntable td:nth-child(2){grid-row:2;grid-column:1/-1}.ntable td:nth-child(3){grid-row:3;grid-column:1}.ntable td:nth-child(4){grid-row:3;grid-column:2}
.ntable td:nth-child(3)::before{content:"💬 "}.ntable td:nth-child(4)::before{content:"▶ "}.wk-n{margin-left:auto;margin-top:0}
.wk-items{grid-template-columns:1fr}
.card{padding:18px;border-radius:18px}.yt-rec,.warm,.pod{padding:22px 18px}
.tabs{gap:4px;padding:4px;border-radius:16px}.tab{padding:8px 4px;text-align:center;border-radius:12px}.tab-date{font-size:10.5px}.tab-count{top:3px;right:4px;font-size:9.5px}
.m b{font-size:20px}.m.big b{font-size:22px}
.actions .spacer{display:none}.btn{padding:8px 11px;font-size:13.5px}
.chainflow{grid-template-columns:1fr 1fr}
.froute{grid-template-columns:1fr;padding:12px}.froute .farr{display:none}.froute .getnode{grid-column:auto}.fday{padding-left:2px}
.wordnode{justify-self:start}
.trends,.lm-grid,.reveal{grid-template-columns:1fr}
.slides{grid-auto-columns:78%}
.warm::before{width:4px}
.pblocks{grid-template-columns:1fr}
}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}html{scroll-behavior:auto}}
@media print{
:root{--bg:#fff;--card:#fff;--card2:#F5F6F8;--line:#DDE1E7;--line2:#CBD1DA;--text:#1F2430;--muted:#5C6677;--accent:#C99A00;--glow:none}
body{background:#fff;color:#1F2430;font-size:12px}
.nav,.hero-radar,.tabs,.actions,.take,.hero-bg,.wave,.slides-h .hint{display:none!important}
.day-panel{display:block!important;break-inside:auto}.panel[hidden]{display:block!important}
.card,.warm,.pod,.lm,.trend,.wk-day,.ct,.tile{box-shadow:none!important;background:#fff!important;break-inside:avoid}
.summary p,.why p,.hook,.note,.script p,.shoot,.pot p,.lead,.yt-angle,.yt-why,.pod-why,.reveal p,.wbox p,.checks li,.fm-card p,.ntable td,.rb-l,.fb-l,.bridge p,.pblock ul,.trend p,.sl-text,.sl-pr{color:#1F2430!important}
.hook{background:#FFF8D6}.slides{grid-auto-flow:row;grid-template-columns:repeat(3,1fr);overflow:visible}.slide{aspect-ratio:auto;background:#fff!important;color:#1F2430}.sl-body{overflow:visible}
.sl-head,h1 span,.m.acc b{color:#8A6A00!important;text-shadow:none}.s-xl .sl-text{color:#1F2430}
.sec{padding-block:24px}.reel-grid{grid-template-columns:1fr}
a{text-decoration:none}
}
"""

JS = r"""
(function(){
var KEY='cp2-take-__WEEK__';var taken={};
try{taken=JSON.parse(localStorage.getItem(KEY)||'{}')||{}}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(taken))}catch(e){}}
var boxes=[].slice.call(document.querySelectorAll('.take input'));
function refresh(){var n=0;boxes.forEach(function(b){var on=!!taken[b.dataset.code];b.checked=on;var c=b.closest('.reel');if(c)c.classList.toggle('taken',on);if(on)n++;});
document.querySelectorAll('[data-count]').forEach(function(e){e.textContent=n});
var ctr=document.querySelector('.counter');if(ctr)ctr.classList.toggle('on',n>0);
document.querySelectorAll('.tab').forEach(function(t){var k=t.dataset.codes.split(',').filter(function(c){return taken[c]}).length;t.querySelector('.tab-count').textContent=k?('✓'+k):'';});}
boxes.forEach(function(b){b.addEventListener('change',function(){if(b.checked)taken[b.dataset.code]=1;else delete taken[b.dataset.code];save();refresh();});});
refresh();
var tabs=[].slice.call(document.querySelectorAll('.tab'));
function show(id){tabs.forEach(function(t){var on=t.dataset.target===id;t.classList.toggle('active',on);t.setAttribute('aria-selected',on?'true':'false');});
document.querySelectorAll('.day-panel').forEach(function(p){p.classList.toggle('active',p.id===id)});}
tabs.forEach(function(t,i){t.addEventListener('click',function(){show(t.dataset.target)});
t.addEventListener('keydown',function(e){var j=e.key==='ArrowRight'?i+1:e.key==='ArrowLeft'?i-1:-9;if(j>-9){j=(j+tabs.length)%tabs.length;tabs[j].focus();show(tabs[j].dataset.target);}});});
document.querySelectorAll('[data-goto-day]').forEach(function(a){a.addEventListener('click',function(){show(a.dataset.gotoDay)});});
document.querySelectorAll('[data-toggle]').forEach(function(b){b.addEventListener('click',function(){var p=document.getElementById(b.dataset.toggle);if(!p)return;var open=p.hidden;p.hidden=!open;b.setAttribute('aria-expanded',open?'true':'false');b.classList.toggle('on',open);});});
document.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){var t=document.getElementById(b.dataset.copy).value;
function done(){var o=b.innerHTML;b.innerHTML='✓ Скопировано';b.classList.add('ok');setTimeout(function(){b.innerHTML=o;b.classList.remove('ok')},1600);}
function fallback(){var ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(e){}ta.remove();done();}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(done,fallback)}else{fallback()}});});
var links=[].slice.call(document.querySelectorAll('.nav-links a'));var navl=document.querySelector('.nav-links');
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){links.forEach(function(l){var on=l.getAttribute('href')==='#'+e.target.id;l.classList.toggle('active',on);
if(on&&navl){navl.scrollTo({left:l.offsetLeft-navl.clientWidth/2+l.clientWidth/2,behavior:'smooth'})}});}});},{rootMargin:'-40% 0px -55% 0px'});
document.querySelectorAll('section[id]').forEach(function(s){io.observe(s)});}
function marks(){document.querySelectorAll('.slide').forEach(function(s){var b=s.querySelector('.sl-body');s.classList.toggle('more',b.scrollHeight>b.clientHeight+4);});}
marks();window.addEventListener('load',marks);if(document.fonts&&document.fonts.ready)document.fonts.ready.then(marks);
document.querySelectorAll('.sl-body').forEach(function(b){b.addEventListener('scroll',function(){if(b.scrollTop+b.clientHeight>=b.scrollHeight-6)b.parentNode.classList.remove('more');});});
window.addEventListener('beforeprint',function(){document.querySelectorAll('.panel[hidden]').forEach(function(p){p.dataset.ph='1';p.hidden=false});});
window.addEventListener('afterprint',function(){document.querySelectorAll('.panel[data-ph]').forEach(function(p){p.hidden=true;delete p.dataset.ph});});
})();
"""


def build_page():
    today = dt.date.today()
    body = (nav() + hero() + "<main>" + week() + reels_section() + stories_section() + carousels_section() + warmup_section()
            + telegram_section() + funnel_section() + nospeech_section() + how_section() + "</main>"
            + f'<footer class="foot"><b>Контент-план</b><br>{E(ST.get("week"))} · для {E(genitive(ST.get("client")))} · собрано {today.day} {MONTHS[today.month - 1]} {today.year}<br>'
              f'Ссылки на оригиналы только для сверки. Картинок чужих роликов на странице нет.</footer>')
    title = f"Контент-план · {WEEK_TXT}"
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="color-scheme" content="dark">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&family=Unbounded:wght@500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
{body}
<script>{JS.replace("__WEEK__", WEEK_START)}</script></body></html>'''


def render(base):
    """Собрать plan-<дата>.html в папке недели и вернуть путь к нему."""
    init(base)
    out = BASE / f"plan-{WEEK_START}.html"
    out.write_text(build_page(), encoding="utf-8")
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit("python -m integrations.content_plan.render <папка_недели>")
    out = render(sys.argv[1])
    print(f"OK {out.name}: {out.stat().st_size / 1024:.1f} КБ")


if __name__ == "__main__":
    main()
