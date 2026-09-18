# Skill Adapter: `humaniser`

- type: `project-custom-skill`
- category: `content/review`
- purpose: Финальная очистка готового публичного текста от нейросетевых клише без изменения смысла и без выдумывания фактов.
- execution_mode: `content-native`
- source_repo: https://github.com/burovakaterina86-cloud/skilltexthumaniser
- pinned_commit: `0adc1aaa9ff99c3aaa1844fa0e77b6ab6dff6cec`
- pinned_upstream: https://github.com/burovakaterina86-cloud/skilltexthumaniser/blob/0adc1aaa9ff99c3aaa1844fa0e77b6ab6dff6cec/skills/humaniser/SKILL.md
- license: MIT

## Activation

Использовать ОБЯЗАТЕЛЬНО вторым языковым проходом после `textwriter` для каждого публичного текста Катерины.

Пайплайн:
`content brief → textwriter → humaniser → VOICE/preflight → final`

## Роль в Project

`humaniser` не имеет права менять стратегию, факты или функцию материала.

Приоритет:
1. текущий запрос Катерины;
2. `11_DECISION_LOG.md`;
3. профильные SOURCE OF TRUTH;
4. `VOICE.md` + `04_BRAND_VOICE.md`;
5. `07_CONTENT_RULES.md`;
6. `textwriter` draft;
7. этот skill.

## Обязательные Project overrides

DETECTOR может отмечать AI-паттерны, но REWRITER НЕ ИМЕЕТ ПРАВА:

- менять FUNNEL_STAGE;
- менять FUNCTION;
- менять BELIEF_BEFORE → BELIEF_AFTER;
- менять MAIN_IDEA;
- менять CTA;
- удалять или добавлять PROOF;
- менять цифры, даты, имена или статус доказательства;
- придумывать конкретику;
- придумывать эмоции, сцены, воспоминания, внутренние реплики или диалоги;
- добавлять новый авторский сленг;
- добавлять мат;
- превращать гипотезу в факт или обещание;
- удалять утверждённые брендовые фразы только потому, что их конструкция похожа на общее клише.

Если утверждённая брендовая формула конфликтует с общим правилом humaniser, сохранить брендовый смысл и найти более естественное окружение вокруг него.

## Три обязательных прохода

1. DETECTOR
   Найди канцелярит, пустые связки, fake-energy, шаблонную близость, одинаковый ритм, лишние усилители и другие AI-маркеры.

2. REWRITER
   Исправь только языковую форму. Не делай текст длиннее без необходимости. Не добавляй новую информацию.

3. CHECKER
   Сверь:
   - смысл сохранён;
   - голос соответствует `VOICE.md`;
   - ничего не выдумано;
   - CTA и психологический переход сохранены;
   - факты и proof-status не изменены;
   - текст можно прочитать вслух естественно.

## Output contract

В обычном production-режиме:
- НЕ показывать таблицу `Было → Стало`;
- НЕ показывать служебные замечания;
- вернуть только очищенную финальную версию.

Таблицу аудита показывать только по прямому запросу Катерины.
