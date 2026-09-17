# 01 — Каркас и защита: Guard, политика, настройки

**Требования:** R02, R07, R13, R14, R15, R09, R44
**Blocked by:** —
**Зона:** `.claude/settings.json` · `.claude/hooks/guard.py` · `runtime/policy.yaml` · `runtime/__init__.py` · `tests/test_guard.py` · `requirements.txt` · `.env.example` · `.gitignore` · `start.bat` · `.venv/`
**Волна:** 1
**Status:** ready

## Что должно заработать

Появляется скелет проекта и главный защитный слой. Любой вызов инструмента Claude Code (включая `mcp__*`, Grep, Glob, Bash, PowerShell, WebFetch) проходит через Guard-хук, который по `runtime/policy.yaml` решает: пропустить (READ, WRITE внутри корня), отказать (секреты, опасные команды, запись в собственные настройки/хуки/`runtime/`/`integrations/`, ввод в поля паролей и карт), или спросить владелицу через Approvals API (EXTERNAL, MONEY/IRREVERSIBLE, любое удаление, неизвестный MCP-инструмент). Ошибка внутри хука или недоступный Approvals API = отказ (exit 2). Сам Approvals API пишет таск 03 — здесь Guard только ходит к нему по контракту из interfaces.md; в тестах API подменяется.

Также: `requirements.txt` (python-telegram-bot[job-queue]>=21, faster-whisper, pyyaml, aiohttp, pytest, pytest-asyncio), `.venv` создан и зависимости установлены (`py -3.12 -m venv .venv` или `python -m venv .venv`; `pip install -r requirements.txt` — PyPI разрешён), `.env.example` с пустыми `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `JARVIS_DAILY_RUN_BUDGET`, `JARVIS_PURCHASE_LIMIT_RUB`; `.gitignore` дополнен (`state/`, `inbox/`, `.venv/`, `.env`). `.claude/settings.json`: permissions allow/deny (deny `Read(//**/.env*)`, `Read(~/.claude/.credentials.json)`, `Edit(.claude/settings*.json)`, `Edit(.claude/hooks/**)`, `Edit(runtime/**)`, `Edit(integrations/**)`, `Edit(.claude/skills/**)`, `Edit(.claude/agents/**)`), hooks: PreToolUse matcher `*` → guard.py; PostToolUse → memory_notice.py; Stop → capture_learning.py; PreCompact → pre_compact.py; SessionStart → session_start.py (эти четыре файла пишет таск 05 — зарегистрировать сейчас, команда вызывает `.venv\Scripts\python.exe` по абсолютному пути от `$CLAUDE_PROJECT_DIR`). `start.bat` — заглушка запуска `python -m integrations.telegram` из venv с `chcp 65001` (сам модуль пишет таск 04).

## Из брифа, дословно

> «никаких `--dangerously-skip-permissions` глобально»
> «READ → автоматически; WRITE workspace → автоматически; EXTERNAL ACTION → approval policy; IRREVERSIBLE / MONEY → обязательное подтверждение»
> «hooks … блокируют опасные shell-команды и доступ к `.env`, ключам и credentials на уровне Claude Code, а не только промптом»
> «может бронировать авиабилеты», «добавлять товары в корзину»

## Разделы спецификации

Истории 44–51, 37–38a (уровни и оплата), Решения §3, §4, §11; Структура каталогов; Границы: `guard`.

## Критерии приёмки

- [ ] Guard — чистая функция `decide(event: dict) -> Decision(level, action, reason)` + тонкая обёртка stdin/exit-code; таблица тестов ≥ 30 кейсов, все зелёные
- [ ] Чтение `.env`, `~/.claude/.credentials.json`, `state/browser-profile/`, `state/secrets/` любым инструментом (Read/Grep/Glob/Bash/PowerShell) → отказ
- [ ] Запись в `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/`, `.claude/agents/`, `runtime/`, `integrations/` → отказ; запись в `essa-ai/`, `memory/`, `drafts/`, `inbox/`, корневые SOUL/GOALS/MEMORY.md → пропуск
- [ ] Любое удаление файлов, отправка/публикация/регистрация (по шаблонам policy.yaml), неизвестный `mcp__*` → запрос к Approvals API; allow → exit 0, deny/таймаут/ошибка соединения → exit 2
- [ ] MONEY с суммой выше `JARVIS_PURCHASE_LIMIT_RUB` → отказ без запроса; ввод в поле карты/CVV/пароля через Playwright (`browser_type`/`browser_fill_form` с такими полями) → отказ
- [ ] Внутреннее исключение Guard → exit 2 (fail-closed), тест это проверяет
- [ ] EXTERNAL-правило с `auto` в policy.yaml пропускается без запроса; MONEY/IRREVERSIBLE с `auto` всё равно спрашивает
- [ ] В репозитории нет строки `dangerously-skip-permissions` (тест-grep)
- [ ] `.venv` создан, `pytest` запускается одной командой из interfaces.md
