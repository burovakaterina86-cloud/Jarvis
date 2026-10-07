"""Одна точка входа рилс-радара.

    python -m integrations.radar <config>

Коды выхода: 0 — готово; 2 — не хватает настроек или ключей; 3 — упёрлись в
потолок запросов (число рилсов за прогон, так тарифицирует Apify) или сервис
отказал — что успели собрать, всё равно на диске, папка результата честно
пишет, на чём остановились (`STOPPED.md`).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from . import filter as filter_mod
from . import apify, rank, report, transcribe
from .budget import BudgetExceeded, RequestBudget
from .config import ConfigError, RadarConfig, load_config
from .keys import KeysError, require_keys

ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = ROOT / "essa-ai" / "content"

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_BUDGET_OR_SERVICE = 3


def _utf8_output() -> None:
    """Отчёт не зависит от кодировки консоли — как в `integrations.visuals.build`."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        isatty = getattr(stream, "isatty", lambda: False)
        try:
            if isatty():
                reconfigure(errors="replace")
            else:
                reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def run(config: RadarConfig, apify_client, groq_client, out_dir: Path,
        now: datetime | None = None) -> int:
    """`now` — момент, от которого считаются окна свежести; без него — текущее время."""
    budget = RequestBudget(config.max_requests_per_run)
    try:
        raw_reels = apify.fetch_recent_reels(apify_client, budget, config.competitors,
                                              config.window_days, config.reels_per_account, now=now)
        relevant = filter_mod.filter_relevant(raw_reels, config.keywords)
        top = rank.rank_composite(relevant, config.top_k)
        transcripts = transcribe.transcribe_top(groq_client, top, out_dir / "transcripts")
        own_top = apify.fetch_own_top(apify_client, budget, config.own_username,
                                       config.own_window_days, config.own_fetch_limit, 10,
                                       now=now)
    except BudgetExceeded as exc:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "STOPPED.md").write_text(
            f"остановлено на потолке запросов: {exc}\n", encoding="utf-8")
        print(f"упёрлись в потолок запросов: {exc}")
        return EXIT_BUDGET_OR_SERVICE
    except Exception as exc:  # сервис отказал — Apify/Groq недоступны или вернули ошибку, или баг в коде
        from runtime import errorlog
        errorlog.record("radar.run", exc)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "STOPPED.md").write_text(f"остановлено: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"сервис отказал: {exc}")
        return EXIT_BUDGET_OR_SERVICE

    out_dir.mkdir(parents=True, exist_ok=True)
    report.write_radar_md(out_dir / "radar.md", top, transcripts)
    report.write_briefs_input(out_dir / "briefs-input.json", top, transcripts, config.top_final)
    report.write_own_top_md(out_dir / "own-top.md", own_top)
    print(f"готово: {out_dir}")
    print("briefs.md пишется отдельно, через textwriter -> humaniser, из briefs-input.json")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _utf8_output()
    if len(argv) != 1:
        print(__doc__)
        return EXIT_CONFIG
    try:
        config = load_config(argv[0])
    except ConfigError as exc:
        print(f"настройки не готовы: {exc}")
        return EXIT_CONFIG
    try:
        apify_token, groq_key = require_keys()
    except KeysError as exc:
        print(str(exc))
        return EXIT_CONFIG

    from .apify_client import ApifyApiClient
    from .groq_client import GroqApiClient

    apify_client = ApifyApiClient(apify_token)
    groq_client = GroqApiClient(groq_key)
    out_dir = CONTENT_ROOT / f"radar-{date.today().isoformat()}"
    return run(config, apify_client, groq_client, out_dir)


if __name__ == "__main__":
    sys.exit(main())
