"""Скачивание логотипов (узкий список источников) и свои сцены `custom`. Без сети: подставной opener."""
import io
import json
import urllib.error
from pathlib import Path

import pytest

from integrations.montage import config, custom, logos, overlay
from integrations.montage import spec as S

ROOT = Path(__file__).resolve().parents[1]
WORDS = json.loads((ROOT / "tests" / "fixtures" / "montage_words_v2.json").read_text(encoding="utf-8"))
GOOD_SVG = (config.ASSETS / "logos" / "gmail.svg").read_bytes()


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(routes):
    """routes: {часть адреса: bytes | HTTP-код}. Запоминает, что запрашивали."""
    calls = []

    def opener(req, timeout=0):
        url = req.full_url
        calls.append(url)
        for part, val in routes.items():
            if part in url:
                if isinstance(val, int):
                    raise urllib.error.HTTPError(url, val, "x", {}, None)
                return Resp(val)
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)
    opener.calls = calls
    return opener


# ---------------------------------------------------------------- логотипы
def test_only_two_github_hosts_are_allowed():
    assert logos.check_url("https://raw.githubusercontent.com/glincker/thesvg/main/x.svg")
    for bad in ("https://evil.example.com/a.svg", "http://raw.githubusercontent.com/a.svg", "file:///C:/secret"):
        with pytest.raises(logos.LogoError):
            logos.check_url(bad)


def test_slug_is_validated_before_any_request():
    for bad in ("../etc", "Notion", "a b", "x/y", "", "-x"):
        with pytest.raises(logos.LogoError):
            logos.candidates(bad)
    op = fake_opener({})
    with pytest.raises(logos.LogoError):
        logos.fetch("../../x", opener=op)
    assert op.calls == []                                        # плохое имя — ни одного запроса


def test_real_logo_files_pass_the_sanitizer():
    for f in (config.ASSETS / "logos").glob("*.svg"):
        logos.sanitize_svg(f.read_bytes())
    logos.sanitize_svg((config.ASSETS / "claude-icon.svg").read_bytes())


@pytest.mark.parametrize("evil", [
    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    b"<svg xmlns='http://www.w3.org/2000/svg' onload='x()'></svg>",
    b"<svg xmlns='http://www.w3.org/2000/svg'><image href='http://evil/x.png'/></svg>",
    b"<svg xmlns='http://www.w3.org/2000/svg'><use xlink:href='http://evil/a.svg#x'/></svg>",
    b"<svg xmlns='http://www.w3.org/2000/svg'><rect style='fill:url(http://evil/x)'/></svg>",
    b"<!DOCTYPE svg [<!ENTITY a 'b'>]><svg xmlns='http://www.w3.org/2000/svg'/>",
    b"<svg xmlns='http://www.w3.org/2000/svg'><foreignObject><div/></foreignObject></svg>",
    b"<html><body>not svg</body></html>",
])
def test_sanitizer_rejects_dangerous_or_non_svg(evil):
    with pytest.raises(logos.LogoError):
        logos.sanitize_svg(evil)


def test_fetch_writes_file_records_source_and_falls_back_to_second_catalog(tmp_path):
    op = fake_opener({"/glincker/thesvg/": 404, "/gilbarbara/logos/main/logos/notion.svg": GOOD_SVG})
    out = logos.fetch("notion", dest=tmp_path, opener=op)
    assert out == tmp_path / "notion.svg" and out.read_bytes() == GOOD_SVG
    src = json.loads((tmp_path / "_sources.json").read_text(encoding="utf-8"))
    assert "gilbarbara/logos" in src["notion"]
    assert all(u.startswith("https://raw.githubusercontent.com/") for u in op.calls)


def test_fetch_renames_with_as_and_reports_not_found(tmp_path):
    op = fake_opener({"/glincker/thesvg/main/public/icons/gmail/default.svg": GOOD_SVG})
    assert logos.fetch("gmail", as_name="mail", dest=tmp_path, opener=op).name == "mail.svg"
    with pytest.raises(logos.LogoError, match="не найден"):
        logos.fetch("nothing-here", dest=tmp_path, opener=fake_opener({}))


def test_fetch_refuses_oversized_file(tmp_path):
    big = b"<svg xmlns='http://www.w3.org/2000/svg'>" + b" " * (logos.MAX_BYTES + 10) + b"</svg>"
    with pytest.raises(logos.LogoError, match="больше"):
        logos.fetch("big", dest=tmp_path, opener=fake_opener({"/thesvg/": big, "/logos/": big}))


def test_search_merges_both_catalogs_and_puts_exact_match_first(tmp_path):
    tree = lambda names: json.dumps({"tree": [{"path": n} for n in names]}).encode()
    op = fake_opener({"/glincker/thesvg/git/trees": tree(["notion", "notion-badge", "slack"]),
                      "/gilbarbara/logos/git/trees": tree(["notion.svg", "notion-icon.svg", "figma.svg"])})
    hits = logos.search("notion", opener=op, dest=tmp_path)
    assert hits[0] == "notion" and set(hits) == {"notion", "notion-badge", "notion-icon"}
    assert (tmp_path / "_index.json").exists()
    n_calls = len(op.calls)
    logos.search("figma", opener=op, dest=tmp_path)
    assert len(op.calls) == n_calls                              # индекс из кэша, второй раз сети нет


def test_spec_finds_a_downloaded_logo_in_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGO_CACHE", tmp_path)
    (tmp_path / "zzz-brand.svg").write_bytes(GOOD_SVG)
    assert S.logo_path("zzz-brand") == tmp_path / "zzz-brand.svg"
    with pytest.raises(S.SpecError, match="logos search"):
        S.logo_path("not-downloaded-yet")


# ---------------------------------------------------------------- свои сцены
GOOD_HTML = ("<div class='abs' style='position:absolute;left:100px;top:300px;width:800px;height:200px;background:#fff' data-a='pop' data-d='0.3'>"
             "<img src='{{logo:gmail}}' style='width:40px'><svg width='40' height='40'><circle cx='20' cy='20' r='18'/></svg>"
             "<span data-word='созвон' style='font-family:G'>созвон</span></div>")


@pytest.mark.parametrize("bad,msg", [
    ("<script>x()</script>", "нельзя <script>"),
    ("<img src='x.png'>", "внешние адреса"),
    ("<div onclick='x()'>", "обработчики"),
    ("<div style='background:url(http://evil/x.png)'>", "url"),
    ("<a href='https://evil.com'>x</a>", "внешние адреса"),
    ("<div style='@import url(x)'>", "@import"),
    ("<iframe src='x'></iframe>", "нельзя <iframe>"),
    ("<div>https://evil.com/steal?x=1</div>", "адреса в интернет"),
])
def test_custom_html_sieve_rejects_scripts_images_and_network(bad, msg):
    with pytest.raises(S.SpecError, match=msg):
        custom.sanitize(bad)


def test_custom_accepts_layout_html_inline_svg_and_fonts():
    assert custom.sanitize(GOOD_HTML) == GOOD_HTML


def test_custom_process_resolves_logo_placeholder_and_spoken_word():
    out = custom.process(GOOD_HTML + "<div style=\"background:url({{logo:gmail}})\"></div>", WORDS, 9.1)
    assert "data-t='10.88'" in out and "data-word" not in out
    assert "file:///" in out and "gmail.svg" in out and "{{" not in out
    with pytest.raises(S.SpecError, match="нет слова «абракадабра»"):
        custom.process("<span data-word='абракадабра'></span>", WORDS, 0)
    with pytest.raises(S.SpecError, match="нет логотипа"):
        custom.process("<div style=\"background:url({{logo:no-such}})\"></div>", WORDS, 0)
    with pytest.raises(S.SpecError, match="неразобранные"):
        custom.process("<div>{{evil}}</div>", WORDS, 0)


def test_safe_zone_warnings_for_custom_html():
    assert custom.safe_warnings("<div style='position:absolute;left:100px;top:300px;width:800px;height:200px'>") == []
    w = custom.safe_warnings("<div style='position:absolute;left:100px;top:60px;width:800px;height:100px'>")
    assert any("шапкой" in x for x in w)
    w = custom.safe_warnings("<div style='position:absolute;left:100px;top:1100px;width:800px;height:300px'>")
    assert any("1248" in x for x in w)
    w = custom.safe_warnings("<div style='position:absolute;left:10px;top:300px;width:900px;height:100px'>")
    assert any("краю" in x for x in w)


def test_custom_file_must_live_in_outbox(tmp_path):
    bad = {"scenes": [{"type": "custom", "start": 0, "file": str(tmp_path / "x.html")}]}
    with pytest.raises(S.SpecError, match="outbox"):
        S.resolve(bad, WORDS, 65.99)
    with pytest.raises(S.SpecError, match="layout"):
        S.resolve({"scenes": [{"type": "custom", "start": 0, "layout": "weird", "html": "<div></div>"}]}, WORDS, 65.99)


def test_custom_scene_builds_into_overlay_with_right_zone_and_background(tmp_path):
    scenes = [{"type": "custom", "start": 0, "end": 3, "layout": "full", "html": GOOD_HTML},
              {"type": "custom", "start": 3, "end": 6, "layout": "split", "html": GOOD_HTML},
              {"type": "custom", "start": 6, "end": 9, "layout": "band", "html": GOOD_HTML}]
    res = S.resolve({"scenes": scenes}, WORDS, 65.99)
    assert [s.zone for s in res.scenes] == ["full", "split", "band"]
    tl = overlay.build(res, tmp_path)
    assert tl["full"] == [[0.0, 3.0]] and tl["split"] == [[3.0, 6.0]] and tl["band"] == [[6.0, 9.0]]
    html = (tmp_path / "overlay.html").read_text(encoding="utf-8")
    assert "data-t='10.88'" in html or "data-t='" in html
    assert {m["type"] for m in tl["scenes"]} == {"custom"}
    assert tl["warnings"] == []


def test_example_custom_scene_passes_the_sieve_and_builds(tmp_path):
    html = (config.HERE / "examples" / "custom-telegram-screen.html").read_text(encoding="utf-8")
    assert not any(ch in html for ch in "✂📝🎞")                  # эмодзи в headless-браузере дают чужие глифы
    res = S.resolve({"scenes": [{"type": "custom", "start": 3.4, "end": 9.1, "layout": "full", "html": html}]}, WORDS, 65.99)
    tl = overlay.build(res, tmp_path)
    assert tl["warnings"] == [] and tl["full"] == [[3.4, 9.1]]
    page = (tmp_path / "overlay.html").read_text(encoding="utf-8")
    import re
    for sec in ("6.04", "6.66", "7.28"):                                                        # календарь, почту, новости
        assert re.search(rf"data-t=[\"']{sec}[\"']", page), sec


def test_preview_zone_picks_the_layout_of_the_moment():
    from integrations.montage import preview
    tl = {"split": [[0, 6]], "band": [[33, 36]], "full": [[6, 9]]}
    assert [preview._zone(tl, x) for x in (1, 7, 34, 50)] == ["split", "full", "band", "plain"]


def test_html_comments_are_dropped_before_placeholders_are_resolved():
    out = custom.process("<!-- пример: {{logo:имя}} и data-word='x' --><div>ok</div>", WORDS, 0)
    assert out == "<div>ok</div>"


def test_nested_children_are_not_checked_against_the_frame():
    html = ("<div style='position:absolute;left:120px;top:760px;width:840px;height:240px'>"
            "<div style='position:absolute;left:50px;top:112px;width:740px;height:16px'></div></div>")
    assert custom.safe_warnings(html) == []
    html2 = ("<div style='position:absolute;left:120px;top:60px;width:840px;height:100px'></div>"
             "<div style='position:absolute;left:100px;top:300px;width:800px;height:100px'><i style='top:2px'></i></div>")
    assert len(custom.safe_warnings(html2)) == 1
