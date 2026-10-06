"""Сборка ffmpeg, громкость, окна пауз, отчёт реза, вендорная правка порога. Без сети."""
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
