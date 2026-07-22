---
key: "TC-003"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Засеянная работа попадает в свою вкладку Library"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-04", "automation:active"]
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

# Засеянная работа попадает в свою вкладку Library

_Спроецировано из `test-cases/smoke/TC-003.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-003 — Рейтинг → правильная вкладка Library

## Сценарий (Given-When-Then)
**Given** в Room засеяна работа с рейтингом R (по одной на каждый из SAVE/LIKE/READ/PENDING/DISLIKE)
**When** открыт экран Library и выбрана вкладка для рейтинга R
**Then** засеянная работа присутствует в этой вкладке

## Заметки
Детерминизм через сидинг Room (framework/data/seed_db.py), без обращения к AO3.
Параметризован на 5 рейтингов. Вкладки: FAVORITE/KUDOSED/READ/PENDING/DISLIKED.

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_smoke.py` → `9 passed in 329.52s`, `PYTEST_EXIT=0`
  (все 5 параметров `test_seeded_work_appears_in_correct_tab`).
- **Красная проба (п.7):** порча на уровне ДАННЫХ — в фикстуре `seeded_library` работа
  `W.LOVED` засеяна с рейтингом `DISLIKE` вместо `SAVE`. Прогон
  `-k 'test_seeded_work_appears_in_correct_tab and SAVE-LOVED' --reruns 0` → `FAILED`:
  `AssertionError: работа «A Loved Test Work» не найдена во вкладке FAVORITE`
  (`library_steps.py:41`) — падение указывает на суть (рейтинг определяет вкладку).
- **Откат:** `git checkout -- framework/tests/conftest.py`; дифф фикстуры чист.
