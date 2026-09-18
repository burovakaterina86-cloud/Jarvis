# Skill Adapter: `carousel-instagram`

- category: `social/artifact`
- purpose: создание Instagram-каруселей 1080×1350 с сохранением стратегии, функции материала, голоса и активной дизайн-системы Project.
- execution_mode: `artifact`
- source_load: `required for detailed/production execution`
- pinned upstream: https://github.com/qwwiwi/agentos-skills-public/blob/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/carousel-instagram/SKILL.md
- raw source: https://raw.githubusercontent.com/qwwiwi/agentos-skills-public/3a8efdcaa8dce35ebaafd389e4b98ac79a0b0802/skills/carousel-instagram/SKILL.md

---

## Activation

Активировать по смыслу для запросов:

- `карусель instagram`
- `слайды 1080x1350`
- `сделай карусель`
- `оформи карусель`
- `отрендери карусель`
- `собери слайды`
- `сделай carousel`

---

# 1. РОЛЬ SKILL

Этот skill отвечает за:

- визуальную сборку карусели;
- композицию;
- иерархию;
- раскладку текста;
- размещение фото / скриншотов;
- применение активного style-mode;
- технический render;
- visual QA.

Этот skill НЕ является источником:

- стратегии;
- аудитории;
- позиционирования;
- фактов;
- кейсов;
- proof;
- funnel-stage;
- CTA;
- Tone of Voice;
- продуктовых решений.

---

# 2. ПРИОРИТЕТЫ

При конфликте использовать:

1. текущий прямой запрос Катерины;
2. `11_DECISION_LOG.md`;
3. профильные SOURCE OF TRUTH;
4. `06_CONTENT_PLAN_30_DAYS.md`;
5. `07_CONTENT_RULES.md`;
6. `VOICE.md`;
7. `04_BRAND_VOICE.md`;
8. `DESIGN.md`;
9. этот adapter;
10. upstream `carousel-instagram`.

Project source-of-truth всегда выше AgentOS skill.

---

# 3. ОБЯЗАТЕЛЬНЫЕ ИСТОЧНИКИ ПЕРЕД PRODUCTION

Если карусель предназначена для реальной публикации, определить:

```text
FUNNEL_STAGE
FUNCTION
BELIEF_BEFORE
BELIEF_AFTER
MAIN_IDEA
PROOF
NEXT_STEP
CTA
```

Если параметры уже заданы в `06_CONTENT_PLAN_30_DAYS.md`:

- не заменять их;
- не «усиливать» стратегию;
- не придумывать другой CTA;
- не менять психологический переход.

Использовать:
- `07_CONTENT_RULES.md` — для структуры и функции;
- `VOICE.md` + `04_BRAND_VOICE.md` — для языка;
- `DESIGN.md` — для визуального исполнения.

---

# 4. ОБЯЗАТЕЛЬНЫЙ PUBLIC-TEXT PIPELINE

Для готового публичного текста карусели:

```text
content brief
→ slide functions
→ textwriter
→ humaniser
→ VOICE / BRAND_VOICE preflight
→ carousel-instagram
```

`textwriter` и `humaniser` не имеют права менять:

- FUNNEL_STAGE;
- FUNCTION;
- BELIEF_BEFORE;
- BELIEF_AFTER;
- MAIN_IDEA;
- PROOF;
- NEXT_STEP;
- CTA;
- доказательный статус.

Если Катерина уже дала утверждённый текст слайдов:

- не переписывать его заново;
- разрешены только минимальные layout-правки;
- сокращение допустимо только без изменения смысла;
- важные формулировки не заменять ради красоты.

---

# 5. ACTIVE STYLE CONSTRAINT

Использовать только:

- `STYLE_01 — SYSTEM / PROCESS`
- `STYLE_02_LIGHT — EDITORIAL / STORY`
- `STYLE_02_DARK — EDITORIAL / STORY (dark variant)`

Не использовать и не предлагать без прямого запроса Катерины:

- `STYLE_03`
- `STYLE_04`
- `STYLE_05`

Не создавать новые style-ID самостоятельно.

---

# 6. STYLE SELECTION

Если Катерина указала конкретный style-mode:

использовать его.

Если style-mode не указан:

## PROCESS / SYSTEM / WORKFLOW / MAP / LEVELS

→ `STYLE_01`

## POSITIONING / STORY / OBSERVATION / EXPLANATION / BELIEF SHIFT

→ `STYLE_02_LIGHT`

## Если Катерина просит тёмную editorial-версию

→ `STYLE_02_DARK`

По умолчанию для editorial использовать:

`STYLE_02_LIGHT`.

Не выбирать STYLE_02_DARK только потому, что «тёмный выглядит эффектнее».

---

# 7. STYLE_01 — EXECUTION CONTRACT

## Назначение

Системы, процессы, workflow, карты, уровни, причинно-следственные связи.

## Visual language

Использовать:
- dark graphite;
- white;
- violet / lavender accents;
- крупный display;
- cards;
- thin dividers;
- numbering;
- arrows;
- process blocks;
- interface-like modules;
- blurred / darkened photo background только если помогает смыслу.

Не использовать:
- случайный orange;
- yellow;
- rainbow;
- glossy 3D;
- декоративные элементы без функции.

Главный вопрос:

**понятно ли человеку, как устроен процесс?**

---

# 8. STYLE_02_LIGHT — EXECUTION CONTRACT

## Назначение

Positioning, storytelling, observation, explanation, belief shift, brand statement.

## Visual language

Использовать:
- light / lavender base;
- graphite text;
- violet accents;
- editorial grid;
- крупную узкую типографику;
- рамки;
- простую геометрию;
- line-icons;
- large numbering;
- contrast cards;
- фото точечно;
- много воздуха.

Не превращать:
- в lifestyle-журнал;
- в Canva-template;
- в glossy AI-ad.

---

# 9. STYLE_02_DARK — EXECUTION CONTRACT

Это dark-variant STYLE_02_LIGHT.

## Назначение

Та же editorial-задача, но на тёмной базе.

## Visual language

Использовать:
- `BG_DARK_PRIMARY`;
- `BG_DARK_SECONDARY`;
- `TEXT_ON_DARK`;
- `VIOLET_PRIMARY`;
- `VIOLET_SOFT`;
- `LAVENDER`;
- editorial grid;
- frames;
- cards;
- large headline;
- мягкие semi-transparent surfaces.

Не превращать:
- в STYLE_01;
- в техническую workflow-схему без необходимости;
- в 3D / glossy / neon visual.

---

# 10. DESIGN TOKENS

Всегда читать актуальные значения из `DESIGN.md`.

Текущая typography:

```text
HEADLINE = Roboto Condensed Bold
BODY = Open Sans Regular
SUPPORT = Open Sans SemiBold
```

Текущая core palette:

```text
BG_DARK_PRIMARY      #0D1015
BG_DARK_SECONDARY    #292834

BG_LIGHT_PRIMARY     #F1F0FA
BG_LIGHT_SECONDARY   #ECE9FA

TEXT_ON_DARK         #F7F5FA
TEXT_ON_LIGHT        #14151A
TEXT_MUTED_DARK      #B8B4C2
TEXT_MUTED_LIGHT     #686775

VIOLET_PRIMARY       #7158E7
VIOLET_STRONG        #592DE2
VIOLET_SOFT          #9F87EC
LAVENDER             #C8BFE7
```

Если `DESIGN.md` позже обновлён:

использовать `DESIGN.md`, а не значения, продублированные здесь.

---

# 11. TECHNICAL INVARIANTS

Instagram carousel:

`1080 × 1350 px`

Safe zone:
`72–88 px`

Default:
`80 px`

Требования:
- mobile-first readability;
- no clipping;
- no overflow;
- no text outside safe zone;
- no text over face/eyes;
- no important microtext;
- consistent grid;
- consistent typography;
- consistent palette;
- one visual system per carousel.

---

# 12. TYPOGRAPHY RULES

## Cover / Hook

`Roboto Condensed Bold`

Рабочий диапазон:
`88–120 px`

## Slide title

`Roboto Condensed Bold`

Рабочий диапазон:
`60–84 px`

## Body

`Open Sans Regular`

Рабочий диапазон:
`34–42 px`

## Labels / badges

`Open Sans SemiBold`
или
`Roboto Condensed Bold`

Рабочий диапазон:
`24–30 px`

## Critical rule

Если текст не помещается:

1. проверить, можно ли сократить без изменения смысла;
2. изменить перенос строк;
3. изменить композицию;
4. только после этого слегка уменьшать размер.

Не делать важный текст мелким ради вмещения.

---

# 13. CAROUSEL SEMANTIC ROUTE

Типовая логика:

```text
HOOK
↓
IDENTIFICATION
↓
PROBLEM
↓
CONFLICT
↓
PATTERN INTERRUPT
↓
NEW BELIEF
↓
MECHANISM / PROOF
↓
BRAND IDEA
↓
CTA
```

Количество слайдов можно менять.

Нельзя:
- удалить ключевой переход;
- переставить смысловые блоки ради дизайна;
- продать раньше;
- придумать proof;
- усилить case;
- изменить CTA.

Главный критерий:

**сделала ли карусель свою работу в воронке?**

---

# 14. CAROUSEL RHYTHM PASS

STATUS: `MANDATORY PRE-RENDER PASS`

Перед render ОБЯЗАТЕЛЬНО построить внутреннюю карту карусели:

```text
SLIDE 01 — semantic function / visual type
SLIDE 02 — semantic function / visual type
SLIDE 03 — semantic function / visual type
...
```

Допустимые visual types:

```text
PHOTO
TEXT
CARD
SCHEME
PROCESS
STATEMENT
CTA
```

Пример:

```text
01 HOOK              → PHOTO
02 IDENTIFICATION    → CARD
03 PROBLEM           → PHOTO
04 CONFLICT          → TEXT
05 PATTERN INTERRUPT → STATEMENT
06 NEW BELIEF        → PROCESS
07 MECHANISM         → SCHEME
08 BRAND IDEA        → STATEMENT
09 CTA               → PHOTO
```

Эта карта является внутренней production-проверкой.
Не показывать её пользователю без запроса.

## Проверить до render

- нет ли одинакового dominant layout на соседних слайдах;
- нет ли двух `PHOTO-DOMINANT` слайдов подряд без смысловой причины;
- нет ли визуально однообразного блока из 3+ слайдов;
- не повторяется ли одна и та же card-composition слишком часто;
- отличается ли `BRAND IDEA` от `CTA`;
- соответствует ли visual type функции слайда;
- не добавлена ли фотография только ради заполнения пространства;
- финальные слайды усиливают завершение, а не повторяют друг друга.

## Допустимые исключения

Два photo-dominant слайда подряд допустимы, если они образуют осознанную смысловую пару, например:
- before → after;
- comparison;
- последовательность одного события;
- доказательная пара, где оба изображения нужны.

## Если ритм слабый

Менять:
- композицию;
- visual type;
- размещение фото;
- размер блоков;
- плотность;
- визуальный акцент.

НЕ менять:
- FUNNEL_STAGE;
- FUNCTION;
- BELIEF_BEFORE;
- BELIEF_AFTER;
- MAIN_IDEA;
- PROOF;
- NEXT_STEP;
- CTA;
- смысловой порядок слайдов.

---

# 15. PHOTO / SCREENSHOT RULES

Фото и screenshots использовать только когда они помогают смыслу.

## COVER PHOTO

На первом слайде фотография может быть:
- более яркой;
- более контрастной;
- визуально самостоятельной;
- одним из главных элементов hook-композиции.

При этом headline должен оставаться главным смысловым входом.

## INTERNAL PHOTOS

На внутренних слайдах фотография должна быть вторична по отношению к смыслу и тексту.

Для dark styles по умолчанию:
- слегка затемнять photo;
- ориентир: примерно `15–25%`;
- при необходимости немного снижать contrast;
- допустима лёгкая холодная тонировка под graphite / violet palette.

Не затемнять механически, если фото уже спокойное и не конкурирует с текстом.

Критерий:

**главный текст и смысл должны считываться раньше фотографии.**

## PHOTO PURPOSE CHECK

Перед добавлением фото спросить:

**«Что это фото добавляет функции этого слайда?»**

Фото допустимо, если оно:
- показывает автора;
- поддерживает ситуацию;
- создаёт нужный человеческий контакт;
- показывает процесс;
- является proof / result;
- помогает функции слайда.

Если ответ только:

**«Чтобы было красивее»**

— фото не использовать.

## Общие photo-rules

Можно:
- portrait;
- work context;
- background;
- отдельный photo-block.

Нельзя:
- закрывать лицо текстом;
- деформировать;
- делать случайный crop;
- использовать фото как filler;
- ставить два photo-dominant слайда подряд без смысловой причины.

## Screenshots

Можно:
- browser;
- ChatGPT;
- interface;
- workflow step;
- before/after.

Требования:
- важная зона читаема;
- лишнее обрезано;
- нет персональных / секретных данных;
- screenshot не заменяет объяснение.

---

# 16. ICONS / DECOR

Использовать:
- simple line-icons;
- geometric forms;
- restrained flat-icons.

Не смешивать внутри одного материала:
- 3D icons;
- line icons;
- emoji;
- hand-drawn icons.

Decor должен поддерживать структуру.

Если decor ничего не объясняет:

удалить.

---

# 17. RENDERING

Upstream skill использует HTML/CSS + Playwright.

В ChatGPT Project:

1. использовать реальный доступный code/render workflow;
2. если доступен детерминированный HTML/CSS → PNG render — использовать его;
3. после чернового render собрать contact sheet / общий preview всех слайдов и выполнить whole-carousel rhythm check;
4. если полноценный contact sheet технически недоступен — выполнить эквивалентную последовательную проверку всей карусели до финальной выдачи;
5. текст и типографику не генерировать как image-generation;
6. не рисовать «похожий шрифт» через генеративную картинку;
7. если реальный render недоступен — не притворяться, что PNG создан;
8. в таком случае вернуть:
   - production-ready HTML/CSS;
   - slide specification;
   - или другой реально доступный artifact-класс.

Не утверждать, что Playwright / CLI / browser command запускался, если он не запускался.

---

# 18. OUTPUT CONTRACT

Если render доступен:

обязательно для внутреннего QA:
- собрать общий preview / contact sheet;
- проверить visual rhythm всей карусели до финальной выдачи.

Пользователю выдать:
- отдельный PNG для каждого слайда;
- общий preview/contact sheet — если он помогает оценить карусель или Катерина просит его;
- исходный HTML/CSS, если он полезен для редактирования.

Если Катерина просит только текст/структуру:

не запускать лишний artifact workflow.

Если Катерина просит только design-test:

не менять текст и стратегию.

---

# 19. VISUAL QA

Перед финалом проверить:

## Strategy

[ ] FUNNEL_STAGE сохранён  
[ ] FUNCTION сохранена  
[ ] BELIEF_BEFORE → BELIEF_AFTER сохранён  
[ ] MAIN_IDEA сохранена  
[ ] PROOF не усилен  
[ ] CTA сохранён  

## Text

[ ] public-text pipeline пройден, если текст создавался сейчас  
[ ] VOICE соблюдён  
[ ] нет выдуманных фактов  
[ ] нет лишнего AI-jargon  

## Design

[ ] выбран только активный style-mode  
[ ] STYLE_03 / 04 / 05 не применены  
[ ] Roboto Condensed + Open Sans  
[ ] core palette из DESIGN.md  
[ ] нет yellow/orange core-accent  
[ ] safe zone соблюдена  
[ ] no clipping  
[ ] body читается на телефоне  
[ ] ключевой hook считывается первым  
[ ] нет текста поверх лица  
[ ] нет лишнего decor  
[ ] все слайды выглядят одной системой  

## Rhythm

[ ] выполнен `CAROUSEL RHYTHM PASS`  
[ ] карусель просмотрена целиком как последовательность  
[ ] при доступном render просмотрен contact sheet / общий preview  
[ ] соседние слайды не повторяют одну dominant composition без причины  
[ ] нет двух photo-dominant слайдов подряд без осознанной смысловой причины  
[ ] нет визуально однообразного блока из 3+ слайдов  
[ ] внутренние фото не перетягивают внимание с текста  
[ ] BRAND IDEA и CTA визуально различаются  
[ ] финальные слайды усиливают завершение, а не повторяют друг друга  

---

# 20. FAIL CONDITIONS

Остановиться и исправить до выдачи, если:

- текст не помещается и был механически уменьшен до мелкого;
- CTA изменился;
- proof усилен;
- добавлен новый кейс;
- style-mode не активен;
- появился yellow/orange core-accent без прямого запроса;
- использованы чужие фирменные элементы из reference;
- carousel выглядит как набор разных шаблонов;
- два соседних слайда механически повторяют один dominant layout без смысловой причины;
- два photo-dominant слайда стоят подряд без осознанной смысловой причины;
- BRAND IDEA и CTA собраны в почти одинаковой dominant composition;
- внутреннее фото заметно перетягивает внимание с главного текста;
- whole-carousel rhythm check не выполнен;
- Image Generation использована вместо реальной типографики;
- заявлен render, который фактически не выполнялся.

---

# 21. MAIN RULE

Не оптимизировать карусель под:

**«сделать красивее любой ценой».**

Оптимизировать под:

**«сделать смысл понятнее, удержать нужный психологический переход и оформить это в узнаваемой системе Катерины».**
