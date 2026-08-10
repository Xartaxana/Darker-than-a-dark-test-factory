---
key: "AT-BUG-057"
project: "AO3"
issueType: "bug"
status: "bug-verified"
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
created: "2026-08-10T12:29:29Z"
updated: "2026-08-10T12:29:29Z"
archived: false
resolution: "done"
---

# Нестабильный TC-016 (p0, live): RatingOverlay не открывается на странице работы после open_work_page → open_tab(Browse); в изоляции 3/3 зелёный

_Спроецировано из `bugs/AT-BUG-057.md` (источник правды).
Статус в нашей машине: **Verified**._

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

## Карантин (снят — см. «Починка»)

Было: `automation_status: quarantined`, `quarantine_owner: test-maintainer`,
`quarantine_since: 2026-08-05T03:20:00Z`, `quarantine_expiry` не задан.
`test-cases/library/TC-016.md`: `automation_status: quarantined → active`
(guard-переход, `schemas/transitions.yaml`), `quarantine_*`-поля очищены.

## Починка (test-maintainer, 2026-08-10)

**Найден код-грунтованный корень (не только диагностика).** `RatingMenu`
(`WorkRatingPanel` в `BottomBar.kt`) рендерится по условию `if (selectedTab ==
AppTab.BROWSE && isWorkPage)`. `isWorkPage` — состояние `BrowserViewModel`,
выставляется в `onPageLoaded(tabId, url)` (`BrowserViewModel.kt:474-487`, regex
`/works/(\d+)`), который вызывается СИНХРОННО из `WebViewClient.onPageFinished`
(`BrowserScreen.kt:594`). `framework/screens/browser_screen.py::open_work()`
до фикса ждал только `driver.current_url` — свойство navigation commit'а
chromedriver, которое обновляется РАНЬШЕ `onPageFinished` (тот же класс гонки,
что уже задокументирован в `wait_home_page_loaded` для домашней страницы). Тест
мог начать опрашивать `RatingOverlay.is_visible()` до того, как `isWorkPage`
вообще стало `true` — на быстрой сети `is_visible()`-поллинг (8s) успевал
догнать; на медленной/интерстишл-сети (задокументированный разброс 71s→131s
в изолированных прогонах 2026-08-05) — не всегда.

1. **`framework/screens/browser_screen.py::open_work()`** — добавлено явное
   ожидание маркера `window.__ao3AppDark` ПОСЛЕ commit'а URL (тот же приём,
   что `wait_home_page_loaded`: маркер инжектится ТЕМ ЖЕ `onPageFinished`
   сразу после `onPageLoaded`, его появление в свежем `window` детерминированно
   доказывает, что `isWorkPage` уже применилось). Разделяемый метод — фикс
   защищает ВСЕ вызовы `rate_current_work`/`add_tag_via_panel`/
   `assert_rating_panel_present_and_clickable`/`capture_panel_rating_baseline`
   после `open_work_page`, не только TC-016 (правило 9, класс, а не экземпляр).
2. **`framework/steps/rating_steps.py`** — усилена диагностика ассерта «меню
   рейтинга не появилось на странице работы» ВО ВСЕХ 4 местах, где он
   встречался (тот же класс, cм. п.1): сообщение теперь называет URL активной
   WebView-вкладки и признак `work_page` (тот же regex `/works/(\d+)`, что
   вычисляет `isWorkPage` в приложении, — диагностика согласована с реальным
   условием, не эвристика). `_work_page_diagnosis()` вычисляется ТОЛЬКО при
   провале (не на зелёном пути — не тратит лишний webview round-trip).
3. **Replay-двойник (п.2 «Что сделать») — оценён, НЕ сделан: дорого.**
   Сценарий формально не требует живого AO3 (работа сидится в Room, проверка —
   межвкладочное перемещение в Library), но САМ триггер — панель `RatingMenu`
   на `/works/{id}` — существует только внутри реальной WebView-страницы AO3;
   двойник потребовал бы либо mitm-записи полной страницы работы (уже есть
   похожие записи для TC-114/115, но там rating выставляется НЕ через панель
   work-page, а тег правится — другой путь), либо мок-страницы, воспроизводящей
   структуру, которую `ao3_bridge.js`/приложение ожидают от `/works/{id}` —
   риск разъехаться с реальным AO3 DOM тем же классом, что уже ловился в
   `AT-BUG-054` (испорченный класс блёрба в записи). Учитывая, что явное
   ожидание (п.1) устраняет причину race напрямую и дёшево, а replay-двойник
   добавляет содержательный риск драфта без замера выигрыша — не делаю;
   явная строка по DoD.

**Дефекты-собратья (доклад по правилу 9, не расширяю scope):** ни одного НОВОГО
блокера не обнаружено. Единственное найденное во время работы падение
(`test_edit_tag_on_already_saved_work_via_panel_does_not_redownload`, TC-114,
`@pytest.mark.replay`, разовый регрессионный прогон после правки shared
`open_work()`) — уже задокументированный `BUG-014` (app_bug, `status: Open`,
`red_lock` для TC-114/TC-115): сигнатура падения совпадает буква в букву с
тем, что описано в `bugs/BUG-014.md` (`assert_download_icon_shown` +
autouse-варнинг `download_oracle` про тот же файл
`ao3_A Loved Test Work_900000001.html`) — известный app-баг про ретроактивное
авто-скачивание, а не регрессия от этой правки (правка в `open_work()`
касается только ожидания загрузки страницы, не логики скачивания). Новый
test_debt-баг не заводится — уже покрыт открытым `BUG-014`.

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10T11:15:00Z | framework (без изменения сборки приложения, test_debt) | TC-016, изолированно, 3 независимых вызова `Invoke-Pytest -k test_change_rating_moves_work_between_tabs -v` подряд | PASSED / PASSED / PASSED — `1 passed, 321 deselected in 53.88s` `PYTEST_EXIT=0`; `... in 51.88s` `PYTEST_EXIT=0`; `... in 52.27s` `PYTEST_EXIT=0` | test-maintainer: 3/3 зелёных с усиленной диагностикой — карантин снят, `awaiting: qa` для fix-verifier |
| 2026-08-10T12:29:29Z | source_commit 6f884d97, APK versionCode 12/dev-local (test_debt в обвязке, сборка приложения не тронута фиксом) | fix-verifier, независимый прогон: TC-016, `Invoke-Pytest -k test_change_rating_moves_work_between_tabs -v` — 1 прогон (live-тест, единичный прогон легален per манифест диспатча, поверх 3x-серии maintainer'а) | `1 passed, 339 deselected in 49.90s`, `PYTEST_EXIT=0` | **Verified** — fix-verifier, D1 mode=verify, независимое подтверждение |

## Обсуждение

**[test-maintainer @ 2026-08-10T11:20:00Z]** Root-cause найден чтением кода
приложения (МЕСТО РЕНДЕРА `WorkRatingPanel`/`BottomBar.kt`) — race между
navigation commit и `onPageFinished`/`isWorkPage`, тот же класс, что уже
задокументирован в `wait_home_page_loaded`. Красная проба диагностики:
временный тест `test_at_bug_057_red_probe` (вызов `rate_current_work` на
домашней странице AO3, НЕ work-page) дал `AssertionError: меню рейтинга не
появилось на странице работы (url='https://archiveofourown.org/'
work_page=False)` — сообщение называет URL и признак work-page, как требовал
DoD. Проба удалена откатом по байтовой копии в этом же ходе (`git status
--porcelain` пуст ДО и ПОСЛЕ отката, сверено). `awaiting: qa` — жду
fix-verifier (правило D1/B4, сборка приложения не нужна). Диф НЕ закоммичен
этим ходом (правила git-safety для субагента) — лежит в рабочем дереве
репозитория; путь: `framework/screens/browser_screen.py`,
`framework/steps/rating_steps.py`, `test-cases/library/TC-016.md`,
`bugs/AT-BUG-057.md`.

**2026-08-10T12:29:29Z — fix-verifier (D1, mode=verify):** координатор
закоммитил дифф коммитом `72adfc1` (`git log`/`git show --stat`
подтверждают: `bugs/AT-BUG-057.md`, `framework/screens/browser_screen.py`,
`framework/steps/rating_steps.py`, `test-cases/library/TC-016.md`) —
`fixed_in` исправлен на `72adfc1` (было: описательная строка «не
закоммичено этим ходом», устаревшая после коммита координатора).
Независимый прогон TC-016 (live, единичный прогон достаточен per
манифест) на этом HEAD, `emulator-5554` (`Get-Device` → `DEVICE`):
`1 passed, 339 deselected in 49.90s`, `PYTEST_EXIT=0`. Сборка приложения —
`source_commit 6f884d97`, установленный APK `versionCode 12`/`dev-local`,
долг в обвязке (race в ожидании `onPageFinished`), от сборки не зависит.
`Fixed` → `Verified`, `awaiting: qa` → `awaiting: none`, лок снят.
