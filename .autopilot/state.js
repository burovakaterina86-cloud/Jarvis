window.STATE =
{
  "slug": "essa-jarvis",
  "dir": "2026-09-17-essa-jarvis",
  "title": "ESSA-JARVIS — автономный агент поверх Claude Code",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-17-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-17T22:36:55+07:00",
  "updatedAt": "2026-09-18T12:27:12+07:00",
  "finishedAt": "2026-09-18T12:27:12+07:00",
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-09-17T22:36:55+07:00",
      "finishedAt": "2026-09-17T22:38:44+07:00"
    },
    {
      "id": "manifest",
      "status": "done",
      "startedAt": "2026-09-17T22:38:44+07:00",
      "finishedAt": "2026-09-17T22:38:44+07:00"
    },
    {
      "id": "briefing",
      "status": "done",
      "startedAt": "2026-09-17T22:38:44+07:00",
      "finishedAt": "2026-09-17T22:52:14+07:00"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-09-17T22:52:14+07:00",
      "finishedAt": "2026-09-17T23:24:56+07:00",
      "note": "G2: 30 находок закрыты; дизайн подтверждён «ок»"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-09-17T23:24:56+07:00",
      "finishedAt": "2026-09-17T23:24:56+07:00",
      "note": "8 тасков, ярус T2, 5 волн"
    },
    {
      "id": "build",
      "status": "done",
      "startedAt": "2026-09-17T23:24:56+07:00",
      "note": "8 из 8 тасков готовы",
      "finishedAt": "2026-09-18T12:27:12+07:00"
    },
    {
      "id": "review",
      "status": "done",
      "startedAt": "2026-09-17T23:33:03+07:00",
      "finishedAt": "2026-09-18T12:27:12+07:00",
      "note": "все таски проверены двумя ревьюерами"
    },
    {
      "id": "final",
      "status": "done",
      "startedAt": "2026-09-18T12:27:12+07:00",
      "finishedAt": "2026-09-18T12:27:12+07:00",
      "note": "слепая приёмка: живой путь не подтверждён до входа в Claude"
    }
  ],
  "requirements": {
    "total": 62,
    "done": 46,
    "inTicket": 0,
    "inSpec": 0,
    "placeholder": 2,
    "deferred": 11,
    "dropped": 3
  },
  "tickets": [
    {
      "id": "01",
      "title": "Каркас и защита: Guard, политика, настройки",
      "requirements": [
        "R02",
        "R07",
        "R13",
        "R14",
        "R15",
        "R09",
        "R44"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        ".claude/settings.json",
        ".claude/hooks/guard.py",
        "runtime/policy.yaml",
        "runtime/__init__.py",
        "tests/test_guard.py",
        "requirements.txt",
        ".env.example",
        ".gitignore",
        "start.bat",
        ".venv/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-17T23:25:17+07:00",
      "repairFindings": [
        "shell-запись вне корня → ask; чтение .env через glob → deny; deadline Approvals < таймаут хука; кавычки не выключают deny; нераспознанное удаление → ask; лимит не задан → ask",
        "запись через $HOME/$env:/%VAR% → ask; [IO.File]::Delete → ask"
      ],
      "finishedAt": "2026-09-17T23:40:46+07:00",
      "tests": {
        "passed": 105,
        "failed": 0
      },
      "commit": "2077875"
    },
    {
      "id": "02",
      "title": "Мост к Claude Code: ходы, сессии, очередь, события",
      "requirements": [
        "R02",
        "R03",
        "R04",
        "R05",
        "R06",
        "R11",
        "R13"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "runtime/claude_bridge.py",
        "runtime/sessions.py",
        "runtime/task_router.py",
        "runtime/events.py",
        "runtime/jarvis-turn.md",
        "tests/test_bridge.py",
        "tests/fake_claude/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-17T23:40:46+07:00",
      "repairFindings": [
        "повтор хода после выполненных инструментов; переполнение по тексту ответа; бюджет списывается на неуспешных ходах; непокрытые ветки разбора; убийство дерева",
        "D02: окружение сессии Claude Code ломало вход по подписке"
      ],
      "finishedAt": "2026-09-18T11:35:17+07:00",
      "tests": {
        "passed": 215,
        "failed": 0
      },
      "commit": "3d27130"
    },
    {
      "id": "03",
      "title": "Approvals API: подтверждения владелицы",
      "requirements": [
        "R14",
        "R26"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "runtime/approvals.py",
        "tests/test_approvals.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-17T23:40:46+07:00",
      "repairFindings": [
        "client_gone недостижим; таймаут сервера < срока Guard; тесты 400/stop; права токена; обрезка журнала"
      ],
      "finishedAt": "2026-09-18T06:42:22+07:00",
      "tests": {
        "passed": 183,
        "failed": 0
      },
      "commit": "d163431"
    },
    {
      "id": "05",
      "title": "Личность, память, правила и папка ESSA",
      "requirements": [
        "R08",
        "R10",
        "R11",
        "R12",
        "R19",
        "R29i",
        "R30",
        "R33",
        "R34"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "CLAUDE.md",
        "SOUL.md",
        "GOALS.md",
        "MEMORY.md",
        ".claude/rules/",
        ".claude/hooks/memory_notice.py",
        ".claude/hooks/capture_learning.py",
        ".claude/hooks/pre_compact.py",
        ".claude/hooks/session_start.py",
        "essa-ai/",
        "memory/",
        "scripts/check_context_size.py",
        "tests/test_memory_hooks.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-17T23:40:46+07:00",
      "repairFindings": [
        "🧠 запомнил при неуспешной записи; разбор transcript учитывает вставки хуков и субагентов; нет теста на check_context_size"
      ],
      "finishedAt": "2026-09-18T06:44:22+07:00",
      "tests": {
        "passed": 193,
        "failed": 0
      },
      "commit": "e52abcc"
    },
    {
      "id": "06",
      "title": "Контентные навыки и браузер",
      "requirements": [
        "R21",
        "R22",
        "R23",
        "R24",
        "R25",
        "R26",
        "R27",
        "R35",
        "G03",
        "G05",
        "G07",
        "G08"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        ".claude/skills/trend-radar/",
        ".claude/skills/competitor-research/",
        ".claude/skills/content-strategy/",
        ".claude/skills/content-plan/",
        ".claude/skills/copywriting/",
        ".claude/skills/reels-script/",
        ".claude/skills/repurpose-content/",
        ".claude/skills/browser-use/",
        ".mcp.json",
        "integrations/browser/",
        "tests/test_skills_format.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-17T23:44:15+07:00",
      "repairFindings": [
        "профиль браузера у login.py и MCP считается по-разному; формулировка запрета публикации; find_browser; тесты"
      ],
      "finishedAt": "2026-09-18T06:46:35+07:00",
      "tests": {
        "passed": 220,
        "failed": 0
      },
      "commit": "9517118"
    },
    {
      "id": "04",
      "title": "Telegram: бот владелицы, голос, файлы, статус, кнопки",
      "requirements": [
        "R06",
        "R17i",
        "R18",
        "R07",
        "G11",
        "R27",
        "R14"
      ],
      "blockedBy": [
        "02",
        "03"
      ],
      "wave": 3,
      "zone": [
        "integrations/telegram/",
        "integrations/__init__.py",
        "tests/test_telegram.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-18T06:40:01+07:00",
      "repairFindings": [
        "режим настройки отвечал посторонним; new_session не показывался; два статус-сообщения; доставка ответа без защиты; uses_browser по словам; дыры в тестах"
      ],
      "finishedAt": "2026-09-18T07:00:04+07:00",
      "tests": {
        "passed": 251,
        "failed": 0
      },
      "commit": "525dea4"
    },
    {
      "id": "07",
      "title": "Навыки и помощники, которые агент создаёт сам",
      "requirements": [
        "R33",
        "R34",
        "G01",
        "G04"
      ],
      "blockedBy": [
        "04",
        "05"
      ],
      "wave": 4,
      "zone": [
        ".claude/skills/create-skill/",
        ".claude/skills/create-agent/",
        "drafts/",
        "runtime/activation.py",
        "integrations/telegram/",
        "tests/test_activation.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-18T07:00:04+07:00",
      "repairFindings": [
        "базовые помощники оказались включены без кнопки; тесты зависят от рабочего дерева; статус теста по слову; неатомарная активация"
      ],
      "finishedAt": "2026-09-18T11:38:52+07:00",
      "tests": {
        "passed": 290,
        "failed": 0
      },
      "commit": "9653129"
    },
    {
      "id": "08",
      "title": "Сквозная проверка, справочник и запуск",
      "requirements": [
        "R07",
        "R12",
        "R27",
        "R42",
        "R43",
        "R46",
        "R28"
      ],
      "blockedBy": [
        "06",
        "07"
      ],
      "wave": 5,
      "zone": [
        "docs/REFERENCE.md",
        "docs/SETUP.md",
        "tests/test_e2e_offline.py",
        "scripts/",
        "start.bat"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-18T11:38:52+07:00",
      "repairFindings": [
        "в документах не сказано, что живой прогон не выполнялся; пример .env склеивал пояснение со значением; два сканера запрета; check_hooks пишет в рабочий журнал"
      ],
      "finishedAt": "2026-09-18T12:27:12+07:00",
      "tests": {
        "passed": 298,
        "failed": 0
      },
      "commit": "7f67618"
    }
  ],
  "singlePass": null,
  "tests": {
    "passed": 298,
    "failed": 0
  },
  "debt": {
    "placeholders": [
      "профиль ESSA.AI (essa-ai/*.md)",
      "SOUL.md / GOALS.md",
      "вход на сайты в браузере JARVIS",
      "лимит суммы покупок в policy.yaml"
    ],
    "assumptions": [
      "дневной бюджет запусков по умолчанию 100 (переменная JARVIS_DAILY_RUN_BUDGET пустая) — число выбрано за владелицу"
    ],
    "emptyEnv": [
      "TELEGRAM_BOT_TOKEN",
      "TELEGRAM_OWNER_ID"
    ]
  },
  "additions": [],
  "coverage": {
    "findings": 30,
    "missing": 18,
    "half": 12,
    "extra": "все — углубление R##.n или материалы пользователя; ничего не вырезано",
    "action": "все 30 закрыты правками spec.md (2026-09-17)"
  },
  "concerns": [
    "guard: браузерные click/type/press_key классифицируются по подписи element, которую пишет агент — MONEY в браузере ловится эвристикой (T01 craft)",
    "guard: shell-эвристика в принципе обходима (cd + относительный путь, переменные) — защита многослойная, но не абсолютная (T01)",
    "guard.py: дублированные проверки shell_tools/read_tools, раскрытие ~ в двух местах, список полей карт в двух файлах, импорты в середине test_guard.py (T01 craft)",
    "test_guard: поиск запрещённого флага исключает docs/ и .md (документация упоминает флаг как запрещённый) (T01 craft)",
    "decide(event, policy, root, env) и поле kind — сигнатура шире, чем в таске (T01 spec, не блокирует)",
    "approvals.py: addresses читает приватное _site._server; emit_event-заглушка дублирует guard._log_blocked (T03 craft)",
    "approvals: падение подписчика on_request только логируется — Guard ждёт до таймаута (T03 spec)",
    "хуки памяти: дублированная обёртка main в 4 файлах, неиспользуемые параметры (T05 craft)",
    "check_context_size: бюджет 12 KB считает только 4 корневых файла, правила (6.4 KB) отдельной строкой (T05 craft)",
    "capture_learning: порог «3 вызова инструментов» — эвристика, в спецификации не описан (T05 manifest/spec)",
    "delegation.md дублирует список базовых ролей из истории 55 — при расхождении с .claude/agents правило будет врать (T05 spec)",
    "claude_bridge: разбор события дублируется (_log_event/_absorb), «успех» считается в трёх местах (T02 craft)",
    "events.jsonl: ротация не синхронизирована между процессами (мост, guard, approvals) — возможна потеря дописей (T02 craft)",
    "навыки: политика безопасности частично продублирована из .claude/rules (T06 craft)",
    "trend-radar: ограничение «~15 минут браузерной работы» агент не может измерить (T06 craft)",
    "голос: путь faster-whisper не исполнялся ни разу (нет образца ogg) — проверить вживую на первом голосовом (T04)",
    "кнопки «Принято/Переделать/Опубликовано» появляются, только если агент упомянул папку комплекта в ответе (T04)",
    "отказы Guard не попадают в статус-сообщение: events.jsonl никто не читает (T04)",
    "статус не показывает отказы Guard: события blocked идут в events.jsonl, поток хода их не несёт (T04 spec/craft — долг)",
    "start.bat молча копирует .env из .env.example (в спецификации нет; поведение безопасное) (T04 spec)",
    "браузерные ходы не сериализуются глобально (uses_browser всегда False); при одном владельце ходы и так идут по очереди, риск — только при параллельных чатах (T04 долг)",
    "вход в claude на машине владелицы истёк (OAuth session expired) — до `claude` + /login бот получает auth_required (проверка в T08)",
    "сквозным путём не покрыты истёкший таймаут подтверждения и MONEY выше лимита (T08 craft — долг)",
    "числа таймаутов (590/580/620) названы в трёх местах: policy.yaml, approvals.py, REFERENCE.md (T08 craft)"
  ],
  "reviewers": {
    "manifestSpec": "a5b820cc515998171",
    "craft": "a8e2ba34d51fbe905"
  },
  "blind": {
    "verdict": "собрано; живой путь не подтверждён",
    "drift": [
      "R27 (Definition of Done MVP): манифест считал путь «сообщение с телефона → комплект контента» закрытым таском 04+06, слепая проверка показала: ни одного успешного хода не было — claude на машине отвечает auth_required, в essa-ai/content/ пусто",
      "R30 (память): структура есть, но ни одного факта не записано — не проверено вживую",
      "G11 (голос): модель faster-whisper не скачана, распознавание вживую не работало",
      "R25/G03/G05/G08 (браузер): профиль state/browser-profile пуст, ни одной браузерной задачи не выполнено",
      "R32 (состояния задач): в событиях нет PLANNING и REVIEW — эти состояния относятся к планировщику V0.7 и отложены",
      "R08/R10: SOUL.md и GOALS.md — метки [ЗАПОЛНИ], характер и цели фактически не заданы (ожидаемо: это факты владелицы)"
    ],
    "commands": [
      ".venv/Scripts/python.exe -m pytest -q → 297 passed",
      "tests/smoke_real_turn.py → auth_required (цепочка до claude отработала)",
      "scripts/check_hooks.py → все команды хуков исполняются как задумано",
      "scripts/check_context_size.py → 4.25 KB / 12 KB ok",
      "guard вживую: Read .env → exit 2; запись в runtime/policy.yaml → exit 2; запись в essa-ai/content → exit 0",
      "живой круг подтверждений: MONEY → кнопка → allow → exit 0",
      "npx @playwright/mcp@latest --version → 0.0.81"
    ]
  }
}
