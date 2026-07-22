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

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_smoke.py` → `9 passed in 329.52s`, `PYTEST_EXIT=0`
  (в т.ч. `test_theme_toggle_stable`).
- **Красная проба (п.7):** порча проверяемого условия — перед финальным assert добавлен уход
  с экрана Settings (`open_tab(driver, "Browse")`), так что проверка «Settings по-прежнему
  отрисован» встречает не-Settings. Прогон `-k test_theme_toggle_stable --reruns 0` → `FAILED`:
  `AssertionError: экран Settings не отрисовался (нет секции Theme)` (`settings_steps.py:15`) —
  падение подтверждает, что assert реально проверяет присутствие экрана Settings, а не проходит
  вслепую. (Замечание в scope п.7: assert кейса слабый — «Settings отрисован» вместо явной
  проверки применённой темы; это дизайн-вопрос п.3 F1, вне режима red-probe-only, здесь только
  зафиксирован.)
- **Откат:** `git checkout -- framework/tests/test_smoke.py`; дифф теста чист.
