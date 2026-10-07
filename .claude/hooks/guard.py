"""Guard — PreToolUse-хук JARVIS.

Вход: JSON PreToolUse на stdin. Выход: exit 0 (пропустить) или exit 2 + причина в stderr (отказ).
Правила — runtime/policy.yaml. Любая ошибка внутри хука — отказ (fail-closed).

Публичное:
    load_policy(path) -> dict
    decide(event, policy, root, env) -> Decision(level, action, reason, kind)   # чистая функция
    run(event, root, policy_path, env, mode) -> (exit_code, reason)             # с запросом к Approvals API

Режимы (аргумент `--mode`, не переменная окружения — бот не должен его унаследовать):
    jarvis (по умолчанию) — бот: всё по policy.yaml, EXTERNAL/MONEY — кнопка в Telegram;
    dev — сессии разработки Claude Code (`.claude/settings.json`): действуют только жёсткие
          запреты из `policy.yaml: dev_mode.deny_kinds` (секреты, опасные команды, пароли/карты,
          оплата); защищённые пути сняты, остальное решают штатные разрешения Claude Code.
Неизвестный режим — отказ (ADR 0012).

Codex (P4.1, аргумент `--runtime codex`, из `.codex/hooks.json`): вход хука Codex переводится в события Guard
(`Bash` — как есть; `apply_patch` — по файлу патча: добавление/правка → Write/Edit, удаление → rm) и решается
тем же `decide()`. Codex слушает только JSON-запрет и пропускает вызов, если хук упал, — поэтому ответ
всегда JSON, выход всегда 0, любая ошибка — запрет. Режим: есть `JARVIS_TASK_ID` (ставит бот) — полный,
нет — режим разработки (её собственные сессии Codex). Окружение тут может только ужесточить режим.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LEVELS = ["READ", "WRITE", "EXTERNAL", "MONEY", "DENY"]
MODES = ("jarvis", "dev")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "runtime" / "policy.yaml"


@dataclass(frozen=True)
class Decision:
    level: str   # READ | WRITE | EXTERNAL | MONEY | DENY
    action: str  # allow | ask | deny
    reason: str
    kind: str = ""


def load_policy(path) -> dict:
    import yaml  # внутри: ошибка импорта тоже должна дать отказ

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("policy.yaml: ожидался словарь")
    return data


# ---------- пути ----------

def _norm(s: str) -> str:
    return re.sub(r"/+", "/", str(s).replace("\\", "/")).lower()


_DRIVE = re.compile(r"^[a-z]:$")
_LONG_PREFIX = re.compile(r"^(?:\\\\\?\\|//\?/)")


def _norm_path(s: str) -> str:
    """Путь так, как его разберёт Windows: точки и пробелы в конце имени отбрасываются (`runtime./policy.yaml` —
    это `runtime/policy.yaml`), потоки NTFS (`file:поток`) — тоже, регистр не важен."""
    out = []
    for i, part in enumerate(_norm(s).split("/")):
        if part in ("", ".", "..") or (i == 0 and _DRIVE.match(part)):
            out.append(part)
        else:
            out.append(part.split(":", 1)[0].rstrip(". "))
    return "/".join(out)


def _with_base(path: str, base: Path) -> str:
    p = _LONG_PREFIX.sub("", os.path.expanduser(str(path)))   # `\\?\C:\…` — тот же путь без приставки
    return p if os.path.isabs(p) else os.path.join(str(base), p)


def _abs(path: str, base: Path) -> str:
    return _norm_path(os.path.normpath(_with_base(path, base)))


def _variants(path: str, base: Path) -> list[str]:
    """Путь как написан и его настоящее место: junction и символическая ссылка (`outbox/rt` → `runtime`) и
    короткие имена Windows (`INTEGR~1`) раскрываются, иначе защита папок обходится ссылкой."""
    lexical = _abs(path, base)
    try:
        real = _norm_path(os.path.realpath(_with_base(path, base)))
    except (OSError, ValueError):
        return [lexical]
    return [lexical] if real == lexical else [lexical, real]


def _glob_hit(abs_path: str, pattern: str, root: Path) -> bool:
    pat = _norm(os.path.expanduser(pattern)) if pattern.startswith("~") else pattern
    if pattern.startswith("**/"):
        tail = _norm(pattern[3:])
        name_parts = abs_path.split("/")
        return any(fnmatch.fnmatchcase(part, tail) for part in name_parts) or fnmatch.fnmatchcase(abs_path, "*/" + tail)
    full = _abs(pat, root) if not pattern.startswith("~") else _norm(os.path.normpath(os.path.expanduser(pattern)))
    if full.endswith("/**"):
        base = full[:-3]
        return abs_path == base or abs_path.startswith(base + "/")
    return fnmatch.fnmatchcase(abs_path, full)


def _literal(pattern: str) -> str:
    """Опорная подстрока шаблона для поиска в тексте команды."""
    s = _norm(pattern)
    for prefix in ("**/", "~/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if s.endswith("/**"):
        s = s[:-3]
    return s.split("*")[0].rstrip("/")


def _text_mentions(text: str, patterns, root: Path) -> str | None:
    t = _norm(text)
    root_n = _norm(root)
    t = t.replace(root_n + "/", "")
    for pat in patterns or []:
        lit = _literal(pat)
        if not lit:
            continue
        # шаблон вида "name*" ловит и продолжения имени (.envrc, credentials.bak)
        tail = "" if _norm(pat).split("/")[-1].startswith(lit.split("/")[-1] + "*") else r"(?![\w\-])"
        if re.search(r"(?<![\w.\-])" + re.escape(lit) + tail, t):
            return pat
    return None


def _path_denied(value: str, patterns, root: Path, base: Path) -> str | None:
    for absolute in _variants(value, base):
        for pat in patterns or []:
            if _glob_hit(absolute, pat, root):
                return pat
    return _text_mentions(value, patterns, root)


def _root_file_name(token: str, root: Path) -> str | None:
    """Имя файла, лежащего прямо в корне проекта (`argparse.py`, `./start.bat`, `<корень>/x.py`), иначе None."""
    t = _norm_path(token.strip())
    root_n = _norm(os.path.normpath(str(root)))
    if t.startswith(root_n + "/"):
        t = t[len(root_n) + 1:]
    t = t[2:] if t.startswith("./") else t
    return t if t and "/" not in t and not t.startswith(("-", "$")) else None


def _protected_root_name(name: str, policy: dict) -> str | None:
    for pat in policy.get("protected_root_files") or []:
        if fnmatch.fnmatchcase(name.lower(), pat.lower()):
            return pat
    return None


def _root_file_target(variants: list[str], root: Path, policy: dict) -> str | None:
    """Файл запуска в корне проекта: `python -m …` ставит корень первым в sys.path, и положенный туда
    `argparse.py` подменил бы стандартный модуль внутри доверенного запуска; `pytest` берёт `conftest.py`,
    а `start.bat` — это сам запуск бота."""
    root_n = _norm(os.path.normpath(str(root)))
    for v in variants:
        head, _, name = v.rpartition("/")
        if head == root_n and _protected_root_name(name, policy):
            return name
    return None


def _shell_root_file(text: str, root: Path, policy: dict) -> str | None:
    for token in re.split(r"[\s;&|()<>,\x22'`=]+", _dequote(text)):
        name = _root_file_name(token, root)
        if name and _protected_root_name(name, policy):
            return name
    return None


def _inside(abs_path: str, root: Path) -> bool:
    r = _norm(os.path.normpath(str(root)))
    return abs_path == r or abs_path.startswith(r + "/")


# ---------- команды ----------

# .e* / .en? / .[e]nv / .env* — подбор имени секрета шаблоном оболочки
_SECRET_WILDCARD = re.compile(
    r"(?<![\w.])\.(e|\[[^\]]*e[^\]]*\])(n|\[[^\]]*\])?(v|\[[^\]]*\])?[*?\[]"
    r"|(?<![\w.])\.\[[^\]]*e[^\]]*\]"
    r"|(?<![\w.])\.[e?][n?]?[v?]?(?=[\s;|&)]|$)", re.IGNORECASE)
_WRITE_VERBS = re.compile(
    r"(?<![0-9&])>(?!&)|\b(tee|cp|mv|copy|move|ren|rename|touch|mkdir|ln|xcopy|robocopy|"
    r"set-content|add-content|out-file|copy-item|move-item|new-item|rename-item|export-\w+)\b"
    r"|\bsed\s+-i|\bgit\s+(checkout|restore|apply|am|reset|stash|mv|clone)\b"
    r"|\bmklink\b|\bfsutil\b|-itemtype\s+(junction|symboliclink|hardlink)", re.IGNORECASE)
_INTERPRETERS = re.compile(r"\b(python\w*|py|node|pwsh|powershell|perl|ruby)\b", re.IGNORECASE)
_SAFE_SINKS = {"/dev/null", "nul", "$null", "/dev/stdout", "/dev/stderr"}


def _dequote(text: str) -> str:
    """Склеивает "a" + "b", убирает кавычки и экранирование — правила видят саму команду."""
    t = re.sub(r"[\"']\s*\+\s*[\"']", "", text)
    return t.replace("\\\"", "").replace('"', "").replace("'", "").replace("`", "")


def _outside_targets(command: str, root: Path, base: Path, allow) -> list[str]:
    found = []
    for tok in re.split(r"[\s;&|()<>,]+", _dequote(command)):
        if not tok or tok.lower() in _SAFE_SINKS or "://" in tok:
            continue
        if re.match(r"^(\$|%\w+%)", tok):  # путь из переменной — куда он ведёт, не известно: спросить
            found.append(tok)
            continue
        m = re.match(r"^/([a-z])/(.*)$", tok, re.IGNORECASE)  # Git Bash: /c/Users → c:/Users
        path = f"{m.group(1)}:/{m.group(2)}" if m else tok
        absolute_like = (re.match(r"^[a-z]:[\\/]", path, re.IGNORECASE) or path.startswith(("~", "\\\\"))
                         or re.match(r"^/[^/]+/", path) or re.search(r"(^|[\\/])\.\.([\\/]|$)", path))
        if not absolute_like:
            continue
        absolute = _abs(path, base)
        if _inside(absolute, root) or any(_glob_hit(absolute, p, root) for p in allow):
            continue
        found.append(tok)
    return found


# ---------- запуск кода ----------

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_PY_OR_NODE = re.compile(r"^(python(\d+(\.\d+)?)?|pythonw|py|node)(\.exe)?$", re.IGNORECASE)
_SHELLS = re.compile(r"^(powershell|pwsh|cmd)(\.exe)?$", re.IGNORECASE)
_FLAGS_WITH_VALUE = {"-X", "-W", "-Q"}
_INLINE = {"-c", "-", "-e", "-p", "--eval", "--print"}


def _rel_target(path: str, root: Path) -> str:
    t = path.replace("\\", "/")
    if t.startswith("./"):
        t = t[2:]
    if os.path.isabs(t) or re.match(r"^[a-z]:/", t, re.IGNORECASE):
        absolute = _abs(t, root)
        root_n = _norm(os.path.normpath(str(root)))
        if absolute.startswith(root_n + "/"):
            t = absolute[len(root_n) + 1:]
    return t.lower()


def _script_runs(command: str, policy: dict, root: Path) -> list[tuple[str, bool]]:
    """Запуски интерпретатора в команде: [(сегмент, доверенный ли)].

    Доверенный — `-m <модуль>` из `script_allow.modules` или файл из `script_allow.files`
    (только места, куда агент писать не может). Код в строке (`-c`, `-e`, stdin) — недоверенный.
    """
    allow = policy.get("script_allow") or {}
    modules = [m.lower() for m in allow.get("modules") or []]
    files = [f.lower() for f in allow.get("files") or []]
    runs = []
    for segment in _SEGMENT_SPLIT.split(_dequote(command)):
        tokens = segment.split()
        while tokens and tokens[0] in ("&", "."):
            tokens = tokens[1:]
        if not tokens:
            continue
        exe = re.split(r"[\\/]", tokens[0])[-1]
        if _SHELLS.match(exe):
            if _INTERPRETERS.search(" ".join(tokens[1:])):
                runs.append((segment, False))
            continue
        if not _PY_OR_NODE.match(exe):
            continue
        trusted, args, i = False, tokens[1:], 0
        while i < len(args):
            arg = args[i]
            if arg == "-m" and i + 1 < len(args):
                trusted = any(fnmatch.fnmatchcase(args[i + 1].lower(), m) for m in modules)
                break
            if arg in _INLINE:
                break
            if arg in _FLAGS_WITH_VALUE:
                i += 2
                continue
            if arg.startswith("-"):
                i += 1
                continue
            target = _rel_target(arg, root)
            trusted = any(fnmatch.fnmatchcase(target, f) for f in files)
            break
        runs.append((segment, trusted))
    return runs


def _without_trusted_runs(command: str, runs) -> str:
    """Команда без доверенных запусков, где нет записи: упоминание `integrations` в
    `python -m integrations.visuals.build` — это запуск, а не правка защищённой папки."""
    keep = [seg for seg in _SEGMENT_SPLIT.split(_dequote(command))
            if not any(seg == r_seg and ok and not _WRITE_VERBS.search(seg) for r_seg, ok in runs)]
    return "\n".join(keep)


# ---------- большие файлы ----------

def _int(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _chunk_bytes(path: str, offset: int, limit: int, cap: int) -> int:
    """Сколько байт вернёт чтение с offset строки в limit строк. Считает не дальше cap+1 байта.

    Меряем именно байты: `limit` у Read задан в строках, и limit=999999 — это весь файл,
    а не кусок. Строки считаем сами, потому что их длина заранее не известна.
    """
    total = 0
    read = 0
    with open(path, "rb") as f:
        for number, line in enumerate(f, start=1):
            if number < max(offset, 1):
                continue
            total += len(line)
            read += 1
            if total > cap or (limit and read >= limit):
                break
    return total


def _big_read(tool: str, tool_input: dict, policy: dict, base: Path) -> str | None:
    """Чтение сверх порога → причина для EXTERNAL, иначе None.

    Поиск (Grep/Glob) сюда не попадает: в big_read.tools только инструменты чтения.
    Кусок проходит, если укладывается в порог по объёму, а не просто назван куском.

    Shell — отдельно, `_big_shell_read`: простые `cat|type|Get-Content <файл>` без ограничителя
    в цепочке. Произвольные программы, читающие файл сами (python, node), он не ловит — размер
    в такой командной строке не определить; заслон не полный сознательно.
    """
    cfg = policy.get("big_read") or {}
    field = (cfg.get("tools") or {}).get(tool)
    if not field:
        return None
    try:
        max_kb = float(cfg.get("max_kb"))
    except (TypeError, ValueError):
        raise ValueError("policy.yaml: big_read.max_kb должен быть числом")
    target = tool_input.get(field)
    if not isinstance(target, str) or not target:
        return None
    path = os.path.expanduser(target)
    if not os.path.isabs(path):
        path = os.path.join(str(base), path)
    cap = int(max_kb * 1024)
    try:
        if not os.path.isfile(path):  # нет файла или это каталог — не наше дело
            return None
        size = os.path.getsize(path)
        if size <= cap:
            return None
        chunk_fields = cfg.get("chunk_fields") or []
        if any(tool_input.get(f) not in (None, "", 0) for f in chunk_fields):
            offset = _int(tool_input.get(chunk_fields[0])) if chunk_fields else 0
            limit = _int(tool_input.get(chunk_fields[1])) if len(chunk_fields) > 1 else 0
            if _chunk_bytes(path, offset, limit, cap) <= cap:
                return None
    except OSError:  # файл недоступен — не наше дело
        return None
    return (f"файл {os.path.basename(path)} — {size / 1024:.0f} КБ, это больше {max_kb:g} КБ. "
            f"Целиком такой файл читать дорого: найди нужное через Grep "
            f"или прочитай кусок поменьше, указав offset и limit")


_CHAIN_SPLIT = re.compile(r"&&|\|\||;|\n")


def _big_shell_read(command: str, policy: dict, base: Path) -> str | None:
    """`cat|type|Get-Content <файл>` целиком, файл больше порога → причина для EXTERNAL big_read.

    Кусок или поиск — в той же цепочке есть ограничитель (`head`, `tail`, `-TotalCount`, `grep`, …) —
    проходит. Размер известен только у существующего файла; путь из переменной не угадываем.
    """
    cfg = policy.get("big_read") or {}
    readers = {r.lower() for r in cfg.get("shell_readers") or []}
    limiters = {lim.lower() for lim in cfg.get("shell_limiters") or []}
    if not readers:
        return None
    max_kb = float(cfg.get("max_kb"))
    for element in _CHAIN_SPLIT.split(_dequote(command)):
        first = element.split("|")[0].split()
        while first and first[0] in ("&", "."):
            first = first[1:]
        if not first or re.sub(r"\.exe$", "", re.split(r"[\\/]", first[0])[-1].lower()) not in readers:
            continue
        if limiters & {t.lower() for t in element.replace("|", " ").split()}:
            continue
        for token in first[1:]:
            if token.startswith("-"):
                continue
            path = os.path.expanduser(token)
            if not os.path.isabs(path):
                path = os.path.join(str(base), path)
            try:
                if os.path.isfile(path) and os.path.getsize(path) > max_kb * 1024:
                    size = os.path.getsize(path) / 1024
                    return (f"файл {os.path.basename(path)} — {size:.0f} КБ, это больше {max_kb:g} КБ. "
                            "Целиком такой файл читать дорого: найди нужное поиском (grep, Select-String) "
                            "или возьми кусок (head, tail, -TotalCount)")
            except OSError:
                continue
    return None


# ---------- данные в адресе запроса ----------

_PRIVATE_HOST = re.compile(r"^(10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0$|fe80:|f[cd][0-9a-f]{2}:)|\.local$|\.internal$")


def _url_problem(url: str, cfg: dict, *, scheme_check: bool) -> tuple[str, str, str] | None:
    """(уровень, вид, причина) для адреса или None.

    Схема не http/https (`file://`, `javascript:`, `chrome://`) — отказ: через «чтение страницы» можно было бы
    открыть локальный файл. Домашняя сеть и служебные адреса облака (169.254.…) — кнопка. Данные в адресе
    (длинные параметры или непрозрачный кусок вроде токена) — кнопка: так нельзя вынести секрет или файл."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return "EXTERNAL", "url_data", f"непонятный адрес запроса: {url[:200]}"
    scheme = parts.scheme.lower()
    if scheme_check and url.strip().lower() != "about:blank" and scheme not in ("http", "https"):
        return "DENY", "url_scheme", f"адрес со схемой «{scheme or '?'}» запрещён: только http и https ({url[:120]})"
    host = (parts.hostname or "").lower()
    if _PRIVATE_HOST.search(host):
        return "EXTERNAL", "local_network", f"адрес во внутренней сети: {host}"
    max_query, max_token = int(cfg.get("max_query") or 200), int(cfg.get("max_token") or 32)
    tail = parts.query + parts.fragment
    opaque = re.compile(r"(?=[A-Za-z0-9+=_]*\d)(?=[A-Za-z0-9+=_]*[A-Za-z])[A-Za-z0-9+=_]{%d,}" % max_token)
    if len(tail) > max_query or opaque.search(parts.path + "?" + tail):
        return "EXTERNAL", "url_data", f"в адресе запроса к {parts.netloc or '?'} похоже есть данные: {url[:200]}"
    return None


def _url_data(tool: str, tool_input: dict, policy: dict) -> tuple[str, str, str] | None:
    """Проверка адреса у инструментов «чтения страницы» (WebFetch, переход браузера)."""
    cfg = policy.get("url_data") or {}
    field = (cfg.get("tools") or {}).get(tool)
    url = tool_input.get(field) if field else None
    if not isinstance(url, str) or not url:
        return None
    return _url_problem(url, cfg, scheme_check=True)


_URL_IN_TEXT = re.compile(r"https?://[^\s'\"<>`)]+", re.IGNORECASE)


def _shell_url_data(command: str, policy: dict) -> tuple[str, str, str] | None:
    """Те же проверки для адресов внутри команды (`curl 'https://x/?d=<данные>'`): раньше смотрели только WebFetch."""
    cfg = policy.get("url_data") or {}
    for url in _URL_IN_TEXT.findall(command):
        problem = _url_problem(url, cfg, scheme_check=False)
        if problem:
            return problem
    return None


# ---------- суммы ----------

_AMOUNT_RE = re.compile(r"(\d[\d\s ]*(?:[.,]\d+)?)\s*(?:₽|руб|rub|р\.)", re.IGNORECASE)
_AMOUNT_KEYS = {"amount", "price", "total", "sum", "amount_rub", "сумма"}


def _amounts(tool_input) -> list[float]:
    found: list[float] = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in _AMOUNT_KEYS:
                    try:
                        found.append(float(str(v).replace(" ", "").replace(",", ".")))
                    except ValueError:
                        pass
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            for m in _AMOUNT_RE.finditer(x):
                try:
                    found.append(float(re.sub(r"[\s ]", "", m.group(1)).replace(",", ".")))
                except ValueError:
                    pass

    walk(tool_input)
    return found


# ---------- решение ----------

def _finish(level: str, kind: str, reason: str, policy: dict, tool_input, env) -> Decision:
    money_kinds = set(policy.get("money_kinds") or [])
    if level == "EXTERNAL" and kind in money_kinds:
        level = "MONEY"
    if level == "DENY":
        return Decision("DENY", "deny", reason, kind)
    if level == "MONEY":
        limit_raw = (env or {}).get(policy.get("purchase_limit_env") or "JARVIS_PURCHASE_LIMIT_RUB")
        if limit_raw and kind != "delete":
            try:
                limit = float(str(limit_raw).replace(" ", "").replace(",", "."))
            except ValueError:
                return Decision("MONEY", "deny", "лимит покупки задан неверно", kind)
            over = [a for a in _amounts(tool_input) if a > limit]
            if over:
                return Decision("MONEY", "deny",
                                f"сумма {max(over):g} ₽ выше лимита {limit:g} ₽ — оплати сама", kind)
        return Decision("MONEY", "ask", reason, kind)
    if level == "EXTERNAL":
        mode = (policy.get("external") or {}).get(kind, "ask")
        return Decision("EXTERNAL", "allow" if mode == "auto" else "ask", reason, kind)
    return Decision(level, "allow", reason, kind)


_PREVIEW_LIMIT = 300


def _change_preview(tool_input: dict) -> str:
    """Начало правки одной строкой — его владелица видит на кнопке."""
    parts = [tool_input.get(f) for f in ("new_string", "content", "new_source")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            parts.append(edit.get("new_string"))
    text = " ".join(" ".join(str(p).split()) for p in parts if isinstance(p, str) and p.strip())
    return text if len(text) <= _PREVIEW_LIMIT else text[:_PREVIEW_LIMIT] + "…"


def _self_modify_reason(target: str, tool_input: dict) -> str:
    preview = _change_preview(tool_input)
    return f"правка собственных правил JARVIS: {target}" + (f" — «{preview}»" if preview else "")


def _tool_matches(spec: str, tool: str) -> bool:
    return spec in ("*", None, "") or re.fullmatch(spec, tool) is not None


def decide(event: dict, policy: dict, root, env=None) -> Decision:
    root = Path(root)
    tool = event.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return Decision("DENY", "deny", "нет имени инструмента", "malformed")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return Decision("DENY", "deny", "аргументы инструмента не словарь", "malformed")
    base = Path(event.get("cwd") or root)
    blob = json.dumps(tool_input, ensure_ascii=False)
    deny_paths = policy.get("deny_paths") or []
    protected = policy.get("protected_write_paths") or []
    ask_paths = policy.get("ask_write_paths") or []

    # 1. секреты — в любом инструменте, в полях путей и в тексте команд
    for field in policy.get("path_fields") or []:
        val = tool_input.get(field)
        if isinstance(val, str) and val and _path_denied(val, deny_paths, root, base):
            return Decision("DENY", "deny", f"доступ к секретам запрещён ({val})", "secret")
    if tool in (policy.get("shell_tools") or []) or tool.startswith("mcp__"):
        hit = _text_mentions(blob, deny_paths, root) or _text_mentions(_dequote(blob), deny_paths, root)
        if hit:
            return Decision("DENY", "deny", f"команда упоминает секреты ({hit})", "secret")
    if tool in (policy.get("shell_tools") or []):
        cmd = _dequote(str(tool_input.get("command") or ""))
        if _SECRET_WILDCARD.search(cmd) or re.search(r"credentials", cmd, re.IGNORECASE):
            return Decision("DENY", "deny", "команда подбирает имя секрета шаблоном", "secret")

    write_tools = policy.get("write_tools") or {}
    shell = tool in (policy.get("shell_tools") or [])

    # 1б. права субагента по роли: `agent_type` есть во входе хука только у вызовов субагента (P2.0)
    agent = event.get("agent_type")
    scope = (policy.get("agents") or {}).get(agent) if isinstance(agent, str) else None
    if isinstance(scope, dict):
        allowed = scope.get("write") or []
        if tool in write_tools:
            target = tool_input.get(write_tools[tool])
            absolute = _abs(target, base) if isinstance(target, str) and target else ""
            if not absolute or not any(_glob_hit(absolute, pat, root) for pat in allowed):
                where = ", ".join(allowed) if allowed else "никуда"
                return Decision("DENY", "deny", f"помощник {agent} пишет только в: {where} ({target})",
                                "agent_scope")
        elif shell and not scope.get("shell"):
            return Decision("DENY", "deny", f"помощнику {agent} команды не положены", "agent_scope")

    # 2. запись в защищённые места
    level, kind, reason = "READ", "", "чтение"
    if tool in write_tools:
        target = tool_input.get(write_tools[tool])
        if not isinstance(target, str) or not target:
            return Decision("DENY", "deny", "нет пути записи", "malformed")
        variants = _variants(target, base)
        for pat in protected:
            if any(_glob_hit(v, pat, root) for v in variants):
                return Decision("DENY", "deny", f"запись в защищённое место запрещена ({target})", "protected")
        if _root_file_target(variants, root, policy):
            return Decision("DENY", "deny", f"файлы запуска в корне проекта защищены ({target})", "protected")
        if any(_glob_hit(v, pat, root) for v in variants for pat in ask_paths):
            level, kind, reason = "EXTERNAL", "self_modify", _self_modify_reason(target, tool_input)
        elif all(_inside(v, root) for v in variants) or any(
                _glob_hit(v, p, root) for v in variants for p in policy.get("allow_write_paths") or []):
            level, kind, reason = "WRITE", "write", "запись внутри JARVIS"
        else:
            level, kind, reason = "EXTERNAL", "write_outside_root", f"запись вне папки JARVIS: {target}"
    elif shell:
        command = str(tool_input.get("command") or "")
        runs = _script_runs(command, policy, root)
        checked = _without_trusted_runs(command, runs)
        if _text_mentions(checked, protected, root) \
                and (_WRITE_VERBS.search(checked) or _INTERPRETERS.search(checked)):
            return Decision("DENY", "deny", "команда меняет защищённые файлы", "protected")
        if _WRITE_VERBS.search(checked) and _shell_root_file(checked, root, policy):
            return Decision("DENY", "deny", "команда создаёт или меняет файл запуска в корне проекта", "protected")
        level, kind, reason = "WRITE", "shell", "команда"
        changes_files = _WRITE_VERBS.search(checked) or _INTERPRETERS.search(checked)
        short = " ".join(command.split())
        short = short if len(short) <= _PREVIEW_LIMIT else short[:_PREVIEW_LIMIT] + "…"
        if changes_files and _text_mentions(checked, ask_paths, root):
            level, kind, reason = "EXTERNAL", "self_modify", f"правка собственных правил JARVIS командой: {short}"
        elif any(not ok for _, ok in runs):
            level, kind, reason = "EXTERNAL", "run_script", f"запуск кода вне доверенных мест: {short}"
        elif _WRITE_VERBS.search(command):
            outside = _outside_targets(command, root, base, policy.get("allow_write_paths") or [])
            if outside:
                level, kind, reason = "EXTERNAL", "write_outside_root", f"запись вне папки JARVIS: {outside[0]}"
        if kind == "shell":
            big = _big_shell_read(command, policy, base)
            if big:
                level, kind, reason = "EXTERNAL", "big_read", big
    elif tool.startswith("mcp__"):
        if any(_tool_matches(t, tool) for t in policy.get("read_tools") or []):
            level, kind, reason = "READ", "", "чтение"
        else:
            level, kind, reason = "EXTERNAL", "unknown_tool", f"хочу использовать незнакомый инструмент «{tool}»"
    elif not any(_tool_matches(t, tool) for t in policy.get("read_tools") or []):
        level, kind, reason = "EXTERNAL", "unknown_tool", f"хочу использовать незнакомый инструмент «{tool}»"

    # 2б. чтение большого файла целиком — тем же путём, что EXTERNAL
    if level == "READ":
        big = _big_read(tool, tool_input, policy, base)
        if big:
            level, kind, reason = "EXTERNAL", "big_read", big
    # 2в. данные в адресе «чтения» страницы — тоже кнопкой (аудит: риск выноса через WebFetch)
    if level == "READ":
        problem = _url_data(tool, tool_input, policy)
        if problem:
            level, kind, reason = problem
    elif shell and kind == "shell":
        problem = _shell_url_data(str(tool_input.get("command") or ""), policy)
        if problem:
            level, kind, reason = problem

    # 3. правила: побеждает самый строгий уровень; правило уточняет вид при равном уровне умолчания
    from_rule = False
    for rule in policy.get("rules") or []:
        if not _tool_matches(rule.get("tool", "*"), tool):
            continue
        texts = [blob]
        if shell:  # правила по самой командной строке: сырой и без кавычек
            raw = str(tool_input.get("command") or "")
            texts = [raw, _dequote(raw)]
        if not any(re.search(rule.get("match", "."), t, re.IGNORECASE) for t in texts):
            continue
        r_level = rule.get("level", "EXTERNAL")
        if r_level not in LEVELS:
            raise ValueError(f"policy.yaml: неизвестный уровень {r_level}")
        diff = LEVELS.index(r_level) - LEVELS.index(level)
        if diff > 0 or (diff == 0 and not from_rule):
            level, kind, reason = r_level, rule.get("kind", ""), rule.get("reason") or r_level
            from_rule = True
        if r_level == "DENY":
            break

    return _finish(level, kind, reason, policy, tool_input, env)


# ---------- Approvals API ----------

def ask_approval(decision: Decision, event: dict, root, timeout: float,
                 task_id: str | None = None) -> tuple[bool, str]:
    import urllib.request

    root = Path(root)
    try:
        port = int((root / "state" / "approvals.port").read_text(encoding="utf-8").strip())
        token = (root / "state" / "secrets" / "approvals.token").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False, "Approvals API недоступен (нет порта или токена)"
    tool = event.get("tool_name", "")
    body = json.dumps({
        "level": "MONEY" if decision.level == "MONEY" else "EXTERNAL",
        "tool": tool,
        "summary": f"{decision.reason}: {tool}",
        "details": {"kind": decision.kind, "tool_input": event.get("tool_input") or {}},
        "task_id": task_id,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/approve", data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "X-Jarvis-Token": token})
    import threading

    box: dict = {}

    def call():
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                box["data"] = json.loads(resp.read().decode("utf-8"))
        except BaseException as exc:  # таймаут, отказ соединения, 401, мусор — всё отказ
            box["error"] = exc

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(timeout)  # общий срок на весь ответ, а не на одну операцию сокета
    if worker.is_alive():
        return False, "Approvals API: нет решения за отведённое время"
    if "data" not in box:
        return False, f"Approvals API: нет решения ({type(box.get('error')).__name__})"
    data = box["data"]
    if isinstance(data, dict) and data.get("decision") == "allow":
        return True, str(data.get("reason") or "подтверждено")
    return False, str((data or {}).get("reason") or "отклонено владелицей")


def _masked(reason: str, root) -> str:
    """Причина для журнала без значений секретов. Нет `runtime.redact` — причину не пишем вовсе.

    Импорт ленивый и вне пути решения: его сбой не должен менять решение Guard.
    """
    try:
        root_str = str(Path(root))
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        from runtime.redact import redact
        return redact(reason)
    except Exception:
        return "причина скрыта: нет runtime/redact.py для маскировки"


def _log_blocked(root, event: dict, reason: str, task_id: str | None = None,
                 mode: str = "jarvis", runtime: str = "claude") -> None:
    try:
        path = Path(root) / "state" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        agent = event.get("agent_type") if isinstance(event.get("agent_type"), str) else "jarvis"
        line = {"ts": datetime.now(timezone.utc).isoformat(), "type": "blocked",
                "session": event.get("session_id"), "agent": agent, "task": "",
                "status": "working", "progress": None, "task_id": task_id,
                "tool": event.get("tool_name"), "reason": _masked(reason, root), "mode": mode,
                "runtime": runtime}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _dev_policy(policy: dict) -> dict:
    """Политика для режима dev: без защищённых путей и правки собственных правил —
    разработчик правит код JARVIS; секреты и правила-запреты остаются."""
    # Правила «на любой инструмент» здесь смотрят только на то, что исполняется (shell, MCP):
    # текст документа или теста, где упомянута опасная команда, — не её запуск.
    executing = "|".join([*(policy.get("shell_tools") or []), "mcp__.*"])
    rules = [{**r, "tool": executing} if r.get("tool", "*") in ("*", None, "") else r
             for r in policy.get("rules") or []]
    return {**policy, "protected_write_paths": [], "ask_write_paths": [], "rules": rules}


def run(event: dict, root=ROOT, policy_path=DEFAULT_POLICY, env=None, mode: str = "jarvis",
        runtime: str = "claude") -> tuple[int, str]:
    env = os.environ if env is None else env
    task_id = (env or {}).get("JARVIS_TASK_ID")  # ставит мост — связывает запись с задачей
    try:
        if mode not in MODES:
            raise ValueError(f"неизвестный режим Guard: {mode!r}")
        policy = load_policy(policy_path)
        if mode == "dev":
            decision = decide(event, policy=_dev_policy(policy), root=root, env=env)
            deny_kinds = set((policy.get("dev_mode") or {}).get("deny_kinds") or [])
            if decision.action == "deny" and decision.kind in deny_kinds:
                reason = f"JARVIS Guard: отказ — {decision.reason}"
                _log_blocked(root, event if isinstance(event, dict) else {}, reason, task_id, mode, runtime)
                return 2, reason
            return 0, ""
        decision = decide(event, policy=policy, root=root, env=env)
        if decision.action == "allow":
            return 0, ""
        if decision.action == "ask":
            ok, why = ask_approval(decision, event, root, float(policy.get("approval_timeout_sec") or 600),
                                   task_id)
            if ok:
                return 0, ""
            reason = f"JARVIS Guard: {decision.reason} — {why}"
        else:
            reason = f"JARVIS Guard: отказ — {decision.reason}"
    except Exception as exc:
        reason = f"JARVIS Guard: внутренняя ошибка, отказ ({type(exc).__name__})"
    _log_blocked(root, event if isinstance(event, dict) else {}, reason, task_id, runtime=runtime)
    return 2, reason


# ---------- Codex ----------

CANARY = "JARVIS_HOOK_CANARY"
_PATCH_LINE = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$", re.MULTILINE)


def codex_events(event: dict) -> list[dict]:
    """Вход хука Codex → события Guard. apply_patch без единого файла → Write без пути (отказ)."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    base = {k: event.get(k) for k in ("hook_event_name", "session_id", "cwd") if event.get(k) is not None}
    if tool == "apply_patch":
        text = str(tool_input.get("command") or tool_input.get("patch") or "")
        out = []
        for action, path in _PATCH_LINE.findall(text):
            if action == "Delete File":
                out.append({**base, "tool_name": "Bash", "tool_input": {"command": f"rm {path}"}})
            else:
                name = "Edit" if action == "Update File" else "Write"
                out.append({**base, "tool_name": name,
                            "tool_input": {"file_path": path, "content": text[:4000]}})
        return out or [{**base, "tool_name": "Write", "tool_input": {"file_path": "", "content": text[:4000]}}]
    if tool == "Bash" and isinstance(tool_input.get("command"), list):
        return [{**event, "tool_input": {**tool_input, "command": " ".join(map(str, tool_input["command"]))}}]
    return [event]


def _canary(event: dict, root, env) -> str | None:
    command = str((event.get("tool_input") or {}).get("command") or "") if isinstance(event.get("tool_input"), dict) else ""
    if event.get("tool_name") != "Bash" or CANARY not in command:
        return None
    try:
        mark = Path(root) / "state" / "codex_canary.json"
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                    "task_id": (env or {}).get("JARVIS_TASK_ID")}), encoding="utf-8")
    except OSError:
        pass
    return "JARVIS Guard: canary — проверка, что хук Codex жив и ему доверяют"


def codex_decision(event: dict, root=ROOT, policy_path=DEFAULT_POLICY, env=None,
                   mode: str | None = None) -> str | None:
    """Причина запрета для Codex или None (разрешено). Никогда не бросает исключений."""
    env = os.environ if env is None else env
    try:
        canary = _canary(event, root, env)
        if canary:
            return canary
        mode = mode or ("jarvis" if (env or {}).get("JARVIS_TASK_ID") else "dev")
        for item in codex_events(event):
            code, reason = run(item, root=root, policy_path=policy_path, env=env, mode=mode, runtime="codex")
            if code != 0:
                return reason
        return None
    except Exception as exc:  # noqa: BLE001 — для Codex сбой хука обязан быть запретом
        return f"JARVIS Guard: внутренняя ошибка, отказ ({type(exc).__name__})"


def codex_deny_json(reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": reason}}, ensure_ascii=False)


def _parse_argv(argv: list[str]) -> tuple[str | None, str]:
    """(`--mode`, `--runtime`) в любом порядке. Другие аргументы — ошибка, то есть отказ."""
    mode, runtime, rest = None, "claude", list(argv)
    while rest:
        if len(rest) >= 2 and rest[0] == "--mode":
            mode, rest = rest[1], rest[2:]
        elif len(rest) >= 2 and rest[0] == "--runtime" and rest[1] in ("claude", "codex"):
            runtime, rest = rest[1], rest[2:]
        else:
            raise ValueError("неизвестные аргументы Guard")
    return mode, runtime


def _mode_from_argv(argv: list[str]) -> str:
    """`--mode <режим>` или ничего (режим бота). Любые другие аргументы — ошибка, то есть отказ."""
    mode, _ = _parse_argv(argv)
    return mode or "jarvis"


def codex_main(mode: str | None) -> int:
    """Хук Codex: JSON-запрет в stdout или тишина; выход всегда 0 (код 2 Codex не слушает)."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
        reason = codex_decision(event, mode=mode)
    except Exception as exc:  # noqa: BLE001
        reason = f"JARVIS Guard: внутренняя ошибка, отказ ({type(exc).__name__})"
    if reason:
        sys.stdout.buffer.write((codex_deny_json(reason) + "\n").encode("utf-8"))
        sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        mode_arg, runtime = _parse_argv(args)
    except ValueError:
        if "--runtime" in args and "codex" in args:
            sys.stdout.buffer.write((codex_deny_json("JARVIS Guard: неизвестные аргументы, отказ") + "\n").encode("utf-8"))
            return 0
        sys.stderr.buffer.write("JARVIS Guard: неизвестные аргументы, отказ\n".encode("utf-8"))
        return 2
    if runtime == "codex":
        return codex_main(mode_arg)
    try:
        mode = mode_arg or "jarvis"
        raw = sys.stdin.buffer.read().decode("utf-8")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
        code, reason = run(event, mode=mode)
    except Exception as exc:
        code, reason = 2, f"JARVIS Guard: внутренняя ошибка, отказ ({type(exc).__name__})"
    if code != 0:
        sys.stderr.buffer.write((reason + "\n").encode("utf-8"))
        sys.stderr.flush()
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.exit(2)
