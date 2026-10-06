# Этап 6. Карусели (2 в неделю, в плане 3–4 варианта)

Вход: `carousels_pool.json` (после `collect` и `pool`: посты авторов типа Sidecar, ≤14 дней, порог 1000 комментариев, при нехватке 300 — пометь «порог 300»).
Выход: `carousels.json`, слайды — `raw/carousels/<код>/01.jpg…`.

1. Выбери 6–8 лучших, не больше одной от автора, тема в нише, не из `history.json`.
2. **Слайды качай сразу** — ссылки Instagram протухают за часы: `python -m integrations.content_plan slides <папка_недели> КОД…` (бесплатно, из уже собранных данных, только с серверов Instagram). Анимированные слайды приходят пустыми кадрами — так и пиши в `availability_note`, не выдумывай.
3. Прочитай картинки: текст слайдов дословно и коротко визуал.
4. Выбери 3–4 варианта, переведи слайды по `05-text-rules.md`, укажи кодовое слово и связь с лид-магнитом.

Выход:
```json
{"carousels":[{"code","url","author","age_days","comments","likes","slides_count","x_author","format",
  "title_ru","hook_ru","why","cta_word_ru","slides_ru":[],"visual_notes","lead_magnet_link"}],
 "stats":{"collected","carousels_found","passed_threshold","threshold_used","cost_usd_estimate"},
 "rejected":[{"code","author","comments","reason"}]}
```

Оформление самой карусели в её стиле — навык `carousel-instagram` (после того, как она выберет вариант). В план чужие картинки не вставляются.
