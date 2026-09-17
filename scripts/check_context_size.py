"""Проверка бюджета контекста, который JARVIS грузит каждым ходом.

Запуск: .venv\\Scripts\\python.exe scripts\\check_context_size.py [корень]
Печатает размеры; exit 1, если превышен любой бюджет. 1 KB = 1024 байта (UTF-8 на диске).
Файлы .claude/rules/*.md Claude Code тоже грузит каждым ходом — они печатаются
и входят в строку «всего каждым ходом» (информационно).
"""
import sys
from pathlib import Path

KB = 1024
BUDGETS = {"CLAUDE.md": 5 * KB, "SOUL.md": 2 * KB, "GOALS.md": 2 * KB, "MEMORY.md": 5 * KB}
CORE_TOTAL = 12 * KB


def check(root):
    root = Path(root)
    ok = True
    total = 0
    for name, limit in BUDGETS.items():
        path = root / name
        size = path.stat().st_size if path.is_file() else 0
        total += size
        bad = size > limit or not path.is_file()
        ok = ok and not bad
        mark = "ПРЕВЫШЕН" if size > limit else ("НЕТ ФАЙЛА" if not path.is_file() else "ok")
        print(f"{name:<12} {size / KB:5.2f} KB / {limit / KB:.0f} KB  {mark}")
    core_bad = total > CORE_TOTAL
    ok = ok and not core_bad
    print(f"{'сумма':<12} {total / KB:5.2f} KB / {CORE_TOTAL / KB:.0f} KB  {'ПРЕВЫШЕН' if core_bad else 'ok'}")
    rules = sorted((root / ".claude" / "rules").glob("*.md"))
    rules_size = sum(p.stat().st_size for p in rules)
    print(f"{'rules/*.md':<12} {rules_size / KB:5.2f} KB  ({len(rules)} файлов)")
    print(f"{'всего каждым ходом':<12} {(total + rules_size) / KB:5.2f} KB")
    return ok


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    return 0 if check(root) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
