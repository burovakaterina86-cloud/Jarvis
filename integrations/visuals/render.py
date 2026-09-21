"""Единственная точка снимка страницы.

`render_image(html_path, out_png, width, height)` — всё, чем в проекте
делается PNG из вёрстки. Никто другой браузер не дёргает.

Браузер в JARVIS подключён как MCP-сервер `playwright` (см. `.mcp.json`,
профиль `state/browser-profile`), питоновского пакета `playwright` в `.venv`
нет и ставить его таск не разрешает. Поэтому:

- если пакет всё-таки есть — снимок делается прямо здесь;
- если нет — функция не падает и не молчит: возвращает `RenderResult`
  с понятной причиной и готовым планом `mcp_plan` — последовательностью
  вызовов MCP-браузера, которую выполняет агент. Тексты комплекта при этом
  никуда не деваются, HTML остаётся на диске.

Шрифты на машине не установлены и приезжают с Google Fonts. Нет сети —
в `warnings` пишется, какой шрифт чем подменён.
"""
from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import tokens

#: Таймаут проверки доступности Google Fonts, секунды.
FONTS_TIMEOUT = 3.0

#: Хост локальной раздачи вёрстки для MCP-браузера.
SERVE_HOST = "127.0.0.1"

#: Что снимает MCP-браузер: холст, а не окно.
CANVAS_SELECTOR = "div.canvas"

#: Сколько ждать загрузки страницы и шрифтов перед снимком, миллисекунды.
PAGE_TIMEOUT_MS = 15000


@dataclass
class RenderResult:
    """Итог одного снимка."""

    ok: bool
    html_path: Path
    png_path: Path | None
    width: int
    height: int
    engine: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    mcp_plan: list[dict[str, Any]] = field(default_factory=list)


def _playwright_module():
    """Питоновский Playwright, если он есть в окружении. Иначе `None`."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return None
    return sync_playwright


def _fonts_reachable(timeout: float | None = None) -> bool:
    """Доступен ли хост Google Fonts."""
    try:
        with socket.create_connection(
            (tokens.GOOGLE_FONTS_HOST, 443), timeout=timeout or FONTS_TIMEOUT
        ):
            return True
    except OSError:
        return False


def font_warning() -> str | None:
    """Предупреждение о подмене шрифтов, если сети нет."""
    if _fonts_reachable():
        return None
    head = tokens.FONTS["HEADLINE"]
    body = tokens.FONTS["BODY"]
    return (
        f"Нет сети до {tokens.GOOGLE_FONTS_HOST}: "
        f"«{head}» и «{body}» не загрузились, "
        f"браузер подставит стек «{tokens.FALLBACK_STACK}». "
        "Снимок годится для черновой проверки, не для публикации."
    )


@contextmanager
def serve(directory: str | Path, host: str = SERVE_HOST):
    """Раздать папку по http на время снимка и вернуть базовый URL.

    Нужен потому, что MCP-браузер отказывает протоколу `file:`
    («Access to "file:" protocol is blocked»). Сервер локальный, порт
    выбирает система, живёт только внутри контекста.
    """
    directory = str(Path(directory).resolve())

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, *a):  # тишина в консоли
            pass

    httpd = ThreadingHTTPServer((host, 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def mcp_plan(
    html_path: Path, out_png: Path, width: int, height: int, base_url: str | None = None
) -> list[dict]:
    """План снимка через подключённый MCP-браузер.

    Её родной способ — вёрстка плюс снимок браузером
    (`SKILL_carousel-instagram.md` §17: «Upstream skill использует HTML/CSS + Playwright»).

    Две особенности этого MCP-сервера проверены на живом браузере:
    1. `file:` заблокирован — страницу отдаёт локальный `serve()`;
    2. размер окна фиксирован, `browser_resize` на кадр не влияет, поэтому
       снимается не вьюпорт, а сам холст (`div.canvas`) — его размер задан
       в CSS и от окна не зависит.
    Путь PNG обязан лежать внутри папки проекта: наружу сервер не пишет.
    """
    url = f"{base_url}/{Path(html_path).name}" if base_url else Path(html_path).resolve().as_uri()
    return [
        {
            "tool": "mcp__playwright__browser_navigate",
            "args": {"url": url},
            "note": "страницу раздаёт integrations.visuals.render.serve(); file: заблокирован",
        },
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "args": {
                "target": CANVAS_SELECTOR,
                "element": f"холст {width}×{height}",
                "filename": str(Path(out_png).resolve()),
                "scale": "css",
                "type": "png",
            },
            "note": "снимок холста, а не вьюпорта: окно MCP-браузера не масштабируется",
        },
    ]


def render_image(
    html_path: str | Path,
    out_png: str | Path,
    width: int = tokens.CANVAS["carousel"][0],
    height: int = tokens.CANVAS["carousel"][1],
) -> RenderResult:
    """Снять страницу `html_path` кадром `width×height` в файл `out_png`.

    Никогда не бросает из-за отсутствия браузера или сети: причина и план
    возвращаются в `RenderResult`, чтобы вызывающий ход не прерывался.
    """
    html_path = Path(html_path)
    out_png = Path(out_png)
    warnings = [w for w in (font_warning(),) if w]
    plan = mcp_plan(html_path, out_png, width, height)

    if not html_path.is_file():
        return RenderResult(
            ok=False, html_path=html_path, png_path=None, width=width, height=height,
            engine="none", warnings=warnings,
            error=f"нет файла вёрстки: {html_path}", mcp_plan=plan,
        )

    sync_playwright = _playwright_module()
    if sync_playwright is None:
        return RenderResult(
            ok=False, html_path=html_path, png_path=None, width=width, height=height,
            engine="none", warnings=warnings,
            error=(
                "питоновский пакет playwright не установлен — снимок делается "
                "подключённым MCP-браузером по шагам mcp_plan; вёрстка сохранена "
                f"в {html_path}"
            ),
            mcp_plan=plan,
        )

    try:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": height}, device_scale_factor=1
            )
            page.goto(html_path.resolve().as_uri(), timeout=PAGE_TIMEOUT_MS)
            try:
                page.wait_for_function("document.fonts.ready", timeout=PAGE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001 — шрифты не приехали, кадр всё равно снимаем
                warnings.append(
                    "шрифты не догрузились за "
                    f"{PAGE_TIMEOUT_MS // 1000} с, кадр снят стеком "
                    f"«{tokens.FALLBACK_STACK}»"
                )
            page.screenshot(path=str(out_png), type="png")
            browser.close()
    except Exception as exc:  # noqa: BLE001 — браузер не поднялся; ход не роняем
        return RenderResult(
            ok=False, html_path=html_path, png_path=None, width=width, height=height,
            engine="playwright-python", warnings=warnings,
            error=f"браузер не снял кадр: {exc}", mcp_plan=plan,
        )

    return RenderResult(
        ok=True, html_path=html_path, png_path=out_png, width=width, height=height,
        engine="playwright-python", warnings=warnings,
    )
