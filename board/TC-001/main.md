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

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_smoke.py` → `9 passed in 329.52s`, `PYTEST_EXIT=0`
  (в т.ч. `test_app_launches_and_loads_ao3`).
- **Красная проба (п.7):** порча проверяемого условия — ожидаемый домен в assert подменён
  на `definitely-not-ao3.invalid`. Прогон `-k test_app_launches_and_loads_ao3 --reruns 0` →
  `FAILED`: `AssertionError: assert 'definitely-not-ao3.invalid' in 'https://archiveofourown.org/'`
  (`test_smoke.py:25`) — падение указывает на суть (реально загружен домен AO3).
- **Откат:** `git checkout -- framework/tests/test_smoke.py`; дифф теста чист.
