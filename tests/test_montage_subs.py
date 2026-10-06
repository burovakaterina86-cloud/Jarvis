"""Правка слов распознавателя в субтитрах и положение строк. Без сети."""
from integrations.montage import config, subs

H = r"{\c&H004DD3FF}"
W = r"{\c&H00FFFFFF}"


def test_fix_word_keeps_highlight_tags_and_punctuation():
    text = f"Утренняя {H}сова.{W}\n"
    assert subs.fix_tokens(text, {"сова": "сводка"}) == f"Утренняя {H}сводка.{W}\n"


def test_fix_is_case_insensitive_for_lowercase_keys_and_ignores_other_words():
    assert subs.fix_tokens("в клод, которые", {"клод": "Клод"}) == "в Клод, которые"
    assert subs.fix_tokens("сова летит", {"сов": "x"}) == "сова летит"       # только слово целиком


def test_key_with_punctuation_is_exact():
    fixes = {"почты,": "почте,"}
    assert subs.fix_tokens("почты, он сам", fixes) == "почте, он сам"
    assert subs.fix_tokens("Разбор почты.", fixes) == "Разбор почты."          # без запятой — другое место


def test_context_fix_applies_only_after_the_given_previous_word():
    ctx = {"привязываю|к": "Клод"}
    assert subs.fix_tokens("Я привязываю к", {}, ctx) == "Я привязываю Клод"
    assert subs.fix_tokens("иду к дому", {}, ctx) == "иду к дому"


def test_number_of_words_is_never_changed():
    text = "я привязываю к лотку"
    out = subs.fix_tokens(text, {"лотку": "к"}, {"привязываю|к": "Клод"})
    assert out == "я привязываю Клод к" and len(out.split()) == len(text.split())


def test_finalize_places_every_line_at_the_bottom_with_outline(tmp_path):
    src = tmp_path / "a.ass"
    src.write_text("[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Main,,0,0,0,,{\\c&H004DD3FF}клод{\\c&H00FFFFFF} тут\n", encoding="utf-8")
    out = tmp_path / "b.ass"
    n = subs.finalize(src, out, fixes={})
    line = [x for x in out.read_text(encoding="utf-8").splitlines() if x.startswith("Dialogue")][0]
    assert f"\\an2\\pos(540,{config.SUB_Y})" in line and "\\bord7" in line and "\\3a&H00&" in line
    assert "Клод" in line and n == 1                     # типовая замена из data/word_fixes.json


def test_subtitle_line_is_below_the_shoulders_and_above_instagram_bottom_bar():
    assert 1640 < config.SUB_Y <= config.SAFE_BOTTOM_UI - 30   # плечи ~1640 (замер), панель Instagram с 1760
    assert config.SUB_MAX_CHARS == 24
