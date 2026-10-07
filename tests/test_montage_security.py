"""Безопасность страницы оверлея монтажа (ревью 2026-10-07): сито, числа в атрибутах, доступ браузера к файлам."""
import json
from pathlib import Path

import pytest

from integrations.montage import config, custom, overlay, render
from integrations.montage import spec as S


@pytest.mark.parametrize("html", [
    "<svg/onload=alert(1)></svg>",                                  # обработчик без пробела перед on…
    "<div\tonclick=x>t</div>",
    "<img srcset='{{logo:claude}} 1x, \\\\host\\share\\a.png 2x'>",
    "<div style=\"background:image-set('a.png' 1x)\">t</div>",
    "<div style=\"width:expression(alert(1))\">t</div>",
])
def test_custom_sieve_rejects_known_bypasses(html):
    with pytest.raises(S.SpecError):
        custom.sanitize(html)


def test_custom_sieve_still_accepts_normal_markup():
    html = ("<div style='left:70px;top:300px;width:900px;font-size:40px'>Привет <b>мир</b></div>"
            "<svg viewBox='0 0 8 8'><circle cx='4' cy='4' r='3'/></svg>")
    assert custom.sanitize(html) == html


def test_example_custom_scene_passes_the_sieve():
    example = Path(config.HERE) / "examples" / "custom-telegram-screen.html"
    assert custom.sanitize(example.read_text(encoding="utf-8"))


def test_numeric_fields_cannot_inject_markup():
    with pytest.raises(ValueError):
        overlay.num("1' onmouseover='x")
    with pytest.raises(ValueError):
        overlay.num(float("nan"))
    assert overlay.num(21.0) == "21.0" and overlay.num(150) == "150" and overlay.num("2.5") == "2.5"
    assert "'" not in overlay.attr("a' onload='x") and "&#x27;" in overlay.attr("a'b")


def test_browser_may_read_only_montage_folders(tmp_path):
    page = tmp_path / "work" / "overlay.html"
    roots = render.allowed_roots(page)
    assert config.ASSETS in roots and config.LOGO_CACHE in roots and (tmp_path / "work").resolve() in roots
    env = render.env_for(page, tmp_path / "frames", 10)
    assert json.loads(env["MONTAGE_ALLOW"]) == [str(p) for p in roots]
    assert not any("state" in Path(p).parts or "secrets" in Path(p).parts for p in roots)


def test_render_script_blocks_everything_but_data_and_allowed_files():
    mjs = (config.TEMPLATES / "render.mjs").read_text(encoding="utf-8")
    assert "setRequestInterception(true)" in mjs and "MONTAGE_ALLOW" in mjs and "blockedbyclient" in mjs
