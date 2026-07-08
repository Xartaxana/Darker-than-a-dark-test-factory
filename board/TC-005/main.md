---
key: "TC-005"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Переключение темы Light/Dark/System не роняет приложение"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-08T23:15:00Z"
updated: "2026-07-08T23:15:00Z"
archived: false
resolution: "done"
---

# Переключение темы Light/Dark/System не роняет приложение

_Спроецировано из `test-cases/smoke/TC-005.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-005 — Стабильность переключения тем

## Сценарий (Given-When-Then)
**Given** открыт экран Settings
**When** последовательно выбраны Dark, Light, System
**Then** экран Settings по-прежнему отрисован (приложение не упало)

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).
