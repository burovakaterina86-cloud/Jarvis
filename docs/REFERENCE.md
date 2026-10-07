# REFERENCE — технический справочник JARVIS

Для того, кто чинит и дорабатывает систему. Читается по необходимости, целиком держать
в голове не нужно. Целевая картина — `docs/ARCHITECTURE.md`, первая версия — `docs/MVP.md`,
пошаговая настройка для владелицы — `docs/SETUP.md`.

---

## 1. Запуск Claude Code (мост)

Думает Claude Code по подписке владелицы; Python только запускает процесс и разбирает поток.
Строка запуска собирается в `runtime/claude_bridge.build_args()`:

```
claude -p --output-format stream-json --verbose [--resume <session_id>]
       --permission-mode dontAsk
       --append-system-prompt-file runtime/jarvis-turn.md
       --settings runtime/jarvis-settings.json
       --max-turns 60
```

- Промпт уходит в **stdin**, не в аргументах: так он не попадает в список процессов.
- `--dangerously-skip-permissions` / `bypassPermissions` **не используется нигде** —
  это проверяет `tests/test_e2e_offline.py::test_no_permission_bypass_anywhere_in_code`.
- Настройки агента лежат в `runtime/jarvis-settings.json`, а не в `.claude/settings.json`:
  иначе хуки и deny-правила JARVIS применились бы и к сессиям разработки в этой же папке.
- Окружение дочернего процесса собирает `build_env()`: выбрасывает всё `CLAUDE*`, `ANTHROPIC*`,
  `TELEGRAM*` (кроме `CLAUDE_CODE_GIT_BASH_PATH`). Поэтому агент не видит токен бота и не
  уходит на чужую авторизацию. `JARVIS_*` передаются — из них Guard читает лимит покупки.
- `claude` ищется через `shutil.which("claude")`.
- Итог хода берётся из финального события `result`, а не из последнего текста: иначе владелице
  ушло бы служебное напоминание хука `capture_learning`.

Статусы `TurnResult.status`: `ok`, `stopped` (нажали `/stop`), `rate_limited` (лимит подписки),
`auth_required` (нужен `/login`), `error`. Мост не бросает исключений.

Особые случаи, которые мост разруливает сам:
| Что случилось | Что делает мост |
|---|---|
| `--resume` не удался, инструментов ещё не было | один повтор без `--resume`, `new_session=True` |
| Контекст переполнен | новый разговор со сводкой задачи |
| Ход оборвался **после** вызова инструментов | не повторяет (действие могло выполниться), пишет об этом владелице |

## 2. Формат `state/events.jsonl`

Одна JSON-строка на событие, UTF-8, дописывание; при 10 МБ — ротация в `events.1.jsonl`.
Обязательные поля есть всегда:

```json
{"ts":"2026-09-18T09:12:31.004+00:00","type":"tool_use","session":"abc-123",
 "agent":"jarvis","task":"контент на завтра","status":"working","progress":null,"tool":"Read"}
```

- `type`: `user_message`, `assistant_message`, `tool_use`, `tool_result`, `approval_request`,
  `approval_decision`, `blocked`, `result`, `error`.
- `agent`: `jarvis` или `subagent` (событие с `parent_tool_use_id`).
- `status`: `queued`, `working`, `waiting_approval`, `done`, `failed`; `progress` — 0..1 или `null`.
- Доп. поля по типу: `tool`, `reason` (у `blocked`), `cost`, `duration`, `subtype`, `error`,
  `position` (место в очереди), `text` (обрезается до 500 символов).

Пишет `runtime.events.emit(type, **fields)`; в тестах подменяется `runtime.events.EVENTS_PATH`.
Отдельный журнал решений — `state/approvals.jsonl`: строки `{"type":"request",...}` и
`{"type":"decision", "decision":"allow|deny", "reason":...}`.

## 3. `runtime/policy.yaml` — политика Guard

Читает `.claude/hooks/guard.py` на каждый вызов инструмента (PreToolUse, matcher `*`).
Схема (полное описание — в шапке самого файла):

| Ключ | Смысл |
|---|---|
| `approval_timeout_sec` | сколько Guard ждёт ответа владелицы (590 с; сервер отвечает `deny` на 580 с) |
| `purchase_limit_env` | имя переменной с лимитом покупки (`JARVIS_PURCHASE_LIMIT_RUB`); сумма выше — отказ без вопроса |
| `external` | `{<вид>: ask\|auto}` — EXTERNAL-виды; вида нет в списке → `ask` |
| `money_kinds` | виды, которые всегда MONEY и всегда `ask` (`auto` игнорируется) |
| `read_tools` | инструменты без побочных эффектов → READ |
| `write_tools` | `{инструмент: поле пути}` |
| `path_fields`, `shell_tools` | где искать пути и где искать команду |
| `deny_paths` | секреты: любое чтение или упоминание → DENY |
| `protected_write_paths` | запись → DENY (`runtime/**`, `.claude/hooks/**`, `integrations/**`, `.env*` …) |
| `allow_write_paths` | запись вне корня проекта, разрешённая без вопроса |
| `rules` | список правил `{tool, match, level, kind, reason}` |

Уровни: `READ` → сразу, `WRITE` внутри корня → сразу, `EXTERNAL` → кнопка, `MONEY` → кнопка
всегда, `DENY` → отказ. Срабатывают **все** подходящие правила, побеждает строжайший уровень.
Неизвестный инструмент (в том числе `mcp__*`) → EXTERNAL `unknown_tool`.

**Как добавить правило.** Дописать строку в `rules:` (файл правит только владелица руками —
агенту запись в `runtime/` запрещена):

```yaml
  - {tool: "mcp__playwright__browser_click", match: '(подписаться|follow)',
     level: EXTERNAL, kind: send_message, reason: "подписка на аккаунт"}
```

- `tool` — regex по имени инструмента (полное совпадение) или `*`.
- `match` — regex по JSON аргументов вызова, без учёта регистра; для Bash/PowerShell
  проверяется и исходная командная строка, и она же без кавычек.
- `kind` — имя вида; чтобы он спрашивал или не спрашивал, добавить его в `external:` или
  в `money_kinds:`.
- Проверить правило: добавить строку в таблицу случаев `tests/test_guard.py` и прогнать тесты.

Отказы Guard: exit 2 + причина в stderr + строка `blocked` в `state/events.jsonl`.
Fail-closed: нет файла порта, нет токена, нет соединения, таймаут, мусор на stdin, исключение —
всё это отказ.

## 4. Approvals API

Локальный HTTP-сервис моста (`runtime/approvals.py`), поднимается вместе с ботом.

```
POST http://127.0.0.1:<port>/approve      заголовок X-Jarvis-Token: <token>
тело  {"level":"EXTERNAL|MONEY","tool":str,"summary":str,"details":{...}}
ответ 200 {"decision":"allow|deny","reason":str} · 401 без токена · 400 при плохом теле
```

Порт — `state/approvals.port`, токен — `state/secrets/approvals.token` (создаётся заново при
каждом старте, права только владельцу). Таймаут 580 с; ушёл Guard — запрос снимается сразу,
в журнал идёт `deny/client_gone`. Обойти подтверждение промптом нельзя: решение принимает
Guard-хук, а не агент.

## 5. Команды бота

| Команда | Что делает |
|---|---|
| `/start`, `/help` | что умеет и как пользоваться |
| `/whoami` | показывает Telegram ID — его вписывают в `TELEGRAM_OWNER_ID` |
| `/new` | начать разговор заново (сброс сессии чата) |
| `/stop` или отдельное «стоп» | отменить уже существующую работу чата во всех очередях, разрешения, фоновые jobs и продолжения; будущие слоты расписания остаются |
| `/status` | что сейчас в работе и сколько в очереди |
| `/browser_login <адрес>` | открыть сайт в браузерном профиле JARVIS, чтобы войти руками |

Кроме команд: текст, голосовые (faster-whisper, локально, `language=ru`), фото и документы
(сохраняются в `inbox/<дата>/`). Кнопки: «Подтвердить/Отклонить» (подтверждения),
«Принято/Переделать/Опубликовано» (контент), «Активировать/Посмотреть/Удалить черновик»
(новые навыки и помощники). Чужие сообщения игнорируются молча.

## 6. Где что лежит

| Путь | Что |
|---|---|
| `integrations/telegram/` | бот: `gateway.py`, `status.py`, `files.py`, `voice.py` |
| `integrations/browser/login.py` | `python -m integrations.browser.login <url>` — вход на сайт |
| `runtime/` | `claude_bridge.py`, `task_router.py`, `sessions.py`, `events.py`, `approvals.py`, `activation.py`, `policy.yaml`, `jarvis-settings.json`, `jarvis-turn.md` |
| `.claude/hooks/` | `guard.py` (защита), `memory_notice.py`, `capture_learning.py`, `pre_compact.py`, `session_start.py` |
| `.claude/skills/`, `.claude/agents/`, `.claude/rules/` | навыки, помощники, правила поведения |
| `drafts/skills/`, `drafts/agents/` | черновики, пока владелица не нажала «Активировать» |
| `CLAUDE.md`, `SOUL.md`, `GOALS.md`, `MEMORY.md` | личность и контекст, загружаются каждым ходом (бюджет 12 КБ) |
| `essa-ai/` | бизнес-контекст ESSA.AI и готовый контент |
| `memory/` | долгая память: `decisions/`, `projects/`, `people/`, `episodes/` |
| `state/` | всё изменчивое: сессии, события, журнал решений, порт и токен, профиль браузера, бюджет запусков |
| `inbox/` | присланные файлы и фото |
| `.env` | секреты (в git не попадает, агенту читать запрещено) |

Базы данных и веб-панели нет и не должно быть: состояние — только файлы в `state/`
(проверяется тестом `test_no_database_server_and_no_web_dashboard`).

## 6а. Очередь, быстрая полоса и фоновые работы

Её жалоба 2026-10-06: бот не умел работать в фоне и не отвечал на вопрос, пока шла долгая задача. Теперь три отдельных механизма:

| Что | Как устроено | Где |
|---|---|---|
| Очередь чата | одна активная задача на чат, остальные ждут (как раньше) | `runtime/task_router.py` |
| Быстрая полоса `side` | короткий вопрос («ты здесь?», «как там монтаж?», «когда будет?») во время задачи идёт параллельно: лёгкий ход только на чтение со срезом «что сейчас происходит»; просьба что-то сделать (ответ «ОЧЕРЕДЬ») встаёт в обычную очередь | `runtime/side_lane.py`, `runtime/prompts/side-lane.md` |
| Фоновые работы | долгое выполняет **бот**, а не ход агента: агент ставит работу командой `python -m integrations.jobs submit …` и заканчивает ход; бот запускает процесс (белый список модулей), следит и присылает результат письмом с файлом; не больше 2 одновременно, больше 2 часов — останавливается, перезапуск бота — «прервана» | `integrations/jobs/`, запросы `jobs/requests/`, состояние `state/jobs/` |

Рендер монтажа защищён от обрыва: замок рабочей папки, добивание хвостов старого рендера, повтор стирания кадров, проверка числа кадров до ffmpeg (`integrations/montage/render.py`).

## 7. Тесты и проверки

| Команда | Что проверяет |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | весь офлайн-прогон, реальный `claude` не запускается |
| `.venv\Scripts\python.exe -m pytest -q tests/test_e2e_offline.py` | сквозной путь: апдейт → очередь → мост → настоящий Guard → Approvals → кнопка → ответ в чат; плюс отсутствие bypass-флагов, бюджет контекста, отсутствие БД |
| `.venv\Scripts\python.exe scripts/check_context_size.py` | размеры `CLAUDE/SOUL/GOALS/MEMORY` ≤ 12 КБ суммарно |
| `.venv\Scripts\python.exe scripts/check_hooks.py` | команды хуков из `jarvis-settings.json` реально исполняются в Git Bash (пропуск/отказ Guard, хуки памяти) |
| `.venv\Scripts\python.exe tests\smoke_real_turn.py` | **с реальным `claude`**: ход с чтением `essa-ai/PROFILE.md`; попытка прочитать `.env` блокируется Guard |
| `.venv\Scripts\python.exe tests\smoke_real_claude.py` | **с реальным `claude`**: простой ход «привет» |

Дымовые файлы (`tests/smoke_*.py`) в общий прогон не входят: `pytest.ini` добавляет
`-m "not smoke"`. Сквозной тест использует настоящий `guard.py` и настоящую `policy.yaml`,
скопированные в песочницу tmp, — поэтому он ничего не пишет в рабочие `state/` и `memory/`.

## 8. Известные ограничения

- **Сквозная проверка с настоящим `claude` при сборке НЕ выполнялась.** На машине истёк вход
  (`auth_required`), поэтому ход `claude -p` через мост, голосовые и живой Telegram-прогон
  не подтверждены. Подтверждено офлайн: весь `pytest` зелёный (включая сквозной
  `tests/test_e2e_offline.py` с настоящим `guard.py` и Approvals) и живой запуск команд хуков
  через Git Bash (`scripts/check_hooks.py`). Живой прогон делает владелица после
  `claude` + `/login`: `tests\smoke_real_turn.py` (ход по `essa-ai/PROFILE.md` и отказ Guard
  на чтении `.env`), затем сценарий приёмки из `docs/MVP.md`.
- **Вход в Claude.** Подписка живёт в самом `claude`. Если вход истёк, любой ход возвращает
  `auth_required` и бот пишет «нужно заново войти в Claude на компьютере». Лечится только
  руками: `claude` в терминале, затем `/login`.
- **Лимиты подписки.** При исчерпании — `rate_limited` и сообщение «продолжу в HH:MM».
  Дневной предел запусков — `JARVIS_DAILY_RUN_BUDGET` (по умолчанию 100).
- **Браузерный профиль занят одним процессом.** Пока идёт браузерная задача, `/browser_login`
  не сработает, и наоборот: закрыть окно браузера и повторить.
- **Windows.** Хуки Claude Code запускаются через Git Bash; без Git for Windows защита
  не работает. Проверка — `scripts/check_hooks.py`. Остановка хода — `taskkill /T /F`.
- **Кириллица в `start.bat`.** После `chcp 65001` cmd ломает разбор не-ASCII текста, поэтому
  `.bat` только на латинице; русские сообщения печатает Python.
- **Голос.** Первое голосовое после запуска распознаётся дольше: грузится модель whisper
  (`JARVIS_WHISPER_MODEL`, по умолчанию `small`).
- **Кнопка подтверждения живёт сутки**, а сам запрос — 10 минут: после этого Guard уже
  отказал, и нажатие отвечает «запрос неактуален».
- **Approvals слушает только `127.0.0.1`** и требует токен: снаружи к нему не подключиться.
