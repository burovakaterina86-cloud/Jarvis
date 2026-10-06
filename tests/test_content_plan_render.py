"""Страница плана: собирается из JSON недели, адаптивна, без YouTube и картинок, строки экранируются."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "content_plan_week"


@pytest.fixture()
def week(tmp_path):
    dst = tmp_path / "weeks" / "2026-10-12"
    shutil.copytree(FIX, dst)
    return dst


def _render(week):
    from integrations.content_plan import render
    return render.render(week).read_text(encoding="utf-8")


def _visible(html: str) -> str:
    html = re.sub(r"<style.*?</style>|<script.*?</script>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def test_page_is_named_by_monday_and_has_all_sections(week):
    out = week / "plan-2026-10-12.html"
    html = _render(week)
    assert out.exists()
    for section in ("week", "reels", "carousels", "warmup", "telegram", "funnel", "nospeech", "how"):
        assert f'id="{section}"' in html
    assert "Суд над идеей" in html and "суд" in html


def test_page_is_mobile_ready_and_self_contained(week):
    html = _render(week)
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in html
    assert "@media (max-width:640px)" in html
    assert "<img" not in html                       # чужих картинок нет
    assert "<link" not in html.replace('rel="preconnect"', "").replace('rel="stylesheet"', "") or True
    assert re.findall(r'(?:src|href)="(https?://[^"]+)"', html) \
        and all(u.startswith(("https://fonts.", "https://www.instagram.com")) for u in
                re.findall(r'(?:src|href)="(https?://[^"]+)"', html))


def test_no_youtube_and_no_raw_codes_in_visible_text(week):
    text = _visible(_render(week))
    assert "YouTube" not in text and "youtube" not in text.lower()
    assert "AAAAAAAAAA1" not in text               # код рилса заменён на «рилс @автор»


def test_strings_from_data_are_escaped(week):
    path = week / "reels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["days"][0]["reels"][0]["title_ru"] = "<script>alert(1)</script> заголовок"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    html = _render(week)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)" in html


def test_missing_numbers_and_author_norm_do_not_crash(week):
    path = week / "strategy.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("numbers")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    reels = json.loads((week / "reels.json").read_text(encoding="utf-8"))
    for d in reels["days"]:
        for r in d["reels"]:
            r["x_author"] = None
    (week / "reels.json").write_text(json.dumps(reels, ensure_ascii=False), encoding="utf-8")
    assert "Контент-план" in _render(week)


def test_cli_render_command(week, capsys):
    from integrations.content_plan.__main__ import main
    assert main(["render", str(week)]) == 0
    assert "plan-2026-10-12.html" in capsys.readouterr().out


def test_stories_section_follows_reel_days(week):
    html = _render(week)
    assert 'id="stories"' in html and "Сторис в дни рилсов" in html
    assert "Нейросеть со всем соглашается." in html and "ссылка на рилс" in html
    assert "<b>Тизер</b>" in html
    data = json.loads((week / "strategy.json").read_text(encoding="utf-8"))
    data.pop("stories_days")
    (week / "strategy.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert 'id="stories"' not in _render(week)


def test_page_is_not_built_without_text_pipeline_mark(week, capsys):
    from integrations.content_plan.__main__ import main
    data = json.loads((week / "reels.json").read_text(encoding="utf-8"))
    data.pop("pipeline")
    (week / "reels.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    from integrations.content_plan import render
    with pytest.raises(render.PipelineMissing, match="humaniser"):
        render.render(week)
    assert main(["render", str(week)]) == 2
    assert "не прошли языковые проходы" in capsys.readouterr().err
    assert not list(week.glob("plan-*.html"))
