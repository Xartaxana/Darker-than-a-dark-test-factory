---
key: "TC-071"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Rate-кнопка инжектируется в каждый неоценённый work-блёрб replay-листинга (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-19T04:33:02Z"
updated: "2026-07-19T04:33:02Z"
archived: false
resolution: "done"
---

# Rate-кнопка инжектируется в каждый неоценённый work-блёрб replay-листинга (replay)

_Спроецировано из `test-cases/canary/TC-071.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-071 — Rate-кнопка на неоценённом блёрбе (replay)

## Предусловия
- Приложение запущено с чистыми данными (ни одна работа не оценена), режим
  **replay** (`framework/data/recordings/listing_basic.mitm`).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме с чистыми данными и открыта
`listing_basic.mitm`

**When** страница полностью загружается и bridge выполняет начальный проход
инъекции

**Then** каждая из 5 работ (`LOVED/KUDOSED/READ/PENDING/DISLIKED`,
`framework/data/works.py::ALL`) имеет собственную `[data-ao3-rate-btn]` с
атрибутом, равным её `ao3_id`, в состоянии "неоценено" (прозрачный фон)

**Инвариант:** тот же контракт, что TC-070, на детерминированном фиксированном
наборе из 5 работ — регрессионный якорь.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/listing_basic.mitm` |
| Работы | `ALL` (900000001..900000005) |

## Заметки для автоматизации
- Фикстура готова (AT-BUG-004 Verified), блокеров нет.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
