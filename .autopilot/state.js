window.STATE =
{
  "slug": "essa-style-and-visuals",
  "dir": "2026-09-21-essa-style-and-visuals--wip",
  "title": "Стиль Катерины и картинки: конвейер текста + карусели, обложки, фоны сторис",
  "mode": "semi",
  "depth": "normal",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-09-21-brief.md",
  "memoryFile": "AGENTS.md",
  "skillDir": "C:/Users/burov/.claude/skills/autopilot",
  "startedAt": "2026-09-21T09:00:00+07:00",
  "updatedAt": "2026-09-21T17:10:00+07:00",
  "finishedAt": null,
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
      "status": "active",
      "startedAt": "2026-09-21T09:30:00+07:00",
      "note": "готовы 01, 02, 04; 05 на доводке, 03 ждёт — прервано лимитом сессии до 19:00"
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
    "total": 17,
    "done": 0,
    "inTicket": 11,
    "inSpec": 0,
    "placeholder": 0,
    "deferred": 3,
    "dropped": 1
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
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    },
    {
      "id": "05",
      "title": "Плотность и графика по её эталону",
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
      "status": "repair",
      "retries": 0,
      "repairs": 2,
      "handoffs": 0,
      "startedAt": "2026-09-21T15:45:00+07:00",
      "commit": "6bedd5a (частично)",
      "repairFindings": [
        "объём и воздух: блоки плоские, вертикаль пустая",
        "карточки перерастянуты во всю высоту вместо компактных; hourglass рисуется развалившейся; остаток пустоты под шагами; вставка скрина ни разу не проверена на настоящем файле"
      ]
    }
  ],
  "singlePass": null,
  "tests": {
    "passed": 391,
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
    "иконка шага при неизвестном имени молча подменяется нейтральным кружком: место не пустует, но ошибка в имени не видна (T05)"
  ],
  "reviewers": {},
  "blind": {},
  "coverage": {
    "findings": 6,
    "missing": 4,
    "half": 2,
    "extra": "present, жёсткий запрет показа текста, техрамки без записи в «решения за неё»",
    "action": "все 6 закрыты правками spec.md и тасков 02/03 (2026-09-21)"
  }
}
