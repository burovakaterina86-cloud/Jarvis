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


# ---------- замок и таймаут рендера (ревью 2026-10-07) ----------

def test_lock_is_taken_atomically_by_only_one_of_many_builds(tmp_path):
    import threading as th

    wins, busy = [], []

    def grab():
        try:
            render.acquire_lock(tmp_path, alive=lambda pid: True)
            wins.append(1)
        except render.BuildBusy:
            busy.append(1)

    threads = [th.Thread(target=grab) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(wins) == 1 and len(busy) == 11


def test_fresh_lock_without_pid_cannot_be_stolen(tmp_path):
    lock = tmp_path / render.LOCK_NAME
    lock.write_text("", encoding="utf-8")
    with pytest.raises(render.BuildBusy):
        render.acquire_lock(tmp_path, alive=lambda pid: False)
    assert lock.read_text(encoding="utf-8") == ""


def test_frozen_render_is_killed_at_timeout(tmp_path, monkeypatch):
    killed = []

    class Hung:
        returncode = None
        stdout = iter(())

        def wait(self):
            import time
            for _ in range(100):
                if killed:
                    return 1
                time.sleep(0.02)
            return 1

        def poll(self):
            return None if not killed else 1

    monkeypatch.setattr(render, "RENDER_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(render.subprocess, "Popen", lambda *a, **k: Hung())
    monkeypatch.setattr(render.procutil, "kill_tree", lambda proc: killed.append(proc))
    monkeypatch.setattr(render, "env_for", lambda *a, **k: {})
    monkeypatch.setattr(render, "kill_orphans", lambda: None)
    with pytest.raises(RuntimeError, match="не уложился"):
        render.render_frames(tmp_path, 1.0, t0=0.0, t1=0.5)
    assert killed


# ---------- молчаливые ошибки и затирание файлов (ревью 2026-10-07) ----------

def test_broken_logo_sources_file_is_kept_aside_not_silently_reset(tmp_path):
    from integrations.montage import logos
    (tmp_path / "_sources.json").write_text("{не json", encoding="utf-8")
    logos._remember(tmp_path, "claude", "https://x/y.svg")
    assert json.loads((tmp_path / "_sources.json").read_text(encoding="utf-8")) == {"claude": "https://x/y.svg"}
    assert (tmp_path / "_sources.json.bad").read_text(encoding="utf-8") == "{не json"


def test_same_name_screens_from_different_folders_do_not_overwrite_each_other(tmp_path):
    from integrations.visuals import kit
    a, b, out = tmp_path / "a", tmp_path / "b", tmp_path / "out"
    a.mkdir(); b.mkdir()
    (a / "screen.png").write_bytes(b"first")
    (b / "screen.png").write_bytes(b"second")
    one, two = kit._carry_one(str(a / "screen.png"), out), kit._carry_one(str(b / "screen.png"), out)
    assert one != two and one.read_bytes() == b"first" and two.read_bytes() == b"second"
    assert kit._carry_one(str(a / "screen.png"), out) == one          # тот же файл — то же имя


def test_montage_cli_turns_tool_failures_into_a_clear_error(tmp_path, monkeypatch, capsys):
    import subprocess as sp

    from integrations.montage import run
    monkeypatch.setattr(run, "check", lambda: (_ for _ in ()).throw(sp.CalledProcessError(1, "ffprobe")))
    assert run.main(["check"]) == 2
    assert "ОШИБКА: CalledProcessError" in capsys.readouterr().err
