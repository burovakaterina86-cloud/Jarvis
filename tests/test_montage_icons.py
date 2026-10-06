"""Иконки плашек: набор, подбор по смыслу, явное и отключённое, подстановка в своих сценах. Без сети и браузера."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from integrations.montage import custom, icons, overlay
from integrations.montage import spec as S

ROOT = Path(__file__).resolve().parents[1]
WORDS = json.loads((ROOT / "tests" / "fixtures" / "montage_words_v2.json").read_text(encoding="utf-8"))
EXAMPLE = ROOT / "integrations" / "montage" / "examples" / "10-sistem.spec.json"


@pytest.mark.parametrize("name", icons.NAMES)
def test_every_icon_is_valid_svg_with_current_color(name):
    root = ET.fromstring(icons.icon_svg(name, 40))
    assert root.tag.endswith("svg") and root.get("stroke") == "currentColor"      # цвет от текста плашки
    assert root.get("viewBox") == "0 0 24 24" and root.get("width") == "40"
    assert len(list(root)) >= 1


@pytest.mark.parametrize("text,expected", [
    ("свою озвучку", "mic"), ("материалы", "folder"), ("анимацию", "sparkles"), ("созвон", "phone"), ("1 риск", "warning"),
    ("скриншоты", "image"), ("доходы", "chart"), ("что лучше", "lightbulb"), ("а что нет", "x"), ("заметки", "notebook"),
    ("без чувствительных данных", "shield"), ("промпт", "terminal"),
])
def test_icon_is_chosen_by_meaning(text, expected):
    assert icons.auto_icon(text) == expected


def test_no_confident_match_means_no_icon_and_short_stems_need_whole_words():
    assert icons.auto_icon("в 10 раз эффективнее") in {"chart", None}
    assert icons.auto_icon("абракадабра") is None
    assert icons.auto_icon("результат") is None             # «рез» — ножницы только как целое слово
    assert icons.auto_icon("кодовое слово") is None         # «код» — терминал только как целое слово
    assert icons.auto_icon("нет") == "x" and icons.auto_icon("интернет") is None


def test_placeholders_in_custom_html_become_inline_svg_with_size():
    out = icons.fill_placeholders("<b>{{icon:mic}}</b><i>{{icon:star|64}}</i>")
    assert out.count("<svg") == 2 and 'width="40"' in out and 'width="64"' in out
    with pytest.raises(ValueError, match="нет иконки"):
        icons.fill_placeholders("{{icon:nonexistent}}")


def test_custom_scene_accepts_icon_placeholders_and_rejects_unknown_ones():
    html = "<div style='position:absolute;left:100px;top:300px;width:800px;height:100px'>{{icon:gift|56}} подарок</div>"
    assert "<svg" in custom.process(html, WORDS, 0)
    with pytest.raises(S.SpecError, match="нет иконки"):
        custom.process("<div>{{icon:zzz}}</div>", WORDS, 0)


def _res(chips):
    return S.resolve({"scenes": [{"type": "step", "n": 1, "start": 3.4, "end": 7.7, "title": "Т", "chips": chips}]}, WORDS, 65.99)


def test_chips_get_automatic_icons_explicit_wins_null_disables_logo_beats_icon():
    r = _res([{"text": "календарь", "logo": "google-calendar"}, {"text": "созвон"}, {"text": "созвон", "icon": "star"},
              {"text": "созвон", "icon": None}, {"text": "что-то неясное"}])
    got = [c["icon"] for c in r.scenes[0].data["chips"]]
    assert got == [None, "phone", "star", None, None]


def test_unknown_explicit_icon_is_a_spec_error_with_the_list():
    with pytest.raises(S.SpecError, match="нет иконки «zzz».*mic"):
        _res([{"text": "x", "icon": "zzz"}])


def test_pill_gets_icon_too(tmp_path):
    r = S.resolve({"scenes": [{"type": "pill", "start": 0, "end": 3, "text": "без чувствительных данных"},
                              {"type": "pill", "start": 3, "end": 6, "text": "эту часть я разобрала", "icon": "gift"},
                              {"type": "pill", "start": 6, "end": 9, "text": "в 10 раз", "logo": "claude"}]}, WORDS, 65.99)
    assert [s.data["icon"] for s in r.scenes] == ["shield", "gift", None]
    overlay.build(r, tmp_path)
    html = (tmp_path / "overlay.html").read_text(encoding="utf-8")
    assert html.count("<svg width=\"56\"") == 2                # две пилюли с иконкой, третья — с логотипом


def test_example_spec_chips_render_with_icons(tmp_path):
    res = S.resolve(S.load(EXAMPLE), WORDS, 65.99)
    overlay.build(res, tmp_path)
    html = (tmp_path / "overlay.html").read_text(encoding="utf-8")
    assert html.count('<svg width="44"') >= 18                  # у большинства чипов шагов есть иконка
