"""Очистка шума: когда применять, проверка речи, откат, настоящий ffmpeg на синтетике. Без сети (распознавание подменено)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from integrations.montage import config, denoise

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="нет ffmpeg")


def test_auto_cleans_only_noisy_recordings():
    assert denoise.should_clean("auto", 17.8)[0] is True        # дубль «монтаж»
    assert denoise.should_clean("auto", 28.7)[0] is False       # «10 систем» — чистая запись
    assert denoise.should_clean("on", 40)[0] is True and denoise.should_clean("off", 5)[0] is False
    with pytest.raises(ValueError):
        denoise.should_clean("maybe", 10)


def test_her_choice_is_the_mild_filter():
    assert config.DENOISE_FILTER.startswith("afftdn=") and "anlmdn" not in config.DENOISE_FILTER
    assert config.DENOISE_MIN_SIMILARITY >= 0.97 and config.DENOISE_MAX_LOST_WORDS <= 1


def test_speech_check_accepts_small_variance_and_rejects_lost_words():
    base = "это раз два три четыре пять шесть семь восемь девять десять и опять и вот еще немного слов".split()
    ok, ratio, changed = denoise.speech_ok(base, base)
    assert ok and ratio == 1.0 and changed == []
    one = base[:5] + ["иное"] + base[6:]                             # одно слово распознано иначе
    ok, ratio, _ = denoise.speech_ok(base, one)
    assert ok and ratio >= 0.9
    lost = base[:4] + base[8:]                                        # пропало четыре слова
    ok, _, changed = denoise.speech_ok(base, lost)
    assert not ok and len(changed) == 4


def test_tokens_ignore_case_punctuation_and_yo():
    assert denoise.norm_tokens([{"word": "Ёлка,"}, {"word": "ДЕРЕВО."}]) == ["елка", "дерево"]


def _noisy_clip(path: Path) -> None:
    """3 с: «речь» (тон 220 Гц с пульсацией) на фоне шума."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=3", "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:a=0.08",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3:r=10", "-filter_complex", "[0][1]amix=inputs=2:duration=first[a]", "-map", "2:v",
                    "-map", "[a]", "-shortest", str(path)], check=True)


@needs_ffmpeg
def test_clean_audio_keeps_video_and_duration_and_headroom_function_runs(tmp_path):
    src = tmp_path / "in.mp4"
    _noisy_clip(src)
    out = denoise.clean_audio(src, tmp_path / "out.mov")
    dur = lambda p: float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))
    assert abs(dur(src) - dur(out)) < 0.1
    assert isinstance(denoise.headroom_db(src), float) and isinstance(denoise.headroom_db(out), float)


@needs_ffmpeg
def test_run_applies_when_speech_is_intact_and_falls_back_when_not(tmp_path):
    src = tmp_path / "in.mp4"
    _noisy_clip(src)
    words = [{"word": w} for w in "один два три четыре пять шесть семь восемь девять десять".split()]
    same = lambda path: words                                          # «распознавание» одинаково до и после
    rep = denoise.run(src, tmp_path, "on", transcribe=same)
    assert rep.applied and rep.source == tmp_path / "denoised.mov" and rep.similarity == 1.0

    calls = []

    def broken(path):                                                  # после очистки половина слов пропала
        calls.append(path)
        return words if len(calls) == 1 else words[:5]
    rep2 = denoise.run(src, tmp_path, "on", transcribe=broken)
    assert not rep2.applied and rep2.source == src and "очистка отменена" in rep2.reason


@needs_ffmpeg
def test_off_and_auto_on_clean_audio_do_not_touch_the_file(tmp_path):
    src = tmp_path / "in.mp4"
    _noisy_clip(src)
    rep = denoise.run(src, tmp_path, "off")
    assert not rep.applied and rep.source == src and not (tmp_path / "denoised.mov").exists()
