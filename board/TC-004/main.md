---
key: "TC-004"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Clear all ratings очищает библиотеку"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-01", "automation:active"]
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

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_smoke.py` → `9 passed in 329.52s`, `PYTEST_EXIT=0`
  (в т.ч. `test_clear_all_ratings`).
- **Красная проба (п.7):** порча проверяемого условия — действие «Clear all ratings» в тесте
  пропущено (рейтинги остаются в БД). Прогон `-k test_clear_all_ratings --reruns 0` → `FAILED`:
  `AssertionError: ожидали 0 рейтингов, в БД: 5` (`settings_steps.py:112`, on-device sqlite3) —
  падение указывает на суть (после очистки рейтингов не должно остаться).
- **Откат:** `git checkout -- framework/tests/test_smoke.py`; дифф теста чист.
