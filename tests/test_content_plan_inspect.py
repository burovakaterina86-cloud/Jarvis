"""Просмотр идей не исполняет произвольный код и не покидает weeks."""
import json
import pytest
from integrations.content_plan import inspect as viewer


@pytest.fixture
def week(tmp_path, monkeypatch):
    weeks = tmp_path / "weeks"
    folder = weeks / "test-week"
    folder.mkdir(parents=True)
    monkeypatch.setattr(viewer, "WEEKS", weeks)
    (folder / "reels.json").write_text(json.dumps({"week": "2026-10-19", "days": [{"date": "2026-10-19", "reels":
        [{"title_ru": "Идея один", "hook": "Начало"}, {"title_ru": "Идея два"}]}]}, ensure_ascii=False), encoding="utf-8")
    return folder


def test_bounded_inspection_returns_ideas_without_changing_file(week):
    before = (week / "reels.json").read_bytes()
    result = viewer.inspect_week(week, limit=1)
    assert result["status"] == "ok" and result["ideas"] == [{"date": "2026-10-19", "title": "Идея один", "hook": "Начало"}]
    assert (week / "reels.json").read_bytes() == before


@pytest.mark.parametrize("name", ["../escape", "C:/Windows", "a/b", ""])
def test_cli_refuses_paths_instead_of_week_name(week, name):
    assert viewer.main(["--week", name]) == 2


@pytest.mark.parametrize("limit", [0, 21])
def test_inspection_refuses_invalid_limit(week, limit):
    with pytest.raises(ValueError):
        viewer.inspect_week(week, limit=limit)


def test_empty_and_broken_json_are_distinct(week):
    (week / "reels.json").write_text('{"days": []}', encoding="utf-8")
    assert viewer.inspect_week(week)["status"] == "empty"
    (week / "reels.json").write_text('{broken', encoding="utf-8")
    assert viewer.main(["--week", week.name]) == 2


def test_week_outside_allowed_directory_is_refused(week, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="weeks"):
        viewer.inspect_week(outside)


def test_standard_viewer_needs_no_arbitrary_script_approval(week):
    from tests.test_guard import REPO, decide, ev
    decision = decide(ev("Bash", command="python -m integrations.content_plan.inspect --week test-week --limit 3"), REPO)
    assert decision.action == "allow"
