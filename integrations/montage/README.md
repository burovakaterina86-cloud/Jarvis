# integrations/montage — рилс из сырого дубля под ключ

Конвейер монтажа вертикального ролика 1080×1920 для Instagram: **дубль → чистовик → субтитры → оформление → громкость**.
Метод — Даши (эфир 22.09, `qwwiwi/montage-pipeline`, MIT); настройки, оформление и анимация — под её запись и её выбор (2026-10-06).
Навык для JARVIS: `.claude/skills/reel-montage/SKILL.md`. Журнал находок: `docs/errors.md`.

## Команды (из корня проекта)

```bash
python -m integrations.montage.run check                      # чего не хватает на машине
python -m integrations.montage.run plan <дубль>               # план реза: порог, число пауз, аудит
python -m integrations.montage.run phrases <дубль> --work outbox/montage/<имя>   # расшифровка по фразам → искать повторы
python -m integrations.montage.run make <дубль> --spec <spec.json> [--drop ОТ-ДО …] --name <имя>
python -m integrations.montage.run preview --work outbox/montage/<имя> --spec <spec.json> --at 4,12.9,62      # кадры оформления за ~20 с
python -m integrations.montage.run remake --work outbox/montage/<имя> --spec <spec.json>   # правка оформления без реза
```

Результат — `outbox/<имя>.mp4`; рабочая папка `outbox/montage/<имя>/` (`summary.json`, `subs.txt`, `seams/`, `words.json`).

## Шаги и модули

| Шаг | Модуль | Что делает |
|---|---|---|
| 0 очистка шума | `denoise.py` | необязательно (`--denoise auto`): мягкий `afftdn`, только для шумных записей, с проверкой слов до/после и откатом |
| 1 рез | `cut.py` → `vendor/montage_pipeline/roughcut.py` | паузы по энергии звука (порог −42 дБ), аудит, проверка речи, ускорение 1,3 |
| 2 слова | `words.py` | Groq whisper-large-v3, слова с таймкодами; по фразам — для поиска повторов |
| 3 спецификация | `spec.py`, `icons.py` | JSON → сцены; времена — якоря на слова |
| 4 субтитры | `subs.py` → `vendor/…/captions.py` | ASS ≤ 24 символов, правка слов, y = 1730, обводка |
| 5–6 оформление | `overlay.py`, `templates/`, `render.py` | страница с анимацией `render(t)` → прозрачные PNG (Node + puppeteer-core + Edge) |
| 7 сборка | `compose.py`, `loudness.py` | ffmpeg: раскладка, оверлей, субтитры сверху; −14 LUFS в два прохода |

Зависимости: ffmpeg/ffprobe, curl, Node, Edge или Chrome, `puppeteer-core` (ставится с `npm i -g hyperframes`, путь — `MONTAGE_PUPPETEER`),
`GROQ_API_KEY` в окружении. Python — только стандартная библиотека.

## Логотипы, иконки и свои сцены

- `python -m integrations.montage.logos search|fetch|list` — настоящие SVG из `glincker/thesvg` и `gilbarbara/logos` в `outbox/montage/logos/`. Только эти два
  источника по HTTPS, только SVG до 200 КБ без скриптов и внешних ссылок, имя `[a-z0-9-]`. Её разрешение 2026-10-06.
- `icons.py` — 36 линейных SVG-иконок; плашка получает иконку по смыслу слов (или `"icon": "имя"`, `null` — без неё); в своих сценах `{{icon:имя|размер}}`.
- `type: custom` в спецификации — новый экран или плашка HTML-ом (`custom.py`): анимация атрибутами `data-a/data-d/data-word`, логотипы
  `{{logo:имя}}`, сито без скриптов и сети, предупреждения о выходе за безопасную зону. Образец — `examples/custom-telegram-screen.html`.

## Числа (`config.py`) — каждое измерено

`FLOOR_DB −42` · `SPEED 1,3` · `SUB_Y 1730` · `SUB_MAX_CHARS 24` · зоны Instagram: шапка 115, подпись 1248, панель 1760, справа с x = 930 ·
громкость −14 LUFS / пик −1 dBTP, цепочка `highpass 100 Гц + компрессор 2:1 + лимитер`.

## Тесты

`tests/test_montage_*.py` — без сети и браузера: якоря на слова, правка слов, окна раскладок, безопасные зоны Instagram,
граф ffmpeg, вендорная правка порога. Полный прогон конвейера — вручную (`make` на тестовом дубле).
