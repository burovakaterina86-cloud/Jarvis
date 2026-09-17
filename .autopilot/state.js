window.STATE =
{
  "slug": "essa-jarvis",
  "dir": "2026-09-17-essa-jarvis--wip",
  "title": "ESSA-JARVIS — автономный агент поверх Claude Code",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": null,
  "briefFile": "2026-09-17-brief.md",
  "memoryFile": "CLAUDE.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-17T22:36:55+07:00",
  "updatedAt": "2026-09-17T23:20:36+07:00",
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
      "status": "active",
      "startedAt": "2026-09-17T22:52:14+07:00"
    },
    {
      "id": "plan",
      "status": "pending"
    },
    {
      "id": "build",
      "status": "pending"
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
    "done": 0,
    "inTicket": 0,
    "inSpec": 46,
    "placeholder": 0,
    "deferred": 11,
    "dropped": 3
  },
  "tickets": [],
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
