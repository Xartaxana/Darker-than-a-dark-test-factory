---
key: "TC-007"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Простановка каждого из 5 рейтингов со страницы работы (панель)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-04", "automation:active"]
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

# Простановка каждого из 5 рейтингов со страницы работы (панель)

_Спроецировано из `test-cases/rating/TC-007.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-007 — Пять рейтингов со страницы работы

## Предусловия
- Приложение запущено с чистыми данными (`pm clear` / fresh install).
- Открыта страница работы `/works/{id}` (работа из `framework/data/works.py`,
  например `LOVED.ao3_id`), URL распознан как work page (`onWorkPageLoaded`).
- Панель `RatingMenu` раскрыта (нижняя выезжающая панель над nav tabs).

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными и открыта страница работы `/works/{id}`
**And** панель рейтинга (`RatingMenu`) раскрыта, ни один из 5 рейтингов ещё не выбран

**When** пользователь нажимает кнопку рейтинга «R» (параметр: Loved / Liked / Read /
Pending / Disliked)

**Then** кнопка «R» отображается как выбранная (визуальное состояние `selected`)
**And** бейдж/цвет на странице обновляется без перезагрузки WebView
**And** в Library соответствующая вкладка (FAVORITE/KUDOSED/READ/PENDING/DISLIKED —
фактические подписи, см. framework/README.md) содержит эту работу после перехода
на экран Library

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `ao3_id` из `framework/data/works.py` (любая, напр. `LOVED`) |
| Рейтинг R | один из: Loved(SAVE) / Liked(LIKE) / Read(READ) / Pending(PENDING) / Disliked(DISLIKE) |

## Заметки для автоматизации
- Параметризовать по 5 значениям Rating; один прогон = одна простановка на чистых
  данных (не переиспользовать одну и ту же работу между итерациями без очистки, чтобы
  не маскировать deselect-логику — см. отдельный TC-008 для deselect).
- Панель находится ниже nav tabs, раскрывается тапом по pill-ручке (см.
  BrowserScreen.kt, `showRatingOverlay`/встроенная панель на work page — отличается от
  bottom-sheet листинга, см. TC-009).
- Проверка "запись в Room" — косвенно через Library (прямого доступа к БД из UI-теста
  нет; при необходимости прямой проверки — `framework/data/seed_db.py` подход для
  чтения, не только записи).
- LIKE/SAVE дополнительно авто-кликают AO3 kudos-кнопку на открытой странице работы
  (app-under-test/CLAUDE.md) — не является предметом этого кейса, но может быть
  наблюдаемым побочным эффектом при отладке (не assert здесь).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...» (deselect вынесен в TC-008)
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## Автоматизация (test-automator, 2026-07-03)

Реализовано в `framework/tests/test_rating.py::test_rate_work_from_work_page_panel`
(параметризован по 5 рейтингам). 3/3 стабильных зелёных прогона подряд (плюс полный
P0 smoke 17/17 без регрессий).

**Важная деталь реализации** (не меняет наблюдаемое поведение из сценария, но важна
для повторной автоматизации/поддержки): `savePanelRating` (app-under-test
`BrowserViewModel.kt`) при отсутствии строки в Room для `workId` сначала скрейпит
title/author/fandom/wordCount из живого DOM страницы работы (`workInfoJs`, селекторы
`h2.title.heading` и т.п.), и только затем сохраняет рейтинг. `ao3_id` в
`framework/data/works.py` синтетические и не существуют на archiveofourown.org —
живой скрейп такой страницы возвращает пустые поля, и Room получает строку с верным
рейтингом, но БЕЗ title (проверено вживую: запись отображается как "0 words" без
имени, что ломает проверку "работа W видна в вкладке по названию", саму по себе не
неверную). Чтобы тест проверял именно панель RatingMenu (as designed), а не сетевой
скрейп чужого сайта (не предмет этого кейса), фикстура `placeholder_seeded_work`
(`framework/tests/conftest.py`) предварительно сеет строку с `rating=None`, но
полными title/author/fandom/wordCount — тогда `savePanelRating` идёт по ветке
«обновить существующую строку» без обращения к DOM. Тот же приём естественным
образом получается в TC-016 (там `existing != null` из-за предшествующего рейтинга).

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T01:19:44Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса и `automation_status` не менялись).
- **Зелёный (п.6):** `Get-Device` → `DEVICE: emulator-5554`;
  `Invoke-Pytest tests/test_rating.py` → `6 passed in 213.26s`, `PYTEST_EXIT=0`
  (все 5 параметров `test_rate_work_from_work_page_panel`).
- **Красная проба (п.7):** порча проверяемого условия — действие панели `rate_current_work`
  пропущено (placeholder остаётся с `rating=None`). Прогон
  `-k 'test_rate_work_from_work_page_panel and SAVE' --reruns 0` → `FAILED`:
  `AssertionError: работа «A Loved Test Work» не найдена во вкладке FAVORITE`
  (`library_steps.py:41`) — падение указывает на суть (именно панель RatingMenu проставляет
  рейтинг, попадающий в Library).
- **Откат:** `git checkout -- framework/tests/test_rating.py`; дифф теста чист.
