# Codex как второй worker Jarvis — исследование для P4.1

Дата: 2026-10-05. Задача P4.1: когда у Claude Code кончается лимит подписки, Jarvis продолжает работу в Codex.
План P4.1 реализован (ADR 0014); ниже — исследование, на котором он стоит. Всё, что помечено **проверено**, — живые прогоны на её компьютере (временные папки,
хуки только писали имена полей). **Не проверено** — сказано прямо.

## 1. Что установлено

| Что | Значение |
|---|---|
| Версия | `codex-cli 0.157.0`, Windows x64, через npm (`C:\Users\burov\AppData\Roaming\npm\codex`) |
| Вход | ChatGPT (`codex login status` → «Logged in using ChatGPT»), файл входа в `~/.codex/` — не читали |
| Неинтерактивный режим | `codex exec` (+ `exec resume <id>`, `exec fork`, `exec review`) |
| Её настройки | `~/.codex/config.toml` грузится всегда; в нём MCP-сервер, который сейчас падает на авторизации, и плагины (Superpowers) — они влезают в каждый прогон |

Флаги `codex exec`, важные для Jarvis: `--json` (события JSONL), `-s read-only|workspace-write|danger-full-access`,
`--output-schema <файл>`, `--ephemeral` (без сохранения сессии), `-C <папка>`, `-o <файл последнего ответа>`,
`-c ключ=значение`, `--ignore-user-config`, `--ignore-rules`, `--dangerously-bypass-hook-trust`,
`--dangerously-bypass-approvals-and-sandbox` (в Jarvis — никогда).

## 2. Проверено живыми прогонами

| Что | Результат |
|---|---|
| События `exec --json` | `thread.started{thread_id}` → `turn.started` → `item.started/completed` (`agent_message.text`, `command_execution{command, exit_code, status}`, `file_change{changes[path, kind]}`) → `turn.completed{usage}`. Ошибка хода — `turn.failed{error.message}` (по документации; живьём не ловили) |
| Песочница `-s read-only` | **работает**: чтение прошло, запись `out.txt` не создана |
| `--output-schema` | **работает**: последний `agent_message.text` — JSON по схеме (берём последнее сообщение — промежуточные тоже бывают в схеме) |
| `--ephemeral` | **работает**: файла сессии в `~/.codex/sessions/` нет |
| Свои инструкции | **работает**: `-c 'developer_instructions="…"'` — Codex следует им (ответил ровно заданным словом) |
| Хук `PreToolUse` через `-c hooks…` | **не подключился** (ни одного вызова хука) |
| Хук `PreToolUse` из `<репо>/.codex/hooks.json` | **вызывается** для shell (`tool_name: "Bash"`, `tool_input.command` — команда) и правок файлов (`tool_name: "apply_patch"`, `tool_input.command` — **текст патча** `*** Add File: note.txt …`; пути надо достать из патча). Поля входа: `cwd, hook_event_name, model, permission_mode, session_id, tool_input, tool_name, tool_use_id, transcript_path, turn_id` |
| Запрет JSON-ответом `{"hookSpecificOutput":{"permissionDecision":"deny",…}}` | **работает** и для `Bash`, и для `apply_patch`: файлы не созданы |
| Запрет кодом выхода `2` + stderr | **НЕ работает** в 0.157.0 на Windows (документация обещает обратное): обе записи прошли |
| Хук упал (исключение) | **Codex продолжает** — fail-open. Обратное принципу Guard |
| Доверие к хукам | проектные хуки требуют доверия к папке; без него — `--dangerously-bypass-hook-trust` (Codex сам пишет предупреждение в события) |

Как Codex сообщает об **исчерпании лимита** — **не проверено** (лимит не кончался). В событиях `exec --json`
сведений о лимите нет. В файлах сессий (`~/.codex/sessions/**/rollout-*.jsonl`) есть
`rate_limits: {primary: {used_percent, window_minutes: 300, resets_at}, secondary: {… 10080 …}}` —
то же, что показывает интерактивный Codex; у `--ephemeral`-сессий файла нет.

## 3. Чем заменить Guard у Codex

Защита Codex сама по себе — песочница (`read-only`/`workspace-write`) и `approval_policy`. Кнопок владелицы,
секретов, денег, браузерных правил, прав ролей в ней нет. Замена Guard — **его же `decide()` через хук Codex**:

1. **Адаптер хука** (`guard.py --runtime codex` или отдельный тонкий файл): переводит вход Codex в событие Guard
   (`Bash` → shell как есть; `apply_patch` → пути из строк `*** Add File: / Update File: / Delete File:` → решение
   как для `Write`/`Edit` по каждому пути, `Delete File` → `delete`), спрашивает Approvals API как сейчас и
   **всегда отвечает JSON-ом** (`permissionDecision: deny` с причиной), выход 0. Любая внутренняя ошибка → JSON-запрет.
2. **Fail-open закрывает мост**: перед каждым запуском Codex — «канарейка»: выполнить ту же команду хука с заведомо
   запрещённым событием (чтение `.env`) и требовать JSON-запрет; нет ответа — Codex не запускать.
3. **Доверие**: хуки Jarvis живут в `Jarvis/.codex/hooks.json` (в `policy.yaml` сделать путь DENY для агента, а не
   только кнопкой). Либо владелица один раз доверяет им в интерактивном Codex (`/hooks`), либо мост запускает с
   `--dangerously-bypass-hook-trust` — файл хуков он и так охраняет. Решает владелица.
4. **Режимы**: проектный хук Codex сработает и в её собственных сессиях Codex в этой папке. Режим без передачи
   аргументом: бот задаёт `JARVIS_TASK_ID` → полный режим; нет — режим разработки (только запреты). Здесь
   наследование безопасно: окружение может лишь ужесточить режим. Проверить живьём.
5. **Не перехватывается хуками**: встроенный веб-поиск Codex (hosted). Файлы Codex читает командами shell — это
   ловит shell-ветка Guard (секреты, большие файлы).

## 4. Как Jarvis сейчас понимает, что лимит Claude кончился

`runtime/claude_bridge.py`: событие `rate_limit_event` с `rate_limit_info.status == "rejected"` (время сброса —
`resetsAt`) или `system/api_retry` с `error: rate_limit` → `TurnResult.status = "rate_limited"`, владелице —
«Лимит подписки Claude исчерпан, продолжу в ЧЧ:ММ», дневной лимит запусков возвращается. Статус
`allowed_warning` (лимит на подходе) сейчас только пропускается — его можно использовать для заблаговременного
предупреждения.

## 5. Ещё находки, которые влияют на дизайн

- **`AGENTS.md` в корне Codex читает сам**, а у нас это заметки разработчика, не «мозг» Jarvis. Для бота «мозг»
  (`CLAUDE.md` без `@`-импортов + `SOUL/GOALS/MEMORY` + `runtime/jarvis-turn.md`) передаём через
  `developer_instructions`; её собственные сессии Codex продолжают читать `AGENTS.md` — так и задумано.
- **Её `~/.codex/config.toml` нельзя отключать** (проверено P4.1a): с `--ignore-user-config` Codex считает папку
  недоверенной — сам включает read-only и **не запускает проектные хуки** (доверие к папкам записано в её
  настройках). Для бота — `--disable plugins` (плагины не попадают); её MCP-сервер даёт только шум в stderr.
- Навыки Codex берёт из `.agents/skills/`, помощников — из `.codex/agents/` — зеркала уже поддерживаются (P4.2).
- Продолжение разговора — `codex exec resume <thread_id>` (аналог `--resume`); сессии Codex и Claude разные:
  при переключении контекст передаётся брифом (как режим `brief` из P3.1).

## 6. Предлагаемый план P4.1 (маленькими этапами)

| ID | Этап | Проверка |
|---|---|---|
| P4.1a | `smoke_codex_capabilities.py` (маркер smoke): сегодняшние прогоны как повторяемый тест + проверка `--ignore-user-config` и режима по `JARVIS_TASK_ID` | таблица «есть/нет» как в P2.0 |
| P4.1b | Адаптер Guard для Codex: вход Codex → `decide()`, пути из `apply_patch`, всегда JSON-ответ, ошибка → запрет; `.codex/hooks.json`; `.codex/hooks.json` — DENY для агента | юнит-тесты на записанных входах + живой прогон «запрещено → файла нет» |
| P4.1c | Канарейка перед запуском Codex (fail-open хука закрывает мост) | тест: сломанный хук → Codex не запускается |
| P4.1d | Шов `WorkerRuntime` (`run_turn`, `stop`) и `runtime/codex_bridge.py`: `exec --json [resume]`, разбор событий в `TurnResult`, «мозг» через `developer_instructions`, `-s workspace-write`, остановка дерева процесса | фейковый codex как фейковый claude; смоук на живом |
| P4.1e | Переключение в роутере: Claude `rate_limited` → кнопка «Лимит Claude до ЧЧ:ММ. Продолжить в Codex?» (или авто по `JARVIS_FALLBACK=ask|auto|off`); бриф для новой сессии; ревьюер в Codex — `-s read-only` + `--output-schema` | тесты роутера; живой прогон |
| P4.1f | Лимиты в `/status`: Claude `allowed_warning`, Codex `rate_limits` из файла сессии | тест на записанном файле |

ADR: «Codex — второй worker; подключается только с адаптером Guard и канарейкой» — уточняет ADR 0001.

**Решения владелицы (2026-10-05)**:
1. Доверие к хукам — **она подтверждает сама** один раз (`/hooks` в Codex в папке Jarvis); флаг `--dangerously-bypass-hook-trust` у бота не используем. Канарейка моста проверяет, что доверие не слетело.
2. Переключение — **по кнопке**, и так, чтобы ей было понятно, что происходит и в какой момент (схема — в ответе владелице 2026-10-05, после согласования переносится сюда).
3. Проверяющий в режиме Codex — **тоже Codex** (`-s read-only`, `--output-schema`, `--ephemeral`); под ответом «Проверено Codex».

Схема переключения (согласована 2026-10-05): лимит Claude кончился → сообщение «⏳ Лимит Claude закончился, обновится в ЧЧ:ММ; задача … не доделана: …» и кнопки **[Продолжить в Codex] [Подождать до ЧЧ:ММ]**. Codex получает сводку (запрос, план, сделанные файлы); карточка и ответы помечены «🟢 Codex», внизу «Сделано в Codex»; её следующие сообщения тоже идут в Codex. «Подождать» — задача сама стартует в Claude в момент сброса. Лимит Claude восстановился → бот сообщает и сам возвращается к Claude со сводкой сделанного в Codex (единственный автоматический шаг). `/status` — кто работает и остатки лимитов; `/codex`, `/claude` — ручное переключение. Guard в Codex проверяется перед каждым запуском; доверие к хукам слетело — Codex не запускается, бот присылает инструкцию «/hooks».

## Источники

- [Codex: Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced.md) — хуки в `config.toml`/`hooks.json`, доверие к проекту, песочница, `approval_policy`
- [Codex: Hooks](https://learn.chatgpt.com/docs/hooks.md) — события, поля входа, способы запрета, доверие
- [Codex exec --json: события](https://littlebearapps.com/help/untether/exec-json-cheatsheet) — `turn.failed`, типы элементов (сторонний конспект; основное подтверждено прогоном)
