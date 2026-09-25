"""Файлы из Telegram: очистка имён, папка inbox/, статусы контент-комплектов.

Ничего не знает про Telegram API — только пути и содержимое на диске.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MAX_NAME = 100
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SPACES = re.compile(r"\s+")
# Зарезервированные имена устройств Windows: CON, PRN, AUX, NUL, COM1..9, LPT1..9
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}

CONTENT_DIR = Path("essa-ai") / "content"
PUBLISHED = CONTENT_DIR / "PUBLISHED.md"
_BUNDLE_RE = re.compile(r"essa-ai[/\\]content[/\\]([0-9A-Za-zА-Яа-яЁё._\-]+)")

DECISIONS = {
    "accepted": "Принято",
    "redo": "Переделать",
    "published": "Опубликовано",
}


def sanitize_name(name: str) -> str:
    """Безопасное имя файла: без путей, спецсимволов и имён устройств Windows."""
    name = (name or "").replace("\r", " ").replace("\n", " ")
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _BAD_CHARS.sub("_", name)
    name = _SPACES.sub("_", name).strip("._ ")
    if not name:
        return "file"
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED:
        name = "_" + name
    if len(name) > MAX_NAME:
        suffix = Path(name).suffix[:10]
        name = name[: MAX_NAME - len(suffix)] + suffix
    return name


def inbox_path(root: Path | str, name: str, when: dt.date | None = None) -> Path:
    """Путь inbox/YYYY-MM-DD/<очищенное имя> без перезаписи существующего файла."""
    day = (when or dt.date.today()).isoformat()
    folder = Path(root) / "inbox" / day
    clean = sanitize_name(name)
    candidate = folder / clean
    if not candidate.exists():
        return candidate
    stem, suffix = Path(clean).stem, Path(clean).suffix
    n = 1
    while (folder / f"{stem}-{n}{suffix}").exists():
        n += 1
    return folder / f"{stem}-{n}{suffix}"


def reserve_path(root: Path | str, name: str, when: dt.date | None = None,
                 attempts: int = 100) -> Path:
    """Занимает имя в inbox/ одной операцией (O_EXCL): два файла подряд не затрут друг друга."""
    day = (when or dt.date.today()).isoformat()
    folder = Path(root) / "inbox" / day
    folder.mkdir(parents=True, exist_ok=True)
    clean = sanitize_name(name)
    stem, suffix = Path(clean).stem, Path(clean).suffix
    for n in range(attempts):
        candidate = folder / (clean if n == 0 else f"{stem}-{n}{suffix}")
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise FileExistsError(f"не нашёл свободного имени для {clean} за {attempts} попыток")


def save_bytes(root: Path | str, name: str, data: bytes, when: dt.date | None = None) -> Path:
    path = reserve_path(root, name, when=when)
    path.write_bytes(data)
    return path


def find_content_bundle(text: str, root: Path | str = ROOT) -> str | None:
    """Имя папки комплекта, если ответ агента ссылается на существующий essa-ai/content/<папка>."""
    root = Path(root)
    for match in _BUNDLE_RE.finditer(text or ""):
        name = match.group(1)
        if name.upper().startswith("PUBLISHED"):
            continue
        if (root / CONTENT_DIR / name).is_dir():
            return name
    return None


def mark_content(root: Path | str, name: str, decision: str, when: dt.date | None = None,
                 note: str = "") -> str:
    """Пишет решение владелицы в <комплект>/status; «Опубликовано» — строку в PUBLISHED.md."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got {decision!r}")
    root = Path(root)
    bundle = root / CONTENT_DIR / sanitize_name(name)
    if not bundle.is_dir():
        raise FileNotFoundError(bundle)
    bundle.joinpath("status").write_text(decision + "\n", encoding="utf-8")
    if decision == "published":
        day = (when or dt.date.today()).isoformat()
        line = f"- {day} | {name} | {note or 'отмечено кнопкой в Telegram'}\n"
        published = root / PUBLISHED
        published.parent.mkdir(parents=True, exist_ok=True)
        with open(published, "a", encoding="utf-8") as fh:
            fh.write(line)
    return DECISIONS[decision]


# ---------------------------------------------------------- вложения (📎)

# Готовые файлы (PDF лидмагнита, PNG карусели, radar.md …) агент называет строкой
# «📎 <путь>» в ответе — так бот понимает, что прислать документом, а не просто упомянуть.
ATTACH_MAX_FILES = 15
ATTACH_MAX_BYTES = 50 * 1024 * 1024   # лимит Telegram на документ
_ATTACH_LINE_RE = re.compile(r"^📎\s*(.+?)\s*$")

_GUARD_PATH = ROOT / ".claude" / "hooks" / "guard.py"
_POLICY_PATH = ROOT / "runtime" / "policy.yaml"
_guard_module = None      # кэш: guard.py читаем и исполняем один раз на процесс
_guard_policy = None


def extract_attachments(text: str) -> tuple[str, list[str]]:
    """Убирает строки «📎 <путь>» из ответа агента, возвращает (текст без них, пути по порядку)."""
    kept: list[str] = []
    paths: list[str] = []
    for line in (text or "").split("\n"):
        m = _ATTACH_LINE_RE.match(line.strip())
        if m:
            paths.append(m.group(1))
        else:
            kept.append(line)
    return "\n".join(kept), paths


def _load_guard():
    """Читает .claude/hooks/guard.py как модуль — тот же способ, что tests/test_guard.py.

    Секретов не заводим второй раз: решение, что путь запрещён (.env, credentials,
    state/secrets/, ~/.ssh, профиль браузера…), берём из настоящего Guard.
    """
    global _guard_module, _guard_policy
    if _guard_module is None:
        import sys

        spec = importlib.util.spec_from_file_location("jarvis_guard_attachments", _GUARD_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod   # dataclass(frozen=True) с `from __future__ import annotations`
        spec.loader.exec_module(mod)   # ищет свой модуль в sys.modules — без записи упадёт AttributeError
        _guard_module = mod
        _guard_policy = mod.load_policy(_POLICY_PATH)
    return _guard_module, _guard_policy


def _is_denied_by_guard(root: Path, abs_path: Path) -> bool:
    guard, policy = _load_guard()
    event = {"hook_event_name": "PreToolUse", "tool_name": "Read",
              "tool_input": {"file_path": str(abs_path)}}
    decision = guard.decide(event, policy=policy, root=root, env={})
    return decision.level == "DENY"


def resolve_attachment(root: Path | str, raw: str) -> Path:
    """Путь из строки «📎 …» → безопасный абсолютный путь, либо ValueError с человеческой причиной.

    Проверяет по порядку: путь считается от корня проекта и не должен после `resolve()`
    оказаться снаружи (никаких `..`, симлинков наружу, чужих абсолютных путей); файл
    существует и это обычный файл, а не папка; не защищён Guard'ом (секреты); не больше
    лимита Telegram. Вызывающий код превращает исключение в «Не отправил <имя>: <причина>».
    """
    root = Path(root).resolve()
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("пустой путь")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise ValueError("файл не найден")
    if resolved != root and root not in resolved.parents:
        raise ValueError("путь вне папки проекта")
    if resolved.is_dir():
        raise ValueError("это папка, а не файл")
    if not resolved.is_file():
        raise ValueError("это не обычный файл")
    if _is_denied_by_guard(root, resolved):
        raise ValueError("защищённый файл — не отправляю")
    size = resolved.stat().st_size
    if size > ATTACH_MAX_BYTES:
        raise ValueError(f"файл больше {ATTACH_MAX_BYTES // (1024 * 1024)} МБ")
    return resolved
