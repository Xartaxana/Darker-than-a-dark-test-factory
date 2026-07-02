---
key: "TC-001"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Запуск приложения и загрузка AO3 в WebView"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:smoke", "risk:R-03"]
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
