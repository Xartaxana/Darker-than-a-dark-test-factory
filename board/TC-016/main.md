---
key: "TC-016"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Смена рейтинга перемещает work из одной вкладки Library в другую"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-04", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T11:20:00Z"
updated: "2026-08-10T11:20:00Z"
archived: false
resolution: "done"
---

# Смена рейтинга перемещает work из одной вкладки Library в другую

_Спроецировано из `test-cases/library/TC-016.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-016 — Смена рейтинга перемещает work между вкладками Library

## Предусловия
- Приложение запущено, в Room засеяна работа W с `rating=LIKE` (KUDOSED)
  (`framework/data/seed_db.py`).
- Открыт экран Library, вкладка KUDOSED содержит работу W.

## Сценарий (Given-When-Then)

**Given** приложение запущено, работа W засеяна с рейтингом Liked и присутствует во
вкладке KUDOSED экрана Library

**When** пользователь открывает страницу работы W (`/works/{id}`) и через панель
`RatingMenu` меняет рейтинг на Loved

**Then** после возврата на экран Library вкладка KUDOSED больше не содержит работу W
**And** вкладка FAVORITE содержит работу W

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `KUDOSED` из `framework/data/works.py`, засеяна с `rating=LIKE`, затем изменена на `SAVE` |

## Заметки для автоматизации
- Отличается от TC-008 (deselect до `rating=null`) — здесь смена между двумя
  ненулевыми рейтингами; отдельный сценарий, т.к. проверяет именно межвкладочное
  перемещение в Library, а не сам факт постановки/снятия.
- Не дублирует TC-003 (Automated, area=smoke — базовая проверка "рейтинг →
  правильная вкладка" на 5 параметрах); TC-016 фокусируется на *смене* уже
  существующего рейтинга.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## B3-поля (test-maintainer, 2026-07-08, AT-BUG-003)
Автоматизирован до гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось).
`automation_status: active` проставлен по факту (тест живёт в suite и зелёный).

## Ревью автотеста (red-probe ретрофит, test-reviewer, 2026-07-22)
Только пп.6-7 чек-листа F1 (статус кейса не меняется).
- Зелёный прогон: `Invoke-Pytest -k test_change_rating_moves_work_between_tabs`
  PASSED (в батче TC-016/027/028 3/3, 145.98s).
- **Красная проба (п.7, 2026-07-22T00:24:08Z):** порча целевого рейтинга в шаге —
  `rate_current_work(driver, "SAVE")` → `"READ"` (приложение выставляет РЕЙТИНГ,
  ведущий в другую вкладку). Тест УПАЛ на сути: `assert_work_in_tab(SAVE)` →
  «работа «A Kudosed Test Work» не найдена во вкладке FAVORITE» (работа ушла на
  вкладку READ, `assert_work_not_in_tab(LIKE)` при этом прошёл — работа корректно
  покинула KUDOSED). Осмысленный assert, не таймаут. Порча откачена в том же ходе
  (`git checkout -- framework/tests/test_library.py`), дифф чист. Тест умеет падать.

## Снятие карантина (test-maintainer, 2026-08-10, AT-BUG-057)
`automation_status: quarantined → active` (guard-переход, `schemas/transitions.yaml`
`{from: quarantined, to: active, by: [test-maintainer]}`), `quarantine_*`-поля
очищены. Причина карантина: `AssertionError: меню рейтинга не появилось на
странице работы` — гонка между navigation commit (`current_url`) и реальным
применением состояния `isWorkPage` (`BrowserViewModel.onPageLoaded`, вызывается
из `onPageFinished`, т.е. позже commit'а), от которой зависит рендер `RatingMenu`
(`BottomBar.kt`: `if (selectedTab == AppTab.BROWSE && isWorkPage)`). Починка —
`framework/screens/browser_screen.py::open_work()` теперь ждёт маркер
`window.__ao3AppDark` (инжектится тем же `onPageFinished` сразу после
`onPageLoaded`) ПОСЛЕ commit'а URL, тем же приёмом, что уже `wait_home_page_loaded`
использует для домашней страницы — доказывает, что `isWorkPage` уже применилось,
прежде чем `rate_current_work`/`add_tag_via_panel` и другие шаги начинают
опрашивать `RatingOverlay`. Диагностика падения усилена (`rating_steps.py`):
сообщение ассерта теперь называет URL активной вкладки и признак work-page.
3/3 зелёных изолированных прогона (`Invoke-Pytest -k
test_change_rating_moves_work_between_tabs -v`, 53.88s/51.88s/52.27s,
`PYTEST_EXIT=0` каждый раз) — детали в `bugs/AT-BUG-057.md`.
