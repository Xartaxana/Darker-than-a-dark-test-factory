---
key: "TC-005"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Переключение темы Light/Dark/System не роняет приложение"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings"]
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

# Переключение темы Light/Dark/System не роняет приложение

_Спроецировано из `test-cases/smoke/TC-005.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-005 — Стабильность переключения тем

## Сценарий (Given-When-Then)
**Given** открыт экран Settings
**When** последовательно выбраны Dark, Light, System
**Then** экран Settings по-прежнему отрисован (приложение не упало)
