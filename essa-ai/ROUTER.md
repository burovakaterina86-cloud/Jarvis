# AgentOS ChatGPT Router

## Алгоритм выбора

1. Определи домен запроса: research / coding / content / social / ai-media / sites-apps / visualization / system-memory.
2. Сопоставь смысл запроса с `purpose` и `triggers` в `AGENTOS_CHATGPT_CORE.md`.
3. Выбери один основной skill. Вторичный skill добавляй только если он закрывает отдельный этап.
4. Если запрос комплексный, строй цепочку с явным порядком вход → преобразование → выход.
5. Если `ROLE_PACKS.md` доступен — используй его как вспомогательный набор для роли, но всё равно выбирай минимальные skills. Отсутствие `ROLE_PACKS.md` не блокирует маршрутизацию: основной источник выбора skill — реестр `AGENTOS_CHATGPT_CORE.md`.
6. Если user назвал конкретный skill, не заменяй его другим без причины.
7. Если задача не покрыта каталогом, не выдумывай новый AgentOS skill: реши обычными возможностями ChatGPT и отметь, что это не upstream skill.

## Разрешение конфликтов
- Project source-of-truth > AgentOS skill.
- Факты пользователя > примеры skill.
- Ограничение реального инструмента > обещание из Claude-ориентированного workflow.
- Безопасность и приватность > автоматизация.

## Обязательный production pipeline для публичного текста

Это исключение из правила «минимальный набор skills», потому что Катерина явно установила два обязательных отдельных этапа качества.

Если результат предназначен для публичной публикации от имени Катерины:

1. Сначала определить стратегический контент-бриф по Project SOURCE OF TRUTH.
2. Профильный skill решает задачу формата/структуры (`content-engine`, `reels`, `carousel-instagram`, `present` и т.д.).
3. `textwriter` — обязательный языковой pass.
4. `humaniser` — обязательный финальный языковой pass.
5. Сверить итог с `VOICE.md`, `04_BRAND_VOICE.md`, `07_CONTENT_RULES.md` и proof/fact sources.
6. Только после этого показывать финальную публичную версию.

Для обычного поста:
`content-engine (brief) → textwriter → humaniser → voice/fact/funnel preflight → final`

Для Reels:
`reels → textwriter → humaniser → preflight`

Для карусели:
`content brief + slide functions → textwriter → humaniser → carousel-instagram`
При этом `textwriter`/`humaniser` не могут менять функцию слайдов и смысловой маршрут.

Если пользователь просит только анализ/идею/черновой план, обязательная языковая цепочка не нужна, пока результат не является готовым публичным текстом.

