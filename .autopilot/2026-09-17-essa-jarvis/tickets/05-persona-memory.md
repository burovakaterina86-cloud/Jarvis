# 05 — Личность, память, правила и папка ESSA

**Требования:** R08, R10, R11, R12, R19, R29i, R30, R33, R34
**Blocked by:** 01
**Зона:** `CLAUDE.md` · `SOUL.md` · `GOALS.md` · `MEMORY.md` · `.claude/rules/` · `.claude/hooks/memory_notice.py` · `.claude/hooks/capture_learning.py` · `.claude/hooks/pre_compact.py` · `.claude/hooks/session_start.py` · `essa-ai/` · `memory/` · `scripts/check_context_size.py` · `tests/test_memory_hooks.py`
**Волна:** 2
**Status:** ready

## Что должно заработать

Агент знает, кто он, чьи цели, что где лежит, и как сохранять память — при этом каждый ход грузит ≤ 12 KB. Корневой `CLAUDE.md` (≤ 5 KB) — карта: `@SOUL.md @GOALS.md @MEMORY.md`, где лежат навыки, `essa-ai/`, `memory/`, `docs/REFERENCE.md`, `drafts/`, правило «читай только нужное», уровни безопасности в двух строках со ссылкой на rules. `SOUL.md`, `GOALS.md` — черновики с метками `[ЗАПОЛНИ: …]`, без выдуманных фактов о владелице и ESSA. `MEMORY.md` — заголовок и правило формата. `.claude/rules/`: `safety.md`, `approvals.md`, `memory.md` (когда что сохранять: сессия / MEMORY.md / memory/decisions|projects|people / essa-ai/knowledge), `untrusted-content.md`, `delegation.md` (текст из истории 56). `essa-ai/` — PROFILE, VOICE, AUDIENCE, PRODUCTS, STRATEGY, ANALYTICS.md с метками `[ЗАПОЛНИ]`, `content/PUBLISHED.md` (шапка таблицы), `knowledge/`. `memory/{decisions,projects,people,episodes}/` с `.gitkeep`. Хуки: `memory_notice.py` (PostToolUse: запись в MEMORY.md/memory/essa-ai/knowledge → additionalContext «сообщи владелице: 🧠 запомнил: …»), `capture_learning.py` (Stop: один раз за ход напомнить про урок/алгоритм, не зацикливать — проверка `stop_hook_active`), `pre_compact.py` (строка в `memory/episodes/YYYY-MM.jsonl`), `session_start.py` (MEMORY.md > 5 KB → additionalContext «сожми MEMORY.md»). Хуки не должны падать: ошибка → exit 0 без эффекта (они не защитные). `scripts/check_context_size.py` печатает размеры и exit 1 при превышении бюджета.

## Из брифа, дословно

> «всегда загружаем очень мало. `CLAUDE.md + SOUL.md + компактный MEMORY.md + GOALS.md`»
> «CLAUDE.md 3–5 KB / SOUL.md 1–2 KB / MEMORY.md 3–5 KB / GOALS.md 1–2 KB»
> «Агент должен сам решать: это информация только для текущего разговора; или: это решение надо сохранить надолго.»
> «capture-learning.py»

## Разделы спецификации

Истории 17–23, 22a, 22b, 24, 28, 56; Потоки данных §3; Решения §7; Структура каталогов.

## Критерии приёмки

- [ ] `scripts/check_context_size.py` проходит: CLAUDE ≤ 5 KB, SOUL ≤ 2 KB, GOALS ≤ 2 KB, MEMORY ≤ 5 KB, сумма ≤ 12 KB
- [ ] В `SOUL.md`, `GOALS.md`, `essa-ai/*.md` нет утверждений о владелице/ESSA без метки `[ЗАПОЛНИ]` (ревьюер проверяет глазами)
- [ ] Все 5 правил в `.claude/rules/` существуют, `delegation.md` содержит условие делегирования и цикл из истории 56
- [ ] Хуки памяти протестированы на записанных JSON-входах: memory_notice даёт additionalContext только для путей памяти; capture_learning не срабатывает при `stop_hook_active=true`; pre_compact пишет валидную JSONL-строку; session_start реагирует на > 5 KB
- [ ] Любое исключение в этих хуках → exit 0 (тест)
- [ ] Файл `CLAUDE.md` в корне не содержит блока autopilot (он в AGENTS.md)
