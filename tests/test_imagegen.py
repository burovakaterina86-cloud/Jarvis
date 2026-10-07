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
        assert cwd != dest.parent and cmd[cmd.index("-C") + 1] == str(cwd)   # Codex пишет не в папку результата
        (cwd / "a.png").write_bytes(b"png")
        return 0, events({"type": "thread.started", "thread_id": "t"}, {"type": "turn.completed"})

    assert ig.generate_codex("кот", dest, run=run, home=tmp_path) == dest


def test_codex_gets_absolute_folder_for_relative_dest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def run(cmd, cwd):
        seen["C"], seen["cwd"] = cmd[cmd.index("-C") + 1], cwd
        (Path(cwd) / "a.png").write_bytes(b"png")
        return 0, ""

    ig.generate_codex("кот", Path("imgs/a.png"), run=run, home=tmp_path)
    assert Path(seen["C"]).is_absolute() and Path(seen["C"]) == Path(seen["cwd"])
    assert (tmp_path / "imgs" / "a.png").read_bytes() == b"png"


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
    assert ig.KIE_REF == ("nano-banana-2", "gpt-image-2-5-flare-image-to-image")
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


def test_kie_with_refs_uploads_and_goes_nano_then_gpt_in_2k(tmp_path):
    ref = tmp_path / "me.png"
    ref.write_bytes(b"png")
    bodies = []
    ig.generate_kie("она за столом", tmp_path / "a.png", resolution="1K", refs=[ref], key="k",
                    api=_api_first_fails(bodies), download=lambda u, d: None, sleep=lambda s: None)
    assert [b["model"] for b in bodies] == list(ig.KIE_REF)
    assert bodies[0]["input"]["image_input"] == ["https://kie/ref.png"]      # nano — первая
    assert bodies[1]["input"]["input_urls"] == ["https://kie/ref.png"]       # gpt — запасная
    assert bodies[1]["input"]["resolution"] == "2K"


def test_codex_gets_reference_images(tmp_path):
    ref = tmp_path / "me.png"
    ref.write_bytes(b"png")
    dest = tmp_path / "a.png"

    def run(cmd, cwd):
        assert f"--image={ref.resolve()}" in cmd
        assert ig.KEEP_FACE in cmd[-1]
        (cwd / "a.png").write_bytes(b"png")
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


def test_nano_banana_only_for_appearance_and_first_there():
    # самая дорогая — только для её внешности; по сходству она выбрала её основной (2026-09-25)
    assert "nano-banana-2" not in ig.KIE_TEXT and "nano-banana-2" not in ig.KIE_STYLE
    assert ig.KIE_REF[0] == "nano-banana-2"



def test_her_photos_are_never_strict_classic():
    # её слова 2026-09-25: «не делай слишком строгие фото со мной… одежда современная но не строгая»
    assert "never strict classic" in ig.KEEP_FACE
    body = ig.kie_task_body("gpt-image-2-5-flare-image-to-image", "она за столом", "4:5", "2K", ["u"])
    assert "never strict classic" in body["input"]["prompt"]


def test_hair_is_cool_beige_blonde():
    assert "cool beige ash blonde" in ig.KEEP_FACE


def test_style_refs_skip_face_and_realism_and_use_gpt_only(tmp_path):
    ref = tmp_path / "hand.png"
    ref.write_bytes(b"png")
    bodies = []

    def api(method, path, key, body=None):
        if path == ig.KIE_UPLOAD:
            return {"code": 200, "data": {"downloadUrl": "https://kie/hand.png"}}
        if method == "POST":
            bodies.append(body)
            return {"code": 200, "data": {"taskId": "t"}}
        return {"code": 200, "data": {"state": "success", "resultJson": json.dumps({"resultUrls": ["u"]})}}

    ig.generate_kie("напиши текст", tmp_path / "a.png", refs=[ref], style=True, key="k", api=api,
                    download=lambda u, d: None, sleep=lambda s: None)
    assert [b["model"] for b in bodies] == list(ig.KIE_STYLE)
    assert bodies[0]["input"]["prompt"] == "напиши текст"


def test_generate_routes_style_refs(tmp_path):
    seen = {}

    def codex(p, d, ratio, refs=(), raw=False):
        seen["raw"], seen["refs"] = raw, refs
        return d

    ig.generate("x", tmp_path / "a.png", style_refs=["s.png"], codex=codex, kie=lambda *a, **k: None)
    assert seen == {"raw": True, "refs": ["s.png"]}


def test_identity_lock_is_her_contract():
    for part in ("PRIMARY IDENTITY REFERENCE", "not like a similar woman", "Do not create her from a text",
                 "how the eyes are set", "hairline", "natural facial asymmetry", "skin tone", "moles, freckles",
                 "make her younger", "more symmetrical", "plastic or overly smooth", "make the face thinner",
                 "likeness always wins"):
        assert part in ig.IDENTITY_LOCK, part
    assert ig.KEEP_FACE.startswith(ig.IDENTITY_LOCK)


def test_identity_lock_has_her_sharpness_and_no_age_rule():
    # её правило 2026-09-25: возраст не добавлять, фигура та же, лицо ультра-резкое, без размытия и сглаживания
    for part in ("make her older", "add age", "body build and figure proportions", "strictly as in the reference",
                 "crystal-clear, ultra-sharp", "NO BLUR, NO SOFT FOCUS, NO SMOOTHING",
                 "Every pore, every eyebrow hair and eyelash"):
        assert part in ig.IDENTITY_LOCK, part
    assert "face is always in sharp focus" in ig.REALISM
    assert "the face is always in sharp focus" in ig.edit_prompt("background")


def test_edit_mode_edits_her_photo_not_regenerates(tmp_path):
    photo = tmp_path / "me.jpg"
    photo.write_bytes(b"x")
    seen = {}

    def codex(p, d, ratio, refs=(), raw=False):
        seen.update(prompt=p, refs=refs, raw=raw)
        return d

    ig.generate("светлый лавандовый фон", tmp_path / "a.png", refs=[photo], edit_scope="background only",
                codex=codex, kie=lambda *a, **k: None)
    assert seen["raw"] is True and seen["refs"] == [photo]
    assert "EDIT SCOPE - change ONLY: background only" in seen["prompt"]
    assert "Target: светлый лавандовый фон" in seen["prompt"]
    assert "Photorealistic:" not in seen["prompt"]


def test_edit_mode_without_photo_uses_her_main_photo_from_assets(tmp_path):
    seen = {}
    ig.generate("x", tmp_path / "a.png", edit_scope="background",
                codex=lambda p, d, r, refs=(), raw=False: seen.setdefault("refs", refs) and d,
                kie=lambda *a, **k: None)
    assert seen["refs"][0].name == "face-main-selfie-black.jpg"


def test_no_text_description_of_her_face():
    # её инструкция: не заменять фото описанием, не делать лицо худее/глаже
    for banned in ("slim and angular", "makeup", "narrow oval face"):
        assert banned not in ig.KEEP_FACE, banned


def test_no_identity_reference_no_generation(tmp_path):
    import pytest
    with pytest.raises(ig.NoIdentityReference):
        ig.require_identity([tmp_path / "нет.jpg"], root=tmp_path)      # ни переданных, ни в ассетах


def test_her_frame_takes_her_reference_set_from_assets_in_order():
    refs = ig.require_identity([])
    assert [r.name for r in refs][:3] == ["face-main-selfie-black.jpg", "face-front-white.jpg", "face-selfie-2.jpg"]


def test_missing_passed_ref_falls_back_to_assets_not_to_text(tmp_path):
    import pytest
    seen = {}
    ig.generate("она за столом", tmp_path / "a.png", her=True, refs=[tmp_path / "нет.jpg"],
                codex=lambda p, d, r, refs=(), raw=False: seen.setdefault("refs", refs) and d,
                kie=lambda *a, **k: pytest.fail("codex ответил"))
    assert seen["refs"] and seen["refs"][0].name == "face-main-selfie-black.jpg"


def test_hairstyle_and_clothing_always_change():
    # её правило 2026-09-25: «причёску, одежду обязательно меняем» — лицо и цвет волос остаются
    assert "overall hairstyle unless asked" not in ig.IDENTITY_LOCK
    assert "Hairstyle and clothing MUST be different from the reference photos" in ig.KEEP_FACE
    assert "hair colour stays" in ig.KEEP_FACE


def test_run_codex_sends_prompt_through_stdin_and_never_through_cmd_shim(monkeypatch, tmp_path):
    """Многострочный промпт и `&` не должны идти аргументом: codex.cmd обрезает и исполняет их."""
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, input=kw.get("input"))

        class P:
            returncode, stdout = 0, ""
        return P()

    monkeypatch.setattr("runtime.codex_bridge.default_codex_cmd", lambda: ["node", "codex.js"])
    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    prompt = 'строка 1\nA sign "OPEN & echo PWNED>marker.txt & rem'
    ig.run_codex(["codex", "exec", "--json", prompt], tmp_path)
    assert seen["argv"] == ["node", "codex.js", "exec", "--json", "-"]
    assert seen["input"] == prompt and not any(".cmd" in a.lower() for a in seen["argv"])


def test_kie_key_is_never_sent_to_a_foreign_host():
    assert {"api.kie.ai", "kieai.redpandaai.co"} == ig.KIE_HOSTS
    assert urllib_host(ig.KIE_BASE) in ig.KIE_HOSTS and urllib_host(ig.KIE_UPLOAD) in ig.KIE_HOSTS
    with pytest.raises(ig.ImageGenError, match="не из kie.ai"):
        ig.kie_http("POST", "https://evil.example/upload", "secret-key", {})


def urllib_host(url):
    import urllib.parse
    return urllib.parse.urlsplit(url).hostname
