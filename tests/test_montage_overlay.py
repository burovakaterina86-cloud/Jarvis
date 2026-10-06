"""Сборка страницы оверлея, окна раскладки и безопасные зоны Instagram. Без браузера и ffmpeg."""
import json
import re
from pathlib import Path

import pytest

from integrations.montage import config, overlay
from integrations.montage import spec as S

ROOT = Path(__file__).resolve().parents[1]
WORDS = json.loads((ROOT / "tests" / "fixtures" / "montage_words_v2.json").read_text(encoding="utf-8"))
EXAMPLE = ROOT / "integrations" / "montage" / "examples" / "10-sistem.spec.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    work = tmp_path_factory.mktemp("overlay")
    res = S.resolve(S.load(EXAMPLE), WORDS, 65.99)
    tl = overlay.build(res, work)
    return res, tl, (work / "overlay.html").read_text(encoding="utf-8"), work


def test_files_and_scene_ids(built):
    res, tl, html, work = built
    assert (work / "timeline.json").exists()
    for sc in res.scenes:
        assert f"id='{sc.id}'" in html
    assert len(tl["scenes"]) == len(res.scenes)
    assert "%%" not in html                                    # все подстановки шаблона сделаны


def test_layout_windows_are_consistent(built):
    res, tl, _, _ = built
    kinds = {s.id: s.type for s in res.scenes}
    assert len(tl["split"]) == sum(1 for t in kinds.values() if t in {"hook", "step"}) == 11
    assert len(tl["band"]) == 3                                # две плашки и призыв
    assert len(tl["full"]) == 4
    flat = [w for key in ("split", "band", "full") for w in tl[key]]
    flat.sort()
    for (a1, b1), (a2, b2) in zip(flat, flat[1:]):
        assert b1 <= a2 + 1e-9                                 # окна раскладок не пересекаются
    assert flat[0][0] == 0 and flat[-1][1] == tl["dur"]


def test_js_types_and_cta_press_time(built):
    _, tl, _, _ = built
    types = {m["type"] for m in tl["scenes"]}
    assert types == {"hook", "panel", "phone", "week", "money", "pipe", "pill", "cta"}
    cta = [m for m in tl["scenes"] if m["type"] == "cta"][0]
    assert 61.0 < cta["press"] < 63.0
    assert [m["n"] for m in tl["scenes"] if m["type"] == "panel"] == list(range(1, 11))


def test_every_chip_has_a_press_time_inside_its_scene(built):
    res, _, html, _ = built
    for sc in res.scenes:
        if sc.type != "step":
            continue
        for c in sc.data["chips"]:
            if not c.get("arrow"):
                assert sc.start < c["t"] < sc.end, (sc.id, c)
                assert f"data-t='{c['t']}'" in html


def test_nothing_sits_under_the_instagram_header(built):
    """Всё, что не фон, начинается ниже шапки Instagram (115 px)."""
    _, _, html, _ = built
    offenders = []
    for m in re.finditer(r"<div class='?([^'>]*)'? style='([^']*)'", html):
        classes, style = m.groups()
        top = re.search(r"(?:^|;)top:(\d+)px", style)
        if not top or int(top.group(1)) >= config.SAFE_TOP:
            continue
        if "left:0;top:0" in style.replace(" ", "") or "fsbg" in classes:
            continue                                           # фоны панели и экрана
        offenders.append((classes, top.group(1)))
    assert not offenders, offenders


def test_full_screen_content_stays_above_caption_line_and_inside_side_margins(built):
    _, _, html, _ = built
    for m in re.finditer(r"left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px", html):
        left, top, w, h = map(int, m.groups())
        if w >= 1000 or h >= 1900:
            continue                                           # фоны
        assert left >= config.SAFE_SIDE - 1 and left + w <= 1080 - config.SAFE_SIDE + 1, m.group(0)
        assert top + h <= config.SAFE_CAPTION + 2, m.group(0)


def test_missing_data_for_logo_is_a_spec_error_before_render(tmp_path):
    bad = {"scenes": [{"type": "money", "start": 0, "left": "no-such-logo", "rows": []}]}
    with pytest.raises(S.SpecError, match="нет логотипа"):
        S.resolve(bad, WORDS, 65.99)
