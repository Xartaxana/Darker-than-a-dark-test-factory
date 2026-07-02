---
key: "TC-002"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Нижняя навигация переключает Browse/Library/Settings"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:smoke"]
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

# Нижняя навигация переключает Browse/Library/Settings

_Спроецировано из `test-cases/smoke/TC-002.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-002 — Нижняя навигация

## Сценарий (Given-When-Then)
**Given** приложение запущено (нативный UI готов)
**When** пользователь раскрывает нижнюю ручку и открывает Settings
**Then** экран Settings отрисован (секция Theme видна)
**And when** пользователь открывает Library
**Then** видна вкладка FAVORITE

## Заметки
На вкладке Browse навигация скрыта за ручкой-пилюлей; `BottomNav` раскрывает её.
