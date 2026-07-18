---
key: "TC-073"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Rate-кнопка отражает бейдж рейтинга непрозрачным цветом BADGE-палитры на replay-листинге (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02/R-04"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T08:56:07Z"
updated: "2026-07-18T08:56:07Z"
archived: false
resolution: null
---

# Rate-кнопка отражает бейдж рейтинга непрозрачным цветом BADGE-палитры на replay-листинге (replay)

_Спроецировано из `test-cases/canary/TC-073.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-073 — Бейдж рейтинга = цвет Rate-кнопки (replay)

## Предусловия
- Приложение запущено, режим **replay** (`listing_basic.mitm`).
- Работа `LOVED` (900000001) засеяна в Room с `rating=SAVE` ДО первого рендера
  листинга (`seed_db.py::seed`).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме, работа `LOVED` засеяна с
рейтингом `SAVE`, открыта `listing_basic.mitm`

**When** страница полностью загружается (Kotlin вызывает `applyRatings` с
засеянными данными по видимым work id)

**Then** `[data-ao3-rate-btn]` работы `LOVED` (work id 900000001) имеет
непрозрачный `background-color`, равный `BADGE.SAVE.bg`, и бордер, равный
`BADGE.SAVE.border`
**And** `[data-ao3-rate-btn]` остальных 4 работ (не засеяны) остаются в
состоянии "неоценено" (прозрачный фон) — детерминированное подтверждение, что
закраска per-work, не глобальная

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/listing_basic.mitm` |
| Работа | `LOVED` (900000001), `rating=SAVE` |

## Заметки для автоматизации
- Сидинг через `seed_db.py::seed([(W.LOVED, "SAVE")])` перед стартом
  приложения — существующая инфраструктура, блокеров нет.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
