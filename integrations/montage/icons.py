"""Иконки для плашек: линейные SVG одного веса (24×24, штрих 2), цвет — от текста (`currentColor`).

Свои, а не эмодзи: в браузере без цветного шрифта эмодзи выходят чужими глифами (журнал J10). Иконка подбирается по смыслу слова
(`auto_icon`), можно задать явно (`"icon": "mic"`) или отключить (`"icon": null`). Фирменные знаки (Gmail, Telegram, Claude) —
не здесь, а настоящими SVG из каталога логотипов (`logos.py`).
В своих сценах: `{{icon:mic}}` или `{{icon:mic|56}}` (размер в px).
"""
from __future__ import annotations

import re

_P = {
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "text": '<path d="M5 6h14M12 6v13M9 19h6"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "sparkles": '<path d="M11 3l1.8 4.7 4.7 1.8-4.7 1.8L11 16l-1.8-4.7L4.5 9.5l4.7-1.8z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "newspaper": '<path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M19 8h2v10a2 2 0 0 1-2 2M9 8h6M9 12h6M9 16h4"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
    "lightbulb": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "send": '<path d="M21 3L3 10.5l7 2.5 2.5 7z"/><path d="M10 13l11-10"/>',
    "play": '<path d="M8 5v14l11-7z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 8l11.5 10M8.5 16L20 6"/>',
    "captions": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 11h4M13 11h4M7 15h2M11 15h6"/>',
    "shield": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "gift": '<rect x="3" y="9" width="18" height="12" rx="1.5"/><path d="M12 9v12M3 13h18M12 9C10 5 6 6 7 9c1 1.5 5 0 5 0zM12 9c2-4 6-3 5 0-1 1.5-5 0-5 0z"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "wallet": '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18M16 15h2"/>',
    "chart": '<path d="M4 20V4M4 20h16M8 16v-5M12 16V8M16 16v-8"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
    "notebook": '<path d="M6 3h11a2 2 0 0 1 2 2v16H8a2 2 0 0 1-2-2z"/><path d="M6 3v16M10 8h6M10 12h6"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="M4 18l5-5 4 4 3-3 4 4"/>',
    "message": '<path d="M4 5h16v11H9l-5 4z"/>',
    "warning": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.1"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11M4 6h.1M4 12h.1M4 18h.1"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
}

NAMES = sorted(_P)

# корень слова (по нижнему регистру) → иконка; порядок важен: первое совпадение
_AUTO = [
    ("озвуч", "mic"), ("голос", "mic"), ("материал", "folder"), ("файл", "folder"), ("задач", "target"), ("цел", "target"), ("план", "target"),
    ("вердикт", "check"), ("готов", "check"), ("итог", "check"), ("сдвин", "check"), ("заметк", "notebook"), ("документ", "file"),
    ("инструкц", "file"), ("справк", "file"), ("скриншот", "image"), ("фото", "image"), ("картин", "image"), ("текст", "text"), ("пост", "message"),
    ("сообщен", "message"), ("объясн", "message"), ("сцен", "film"), ("анимац", "sparkles"), ("акцент", "star"), ("важн", "star"),
    ("календар", "calendar"), ("встреч", "calendar"), ("почт", "mail"), ("письм", "mail"), ("новост", "newspaper"), ("созвон", "phone"),
    ("звон", "phone"), ("тезис", "list"), ("список", "list"), ("риск", "warning"), ("провал", "warning"), ("ошибк", "warning"),
    ("ждут", "clock"), ("время", "clock"), ("имя", "user"), ("клиент", "user"), ("скептик", "user"), ("стратег", "target"),
    ("финансист", "wallet"), ("доход", "chart"), ("расход", "wallet"), ("платеж", "wallet"), ("подписк", "wallet"), ("лучше", "lightbulb"),
    ("идея", "lightbulb"), ("видео", "video"), ("ролик", "video"), ("промпт", "terminal"), ("промт", "terminal"), ("код", "terminal"),
    ("нет", "x"), ("рез", "scissors"), ("субтитр", "captions"), ("чувствит", "shield"), ("защит", "shield"), ("ссылк", "link"),
    ("поиск", "search"), ("отправ", "send"), ("оформл", "sparkles"), ("монтаж", "scissors"), ("именно", "target"),
    ("эффектив", "chart"),
]


def icon_svg(name: str, size: int = 40) -> str:
    if name not in _P:
        raise KeyError(name)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" style="flex:none">{_P[name]}</svg>')


def auto_icon(text: str) -> str | None:
    """Иконка по смыслу слов в подписи; нет уверенного совпадения — None (лучше без иконки, чем не по смыслу)."""
    t = text.lower().replace("ё", "е")
    for stem, name in _AUTO:
        tail = r"(?![а-яa-z])" if len(stem) <= 3 else ""      # короткие корни («нет», «рез», «код») — только слово целиком
        if re.search(rf"(?<![а-яa-z]){stem}{tail}", t):
            return name
    return None


def fill_placeholders(html: str) -> str:
    """`{{icon:имя}}` / `{{icon:имя|размер}}` в HTML своей сцены → встроенный SVG."""
    def sub(m):
        name, size = m.group(1), int(m.group(2) or 40)
        if name not in _P:
            raise ValueError(f"нет иконки «{name}»; есть: {', '.join(NAMES)}")
        return icon_svg(name, max(16, min(size, 200)))
    return re.sub(r"\{\{icon:([a-z\-]+)(?:\|(\d+))?\}\}", sub, html)
