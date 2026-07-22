---
key: "TC-002"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Нижняя навигация переключает Browse/Library/Settings"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:smoke", "automation:active"]
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

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_smoke.py` → `9 passed in 329.52s`, `PYTEST_EXIT=0`
  (в т.ч. `test_bottom_nav_switches_screens`).
- **Красная проба (п.7):** порча проверяемого условия — навигация в шаге «открыть Settings»
  подменена на открытие Library (экран Settings не отрисовывается). Прогон
  `-k test_bottom_nav_switches_screens --reruns 0` → `FAILED`:
  `AssertionError: экран Settings не отрисовался (нет секции Theme)` (`settings_steps.py:15`) —
  падение указывает на суть (assert реально проверяет наличие экрана Settings, а не факт нажатия).
- **Откат:** `git checkout -- framework/tests/test_smoke.py`; дифф теста чист.
