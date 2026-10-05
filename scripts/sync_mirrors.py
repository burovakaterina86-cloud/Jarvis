"""Проверка зеркал для других CLI: `.claude/skills` ↔ `.agents/skills`, `.claude/agents` ↔ `.codex/agents`.

    python scripts/sync_mirrors.py --check [--root <папка>]

Источник истины — `.claude/`. Скрипт только сообщает о расхождениях и ничего не копирует:
чинить ли зеркала (или снять их как неподдерживаемые) — решение владелицы (аудит 2026-10-05, P1.5/P4.2).
Код выхода: 0 — зеркала совпадают, 1 — есть расхождения, 2 — ошибка аргументов.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}


def _files(base: Path) -> dict[str, Path]:
    if not base.is_dir():
        return {}
    out = {}
    for item in base.rglob("*"):
        rel = item.relative_to(base)
        if item.is_file() and not SKIP_PARTS & set(rel.parts) and item.suffix not in SKIP_SUFFIXES:
            out[rel.as_posix()] = item
    return out


TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".html", ".css", ".js", ".ps1"}


def _content(path: Path) -> bytes:
    """Байты файла; у текстовых — без разницы CRLF/LF (git на Windows меняет концы строк)."""
    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n") if path.suffix.lower() in TEXT_SUFFIXES else data


def _compare_skills(root: Path) -> list[str]:
    src, dst = _files(root / ".claude" / "skills"), _files(root / ".agents" / "skills")
    report = []
    for rel in sorted(src.keys() | dst.keys()):
        shown = f".agents/skills/{rel}"
        if rel not in dst:
            report.append(f"нет копии: {shown}")
        elif rel not in src:
            report.append(f"лишнее в копии: {shown}")
        elif _content(src[rel]) != _content(dst[rel]):
            report.append(f"расходится: {shown}")
    return report


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _agent_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
    return meta, _norm(body)


def _compare_agents(root: Path) -> list[str]:
    src = {p.stem: p for p in (root / ".claude" / "agents").glob("*.md")}
    dst = {p.stem: p for p in (root / ".codex" / "agents").glob("*.toml")}
    report = []
    for name in sorted(src.keys() | dst.keys()):
        shown = f".codex/agents/{name}.toml"
        if name not in dst:
            report.append(f"нет копии: {shown}")
            continue
        if name not in src:
            report.append(f"лишнее в копии: {shown}")
            continue
        meta, body = _agent_md(src[name])
        try:
            toml = tomllib.loads(dst[name].read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            report.append(f"не читается: {shown}")
            continue
        same = (toml.get("name") == meta.get("name") and toml.get("description") == meta.get("description")
                and _norm(str(toml.get("developer_instructions") or "")) == body)
        if not same:
            report.append(f"расходится: {shown}")
    return report


def compare(root: Path | str = ROOT) -> list[str]:
    root = Path(root)
    return _compare_skills(root) + _compare_agents(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка зеркал .agents/ и .codex/ относительно .claude/")
    parser.add_argument("--check", action="store_true", required=True, help="только проверить")
    parser.add_argument("--root", default=str(ROOT))
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    report = compare(args.root)
    if not report:
        print("зеркала совпадают с .claude/")
        return 0
    print(f"расхождений: {len(report)} (источник истины — .claude/)")
    for line in report:
        print("  " + line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
