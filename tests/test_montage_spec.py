"""Спецификация ролика: якоря на слова, окна сцен, ошибки по-русски. Без сети и без ffmpeg."""
import json
from pathlib import Path

import pytest

from integrations.montage import spec as S

ROOT = Path(__file__).resolve().parents[1]
WORDS = json.loads((ROOT / "tests" / "fixtures" / "montage_words_v2.json").read_text(encoding="utf-8"))
EXAMPLE = ROOT / "integrations" / "montage" / "examples" / "10-sistem.spec.json"
DUR = 65.99


def _res(scenes):
    return S.resolve({"scenes": scenes}, WORDS, DUR)


def test_word_anchor_finds_first_stem_after_time():
    assert S.find_word(WORDS, "первая") == 3.4
    assert S.find_word(WORDS, "итог") == 48.76            # «Недельный итог»
    assert S.find_word(WORDS, "итог", after=53.9) == 54.0  # «Итог всей работы»
    assert S.find_word(WORDS, "несуществующее") is None


def test_numbers_and_anchors_both_work_and_offset_applies():
    assert S.resolve_time(5, WORDS) == 5.0
    assert S.resolve_time({"word": "вторая", "offset": 0.5}, WORDS) == 9.6


def test_missing_word_is_an_error_not_a_guess():
    with pytest.raises(S.SpecError, match="нет слова «лодка»"):
        S.resolve_time({"word": "лодка"}, WORDS, "сцена 3")


def test_scene_ends_at_next_start_and_last_at_duration():
    r = _res([{"type": "hook", "start": 0, "lines": [[{"t": "а"}]]},
              {"type": "step", "n": 1, "start": {"word": "первая"}, "title": "Т", "chips": []}])
    assert (r.scenes[0].start, r.scenes[0].end) == (0.0, 3.4)
    assert r.scenes[1].end == DUR


def test_scenes_must_go_in_time_order_and_be_long_enough():
    with pytest.raises(S.SpecError, match="не позже предыдущей"):
        _res([{"type": "hook", "start": 5, "lines": []}, {"type": "step", "n": 1, "start": 4, "title": "", "chips": []}])
    with pytest.raises(S.SpecError, match="короче"):
        _res([{"type": "hook", "start": 0, "lines": []}, {"type": "step", "n": 1, "start": 0.3, "title": "", "chips": []}])
    with pytest.raises(S.SpecError, match="неизвестный тип"):
        _res([{"type": "magic", "start": 0}])


def test_chip_press_time_is_the_spoken_word_inside_the_window():
    r = _res([{"type": "step", "n": 1, "start": 3.4, "end": 7.74, "title": "Т",
               "chips": [{"text": "календарь", "word": "календар"}, {"text": "почта", "word": "почту"}]}])
    assert [c["t"] for c in r.scenes[0].data["chips"]] == [6.04, 6.66]


def test_chip_word_outside_the_window_is_spread_evenly_and_explicit_t_wins():
    r = _res([{"type": "step", "n": 7, "start": 35.96, "end": 37.94, "title": "Т",
               "chips": [{"text": "a", "word": "посты"}, {"arrow": True}, {"text": "b", "t": 37.25}]}])
    chips = [c for c in r.scenes[0].data["chips"] if not c.get("arrow")]
    assert chips[1]["t"] == 37.25
    assert 35.96 + 0.3 < chips[0]["t"] < 37.94          # слово «посты» после окна — нажатие внутри окна


def test_unknown_logo_gives_a_clear_message():
    with pytest.raises(S.SpecError, match="нет логотипа «zzz»"):
        _res([{"type": "step", "n": 1, "start": 3.4, "title": "Т", "chips": [{"text": "x", "logo": "zzz"}]}])


def test_example_spec_resolves_on_the_real_words_of_the_test_reel():
    r = S.resolve(S.load(EXAMPLE), WORDS, DUR)
    ids = [s.id for s in r.scenes]
    assert ids[0].startswith("hook") and ids[-1].startswith("cta")
    assert [s.type for s in r.scenes].count("step") == 10
    assert {"phone", "week", "money", "pipe", "pill"} <= {s.type for s in r.scenes}
    for a, b in zip(r.scenes, r.scenes[1:]):
        assert a.end == b.start                           # сцены без дыр
    cta = r.scenes[-1]
    assert 61.0 < cta.data["press_t"] < 63.0              # «Клод» в призыве
    assert r.fixes["лотку"] == "к" and r.context_fixes["привязываю|к"] == "Клод"
