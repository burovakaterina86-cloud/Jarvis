"""Guard — PreToolUse-хук JARVIS.

Вход: JSON PreToolUse на stdin. Выход: exit 0 (пропустить) или exit 2 + причина в stderr (отказ).
Правила — runtime/policy.yaml. Любая ошибка внутри хука — отказ (fail-closed).

Публичное:
    load_policy(path) -> dict
    decide(event, policy, root, env) -> Decision(level, action, reason, kind)   # чистая функция
    run(event, root, policy_path, env) -> (exit_code, reason)                   # с запросом к Approvals API
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


def _abs(path: str, base: Path) -> str:
    p = os.path.expanduser(str(path))
    if not os.path.isabs(p):
        p = os.path.join(str(base), p)
    return _norm(os.path.normpath(p))


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
    absolute = _abs(value, base)
    for pat in patterns or []:
        if _glob_hit(absolute, pat, root):
            return pat
    return _text_mentions(value, patterns, root)


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
    r"|\bsed\s+-i|\bgit\s+(checkout|restore|apply|am|reset|stash|mv|clone)\b", re.IGNORECASE)
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

    Граница: заслон стоит на инструментах чтения. `Bash: cat <большой файл>` он не ловит —
    размер в произвольной командной строке надёжно не определить; shell идёт своим путём
    (WRITE-команда). Заслон не полный, и это сознательное решение, а не пробел.
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

    # 2. запись в защищённые места
    write_tools = policy.get("write_tools") or {}
    shell = tool in (policy.get("shell_tools") or [])
    level, kind, reason = "READ", "", "чтение"
    if tool in write_tools:
        target = tool_input.get(write_tools[tool])
        if not isinstance(target, str) or not target:
            return Decision("DENY", "deny", "нет пути записи", "malformed")
        absolute = _abs(target, base)
        for pat in protected:
            if _glob_hit(absolute, pat, root):
                return Decision("DENY", "deny", f"запись в защищённое место запрещена ({target})", "protected")
        if any(_glob_hit(absolute, pat, root) for pat in ask_paths):
            level, kind, reason = "EXTERNAL", "self_modify", _self_modify_reason(target, tool_input)
        elif _inside(absolute, root) or any(_glob_hit(absolute, p, root) for p in policy.get("allow_write_paths") or []):
            level, kind, reason = "WRITE", "write", "запись внутри JARVIS"
        else:
            level, kind, reason = "EXTERNAL", "write_outside_root", f"запись вне папки JARVIS: {target}"
    elif shell:
        command = str(tool_input.get("command") or "")
        if (_text_mentions(command, protected, root) or _text_mentions(_dequote(command), protected, root)) \
                and (_WRITE_VERBS.search(command) or _INTERPRETERS.search(command)):
            return Decision("DENY", "deny", "команда меняет защищённые файлы", "protected")
        level, kind, reason = "WRITE", "shell", "команда"
        changes_files = _WRITE_VERBS.search(command) or _INTERPRETERS.search(command)
        if changes_files and (_text_mentions(command, ask_paths, root)
                              or _text_mentions(_dequote(command), ask_paths, root)):
            short = " ".join(command.split())
            short = short if len(short) <= _PREVIEW_LIMIT else short[:_PREVIEW_LIMIT] + "…"
            level, kind, reason = "EXTERNAL", "self_modify", f"правка собственных правил JARVIS командой: {short}"
        elif _WRITE_VERBS.search(command):
            outside = _outside_targets(command, root, base, policy.get("allow_write_paths") or [])
            if outside:
                level, kind, reason = "EXTERNAL", "write_outside_root", f"запись вне папки JARVIS: {outside[0]}"
    elif tool.startswith("mcp__"):
        if any(_tool_matches(t, tool) for t in policy.get("read_tools") or []):
            level, kind, reason = "READ", "", "чтение"
        else:
            level, kind, reason = "EXTERNAL", "unknown_tool", f"неизвестный инструмент {tool}"
    elif not any(_tool_matches(t, tool) for t in policy.get("read_tools") or []):
        level, kind, reason = "EXTERNAL", "unknown_tool", f"неизвестный инструмент {tool}"

    # 2б. чтение большого файла целиком — тем же путём, что EXTERNAL
    if level == "READ":
        big = _big_read(tool, tool_input, policy, base)
        if big:
            level, kind, reason = "EXTERNAL", "big_read", big

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

def ask_approval(decision: Decision, event: dict, root, timeout: float) -> tuple[bool, str]:
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


def _log_blocked(root, event: dict, reason: str) -> None:
    try:
        path = Path(root) / "state" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(timezone.utc).isoformat(), "type": "blocked",
                "session": event.get("session_id"), "agent": "jarvis", "task": "",
                "status": "working", "progress": None,
                "tool": event.get("tool_name"), "reason": reason}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def run(event: dict, root=ROOT, policy_path=DEFAULT_POLICY, env=None) -> tuple[int, str]:
    env = os.environ if env is None else env
    try:
        policy = load_policy(policy_path)
        decision = decide(event, policy=policy, root=root, env=env)
        if decision.action == "allow":
            return 0, ""
        if decision.action == "ask":
            ok, why = ask_approval(decision, event, root, float(policy.get("approval_timeout_sec") or 600))
            if ok:
                return 0, ""
            reason = f"JARVIS Guard: {decision.reason} — {why}"
        else:
            reason = f"JARVIS Guard: отказ — {decision.reason}"
    except Exception as exc:
        reason = f"JARVIS Guard: внутренняя ошибка, отказ ({type(exc).__name__})"
    _log_blocked(root, event if isinstance(event, dict) else {}, reason)
    return 2, reason


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
        code, reason = run(event)
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
