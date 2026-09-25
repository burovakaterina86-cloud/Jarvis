"""Генерация картинок для лидмагнитов через kie.ai (GPT Image 2) — без сети, HTTP подменён."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "skills" / "lead-magnet-agent" / "scripts" / "kie_image.py"


def load():
    spec = importlib.util.spec_from_file_location("kie_image", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_key_names_the_variable():
    kie = load()
    with pytest.raises(kie.KieError) as excinfo:
        kie.require_key(env={})
    assert "KIE_API_KEY" in str(excinfo.value)


def test_task_body_uses_gpt_image_2():
    kie = load()
    body = kie.task_body("кот в очках", aspect_ratio="3:4", resolution="2K")
    assert body == {
        "model": "gpt-image-2-text-to-image",
        "input": {"prompt": "кот в очках", "aspect_ratio": "3:4", "resolution": "2K"},
    }


def test_generate_polls_until_success_and_downloads(tmp_path):
    kie = load()
    calls = []
    states = iter(["waiting", "generating", "success"])

    def fake_api(method, path, key, body=None):
        calls.append((method, path))
        if method == "POST":
            return {"code": 200, "data": {"taskId": "t1"}}
        state = next(states)
        data = {"state": state}
        if state == "success":
            data["resultJson"] = json.dumps({"resultUrls": ["https://x/img.png"]})
        return {"code": 200, "data": data}

    saved = []
    out = kie.generate(
        "обложка", tmp_path / "cover.png", key="k",
        api=fake_api, download=lambda url, dest: saved.append((url, dest)), sleep=lambda s: None,
    )
    assert out == tmp_path / "cover.png"
    assert saved == [("https://x/img.png", tmp_path / "cover.png")]
    assert calls[0] == ("POST", "/api/v1/jobs/createTask")
    assert calls[1][1] == "/api/v1/jobs/recordInfo?taskId=t1"


def test_generate_reports_failure():
    kie = load()

    def fake_api(method, path, key, body=None):
        if method == "POST":
            return {"code": 200, "data": {"taskId": "t1"}}
        return {"code": 200, "data": {"state": "fail", "failMsg": "content policy"}}

    with pytest.raises(kie.KieError) as excinfo:
        kie.generate("x", Path("x.png"), key="k", api=fake_api, download=None, sleep=lambda s: None)
    assert "content policy" in str(excinfo.value)


def test_create_task_error_is_reported():
    kie = load()

    def fake_api(method, path, key, body=None):
        return {"code": 402, "msg": "insufficient credits"}

    with pytest.raises(kie.KieError) as excinfo:
        kie.generate("x", Path("x.png"), key="k", api=fake_api, download=None, sleep=lambda s: None)
    assert "insufficient credits" in str(excinfo.value)
