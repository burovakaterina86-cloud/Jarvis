"""Зеркала для Codex: `.claude/skills` → `.agents/skills`, `.claude/rules/*.md` → `.agents/rules/*.md`,
`.claude/agents/*.md` → `.codex/agents/*.toml`.

    python scripts/sync_mirrors.py --check [--root <папка>]   # только проверить
    python scripts/sync_mirrors.py --write [--root <папка>]   # пересобрать зеркала из .claude/

Источник истины — `.claude/`. Правило зеркала: пути в тексте переписываются на настоящие папки Codex
(`.claude/skills` → `.agents/skills`, `.claude/rules` → `.agents/rules`, `.claude/agents/<имя>.md` →
`.codex/agents/<имя>.toml`), `CLAUDE.md` → `AGENTS.md`; прочие `.claude/…` (хуки, настройки) остаются как есть —
такие файлы существуют. Раньше `.claude` заменялось на несуществующую `.Codex`: ссылки вели в никуда, а на
регистрозависимой файловой системе путь не нашёлся бы вовсе. Навык `autopilot` — дословная копия
(у него свои пути установки); концы строк не важны (git на Windows их меняет).
Владелица пользуется Codex (её решение 2026-10-05) — зеркала поддерживаются, а не снимаются.
Код выхода: 0 — зеркала совпадают (или пересобраны), 1 — есть расхождения, 2 — ошибка аргументов.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VERBATIM = {"autopilot"}
SKIP_PARTS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}


_REWRITES = ((b".claude/skills", b".agents/skills"), (b".claude/rules", b".agents/rules"),
             (b".claude/agents", b".codex/agents"), (b"CLAUDE.md", b"AGENTS.md"))
_AGENT_MD = re.compile(rb"(\.codex/agents/[\w\-<>]+)\.md")


def rewrite(data: bytes) -> bytes:
    """Пути `.claude/…` в тексте → настоящие папки зеркал Codex (см. модульную строку)."""
    for old, new in _REWRITES:
        data = data.replace(old, new)
    return _AGENT_MD.sub(rb"\1.toml", data)


def mirrored(skill: str, data: bytes) -> bytes:
    """Содержимое файла навыка в зеркале (байты, концы строк — LF)."""
    data = data.replace(b"\r\n", b"\n")
    return data if skill in VERBATIM else rewrite(data)


def _mirror_text(text: str) -> str:
    return rewrite(text.encode("utf-8")).decode("utf-8")


def _files(base: Path) -> dict[str, Path]:
    if not base.is_dir():
        return {}
    out = {}
    for item in base.rglob("*"):
        rel = item.relative_to(base)
        if item.is_file() and not SKIP_PARTS & set(rel.parts) and item.suffix not in SKIP_SUFFIXES:
            out[rel.as_posix()] = item
    return out


def _skill_of(rel: str) -> str:
    return rel.split("/", 1)[0]


def _skill_same(rel: str, src: Path, dst: Path) -> bool:
    return dst.is_file() and mirrored(_skill_of(rel), src.read_bytes()) == dst.read_bytes().replace(b"\r\n", b"\n")


def _compare_skills(root: Path) -> list[str]:
    src, dst = _files(root / ".claude" / "skills"), _files(root / ".agents" / "skills")
    report = []
    for rel in sorted(src.keys() | dst.keys()):
        shown = f".agents/skills/{rel}"
        if rel not in dst:
            report.append(f"нет копии: {shown}")
        elif rel not in src:
            report.append(f"лишнее в копии: {shown}")
        elif not _skill_same(rel, src[rel], dst[rel]):
            report.append(f"расходится: {shown}")
    return report


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _agent_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        meta = yaml.safe_load(head) or {}
    return meta, _norm(body)


def agent_toml(meta: dict, body: str) -> str:
    """Определение помощника для Codex: name, description, developer_instructions."""
    instructions = _mirror_text(body).replace("\\", "\\\\").replace('"""', '""\\"')
    return (f"name = {json.dumps(str(meta.get('name', '')), ensure_ascii=False)}\n"
            f"description = {json.dumps(str(meta.get('description', '')), ensure_ascii=False)}\n"
            f'developer_instructions = """\n{instructions}"""\n')


def _agent_same(src: Path, dst: Path) -> bool | None:
    """True — совпадает, False — расходится, None — копия не читается."""
    meta, body = _agent_md(src)
    try:
        toml = tomllib.loads(dst.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    return (toml.get("name") == meta.get("name") and toml.get("description") == meta.get("description")
            and _norm(str(toml.get("developer_instructions") or "")) == _mirror_text(body))


def _compare_agents(root: Path) -> list[str]:
    src = {p.stem: p for p in (root / ".claude" / "agents").glob("*.md")}
    dst = {p.stem: p for p in (root / ".codex" / "agents").glob("*.toml")}
    report = []
    for name in sorted(src.keys() | dst.keys()):
        shown = f".codex/agents/{name}.toml"
        if name not in dst:
            report.append(f"нет копии: {shown}")
        elif name not in src:
            report.append(f"лишнее в копии: {shown}")
        else:
            same = _agent_same(src[name], dst[name])
            if same is None:
                report.append(f"не читается: {shown}")
            elif not same:
                report.append(f"расходится: {shown}")
    return report


def _compare_rules(root: Path) -> list[str]:
    src, dst = _files(root / ".claude" / "rules"), _files(root / ".agents" / "rules")
    report = []
    for rel in sorted(src.keys() | dst.keys()):
        shown = f".agents/rules/{rel}"
        if rel not in dst:
            report.append(f"нет копии: {shown}")
        elif rel not in src:
            report.append(f"лишнее в копии: {shown}")
        elif mirrored("rules", src[rel].read_bytes()) != dst[rel].read_bytes().replace(b"\r\n", b"\n"):
            report.append(f"расходится: {shown}")
    return report


def compare(root: Path | str = ROOT) -> list[str]:
    root = Path(root)
    return _compare_skills(root) + _compare_rules(root) + _compare_agents(root)


def write(root: Path | str = ROOT) -> list[str]:
    """Пересобирает зеркала из .claude/. Возвращает список изменённых путей."""
    root = Path(root)
    changed = []
    src, dst_root = _files(root / ".claude" / "skills"), root / ".agents" / "skills"
    for rel, path in sorted(src.items()):
        target = dst_root / rel
        if not _skill_same(rel, path, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(mirrored(_skill_of(rel), path.read_bytes()))
            changed.append(f".agents/skills/{rel}")
    for rel in sorted(set(_files(dst_root)) - set(src)):
        (dst_root / rel).unlink()
        changed.append(f".agents/skills/{rel} (удалён: нет в .claude)")
    rules_src, rules_dst = _files(root / ".claude" / "rules"), root / ".agents" / "rules"
    for rel, path in sorted(rules_src.items()):
        target = rules_dst / rel
        body = mirrored("rules", path.read_bytes())
        if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != body:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            changed.append(f".agents/rules/{rel}")
    for rel in sorted(set(_files(rules_dst)) - set(rules_src)):
        (rules_dst / rel).unlink()
        changed.append(f".agents/rules/{rel} (удалён: нет в .claude)")
    agents_src = {p.stem: p for p in (root / ".claude" / "agents").glob("*.md")}
    agents_dst = root / ".codex" / "agents"
    for name, path in sorted(agents_src.items()):
        target = agents_dst / f"{name}.toml"
        if not target.is_file() or not _agent_same(path, target):
            agents_dst.mkdir(parents=True, exist_ok=True)
            target.write_text(agent_toml(*_agent_md(path)), encoding="utf-8")
            changed.append(f".codex/agents/{name}.toml")
    for path in sorted(agents_dst.glob("*.toml")):
        if path.stem not in agents_src:
            path.unlink()
            changed.append(f".codex/agents/{path.name} (удалён: нет в .claude)")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Зеркала .agents/ и .codex/ относительно .claude/")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="только проверить")
    mode.add_argument("--write", action="store_true", help="пересобрать зеркала из .claude/")
    parser.add_argument("--root", default=str(ROOT))
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.write:
        changed = write(args.root)
        print(f"пересобрано: {len(changed)}" if changed else "зеркала уже совпадали")
        for line in changed:
            print("  " + line)
        return 0 if not compare(args.root) else 1
    report = compare(args.root)
    if not report:
        print("зеркала совпадают с .claude/")
        return 0
    print(f"расхождений: {len(report)} (источник истины — .claude/; исправить: --write)")
    for line in report:
        print("  " + line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
