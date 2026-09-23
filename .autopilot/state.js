window.STATE =
{
  "slug": "essa-style-and-visuals",
  "dir": "2026-09-21-essa-style-and-visuals",
  "title": "Стиль Катерины и картинки: конвейер текста + карусели, обложки, фоны сторис",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-21-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-21T09:00:00+07:00",
  "updatedAt": "2026-09-23T15:00:00+07:00",
  "finishedAt": "2026-09-23T15:00:00+07:00",
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-09-21T09:00:00+07:00",
      "finishedAt": "2026-09-21T09:05:00+07:00"
    },
    {
      "id": "manifest",
      "status": "done",
      "startedAt": "2026-09-21T09:05:00+07:00",
      "finishedAt": "2026-09-21T09:10:00+07:00"
    },
    {
      "id": "briefing",
      "status": "skipped",
      "note": "выбор сделан кнопкой; размеры и стиль уже заданы её файлами"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-09-21T09:10:00+07:00",
      "finishedAt": "2026-09-21T09:25:00+07:00",
      "note": "сверка покрытия нашла 6 пропусков — спецификация исправлена"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-09-21T09:25:00+07:00",
      "finishedAt": "2026-09-21T09:30:00+07:00",
      "note": "4 таска в 2 волнах"
    },
    {
      "id": "build",
      "status": "done",
      "startedAt": "2026-09-21T09:30:00+07:00",
      "note": "12 тасков сданы",
      "finishedAt": "2026-09-23T10:40:00+07:00"
    },
    {
      "id": "review",
      "status": "done",
      "finishedAt": "2026-09-23T10:40:00+07:00",
      "note": "12 тасков сданы"
    },
    {
      "id": "final",
      "status": "done",
      "startedAt": "2026-09-23T10:45:00+07:00",
      "finishedAt": "2026-09-23T15:00:00+07:00",
      "note": "закрыта облегчённо по её выбору: повторная слепая приёмка не проводилась"
    }
  ],
  "requirements": {
    "total": 45,
    "done": 40,
    "inTicket": 0,
    "inSpec": 0,
    "placeholder": 0,
    "deferred": 3,
    "dropped": 2
  },
  "tickets": [
    {
      "id": "01",
      "title": "Конвейер текста: textwriter → humaniser → сверка с голосом",
      "requirements": [
        "S05",
        "S06",
        "S04"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        ".claude/skills/textwriter/",
        ".claude/skills/humaniser/",
        ".claude/skills/copywriting/SKILL.md",
        ".claude/agents/copywriter.md",
        "tests/test_text_pipeline.py"
      ],
      "status": "done",
      "retries": 1,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-21T09:30:00+07:00",
      "tests": {
        "passed": 343,
        "failed": 0
      },
      "repairFindings": [
        "тесты — grep по собственной прозе: баны захардкожены вместо сверки с её файлами, порядок проверяется подстрокой схемы, отказ не покрыт"
      ],
      "finishedAt": "2026-09-21T15:10:00+07:00",
      "commit": "d0a47c5 + 44ae65e"
    },
    {
      "id": "02",
      "title": "Картинки: карусели, обложки, фоны сторис",
      "requirements": [
        "S07",
        "S08",
        "S01",
        "E02",
        "E03",
        "E04"
      ],
      "blockedBy": [],
      "wave": 2,
      "zone": [
        "integrations/visuals/",
        ".claude/skills/carousel-instagram/",
        "tests/test_visuals.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "startedAt": "2026-09-21T14:55:00+07:00",
      "finishedAt": "2026-09-21T17:10:00+07:00",
      "commit": "6bedd5a",
      "tests": {
        "passed": 391,
        "failed": 0
      }
    },
    {
      "id": "04",
      "title": "Заслон на чтение больших файлов",
      "requirements": [
        "S09"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "runtime/policy.yaml",
        ".claude/hooks/guard.py",
        "tests/test_guard.py"
      ],
      "status": "done",
      "retries": 1,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-09-21T09:30:00+07:00",
      "tests": {
        "passed": 343,
        "failed": 0
      },
      "repairFindings": [
        "limit считается в строках: Read(limit=999999) протаскивал весь файл мимо заслона; странный ввод без тестов"
      ],
      "finishedAt": "2026-09-21T15:20:00+07:00",
      "commit": "f756d35"
    },
    {
      "id": "03",
      "title": "Перенос остальных скиллов и формат create-skill",
      "requirements": [
        "S02",
        "S03",
        "E01"
      ],
      "blockedBy": [],
      "wave": 3,
      "zone": [
        ".claude/skills/reels/",
        ".claude/skills/content-engine/",
        ".claude/skills/create-skill/SKILL.md",
        "tests/test_skill_transfer.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "commit": "40fe496",
      "finishedAt": "2026-09-21T20:30:00+07:00"
    },
    {
      "id": "05",
      "title": "Плотность и графика по первому эталону",
      "requirements": [
        "G01",
        "G02",
        "G03",
        "G04",
        "G05",
        "G06",
        "G07",
        "G08"
      ],
      "blockedBy": [
        "02"
      ],
      "wave": 3,
      "zone": [
        "integrations/visuals/templates.py",
        "integrations/visuals/tokens.py",
        ".claude/skills/carousel-instagram/SKILL.md",
        "tests/test_visuals.py"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-21T15:45:00+07:00",
      "commit": "6bedd5a + 40fe496",
      "repairFindings": [
        "объём и воздух: блоки плоские, вертикаль пустая",
        "карточки перерастянуты во всю высоту вместо компактных; hourglass рисуется развалившейся; остаток пустоты под шагами; вставка скрина ни разу не проверена на настоящем файле"
      ],
      "finishedAt": "2026-09-21T20:30:00+07:00"
    },
    {
      "id": "06",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Пять скиллов с GitHub",
      "requirements": [
        "S02"
      ],
      "status": "done",
      "commit": "40fe496",
      "finishedAt": "2026-09-21T20:30:00+07:00",
      "wave": 3
    },
    {
      "id": "07",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Второй эталон: тонкие линии, оранжевый, портрет",
      "requirements": [
        "G09",
        "G10",
        "G11",
        "G12",
        "G13",
        "G14",
        "G15",
        "D01"
      ],
      "status": "done",
      "commit": "7866bae",
      "finishedAt": "2026-09-22T11:30:00+07:00",
      "wave": 4
    },
    {
      "id": "08",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Объём и сцена из её скринов",
      "requirements": [
        "G16",
        "G17",
        "G18"
      ],
      "status": "done",
      "commit": "e64dfc7",
      "finishedAt": "2026-09-22T13:30:00+07:00",
      "wave": 5
    },
    {
      "id": "09",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Размытые скрины, пометки отдельно",
      "requirements": [
        "G19",
        "G20"
      ],
      "status": "done",
      "commit": "ec24e97 + f6d364d",
      "finishedAt": "2026-09-22T15:00:00+07:00",
      "wave": 6
    },
    {
      "id": "10",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Её дизайн-система каруселей",
      "requirements": [
        "G21",
        "D03",
        "D04",
        "D05"
      ],
      "status": "done",
      "commit": "b04360b",
      "finishedAt": "2026-09-22T19:00:00+07:00",
      "wave": 7
    },
    {
      "id": "11",
      "retries": 1,
      "repairs": 0,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Дефекты «7 признаков» и новые кадры",
      "requirements": [
        "G21"
      ],
      "status": "done",
      "commit": "f1fbf5c",
      "finishedAt": "2026-09-23T09:30:00+07:00",
      "wave": 8
    },
    {
      "id": "12",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "blockedBy": [],
      "zone": [
        "integrations/visuals/"
      ],
      "title": "Навык знает вёрстку, сборка одной командой",
      "requirements": [
        "G21"
      ],
      "status": "done",
      "commit": "e7a8b76",
      "finishedAt": "2026-09-23T10:40:00+07:00",
      "wave": 9
    }
  ],
  "singlePass": null,
  "tests": {
    "passed": 568,
    "failed": 0
  },
  "debt": {
    "placeholders": [],
    "assumptions": [],
    "emptyEnv": []
  },
  "additions": [
    "отметка в файле комплекта о том, пройден ли конвейер очистки — служит S06",
    "в .venv установлен playwright + chromium — с разрешения владелицы; без него рендер зависел от внешнего браузера и терял пиксель по краю"
  ],
  "concerns": [
    "волна 1 оборвалась целиком: три исполнителя разом остановлены сторожевым таймером механизма запуска, не отказом кода; таск 01 успел половину, таски 02 и 04 — ничего. Перезапуск по двое",
    "заслон не ловит чтение через cat/Get-Content в shell: размер в произвольной командной строке надёжно не определить (T04, спецификация просила заслон на чтение)",
    "textwriter: описание навыка пришлось написать без двоеточия — yaml в тесте формата спотыкается о «: » в неквотированном скаляре (T01 craft)",
    "формат отметки о проходе конвейера продублирован дословно в трёх файлах — правка формата потребует трёх правок (T01 craft)",
    "заслон намеренно не покрывает чтение через shell (cat/Get-Content): размер в произвольной командной строке надёжно не определить (T04, граница названа в коде)",
    "таски 02 и 05 закоммичены зелёными, но ревью по осям манифест/спецификация/craft им ещё не проводилось — долг (лимит сессии)",
    "иконка шага при неизвестном имени молча подменяется нейтральным кружком: место не пустует, но ошибка в имени не видна (T05)",
    "ревью по осям манифест/спецификация/craft проведено для тасков 01 и 04; таски 02–12 шли по её глазу на рендере, формального ревью им не было — долг, закрывается приёмкой"
  ],
  "reviewers": {},
  "blind": {
    "verdict": "первая слепая приёмка: частично; все её находки закрыты тасками 13–15; повторная не проводилась — владелица выбрала закрыть без неё, чтобы не тратить лимит",
    "drift": [
      "повторной слепой проверки после тасков 13–15 не было — соответствие подтверждено только её глазом на рендере и тестами"
    ],
    "commands": [
      ".venv\\Scripts\\python.exe -m pytest -q → 568 passed",
      "python -m integrations.visuals.build essa-ai\\content6-09-23-7-priznakov → 9 PNG, код 0"
    ]
  },
  "coverage": {
    "findings": 6,
    "missing": 4,
    "half": 2,
    "extra": "present, жёсткий запрет показа текста, техрамки без записи в «решения за неё»",
    "action": "все 6 закрыты правками spec.md и тасков 02/03 (2026-09-21)"
  }
}
