# Skill Adapter: `present`

- category: `content/artifact`
- purpose: Создание HTML-презентаций/отчётов по исходной методике AgentOS.
- execution_mode: `artifact`
- source_load: `required for detailed/production execution`
- pinned upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/present/SKILL.md
- raw source: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/present/SKILL.md

## Activation
- `презентация`
- `слайды`
- `html presentation`
- `отчёт в слайдах`

## ChatGPT execution contract
1. Сохрани цель и ограничения пользователя/Project.
2. При необходимости детальной методики загрузи pinned upstream `SKILL.md`.
3. Если `SKILL.md` ссылается на reference/template/script/config, загрузи нужный файл из той же pinned директории до выполнения соответствующего шага.
4. Переведи Claude Code-specific инструменты через `CAPABILITY_MAPPING.md`.
5. Не имитируй отсутствующий API/CLI.
6. Верни тот же класс результата, который обещает skill, насколько это поддерживается инструментами ChatGPT.
