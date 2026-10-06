"""CLI: python -m integrations.content_plan <collect|pool|transcribe|digest|weekly|slides|render> <папка_недели>

collect      поиск + слой авторов + карусели → raw/ (платно, нужен APIFY_TOKEN, потолок из паспорта)
examples     её примеры рилсов: <папка>/urls.txt → расшифровки и examples_digest.txt (платно, ≈ $0,01 за рилс)
pool         raw/reels_*.json → reels_pool.json, reels_review.txt, carousels_pool.json
transcribe   расшифровать кандидатов пула (платно): топ N по слотам, коды в raw/transcripts_*.json
weekly       вся цепочка недели одной командой: сбор → пул → расшифровка → сводка (то, что запускает расписание)
slides       slides <папка> КОД…: скачать слайды выбранных каруселей в raw/carousels/ (бесплатно)
render       reels.json + carousels.json + strategy.json → plan-ГГГГ-ММ-ДД.html (адаптивная страница, без платных вызовов)
digest       пул + расшифровки → reels_digest.txt для отбора по тексту (Claude)

Коды выхода: 0 — готово, 2 — не хватает паспорта или ключа, 3 — потолок трат или сервис отказал.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import re
import sys
import urllib.error
from pathlib import Path

from . import collect, digest, history as hist, pool
from .apify import ApifyRestClient, ApifyRunError, BudgetExceeded, KeyMissing, UsdBudget, require_token
from .profile import ProfileError, load_profile

#: Расшифровываем всё, что прошло цифры; запас («запас») не расшифровываем — он дальше не идёт.
TRANSCRIBE_SLOTS = ("воронка", "аутлаер", "горячее", "воронка-600")


def _load_raw(week_dir: Path, prefix: str) -> dict[str, list]:
    raw = {}
    for fn in sorted(glob.glob(str(week_dir / "raw" / f"{prefix}_*.json"))):
        name = Path(fn).stem[len(prefix) + 1:]
        raw[name] = json.loads(Path(fn).read_text(encoding="utf-8"))
    return raw


def cmd_pool(profile, week_dir: Path, now: dt.datetime) -> int:
    seen = hist.seen_codes(hist.load_history())
    reels = pool.build_pool(_load_raw(week_dir, "reels"), seen=seen, now=now, window_days=profile.window_days,
                            threshold=profile.comments_threshold, fallback=profile.comments_fallback,
                            stop_words=profile.stop_words,
                            langs=profile.market_langs)
    (week_dir / "reels_pool.json").write_text(json.dumps(reels, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    (week_dir / "reels_review.txt").write_text(pool.review_text(reels), encoding="utf-8")
    print(f"рилсов в пуле: {len(reels)}; слоты: {pool.slot_counts(reels)}")
    posts = _load_raw(week_dir, "carousels")
    if posts:
        items = [x for rows in posts.values() for x in rows]
        carousels, used = pool.build_carousel_pool(items, seen=seen, now=now, window_days=profile.window_days,
                                                   threshold=profile.carousel_threshold,
                                                   fallback=profile.carousel_fallback, stop_words=profile.stop_words,
                                                   langs=profile.market_langs)
        (week_dir / "carousels_pool.json").write_text(json.dumps(carousels, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")
        print(f"каруселей: {len(carousels)} (порог {used} комментариев)")
    return 0


def cmd_digest(week_dir: Path) -> int:
    reels = json.loads((week_dir / "reels_pool.json").read_text(encoding="utf-8"))
    batches = list(_load_raw(week_dir, "transcripts").values())
    transcripts = digest.merge_transcripts(batches)
    (week_dir / "reels_transcripts.json").write_text(json.dumps(transcripts, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    (week_dir / "reels_digest.txt").write_text(digest.build_digest(reels, transcripts), encoding="utf-8")
    silent = sum(1 for x in transcripts.values() if not digest.has_speech(x))
    print(f"рилсов в сводке: {len(transcripts)}; без речи: {silent}")
    return 0


def cmd_collect(profile, week_dir: Path, client, budget: UsdBudget, today: dt.date, trial: bool = False) -> int:
    counts = collect.collect_reels(profile, client, budget, week_dir, today, trial=trial)
    authors = json.loads((week_dir / "authors.json").read_text(encoding="utf-8")) \
        if (week_dir / "authors.json").exists() else list(profile.seed_authors)
    if profile.carousels_per_week and authors and not trial:
        counts["carousels"] = collect.collect_carousels(profile, client, budget, week_dir, today, authors)
    print(f"собрано: {counts}; потрачено ≈ ${budget.spent:.2f} из ${budget.limit:.2f}")
    return 0


def cmd_transcribe(profile, week_dir: Path, client, budget: UsdBudget, codes: list[str] | None = None) -> int:
    reels = json.loads((week_dir / "reels_pool.json").read_text(encoding="utf-8"))
    codes = codes or [r["code"] for r in reels if r["slot"] in TRANSCRIBE_SLOTS]
    done = {c for rows in _load_raw(week_dir, "transcripts").values() for c in (x.get("shortCode") for x in rows)}
    todo = [c for c in codes if c not in done]
    n = collect.transcribe(todo, client, budget, week_dir, include_on_screen=bool(profile.no_speech_reels))
    print(f"расшифровано: {n} из {len(todo)}; потрачено ≈ ${budget.spent:.2f} из ${budget.limit:.2f}")
    return 0


def cmd_weekly(profile, week_dir: Path, client, today: dt.date) -> int:
    """Недельная цепочка без Claude. Каждый этап пропускается, если уже сделан: после сбоя или лимита можно
    запускать снова и не платить дважды. Расшифровка упёрлась в потолок — идём дальше с тем, что есть."""
    total = float(profile.budget_usd)
    if _load_raw(week_dir, "reels"):
        print("сбор уже был, пропускаю")
    else:
        cmd_collect(profile, week_dir, client, UsdBudget(round(total * 0.6, 2)), today)
    cmd_pool(profile, week_dir, dt.datetime.now(dt.timezone.utc))
    try:
        cmd_transcribe(profile, week_dir, client, UsdBudget(round(total * 0.4, 2)))
    except BudgetExceeded as exc:
        print(f"расшифровка остановилась на потолке ({exc}); иду дальше с тем, что есть")
    return cmd_digest(week_dir)


def reel_codes(text: str) -> list[str]:
    """Коды рилсов и постов из ссылок (параметры utm и повторы отбрасываются, порядок сохраняется)."""
    return list(dict.fromkeys(re.findall(r"instagram\.com/(?:reel|reels|p)/([\w-]+)", text)))


def cmd_examples(folder: Path, client, budget: UsdBudget) -> int:
    codes = reel_codes((folder / "urls.txt").read_text(encoding="utf-8"))
    done = {x.get("shortCode") for rows in _load_raw(folder, "transcripts").values() for x in rows}
    todo = [c for c in codes if c not in done]
    n = collect.transcribe(todo, client, budget, folder, include_on_screen=True) if todo else 0
    transcripts = digest.merge_transcripts(list(_load_raw(folder, "transcripts").values()))
    (folder / "examples_digest.txt").write_text(digest.build_digest([], transcripts), encoding="utf-8")
    silent = sum(1 for x in transcripts.values() if not digest.has_speech(x))
    print(f"примеров: {len(codes)}, расшифровано сейчас: {n}, без речи: {silent}; "
          f"потрачено ≈ ${budget.spent:.2f} из ${budget.limit:.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="integrations.content_plan")
    parser.add_argument("command", choices=["collect", "pool", "transcribe", "digest", "examples", "render", "weekly", "slides"])
    parser.add_argument("week_dir", type=Path)
    parser.add_argument("--budget", type=float, help="потолок трат на прогон, $ (по умолчанию из паспорта)")
    parser.add_argument("--trial", action="store_true",
                        help="пробная выдача первого запуска: меньше запросов, без слоя авторов и каруселей")
    parser.add_argument("slide_codes", nargs="*", help="slides: коды каруселей")
    parser.add_argument("--codes", nargs="+", help="transcribe: только эти рилсы (по умолчанию — все слоты кроме «запас»)")
    args = parser.parse_args(argv)
    week_dir: Path = args.week_dir
    week_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    try:
        if args.command == "render":
            from . import render
            out = render.render(week_dir)
            print(f"{out.name}: {out.stat().st_size / 1024:.1f} КБ")
            return 0
        if args.command == "slides":
            saved = collect.download_slides(week_dir, args.slide_codes)
            print(f"слайды скачаны: {saved}")
            return 0 if saved and all(saved.values()) else 3
        profile = load_profile(require=args.command != "examples")
        budget = UsdBudget(args.budget or (1.0 if args.command == "examples" else float(profile.budget_usd)))
        if args.command == "pool":
            return cmd_pool(profile, week_dir, dt.datetime.now(dt.timezone.utc))
        if args.command == "digest":
            return cmd_digest(week_dir)
        client = ApifyRestClient(require_token())
        if args.command == "examples":
            return cmd_examples(week_dir, client, budget)
        if args.command == "weekly":
            return cmd_weekly(profile, week_dir, client, today)
        if args.command == "collect":
            return cmd_collect(profile, week_dir, client, budget, today, trial=args.trial)
        return cmd_transcribe(profile, week_dir, client, budget, args.codes)
    except ProfileError as exc:
        print(f"паспорт не готов: {exc}", file=sys.stderr)
        return 2
    except KeyMissing as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except urllib.error.HTTPError as exc:
        why = ("у аккаунта Apify кончился лимит расходов или тариф не позволяет запуск — проверь Billing и Settings → Limits"
               if exc.code in (402, 403) else "сервис ответил ошибкой")
        (week_dir / "STOPPED.md").write_text(f"# Остановлено\n\nApify: HTTP {exc.code}. {why}.\n", encoding="utf-8")
        print(f"остановлено: Apify HTTP {exc.code}. {why}", file=sys.stderr)
        return 3
    except (BudgetExceeded, ApifyRunError) as exc:
        (week_dir / "STOPPED.md").write_text(f"# Остановлено\n\n{exc}\n", encoding="utf-8")
        print(f"остановлено: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
