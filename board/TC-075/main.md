---
key: "TC-075"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Note-кнопка инжектируется в work-блёрб replay-листинга тогда и только тогда, когда есть comment (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02/R-04", "automation:active"]
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

# Note-кнопка инжектируется в work-блёрб replay-листинга тогда и только тогда, когда есть comment (replay)

_Спроецировано из `test-cases/canary/TC-075.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-075 — Note-кнопка присутствует ⟺ есть comment (replay)

## Предусловия
- Приложение запущено, режим **replay** (`listing_basic.mitm`).
- Работа `DISLIKED` (900000005) засеяна с `rating=DISLIKE` и непустым
  `comment` (`seed_db.py::seed_with_comment`); остальные 4 работы без
  комментария.

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме, `DISLIKED` засеяна с
комментарием, открыта `listing_basic.mitm`

**When** страница полностью загружается (`applyRatings` применяет засеянные
данные)

**Then** `[data-ao3-btn-wrap]` работы `DISLIKED` содержит `[data-ao3-note-btn]`
с `title`, равным засеянному comment
**And** остальные 4 работы (без comment) НЕ имеют `[data-ao3-note-btn]`

**Инвариант:** тот же контракт, что TC-074 (биусловное присутствие Note-кнопки
по факту comment), детерминированно проверенный на смешанном наборе (1
прокомментированная работа + 4 без комментария на одной странице).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/listing_basic.mitm` |
| Работа | `DISLIKED` (900000005), `rating=DISLIKE`, `comment="..."` |

## Заметки для автоматизации
- Сидинг через `seed_with_comment` — уже поддерживает `comment` независимо от
  `rating`/`tags` (см. AT-BUG-004, инкремент 1). Блокеров нет.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
