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

- **Настройки агента JARVIS** (D01): не в `.claude/settings.json`, а в `runtime/jarvis-settings.json`; мост передаёт `--settings runtime/jarvis-settings.json`. Проектный `.claude/settings.json` не создаётся — иначе hooks/deny JARVIS применились бы к сессиям разработки.

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

### Из таска 01 — каркас и Guard

- `.claude/hooks/guard.py`: `decide(event: dict, policy: dict, root, env=None) -> Decision(level, action, reason, kind)`; level READ|WRITE|EXTERNAL|MONEY|DENY, action allow|ask|deny. Также `load_policy(path)`, `run(event, root, policy_path, env) -> (exit_code, reason)`, `ask_approval(decision, event, root, timeout) -> (bool, str)`. Корень = `Path(guard.py).parents[2]`.
- Exit 0 — пропуск; exit 2 — отказ (причина в stderr, UTF-8): deny, отказ владелицы, таймаут, 401, нет порта/токена/соединения, исключение, мусор на stdin. Каждый отказ → `{"type":"blocked", tool, reason, ...}` в `state/events.jsonl`.
- Guard → Approvals: порт `<root>/state/approvals.port`, токен `<root>/state/secrets/approvals.token`, `POST http://127.0.0.1:<port>/approve`, заголовок `X-Jarvis-Token`, тело `{level, tool, summary, details: {kind, tool_input}}`; разрешает только 200 + `decision: allow`; таймаут из `approval_timeout_sec`.
- `runtime/policy.yaml` ключи: `approval_timeout_sec`, `purchase_limit_env`, `external{kind: ask|auto}`, `money_kinds[]`, `read_tools[]`, `write_tools{tool: поле_пути}`, `path_fields[]`, `shell_tools[]`, `deny_paths[]`, `protected_write_paths[]`, `allow_write_paths[]`, `rules[{tool: regex|"*", match: regex по JSON аргументов, level, kind, reason}]`; срабатывают все правила, побеждает строжайший уровень.
- Лимит покупки: Guard читает только env `JARVIS_PURCHASE_LIMIT_RUB` — **мост (таск 02) обязан передать её в окружение `claude`** (как и остальное нужное из `.env`, кроме Telegram-секретов).
- `runtime/jarvis-settings.json`: `defaultMode: dontAsk`, allow/deny, хуки PreToolUse `*` → guard.py; PostToolUse → `memory_notice.py`; Stop → `capture_learning.py`; PreCompact → `pre_compact.py`; SessionStart → `session_start.py` (все в `.claude/hooks/`, пишет таск 05). Команды хуков в bash-форме: `"$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe" <hook> || exit 2` — работа под Claude Code на Windows не проверена, проверяет таск 08.
- Правила для Bash/PowerShell сверяются с командной строкой (исходной и без кавычек/склеек). Shell-запись вне корня, через `..` или в путь с переменной (`$HOME`, `$env:`, `%VAR%`) → EXTERNAL `write_outside_root`. Любое удаление (`rm`, `del`, `Remove-Item`, `os.remove`, `::Delete(` …) → MONEY/ask. Токены `.e*`/`.env`/`credentials` в shell → DENY. `approval_timeout_sec: 590` (общий deadline), таймаут хука 620 с. Лимит не задан → MONEY ask.
- Тесты: `.venv\Scripts\python.exe -m pytest -q`; `pytest.ini` в корне. 105 тестов.

### Из таска 03 — Approvals API

- `runtime.approvals.ApprovalsServer(timeout: float = 600.0)`; `async start(root) -> int` (порт; только 127.0.0.1; пишет `state/approvals.port`, новый `state/secrets/approvals.token`); `async stop()` (удаляет файлы, висящие → deny `shutdown`); повторный start → RuntimeError.
- `on_request(callback(request_id: str, level, tool, summary, details: dict))` — sync или async.
- `resolve(request_id, "allow"|"deny", reason="") -> bool` — False, если запроса уже нет (Guard ушёл: reason `client_gone`, или таймаут) → Telegram-слой должен сообщить «запрос уже неактуален» и убрать кнопки.
- Свойства: `port`, `pending: list[str]`, `addresses`.
- HTTP: 401 без/с чужим токеном; 400 при плохом теле или level не EXTERNAL|MONEY; 200 `{decision, reason}`.
- Журнал `state/approvals.jsonl`: `{ts,type:"request",request_id,level,tool,summary,details}` / `{ts,type:"decision",request_id,decision,reason,tool}`.
- События пока пишет заглушка `emit_event(root, type, **fields)` внутри approvals.py — заменить на `runtime.events.emit` после таска 02.

### Из таска 05 — личность и память

- Хуки памяти: `main(stdin=None, stdout=None, root=ROOT) -> int` (всегда 0), `handle(event, root) -> dict|None`; JSON на stdin → JSON на stdout.
- `memory_notice` (PostToolUse): запись в `MEMORY.md`, `memory/**`, `essa-ai/knowledge/**` → additionalContext «🧠 запомнил: … (<путь>)».
- `capture_learning` (Stop): молчит при `stop_hook_active`, при нечитаемом transcript и при < 3 вызовов инструментов; иначе напоминание про урок/алгоритм. **Мост (таск 02) должен брать итог хода из финального `result`, иначе владелице уйдёт служебный текст.**
- `pre_compact` (PreCompact): строка в `memory/episodes/YYYY-MM.jsonl` `{date,session,trigger,request,result,files}`.
- `session_start`: `MEMORY.md` > 5 KB → additionalContext «сожми MEMORY.md».
- `scripts/check_context_size.py`: `check(root) -> bool`, бюджеты CLAUDE 5 / SOUL 2 / GOALS 2 / MEMORY 5 KB, сумма 12 KB. Сейчас 4.25 KB + правила 6.40 KB.
- Файлы личности: `CLAUDE.md` (карта проекта для JARVIS), `SOUL.md`, `GOALS.md`, `MEMORY.md`; правила в `.claude/rules/`; бизнес-контекст в `essa-ai/` (PROFILE, VOICE, AUDIENCE, PRODUCTS, STRATEGY, ANALYTICS, `content/PUBLISHED.md`, `knowledge/`); долгая память в `memory/{decisions,projects,people,episodes}/`.

### Из таска 02 — мост к Claude Code

- `claude_bridge.TurnResult(text, session_id, new_session, cost_usd, status: "ok"|"stopped"|"rate_limited"|"auth_required"|"error", error=None)`.
- `async claude_bridge.run_turn(prompt, session_id=None, on_event=None, *, run_id=None, task="", env=None, claude_cmd=None, cwd=None) -> TurnResult` — не бросает исключений. `stop(run_id) -> bool`, `build_env(base=None)`, `build_args(sid)`.
- `sessions.get(chat_id) -> str|None`, `sessions.set(chat_id, sid)`, `sessions.reset(chat_id)`.
- `task_router.Job(prompt, uses_browser=False, task="", on_event=None, on_done=None, result=None)`; `TaskRouter(*, budget=None, budget_path=None, env=None, claude_cmd=None, sessions=None).submit(chat_id, job) -> int` (0 = стартует сразу), `.pending(chat_id)`, `.stop(chat_id)`; модульные `submit/stop/run_id_for`.
- `events.emit(type, **fields) -> dict`; `EVENTS_PATH` / `SESSIONS_PATH` — модульные атрибуты (подменяются в тестах). **Таску 03: заменить заглушку `emit_event` на `events.emit`.**
- Итог хода Telegram-слою брать из финального `result`, а не из последнего текста (иначе уйдёт служебное напоминание хука capture_learning).
- Риск: в дымовом прогоне внутри этой среды разработки `claude` вернул `auth_required` (host-логин вместо подписки). Проверка на боевой машине через `start.bat` — таск 08.

### Из таска 03 — доработка

- `ApprovalsServer(timeout=580.0)`, `DEFAULT_TIMEOUT=580.0` (< 590 с у Guard). `AppRunner(handler_cancellation=True)`: уход Guard снимает запрос сразу → `resolve` False, журнал `deny/client_gone`, allow после ухода не пишется.
- Токен: создаётся `O_EXCL` c 0o600, права до записи; на Windows `icacls`; неудача → WARNING + событие `error`.
- Журнал: строки в `summary`/`details` обрезаются до 500 символов (`JOURNAL_STR_LIMIT`); в `on_request` и Guard уходит полное.

### Из таска 06 — навыки и браузер

- 8 навыков в `.claude/skills/`: `trend-radar`, `competitor-research`, `content-strategy`, `content-plan` (оркестратор), `copywriting`, `reels-script`, `repurpose-content`, `browser-use`.
- Папка комплекта: `essa-ai/content/YYYY-MM-DD-<тема>/{post.md,carousel.md,reels.md,stories.md,sources.md,status}`; `status`: draft|accepted|rework|published; публикация → строка в `essa-ai/content/PUBLISHED.md`.
- MCP-сервер `playwright` (`.mcp.json`): `npx @playwright/mcp@latest --user-data-dir state/browser-profile --browser msedge`. Инструменты: browser_navigate(_back), browser_snapshot, browser_take_screenshot, browser_click, browser_type, browser_fill_form, browser_select_option, browser_press_key, browser_wait_for, browser_tabs, browser_close.
- Вход на сайты: `.venv\Scripts\python.exe -m integrations.browser.login <url>`; `build_command(url, browser_path=None, root=None)`, `find_browser()`, `PROFILE_DIR = state/browser-profile`. Профиль занят одним процессом: во время браузерной задачи вход невозможен.

### Из таска 04 — Telegram

- Команды: `/start` `/help` `/whoami` `/new` `/stop` `/status` `/browser_login <url>`; текст, голос, фото, документы.
- `gateway.Gateway(owner_id, root, router, sessions, approvals, transcriber, min_status_interval)`: `.on_message/.on_voice/.on_file/.on_callback`, `.on_approval_request(request_id, level, tool, summary, details)`, `.attach(bot)`, `.announce()`, `.register(app)`; callback-данные `ap:<tok>:<d>` и `ct:<tok>:<d>`.
- `gateway.load_env(path) -> dict[key, True]` (значений не отдаёт), `Config(token, owner_id).from_env()`, `run(config)`, `main(argv, env_path) -> int`.
- `status.split_message(text, limit=4096)`, `too_long`, `human_elapsed`, `StatusReporter(bot, chat_id, task, min_interval=3.0, clock)` с `.note/.note_blocked/.start/.update/.finish`.
- `files.sanitize_name`, `inbox_path`, `save_bytes`, `find_content_bundle(text, root)`, `mark_content(root, name, accepted|redo|published, when, note)`.
- `voice.transcribe(path, transcriber=None) -> str|None`, `model_name()`, `get_model()`.
- Запуск: `start.bat` (ASCII-only: после `chcp 65001` кириллица в .bat ломает разбор); автозапуск — `powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1` (снять: `-Remove`), ставит владелица сама.
