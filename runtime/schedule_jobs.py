"""Задачи по расписанию, которые Python делает сам (её решение 2026-10-06: беречь лимит Claude).

В `runtime/schedule.json` у такой задачи вместо `prompt` стоит `"handler"`:
  radar        — запускает скрипт радара и присылает 3–5 сильных тем и файл отчёта; Claude не нужен;
  morning      — собирает утреннее сообщение из файлов; Claude не нужен;
  corrections  — нет поправок за неделю → одна строка; есть → Claude получает их прямо в задании.
  content_plan — воскресенье вечером: Python собирает неделю (сбор, пул, расшифровки), потом Claude один ход
                 (отбор, перевод, стратегия, страница) и присылает ей файл плана.

Обработчик возвращает `Outcome`: `text` — готовое письмо владелице (уйдёт через `state/outbox/`, файлы
из `files`), либо `prompt` — короткое задание для одного хода Claude.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from runtime import errorlog, secretenv

ROOT = Path(__file__).resolve().parents[1]
CONTENT = Path("essa-ai") / "content"
RADAR_CONFIG = Path("essa-ai") / "radar" / "config.json"
CORRECTIONS = Path("memory") / "corrections.md"
RADAR_TIMEOUT_SEC = 30 * 60
RADAR_FRESH_DAYS = 7
MIN_HOOK_LEN = 20          # «10 из 10.», «Это.» — не тема
MAX_TOPICS = 5
MIN_TOPICS = 3
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


@dataclass
class Outcome:
    text: str = ""
    files: list[str] = field(default_factory=list)
    prompt: str = ""


# ---------- радар ----------

def parse_radar_md(text: str) -> list[dict]:
    """Строки таблицы `radar.md` (уже по убыванию композитного ранга) → словари."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or not cells[1].startswith("http"):
            continue
        rows.append({"author": cells[0], "url": cells[1], "date": cells[2], "views": cells[3],
                     "comments": cells[4], "er": cells[5], "hook": "|".join(cells[6:]).strip()})
    return rows


def top_topics(rows: list[dict], limit: int = MAX_TOPICS) -> list[dict]:
    """Самые сильные темы: с осмысленным хуком, без повторов; не хватает — добираем любыми."""
    seen, good, rest = set(), [], []
    for row in rows:
        key = row["hook"].lower()
        if key in seen:
            continue
        seen.add(key)
        (good if len(row["hook"]) >= MIN_HOOK_LEN else rest).append(row)
    picked = good[:limit]
    if len(picked) < MIN_TOPICS:
        picked += rest[:MIN_TOPICS - len(picked)]
    return picked


def _short_views(value: str) -> str:
    try:
        n = int(value)
    except ValueError:
        return value
    return f"{n / 1000:.0f} тыс." if n >= 10000 else (f"{n / 1000:.1f} тыс.".replace(".", ",") if n >= 1000 else str(n))


def topic_line(row: dict, hook_len: int = 110) -> str:
    hook = row["hook"] if len(row["hook"]) <= hook_len else row["hook"][:hook_len].rstrip() + "…"
    return f"• {row['author']} — «{hook}» ({_short_views(row['views'])} просмотров, ER {row['er']})"


def latest_radar(root: Path, today: dt.date, fresh_days: int = RADAR_FRESH_DAYS) -> Path | None:
    """Самая свежая папка `radar-ГГГГ-ММ-ДД` не старше `fresh_days` дней и с radar.md."""
    best = None
    for folder in (root / CONTENT).glob("radar-*"):
        m = re.fullmatch(r"radar-(\d{4}-\d{2}-\d{2})", folder.name)
        if not m or not (folder / "radar.md").is_file():
            continue
        try:
            day = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if 0 <= (today - day).days <= fresh_days and (best is None or day > best[0]):
            best = (day, folder)
    return best[1] if best else None


def _radar_python(root: Path) -> str:
    venv = root / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def run_radar_script(root: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run([_radar_python(root), "-m", "integrations.radar", str(root / RADAR_CONFIG)],
                              cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,   # трейсбек не теряем
                              timeout=RADAR_TIMEOUT_SEC, env=secretenv.scrub(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return 3, "радар шёл дольше 30 минут"
    except OSError as exc:
        return 3, f"радар не запустился: {type(exc).__name__}"
    tail = proc.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
    if proc.returncode not in (0, 2):
        errorlog.record("schedule.radar", message=" ".join(tail), type=f"exit {proc.returncode}")
    return proc.returncode, " ".join(tail)


def radar(root: Path, now: dt.datetime, runner=run_radar_script) -> Outcome:
    code, note = runner(root)
    if code == 2:
        return Outcome("Радар не запустился: не хватает настроек или ключей. " + note)
    if code != 0:
        return Outcome("Радар не дошёл до конца: упёрся в потолок запросов или сервис отказал "
                       "(подробности в STOPPED.md в папке радара). " + note)
    folder = latest_radar(root, now.date(), fresh_days=0)
    if folder is None:
        return Outcome("Радар отработал, но папку с отчётом я не нашёл — загляни в essa-ai/content/.")
    rows = parse_radar_md((folder / "radar.md").read_text(encoding="utf-8"))
    topics = top_topics(rows)
    rel = (folder / "radar.md").relative_to(root).as_posix()
    if not topics:
        return Outcome("Радар за неделю готов, но подходящих роликов в нём нет.", [rel])
    lines = ["Радар за неделю готов. Что сильнее всего зашло:", *map(topic_line, topics), "",
             "Комплект контента возьмёт тему отсюда — скажи «сделай контент», когда будешь готова. "
             "ТЗ на съёмку по любой теме напишу по твоей просьбе."]
    return Outcome("\n".join(lines), [rel])


# ---------- утро ----------

def _waiting_sets(root: Path) -> list[str]:
    names = []
    for status in sorted((root / CONTENT).glob("*/status")):
        try:
            if status.read_text(encoding="utf-8").strip().lower() == "draft":
                names.append(status.parent.name)
        except OSError:
            continue
    return names


def _waiting_drafts(root: Path) -> list[str]:
    out = []
    skills = root / "drafts" / "skills"
    if skills.is_dir():
        out += [f"навык «{p.name}»" for p in sorted(skills.iterdir()) if p.is_dir()]
    agents = root / "drafts" / "agents"
    if agents.is_dir():
        out += [f"помощник «{p.stem}»" for p in sorted(agents.glob("*.md"))]
    return out


def morning(root: Path, now: dt.datetime) -> Outcome:
    day = f"{WEEKDAYS[now.weekday()].capitalize()}, {now.day} {MONTHS[now.month - 1]}"
    lines = [f"Доброе утро! {day}.", ""]
    sets, drafts = _waiting_sets(root), _waiting_drafts(root)
    if sets or drafts:
        lines.append("Ждёт твоего решения:")
        lines += [f"• комплект {name}" for name in sets]
        lines += [f"• {name} (черновик — кнопки в чате)" for name in drafts]
        lines.append("")
    folder = latest_radar(root, now.date())
    topic = None
    if folder is not None:
        picked = top_topics(parse_radar_md((folder / "radar.md").read_text(encoding="utf-8")), 1)
        topic = picked[0] if picked else None
    if topic is not None:
        lines += ["Свежая тема из радара:", topic_line(topic), ""]
    if now.weekday() == 0:
        lines += ["В 9:00 запускаю свежий радар.", ""]
    if topic is not None:
        lines.append("Один шаг на сегодня: скажи «сделай контент» — соберу комплект на эту тему.")
    elif sets:
        lines.append(f"Один шаг на сегодня: посмотри комплект {sets[0]} и скажи, что поправить или принять.")
    elif drafts:
        lines.append(f"Один шаг на сегодня: реши по черновику — {drafts[0]}.")
    else:
        lines.append("Один шаг на сегодня: напиши тему — соберу комплект.")
    return Outcome("\n".join(lines).strip())


# ---------- поправки ----------

_CORRECTION = re.compile(r"^- (\d{4}-\d{2}-\d{2}) — (.+)$")


def week_corrections(root: Path, now: dt.datetime, days: int = 7) -> list[str]:
    try:
        text = (root / CORRECTIONS).read_text(encoding="utf-8")
    except OSError:
        return []
    since, out = now.date() - dt.timedelta(days=days), []
    for line in text.splitlines():
        m = _CORRECTION.match(line.strip())
        if not m or "разобрано" in line.lower():
            continue
        try:
            if dt.date.fromisoformat(m.group(1)) >= since:
                out.append(line.strip())
        except ValueError:
            continue
    return out


def corrections(root: Path, now: dt.datetime) -> Outcome:
    found = week_corrections(root, now)
    if not found:
        return Outcome("За неделю поправок не было — правил не предлагаю.")
    template = (root / "runtime" / "prompts" / "corrections-review.md").read_text(encoding="utf-8")
    return Outcome(prompt=template.replace("{{CORRECTIONS}}", "\n".join(found)))


# ---------- недельный контент-план ----------

CONTENT_PLAN_WEEKS = Path("essa-ai") / "content-plan" / "weeks"
CONTENT_PLAN_PROMPT = Path("runtime") / "prompts" / "weekly-content-plan.md"
CONTENT_PLAN_TIMEOUT_SEC = 90 * 60


def plan_monday(now: dt.datetime) -> dt.date:
    """Понедельник недели, для которой собираем план: в воскресенье и позже — следующий; пн–вт — текущий (догон)."""
    day = now.date()
    if day.weekday() in (0, 1):
        return day - dt.timedelta(days=day.weekday())
    return day + dt.timedelta(days=7 - day.weekday())


def run_content_plan_script(root: Path, week_rel: str) -> tuple[int, str]:
    try:
        proc = subprocess.run([_radar_python(root), "-m", "integrations.content_plan", "weekly", week_rel],
                              cwd=str(root), capture_output=True, timeout=CONTENT_PLAN_TIMEOUT_SEC, env=secretenv.scrub(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return 3, "сбор шёл дольше полутора часов"
    except OSError as exc:
        return 3, f"сбор не запустился: {type(exc).__name__}"
    text = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", "replace").strip().splitlines()
    return proc.returncode, " ".join(text[-3:])


def content_plan(root: Path, now: dt.datetime, runner=run_content_plan_script) -> Outcome:
    monday = plan_monday(now)
    week_rel = (CONTENT_PLAN_WEEKS / monday.isoformat()).as_posix()
    if (root / week_rel / f"plan-{monday.isoformat()}.html").is_file():
        return Outcome(f"План на неделю с {monday.day} {MONTHS[monday.month - 1]} уже собран, второй раз не трачу деньги.")
    code, note = runner(root, week_rel)
    if code == 2:
        return Outcome("План недели не начат: не хватает паспорта или ключа Apify. " + note)
    if code != 0:
        return Outcome("План недели не дошёл до конца: сервис отказал или упёрся в потолок трат "
                       f"(подробности в {week_rel}/STOPPED.md). Чаще всего это лимит расходов в Apify: "
                       "проверь Billing и Settings → Limits. " + note)
    template = (root / CONTENT_PLAN_PROMPT).read_text(encoding="utf-8")
    return Outcome(prompt=template.replace("{{WEEK_DIR}}", week_rel).replace("{{WEEK_START}}", monday.isoformat()))


HANDLERS = {"radar": radar, "morning": morning, "corrections": corrections, "content_plan": content_plan}


def run(handler: str, root: Path | str, now: dt.datetime) -> Outcome:
    return HANDLERS[handler](Path(root), now)
