"""Рилс-радар: швы из ticket.md — ранжирование, фильтр ключевых слов, потолок
запросов, отказ без ключей, отказ с метками [ЗАПОЛНИ], структура результата,
кодировка вывода, синхронность зеркала навыка `.agents/skills/reel-radar/`.

Живого прогона нет: HikerAPI из upstream заменён на Apify (её решение
2026-09-23), Apify/Groq — через подменяемые фейковые клиенты на заготовленных
ответах в форме актора `apify/instagram-reel-scraper`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Фильтр по ключевым словам (essa-ai/radar/filter.py)
# ---------------------------------------------------------------------------

def test_filter_matches_caption_by_word_boundary_case_insensitive():
    from integrations.radar.filter import filter_relevant

    reels = [
        {"shortCode": "a", "caption": "Как ИИ убирает рутину эксперта", "hashtags": []},
        {"shortCode": "b", "caption": "Рецепт борща на зиму", "hashtags": []},
        {"shortCode": "c", "caption": "миллион слов без совпадения", "hashtags": ["#automation"]},
    ]
    out = filter_relevant(reels, ["ии", "automation"])
    codes = {r["shortCode"] for r in out}
    assert codes == {"a", "c"}


def test_filter_does_not_match_substring_inside_another_word():
    from integrations.radar.filter import filter_relevant

    # "ии" не должно матчиться внутри слова "линии" — граница слова обязательна.
    reels = [{"shortCode": "x", "caption": "рисуем линии на графике", "hashtags": []}]
    assert filter_relevant(reels, ["ии"]) == []


def test_filter_empty_keywords_does_not_narrow():
    from integrations.radar.filter import filter_relevant

    reels = [{"shortCode": "a", "caption": "что угодно", "hashtags": []}]
    assert filter_relevant(reels, []) == reels


# ---------------------------------------------------------------------------
# Композитное ранжирование (essa-ai/radar/rank.py)
# ---------------------------------------------------------------------------

def test_rank_composite_orders_by_hand_computed_score():
    from integrations.radar.rank import rank_composite

    # Вручную: A лучший по просмотрам (место 0) и по ER (место 0), средний по
    # комментариям (место 1) -> сумма 1. B лучший по комментариям (0), худший
    # по просмотрам и ER (1, 1) -> сумма 2. C везде последний -> сумма 3.
    # Ожидаем порядок A, B, C — посчитано вручную, не тем же кодом, что рангует.
    reels = [
        {"shortCode": "A", "videoPlayCount": 10000, "likesCount": 500, "commentsCount": 80},
        {"shortCode": "B", "videoPlayCount": 5000, "likesCount": 50, "commentsCount": 100},
        {"shortCode": "C", "videoPlayCount": 1000, "likesCount": 10, "commentsCount": 5},
    ]
    out = rank_composite(reels, top_k=25)
    assert [r["shortCode"] for r in out] == ["A", "B", "C"]


def test_rank_composite_respects_top_k():
    from integrations.radar.rank import rank_composite

    reels = [{"shortCode": str(i), "videoPlayCount": i, "likesCount": i, "commentsCount": i}
             for i in range(10)]
    out = rank_composite(reels, top_k=3)
    assert len(out) == 3


# ---------------------------------------------------------------------------
# Потолок запросов (essa-ai/radar/budget.py + apify.py)
# ---------------------------------------------------------------------------

class _FakeApify:
    """Фейковый клиент Apify — форма ответа актора instagram-reel-scraper."""

    def __init__(self, by_username):
        self._by_username = by_username
        self.calls = []

    def fetch_reels(self, username, results_limit, newer_than):
        self.calls.append(username)
        return self._by_username.get(username, [])


def _reel(code, username, views, likes=1, comments=1, days_ago=1, now=None):
    now = now or datetime(2026, 9, 23, tzinfo=timezone.utc)
    ts = now.timestamp() - days_ago * 86400
    return {
        "shortCode": code,
        "ownerUsername": username,
        "caption": "ии автоматизация",
        "hashtags": [],
        "videoPlayCount": views,
        "videoViewCount": views,
        "likesCount": likes,
        "commentsCount": comments,
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "videoUrl": f"https://example.com/{code}.mp4",
        "url": f"https://instagram.com/reel/{code}/",
    }


def test_budget_stops_and_reports_where_it_stopped():
    from integrations.radar.apify import fetch_recent_reels
    from integrations.radar.budget import BudgetExceeded, RequestBudget

    client = _FakeApify({
        "one": [_reel("a1", "one", 100)],
        "two": [_reel("a2", "two", 100)],
        "three": [_reel("a3", "three", 100)],
    })
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    budget = RequestBudget(limit=5)  # хватит на один аккаунт (per_account=3), не на два
    with pytest.raises(BudgetExceeded) as excinfo:
        fetch_recent_reels(client, budget, ["one", "two", "three"], window_days=7,
                            per_account=3, now=now)
    assert excinfo.value.spent == 3  # первый аккаунт списан, второй не начат
    assert excinfo.value.limit == 5
    assert client.calls == ["one"]  # дальше не пошли


def test_run_writes_stopped_marker_on_budget_exceeded(tmp_path):
    from integrations.radar.__main__ import run
    from integrations.radar.config import load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "own_username": "her",
        "competitors": ["one", "two"],
        "keywords": [],
        "reels_per_account": 3,
        "max_requests_per_run": 3,
    }), encoding="utf-8")
    config = load_config(cfg_path)
    client = _FakeApify({"one": [_reel("a1", "one", 100)], "two": [_reel("a2", "two", 100)]})
    out_dir = tmp_path / "out"

    code = run(config, client, groq_client=None, out_dir=out_dir)

    assert code == 3
    assert (out_dir / "STOPPED.md").is_file()
    assert not (out_dir / "radar.md").exists()


# ---------------------------------------------------------------------------
# Отказ без ключей / с метками [ЗАПОЛНИ] (config.py, keys.py, __main__.py)
# ---------------------------------------------------------------------------

def test_require_keys_raises_when_missing(monkeypatch):
    from integrations.radar.keys import KeysError, require_keys

    with pytest.raises(KeysError) as excinfo:
        require_keys(env={})
    assert "APIFY_TOKEN" in str(excinfo.value)
    assert "GROQ_KEY" in str(excinfo.value)


def test_require_keys_ok_when_present():
    from integrations.radar.keys import require_keys

    apify, groq = require_keys(env={"APIFY_TOKEN": "x", "GROQ_KEY": "y"})
    assert (apify, groq) == ("x", "y")


def test_load_config_rejects_placeholder_username(tmp_path):
    from integrations.radar.config import ConfigError, load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "own_username": "[ЗАПОЛНИ: её ник]",
        "competitors": ["real_account"],
    }), encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_config(cfg_path)
    assert "own_username" in str(excinfo.value)


def test_load_config_rejects_empty_competitors(tmp_path):
    from integrations.radar.config import ConfigError, load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"own_username": "her", "competitors": []}), encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_config(cfg_path)
    assert "competitors" in str(excinfo.value)


def test_load_config_accepts_real_values(tmp_path):
    from integrations.radar.config import load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "own_username": "katerina_agents_ai",
        "competitors": ["zuhra.marketing", "oireels"],
    }), encoding="utf-8")
    config = load_config(cfg_path)
    assert config.own_username == "katerina_agents_ai"
    assert config.competitors == ["zuhra.marketing", "oireels"]
    assert config.max_requests_per_run == 200  # значение по умолчанию


def test_shipped_config_has_no_placeholders_and_real_usernames():
    """Владелица прислала ники — essa-ai/radar/config.json должен быть готов к прогону."""
    from integrations.radar.config import load_config

    config = load_config(ROOT / "essa-ai" / "radar" / "config.json")
    assert config.own_username == "katerina_agents_ai"
    assert set(config.competitors) == {"zuhra.marketing", "oireels", "mama_mozg", "mcdenil"}


def test_main_exits_2_without_config_placeholders_resolved(tmp_path, monkeypatch):
    from integrations.radar.__main__ import EXIT_CONFIG, main

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"own_username": "[ЗАПОЛНИ: ник]", "competitors": []}),
                         encoding="utf-8")
    assert main([str(cfg_path)]) == EXIT_CONFIG


def test_main_exits_2_when_keys_missing(tmp_path, monkeypatch):
    from integrations.radar.__main__ import EXIT_CONFIG, main

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"own_username": "her", "competitors": ["someone"]}),
                         encoding="utf-8")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.delenv("GROQ_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main([str(cfg_path)]) == EXIT_CONFIG


# ---------------------------------------------------------------------------
# Структура папки результата (report.py + run())
# ---------------------------------------------------------------------------

class _FakeGroq:
    def __init__(self, text="Инструмент вышел. Идёт за большой тройкой."):
        self._text = text

    def transcribe(self, audio_path):
        return self._text


def test_run_writes_result_folder_structure(tmp_path, monkeypatch):
    from integrations.radar import transcribe as transcribe_mod
    from integrations.radar.__main__ import EXIT_OK, run
    from integrations.radar.config import load_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "own_username": "her",
        "competitors": ["comp"],
        "keywords": [],
        "reels_per_account": 2,
        "own_fetch_limit": 5,
    }), encoding="utf-8")
    config = load_config(cfg_path)

    apify_client = _FakeApify({
        "comp": [_reel("c1", "comp", 5000, likes=100, comments=20)],
        "her": [_reel("h1", "her", 3000, likes=50, comments=10)],
    })
    groq_client = _FakeGroq()

    # Не трогаем сеть/ffmpeg — подменяем download и extract_audio на заглушки.
    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake video")
        return dest

    def fake_extract(video_path, dest):
        dest.write_bytes(b"fake audio")
        return dest

    monkeypatch.setattr(transcribe_mod, "default_download", fake_download)
    monkeypatch.setattr(transcribe_mod, "default_extract_audio", fake_extract)

    out_dir = tmp_path / "radar-2026-09-23"
    code = run(config, apify_client, groq_client, out_dir)

    assert code == EXIT_OK
    assert (out_dir / "radar.md").is_file()
    assert (out_dir / "briefs-input.json").is_file()
    assert (out_dir / "own-top.md").is_file()
    assert (out_dir / "transcripts").is_dir()
    assert (out_dir / "transcripts" / "c1.txt").read_text(encoding="utf-8") == groq_client._text

    briefs = json.loads((out_dir / "briefs-input.json").read_text(encoding="utf-8"))
    assert briefs["items"][0]["code"] == "c1"
    assert briefs["items"][0]["transcript"] == groq_client._text

    radar_text = (out_dir / "radar.md").read_text(encoding="utf-8")
    assert "comp" in radar_text
    assert "https://instagram.com/reel/c1/" in radar_text

    own_text = (out_dir / "own-top.md").read_text(encoding="utf-8")
    assert "https://instagram.com/reel/h1/" in own_text


# ---------------------------------------------------------------------------
# Кодировка вывода (как integrations.visuals.build)
# ---------------------------------------------------------------------------

def test_main_docstring_on_bad_args_does_not_crash_on_pipe(tmp_path, capsys):
    from integrations.radar.__main__ import main

    # Без аргументов main печатает __doc__ и возвращает 2 — не должен падать,
    # даже когда stdout перехвачен (как при запуске из JARVIS).
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "python -m integrations.radar" in captured.out


# ---------------------------------------------------------------------------
# Синхронность зеркала навыка (`.agents/skills/reel-radar/`)
# ---------------------------------------------------------------------------

def test_reel_radar_mirror_matches_claude_skill():
    claude_text = (ROOT / ".claude" / "skills" / "reel-radar" / "SKILL.md").read_text(encoding="utf-8")
    mirror_text = (ROOT / ".agents" / "skills" / "reel-radar" / "SKILL.md").read_text(encoding="utf-8")
    assert claude_text.replace(".claude/", ".Codex/") == mirror_text


def test_content_plan_mirror_matches_claude_skill():
    claude_text = (ROOT / ".claude" / "skills" / "content-plan" / "SKILL.md").read_text(encoding="utf-8")
    mirror_text = (ROOT / ".agents" / "skills" / "content-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert claude_text.replace(".claude/", ".Codex/") == mirror_text


def test_content_plan_mentions_reel_radar_connection():
    text = (ROOT / ".claude" / "skills" / "content-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "radar-*" in text
    assert "reel-radar" in text
