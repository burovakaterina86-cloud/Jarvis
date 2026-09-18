<!-- autopilot:start -->
# ESSA-JARVIS

Личный автономный агент владелицы ESSA.AI: Telegram → тонкий Python-мост → `claude -p` (её подписка Claude Code). Питон не «думает»: он запускает процесс, разбирает stream-json и сторожит безопасность.

Корневой `CLAUDE.md` — это «мозг» самого JARVIS (грузится в каждый его ход, бюджет ≤ 5 KB, проверяет `scripts/check_context_size.py`); заметки для разработки — здесь, в `AGENTS.md`, и в `docs/`.

## Команды

```
.venv\Scripts\python.exe -m pytest -q                       # 297 passed, smoke исключён через addopts
.venv\Scripts\python.exe -m pytest -q tests/test_guard.py   # один модуль
.venv\Scripts\python.exe scripts\check_context_size.py      # бюджеты CLAUDE/SOUL/GOALS/MEMORY; exit 1 при превышении
.venv\Scripts\python.exe scripts\check_hooks.py             # хуки через bash -c, как их зовёт Claude Code; exit 1 при расхождении
start.bat                                                   # боевой запуск: python -m integrations.telegram
.venv\Scripts\python.exe -m pytest -q -m smoke tests/smoke_real_turn.py   # требует рабочий вход в claude
.venv\Scripts\python.exe -m integrations.browser.login <url>             # вход на сайт в профиле браузера
```

## Структура

```
integrations/telegram/   gateway.py (бот, allow-list, кнопки), status.py, files.py, voice.py, __main__.py
integrations/browser/    login.py — ручной вход в state/browser-profile
runtime/                 claude_bridge.py, task_router.py, sessions.py, approvals.py, events.py, activation.py
runtime/                 policy.yaml, jarvis-settings.json, jarvis-turn.md — конфиг агента, не разработки
.claude/hooks/           guard.py + memory_notice/capture_learning/pre_compact/session_start
.claude/skills/          11 навыков JARVIS; .claude/rules/ — 5 правил, грузятся каждым ходом
.claude/agents/          живые субагенты (пусто); черновики — drafts/agents/*.md, drafts/skills/
essa-ai/                 бизнес-контекст ESSA (PROFILE, VOICE, STRATEGY…), content/, knowledge/
memory/                  decisions/ projects/ people/ episodes/ — долгая память агента
state/                   runtime-данные: sessions.json, events.jsonl, approvals.port, secrets/, browser-profile/ (gitignore)
docs/                    ARCHITECTURE.md, MVP.md, SETUP.md, REFERENCE.md
tests/                   test_*.py + fake_claude/fake_claude.py; smoke_*.py — с настоящим claude
```

## Ключевые файлы

- `runtime/claude_bridge.py` — `async run_turn(prompt, session_id=None, on_event=None, *, run_id, task, env, claude_cmd, cwd) -> TurnResult(text, session_id, new_session, cost_usd, status, error)`; исключений не бросает, `status ∈ ok|stopped|rate_limited|auth_required|error`. `build_args()` даёт `-p --output-format stream-json --verbose [--resume SID] --permission-mode dontAsk --append-system-prompt-file runtime/jarvis-turn.md --settings runtime/jarvis-settings.json --max-turns 60`.
- `runtime/claude_bridge.build_env()` — вырезает из окружения дочернего `claude` всё `CLAUDE*`/`ANTHROPIC*`/`TELEGRAM*` (кроме `CLAUDE_CODE_GIT_BASH_PATH`); иначе дочерний процесс уходит на хост-авторизацию вместо подписки. `JARVIS_*` пробрасывается — на этом держится лимит покупки в Guard.
- `.claude/hooks/guard.py` — `decide(event, policy, root, env) -> Decision(level, action, reason, kind)`, уровни READ|WRITE|EXTERNAL|MONEY|DENY, действия allow|ask|deny. exit 0 пропуск, exit 2 отказ (причина в stderr, строка `blocked` в `state/events.jsonl`).
- `runtime/policy.yaml` — таблица правил Guard: `rules[{tool, match, level, kind}]`, `deny_paths`, `protected_write_paths`, `allow_write_paths`, `external{kind: ask|auto}`, `money_kinds`, `approval_timeout_sec: 590`. Срабатывают все правила, побеждает строжайший уровень.
- `runtime/approvals.py` — `ApprovalsServer(timeout=580.0)`, `start(root) -> port`, `on_request(cb)`, `resolve(request_id, allow|deny, reason)`. Журнал `state/approvals.jsonl`.
- `runtime/task_router.py` — очередь ходов: одна активная задача на чат, одна браузерная глобально, дневной бюджет запусков.
- `integrations/telegram/gateway.py` — `Gateway`, `Config.from_env()`, `run(config)`, `main(argv, env_path)`; команды `/start /help /whoami /new /stop /status /browser_login`.
- `runtime/jarvis-settings.json` — permissions + хуки JARVIS. Проектного `.claude/settings.json` нет намеренно: иначе deny/hooks агента применились бы к сессиям разработки.

## Архитектура

Поток хода: Telegram-апдейт → `Gateway` (allow-list по `TELEGRAM_OWNER_ID`, голос через `voice.transcribe`, файлы в `inbox/`) → `TaskRouter.submit(chat_id, job)` → `claude_bridge.run_turn` поднимает `claude -p` c `--settings runtime/jarvis-settings.json` → каждый вызов инструмента проходит PreToolUse-хук `guard.py`.

Guard решает по `policy.yaml`: READ/WRITE внутри корня — allow (exit 0); EXTERNAL/MONEY — `POST http://127.0.0.1:<port>/approve` с заголовком `X-Jarvis-Token` на Approvals API внутри того же процесса бота; DENY — exit 2 сразу.

Approvals отдаёт запрос в `Gateway.on_approval_request` → кнопки в Telegram → `resolve()` → `{decision, reason}` обратно Guard. Нет файла `state/approvals.port`, нет токена, нет соединения, таймаут — deny. Таймауты вложены: Approvals 580 с < Guard 590 с < хук 620 с.

Итог хода Telegram-слой берёт из финального события `result`, а не из последнего текста — иначе владелице уйдёт служебное напоминание Stop-хука `capture_learning`. Сессия чата хранится в `state/sessions.json` (`{chat_id: session_id}`, атомарная запись), всё наблюдаемое — строками JSON в `state/events.jsonl` через `events.emit`.

Новые навыки и субагенты агент пишет только в `drafts/`; перенос в `.claude/skills|agents` делает `runtime.activation` после кнопки владелицы (`validate` → `activate`).

## Соглашения кода

- Python 3.12, стандартная библиотека + `requirements.txt`; нового пакета не ставить — вернуть BLOCKED с названием.
- UTF-8 везде: `encoding="utf-8"` при открытии файлов и в subprocess; `start.bat` только ASCII (кириллица после `chcp 65001` ломает разбор .bat).
- Пути — от `ROOT = Path(__file__).resolve().parents[N]`, не от cwd.
- Тексты для владелицы (бот, навыки, правила, docs) — по-русски; docstring модулей тоже русские.
- Модульные атрибуты вместо констант там, где тест подменяет путь: `events.EVENTS_PATH`, `sessions.SESSIONS_PATH`.
- Флага `--dangerously-skip-permissions` / `bypassPermissions` не должно появиться нигде.

## Окружение

`.env` в корне (gitignore), пример — `.env.example`. Только имена: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `JARVIS_DAILY_RUN_BUDGET` (по умолчанию 100), `JARVIS_PURCHASE_LIMIT_RUB` (не задан → MONEY уходит на подтверждение), `JARVIS_WHISPER_MODEL` (по умолчанию `small`). Значения не читать, не печатать, не логировать. `gateway.load_env()` возвращает только ключи, без значений. Токен Approvals живёт в `state/secrets/approvals.token` и создаётся при старте.

## Тесты

- `pytest.ini`: `testpaths = tests`, `asyncio_mode = auto`, `addopts = -m "not smoke"`.
- Швы: фейковый `claude` (`tests/fake_claude/fake_claude.py`) печатает записанный stream-json — через него проверяются сессии, очередь, статусы, события; Guard тестируется как чистая функция «JSON вызова → решение»; Approvals — по HTTP с фейковым gateway.
- `tests/test_e2e_offline.py` — сквозной проход без сети; `tests/test_skills_format.py` проверяет формат SKILL.md.
- Реальные прогоны — `tests/smoke_real_turn.py`, `tests/smoke_real_claude.py`, только маркером `-m smoke`.

## Подводные камни

- `claude -p` в этой среде сейчас возвращает `auth_required` — истёк вход владелицы. Это факт окружения, а не баг моста: smoke-тесты и ручной прогон через `start.bat` не пройдут, пока она не сделает `claude` → `/login`. Чинить кодом нечего.
- `scripts/check_hooks.py` — не заглушка: отказ Guard дописывает `blocked` в `state/events.jsonl`, PreCompact — эпизод в `memory/episodes/`.
- Профиль браузера занят одним процессом: `integrations.browser.login` не запустить, пока идёт браузерная задача.
- `.claude/agents/` пуст; шесть помощников лежат черновиками в `drafts/agents/`, включает их только владелица кнопкой в Telegram. Новая папка `.claude/agents/` требует перезапуска Claude Code — поэтому `activation.ensure_dirs` вызывается на старте.
- `.agents/skills/` и `.codex/agents/` — зеркала навыков и субагентов для других CLI; правишь `.claude/` — синхронизируй их.
- `state/` и `inbox/` в .gitignore: удалять `state/*.json` на живом боте нельзя, там сессии и бюджет.
- `runtime/`, `integrations/`, `.claude/hooks|skills|agents`, `.env`, `.mcp.json` закрыты на запись для самого JARVIS через deny в `runtime/jarvis-settings.json` — это его правила, разработчика они не ограничивают.

## Как здесь работает Autopilot

Сборка ведётся навыком `/autopilot`. Требования, спецификация и таски — в `.autopilot/`.
Прогресс — `.autopilot/dashboard.html`. Правило: требование из `manifest.md`
может снять только пользователь.

Если работа продолжается — скажи «продолжи автопилот»: состояние поднимется
из `.autopilot/state.js`, переспрашивать ничего не нужно.
<!-- autopilot:end -->
