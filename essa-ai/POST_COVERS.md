# POST_COVERS.md
## Контракт обложек для постов и каруселей

STATUS: `DERIVED TRANSFER GUIDE`

Источник истины: `DESIGN.md`. Этот файл ничего не меняет, а выносит правила обложек отдельно, чтобы второй Project быстро их находил.

## Фирменная типографика

- Заголовки / hooks: `Roboto Condensed Bold`.
- Основной текст: `Open Sans Regular`.
- Подзаголовки / labels: `Open Sans SemiBold`.
- Не вводить третий фирменный шрифт без отдельного решения Катерины.

## Палитра

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

## Правило обложки

**Один сильный тезис + один главный визуальный акцент.**

Использовать:
- `Roboto Condensed Bold`;
- 1–4 строки;
- graphite или light-lavender background;
- один violet-accent;
- максимум один основной объект / фото / интерфейс;
- много воздуха.

Не использовать:
- длинный подзаголовок на 6 строк;
- много иконок;
- пять цветов;
- 3D ради 3D;
- длинный CTA на обложке.

## Фото на обложке

Фото может быть более ярким и контрастным, чем внутренние слайды, и быть одним из главных элементов hook-композиции. Оно должно помогать остановить внимание, не мешая заголовку.

Не закрывать лицо текстом. Не делать случайный crop. Фото не используется как filler.

## Instagram carousel

Canvas: `1080 × 1350 px`.

Safe zone: `72–88 px`, базовый ориентир `80 px`.

Cover / Hook:
- `Roboto Condensed Bold`;
- рабочий размер `88–120 px`;
- line-height `0.92–1.02`;
- hook должен считываться за 1–2 секунды.

Перед production всегда читать полный `DESIGN.md` и `SKILL_carousel-instagram.md`.
