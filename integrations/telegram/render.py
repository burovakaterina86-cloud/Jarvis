"""Markdown-ответ агента → читаемое сообщение Telegram.

Агент думает и пишет markdown: `## заголовки`, `**жирный**`, списки, таблицы, блоки кода.
Telegram markdown не понимает — владелица получала решётки, звёздочки и палки таблиц
и сказала, что ответы «неоформлены и тяжело читаются». Этот модуль переводит их
в тот небольшой HTML, который Telegram действительно умеет:
`<b> <i> <u> <s> <code> <pre> <a>` — остального в ответе быть не должно.

Таблицы разворачиваются в плоский список «строка: значение»: колонки в мобильном
Telegram всё равно съезжают, и таблица там нечитаема в принципе.

Разметка — дело косметическое, поэтому она нигде не может стоить ответа:
`send()` при отказе Telegram разобрать теги отправляет тот же текст простым.
"""
from __future__ import annotations

import logging
import re
from html import escape as _escape
from html import unescape as _unescape

from integrations.telegram.status import TELEGRAM_LIMIT

log = logging.getLogger("jarvis.telegram")

try:   # telegram есть всегда, но модуль должен разбираться и без него (чистая конвертация)
    from telegram.error import BadRequest
except Exception:  # noqa: BLE001 — pragma: no cover
    BadRequest = None

PARSE_MODE = "HTML"
BULLET = "• "
INDENT = "  "
QUOTE = "» "

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(\S*)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_RE = re.compile(r"^(\s*)(?:([-*+])|(\d{1,3})[.)])\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_RULE_RE = re.compile(r"^\s{0,3}([-*_])\s*(?:\1\s*){2,}$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$")
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
# код и ссылка забираются целиком до применения жирного/курсива: внутри них
# звёздочки и подчёркивания — обычные символы, а не разметка
_TOKEN_RE = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\(<?([^)\s>]+)>?\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_BOLD_US_RE = re.compile(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", re.S)
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]*?)(?<=\S)\*(?![\w*])")
_ITALIC_US_RE = re.compile(r"(?<![\w_])_(?=[^\s_])([^_\n]*?)(?<=\S)_(?![\w_])")


# ------------------------------------------------------------------ строчное

def _esc(text: str) -> str:
    return _escape(text, quote=False)


def _markup(text: str) -> str:
    """Жирный/курсив/зачёркнутый на уже экранированном тексте."""
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _BOLD_US_RE.sub(r"<b>\1</b>", text)
    text = _STRIKE_RE.sub(r"<s>\1</s>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _ITALIC_US_RE.sub(r"<i>\1</i>", text)
    return text


def inline(text: str) -> str:
    """Одна строка markdown → HTML. Экранирование — здесь и только здесь."""
    out: list[str] = []
    pos = 0
    for m in _TOKEN_RE.finditer(text):
        out.append(_markup(_esc(text[pos:m.start()])))
        if m.group(1) is not None:
            out.append(f"<code>{_esc(m.group(1))}</code>")
        else:
            url = _escape(m.group(3), quote=True)
            out.append(f'<a href="{url}">{_markup(_esc(m.group(2)))}</a>')
        pos = m.end()
    out.append(_markup(_esc(text[pos:])))
    return "".join(out)


# ------------------------------------------------------------------ таблицы

def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table(lines: list[str], i: int) -> bool:
    return ("|" in lines[i] and i + 1 < len(lines)
            and "|" in lines[i + 1] and bool(_TABLE_SEP_RE.match(lines[i + 1])))


def _flatten_table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Таблица → «строка: значение»: в телефоне колонки не выживают, а пары — да."""
    out: list[str] = []
    for cells in rows:
        if not any(c for c in cells):
            continue
        if out:
            out.append("")
        title = cells[0] if cells else ""
        rest = list(zip(header[1:], cells[1:]))
        if title:
            out.append(f"<b>{inline(title)}</b>")
        for name, value in rest:
            if not value:
                continue
            out.append(f"{inline(name)}: {inline(value)}" if name else inline(value))
        for value in cells[len(header):]:
            if value:
                out.append(inline(value))
    return out


# ------------------------------------------------------------------ блоки

def _blank(out: list[str]) -> None:
    if out and out[-1] != "":
        out.append("")


def to_html(text: str) -> str:
    """Markdown → Telegram-HTML. Ничего не теряет: неузнанное остаётся текстом."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        fence = _FENCE_RE.match(line)
        if fence:
            mark = fence.group(1)[0] * 3
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(mark):
                body.append(lines[i])
                i += 1
            i += 1                       # закрывающая ограда (или конец текста)
            _blank(out)
            out.append("<pre>" + _esc("\n".join(body)) + "</pre>")
            out.append("")
            continue

        head = _HEADING_RE.match(line)
        if head:
            _blank(out)
            out.append("<b>" + inline(head.group(2)) + "</b>")
            out.append("")           # пустая строка после заголовка — воздух в ленте
            i += 1
            continue

        if _is_table(lines, i):
            header = _cells(lines[i])
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            _blank(out)
            out.extend(_flatten_table(header, rows))
            out.append("")
            continue

        if _RULE_RE.match(line):
            _blank(out)                  # разделитель в Telegram — просто пустая строка
            i += 1
            continue

        item = _LIST_RE.match(line)
        if item:
            depth = len(item.group(1).replace("\t", "  ")) // 2
            marker = BULLET if item.group(2) else f"{item.group(3)}. "
            out.append(INDENT * depth + marker + inline(item.group(4)))
            i += 1
            continue

        quoted = _QUOTE_RE.match(line)
        if quoted:
            out.append(QUOTE + inline(quoted.group(1)) if quoted.group(1).strip() else "")
            i += 1
            continue

        if not line.strip():
            _blank(out)
            i += 1
            continue

        out.append(inline(line.rstrip()))
        i += 1

    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


# ------------------------------------------------------------------ разбиение

def _safe_cut(s: str, limit: int) -> int:
    """Наибольшая позиция ≤ limit, где не открыт ни один тег и мы не внутри `<…>`."""
    depth = 0
    best = 0
    i = 0
    n = len(s)
    while i < n and i <= limit:
        if s[i] == "<":
            m = _TAG_RE.match(s, i)
            if m:
                if m.group(0).startswith("</"):
                    depth = max(0, depth - 1)
                elif not m.group(0).endswith("/>"):
                    depth += 1
                i = m.end()
                if depth == 0 and i <= limit:
                    best = i
                continue
        i += 1
        if depth == 0 and i <= limit:
            best = i
    return best or limit


def _cut_line(line: str, limit: int) -> list[str]:
    if len(line) <= limit:
        return [line]
    out = []
    rest = line
    while len(rest) > limit:
        cut = _safe_cut(rest, limit)
        out.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        out.append(rest)
    return out


def _split_pre(block: str, limit: int) -> list[str]:
    """Длинный <pre> закрываем и открываем заново, чтобы подсветка не растеклась."""
    inner = block[len("<pre>"):]
    if inner.endswith("</pre>"):
        inner = inner[:-len("</pre>")]
    wrap = len("<pre></pre>")
    chunks: list[str] = []
    cur = ""
    for line in inner.split("\n"):
        for piece in _cut_line(line, max(1, limit - wrap)):
            add = len(piece) + (1 if cur else 0)
            if cur and len(cur) + add + wrap > limit:
                chunks.append(cur)
                cur = ""
                add = len(piece)
            cur += ("\n" if cur else "") + piece
    if cur:
        chunks.append(cur)
    return [f"<pre>{c}</pre>" for c in chunks] or ["<pre></pre>"]


def _split_block(block: str, limit: int) -> list[str]:
    if block.startswith("<pre>"):
        return _split_pre(block, limit)
    out: list[str] = []
    cur = ""
    for line in block.split("\n"):
        for piece in _cut_line(line, limit):
            add = len(piece) + (1 if cur else 0)
            if cur and len(cur) + add > limit:
                out.append(cur)
                cur = ""
                add = len(piece)
            cur += ("\n" if cur else "") + piece
    if cur:
        out.append(cur)
    return out or [""]


def split_html(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Режет готовый HTML по границам блоков, не разрывая теги."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    cur = ""
    for block in re.split(r"\n{2,}", text):
        if cur and len(cur) + 2 + len(block) <= limit:
            cur += "\n\n" + block
            continue
        if cur:
            parts.append(cur)
            cur = ""
        if len(block) <= limit:
            cur = block
            continue
        chunks = _split_block(block, limit)
        parts.extend(chunks[:-1])
        cur = chunks[-1]
    if cur:
        parts.append(cur)
    return parts or [""]


def prepare(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Ответ агента → готовые к отправке куски HTML."""
    return split_html(to_html(text), limit)


# ------------------------------------------------------------------ отправка

def to_plain(html: str) -> str:
    """Тот же текст без разметки — запасной вариант, когда Telegram теги не принял."""
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    return _unescape(_TAG_RE.sub("", text))


def is_markup_error(exc: BaseException) -> bool:
    # Тип проверяется всегда, в том числе когда telegram не импортировался: иначе сетевой
    # сбой со словом «tag» в тексте сошёл бы за отказ по разметке и ответ ушёл бы дважды.
    known = BadRequest is not None and isinstance(exc, BadRequest)
    if not known and type(exc).__name__ != "BadRequest":
        return False
    text = str(exc).lower()
    return "parse" in text or "entit" in text or "tag" in text


async def send(bot, chat_id, html: str, **kw):
    """Отправить с разметкой; при отказе Telegram — тем же текстом без неё.

    Разметка — украшение. Потерять из-за неё ответ владелицы нельзя.
    """
    try:
        return await bot.send_message(chat_id, html, parse_mode=PARSE_MODE, **kw)
    except Exception as exc:  # noqa: BLE001 — решает is_markup_error, остальное пробрасываем
        if not is_markup_error(exc):
            raise
        log.warning("Telegram не принял разметку — отправляю без неё: %s", type(exc).__name__, exc_info=True)
        return await bot.send_message(chat_id, to_plain(html), **kw)
