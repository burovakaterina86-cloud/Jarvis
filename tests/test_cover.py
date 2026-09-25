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
