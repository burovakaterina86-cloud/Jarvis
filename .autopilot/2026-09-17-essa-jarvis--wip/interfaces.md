# Интерфейсы ESSA-JARVIS

## Правила проекта

- Стек: Python 3.12 (Windows 10/11), python-telegram-bot ≥ 21, aiohttp, faster-whisper, pyyaml, pytest + pytest-asyncio. Node есть на машине (для `npx @playwright/mcp`).
- Окружение: `.venv` в корне (создаёт таск 01). Python: `.venv\Scripts\python.exe`.
- Тесты: `.venv\Scripts\python.exe -m pytest -q` из корня. Дымовые тесты с реальным claude — `tests/smoke_*.py`, в общий прогон не входят (`-m "not smoke"` или отдельный файл без префикса test_).
- Запуск: `start.bat` → `python -m integrations.telegram`.
- Кодировка: UTF-8 везде, `encoding="utf-8"` при открытии файлов и в subprocess.
- Секреты: только в `.env` (его заполняет владелица). Никогда не читать, не печатать, не логировать значения. `state/` и `inbox/` в .gitignore.
- Не трогать: `.autopilot/`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/MVP.md`, файлы вне своей зоны.
- Нет пакета — вернуть `BLOCKED` с названием, а не ставить что-то вне `requirements.txt` (таск 01 создаёт venv и ставит перечисленное; добавить пакет в requirements может только таск, чья зона его включает, с обоснованием в отчёте).
- Флага `--dangerously-skip-permissions` / `bypassPermissions` не должно быть нигде.
- Язык пользовательских текстов (бот, навыки, правила): русский.

## Общие контракты

- **Уровни:** `READ`, `WRITE`, `EXTERNAL`, `MONEY` (включает IRREVERSIBLE и удаление), `DENY`.
- **Approvals API:** `POST http://127.0.0.1:<port>/approve`, заголовок `X-Jarvis-Token: <token>`, тело `{"level": "EXTERNAL|MONEY", "tool": str, "summary": str, "details": dict}` → `200 {"decision": "allow"|"deny", "reason": str}`; 401 без токена. Порт: `state/approvals.port` (текст), токен: `state/secrets/approvals.token`. Таймаут 600 с. Guard: нет файла порта/соединения → deny.
- **policy.yaml:** `external: {<вид>: ask|auto}`, `money_kinds: [...]`, `purchase_limit_env: JARVIS_PURCHASE_LIMIT_RUB`, `deny_paths: [...]`, `protected_write_paths: [...]`, `allow_write_paths: [...]`, `rules: [{tool: <glob>, match: <regex по json аргументов>, level: ..., kind: ...}]`. Точная схема — решение таска 01, описать в шапке файла.
- **Событие (`state/events.jsonl`, одна JSON-строка):** `{"ts": ISO8601, "type": "user_message|assistant_message|tool_use|tool_result|approval_request|approval_decision|blocked|result|error", "session": str|null, "agent": "jarvis"|<субагент>, "task": str, "status": "queued|working|waiting_approval|done|failed", "progress": float|null, ...}`.
- **TurnResult:** `text: str, session_id: str|None, new_session: bool, cost_usd: float|None, status: "ok"|"stopped"|"rate_limited"|"auth_required"|"error", error: str|None`.
- **Сессии:** `state/sessions.json` = `{"<chat_id>": "<session_id>"}`, атомарная запись (tmp + replace).

## Границы, решённые в спецификации

| Модуль | Владеет | Выставляет | Прячет |
|---|---|---|---|
| `gateway` (integrations/telegram) | Telegram: апдейты, allow-list, команды, кнопки, отправка | `run()`; `send(chat_id, text|file)`; `ask_buttons(chat_id, text, options) -> choice` | библиотеку Telegram, разбиение сообщений, rate-limit Telegram |
| `claude_bridge` (runtime) | запуск Claude Code и разбор потока | `async run_turn(prompt, session_id|None, on_event) -> TurnResult{text, session_id, cost, status}`; `stop(run_id)` | флаги CLI, окружение, stdin, парсинг stream-json, retry resume, Windows-убийство дерева |
| `sessions` | сессии | `get(chat_id)`, `set(chat_id, sid)`, `reset(chat_id)` | формат `state/sessions.json`, атомарную запись |
| `task_router` (runtime) | очередь ходов | `submit(chat_id, job) -> position`; одна активная задача на чат, одна браузерная глобально | asyncio-примитивы |
| `approvals` | решения владелицы | HTTP `POST 127.0.0.1:<port>/approve {level, tool, summary, details}` → `{decision: allow|deny, reason}` (блокирующий, таймаут 10 мин) | токен, связь с gateway, журнал `approvals.jsonl` |
| `guard` (хук) | политика безопасности | вход — JSON PreToolUse от Claude Code; выход — exit 0 / exit 2 + причина | `policy.yaml`, классификатор путей и команд |
| `voice` | распознавание | `transcribe(path) -> text | None` | faster-whisper, ffmpeg |
| `events` | журнал событий | `emit(type, **fields)` → строка в `state/events.jsonl` | ротацию файла |
| `activation` | перенос черновиков | `list_drafts()`, `activate(kind, name)`, `discard(kind, name)` | проверку структуры SKILL.md/агента перед переносом |

**Швы для тестов:** (1) `claude_bridge.run_turn` с подменённым исполняемым файлом (фейковый `claude`, печатающий записанный stream-json) — через него проверяются сессии, очередь, статус, события; (2) `guard` — чистая функция «JSON вызова → решение», таблица тест-кейсов; (3) `approvals` HTTP — с фейковым gateway. Сквозной ручной тест — реальное сообщение из Telegram.


## Что построили таски

*(заполняется по мере сборки)*
