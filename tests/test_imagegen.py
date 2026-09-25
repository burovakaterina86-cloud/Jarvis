"""Генерация картинок: сначала Codex по её подписке ChatGPT, лимит кончился — kie.ai. Без сети."""
import json
from pathlib import Path

import pytest

from integrations.visuals import imagegen as ig


# --- Codex ---

def events(*items):
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in items)


LIMIT = events(
    {"type": "thread.started", "thread_id": "th1"},
    {"type": "error", "message": "You’ve hit your usage limit. Upgrade to Pro ... try again at Sep 27th, 2026 10:19 AM."},
    {"type": "turn.failed", "error": {"message": "You’ve hit your usage limit."}},
)


def test_parse_events_finds_thread_and_error():
    thread, error = ig.parse_codex_events(LIMIT)
    assert thread == "th1"
    assert "usage limit" in error


def test_parse_events_ignores_noise_lines():
    thread, error = ig.parse_codex_events("Reading additional input\n" + events(
        {"type": "thread.started", "thread_id": "th2"}, {"type": "turn.completed"}))
    assert (thread, error) == ("th2", None)


def test_codex_limit_raises_limit_error(tmp_path):
    with pytest.raises(ig.CodexLimit):
        ig.generate_codex("кот", tmp_path / "a.png", run=lambda cmd, cwd: (1, LIMIT), home=tmp_path)


def test_codex_saved_file_in_place(tmp_path):
    dest = tmp_path / "a.png"

    def run(cmd, cwd):
        assert "$imagegen" in cmd[-1] and "a.png" in cmd[-1] and "3:4" in cmd[-1]
        dest.write_bytes(b"png")
        return 0, events({"type": "thread.started", "thread_id": "t"}, {"type": "turn.completed"})

    assert ig.generate_codex("кот", dest, run=run, home=tmp_path) == dest


def test_codex_gets_absolute_folder_for_relative_dest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def run(cmd, cwd):
        seen["C"], seen["cwd"] = cmd[cmd.index("-C") + 1], cwd
        (tmp_path / "imgs" / "a.png").write_bytes(b"png")
        return 0, ""

    ig.generate_codex("кот", Path("imgs/a.png"), run=run, home=tmp_path)
    assert Path(seen["C"]).is_absolute() and Path(seen["C"]) == tmp_path / "imgs"


def test_codex_image_picked_from_generated_images(tmp_path):
    dest = tmp_path / "out" / "a.png"
    dest.parent.mkdir()
    gen = tmp_path / "generated_images" / "t9"
    gen.mkdir(parents=True)
    (gen / "exec-1.png").write_bytes(b"img")
    out = ig.generate_codex("кот", dest, home=tmp_path,
                            run=lambda cmd, cwd: (0, events({"type": "thread.started", "thread_id": "t9"})))
    assert out == dest and dest.read_bytes() == b"img"


def test_codex_without_image_is_error(tmp_path):
    with pytest.raises(ig.ImageGenError):
        ig.generate_codex("кот", tmp_path / "a.png", home=tmp_path,
                          run=lambda cmd, cwd: (0, events({"type": "thread.started", "thread_id": "t"})))


# --- kie.ai ---

def test_missing_kie_key_names_the_variable():
    with pytest.raises(ig.ImageGenError) as excinfo:
        ig.require_kie_key(env={})
    assert "KIE_API_KEY" in str(excinfo.value)


def test_kie_chains_by_task():
    assert ig.KIE_TEXT == ("grok-imagine-image-2-0/text-to-image", "gpt-image-2-5-flare-text-to-image")
    assert ig.KIE_REF == ("gpt-image-2-5-flare-image-to-image", "nano-banana-2")
    assert ig.KIE_REF_RESOLUTION == "2K"


def test_grok_body_has_no_resolution_and_snaps_ratio():
    body = ig.kie_task_body("grok-imagine-image-2-0/text-to-image", "кот", aspect_ratio="4:5", resolution="2K")
    assert body["input"]["aspect_ratio"] == "2:3"
    assert "resolution" not in body["input"]
    assert body["input"]["prompt"].startswith("кот") and ig.REALISM in body["input"]["prompt"]


def test_ref_bodies_carry_references_and_keep_face():
    gpt = ig.kie_task_body("gpt-image-2-5-flare-image-to-image", "она за столом", "4:5", "2K", ["u1"])
    assert gpt["input"]["input_urls"] == ["u1"] and gpt["input"]["resolution"] == "2K"
    assert ig.KEEP_FACE in gpt["input"]["prompt"]
    nano = ig.kie_task_body("nano-banana-2", "она за столом", "4:5", "2K", ["u1"])
    assert nano["input"]["image_input"] == ["u1"] and nano["input"]["output_format"] == "png"


def test_unsupported_ratio_snaps_to_nearest():
    body = ig.kie_task_body("gpt-image-2-5-flare-text-to-image", "кот", aspect_ratio="4:5")
    assert body["input"]["aspect_ratio"] == "3:4"
    assert "output_format" not in body["input"]


def test_codex_prompt_asks_for_real_photo():
    assert ig.REALISM in ig.codex_prompt("кот", "a.png", "4:5")
    assert "Not an illustration" in ig.REALISM


def _api_first_fails(models):
    def api(method, path, key, body=None):
        if path == ig.KIE_UPLOAD:
            assert body["base64Data"].startswith("data:image/png;base64,")
            return {"code": 200, "data": {"downloadUrl": "https://kie/ref.png"}}
        if method == "POST":
            models.append(body)
            if len(models) == 1:
                return {"code": 500, "msg": "overloaded"}
            return {"code": 200, "data": {"taskId": "t2"}}
        return {"code": 200, "data": {"state": "success", "resultJson": json.dumps({"resultUrls": ["u"]})}}
    return api


def test_kie_without_refs_grok_then_gpt(tmp_path):
    bodies = []
    out = ig.generate_kie("кот", tmp_path / "a.png", key="k", api=_api_first_fails(bodies),
                          download=lambda u, d: None, sleep=lambda s: None)
    assert out == tmp_path / "a.png"
    assert [b["model"] for b in bodies] == list(ig.KIE_TEXT)


def test_kie_with_refs_uploads_and_goes_gpt_then_nano_in_2k(tmp_path):
    ref = tmp_path / "me.png"
    ref.write_bytes(b"png")
    bodies = []
    ig.generate_kie("она за столом", tmp_path / "a.png", resolution="1K", refs=[ref], key="k",
                    api=_api_first_fails(bodies), download=lambda u, d: None, sleep=lambda s: None)
    assert [b["model"] for b in bodies] == list(ig.KIE_REF)
    assert bodies[1]["input"]["image_input"] == ["https://kie/ref.png"]
    assert bodies[1]["input"]["resolution"] == "2K"


def test_codex_gets_reference_images(tmp_path):
    ref = tmp_path / "me.png"
    ref.write_bytes(b"png")
    dest = tmp_path / "a.png"

    def run(cmd, cwd):
        assert f"--image={ref.resolve()}" in cmd
        assert ig.KEEP_FACE in cmd[-1]
        dest.write_bytes(b"png")
        return 0, ""

    assert ig.generate_codex("она", dest, refs=[ref], run=run, home=tmp_path) == dest


def test_kie_polls_until_success_and_downloads(tmp_path):
    calls, states = [], iter(["waiting", "generating", "success"])

    def api(method, path, key, body=None):
        calls.append((method, path))
        if method == "POST":
            return {"code": 200, "data": {"taskId": "t1"}}
        state = next(states)
        data = {"state": state}
        if state == "success":
            data["resultJson"] = json.dumps({"resultUrls": ["https://x/img.png"]})
        return {"code": 200, "data": data}

    saved = []
    out = ig.generate_kie("обложка", tmp_path / "c.png", key="k", api=api,
                          download=lambda url, dest: saved.append((url, dest)), sleep=lambda s: None)
    assert out == tmp_path / "c.png"
    assert saved == [("https://x/img.png", tmp_path / "c.png")]
    assert calls[0] == ("POST", "/api/v1/jobs/createTask")  # первой пошла Nano Banana 2
    assert calls[1][1] == "/api/v1/jobs/recordInfo?taskId=t1"


def test_kie_failure_and_create_error_are_reported():
    def failing(method, path, key, body=None):
        if method == "POST":
            return {"code": 200, "data": {"taskId": "t1"}}
        return {"code": 200, "data": {"state": "fail", "failMsg": "content policy"}}

    with pytest.raises(ig.ImageGenError, match="content policy"):
        ig.generate_kie("x", Path("x.png"), key="k", api=failing, download=None, sleep=lambda s: None)
    with pytest.raises(ig.ImageGenError, match="insufficient credits"):
        ig.generate_kie("x", Path("x.png"), key="k", sleep=lambda s: None, download=None,
                        api=lambda m, p, k, b=None: {"code": 402, "msg": "insufficient credits"})


# --- порядок: Codex, потом kie.ai ---

def test_codex_first(tmp_path):
    r = ig.generate("кот", tmp_path / "a.png",
                    codex=lambda p, d, ratio, refs=(): d, kie=lambda p, d, ratio, res, refs=(): pytest.fail("kie не нужен"))
    assert (r.path, r.provider, r.note) == (tmp_path / "a.png", "codex", "")


def test_falls_back_to_kie_on_codex_limit(tmp_path):
    def codex(p, d, ratio, refs=()):
        raise ig.CodexLimit("usage limit, try again at Sep 27th")

    r = ig.generate("кот", tmp_path / "a.png", codex=codex, kie=lambda p, d, ratio, res, refs=(): d)
    assert r.provider == "kie"
    assert "лимит" in r.note


def test_falls_back_to_kie_when_codex_broken(tmp_path):
    def codex(p, d, ratio, refs=()):
        raise ig.ImageGenError("codex не установлен")

    r = ig.generate("кот", tmp_path / "a.png", codex=codex, kie=lambda p, d, ratio, res, refs=(): d)
    assert r.provider == "kie" and "codex не установлен" in r.note


def test_only_kie_skips_codex(tmp_path):
    r = ig.generate("кот", tmp_path / "a.png", only="kie",
                    codex=lambda p, d, ratio, refs=(): pytest.fail("codex не нужен"), kie=lambda p, d, ratio, res, refs=(): d)
    assert r.provider == "kie"


def test_both_fail_reports_both(tmp_path):
    def codex(p, d, ratio, refs=()):
        raise ig.CodexLimit("usage limit")

    def kie(p, d, ratio, res, refs=()):
        raise ig.ImageGenError("нет ключа KIE_API_KEY в .env")

    with pytest.raises(ig.ImageGenError) as excinfo:
        ig.generate("кот", tmp_path / "a.png", codex=codex, kie=kie)
    assert "usage limit" in str(excinfo.value) and "KIE_API_KEY" in str(excinfo.value)
