# AgentOS → ChatGPT Adapter Core

Версия адаптера: 1.0.1-chatgpt-project
Проверено: 2026-09-08
Upstream: `qwwiwi/agentos-skills-public`
Pinned commit: `3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802`
Лицензия upstream: MIT

## Что это

Это слой совместимости, который переносит публичный каталог AgentOS из модели Claude Code skills в ChatGPT Projects. Он не притворяется, что ChatGPT имеет файловую систему `~/.claude/skills/` или CLI-инструменты Claude Code. Вместо этого используется: **semantic router → выбранный skill → capability mapping → выполнение доступными инструментами ChatGPT**.

## Принцип полноты

В upstream snapshot найдено 42 уникальных публичных skill. Все 42 зарегистрированы ниже. Названия из секции «Готовятся к публикации» не считаются установленными: исходных публичных skill-папок для них нет.

## Главный runtime-контракт

1. На каждый запрос сначала определить задачу и выбрать **минимальный достаточный набор skills**.
2. Если пользователь явно назвал skill — он приоритетен, если не конфликтует с более высоким контекстом проекта.
3. Для обычной маршрутизации достаточно записи skill в реестре этого файла. Если в Project загружен локальный adapter-файл `SKILL_<name>.md` (или эквивалентный файл skill), использовать его как дополнительную методику. Отсутствие локального adapter-файла само по себе НЕ является ошибкой и не блокирует выполнение.
4. Если локальный adapter указывает `source_load: required` ИЛИ для production-задачи нужна детальная методика, получить pinned upstream `SKILL.md` по точной pinned-ссылке из реестра/adapter. Если upstream `SKILL.md` ссылается на `references/`, `templates/`, `scripts/` или config — получать только реально нужные зависимости из той же pinned версии. Если внешний источник недоступен, выполнить задачу доступными возможностями ChatGPT настолько полно, насколько это возможно, и честно назвать ограничение.
5. Нельзя выдавать замену инструмента за оригинальный инструмент. Например, если вместо Perplexity используется Web Search, прямо считать это ChatGPT-адаптацией, а не «вызовом Perplexity».
6. Если внешняя зависимость недоступна, использовать функционально эквивалентный ChatGPT-инструмент только когда результат действительно можно получить эквивалентно. Иначе назвать ограничение.
7. Не просить пользователя вручную делать то, что доступный инструмент ChatGPT может сделать сам.
8. Не менять факты, стратегию, tone of voice и ограничения проекта ради методики skill. Контекст проекта выше skill.

## Порядок приоритетов

1. Явный текущий запрос пользователя.
2. Project Instructions и пользовательские source-of-truth файлы.
3. Выбранный AgentOS skill / role pack.
4. Общие эвристики модели.

## Композиция

Skills можно соединять. Пример: `reel-radar → transcript → reels → content-engine`. Но роутер не должен подключать skills «на всякий случай»: каждый добавленный skill обязан менять качество или возможность результата.


# Skill Registry

## `perplexity-research`
- category: `research`
- purpose: Web research с источниками; upstream использует Perplexity Sonar API.
- execution_mode: `web-native-fallback`
- triggers: `найди`, `проверь в интернете`, `ресерч`, `best practices`, `тренды`, `fact-check`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/perplexity-research/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/perplexity-research/SKILL.md

## `twitter`
- category: `research/social`
- purpose: Чтение X/Twitter: твиты, статьи, треды, профили, поиск; также используется для контент-ресерча.
- execution_mode: `web-or-external`
- triggers: `x.com`, `twitter`, `твит`, `тред`, `профиль X`, `поиск твитов`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/twitter/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/twitter/SKILL.md

## `markdown-new`
- category: `research`
- purpose: Извлечение и очистка текста из URL в Markdown.
- execution_mode: `web-native`
- triggers: `вытащи текст из ссылки`, `извлеки страницу`, `url в markdown`, `прочитай страницу`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/markdown-new/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/markdown-new/SKILL.md

## `transcript`
- category: `research`
- purpose: Получение транскрипта YouTube/видео по ссылке.
- execution_mode: `web-or-external`
- triggers: `транскрипт`, `расшифруй youtube`, `youtube transcript`, `вытащи речь`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/transcript/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/transcript/SKILL.md

## `groq-voice`
- category: `research`
- purpose: Расшифровка голосовых файлов через Groq Whisper.
- execution_mode: `external-service`
- triggers: `расшифруй голосовое`, `ogg`, `groq whisper`, `voice transcript`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/groq-voice/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/groq-voice/SKILL.md

## `chat-archive`
- category: `research`
- purpose: Анализ архивов Telegram-чатов и извлечение событий/паттернов.
- execution_mode: `uploaded-data`
- triggers: `архив telegram`, `проанализируй чат`, `экспорт переписки`, `chat archive`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/chat-archive/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/chat-archive/SKILL.md

## `telegram-chip`
- category: `research`
- purpose: Работа с Telegram user-account через Telethon/HTTP API: чтение, отправка, экспорт.
- execution_mode: `external-service`
- triggers: `telegram user`, `telethon`, `прочитай telegram`, `экспорт чата`, `отправь в telegram`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/telegram-chip/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/telegram-chip/SKILL.md

## `topic-monitor`
- category: `research`
- purpose: Регулярный мониторинг темы и новые сигналы/материалы.
- execution_mode: `automation-or-web`
- triggers: `мониторь тему`, `следи за`, `регулярный мониторинг`, `дайджест темы`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/topic-monitor/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/topic-monitor/SKILL.md

## `yt-research`
- category: `research`
- purpose: YouTube-ресерч: поиск ниши, velocity, конкуренты, транскрипты.
- execution_mode: `web-or-external`
- triggers: `youtube research`, `найди ролики в нише`, `конкуренты youtube`, `velocity youtube`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/yt-research/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/yt-research/SKILL.md

## `reel-radar`
- category: `research/social`
- purpose: Контент-разведка Instagram Reels: сильные референсы, транскрипты, идеи и ТЗ.
- execution_mode: `external-data`
- triggers: `reel radar`, `разведка reels`, `референсы reels`, `залетевшие рилсы`, `конкуренты reels`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reel-radar/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reel-radar/SKILL.md

## `loop-coding`
- category: `coding`
- purpose: 7-фазный пайплайн больших задач кода: research → audit → plan → implement → review → fix-loop → ship.
- execution_mode: `code-workflow`
- triggers: `большая задача кода`, `рефакторинг`, `миграция`, `loop coding`, `сложная разработка`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/loop-coding/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/loop-coding/SKILL.md

## `fast-loop-coding`
- category: `coding`
- purpose: Облегчённый 4-фазный пайплайн для средних задач.
- execution_mode: `code-workflow`
- triggers: `средняя задача кода`, `50-300 loc`, `fast loop`, `небольшой рефакторинг`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/fast-loop-coding/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/fast-loop-coding/SKILL.md

## `mcp-builder`
- category: `coding`
- purpose: Проектирование и создание MCP-серверов на Python/Node.
- execution_mode: `code-workflow`
- triggers: `mcp server`, `создай mcp`, `mcp-builder`, `инструменты mcp`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/mcp-builder/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/mcp-builder/SKILL.md

## `mcp-api-build`
- category: `coding`
- purpose: Дизайн REST API и преобразование API в MCP с опорой на стандарты.
- execution_mode: `code-workflow`
- triggers: `rest api`, `api design`, `конвертируй api в mcp`, `mcp api`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/mcp-api-build/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/mcp-api-build/SKILL.md

## `senior-brainstorm`
- category: `coding`
- purpose: Архитектурный разбор и выбор стека: что строить, на чём и что лучше купить вместо разработки.
- execution_mode: `reasoning-native`
- triggers: `архитектура`, `выбор стека`, `что строить`, `build vs buy`, `senior brainstorm`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/senior-brainstorm/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/senior-brainstorm/SKILL.md

## `cross-review`
- category: `coding/review`
- purpose: Двойное независимое ревью и слияние findings.
- execution_mode: `review-workflow`
- triggers: `cross review`, `двойное ревью`, `проверь код двумя подходами`, `audit code`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/cross-review/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/cross-review/SKILL.md

## `dev-pipeline`
- category: `coding`
- purpose: Оркестрация разработки и релизного процесса на сервере.
- execution_mode: `external-execution`
- triggers: `dev pipeline`, `разработка на сервере`, `deploy pipeline`, `оркестрация разработки`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/dev-pipeline/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/dev-pipeline/SKILL.md

## `server-doctor`
- category: `coding`
- purpose: Аудит и диагностика Linux/macOS серверов и инцидентов.
- execution_mode: `external-execution`
- triggers: `server doctor`, `почини сервер`, `linux audit`, `диагностика сервера`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/server-doctor/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/server-doctor/SKILL.md

## `agent-browser`
- category: `coding/web`
- purpose: Управление браузером агентом: навигация, клики, формы, скриншоты, извлечение данных, тест веб-приложений.
- execution_mode: `browser-tool`
- triggers: `открой сайт и кликни`, `заполни форму`, `browser agent`, `проверь веб-приложение`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agent-browser/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agent-browser/SKILL.md

## `content-engine`
- category: `content`
- purpose: Tone-of-voice aware контент-движок.
- execution_mode: `content-native`
- triggers: `напиши пост`, `контент`, `tone of voice`, `адаптируй текст`, `контент-план`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/content-engine/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/content-engine/SKILL.md

## `present`
- category: `content/artifact`
- purpose: Создание HTML-презентаций/отчётов по исходной методике AgentOS.
- execution_mode: `artifact`
- triggers: `презентация`, `слайды`, `html presentation`, `отчёт в слайдах`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/present/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/present/SKILL.md

## `seo-tune`
- category: `content/web`
- purpose: SEO/AEO/GEO-аудит и настройка сайта: robots, sitemap, canonical, meta/OG, JSON-LD, llms.txt, IndexNow.
- execution_mode: `web-and-code`
- triggers: `seo audit`, `geo`, `aeo`, `llms.txt`, `json-ld`, `sitemap`, `indexnow`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/seo-tune/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/seo-tune/SKILL.md

## `instagram-superpower`
- category: `social`
- purpose: Аналитика Instagram-аккаунта и конкурентов; upstream использует HikerAPI/Cobalt.
- execution_mode: `external-data`
- triggers: `instagram анализ`, `конкуренты instagram`, `аккаунт instagram`, `скачай reels`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/instagram-superpower/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/instagram-superpower/SKILL.md

## `carousel-instagram`
- category: `social/artifact`
- purpose: Instagram-карусели 1080×1350 из текста и фото; upstream рендерит HTML/CSS + Playwright.
- execution_mode: `artifact`
- triggers: `карусель instagram`, `слайды 1080x1350`, `сделай карусель`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/carousel-instagram/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/carousel-instagram/SKILL.md

## `reels`
- category: `social/content`
- purpose: Сценарии Reels в пяти форматах.
- execution_mode: `content-native`
- triggers: `сценарий reels`, `рилс`, `reel script`, `хук для reels`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reels/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reels/SKILL.md

## `youtube-producer`
- category: `social/content`
- purpose: Производство YouTube long-form: структура и сценарий.
- execution_mode: `content-native`
- triggers: `youtube long-form`, `сценарий youtube`, `видео на youtube`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/youtube-producer/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/youtube-producer/SKILL.md

## `youtube-thumbnail`
- category: `social/artifact`
- purpose: YouTube-обложки 1920×1080 с изображением и текстом.
- execution_mode: `image-artifact`
- triggers: `youtube thumbnail`, `обложка youtube`, `превью 1920x1080`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/youtube-thumbnail/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/youtube-thumbnail/SKILL.md

## `threads-content`
- category: `social/content`
- purpose: Контент и треды для Threads.
- execution_mode: `content-native`
- triggers: `threads`, `тред для threads`, `посты threads`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/threads-content/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/threads-content/SKILL.md

## `reels-analytics-for-brokers`
- category: `social/research`
- purpose: Радар восходящих офферов Instagram: конкуренты, всплески, хуки, динамика. Метод переносится на свою нишу.
- execution_mode: `external-data`
- triggers: `reels analytics`, `радар офферов`, `восходящие офферы`, `анализ хуков reels`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reels-analytics-for-brokers/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/reels-analytics-for-brokers/SKILL.md

## `codex-image`
- category: `ai-media`
- purpose: Генерация картинок, обложек и баннеров через GPT Image/Codex-процесс с референсами.
- execution_mode: `image-native`
- triggers: `сгенерируй картинку`, `обложка`, `баннер`, `codex image`, `gpt image`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/codex-image/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/codex-image/SKILL.md

## `higgsfield-generate`
- category: `ai-media`
- purpose: Общая генерация в Higgsfield.
- execution_mode: `plugin-or-external`
- triggers: `higgsfield`, `сгенерируй видео higgsfield`, `higgsfield generate`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-generate/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-generate/SKILL.md

## `higgsfield-soul-id`
- category: `ai-media`
- purpose: Создание постоянного персонажа через Higgsfield Soul ID.
- execution_mode: `plugin-or-external`
- triggers: `soul id`, `персонаж higgsfield`, `постоянное лицо`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-soul-id/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-soul-id/SKILL.md

## `higgsfield-product-photoshoot`
- category: `ai-media`
- purpose: Продуктовая AI-съёмка через Higgsfield.
- execution_mode: `plugin-or-external`
- triggers: `product photoshoot`, `продуктовая съёмка`, `higgsfield товар`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-product-photoshoot/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-product-photoshoot/SKILL.md

## `higgsfield-marketplace-cards`
- category: `ai-media`
- purpose: Карточки товаров для маркетплейсов через Higgsfield.
- execution_mode: `plugin-or-external`
- triggers: `карточка маркетплейса`, `marketplace card`, `higgsfield карточки`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-marketplace-cards/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/higgsfield-marketplace-cards/SKILL.md

## `workshop`
- category: `sites/apps`
- purpose: Универсальный workflow для сборки и публикации материалов воркшопа.
- execution_mode: `workflow`
- triggers: `воркшоп`, `workshop`, `материалы урока`, `таймкоды воркшопа`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/workshop/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/workshop/SKILL.md

## `agentos-content`
- category: `sites/apps`
- purpose: Контент и материалы для платформ типа AgentOS.
- execution_mode: `workflow`
- triggers: `agentos content`, `платформа обучения`, `загрузить материал на платформу`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agentos-content/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agentos-content/SKILL.md

## `excalidraw`
- category: `visualization`
- purpose: Создание диаграмм/схем Excalidraw.
- execution_mode: `artifact`
- triggers: `excalidraw`, `нарисуй схему`, `диаграмма`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/excalidraw/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/excalidraw/SKILL.md

## `miro-board`
- category: `visualization`
- purpose: Создание/структурирование досок Miro через API.
- execution_mode: `external-service`
- triggers: `miro`, `доска miro`, `разложи на доске`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/miro-board/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/miro-board/SKILL.md

## `datawrapper`
- category: `visualization`
- purpose: Графики и инфографика через Datawrapper-подход.
- execution_mode: `artifact-or-external`
- triggers: `datawrapper`, `график`, `инфографика`, `визуализируй данные`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/datawrapper/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/datawrapper/SKILL.md

## `learnings`
- category: `system/memory`
- purpose: Система самообучения: Episodes → Learnings → Rules.
- execution_mode: `project-memory-adapter`
- triggers: `запиши learning`, `извлеки урок`, `паттерн ошибки`, `episodes rules`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/learnings/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/learnings/SKILL.md

## `memory-audit`
- category: `system/memory`
- purpose: Аудит памяти/контекстных файлов: дубли, устаревшее, конфликтующее.
- execution_mode: `project-memory-adapter`
- triggers: `аудит памяти`, `memory audit`, `дубли в контексте`, `почисти знания`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/memory-audit/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/memory-audit/SKILL.md

## `agent-introspection`
- category: `system/memory`
- purpose: Самодиагностика агента: инструменты, правила, ограничения, качество исполнения.
- execution_mode: `reasoning-native`
- triggers: `самодиагностика агента`, `agent introspection`, `проверь свою систему`, `аудит агента`
- upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agent-introspection/SKILL.md
- raw: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/agent-introspection/SKILL.md


# Не установлены: upstream pending
- `landing-page-copywriter` — в исходном каталоге обозначен как готовящийся/не опубликованный.
- `plf-walker` — в исходном каталоге обозначен как готовящийся/не опубликованный.
- `crm-workflow` — в исходном каталоге обозначен как готовящийся/не опубликованный.
- `qualification` — в исходном каталоге обозначен как готовящийся/не опубликованный.
- `objection-handling` — в исходном каталоге обозначен как готовящийся/не опубликованный.
- `follow-up` — в исходном каталоге обозначен как готовящийся/не опубликованный.


# Project Custom Skills

Следующие skills НЕ входят в число 42 upstream AgentOS skills.
Они добавлены Катериной как отдельные project-custom skills и не меняют upstream count.

## `textwriter`
- type: `project-custom-skill`
- category: `content/writing`
- purpose: Написание публичного текста живым языком + обязательный анти-ИИ-аудит.
- execution_mode: `content-native`
- triggers: `пост`, `напиши текст`, `telegram пост`, `caption`, `лонгрид`, `продающий текст`
- adapter: `SKILL_textwriter.md`
- source_repo: https://github.com/burovakaterina86-cloud/skilltexthumaniser
- pinned_commit: `0adc1aaa9ff99c3aaa1844fa0e77b6ab6dff6cec`

## `humaniser`
- type: `project-custom-skill`
- category: `content/review`
- purpose: Финальная очистка готового публичного текста от AI-клише без изменения смысла.
- execution_mode: `content-native`
- triggers: `humaniser`, `очеловечь`, `убери нейросетевые клише`, `финальная проверка текста`
- adapter: `SKILL_humaniser.md`
- source_repo: https://github.com/burovakaterina86-cloud/skilltexthumaniser
- pinned_commit: `0adc1aaa9ff99c3aaa1844fa0e77b6ab6dff6cec`

## Mandatory public-text chain

Для каждого публичного текста Катерины использовать языковую цепочку:

`project brief → textwriter → humaniser → VOICE/BRAND_VOICE preflight → final`

Если профильный формат требует другого skill, он ставится ДО языковой цепочки.

Примеры:
- обычный пост: `content-engine (brief) → textwriter → humaniser → preflight`
- Reel: `reels → textwriter → humaniser → preflight`
- карусель: `content-engine/07_CONTENT_RULES → carousel structure → textwriter → humaniser → carousel-instagram`
- презентация: `present` для артефакта; публичные текстовые блоки внутри при необходимости проходят `textwriter → humaniser`.

`textwriter` и `humaniser` не имеют права менять Project SOURCE OF TRUTH, стратегию, факты, proof-status, CTA или психологическую функцию материала.
