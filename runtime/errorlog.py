"""Журнал ошибок JARVIS: записывает сбой один раз с причиной и считает повторы.

Два вида записей (`kind`):
  bot   — сбой кода бота (исключение, упавший ход, таймаут): нужен тому, кто чинит;
  agent — ошибка самого агента (отказ Guard, упавший вызов инструмента): из них собирается
          памятка «не повторяй», её читает агент в начале сессии (`digest`, хук session_start).

Файлы (state/, не в git):
  errors.jsonl       — каждое событие: ts, fp, source, type, message, trace (без секретов);
  errors_index.json  — по отпечатку `fp`: сколько раз, когда впервые/в последний раз, подсказка `hint`.

Отпечаток один у «одной и той же» ошибки: цифры, пути и идентификаторы в тексте не считаются.
Всё проходит `runtime.redact`; `record` никогда не бросает исключений и не пишет в `logging`
(иначе обработчик, подвешенный на логгер, зациклился бы).

Командная строка: `python -m runtime.errorlog [list|show <fp>|hint <fp> <текст>|fixed <fp>|digest]`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.redact import redact

ROOT = Path(__file__).resolve().parents[1]
ERRORS_PATH = ROOT / "state" / "errors.jsonl"
INDEX_PATH = ROOT / "state" / "errors_index.json"
MAX_BYTES = 5 * 1024 * 1024      # ротация: errors.jsonl -> errors.1.jsonl
MESSAGE_LIMIT = 500
TRACE_LIMIT = 1800
TRACE_FRAMES = 8
CTX_LIMIT = 200
KINDS = ("bot", "agent")

DIGEST_DAYS = 14
DIGEST_LIMIT = 10
DIGEST_MIN_REPEATS = 2           # ошибка агента попадает в памятку, когда повторилась

_lock = threading.Lock()

_VOLATILE = [
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"]*|(?:~|\.{1,2})?/[^\s'\"]+"), "<путь>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE), "<id>"),
    (re.compile(r"\d+"), "N"),
    (re.compile(r"\s+"), " "),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(text: str) -> str:
    for pattern, repl in _VOLATILE:
        text = pattern.sub(repl, text)
    return text.strip().lower()[:300]


def fingerprint(source: str, exc_type: str, message: str, frame: str = "") -> str:
    key = "|".join([source, exc_type, _normalize(message), frame])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _innermost_frame(exc: BaseException | None) -> str:
    tb = getattr(exc, "__traceback__", None)
    if tb is None:
        return ""
    last = traceback.extract_tb(tb)[-1]
    return f"{Path(last.filename).name}:{last.name}"


def _trace(exc: BaseException | None) -> str:
    if exc is None or getattr(exc, "__traceback__", None) is None:
        return ""
    frames = traceback.format_exception(type(exc), exc, exc.__traceback__, limit=-TRACE_FRAMES)
    return redact("".join(frames))[-TRACE_LIMIT:]


def _clean(value, limit: int = CTX_LIMIT):
    if isinstance(value, str):
        return redact(value)[:limit]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact(str(value))[:limit]


def _load_index(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def record(source: str, error=None, *, message: str | None = None, kind: str = "bot", **ctx) -> str | None:
    """Записывает ошибку; возвращает отпечаток или None, если записать не вышло. Не бросает исключений.

    `error` — исключение (берутся тип, текст и трассировка) или строка; `message` перекрывает текст.
    `ctx` — короткие поля для разбора (task_id, tool…), значения обрезаются и чистятся от секретов.
    """
    try:
        exc = error if isinstance(error, BaseException) else None
        given_type = ctx.pop("type", None)
        exc_type = type(exc).__name__ if exc is not None else str(given_type or "Error")
        text = message if message is not None else (str(exc) if exc is not None else str(error or ""))
        text = " ".join(redact(text).split())[:MESSAGE_LIMIT]
        kind = kind if kind in KINDS else "bot"
        source = str(source)[:80]
        fp = fingerprint(source, exc_type, text, _innermost_frame(exc))
        now = _now().isoformat(timespec="seconds")
        line = {"ts": now, "fp": fp, "kind": kind, "source": source, "type": exc_type,
                "message": text, "trace": _trace(exc),
                "ctx": {str(k)[:40]: _clean(v) for k, v in ctx.items()}}
        path, index_path = Path(ERRORS_PATH), Path(INDEX_PATH)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(path.with_name(path.stem + ".1" + path.suffix))
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            index = _load_index(index_path)
            row = index.get(fp) or {"kind": kind, "source": source, "type": exc_type,
                                    "message": text, "count": 0, "first": now, "hint": ""}
            row.update(count=int(row.get("count", 0)) + 1, last=now)
            row.pop("fixed", None)   # вернулась после «починено» — снова в работе
            index[fp] = row
            _save_index(index_path, index)
        return fp
    except Exception:  # noqa: BLE001 — журнал ошибок не должен сам ронять бота
        return None


# ---------- памятка агенту ----------

def digest(days: int = DIGEST_DAYS, limit: int = DIGEST_LIMIT, now: datetime | None = None,
           index_path: Path | None = None) -> str:
    """Памятка «что уже не получалось» для начала сессии агента; пусто, если повторов не было.

    Берутся ошибки агента (kind=agent), которые повторились и случались за последние `days` дней.
    Сначала самые частые. Подсказка `hint` (её ставит разработчик или владелица) идёт строкой «делай так».
    """
    now = now or _now()
    cutoff = now - timedelta(days=days)
    rows = []
    for fp, row in _load_index(Path(index_path or INDEX_PATH)).items():
        if row.get("kind") != "agent" or row.get("fixed"):
            continue
        try:
            last = datetime.fromisoformat(row["last"])
        except (KeyError, ValueError):
            continue
        if last >= cutoff and int(row.get("count", 0)) >= DIGEST_MIN_REPEATS:
            rows.append((int(row["count"]), last, fp, row))
    if not rows:
        return ""
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    lines = ["Журнал ошибок JARVIS: это уже не получалось. Не повторяй, выбери другой путь "
             "(если не уверена, как — скажи владелице):"]
    for count, last, fp, row in rows[:limit]:
        what = f"{row.get('source', '?')}: {row.get('message', '')}"[:260]
        line = f"- ×{count}, последний раз {last:%d.%m}: {what}"
        if row.get("hint"):
            line += f" → делай так: {row['hint']}"
        lines.append(line)
    return "\n".join(lines)


# ---------- подвеска на logging ----------

class ErrorJournalHandler(logging.Handler):
    """Пишет в журнал каждую запись WARNING и выше с любого логгера (с трассировкой, если она есть)."""

    def __init__(self):
        super().__init__(level=logging.WARNING)

    def emit(self, record_: logging.LogRecord) -> None:
        try:
            exc = record_.exc_info[1] if record_.exc_info else None
            record(record_.name, exc, message=record_.getMessage(), type=record_.levelname)
        except Exception:  # noqa: BLE001
            pass


class RedactFilter(logging.Filter):
    """Маскирует секреты в тексте записи и в трассировке — раньше любой обработчик видел их как есть."""

    def filter(self, record_: logging.LogRecord) -> bool:
        try:
            record_.msg, record_.args = redact(record_.getMessage()), ()
            if record_.exc_info and not record_.exc_text:
                record_.exc_text = redact(logging.Formatter().formatException(record_.exc_info))
        except Exception:  # noqa: BLE001
            pass
        return True


# ---------- командная строка ----------

def _print_rows(index: dict) -> None:
    rows = sorted(index.items(), key=lambda kv: kv[1].get("last", ""), reverse=True)
    for fp, row in rows:
        mark = "✓" if row.get("fixed") else " "
        print(f"{mark} {fp}  ×{row.get('count', 0):<4} {row.get('kind', '?'):5} "
              f"{row.get('last', '')[:16]}  {row.get('source', '?')}: {row.get('message', '')[:90]}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args.pop(0) if args else "list"
    index = _load_index(Path(INDEX_PATH))
    if cmd == "list":
        _print_rows(index)
    elif cmd == "digest":
        print(digest() or "(повторяющихся ошибок агента нет)")
    elif cmd == "show" and args:
        fp, trace = args[0], ""
        print(json.dumps(index.get(fp), ensure_ascii=False, indent=1))
        try:
            for raw in Path(ERRORS_PATH).read_text(encoding="utf-8").splitlines()[-2000:]:
                row = json.loads(raw)
                if row.get("fp") == fp:
                    trace = row.get("trace") or trace
        except (OSError, ValueError):
            pass
        print(trace or "(трассировки нет)")
    elif cmd in ("hint", "fixed") and args and args[0] in index:
        with _lock:
            if cmd == "hint":
                index[args[0]]["hint"] = " ".join(args[1:])[:300]
            else:
                index[args[0]]["fixed"] = _now().isoformat(timespec="seconds")
            _save_index(Path(INDEX_PATH), index)
        print("ок")
    else:
        print(__doc__.strip().splitlines()[-1])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
