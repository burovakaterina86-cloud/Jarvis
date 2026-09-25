"""Обложка поста по её референсам (2026-09-25): без браузера."""
from integrations.visuals import cover


BASE = {"hook": "Как использовать\n[[примеры]]", "pill": "Few-shot логика", "hand": "показать иногда\nсильнее, чем объяснять"}


def test_light_cover_has_her_elements(tmp_path):
    img = tmp_path / "me.png"
    img.write_bytes(b"x")
    html = cover.build_cover({**BASE, "photo": str(img), "icons": ["chat", "doc", "image"],
                              "support": "Примеры\nснимают домыслы"}, "light")
    for part in ('class="pill"', 'class="hand"', 'class="support"', 'class="photo"', 'class="decor"',
                 'class="dots"', 'class="tiles"'):
        assert part in html, part
    assert '<span class="acc">примеры</span>' in html.lower() or '<span class="acc">ПРИМЕРЫ</span>' in html
    assert "mask-image" in html                   # фото сливается с фоном, без эффекта вырезки
    assert cover.THEMES["light"]["accent"] in html


def test_dark_cover_uses_dark_theme_and_terracotta_hand():
    html = cover.build_cover(BASE, "dark")
    assert cover.THEMES["dark"]["bg"] in html
    assert cover.THEMES["dark"]["hand"] in html


def test_default_tag_is_her_line():
    html = cover.build_cover(BASE, "light")
    assert "ТЕСТИРУЮ" in html and "АНАЛИЗИРУЮ" in html and "УЛУЧШАЮ" in html


def test_missing_photo_is_reported(tmp_path):
    notes = []
    cover.build_cover({**BASE, "photo": str(tmp_path / "nope.png")}, "light", notes)
    assert any("nope.png" in n for n in notes)


def test_alternation_flips_theme_and_photo_kind(tmp_path):
    assert cover.next_choice(tmp_path) == {"bg": "light", "photo_kind": "her"}
    cover.remember_choice(tmp_path, {"bg": "light", "photo_kind": "her"})
    assert cover.next_choice(tmp_path) == {"bg": "dark", "photo_kind": "topic"}
    cover.remember_choice(tmp_path, {"bg": "dark", "photo_kind": "topic"})
    assert cover.next_choice(tmp_path) == {"bg": "light", "photo_kind": "her"}


def test_hand_image_replaces_script_font_and_blends(tmp_path):
    img = tmp_path / "hand.png"
    img.write_bytes(b"x")
    light = cover.build_cover({**BASE, "hand_image": str(img)}, "light")
    assert 'class="hand-img"' in light and 'class="hand"' not in light
    # фон вырезается в самой картинке: режимы наложения CSS в слое с z-index не смешиваются с холстом
    assert "mix-blend-mode" not in light


def test_hand_prompt_carries_her_description_and_exact_text():
    pr = cover.hand_prompt("важно не всё подряд,\nа по задаче", "light")
    assert "важно не всё подряд,\nа по задаче" in pr
    for part in ("fashion-editorial", "slant to the right", "connected letters", "Not a calligraphic",
                 "pure white", "terracotta"):
        assert part in pr, part
    assert "pure black" in cover.hand_prompt("x", "dark")


def test_hand_image_is_reused_when_text_unchanged(tmp_path):
    refs = tmp_path / cover.HAND_REFS
    refs.mkdir(parents=True)
    (refs / "light-terracotta.png").write_bytes(b"x")
    calls = []

    def fake(prompt, dest, refs_):
        calls.append(prompt)
        dest.write_bytes(b"png")

    dest = tmp_path / "c-hand.png"
    assert cover.make_hand_image("мысль", "light", dest, tmp_path, generate=fake) == dest
    assert cover.make_hand_image("мысль", "light", dest, tmp_path, generate=fake) == dest
    assert len(calls) == 1
    cover.make_hand_image("другая", "light", dest, tmp_path, generate=fake)
    assert len(calls) == 2
