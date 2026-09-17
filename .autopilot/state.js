window.STATE =
{
  "slug": "essa-jarvis",
  "dir": "2026-09-17-essa-jarvis--wip",
  "title": "ESSA-JARVIS — автономный агент поверх Claude Code",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-17-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-17T22:36:55+07:00",
  "updatedAt": "2026-09-17T23:24:56+07:00",
  "finishedAt": null,
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
      "status": "active",
      "startedAt": "2026-09-17T23:24:56+07:00"
    },
    {
      "id": "review",
      "status": "pending"
    },
    {
      "id": "final",
      "status": "pending"
    }
  ],
  "requirements": {
    "total": 60,
    "done": 8,
    "inTicket": 38,
    "inSpec": 0,
    "placeholder": 0,
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    }
  ],
  "singlePass": null,
  "tests": null,
  "debt": {
    "placeholders": [
      "профиль ESSA.AI (essa-ai/*.md)",
      "SOUL.md / GOALS.md",
      "вход на сайты в браузере JARVIS",
      "лимит суммы покупок в policy.yaml"
    ],
    "assumptions": [],
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
  "concerns": [],
  "reviewers": {
    "manifestSpec": null,
    "craft": null
  },
  "blind": null
}
