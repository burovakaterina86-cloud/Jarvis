"""Второй аккаунт Claude: запасной исполнитель на случай, когда на первом кончился лимит подписки.

Тот же `claude -p`, но вход берётся из отдельной папки (`CLAUDE_CONFIG_DIR`), поэтому бот может работать под вторым
аккаунтом, пока компьютер и Claude Desktop остаются на первом. Папка задаётся в `.env`:

    JARVIS_CLAUDE2_DIR=C:\\Users\\<имя>\\.claude-jarvis2

Один раз войти вторым аккаунтом (это делает владелица сама, пароль боту не нужен):

    $env:CLAUDE_CONFIG_DIR = "C:\\Users\\<имя>\\.claude-jarvis2"; claude      # затем /login

Переключение выбирает владелица: первый Claude → кнопка Codex → при его лимите кнопка второго Claude.
Команда /claude2 выбирает второй аккаунт вручную. Без настройки используется отдельный профиль
state/secrets/claude2; явный JARVIS_CLAUDE2_DIR имеет приоритет.
"""
from __future__ import annotations

import os
from pathlib import Path

from runtime import claude_bridge
from runtime.claude_bridge import TurnResult

LIMITS_KEY = "claude2"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "state" / "secrets" / "claude2"


def config_dir(env: dict | None = None) -> Path | None:
    """Папка входа второго аккаунта, если она задана и существует."""
    value = str((os.environ if env is None else env).get("JARVIS_CLAUDE2_DIR") or "").strip()
    path = Path(value) if value else DEFAULT_CONFIG_DIR
    return path if path is not None and path.is_dir() else None


def available(env: dict | None = None) -> bool:
    return config_dir(env) is not None


def auth_text(folder: Path | None) -> str:
    where = str(folder) if folder else "<папка из JARVIS_CLAUDE2_DIR>"
    return ("Второй аккаунт Claude ещё не вошёл. На компьютере открой терминал и набери: "
            f'$env:CLAUDE_CONFIG_DIR = "{where}"; claude — потом /login со вторым аккаунтом.')


async def run_turn(prompt: str, session_id: str | None = None, on_event=None, *, env: dict | None = None,
                   **kwargs) -> TurnResult:
    """Один ход под вторым аккаунтом. Никогда не бросает исключений — ошибка в TurnResult (runtime="claude2")."""
    folder = config_dir(env)
    if folder is None:
        return TurnResult("Второй аккаунт Claude не настроен (JARVIS_CLAUDE2_DIR в .env).", session_id, False, None,
                          "error", "claude2_not_configured", attempts=0, runtime="claude2")
    res = await claude_bridge.run_turn(prompt, session_id, on_event, env=env,
                                       account=(LIMITS_KEY, str(folder)), **kwargs)
    res.runtime = "claude2"
    if res.status == "auth_required":
        res.text = auth_text(folder)
    return res


def stop(run_id: str) -> bool:
    """Процесс хода лежит в общем реестре моста Claude: останавливаем тем же путём."""
    return claude_bridge.stop(run_id)
