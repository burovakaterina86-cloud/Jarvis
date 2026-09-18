"""Активация черновиков: `drafts/` → `.claude/skills|agents`.

Агент пишет только в `drafts/` — запись в `.claude/skills/**` и `.claude/agents/**`
запрещена Guard'ом (`runtime/policy.yaml`). Перенести черновик в рабочую папку может
только этот модуль, и вызывает его Telegram-слой по кнопке владелицы. Так новый навык
или помощник не включается сам по себе.

Публично: `list_drafts(root)`, `validate(kind, name, root)`, `activate(kind, name, root)`,
`discard(kind, name, root)`, `ensure_dirs(root)`.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

DRAFTS = "drafts"
NAME_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
NAME_LIMIT = 64            # имя навыка — имя папки; длинные ломают пути на Windows
DESC_LIMIT = 1536          # description + when_to_use, лимит Claude Code
BODY_LINES_LIMIT = 500
# Строка результата прогона в TEST.md — строгий формат, а не «где-то встретилось слово».
RESULT_RE = re.compile(r"^Результат:[ \t]*(passed|failed)[ \t]*$", re.MULTILINE)

KINDS = {
    "skill": {"folder": "skills", "file": "SKILL.md", "word": "навык"},
    "agent": {"folder": "agents", "file": None, "word": "помощник"},
}


class ActivationError(RuntimeError):
    """Черновик не прошёл проверку или мешает уже существующий файл."""


@dataclass
class Draft:
    kind: str
    name: str
    path: Path                 # папка навыка или файл агента
    description: str = ""
    when_to_use: str = ""
    test_status: str = "none"  # passed | failed | none
    problems: list[str] = field(default_factory=list)

    @property
    def word(self) -> str:
        return KINDS[self.kind]["word"]

    @property
    def doc(self) -> Path:
        """Файл с frontmatter: SKILL.md навыка или сам файл агента."""
        return self.path / "SKILL.md" if self.kind == "skill" else self.path


# ---------------------------------------------------------------- пути

def draft_path(kind: str, name: str, root: Path | str = ROOT) -> Path:
    root = Path(root)
    if kind == "skill":
        return root / DRAFTS / "skills" / name
    return root / DRAFTS / "agents" / f"{name}.md"


def live_path(kind: str, name: str, root: Path | str = ROOT) -> Path:
    root = Path(root)
    if kind == "skill":
        return root / ".claude" / "skills" / name
    return root / ".claude" / "agents" / f"{name}.md"


def ensure_dirs(root: Path | str = ROOT) -> None:
    """Папки должны существовать заранее: первый файл в новой `.claude/agents/`
    требует перезапуска Claude Code, а черновики некуда класть до первой активации."""
    root = Path(root)
    for rel in (".claude/agents", ".claude/skills", f"{DRAFTS}/skills", f"{DRAFTS}/agents"):
        (root / rel).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- чтение

def _frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---\n"):
        return None, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, text
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, parts[2]
    return (meta if isinstance(meta, dict) else None), parts[2]


def _test_status(folder: Path) -> str:
    test_md = folder / "TEST.md"
    if not test_md.is_file():
        return "none"
    try:
        text = test_md.read_text(encoding="utf-8")
    except OSError:
        return "none"
    found = RESULT_RE.findall(text)
    return found[-1] if found else "none"


def _read_draft(kind: str, name: str, root: Path) -> Draft:
    path = draft_path(kind, name, root)
    draft = Draft(kind=kind, name=name, path=path)
    doc = draft.doc
    if doc.is_file():
        meta, _body = _frontmatter(doc.read_text(encoding="utf-8", errors="replace"))
        if meta:
            draft.description = str(meta.get("description") or "").strip()
            draft.when_to_use = str(meta.get("when_to_use") or "").strip()
    draft.test_status = _test_status(path if kind == "skill" else path.parent / name)
    return draft


def list_drafts(root: Path | str = ROOT) -> list[Draft]:
    """Все черновики на диске, с описанием, результатом теста и замечаниями проверки."""
    root = Path(root)
    out: list[Draft] = []
    skills_dir = root / DRAFTS / "skills"
    if skills_dir.is_dir():
        for folder in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            out.append(_describe("skill", folder.name, root))
    agents_dir = root / DRAFTS / "agents"
    if agents_dir.is_dir():
        for path in sorted(p for p in agents_dir.glob("*.md") if p.is_file()):
            out.append(_describe("agent", path.stem, root))
    return out


def _describe(kind: str, name: str, root: Path) -> Draft:
    draft = _read_draft(kind, name, root)
    draft.problems = validate(kind, name, root)
    return draft


# ---------------------------------------------------------------- проверка

def validate(kind: str, name: str, root: Path | str = ROOT) -> list[str]:
    """Список замечаний; пустой список — черновик можно включать."""
    root = Path(root)
    if kind not in KINDS:
        return [f"неизвестный вид черновика: {kind}"]
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        return [f"плохое имя «{name}»: допустимы только строчные латинские буквы, "
                f"цифры и дефис ([a-z0-9-])"]
    if len(name) > NAME_LIMIT:
        return [f"плохое имя: длиннее {NAME_LIMIT} символов"]

    path = draft_path(kind, name, root)
    problems: list[str] = []
    clash = _live_clash(kind, name, root)
    if clash:
        problems.append(f"{KINDS[kind]['word']} уже есть: {clash} — сначала удали старый "
                        f"(на Windows имена, различающиеся регистром, — один и тот же путь)")
    if kind == "skill":
        if not path.is_dir():
            return [f"нет черновика drafts/skills/{name}/"]
        doc = path / "SKILL.md"
        if not doc.is_file():
            return [f"нет черновика: в drafts/skills/{name}/ отсутствует SKILL.md"]
        files = [path, *path.rglob("*")]
    else:
        if not path.is_file():
            return [f"нет черновика drafts/agents/{name}.md"]
        doc = path
        files = [path]

    problems += _check_tree(files, path if kind == "skill" else path.parent, root)

    meta, body = _frontmatter(doc.read_text(encoding="utf-8", errors="replace"))
    if meta is None:
        problems.append("нет frontmatter: файл должен начинаться с блока --- … ---")
        return problems
    if str(meta.get("name") or "").strip() != name:
        problems.append(f"в frontmatter name={meta.get('name')!r}, а черновик называется {name!r}")
    description = str(meta.get("description") or "").strip()
    when = str(meta.get("when_to_use") or "").strip()
    if not description:
        problems.append("пустое description")
    if kind == "skill" and not when:
        problems.append("пустое when_to_use")
    if len(description) + len(when) > DESC_LIMIT:
        problems.append(f"description + when_to_use длиннее {DESC_LIMIT} символов "
                        f"({len(description) + len(when)})")
    if kind == "skill" and len(body.splitlines()) > BODY_LINES_LIMIT:
        problems.append(f"тело SKILL.md длиннее {BODY_LINES_LIMIT} строк")
    return problems


def _live_clash(kind: str, name: str, root: Path) -> str | None:
    """Имя уже занято в рабочей папке — в том числе если различие только в регистре."""
    parent = live_path(kind, name, root).parent
    if not parent.is_dir():
        return None
    wanted = (name if kind == "skill" else f"{name}.md").lower()
    for item in parent.iterdir():
        if item.name.lower() == wanted:
            return str(item.relative_to(root)).replace("\\", "/")
    return None


def _check_tree(files, base: Path, root: Path) -> list[str]:
    """Проверяем сами пути файлов: символические ссылки и выход за папку черновика.

    Текст черновика не сканируем: упоминание относительного пути в документации навыка —
    это документация, а не побег из песочницы.
    """
    problems: list[str] = []
    base_resolved = base.resolve()
    for item in files:
        if item.is_symlink():
            problems.append(f"символическая ссылка в черновике: {item.name}")
            continue
        try:
            item.resolve().relative_to(base_resolved)
        except (ValueError, OSError):
            problems.append(f"путь наружу черновика: {item.name}")
    return sorted(set(problems))


# ---------------------------------------------------------------- перенос

def activate(kind: str, name: str, root: Path | str = ROOT) -> Path:
    """Переносит проверенный черновик в рабочую папку. Возвращает путь к файлу навыка/агента."""
    root = Path(root)
    problems = validate(kind, name, root)
    if problems:
        raise ActivationError("; ".join(problems))
    target = live_path(kind, name, root)
    if target.exists():
        raise ActivationError(f"{KINDS[kind]['word']} {name} уже есть — сначала удали старый")
    ensure_dirs(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = draft_path(kind, name, root)
    # Перенос в два шага: сначала во временное имя рядом с целью (тот же диск), потом
    # атомарное переименование. Сбой на любом шаге не оставит полпапки в .claude/.
    staging = target.parent / f".{name}.activating"
    _remove(staging)
    try:
        shutil.move(str(source), str(staging))
    except OSError as exc:
        _remove(staging)
        raise ActivationError(f"не смог перенести черновик: {type(exc).__name__}") from exc
    try:
        os.replace(staging, target)
    except OSError as exc:
        try:                        # откат: черновик возвращается на место целиком
            shutil.move(str(staging), str(source))
        except OSError:
            log_path = staging
            raise ActivationError(
                f"перенос не удался, черновик остался в {log_path}") from exc
        finally:
            _remove(target)
        raise ActivationError(f"не смог включить {name}: {type(exc).__name__}") from exc
    return target / "SKILL.md" if kind == "skill" else target


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def discard(kind: str, name: str, root: Path | str = ROOT) -> bool:
    """Удаляет черновик. True — удалил, False — его уже не было."""
    root = Path(root)
    if kind not in KINDS or not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ActivationError(f"плохое имя черновика: {name!r}")
    path = draft_path(kind, name, root)
    if path.is_dir():
        shutil.rmtree(path)
        return True
    if path.is_file():
        path.unlink()
        return True
    return False
