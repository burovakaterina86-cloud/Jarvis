"""Один сканер кода для всех тестов: что считаем кодом, что пропускаем и что ищем.

Раньше запрет на обход прав проверяли два теста своими списками исключений — списки
разъезжались, и дыра могла пролезть в щель между ними. Теперь список один, здесь.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CODE_SUFFIXES = {".py", ".json", ".bat", ".cmd", ".ps1", ".sh", ".yaml", ".yml",
                 ".toml", ".ini", ".js", ".ts", ".txt"}

# Пропускаем:
#   tests/ и docs/ — сами называют запрещённые флаги, чтобы проверять и описывать их отсутствие;
#   .autopilot/ — инструменты сборки (спека, тикеты, панель прогресса), а не продукт;
#   state/, inbox/ — рабочие данные; остальное — чужой или сгенерированный код.
SKIP_DIRS = {".git", ".venv", ".autopilot", "__pycache__", ".pytest_cache", "node_modules",
             "state", "inbox", ".codex", ".agents", "tests", "docs"}

BYPASS_NEEDLES = ("dangerously" + "-skip-permissions", "bypass" + "Permissions")


def code_files(suffixes=None, root: Path = ROOT) -> list[Path]:
    wanted = CODE_SUFFIXES if suffixes is None else set(suffixes)
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in wanted:
            continue
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        found.append(path)
    return found


def bypass_hits(root: Path = ROOT) -> list[str]:
    """Файлы кода, где встречается флаг полного обхода прав. Пусто — так и должно быть."""
    hits = []
    for path in code_files(root=root):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [f"{path.relative_to(root)}: {n}" for n in BYPASS_NEEDLES if n in text]
    return hits
