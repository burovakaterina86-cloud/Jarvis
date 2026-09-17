"""Браузер JARVIS: единственный источник истины о профиле.

Один и тот же профиль используют обе стороны:
- Playwright MCP (`.mcp.json`, сервер `playwright`) — работа агента;
- `integrations/browser/login.py` — ручной вход владелицы.

Путь в `.mcp.json` записан абсолютным, потому что рабочая папка процесса MCP
не гарантирована; тест `tests/test_skills_format.py` сверяет его с `profile_path()`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = Path("state/browser-profile")


def profile_path(root: Path | None = None) -> Path:
    """Абсолютный путь к профилю браузера JARVIS."""
    return (root or ROOT) / PROFILE_DIR


__all__ = ["ROOT", "PROFILE_DIR", "profile_path"]
