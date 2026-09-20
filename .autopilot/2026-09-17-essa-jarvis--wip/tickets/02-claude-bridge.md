# 02 — Мост к Claude Code: ходы, сессии, очередь, события

**Требования:** R02, R03, R04, R05, R06, R11, R13
**Blocked by:** 01
**Зона:** `runtime/claude_bridge.py` · `runtime/sessions.py` · `runtime/task_router.py` · `runtime/events.py` · `runtime/jarvis-turn.md` · `tests/test_bridge.py` · `tests/fake_claude/`
**Волна:** 2
**Status:** ready

## Что должно заработать

Python умеет выполнить один ход Claude Code и вернуть результат, не зная ничего про Telegram. `run_turn` запускает `claude -p` с флагами из спецификации (Решения §2), промпт через stdin, UTF-8, `claude.cmd` через `shutil.which`, окружение без `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`/`CLAUDECODE*`, cwd = корень JARVIS. Поток stream-json разбирается по строкам: каждое событие → колбэк `on_event` и `events.emit` в `state/events.jsonl` (поля `ts, session, agent, task, status, progress` + тип). `session_id` берётся из `system/init` или `result` и сохраняется; следующий ход идёт с `--resume`; ошибка resume → один повтор без него с пометкой `new_session=True`. `api_retry` с `rate_limit`/`authentication_failed` превращаются в понятный статус TurnResult. `stop(run_id)` убивает дерево (`taskkill /T /F /PID`). Сообщение о переполнении контекста → сброс сессии и сводка последней задачи в новый ход. `task_router`: FIFO на чат, одна активная задача на чат, глобальный замок на браузерные задачи (флаг `uses_browser` у job), дневной бюджет запусков из `JARVIS_DAILY_RUN_BUDGET`. `jarvis-turn.md` — короткая добавка к системному промпту (кто владелица, язык ответа — русский, формат ответа для Telegram, про недоверенный контент — ссылка на rules).

## Из брифа, дословно

> «маленький Python-мост вызывает Claude Code через CLI, сохраняет `session_id`, продолжает разговор через `--resume`»
> «Claude Code через существующую подписку»
> «История — compress.»

## Разделы спецификации

Истории 2–5, 8–9, 14, 22a; Потоки данных §1; Решения §2, §9, §10, §11; Границы: `claude_bridge`, `sessions`, `task_router`, `events`; Швы §1.

## Критерии приёмки

- [ ] Тест на фейковом `claude` (скрипт, печатающий записанный stream-json): текст ответа, `session_id`, стоимость разобраны
- [ ] Второй ход вызывается с `--resume <id>`; фейк, падающий на resume → один повтор без resume, `new_session=True`
- [ ] Строка запуска содержит `--permission-mode dontAsk` и не содержит bypass; `ANTHROPIC_API_KEY` отсутствует в окружении дочернего процесса (тест)
- [ ] Промпт > 40 KB передаётся без ошибки (stdin)
- [ ] События пишутся в `events.jsonl` с обязательными полями; `rate_limit` → статус `rate_limited` с текстом для человека
- [ ] Очередь: два job в один чат выполняются последовательно, позиция возвращается; два браузерных job в разные чаты — последовательно
- [ ] `stop` прерывает работающий фейк за < 3 с
- [ ] Дымовой тест `tests/smoke_real_claude.py` (не в общем прогоне): реальный `claude -p` отвечает на «ответь одним словом: привет» — запусти один раз, результат запиши в отчёт
