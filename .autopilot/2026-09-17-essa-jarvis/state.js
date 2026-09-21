window.STATE =
{
  "slug": "essa-jarvis",
  "dir": "2026-09-17-essa-jarvis",
  "title": "ESSA-JARVIS — автономный агент поверх Claude Code",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-18-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-17T22:36:55+07:00",
  "updatedAt": "2026-09-20T11:40:00+07:00",
  "finishedAt": "2026-09-20T11:40:00+07:00",
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
      "startedAt": "2026-09-18T15:15:36+07:00",
      "finishedAt": "2026-09-18T15:22:00+07:00",
      "note": "добавлены приветствие, оформление Telegram-ответов и полный учёт загруженных файлов"
    },
    {
      "id": "briefing",
      "status": "skipped",
      "note": "вопросов не потребовалось — пример и ожидаемое поведение однозначны"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-09-18T15:22:00+07:00",
      "finishedAt": "2026-09-20T10:00:00+07:00",
      "note": "дополнения G12–G15 описаны историями 56–59"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-09-20T10:00:00+07:00",
      "finishedAt": "2026-09-20T10:05:00+07:00",
      "note": "два таска на дополнения: 09 (сделан), 10"
    },
    {
      "id": "build",
      "status": "done",
      "startedAt": "2026-09-20T10:05:00+07:00",
      "note": "10 из 10 тасков готовы",
      "finishedAt": "2026-09-20T11:05:00+07:00"
    },
    {
      "id": "review",
      "status": "done",
      "startedAt": "2026-09-20T10:25:00+07:00",
      "finishedAt": "2026-09-20T11:05:00+07:00",
      "note": "таск 10 — PASS по манифесту и спецификации; 8 находок craft закрыты дозапросом"
    },
    {
      "id": "final",
      "status": "done",
      "startedAt": "2026-09-20T11:05:00+07:00",
      "finishedAt": "2026-09-20T11:40:00+07:00"
    }
  ],
  "requirements": {
    "total": 69,
    "done": 51,
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
    },
    {
      "id": "09",
      "title": "Статус-карточка не засоряет чат",
      "requirements": [
        "G12"
      ],
      "blockedBy": [],
      "wave": 6,
      "zone": [
        "integrations/telegram/status.py",
        "integrations/telegram/gateway.py",
        "tests/test_telegram.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-18T12:30:00+07:00",
      "finishedAt": "2026-09-18T12:58:36+07:00",
      "tests": {
        "passed": 311,
        "failed": 0
      },
      "commit": "e1e829b",
      "repairFindings": [
        "D03: включение помощников кнопкой убрало черновики из HEAD — два теста состава поставки стали красными; роль теперь проверяется там, где лежит сейчас",
        "потеряна строгость: лишний файл в drafts/agents и инертная проверка validate — возвращены (коммит 88bed85)"
      ]
    },
    {
      "id": "10",
      "title": "Приветствие, оформление ответов, видимость файлов ESSA",
      "requirements": [
        "G13",
        "G14",
        "G15"
      ],
      "blockedBy": [
        "09"
      ],
      "wave": 7,
      "zone": [
        "integrations/telegram/gateway.py",
        "integrations/telegram/render.py",
        "tests/test_telegram.py",
        ".env.example",
        "CLAUDE.md",
        "essa-ai/PROFILE.md",
        "essa-ai/STRATEGY.md",
        "essa-ai/PRODUCTS.md",
        "essa-ai/ANALYTICS.md"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-20T10:05:00+07:00",
      "repairFindings": [
        "нет тестов на таблицы и на нарезку с тегами; is_markup_error ловит чужие исключения без модуля telegram; ссылка без кавычек мимо теста; лишний импорт; порог HTML не назван; CLAUDE.md — карта не единственный вход"
      ],
      "finishedAt": "2026-09-20T11:05:00+07:00",
      "tests": {
        "passed": 314,
        "failed": 0
      },
      "commit": "2f1843e"
    }
  ],
  "singlePass": null,
  "tests": {
    "passed": 314,
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
  "additions": [
    "G13: приветствие «Привет, Катерина! На связи Джарвис.» при запуске",
    "G14: читаемое оформление ответов в Telegram",
    "G15: JARVIS должен учитывать все загруженные файлы и реальный ESSA knowledge pack"
  ],
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
    "числа таймаутов (590/580/620) названы в трёх местах: policy.yaml, approvals.py, REFERENCE.md (T08 craft)",
    "тесты базовых ролей: ветка activation.validate для роли-черновика сейчас не исполняется — все шесть ролей уже включены владелицей (T09 repair)",
    "render.py и status.py — два независимых сплиттера по одному лимиту (tag-safe и обычный); дублирование на публичной границе (T10 craft)",
    "ответ агента уходит через render.send в обход общего Gateway._send: будущие ретраи/троттлинг в _send не доедут до ответа (T10 craft)",
    "порог «лентой или файлом» считается по кускам HTML, а не markdown — граница сместилась на несколько процентов (T10 craft, решение принято осознанно)",
    "essa-ai/00_PROJECT_MAP.md (файл владелицы) не упоминает ~13 загруженных файлов и ссылается на три имени с «(1)», которых на диске нет — карта её, мы её не правим (T10 manifest, долг)"
  ],
  "reviewers": {
    "manifestSpec": "ac1c30759adb63eda",
    "craft": "a50f6ce250882d5b8"
  },
  "blind": {
    "verdict": "проект поднимается, главный сценарий проходит целиком; блокирующих находок нет",
    "drift": [
      "R25/G03/G05/G08 (браузер): MCP подключён и навык есть, но в приёмочном прогоне браузер не вызывался — вживую по-прежнему не проверен",
      "R34 (субагенты): шесть ролей включены, но в живом ходе агент их не вызвал и сам это отметил",
      "R31 (TrendRadar): есть навык, отдельного слоя integrations/trend-radar нет — ожидаемо, отложено",
      "R44 (структура): вместо workspaces/essa-ai — корневой essa-ai, навыки в .claude/skills, state/tasks.db нет (планировщик отложен)",
      "smoke_real_turn: на ходе «покажи .env» агент отказался сам, текстом, не дойдя до инструмента — заявленная проверка «Guard отказал» в этом прогоне не выполнилась; сам хук работоспособен (check_hooks: отказ exit 2)"
    ],
    "commands": [
      ".venv\\Scripts\\python.exe -m pytest -q → 314 passed",
      "scripts/check_hooks.py → все команды хуков исполняются как задумано",
      "scripts/check_context_size.py → 4.72 KB / 12 KB ok",
      "python -m integrations.telegram (= start.bat) → бот поднялся, приветствие ушло владелице, Approvals API слушает",
      "живой ход «Сделай контент для ESSA на завтра» → STATUS ok, собран комплект essa-ai/content/2026-09-21-не-изучай-нейросети/"
    ]
  }
}
