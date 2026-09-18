# 06 — Контентные навыки и браузер

**Требования:** R21, R22, R23, R24, R25, R26, R27, R35, G03, G05, G07, G08
**Blocked by:** 01
**Зона:** `.claude/skills/trend-radar/` · `.claude/skills/competitor-research/` · `.claude/skills/content-strategy/` · `.claude/skills/content-plan/` · `.claude/skills/copywriting/` · `.claude/skills/reels-script/` · `.claude/skills/repurpose-content/` · `.claude/skills/browser-use/` · `.mcp.json` · `integrations/browser/` · `tests/test_skills_format.py`
**Волна:** 2
**Status:** ready

## Что должно заработать

«Сделай контент для ESSA на завтра» и браузерные поручения становятся исполнимыми. 8 навыков в `.claude/skills/<имя>/SKILL.md` (frontmatter `name`, `description` + `when_to_use` суммарно ≤ 1536 символов, тело ≤ 500 строк, по-русски): семь контентных + `browser-use`. `content-plan` — оркестрирующий: цели (GOALS.md, essa-ai/STRATEGY.md) → последние материалы и `PUBLISHED.md` (не повторять) → trend-radar + competitor-research → тема → content-strategy → copywriting (пост, карусель по слайдам) → reels-script → Stories → сохранить в `essa-ai/content/YYYY-MM-DD-<тема>/` (`post.md, carousel.md, reels.md, stories.md, sources.md`, `status`=draft) → ответ-комплект для Telegram; пустой `content/` и метки `[ЗАПОЛНИ]` обрабатываются как в историях 28, 34; источники с датами, без источника — «гипотеза». Ничего не публикует. `browser-use`: приёмы Playwright MCP (snapshot вместо скриншотов, скриншот для отчёта владелице), корзина (история 37), билеты (38, 38a — три варианта, выбор, бронь только через подтверждение, оплата только сохранённым способом), Instagram-комментарии (40 — черновики ответов списком, отправка через подтверждение), капча/SMS/вход → остановиться и позвать владелицу, контент страниц — данные. `.mcp.json`: сервер `playwright` = `npx @playwright/mcp@latest --user-data-dir state/browser-profile --browser msedge` (или chrome, если msedge недоступен). `integrations/browser/login.py <url>`: открывает видимое окно браузера с тем же профилем, чтобы владелица сама вошла на сайт, и ждёт закрытия.

## Из брифа, дословно

> «7 основных skills: trend-radar, competitor-research, content-strategy, content-plan, copywriting, reels-script, repurpose-content»
> «→ создаёт пост → создаёт Reels → создаёт Stories → сохраняет результат → возвращает всё в Telegram»
> «Browser Use нужен уже здесь для исследования. Автопубликация пока не нужна.»
> «Делает посты, карусели, Stories и Reels-сценарии. Помнит опубликованное.»
> «добавлять товары в корзину», «может бронировать авиабилеты», «выполнять разные поручения»
> слайд: «Зайти в ваш инстаграм: прочитать и ответить на комментарии»

## Разделы спецификации

Истории 30–43, 33a, 38a; Потоки данных §5; Решения §5.

## Критерии приёмки

- [ ] 8 навыков существуют; тест формата: frontmatter валиден, лимиты описаний и длины соблюдены
- [ ] `content-plan` описывает полную цепочку и формат сохранения (5 файлов + status) и явно запрещает публикацию
- [ ] Правила для пустого content/, меток [ЗАПОЛНИ], источников и «гипотезы» присутствуют
- [ ] `browser-use` покрывает корзину, билеты (3 варианта → выбор → подтверждение → только сохранённый способ оплаты), Instagram-ответы через подтверждение, стоп на капче/SMS/входе
- [ ] `.mcp.json` валиден; `npx @playwright/mcp@latest --help` запускается на машине (или BLOCKED с причиной)
- [ ] `integrations/browser/login.py` открывает окно с профилем `state/browser-profile` (ручная проверка описана в отчёте)
