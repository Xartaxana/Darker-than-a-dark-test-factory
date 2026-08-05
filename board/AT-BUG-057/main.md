---
key: "AT-BUG-057"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p1"
summary: "Нестабильный TC-016 (p0, live): RatingOverlay не открывается на странице работы после open_work_page → open_tab(Browse); в изоляции 3/3 зелёный"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-016", "run:RUN-20260805-0432", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-05T03:20:00Z"
updated: "2026-08-05T03:20:00Z"
archived: false
resolution: null
---

# Нестабильный TC-016 (p0, live): RatingOverlay не открывается на странице работы после open_work_page → open_tab(Browse); в изоляции 3/3 зелёный

_Спроецировано из `bugs/AT-BUG-057.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-057 — карантин TC-016: панель рейтинга на странице работы не открылась (live), в изоляции не воспроизводится

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`).
Поверхность: `framework/tests/test_library.py::test_change_rating_moves_work_between_tabs`
(`@pytest.mark.p0`, `@pytest.mark.live`), `framework/steps/rating_steps.py:23-32`
(`rate_current_work` → `BottomNav.ensure_visible()` + `RatingOverlay.is_visible()`),
`framework/screens/rating_overlay.py`. Эмулятор `ao3_test_api34` (`emulator-5554`,
API 34), Appium `:4723`, режим live (реальный archiveofourown.org).

## Наблюдение

| Прогон | Дата | Исход | Сообщение |
|---|---|---|---|
| D1-прогон (fix-verifier), см. `docs/HANDOFF.md` «TC-016 флейк-кандидат» | 2026-07-29 | FAILED | `AssertionError` в том же шаге; исключающий одиночный прогон тогда НЕ снимался |
| `RUN-20260805-0432` (smoke p0, сборка 1.11 (12)) | 2026-08-05 | FAILED | `AssertionError: меню рейтинга не появилось на странице работы` — `steps/rating_steps.py:31` |

Изолированные перепрогоны (failure-analyst, 2026-08-05, та же сборка/эмулятор,
Appium перезапущен и health-checked, `Get-Device` → `DEVICE: emulator-5554`):

```
Invoke-Pytest -k test_change_rating_moves_work_between_tabs -v
  1 passed, 313 deselected in  71.13s   PYTEST_EXIT=0
  1 passed, 313 deselected in  72.08s   PYTEST_EXIT=0
  1 passed, 313 deselected in 131.57s   PYTEST_EXIT=0
```

3/3 зелёный. Разброс длительности (71s → 131s, x1.85) сам по себе указывает на
живую сеть как источник дисперсии.

## Почему это НЕ регресс сборки 1.11 (12)

1. Сборка = ровно два коммита поверх `63f6aac`:
   `77d65bc` (предикат авто-скачивания в `BrowserViewModel`) и `bfc8f41`
   (строка заголовка диалога лимита вкладок в `MainActivity.kt:619`). Ни один не
   касается `RatingMenu`/`RatingOverlay`, `isWorkPage`, `BottomBar`
   (`git -C app-under-test show --stat` обоих коммитов).
2. В ТОМ ЖЕ дневном регрессе на этой же сборке ЗЕЛЁНЫЙ `TC-114`
   (`test_edit_tag_on_already_saved_work_via_panel_does_not_redownload`) — он
   использует ТУ ЖЕ последовательность `open_work_page` → `open_tab(Browse)` →
   `RatingOverlay.is_visible()` (через `rating_steps.add_tag_via_panel`), только в
   replay. То есть механизм раскрытия панели на 1.11 работает.

## Почему причина не установлена (и почему это долг)

1. **Артефакты падения утрачены.** `Invoke-Pytest` чистит `framework/allure-results/`
   (`--clean-alluredir`) на каждом вызове, а после smoke шли ещё 4 сегмента
   regression — скриншот/page source/logcat момента падения недоступны задним
   числом (третий подряд рецидив класса, см. `runs/RUN-20260805-0432.md`
   «Дефекты-собратья» п.2).
2. **Тест live.** `open_work_page` ведёт WebView на настоящий AO3; панель
   `RatingMenu` рендерится только когда приложение опознало страницу как work-page
   (bridge). Любой интерстишл (bot-check/«shields up» — класс, ради которого в
   приложении есть коммит `63f6aac`), троттлинг или медленная отдача страницы дают
   ровно эту сигнатуру, и отличить их от дефекта теста по одному
   `assert overlay.is_visible()` без артефактов невозможно.
3. **Наблюдение бинарное.** `rate_current_work` падает голым «меню не появилось» —
   не сообщает ни URL вкладки, ни что реально на экране (интерстишл? не work-page?
   панель скрыта `AnimatedVisibility`?), поэтому даже сохранённый скриншот пришлось
   бы читать глазами. Тот же класс слепого наблюдения, что `AT-BUG-055`
   (`run-as cat` prefs) — там пустой ответ неотличим от «0 вкладок», здесь
   «панели нет» неотличимо от «страница не та».

## Что сделать (test-maintainer)

1. Усилить диагностику `rating_steps.rate_current_work`: в сообщение ассерта —
   текущий URL вкладки и признак work-page (то, что уже читает bridge), чтобы
   следующее падение само называло, дошла ли навигация до страницы работы.
2. Рассмотреть replay-двойник TC-016 (сценарий не требует живого AO3: работа
   засеяна в Room, проверяется перемещение между вкладками Library) — либо
   явное ожидание готовности work-page перед `rate_current_work`, а не
   немедленный `is_visible()`.
3. Снять карантин (`automation_status: active`) после зелёной серии на
   исправленном тесте.

## Карантин

`test-cases/library/TC-016.md`: `automation_status: quarantined`,
`quarantine_owner: test-maintainer`, `quarantine_since: 2026-08-05T03:20:00Z`,
`quarantine_expiry` не задан (действует `sla.quarantine_max`).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
