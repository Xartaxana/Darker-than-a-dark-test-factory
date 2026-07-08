---
key: "TC-001"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Запуск приложения и загрузка AO3 в WebView"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:smoke", "risk:R-03", "automation:active"]
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

# Запуск приложения и загрузка AO3 в WebView

_Спроецировано из `test-cases/smoke/TC-001.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-001 — Запуск и загрузка AO3

## Сценарий (Given-When-Then)
**Given** приложение установлено с чистыми данными
**When** приложение запущено
**Then** WebView указывает на `archiveofourown.org`

## Заметки
Live-режим. Cloudflare bot-check не влияет — проверяется домен активной страницы.

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).
