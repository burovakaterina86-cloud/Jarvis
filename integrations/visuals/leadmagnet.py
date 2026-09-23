"""Вёрстка лид-магнита: `lead-magnet.json` → PDF в дизайн-системе ESSA.AI.

    python -m integrations.visuals.leadmagnet <папка>

Читает `<папка>/lead-magnet.json` (формат — общий контракт двух частей
`.autopilot/2026-09-23-lead-magnets--wip/contract.md`: `title`, `subtitle`,
`author`, `intro`, `sections[]` с `heading`/`body`/`table`/`checklist`/
`note`/`handwritten`, `cta`, `background`), собирает HTML многостраничного
A4-документа по её дизайн-контракту `essa-ai/ESSA_PRESENTATION_STYLE.md`
(§3 палитра, §4–6 типографика и рукописные пометки, §13 плашки, §14 декор)
и снимает PDF Python-пакетом `playwright` (`page.pdf`) в `<папка>/<slug>.pdf`,
где `<slug>` — имя папки лид-магнита.

`background`: `"dark"` (по умолчанию — её система задаёт тёмный фон) или
`"light"` (для печати — тёмный PDF дорого печатать). Цвета в обоих режимах —
только из `tokens.py`, свои не вводятся.

Коды выхода: 0 — PDF собран; 2 — ошибка данных (нет файла, битый JSON,
неизвестное или отсутствующее поле); 3 — вёрстка готова, но PDF не снят
(питоновского `playwright` нет или браузер не поднялся) — HTML остаётся
на диске для разбора причины.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from . import tokens
from .build import _utf8_output
from .render import PAGE_TIMEOUT_MS, _playwright_module, font_warning

#: Имя файла данных в папке лид-магнита.
JSON_FILE = "lead-magnet.json"

TOP_LEVEL_FIELDS = {"title", "subtitle", "author", "intro", "sections", "cta", "background",
                    "photo"}  # photo — путь к её вырезанному портрету, от папки JSON
SECTION_FIELDS = {"heading", "body", "table", "checklist", "note", "handwritten"}
TABLE_FIELDS = {"columns", "rows"}
CTA_FIELDS = {"text", "keyword"}

#: Режимы фона — её слово из таска: «Режим фона "dark" | "light" в JSON».
BACKGROUNDS = ("dark", "light")
DEFAULT_BACKGROUND = "dark"

#: Код выхода: данные не читаются или не проходят контракт.
EXIT_DATA_ERROR = 2
#: Код выхода: вёрстка собрана, но PDF не снят.
EXIT_NOT_RENDERED = 3


@dataclass
class LeadMagnetResult:
    """Итог одной сборки лид-магнита."""

    ok: bool
    html_path: Path
    pdf_path: Path | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _t(value: Any) -> str:
    return escape(str(value), quote=True)


# --- данные -----------------------------------------------------------------


def load_data(json_path: str | Path) -> dict[str, Any]:
    """Прочитать и проверить `lead-magnet.json`. Нарушение контракта — `ValueError`."""
    json_path = Path(json_path)
    if not json_path.is_file():
        raise ValueError(f"нет файла данных: {json_path}")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{json_path}: битый JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{json_path}: нужен объект верхнего уровня")

    unknown = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unknown:
        raise ValueError(f"неизвестные поля: {', '.join(unknown)}")

    for key in ("title", "subtitle", "author"):
        if not data.get(key):
            raise ValueError(f'нужно поле "{key}"')

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError('нужен непустой список "sections"')

    for i, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"раздел {i}: нужен объект")
        unknown = sorted(set(section) - SECTION_FIELDS)
        if unknown:
            raise ValueError(f"раздел {i}: неизвестные поля {', '.join(unknown)}")
        if not section.get("heading"):
            raise ValueError(f"раздел {i}: нужно поле heading")
        table = section.get("table")
        if table is not None:
            if not isinstance(table, dict) or set(table) - TABLE_FIELDS:
                raise ValueError(f'раздел {i}: table — объект {{"columns", "rows"}}')
            columns = table.get("columns")
            rows = table.get("rows")
            if not isinstance(columns, list) or not columns:
                raise ValueError(f"раздел {i}: table.columns — непустой список")
            if not isinstance(rows, list):
                raise ValueError(f"раздел {i}: table.rows — список")

    cta = data.get("cta")
    if cta is not None and (not isinstance(cta, dict) or set(cta) - CTA_FIELDS):
        raise ValueError('cta — объект {"text", "keyword"}')

    background = data.get("background", DEFAULT_BACKGROUND)
    if background not in BACKGROUNDS:
        raise ValueError(f'background {background!r} — только {" | ".join(BACKGROUNDS)}')

    return data


# --- палитра ------------------------------------------------------------


def _palette(background: str) -> dict[str, str]:
    """Цвета режима — только из `tokens.py`, ничего не подобрано."""
    cp = tokens.CAROUSEL_PALETTE
    p = tokens.PALETTE
    if background == "light":
        return {
            "bg": p["BG_LIGHT_PRIMARY"],
            "plate": p["BG_LIGHT_SECONDARY"],
            "text": p["TEXT_ON_LIGHT"],
            "muted": p["TEXT_MUTED_LIGHT"],
            "line": p["TEXT_MUTED_LIGHT"],
            "accent": cp["ORANGE_DEEP"],
            "violet": p["VIOLET_PRIMARY"],
        }
    return {
        "bg": cp["BG_DEEP"],
        "plate": tokens.PLATE["BASE"],
        "text": cp["TEXT"],
        "muted": cp["TEXT_MUTED"],
        "line": cp["TEXT_DIM"],
        "accent": cp["ORANGE"],
        "violet": cp["VIOLET"],
    }


# --- HTML-блоки -----------------------------------------------------------


def _accent_last_word(text: str) -> str:
    """Оранжевый акцент на последнем слове (§4: «1–2 ключевых слова могут
    быть оранжевыми», «акцент должен быть смысловым»). Данные лид-магнита
    не размечают, какое слово смысловое, — последнее слово в заголовке её
    собственных примеров («…ВСЁ РАВНО УХОДИТ СЛИШКОМ МНОГО ВРЕМЕНИ») и есть
    смысловой итог фразы, поэтому правило детерминированное, а не гадание."""
    words = text.split()
    if len(words) < 2:
        return f'<span class="accent">{_t(text)}</span>'
    head, last = " ".join(words[:-1]), words[-1]
    return f'{_t(head)} <span class="accent">{_t(last)}</span>'


def _paragraphs(items: list[str] | None) -> str:
    return "".join(f"<p>{_t(p)}</p>" for p in (items or []))


def _handwritten_html(text: str | None) -> str:
    if not text:
        return ""
    return f'<div class="handwritten">{_t(text)}</div>'


def _note_html(text: str | None) -> str:
    if not text:
        return ""
    return f'<div class="note-plate">{_t(text)}</div>'


def _checklist_html(items: list[str] | None) -> str:
    if not items:
        return ""
    rows = "".join(f'<li><span class="box"></span>{_t(item)}</li>' for item in items)
    return f'<ul class="checklist">{rows}</ul>'


def _table_html(table: dict[str, Any] | None) -> str:
    """Таблица для заполнения. Пустая клетка — поле для записи: строчка,
    а не пустое место, читается и распечатанной, и с телефона."""
    if not table:
        return ""
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    head = "".join(f"<th>{_t(c)}</th>" for c in columns)
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
    return (
        '<div class="table-block"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _cover_html(data: dict[str, Any]) -> str:
    """Обложка — самая сильная полоса (её §18): заголовок слева, портрет справа.

    `photo` — путь к её вырезанному портрету; `_photo_uri` уже сделал его
    абсолютным. Портрета нет — обложка собирается без него.
    """
    intro = _paragraphs(data.get("intro"))
    photo = data.get("_photo_uri")
    portrait = f'<img class="cover-photo" src="{_t(photo)}" alt="">' if photo else ""
    cls = "cover with-photo" if photo else "cover"
    return f"""
<section class="{cls}">
  {portrait}
  <div class="cover-text">
    <div class="kicker">ESSA.AI</div>
    <h1 class="headline">{_accent_last_word(data["title"])}</h1>
    <p class="subtitle">{_t(data["subtitle"])}</p>
    <div class="intro">{intro}</div>
    <div class="author">{_t(data["author"])}</div>
  </div>
</section>
"""


def _section_html(section: dict[str, Any], index: int, total: int) -> str:
    heading = section["heading"]
    body = _paragraphs(section.get("body"))
    table = _table_html(section.get("table"))
    checklist = _checklist_html(section.get("checklist"))
    note = _note_html(section.get("note"))
    hand = _handwritten_html(section.get("handwritten"))
    number = f"{index:02d} / {total:02d}"
    return f"""
<section class="section">
  <div class="rubric"><span class="accent">{number}</span><span class="rule"></span></div>
  <h2 class="headline">{_t(heading)}</h2>
  {hand}
  <div class="body">{body}</div>
  {note}
  {checklist}
  {table}
</section>
"""


def _cta_html(cta: dict[str, Any]) -> str:
    keyword = cta.get("keyword")
    text = cta.get("text", "")
    keyword_html = f' <span class="accent">{_t(keyword)}</span>' if keyword else ""
    return f"""
<section class="cta">
  <div class="rule"></div>
  <p class="cta-text">{_t(text)}{keyword_html}</p>
</section>
"""


def _css(c: dict[str, str]) -> str:
    head = tokens.FONTS["HEADLINE"]
    return f"""
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  /* Поля листа задаёт @page: разделы идут потоком и сами переходят на
     следующий лист. Раньше каждый раздел занимал свой лист — 8 листов A4
     с полупустыми страницами, её жалоба «много воздуха» (2026-09-23). */
  @page {{ size: A4; margin: 18mm 16mm; }}
  html, body {{ background: {c["bg"]}; }}
  body {{
    font-family: {tokens.font_stack("BODY")};
    color: {c["text"]};
    -webkit-font-smoothing: antialiased;
  }}
  .headline {{
    font-family: '{head}', {tokens.FALLBACK_STACK};
    font-weight: {tokens.FONT_WEIGHTS["HEADLINE"]};
    text-transform: uppercase;
    line-height: 1.05;
    letter-spacing: 0.01em;
  }}
  .accent {{ color: {c["accent"]}; }}
  .page {{
    width: 210mm;
    min-height: 297mm;
    padding: 22mm 18mm;
    position: relative;
    page-break-after: always;
    break-after: page;
    display: flex;
    flex-direction: column;
  }}
  .page:last-of-type {{ page-break-after: auto; break-after: auto; }}
  .cover {{
    min-height: calc(297mm - 36mm); position: relative;
    display: flex; flex-direction: column; justify-content: center;
    break-after: page; page-break-after: always;
  }}
  .cover-text {{ position: relative; z-index: 1; display: flex; flex-direction: column; gap: 12mm; }}
  /* Текст и портрет — разные колонки: портрет не заходит под текст (её правило
     со слайдов «плашка не налезает на лицо»). */
  .cover.with-photo .cover-text {{ max-width: 52%; }}
  .cover-photo {{
    position: absolute; right: -16mm; bottom: -18mm; height: 78%; width: auto;
    max-width: 50%; object-position: right bottom;
    z-index: 0; object-fit: contain;
    -webkit-mask-image: linear-gradient(to left, #000 60%, transparent 100%);
            mask-image: linear-gradient(to left, #000 60%, transparent 100%);
  }}
  .section {{ margin-bottom: 14mm; break-inside: avoid; page-break-inside: avoid; }}
  .section .headline {{ break-after: avoid; page-break-after: avoid; }}
  .cta {{ margin-top: 6mm; break-inside: avoid; }}
  .kicker {{
    font-family: {tokens.font_stack("SUPPORT")};
    font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
    letter-spacing: 0.18em;
    color: {c["muted"]};
    font-size: 14px;
  }}
  .cover .headline {{ font-size: 64px; }}
  .subtitle {{
    font-family: {tokens.font_stack("BODY")};
    font-size: 22px;
    color: {c["muted"]};
    max-width: 140mm;
  }}
  .intro p {{ font-size: 18px; line-height: 1.5; margin-bottom: 10px; color: {c["text"]}; }}
  .author {{
    font-family: {tokens.font_stack("SUPPORT")};
    font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
    color: {c["accent"]};
    font-size: 15px;
  }}
  .rubric {{ display: flex; align-items: center; gap: 14px; margin-bottom: 10mm; }}
  .rubric .rule {{ flex: 1; height: 1px; background: {c["line"]}; opacity: 0.5; }}
  .section .headline {{ font-size: 36px; margin-bottom: 8mm; }}
  .handwritten {{
    font-family: '{tokens.HAND_FONT}', {tokens.HAND_FALLBACK};
    color: {c["accent"]};
    font-size: 24px;
    margin-bottom: 6mm;
  }}
  .body p {{ font-size: 16px; line-height: 1.55; margin-bottom: 8px; color: {c["text"]}; }}
  .note-plate {{
    background: {c["plate"]};
    border-radius: {tokens.PLATE_RADIUS}px;
    padding: 14px 18px;
    margin: 8mm 0;
    font-size: 15px;
    line-height: 1.5;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .checklist {{ list-style: none; margin: 6mm 0; }}
  .checklist li {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 15px;
    line-height: 1.5;
    margin-bottom: 8px;
  }}
  .checklist .box {{
    width: 14px;
    height: 14px;
    border: 1.5px solid {c["accent"]};
    border-radius: 3px;
    margin-top: 3px;
    flex: none;
  }}
  .table-block {{
    margin-top: 8mm;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{
    text-align: left;
    font-family: {tokens.font_stack("SUPPORT")};
    font-weight: {tokens.FONT_WEIGHTS["SUPPORT"]};
    color: {c["muted"]};
    border-bottom: 1.5px solid {c["line"]};
    padding: 8px 10px;
  }}
  td {{
    padding: 10px;
    border-bottom: 1px solid {c["line"]};
    vertical-align: top;
    color: {c["text"]};
  }}
  td.fillable {{ min-height: 34px; }}
  .fill-line {{
    display: block;
    width: 100%;
    height: 22px;
    border-bottom: 1px dashed {c["muted"]};
  }}
  .cta {{ justify-content: center; align-items: center; text-align: center; gap: 10mm; }}
  .cta .rule {{ width: 60px; height: 2px; background: {c["accent"]}; margin: 0 auto; }}
  .cta-text {{
    font-family: {tokens.font_stack("BODY")};
    font-size: 22px;
    line-height: 1.5;
    max-width: 130mm;
  }}
"""


def render_html(data: dict[str, Any]) -> str:
    """`lead-magnet.json` → HTML многостраничного A4-документа."""
    background = data.get("background", DEFAULT_BACKGROUND)
    c = _palette(background)
    sections = data["sections"]
    total = len(sections)

    photo = data.get("photo")
    if photo and data.get("_base_dir"):
        path = (Path(data["_base_dir"]) / photo).resolve()
        if path.exists():
            data = {**data, "_photo_uri": path.as_uri()}
    body = _cover_html(data)
    body += "".join(_section_html(s, i, total) for i, s in enumerate(sections, start=1))
    cta = data.get("cta")
    if cta:
        body += _cta_html(cta)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{_t(data["title"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{tokens.GOOGLE_FONTS_URL}" rel="stylesheet">
<style>
{_css(c)}
</style>
</head>
<body>
{body}
</body>
</html>
"""


# --- снимок PDF -------------------------------------------------------------


def _render_pdf(html_path: Path, out_pdf: Path) -> tuple[bool, list[str], str | None]:
    """HTML → PDF Python-пакетом `playwright`. Не бросает — причина в возврате."""
    warnings = [w for w in (font_warning(),) if w]
    sync_playwright = _playwright_module()
    if sync_playwright is None:
        return False, warnings, (
            "питоновский пакет playwright не установлен — вёрстка сохранена "
            f"в {html_path}, PDF не снят"
        )
    try:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), timeout=PAGE_TIMEOUT_MS)
            try:
                page.wait_for_function("document.fonts.ready", timeout=PAGE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001 — шрифты не приехали, PDF всё равно снимаем
                warnings.append(
                    "шрифты не догрузились за "
                    f"{PAGE_TIMEOUT_MS // 1000} с, PDF снят стеком «{tokens.FALLBACK_STACK}»"
                )
            page.pdf(path=str(out_pdf), format="A4", print_background=True)
            browser.close()
    except Exception as exc:  # noqa: BLE001 — браузер не поднялся, ход не роняем
        return False, warnings, f"браузер не снял PDF: {exc}"
    return True, warnings, None


def build(kit_dir: str | Path, json_path: str | Path | None = None) -> LeadMagnetResult:
    """Собрать лид-магнит: `lead-magnet.json` → `<kit_dir>/<slug>.pdf`."""
    kit_dir = Path(kit_dir)
    json_path = Path(json_path or kit_dir / JSON_FILE)
    data = load_data(json_path)

    slug = kit_dir.name
    html_path = kit_dir / f"{slug}.html"
    pdf_path = kit_dir / f"{slug}.pdf"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html({**data, "_base_dir": str(json_path.parent)}),
                         encoding="utf-8")

    ok, warnings, error = _render_pdf(html_path, pdf_path)
    return LeadMagnetResult(
        ok=ok,
        html_path=html_path,
        pdf_path=pdf_path if ok else None,
        warnings=warnings,
        error=error,
    )


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

    for warning in result.warnings:
        print(f"внимание: {warning}")

    if not result.ok:
        print(f"PDF не снят: {result.error}")
        return EXIT_NOT_RENDERED

    print(f"готово: {result.pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
