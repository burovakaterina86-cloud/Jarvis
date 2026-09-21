---
name: content-engine
description: Её адаптер контент-движка, перенесённый в JARVIS — tone-of-voice aware контент-движок. Вход по её триггерам и маршрутизация; сборка комплекта остаётся за content-plan, а текст — за конвейером textwriter → humaniser. Ничего не публикует.
when_to_use: По её триггерам «напиши пост», «контент», «tone of voice», «адаптируй текст», «контент-план» — когда просьба про контент ESSA.AI пришла её словами и надо решить, каким навыком её вести.
---

# Content-engine — её адаптер контент-движка

Источник истины — `essa-ai/SKILL_content-engine.md`. Правила ниже перенесены дословно;
расхождение → верен её файл, а этот навык надо поправить.

- category: `content`
- Назначение: Tone-of-voice aware контент-движок.
- execution_mode: `content-native`
- source_load: `required for detailed/production execution`
- pinned upstream: `https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/content-engine/SKILL.md`

## Activation

- `напиши пост`
- `контент`
- `tone of voice`
- `адаптируй текст`
- `контент-план`

## Контракт исполнения

1. Сохрани цель и ограничения пользователя/Project.
2. При необходимости детальной методики загрузи pinned upstream `SKILL.md`.
3. Если `SKILL.md` ссылается на reference/template/script/config, загрузи нужный файл из той же pinned директории до выполнения соответствующего шага.
4. Не имитируй отсутствующий API/CLI.
5. Верни тот же класс результата, который обещает skill, насколько это поддерживается инструментами ChatGPT.

Шаг её контракта про перевод инструментов через `CAPABILITY_MAPPING.md` был нужен
для переноса в ChatGPT и в JARVIS не переносится: здесь инструменты те самые.

## Кто кого вызывает: `content-engine` → `content-plan`

Пара не дублируется. `content-engine` — вход по её триггерам и tone-of-voice рамка:
удержать цель, ограничения Project и голос из `VOICE.md` + `04_BRAND_VOICE.md`.
Цепочка шагов, папка комплекта и её файлы — у `content-plan`. Поэтому
**`content-engine` вызывает `content-plan`** и не повторяет его шаги и список
файлов у себя; обратного вызова нет — `content-plan` работает и без этого навыка.

Куда вести запрос:

1. Нужен комплект (пост, карусель, Reels, Stories) → `content-plan`.
2. Нужен один текст или переписать готовый → `textwriter`, затем обязательным
   вторым проходом `humaniser`; своего текстового прохода здесь нет.
3. Нужен сценарий ролика → `reels`.

## Ограничения

- Приоритет при конфликте — её порядок из `SKILL_textwriter.md`: запрос владелицы,
  `11_DECISION_LOG.md`, профильные SOURCE OF TRUTH, `VOICE.md` + `04_BRAND_VOICE.md`,
  `07_CONTENT_RULES.md`, потом навык.
- Факты, цифры, кейсы, отзывы и CTA — только из файлов `essa-ai/` или её сообщения.
- Результат — черновик: ничего не публикуешь и не отправляешь.
- Маршрут «какой файл читать» — `essa-ai/INDEX.md`. Файлы больше ~30 КБ — только `Grep`.
