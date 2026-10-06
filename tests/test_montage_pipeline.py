"""Сборка ffmpeg, громкость, окна пауз, отчёт реза, вендорная правка порога. Без сети."""
import pytest
import importlib.util
import os
import re
import sys
from pathlib import Path

from integrations.montage import compose, config, cut, loudness, run, words

TL = {"dur": 66.0, "split": [[0, 6], [9, 21]], "band": [[33, 36]], "full": [[6, 9]]}


def test_ffmpeg_graph_windows_layers_and_subtitles_last():
    g = compose.filter_graph(TL)
    assert f"overlay=0:{config.SPLIT_SHIFT}" in g and f"overlay=0:{config.BAND_SHIFT}" in g
    assert "between(t,0,6)+between(t,9,21)" in g and "between(t,33,36)" in g
    assert g.rstrip().endswith("subtitles=subs.ass:fontsdir=fonts[out]")      # субтитры — самый верхний слой
    assert g.index("[v2][1:v]") < g.index("subtitles=")                       # оверлей под субтитрами


def test_empty_window_list_never_enables_a_layer():
    g = compose.filter_graph({**TL, "band": []})
    assert "enable='0'" in g


def test_loudness_second_pass_uses_measurements_and_linear_mode():
    m = {"input_i": "-19.1", "input_tp": "-1.9", "input_lra": "3.5", "input_thresh": "-29.1", "target_offset": "0.05"}
    f = loudness.second_pass_filter(m)
    assert f.startswith(config.LOUD_CHAIN)
    for part in ("I=-14.0", "TP=-1.0", "measured_I=-19.1", "measured_thresh=-29.1", "offset=0.05", "linear=true"):
        assert part in f


def test_chain_is_the_gentle_one_measured_for_her_recording():
    assert "ratio=2" in config.LOUD_CHAIN and "highpass=f=100" in config.LOUD_CHAIN
    assert "ratio=3" not in config.LOUD_CHAIN      # 3:1 ухудшает запас голоса над фоном на тихой записи с гулом


def test_roughcut_floor_override_is_in_the_vendored_copy(monkeypatch):
    spec = importlib.util.spec_from_file_location("rc_vendor", config.VENDOR / "roughcut.py")
    rc = importlib.util.module_from_spec(spec)
    sys.modules["rc_vendor"] = rc
    spec.loader.exec_module(rc)
    monkeypatch.setenv("ROUGHCUT_FLOOR_DB", "-42")
    assert rc.pick_floor([-20.0] * 100) == -42.0
    monkeypatch.delenv("ROUGHCUT_FLOOR_DB")
    assert rc.pick_floor([-20.0] * 100) == -30.0     # без правки громкая запись упирается в канонический потолок


def test_cut_environment_carries_the_floor_and_report_is_parsed():
    assert cut._env(-42.0)["ROUGHCUT_FLOOR_DB"] == "-42.0"
    rep = cut.parse_report("порог тишины    -42.0 дБ (от речи, не от шума)\nпауз найдено    26\nрезов           24, убрано 4.95 с\n"
                           "станет          85.73 с (сжатие 5.5%)\n")
    assert (rep.floor_db, rep.cuts, rep.removed_s, rep.result_s) == (-42.0, 24, 4.95, 85.73)


MARK = """режим mark: только разметка, ничего не собираю
     0.000 -    0.550  пауза 750 мс
     4.170 -    4.370  пауза 380 мс
     5.880 -    6.390  пауза 690 мс
    11.810 -   12.330  пауза 300 мс
    12.880 -   13.150  пауза 530 мс (граница предложения)
"""


def test_pause_windows_and_phrase_split():
    wins = words.parse_mark(MARK)
    assert wins[0] == (0.0, 0.55, 750) and len(wins) == 5
    ph = words.split_phrases(wins, 20.0)
    # паузы короче 320 мс (300) склеиваются внутрь фразы; фраза короче 0,6 с присоединяется к соседней
    assert ph[0][0] == 0.55 and all(b > a for a, b in ph)
    assert not any(a < 11.9 < b for a, b in [(p[0], p[0]) for p in ph])     # внутри фразы 300-мс пауза не режет её


def test_slug_is_safe_for_filenames():
    assert run.slug_of("10 систем в Клод!") == "10-систем-в-клод"
    assert re.fullmatch(r"reel-\d{8}-\d{4}", run.slug_of("   "))


def test_tools_check_names_what_is_missing(monkeypatch):
    monkeypatch.setattr(config, "_load_env", lambda: None)       # не читаем настоящий файл окружения
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_KEY", raising=False)
    assert any("GROQ_API_KEY" in m for m in config.require_tools())


def test_groq_key_accepts_the_bots_name_and_children_get_the_vendor_name(monkeypatch):
    monkeypatch.setattr(config, "_load_env", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_KEY", "test-not-a-real-key")
    assert config.groq_key() == "test-not-a-real-key"
    assert config.child_env()["GROQ_API_KEY"] == "test-not-a-real-key"


def test_canvas_filter_only_for_vertical_non_1080x1920_sources():
    assert cut.canvas_filter(1080, 1920) is None
    f = cut.canvas_filter(720, 1280)
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in f and "crop=1080:1920" in f
    f2 = cut.canvas_filter(464, 848)
    assert f2 and "crop=1080:1920" in f2
    import pytest
    with pytest.raises(RuntimeError, match="не вертикальный"):
        cut.canvas_filter(1920, 1080)


def test_limiter_is_added_only_when_the_peak_does_not_fit_linear_mode():
    # её громкий дубль: пик на 12 дБ над средним — влезает, лимитер не нужен
    assert loudness.limiter_for(-19.1, -7.0) is None
    # тихий дубль «монтаж»: −30 LUFS, пик −14 дБ (запас 16 дБ > 13) — подрезаем до ~−17 dBFS
    lin = loudness.limiter_for(-30.1, -13.96)
    assert lin is not None and 0.12 <= lin <= 0.16
    # нужен потолок ниже допустимого для alimiter — не обещаем linear
    assert loudness.limiter_for(-45.0, -15.0) is None


def test_preview_gets_a_light_copy_readable_without_a_button(tmp_path):
    """Лист кадров весит больше мегабайта, а защита просит кнопку на чтение файла больше 100 КБ."""
    import shutil
    import subprocess
    import pytest
    if not shutil.which("ffmpeg"):
        pytest.skip("нет ffmpeg")
    from integrations.montage import preview
    sheet = tmp_path / "preview.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "nullsrc=s=1900x640,geq=random(1)*255:random(2)*255:random(3)*255",
                    "-frames:v", "1", str(sheet)], check=True)
    assert sheet.stat().st_size > 1_000_000
    small = preview.small_copy(sheet)
    assert small.name == "preview-small.jpg" and small.stat().st_size <= preview.SMALL_MAX_BYTES


def test_skill_queues_the_build_with_the_bot_and_reads_the_light_preview():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".claude" / "skills" / "reel-montage" / "SKILL.md").read_text(encoding="utf-8")
    assert "python -m integrations.jobs submit" in text and "закончи ход" in text and "Не жди сборку внутри хода" in text
    assert "preview-small.jpg" in text
    assert "запусти **фоном**" not in text and "timeout: 600000" not in text


# ---------- защита от оборванной сборки (её требование 2026-10-06) ----------

def test_build_lock_refuses_a_second_live_build_and_takes_over_a_dead_one(tmp_path):
    from integrations.montage import render
    lock = render.acquire_lock(tmp_path)
    assert lock.name == ".build.lock"
    with pytest.raises(render.BuildBusy, match="уже идёт"):
        render.acquire_lock(tmp_path)                                 # тот же живой процесс — отказ
    lock.write_text("999999 0", encoding="utf-8")                     # мёртвый процесс и древний замок
    assert render.acquire_lock(tmp_path, alive=lambda pid: False).exists()
    lock.write_text(f"{__import__('os').getpid()} 0", encoding="utf-8")   # живой, но замок старше двух часов
    assert render.acquire_lock(tmp_path, now=lambda: render.LOCK_STALE_SEC + 10).exists()


def test_stale_frames_are_removed_even_when_windows_holds_them_for_a_moment(tmp_path):
    from integrations.montage import render
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "00001.png").write_bytes(b"x")
    calls = {"n": 0}
    real = render.shutil.rmtree

    def flaky(path):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("папка не пуста")
        return real(path)

    render.shutil.rmtree, sleeps = flaky, []
    try:
        render.rmtree_retry(frames, sleep=sleeps.append)
    finally:
        render.shutil.rmtree = real
    assert not frames.exists() and calls["n"] == 3 and len(sleeps) == 2


def test_incomplete_frame_set_is_refused_before_ffmpeg(tmp_path, monkeypatch):
    from integrations.montage import render
    work = tmp_path / "w"
    (work / "frames").mkdir(parents=True)
    (work / "overlay.html").write_text("<html></html>", encoding="utf-8")
    for i in range(1, 11):
        (work / "frames" / f"{i:05d}.png").write_bytes(b"x")          # 10 кадров вместо 660

    class Fake:
        stdout = iter(["готово\n"])
        def wait(self):
            return 0

    monkeypatch.setattr(render.subprocess, "Popen", lambda *a, **k: Fake())
    monkeypatch.setattr(render, "kill_orphans", lambda: None)
    monkeypatch.setattr(render, "rmtree_retry", lambda p: None)       # «кадры остались от оборванной сборки»
    monkeypatch.setattr(render.config, "find_puppeteer", lambda: "p", raising=False)
    monkeypatch.setattr(render.config, "find_browser", lambda: "b", raising=False)
    with pytest.raises(RuntimeError, match="кадры неполные: 10 из 660"):
        render.render_frames(work, 22.0, fps=30)
    assert not (work / ".build.lock").exists()                         # замок снят и после ошибки


def test_orphan_cleanup_spares_a_build_running_in_another_folder(tmp_path):
    from integrations.montage import render
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (b / ".build.lock").write_text("4242 0", encoding="utf-8")
    assert render.other_builds_alive(tmp_path, a, alive=lambda pid: pid == 4242) is True
    assert render.other_builds_alive(tmp_path, a, alive=lambda pid: False) is False
    assert render.other_builds_alive(tmp_path, b, alive=lambda pid: True) is False   # свой замок не считается
