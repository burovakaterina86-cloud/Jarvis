"""Вёрстка интерактивного HTML-гайда: `lead-magnet.json` -> самодостаточный HTML.

    python -m integrations.visuals.guide <папка>

Читает `<папка>/lead-magnet.json` тем же контрактом, что `leadmagnet.py`
(`load_data` переиспользуется оттуда, а не дублируется — тот же формат
`title`/`subtitle`/`author`/`intro`/`sections[]`/`cta`/`photo`,
`.autopilot/2026-09-23-lead-magnets--wip/contract.md`).

Вёрстка — не система каруселей (`ESSA_PRESENTATION_STYLE.md`, `tokens.py`).
Она прямо спросила «а откуда ты взял этот стиль? разве это мой стиль?» про
PDF в карусельной системе — для гайдов у неё свой стиль. Палитра, шрифт
(Montserrat) и приёмы (тёмно-зелёный первый экран с плашкой-«таблеткой»,
липкая навигация, кремовые разделы, белые карточки, нумерованные кружки)
сняты с её собственных файлов `essa-ai/visual_references/интерактивные
гайды/*.html` и записаны в контракте выше, раздел «поправка владелицы»
2026-09-23 (DESIGN.md §19 — тот же принцип: понятный воспроизводимый
материал, без цвета/шрифта каруселей).

Всё — CSS, JS, шрифт (через Google Fonts) и её портрет (`photo` в JSON,
base64) — внутри одного файла: он должен открываться где угодно, как её
собственные гайды.

Восьмипроцессная таблица (раздел с `table` в JSON) — интерактивная: часы
в неделю и раздражение вводит читатель, частоту выбирает из подписей
(числовая шкала частоты не задана текстом лид-магнита — решение вёрстки,
см. FREQUENCY_SCALE и CONCERNS отчёта), итог по формуле «Частота × Время ×
Раздражение» считается в браузере, самая тяжёлая строка подсвечивается
оранжевым. Ввод сохраняется в localStorage; обёрнуто в try/catch — страница
работает и без него.

Коды выхода: 0 — HTML собран; 2 — ошибка данных (нет файла, битый JSON,
неизвестное или пустое обязательное поле — тот же контракт, что у
`leadmagnet.py`); 3 — данные верны, но файл не записан (ошибка диска).
"""
from __future__ import annotations

import base64
import json
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from .build import _utf8_output
from .leadmagnet import EXIT_DATA_ERROR, JSON_FILE, load_data  # переиспользование, не дублирование

#: Код выхода: данные верны, файл вёрстки не удалось записать на диск.
EXIT_NOT_BUILT = 3

# --- её гайдовая палитра -----------------------------------------------------
# Снята дословно с обоих её файлов essa-ai/visual_references/интерактивные
# гайды/*.html (совпадает в обоих) и записана в contract.md, раздел
# «поправка владелицы» 2026-09-23. Не tokens.py — тот описывает систему
# каруселей, которую она явно отвела для гайдов.
COLORS = {
    "paper": "#F6F1E8",
    "paper2": "#EEE5D8",
    "card": "#FFFDF9",
    "ink": "#172123",
    "muted": "#687572",
    "green": "#123F39",
    "green2": "#24584F",
    "orange": "#E96F49",
    "orange2": "#F19A63",
    "dark": "#0D1718",
    "line": "rgba(23,33,35,.12)",
}

FONT_FAMILY = "Montserrat"
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Montserrat:wght@400;500;600;700;800"
    "&display=swap"
)
GOOGLE_FONTS_HOST = "fonts.googleapis.com"
FALLBACK_STACK = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"
)

#: Шкала частоты для интерактивной таблицы. Текст раздела «Как посчитать»
#: в lead-magnet.json называет формулу («Частота × Время × Раздражение»),
#: но не задаёт, как именно превращать частоту в число — подписей со
#: шкалой там нет. Подписи и числа ниже — решение вёрстки по возрастанию,
#: не её слова; см. CONCERNS в отчёте таска, она должна проверить формулировки.
FREQUENCY_SCALE = [
    ("", "— выбери —", 0),
    ("daily", "каждый день", 7),
    ("often", "несколько раз в неделю", 3),
    ("weekly", "раз в неделю", 1),
    ("rare", "реже", 0.5),
]

IRRITATION_SCALE = [1, 2, 3, 4, 5]

#: Ключевые слова для распознавания ролей колонок в table.columns —
#: без них таблица рисуется как статичные пустые строки для записи.
_HOURS_KEYS = ("час",)
_FREQ_KEYS = ("част",)
_IRRITATION_KEYS = ("раздраж",)
_TOTAL_KEYS = ("итог",)


@dataclass
class GuideResult:
    """Итог одной сборки гайда."""

    ok: bool
    html_path: Path
    error: str | None = None


def _t(value: Any) -> str:
    return escape(str(value), quote=True)


def _paragraphs(items: list[str] | None) -> str:
    return "".join(f"<p>{_t(p)}</p>" for p in (items or []))


def _accent_last_word(text: str) -> str:
    """Оранжевый акцент на последнем — смысловом — слове заголовка."""
    words = text.split()
    if len(words) < 2:
        return f'<span class="accent">{_t(text)}</span>'
    head, last = " ".join(words[:-1]), words[-1]
    return f'{_t(head)} <span class="accent">{_t(last)}</span>'


def _slugify(text: str, fallback: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or fallback


def _note_html(text: str | None) -> str:
    if not text:
        return ""
    return f'<div class="note-card"><div class="note-mark">!</div><p>{_t(text)}</p></div>'


def _handwritten_html(text: str | None) -> str:
    if not text:
        return ""
    return f'<div class="handwritten">{_t(text)}</div>'


def _steps_html(items: list[str] | None) -> str:
    """Шаги нумерованными кружками, зелёный и оранжевый попеременно."""
    if not items:
        return ""
    rows = []
    for i, item in enumerate(items):
        cls = "step-n green" if i % 2 == 0 else "step-n orange"
        rows.append(
            f'<li class="step"><span class="{cls}">{i + 1}</span>'
            f"<span>{_t(item)}</span></li>"
        )
    return f'<ul class="steps">{"".join(rows)}</ul>'


def _find_column(columns: list[str], keys: tuple[str, ...]) -> int | None:
    for i, col in enumerate(columns):
        low = str(col).lower()
        if any(k in low for k in keys):
            return i
    return None


def _audit_table_html(table: dict[str, Any], section_index: int) -> tuple[str, bool]:
    """Таблица раздела: интерактивная, если распознаны колонки часов и
    раздражения, иначе — статичная (пустая клетка — линия для записи)."""
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    hours_i = _find_column(columns, _HOURS_KEYS)
    irritation_i = _find_column(columns, _IRRITATION_KEYS)
    freq_i = _find_column(columns, _FREQ_KEYS)
    total_i = _find_column(columns, _TOTAL_KEYS)
    interactive = hours_i is not None and irritation_i is not None

    head = "".join(f"<th>{_t(c)}</th>" for c in columns)

    if not interactive:
        body_rows = []
        for row in rows:
            cells = []
            for i in range(len(columns)):
                value = row[i] if i < len(row) else ""
                value = "" if value is None else str(value)
                if value.strip():
                    cells.append(f"<td>{_t(value)}</td>")
                else:
                    cells.append('<td class="fillable"><span class="fill-line"></span></td>')
            body_rows.append(f"<tr>{''.join(cells)}</tr>")
        html = (
            f'<div class="table-block"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{''.join(body_rows)}</tbody></table></div>"
        )
        return html, False

    freq_options = "".join(
        f'<option value="{v}" data-n="{n}">{_t(label)}</option>' for v, label, n in FREQUENCY_SCALE
    )
    irritation_options = "".join(f"<option>{n}</option>" for n in IRRITATION_SCALE)

    body_rows = []
    for r, row in enumerate(rows):
        process = _t(row[0]) if row else ""
        hours_val = row[hours_i] if hours_i < len(row) and row[hours_i] else ""
        cells = [f'<td class="process">{process}</td>']
        for i in range(len(columns)):
            if i == 0:
                continue
            if i == hours_i:
                cells.append(
                    f'<td><input type="number" class="f-hours" min="0" step="0.5" '
                    f'inputmode="decimal" placeholder="0" value="{_t(hours_val)}" '
                    f'data-row="{r}"></td>'
                )
            elif i == freq_i:
                cells.append(f'<td><select class="f-freq" data-row="{r}">{freq_options}</select></td>')
            elif i == irritation_i:
                cells.append(
                    f'<td><select class="f-irritation" data-row="{r}">'
                    f'<option value="">—</option>{irritation_options}</select></td>'
                )
            elif i == total_i:
                cells.append(f'<td class="f-total" data-row="{r}">0</td>')
            else:
                value = row[i] if i < len(row) and row[i] else ""
                cells.append(f"<td>{_t(value)}</td>")
        body_rows.append(f'<tr class="audit-row" data-row="{r}" data-process="{process}">{"".join(cells)}</tr>')

    html = f"""
<div class="table-block audit-table" id="audit-table-{section_index}">
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{"".join(body_rows)}</tbody>
  </table>
  <div class="audit-summary">
    <div class="audit-total-hours">Часов в неделю всего: <b id="audit-hours-sum">0</b></div>
    <button type="button" class="btn ghost small" id="audit-clear">Очистить</button>
  </div>
  <div class="audit-winner" id="audit-winner" hidden>
    Твой первый процесс — <span id="audit-winner-name"></span>
  </div>
</div>
"""
    return html, True


def _section_html(section: dict[str, Any], index: int, has_audit: list[bool]) -> str:
    heading = section["heading"]
    slug = _slugify(heading, f"section-{index}")
    body = _paragraphs(section.get("body"))
    hand = _handwritten_html(section.get("handwritten"))
    note = _note_html(section.get("note"))
    steps = _steps_html(section.get("checklist"))
    table_html = ""
    table = section.get("table")
    if table:
        table_html, interactive = _audit_table_html(table, index)
        has_audit.append(interactive)
    return f"""
<section class="section" id="{slug}">
  <div class="kicker">{index:02d} · {_t(heading)}</div>
  <h2 class="headline">{_accent_last_word(heading)}</h2>
  {hand}
  <div class="body">{body}</div>
  {note}
  {steps}
  {table_html}
</section>
"""


def _photo_data_uri(data: dict[str, Any]) -> str | None:
    photo = data.get("photo")
    base_dir = data.get("_base_dir")
    if not photo or not base_dir:
        return None
    path = (Path(base_dir) / photo).resolve()
    if not path.is_file():
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _nav_html(sections: list[dict[str, Any]], audit_slug: str | None) -> str:
    links = ['<a href="#start">Начало</a>']
    for i, section in enumerate(sections, start=1):
        slug = _slugify(section["heading"], f"section-{i}")
        links.append(f'<a href="#{slug}">{_t(section["heading"])}</a>')
    if audit_slug:
        links.append(f'<a href="#{audit_slug}">Таблица</a>')
    return f'<nav class="nav">{"".join(links)}</nav>'


def _cover_html(
    data: dict[str, Any], photo_uri: str | None, audit_slug: str | None, first_slug: str
) -> str:
    portrait = f'<img class="cover-photo" src="{photo_uri}" alt="">' if photo_uri else ""
    cls = "cover with-photo" if photo_uri else "cover"
    intro = _paragraphs(data.get("intro"))
    to_table = f'<a href="#{audit_slug}" class="btn ghost">Сразу к таблице</a>' if audit_slug else ""
    return f"""
<header class="{cls}" id="start">
  <div class="cover-grid">
    <div class="cover-text">
      <div class="eyebrow"><span class="spark"></span> ESSA.AI · AI-АУДИТ</div>
      <h1 class="headline">{_accent_last_word(data["title"])}</h1>
      <p class="subtitle">{_t(data["subtitle"])}</p>
      <div class="intro">{intro}</div>
      <div class="cover-actions">
        <a href="#{first_slug}" class="btn primary">Начать аудит ↓</a>
        {to_table}
      </div>
      <div class="author">{_t(data["author"])}</div>
    </div>
    {portrait}
  </div>
</header>
"""


def _cta_html(cta: dict[str, Any] | None) -> str:
    if not cta:
        return ""
    text = cta.get("text", "")
    keyword = cta.get("keyword")
    keyword_html = f' <span class="accent">{_t(keyword)}</span>' if keyword else ""
    return f"""
<section class="final">
  <div class="kicker">ESSA.AI · СЛЕДУЮЩИЙ ШАГ</div>
  <p class="cta-text">{_t(text)}{keyword_html}</p>
</section>
"""


def _css() -> str:
    c = COLORS
    return f"""
:root {{
  --paper:{c["paper"]}; --paper2:{c["paper2"]}; --card:{c["card"]};
  --ink:{c["ink"]}; --muted:{c["muted"]};
  --green:{c["green"]}; --green2:{c["green2"]};
  --orange:{c["orange"]}; --orange2:{c["orange2"]};
  --dark:{c["dark"]}; --line:{c["line"]};
  --shadow:0 18px 52px rgba(9,26,24,.12);
  --r:22px;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; background: var(--paper); }}
body {{
  margin: 0;
  font-family: '{FONT_FAMILY}', {FALLBACK_STACK};
  color: var(--ink);
  background: var(--paper);
  -webkit-font-smoothing: antialiased;
  overflow-x: hidden;
}}
button, input, select, textarea {{ font: inherit; }}
.accent {{ color: var(--orange); }}
.headline {{ font-weight: 800; line-height: 1.05; letter-spacing: -0.02em; margin: 0 0 18px; }}

.nav {{
  position: sticky; top: 8px; z-index: 50;
  width: max-content; max-width: calc(100% - 20px);
  margin: 10px auto 0; padding: 7px;
  display: flex; gap: 5px; flex-wrap: wrap; justify-content: center;
  border: 1px solid rgba(255,255,255,.66);
  border-radius: 999px; background: rgba(248,244,237,.93);
  box-shadow: 0 8px 28px rgba(0,0,0,.08);
}}
.nav a {{ font-size: 11px; font-weight: 700; text-decoration: none; color: var(--green2); padding: 9px 11px; border-radius: 999px; }}
.nav a:hover {{ background: var(--paper2); }}

.cover {{
  color: #fff; padding: 72px 7% 64px;
  background: linear-gradient(130deg, #0b1515 0%, var(--dark) 58%, var(--green) 100%);
}}
.cover-grid {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 40px; align-items: center; }}
.cover.with-photo .cover-text {{ max-width: 100%; }}
.eyebrow {{
  display: inline-flex; align-items: center; gap: 9px;
  border: 1px solid rgba(255,255,255,.25); border-radius: 999px; padding: 9px 13px;
  font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase;
  background: rgba(255,255,255,.06);
}}
.spark {{ width: 8px; height: 8px; background: var(--orange); transform: rotate(45deg); border-radius: 1px; }}
.cover .headline {{ font-size: clamp(38px,5.5vw,64px); margin: 20px 0 18px; }}
.subtitle {{ font-size: clamp(16px,1.6vw,20px); line-height: 1.55; color: rgba(255,255,255,.82); max-width: 560px; margin: 0 0 14px; }}
.intro p {{ font-size: 15px; line-height: 1.6; color: rgba(255,255,255,.72); margin: 0 0 8px; max-width: 560px; }}
.cover-actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 22px 0 20px; }}
.btn {{ border: 0; border-radius: 13px; padding: 13px 18px; font-size: 13px; font-weight: 800; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; text-decoration: none; }}
.btn.primary {{ background: var(--orange); color: #20130e; }}
.btn.ghost {{ background: rgba(255,255,255,.08); color: #fff; border: 1px solid rgba(255,255,255,.24); }}
.btn.small {{ padding: 8px 12px; font-size: 11px; }}
.author {{ font-size: 13px; font-weight: 700; color: var(--orange2); }}
.cover-photo {{ width: 100%; max-width: 340px; justify-self: end; border-radius: 24px; }}

section.section {{ padding: 64px 7%; border-top: 1px solid var(--line); background: var(--paper); }}
section.section:nth-of-type(even) {{ background: var(--paper2); }}
.kicker {{ font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--orange); margin-bottom: 10px; }}
h2.headline {{ font-size: clamp(28px,3.6vw,42px); color: var(--green); max-width: 820px; }}
.body p {{ font-size: 16px; line-height: 1.6; color: var(--ink); max-width: 760px; margin: 0 0 10px; }}
.handwritten {{ font-family: cursive; color: var(--orange); font-size: 22px; margin-bottom: 10px; }}

.note-card {{
  display: flex; gap: 12px; align-items: flex-start;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r);
  box-shadow: var(--shadow); padding: 16px 18px; margin: 18px 0; max-width: 720px;
}}
.note-mark {{ flex: none; width: 26px; height: 26px; border-radius: 8px; background: var(--orange); color: #fff; font-weight: 800; display: grid; place-items: center; }}
.note-card p {{ margin: 0; font-size: 14px; line-height: 1.55; color: var(--ink); }}

.steps {{ list-style: none; margin: 18px 0; padding: 0; max-width: 760px; }}
.step {{ display: flex; gap: 14px; align-items: flex-start; margin-bottom: 12px; font-size: 15px; line-height: 1.5; }}
.step-n {{ flex: none; width: 30px; height: 30px; border-radius: 999px; color: #fff; font-weight: 800; display: grid; place-items: center; font-size: 13px; }}
.step-n.green {{ background: var(--green); }}
.step-n.orange {{ background: var(--orange); }}

.table-block {{ margin-top: 20px; overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 560px; }}
th {{ text-align: left; font-weight: 700; color: var(--muted); border-bottom: 1.5px solid var(--line); padding: 10px 8px; white-space: nowrap; }}
td {{ padding: 8px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
td.process {{ font-weight: 700; white-space: nowrap; }}
td.fillable {{ min-height: 34px; }}
.fill-line {{ display: block; width: 100%; height: 22px; border-bottom: 1px dashed var(--muted); }}

.audit-table input, .audit-table select {{
  width: 100%; border: 1px solid var(--line); background: #fff; color: var(--ink);
  border-radius: 8px; padding: 8px; outline: none; font-size: 13px;
}}
.audit-table input:focus, .audit-table select:focus {{ border-color: var(--orange); }}
.f-total {{ font-weight: 800; text-align: center; }}
.audit-row.is-max {{ background: rgba(233,111,73,.16); }}
.audit-row.is-max td.process {{ color: var(--orange); }}
.audit-summary {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 14px; flex-wrap: wrap; }}
.audit-total-hours {{ font-size: 14px; color: var(--muted); }}
.audit-total-hours b {{ color: var(--ink); }}
.audit-winner {{
  margin-top: 14px; background: var(--orange); color: #20130e; font-weight: 800;
  border-radius: var(--r); padding: 14px 18px; font-size: 15px;
}}

.final {{ padding: 64px 7%; background: var(--green); color: #fff; text-align: center; }}
.final .kicker {{ color: var(--orange2); }}
.cta-text {{ font-size: clamp(18px,2.4vw,24px); line-height: 1.55; max-width: 640px; margin: 10px auto 0; }}

@media (max-width: 900px) {{
  .cover-grid {{ grid-template-columns: 1fr; }}
  .cover-photo {{ max-width: 220px; justify-self: start; }}
}}
@media (max-width: 700px) {{
  .nav {{ position: relative; top: auto; width: 100%; max-width: none; margin: 0; border-radius: 0; border: 0; border-bottom: 1px solid var(--line); overflow-x: auto; flex-wrap: nowrap; justify-content: flex-start; background: var(--paper); }}
  .nav a {{ white-space: nowrap; flex: 0 0 auto; }}
  .cover {{ padding: 40px 20px 32px; }}
  section.section {{ padding: 40px 20px; }}
  .final {{ padding: 40px 20px; }}
  input, select {{ font-size: 16px; }}
}}
"""


def _js() -> str:
    return """
(function(){
  var STORAGE_KEY = "essa-ai-audit-%(slug)s";

  function safeStorage(){
    try {
      var testKey = "__essa_test__";
      window.localStorage.setItem(testKey, "1");
      window.localStorage.removeItem(testKey);
      return window.localStorage;
    } catch (e) {
      return null;
    }
  }
  var storage = safeStorage();

  function loadSaved(){
    if (!storage) return {};
    try {
      return JSON.parse(storage.getItem(STORAGE_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }
  function save(state){
    if (!storage) return;
    try { storage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
  }

  document.querySelectorAll(".audit-table").forEach(function(tableWrap){
    var rows = tableWrap.querySelectorAll(".audit-row");
    var saved = loadSaved();

    function readRow(row){
      var hours = row.querySelector(".f-hours");
      var freq = row.querySelector(".f-freq");
      var irritation = row.querySelector(".f-irritation");
      var hoursVal = parseFloat(hours && hours.value) || 0;
      var freqVal = freq ? parseFloat(freq.selectedOptions[0].getAttribute("data-n")) || 0 : 0;
      var irritationVal = parseFloat(irritation && irritation.value) || 0;
      return {hours: hoursVal, freq: freqVal, irritation: irritationVal};
    }

    function recalc(){
      var maxTotal = -1, maxRow = null, hoursSum = 0;
      rows.forEach(function(row){
        var v = readRow(row);
        hoursSum += v.hours;
        var total = v.freq * v.hours * v.irritation;
        var cell = row.querySelector(".f-total");
        if (cell) cell.textContent = total ? (Math.round(total * 10) / 10) : "0";
        row.classList.remove("is-max");
        if (total > maxTotal && total > 0) { maxTotal = total; maxRow = row; }
      });
      if (maxRow) {
        maxRow.classList.add("is-max");
      }
      var sumEl = tableWrap.querySelector("#audit-hours-sum") || tableWrap.querySelector(".audit-total-hours b");
      if (sumEl) sumEl.textContent = Math.round(hoursSum * 10) / 10;
      var winnerBox = tableWrap.querySelector(".audit-winner");
      var winnerName = tableWrap.querySelector("#audit-winner-name");
      if (winnerBox && winnerName) {
        if (maxRow) {
          winnerName.textContent = maxRow.getAttribute("data-process") || "";
          winnerBox.hidden = false;
        } else {
          winnerBox.hidden = true;
        }
      }
    }

    function persist(){
      var state = {};
      rows.forEach(function(row){
        state[row.getAttribute("data-row")] = readRow(row);
        var freq = row.querySelector(".f-freq");
        if (freq) state[row.getAttribute("data-row")].freqValue = freq.value;
      });
      save(state);
    }

    rows.forEach(function(row){
      var idx = row.getAttribute("data-row");
      var state = saved[idx];
      if (state) {
        var hours = row.querySelector(".f-hours");
        var freq = row.querySelector(".f-freq");
        var irritation = row.querySelector(".f-irritation");
        if (hours && state.hours) hours.value = state.hours;
        if (freq && state.freqValue) freq.value = state.freqValue;
        if (irritation && state.irritation) irritation.value = state.irritation;
      }
      row.querySelectorAll("input, select").forEach(function(el){
        el.addEventListener("input", function(){ recalc(); persist(); });
        el.addEventListener("change", function(){ recalc(); persist(); });
      });
    });

    var clearBtn = tableWrap.querySelector("#audit-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function(){
        rows.forEach(function(row){
          var hours = row.querySelector(".f-hours");
          var freq = row.querySelector(".f-freq");
          var irritation = row.querySelector(".f-irritation");
          if (hours) hours.value = "";
          if (freq) freq.value = "";
          if (irritation) irritation.value = "";
        });
        if (storage) { try { storage.removeItem(STORAGE_KEY); } catch (e) {} }
        recalc();
      });
    }

    recalc();
  });
})();
"""


def render_html(data: dict[str, Any]) -> str:
    """`lead-magnet.json` -> самодостаточный HTML-гайд."""
    sections = data["sections"]
    photo_uri = _photo_data_uri(data)

    audit_flags: list[bool] = []
    audit_slug = None
    first_slug = _slugify(sections[0]["heading"], "section-1") if sections else "start"
    for i, section in enumerate(sections, start=1):
        if section.get("table"):
            audit_slug = _slugify(section["heading"], f"section-{i}")
            break

    body = _cover_html(data, photo_uri, audit_slug, first_slug)
    body += _nav_html(sections, audit_slug)
    body += "".join(_section_html(s, i, audit_flags) for i, s in enumerate(sections, start=1))
    body += _cta_html(data.get("cta"))

    slug = data.get("_slug", "guide")
    js = _js() % {"slug": _t(slug)}

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{_t(data["title"])}</title>
<meta name="description" content="{_t(data["subtitle"])}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{GOOGLE_FONTS_URL}" rel="stylesheet">
<style>
{_css()}
</style>
</head>
<body>
{body}
<script>
{js}
</script>
</body>
</html>
"""


def build(kit_dir: str | Path, json_path: str | Path | None = None) -> GuideResult:
    """Собрать гайд: `lead-magnet.json` -> `<kit_dir>/<slug>.html`."""
    kit_dir = Path(kit_dir)
    json_path = Path(json_path or kit_dir / JSON_FILE)
    data = load_data(json_path)  # ValueError — контракт данных, код 2 у вызывающего

    slug = kit_dir.name
    html_path = kit_dir / f"{slug}.html"
    html = render_html({**data, "_base_dir": str(json_path.parent), "_slug": slug})
    try:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        return GuideResult(ok=False, html_path=html_path, error=str(exc))
    return GuideResult(ok=True, html_path=html_path)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _utf8_output()
    if len(argv) != 1:
        print(__doc__)
        return EXIT_DATA_ERROR
    try:
        result = build(argv[0])
    except (OSError, ValueError) as exc:
        print(f"сборка не началась: {exc}")
        return EXIT_DATA_ERROR

    if not result.ok:
        print(f"файл не записан: {result.error}")
        return EXIT_NOT_BUILT

    print(f"готово: {result.html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
