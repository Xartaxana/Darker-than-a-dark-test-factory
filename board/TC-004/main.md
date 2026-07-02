---
key: "TC-004"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Clear all ratings очищает библиотеку"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-01"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T03:00:00Z"
updated: "2026-07-02T03:00:00Z"
archived: false
resolution: "done"
---

# Clear all ratings очищает библиотеку

_Спроецировано из `test-cases/smoke/TC-004.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-004 — Clear all ratings

## Сценарий (Given-When-Then)
**Given** в библиотеке есть засеянные работы с рейтингами
**When** в Settings нажата «Clear…» и подтверждён диалог «Clear all ratings»
**Then** в БД приложения не осталось рейтингов
**And** вкладка FAVORITE больше не содержит засеянную работу

## Заметки
Кнопка «Clear…» с юникод-многоточием; клик в Compose на родителе текстового узла.
