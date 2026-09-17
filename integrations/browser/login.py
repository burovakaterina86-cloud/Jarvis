"""Ручной вход владелицы на сайт в профиле браузера JARVIS.

Запуск: `.venv\\Scripts\\python.exe -m integrations.browser.login <url>`
(команда бота `/browser login <сайт>` вызывает то же самое).

Открывает видимое окно Edge (или Chrome) с тем же профилем `state/browser-profile`,
который использует Playwright MCP, и ждёт, пока владелица скажет, что закончила.
Ждём подтверждения, а не завершения процесса: если браузер с этим профилем уже
запущен, он отдаёт окно существующему процессу, и запущенная команда возвращается
сразу — «дождаться закрытия окна» в этом случае невозможно.

Агент паролей не видит и не вводит: скрипт только запускает браузер.
Профиль занят одним процессом: если браузер JARVIS уже работает через MCP,
закрой его (или дождись конца браузерной задачи) перед входом.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import PROFILE_DIR, ROOT, profile_path

# (переменная окружения, путь внутри неё); Edge — первым, он же указан в .mcp.json
BROWSER_LOCATIONS = (
    ("PROGRAMFILES(X86)", r"Microsoft\Edge\Application\msedge.exe"),
    ("PROGRAMFILES", r"Microsoft\Edge\Application\msedge.exe"),
    ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
    ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
)


def find_browser(env: dict[str, str] | None = None) -> Path:
    """Путь к установленному Edge, иначе Chrome (в том числе в профиле пользователя)."""
    env = os.environ if env is None else env
    for var, rel in BROWSER_LOCATIONS:
        base = env.get(var)
        if not base:
            continue
        path = Path(base) / rel
        if path.exists():
            return path
    raise FileNotFoundError(
        "Не найден ни Microsoft Edge, ни Google Chrome — установи один из них."
    )


def mcp_browser_name(browser_path: Path) -> str:
    """Значение для `--browser` Playwright MCP по найденному браузеру."""
    return "msedge" if browser_path.name.lower().startswith("msedge") else "chrome"


def build_command(url: str, browser_path: Path | None = None, root: Path | None = None) -> list[str]:
    """Команда запуска видимого браузера с профилем JARVIS."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Ожидается http(s)-адрес, получено: {url!r}")
    browser_path = browser_path or find_browser()
    return [
        str(browser_path),
        f"--user-data-dir={profile_path(root)}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Использование: python -m integrations.browser.login <url>")
        return 2
    try:
        cmd = build_command(argv[0])
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc))
        return 2
    profile_path().mkdir(parents=True, exist_ok=True)
    print(f"Открываю {argv[0]} в профиле JARVIS ({profile_path()}).")
    subprocess.Popen(cmd)
    input("Войди на сайт. Когда закончишь — закрой окно браузера и нажми Enter: ")
    print("Готово. Сессия сохранена в профиле, агент будет работать под ней.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
