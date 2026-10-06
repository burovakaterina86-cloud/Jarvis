# montage-pipeline (вендорная копия)

Источник: <https://github.com/qwwiwi/montage-pipeline> (MIT, © 2026 Dashi Eshiev), коммит `aa74c64`.
`roughcut.py` — первый заход (рез по энергии звука), `captions.py` — субтитры ASS. Скиллы и журнал ошибок
автора — в его репозитории; наш журнал — `../../docs/errors.md`.

Единственная локальная правка (помечена в коде «ЛОКАЛЬНАЯ ПРАВКА»): `roughcut.py::pick_floor` читает
переменную окружения `ROUGHCUT_FLOOR_DB`. Каноничный порог (от речи, зажим −46…−30 дБ) на её громкой записи
ставится на −30 дБ и режет хвосты слов; для неё работает −42 дБ (`integrations/montage/config.py::FLOOR_DB`).

Обновляя копию из репозитория автора, верни эту правку (см. `tests/test_montage_vendor.py`).
