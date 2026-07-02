---
key: "TC-006"
project: "AO3"
issueType: "test-case"
status: "tc-draft"
priority: "p2"
summary: "Подписи вкладок Library соответствуют фактическому UI"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T04:30:00Z"
updated: "2026-07-02T04:30:00Z"
archived: false
resolution: null
---

# Подписи вкладок Library соответствуют фактическому UI

_Спроецировано из `test-cases/library/TC-006.md` (источник правды).
Статус в нашей машине: **Draft**._

# TC-006 — Подписи вкладок Library

## Сценарий (Given-When-Then)
**Given** открыт экран Library
**When** пользователь смотрит на строку вкладок
**Then** подписи: FAVORITE · KUDOSED · READ · PENDING · DISLIKED · FILES (верхний регистр)

## Заметки
Черновик: связан с BUG-001 (расхождение с PROJECT.md, где обещаны Loved/Liked/Downloads).
Ожидание уточняется после решения по BUG-001 (баг именования vs баг документации).
