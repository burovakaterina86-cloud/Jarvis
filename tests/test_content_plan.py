"""Агент «Контент-план»: пул, норма автора, слоты, повторы, потолок трат, сбор на фальшивом Apify.

Живых запросов нет: клиент подменён фейком, выдача — в форме акторов (memo23, boolean, reel-scraper).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from integrations.content_plan import apify, collect, digest, history, pool
from integrations.content_plan.profile import Profile, ProfileError, load_profile, missing_fields

NOW = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.date()


def reel(code, *, days=2, comments=100, views=10_000, user="a", caption="how to use claude", **extra):
    ts = (NOW - dt.timedelta(days=days)).isoformat()
    return {"shortCode": code, "publishedAt": ts, "commentCount": comments, "viewCount": views,
            "username": user, "caption": caption, **extra}


# ---------- профиль ----------

def test_profile_refuses_placeholders(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({"niche": "[ЗАПОЛНИ: ниша]", "audience": "x", "tags": {"level1": ["ai"]},
                             "memo23_queries": ["claude skills"], "boolean_query_en": "a OR b"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="niche"):
        load_profile(p)
    assert load_profile(p, require=False).plan_reels == 9


def test_missing_fields_empty_lists_and_tags():
    assert set(missing_fields({})) == {"niche", "audience", "tags", "memo23_queries", "boolean_query_en"}
    ok = {"niche": "ai", "audience": "x", "tags": {"level1": ["a"], "level2": [], "level3": []},
          "memo23_queries": ["q"], "boolean_query_en": "a OR b"}
    assert missing_fields(ok) == []


# ---------- пул ----------

def test_pool_filters_old_junk_foreign_and_seen():
    raw = {"memo23": [
        reel("fresh", comments=50),
        reel("old", days=30),
        reel("junk", caption="UPSC exam tips"),
        reel("foreign", caption="como usar claude para você, que dica"),
        reel("cyr", caption="привет"),
        reel("seen"),
        reel("nodate", ) | {"publishedAt": None},
    ]}
    out = pool.build_pool(raw, seen={"seen"}, now=NOW)
    assert [r["code"] for r in out] == ["fresh"]


def test_pool_stop_words_from_profile_drop_candidate():
    raw = {"s": [reel("a", caption="astrology and claude"), reel("b")]}
    assert [r["code"] for r in pool.build_pool(raw, now=NOW, stop_words=["astrology"])] == ["b"]


def test_funnel_slot_needs_call_to_action_and_threshold():
    raw = {"s": [
        reel("f", comments=1500, views=50_000, caption='Comment "SKILLS" and I send the guide'),
        reel("nocta", comments=1500, views=50_000, caption="plain caption"),
        reel("f600", comments=700, views=500_000, caption="comment guide below"),
    ]}
    slots = {r["code"]: r["slot"] for r in pool.build_pool(raw, now=NOW)}
    assert slots["f"] == "воронка"
    assert slots["nocta"] == "горячее"
    assert slots["f600"] == "воронка-600"


def test_thresholds_come_from_profile():
    raw = {"s": [reel("f", comments=400, views=100_000, caption='comment "GUIDE" now')]}
    assert pool.build_pool(raw, now=NOW, threshold=300, fallback=100)[0]["slot"] == "воронка"
    assert pool.build_pool(raw, now=NOW, threshold=1000, fallback=600)[0]["slot"] == "запас"


def test_outlier_vs_own_author_median_not_followers():
    # у автора 6 рилсов по ~1000 просмотров и один на 5000 → ×5
    rows = [reel(f"n{i}", views=1000, user="small") for i in range(6)] + [reel("hit", views=5000, user="small")]
    out = {r["code"]: r for r in pool.build_pool({"authors": rows}, now=NOW)}
    assert out["hit"]["x"] == 5.0 and out["hit"]["slot"] == "аутлаер"
    assert out["n0"]["x"] == 1.0


def test_no_median_for_author_with_fewer_than_five_reels():
    rows = [reel(f"n{i}", views=1000, user="few") for i in range(4)]
    assert all(r["x"] is None for r in pool.build_pool({"authors": rows}, now=NOW))


def test_same_reel_from_two_sources_is_merged_and_keeps_norm():
    authors = [reel(f"n{i}", views=1000, user="u") for i in range(5)] + [reel("dup", views=4000, user="u")]
    out = pool.build_pool({"memo23": [reel("dup", views=4000, user="u")], "authors": authors}, now=NOW)
    dup = next(r for r in out if r["code"] == "dup")
    assert dup["src"] == ["authors", "memo23"] and dup["x"] == 4.0


def test_hidden_likes_minus_one_do_not_break_numbers():
    out = pool.build_pool({"s": [reel("a") | {"likeCount": -1}]}, now=NOW)
    assert out[0]["L"] == 0


def test_timestamp_in_unix_seconds_is_supported():
    item = reel("u") | {"publishedAt": None, "takenAt": int((NOW - dt.timedelta(days=3)).timestamp())}
    assert pool.build_pool({"s": [item]}, now=NOW)[0]["age"] == 3


def test_pool_sorted_funnels_first():
    raw = {"s": [reel("hot", comments=2000, views=400_000),
                 reel("f", comments=1200, views=30_000, caption='comment "GUIDE" please')]}
    assert [r["code"] for r in pool.build_pool(raw, now=NOW)] == ["f", "hot"]


# ---------- карусели ----------

def post(code, kind="Sidecar", comments=1200, days=3, caption="claude tips"):
    return {"shortCode": code, "type": kind, "commentsCount": comments, "likesCount": 5,
            "timestamp": (NOW - dt.timedelta(days=days)).isoformat(), "caption": caption,
            "ownerUsername": "x", "childPosts": [{}, {}, {}]}


def test_carousel_pool_only_sidecar_and_fallback_threshold():
    strong, used = pool.build_carousel_pool([post("a"), post("b", kind="Video"), post("c", comments=400)], now=NOW)
    assert used == 300 and [r["code"] for r in strong] == ["a", "c"]
    many = [post(f"p{i}") for i in range(3)] + [post("low", comments=400)]
    top, used = pool.build_carousel_pool(many, now=NOW)
    assert used == 1000 and len(top) == 3
    assert top[0]["slides"] == 3


# ---------- расшифровки ----------

def test_digest_prefers_record_with_text_and_trims_speech():
    pl = pool.build_pool({"s": [reel("a", comments=1500, views=50_000)]}, now=NOW)
    tr = digest.merge_transcripts([[{"shortCode": "a", "status": "repeat"}],
                                   [{"shortCode": "a", "transcript": "x" * 2000, "language": "en",
                                     "durationSeconds": 31.6}]])
    text = digest.build_digest(pl, tr)
    assert "SPEECH: " + "x" * 900 in text and "x" * 901 not in text
    assert "dur=32s" in text and "@a" in text


def test_digest_on_screen_dict_and_missing_speech():
    tr = {"a": {"shortCode": "a", "onScreenText": {"headline": "H", "body": "B", "cta": "C"}}}
    text = digest.build_digest([], tr)
    assert "ON-SCREEN: H B C" in text and "SPEECH: —" in text
    assert not digest.has_speech(tr["a"])


# ---------- история ----------

def test_history_append_is_idempotent_per_week(tmp_path):
    h = history.append_week(history.load_history(tmp_path / "none.json"), week="2026-10-05", reel_codes=["a"],
                            carousel_codes=["c"], code_words=["гайд"], reel_topics=["t"], carousel_topics=["ct"])
    h = history.append_week(h, week="2026-10-05", reel_codes=["a", "b"], carousel_codes=[], code_words=[],
                            reel_topics=["t2"], carousel_topics=[])
    assert len(h["weeks"]) == 1 and h["weeks"][0]["reel_topics"] == ["t2"]
    assert h["reel_codes"] == ["a", "b"] and history.seen_codes(h) == {"a", "b", "c"}
    history.save_history(h, tmp_path / "h.json")
    assert history.load_history(tmp_path / "h.json") == h


# ---------- Apify: цена, потолок, клиент ----------

def test_estimate_and_budget_stop_before_run():
    assert apify.estimate(apify.UNIT_COST_USD and collect.TRANSCRIBER, 100) == 1.0
    assert apify.estimate(collect.BOOLEAN, 50) == pytest.approx(0.00145 * 50 + 0.02)
    with pytest.raises(KeyError):
        apify.estimate("unknown~actor", 1)
    b = apify.UsdBudget(1.0)
    b.charge(0.6)
    with pytest.raises(apify.BudgetExceeded):
        b.charge(0.5)
    assert b.spent == 0.6


class FakeClient:
    def __init__(self, data):
        self.data, self.calls = data, []

    def run(self, actor, payload):
        self.calls.append((actor, payload))
        return self.data.get(actor, [])


def _profile(**kw):
    base = {"memo23_queries": ["claude skills", "ai agents"], "memo23_cta_queries": ["comment claude"],
            "boolean_query_en": "claude OR chatgpt", "seed_authors": ["seed1"], "window_days": 14,
            "market_langs": ["en"]}
    return Profile({**base, **kw})


def test_collect_reels_runs_sources_then_authors_and_saves_raw(tmp_path):
    client = FakeClient({
        collect.MEMO23: [reel("m1", comments=900, views=200_000, user="found")],
        collect.BOOLEAN: [reel("b1", comments=10, views=500, user="tiny")],
        collect.REEL_SCRAPER: [reel("a1", user="seed1")],
    })
    budget = apify.UsdBudget(10)
    counts = collect.collect_reels(_profile(), client, budget, tmp_path, TODAY)
    assert counts == {"memo23": 1, "boolean": 1, "authors": 1}
    memo = client.calls[0]
    assert memo[0] == collect.MEMO23 and memo[1]["queries"] == ["claude skills", "ai agents", "comment claude"]
    assert client.calls[1][1]["oldestPostDate"] == "2026-09-22"
    authors = client.calls[2][1]["username"]
    assert authors[0] == "seed1" and "found" in authors and "tiny" not in authors   # сильный автор из поиска
    assert (tmp_path / "raw" / "reels_authors.json").exists()
    assert budget.spent == pytest.approx(3 * 60 * 0.0013 + (60 * 0.00145 + 0.03) + 2 * 12 * 0.0023)


def test_collect_stops_on_budget_without_calling_actor(tmp_path):
    client = FakeClient({})
    with pytest.raises(apify.BudgetExceeded):
        collect.collect_reels(_profile(), client, apify.UsdBudget(0.05), tmp_path, TODAY)
    assert client.calls == []


def test_discover_authors_skips_junk_and_caps_but_keeps_all_seed():
    rows = [{"username": "good", "commentCount": 500, "caption": "claude"},
            {"username": "junk", "commentCount": 900, "caption": "UPSC exam"},
            {"username": "quiet", "commentCount": 5, "viewCount": 10}]
    assert collect.discover_authors(rows, ["s1", "s2"]) == ["s1", "s2", "good"]
    assert collect.discover_authors(rows, ["s1", "s2"], cap=1) == ["s1", "s2"]


def test_transcribe_chunks_and_saves(tmp_path):
    codes = [f"c{i}" for i in range(collect.TRANSCRIBE_CHUNK + 5)]
    client = FakeClient({collect.TRANSCRIBER: [{"shortCode": "c0", "transcript": "hi"}]})
    budget = apify.UsdBudget(10)
    collect.transcribe(codes, client, budget, tmp_path)
    assert len(client.calls) == 2 and budget.spent == pytest.approx(len(codes) * 0.01)
    assert (tmp_path / "raw" / "transcripts_01.json").exists() and (tmp_path / "raw" / "transcripts_02.json").exists()
    assert client.calls[0][1]["reelUrls"][0] == "https://www.instagram.com/reel/c0/"


def test_rest_client_polls_until_done_and_paginates():
    seq = []

    class Resp:
        def __init__(self, obj): self.obj = obj
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.obj).encode()

    answers = iter([
        {"data": {"id": "r1", "status": "RUNNING"}},
        {"data": {"status": "RUNNING"}},
        {"data": {"status": "SUCCEEDED"}},
        {"data": {"defaultDatasetId": "d1"}},
        [{"i": n} for n in range(1000)],
        [{"i": 1000}],
    ])

    def opener(req, timeout):
        seq.append((req.method, req.full_url.split("/v2")[1]))
        assert req.headers["Authorization"] == "Bearer T" and "T" not in req.full_url
        return Resp(next(answers))

    client = apify.ApifyRestClient("T", poll_sec=0, sleep=lambda s: None, opener=opener)
    items = client.run("a~b", {"x": 1})
    assert len(items) == 1001
    assert seq[0] == ("POST", "/acts/a~b/runs") and seq[-1][1].endswith("offset=1000")


def test_rest_client_aborts_when_too_slow_and_fails_on_empty_failed_run():
    class Resp:
        def __init__(self, obj): self.obj = obj
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self.obj).encode()

    def slow(req, timeout):
        return Resp({"data": {"id": "r", "status": "RUNNING"}})

    client = apify.ApifyRestClient("T", max_wait_sec=10, poll_sec=5, sleep=lambda s: None, opener=slow)
    with pytest.raises(apify.ApifyRunError, match="остановлен"):
        client.run("a~b", {})

    answers = iter([{"data": {"id": "r", "status": "FAILED"}}, {"data": {"defaultDatasetId": "d"}}, []])
    failed = apify.ApifyRestClient("T", sleep=lambda s: None, opener=lambda r, timeout: Resp(next(answers)))
    with pytest.raises(apify.ApifyRunError, match="FAILED"):
        failed.run("a~b", {})


def test_missing_token_is_named_not_leaked():
    with pytest.raises(apify.KeyMissing, match="APIFY_TOKEN"):
        apify.require_token({})
    assert apify.require_token({"APIFY_TOKEN": "x"}) == "x"


def test_reel_codes_from_links_strip_utm_and_dedupe():
    from integrations.content_plan.__main__ import reel_codes
    text = " ".join([
        "https://www.instagram.com/reel/DeGpOkIOaCh/?utm_source=ig_web_copy_link&stkn=abc",
        "https://www.instagram.com/reel/Dd--BjlO0yv/",
        "https://www.instagram.com/reel/DeGpOkIOaCh/",
        "https://www.instagram.com/p/AbC_1/",
    ])
    assert reel_codes(text) == ["DeGpOkIOaCh", "Dd--BjlO0yv", "AbC_1"]


# ---------- русский рынок (её примеры в основном на русском) ----------

@pytest.mark.parametrize("text", [
    "Пиши «монтаж» и забирай инструкцию 🔥",
    "Пиши слово тренд в комментариях",
    "Напиши в комментах слово АГЕНТ — пришлю",
    "Оставляй кодовое слово «Инструкция» в описании",
])
def test_russian_call_to_action_is_recognised(text):
    assert pool.has_cta(text)


@pytest.mark.parametrize("text", ["Пиши мне, если что", "обычная подпись про нейросети", ""])
def test_russian_text_without_code_word_is_not_call_to_action(text):
    assert not pool.has_cta(text)


def test_language_filter_follows_profile_languages():
    ru, en, empty = "Как собрать агента в Клод", "how to build an agent in claude", "🔥🔥"
    assert pool.caption_lang_ok(ru, ["ru", "en"]) and not pool.caption_lang_ok(ru, ["en"])
    assert pool.caption_lang_ok(en, ["en"]) and not pool.caption_lang_ok(en, ["ru"])
    assert pool.caption_lang_ok(empty, ["ru"]) and pool.caption_lang_ok(empty, ["en"])
    assert not pool.caption_lang_ok("你好 claude", ["ru", "en"])


def test_pool_keeps_russian_funnel_when_ru_is_in_profile():
    raw = {"s": [reel("r", comments=1500, views=60_000, caption="Пиши «монтаж» и забирай инструкцию")]}
    assert pool.build_pool(raw, now=NOW, langs=["en"]) == []
    out = pool.build_pool(raw, now=NOW, langs=["ru", "en"])
    assert out and out[0]["slot"] == "воронка"


def test_memo23_english_only_flag_depends_on_languages():
    en = collect.search_sources(_profile(market_langs=["en"]), TODAY)[0].payload
    mixed = collect.search_sources(_profile(market_langs=["ru", "en"]), TODAY)[0].payload
    assert en["englishOnly"] is True and mixed["englishOnly"] is False


def test_trial_collect_is_small_and_has_no_author_layer(tmp_path):
    prof = _profile(memo23_queries=[f"q{i}" for i in range(12)], memo23_cta_queries=["c1", "c2", "c3"])
    client = FakeClient({collect.MEMO23: [reel("m1", comments=900, views=200_000)]})
    budget = apify.UsdBudget(2)
    counts = collect.collect_reels(prof, client, budget, tmp_path, TODAY, trial=True)
    assert "authors" not in counts
    memo = client.calls[0][1]
    assert len(memo["queries"]) == 8 and memo["maxResultsPerQuery"] == 40 and memo["minimumComments"] == 100
    assert memo["queries"][-2:] == ["c1", "c2"]
    assert budget.spent < 0.65


# ---------- недельная цепочка и слайды ----------

def _weekly_profile(budget_usd=6, **kw):
    return _profile(plan_reels=6, budget_usd=budget_usd, carousels_per_week=0, comments_threshold=1000,
                    comments_fallback=600, carousel_threshold=1000, carousel_fallback=300, stop_words=[],
                    window_days=14, no_speech_reels=False, **kw)


def test_weekly_runs_all_stages_then_skips_paid_collect_on_rerun(tmp_path, capsys):
    from integrations.content_plan.__main__ import cmd_weekly
    now = dt.datetime.now(dt.timezone.utc)
    row = {"shortCode": "w1", "publishedAt": (now - dt.timedelta(days=1)).isoformat(), "commentCount": 1500,
           "viewCount": 50000, "username": "u", "caption": 'comment "GUIDE" claude'}
    client = FakeClient({collect.MEMO23: [row], collect.TRANSCRIBER: [{"shortCode": "w1", "transcript": "hello", "language": "English"}]})
    assert cmd_weekly(_weekly_profile(), tmp_path, client, TODAY) == 0
    actors = [a for a, _ in client.calls]
    assert collect.MEMO23 in actors and collect.TRANSCRIBER in actors
    assert (tmp_path / "reels_pool.json").exists() and "w1" in (tmp_path / "reels_digest.txt").read_text(encoding="utf-8")
    paid_before = len(client.calls)
    assert cmd_weekly(_weekly_profile(), tmp_path, client, TODAY) == 0
    assert len(client.calls) == paid_before                      # ничего не купили второй раз
    assert "сбор уже был" in capsys.readouterr().out


def test_weekly_goes_on_when_transcription_hits_budget(tmp_path, capsys):
    from integrations.content_plan.__main__ import cmd_weekly
    now = dt.datetime.now(dt.timezone.utc)
    rows = [{"shortCode": f"c{i}", "publishedAt": (now - dt.timedelta(days=1)).isoformat(), "commentCount": 2000,
             "viewCount": 90000, "username": f"u{i}", "caption": 'comment "GUIDE" claude'} for i in range(3)]
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "reels_memo23.json").write_text(json.dumps(rows), encoding="utf-8")   # сбор уже сделан
    client = FakeClient({})
    # на расшифровку 40% от $0,05 = $0,02, а пачка из трёх стоит $0,03: упрёмся в потолок и пойдём дальше
    assert cmd_weekly(_weekly_profile(budget_usd=0.05), tmp_path, client, TODAY) == 0
    assert "остановилась на потолке" in capsys.readouterr().out
    assert client.calls == []                                        # платный актор не запускали
    assert (tmp_path / "reels_digest.txt").exists()


def test_download_slides_only_from_instagram_hosts_and_saves_numbered(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    item = {"shortCode": "car1", "childPosts": [{"displayUrl": "https://scontent.cdninstagram.com/a.jpg"},
                                                {"displayUrl": "https://evil.example.com/b.jpg"},
                                                {"displayUrl": "https://x.fbcdn.net/c.jpg"}]}
    (raw / "carousels_authors.json").write_text(json.dumps([item, {"shortCode": "other"}]), encoding="utf-8")
    asked = []
    saved = collect.download_slides(tmp_path, ["car1"], fetch=lambda u: asked.append(u) or b"img")
    assert saved == {"car1": 2} and all("evil" not in u for u in asked)
    assert (raw / "carousels" / "car1" / "01.jpg").read_bytes() == b"img" and (raw / "carousels" / "car1" / "03.jpg").exists()


# ---------- команды без самодельных скриптов ----------

def test_digest_writes_short_file_with_one_line_per_ru_en_reel(tmp_path):
    from integrations.content_plan.__main__ import cmd_digest
    (tmp_path / "raw").mkdir()
    now = dt.datetime.now(dt.timezone.utc)
    pool_rows = pool.build_pool({"s": [reel("r1", comments=2000, views=90000, caption="claude tips"),
                                       reel("r2", comments=2000, views=90000, caption="claude hindi")]}, now=now)
    (tmp_path / "reels_pool.json").write_text(json.dumps(pool_rows), encoding="utf-8")
    (tmp_path / "raw" / "transcripts_01.json").write_text(json.dumps([
        {"shortCode": "r1", "transcript": "hello  there\nfriend", "language": "English", "durationSeconds": 30.4},
        {"shortCode": "r2", "transcript": "namaste", "language": "Hindi"},
        {"shortCode": "r3", "transcript": "", "status": "no_speech"}]), encoding="utf-8")
    cmd_digest(tmp_path)
    lines = (tmp_path / "reels_short.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and lines[0].startswith("r1|@a|") and "hello there friend" in lines[0] and "|En|30s|" in lines[0]


def test_show_prints_full_speech_and_reports_missing(tmp_path, capsys):
    from integrations.content_plan.__main__ import cmd_show
    now = dt.datetime.now(dt.timezone.utc)
    rows = pool.build_pool({"s": [reel("r1", comments=2000, views=90000)]}, now=now)
    (tmp_path / "reels_pool.json").write_text(json.dumps(rows), encoding="utf-8")
    (tmp_path / "reels_transcripts.json").write_text(json.dumps({"r1": {"transcript": "full speech " * 200, "language": "English"}}), encoding="utf-8")
    assert cmd_show(tmp_path, ["r1", "nope"]) == 3
    out = capsys.readouterr().out
    assert "### r1" in out and out.count("full speech") == 200 and "### nope: нет в пуле" in out


def test_check_requires_pipeline_mark_recommended_reel_and_known_codes(tmp_path, capsys):
    from integrations.content_plan.__main__ import cmd_check
    mark = "textwriter → humaniser → VOICE — пройден"
    day = {"date": "2026-10-12", "reels": [{"code": "r1", "recommended": True}]}
    for name, body in (("reels", {"pipeline": mark, "days": [day]}), ("carousels", {"pipeline": mark}), ("strategy", {"pipeline": mark})):
        (tmp_path / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "reels_pool.json").write_text(json.dumps([{"code": "r1"}]), encoding="utf-8")
    assert cmd_check(tmp_path) == 0 and "проблем нет" in capsys.readouterr().out
    (tmp_path / "reels.json").write_text(json.dumps({"days": [{"date": "x", "reels": [{"code": "zzz"}]}]}), encoding="utf-8")
    assert cmd_check(tmp_path) == 2
    out = capsys.readouterr().out
    assert "нет отметки pipeline" in out and "zzz не найден" in out and "нет рекомендуемого" in out


def test_slides_are_shrunk_below_the_guard_read_limit(tmp_path):
    """Реальный ffmpeg на реальной картинке: слайд 700+ КБ должен стать читаемым без кнопки (<100 КБ)."""
    import shutil as sh
    import subprocess
    if not sh.which("ffmpeg"):
        import pytest
        pytest.skip("нет ffmpeg")
    big = tmp_path / "big.jpg"
    # шумовая картинка 1024×1280: после JPEG весит сотни КБ
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "nullsrc=s=1024x1280,geq=random(1)*255:128:128",
                    "-frames:v", "1", "-q:v", "2", str(big)], check=True)
    assert big.stat().st_size > 200_000
    assert collect.shrink_image(big) is True
    assert big.stat().st_size <= collect.SLIDE_MAX_BYTES
    assert not list(tmp_path.glob("*.orig.jpg")) and not list(tmp_path.glob("*.tmp.jpg"))
    small = tmp_path / "small.jpg"
    small.write_bytes(b"x" * 100)
    assert collect.shrink_image(small) is True and small.read_bytes() == b"x" * 100


def test_download_slides_calls_shrink_for_each_saved_file(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    item = {"shortCode": "c1", "childPosts": [{"displayUrl": "https://a.cdninstagram.com/1.jpg"}]}
    (raw / "carousels_x.json").write_text(json.dumps([item]), encoding="utf-8")
    seen = []
    collect.download_slides(tmp_path, ["c1"], fetch=lambda u: b"img", shrink=seen.append)
    assert [p.name for p in seen] == ["01.jpg"]


# ---------- ревью 2026-10-07 ----------

def test_collect_is_not_skipped_forever_after_a_failed_carousel_layer(tmp_path):
    from types import SimpleNamespace

    from integrations.content_plan.__main__ import COLLECT_DONE, collect_finished
    profile = SimpleNamespace(carousels_per_week=3)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "reels_a.json").write_text("[]", encoding="utf-8")
    assert collect_finished(profile, tmp_path) is False                  # рилсы есть, каруселей нет — слой не добран
    (raw / "carousels_a.json").write_text("[]", encoding="utf-8")
    assert collect_finished(profile, tmp_path) is True                   # неделя без метки, но целиком собрана
    (raw / "carousels_a.json").unlink()
    (raw / COLLECT_DONE).write_text("x", encoding="utf-8")
    assert collect_finished(profile, tmp_path) is True                   # метка важнее
    assert collect_finished(SimpleNamespace(carousels_per_week=0), tmp_path / "other") is False


def test_resume_does_not_pay_twice_for_collected_reels(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from integrations.content_plan import __main__ as cp
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "reels_a.json").write_text("[]", encoding="utf-8")
    calls = []
    monkeypatch.setattr(cp.collect, "collect_reels", lambda *a, **k: calls.append("reels") or {"reels": 1})
    monkeypatch.setattr(cp.collect, "collect_carousels", lambda *a, **k: calls.append("carousels") or 2)
    profile = SimpleNamespace(carousels_per_week=3, seed_authors=["a"])
    import datetime as dt
    cp.cmd_collect(profile, tmp_path, None, cp.UsdBudget(1.0), dt.date(2026, 10, 7), resume=True)
    assert calls == ["carousels"] and (raw / cp.COLLECT_DONE).exists()


def test_original_link_must_be_http():
    from integrations.content_plan.render import U
    assert U("javascript:alert(1)") == "#" and U(None) == "#" and U("data:text/html,x") == "#"
    assert U("https://www.instagram.com/reel/abc/") == "https://www.instagram.com/reel/abc/"


def test_shrink_reports_failure_when_file_stays_too_big(tmp_path, monkeypatch):
    from integrations.content_plan import collect
    big = tmp_path / "a.jpg"
    big.write_bytes(b"x" * 500)
    monkeypatch.setattr(collect.shutil, "which", lambda n: "ffmpeg")

    class R:
        returncode = 0

    def fake_run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"y" * 400)        # ffmpeg «отработал», но файл всё равно больше лимита
        return R()

    monkeypatch.setattr(collect.subprocess, "run", fake_run)
    assert collect.shrink_image(big, max_bytes=100) is False
