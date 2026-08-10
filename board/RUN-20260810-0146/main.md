---
key: "RUN-20260810-0146"
project: "AO3"
issueType: "run"
status: "run-triaged"
priority: "p2"
summary: "RUN-20260810-0146"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T03:50:00Z"
updated: "2026-08-10T03:50:00Z"
archived: false
resolution: null
---

# RUN-20260810-0146

_Спроецировано из `runs/RUN-20260810-0146.md` (источник правды).
Статус в нашей машине: **Triaged**._

# RUN-20260810-0146 — regression (replay) на 1.10 (11)

## Контекст запуска

Продолжение того же дневного триггера, что `RUN-20260810-0145` (smoke) —
новая сборка (`source_commit 6f884d979a5c19465c6d8647737376864f424555`).
**Важный контекст (для триажа, не вердикт):** история `app-under-test`
переписана force-push'ем — новая цепочка коммитов идёт от `63f6aac`, а не от
прежнего `fdcbad9`/`bfc8f41a`. Держать в уме при интерпретации расхождений с
прошлым triaged-baseline `RUN-20260805-0437` (1.11 (12)) ниже.

**Селекция**: `python scripts/impact_select.py` (диапазон
`63f6aac3..6f884d979` резолвился по умолчанию, без `--from/--to`) →
**FULL REGRESSION** (`wide_impact`: `app/build.gradle.kts`,
`MainActivity.kt`; unknown-файлы вне карты: `.gitignore`, `.gitlab-ci.yml`).
Селекция НЕ сузила набор — гоняется полный marker-фильтр
`(p0 or p1) and not live`, тот же, что в прошлых full-регрессиях
(`RUN-20260805-0437`/`RUN-20260804-1624`/`RUN-20260803-2012`).

**Команда**: `pytest tests -m "(p0 or p1) and not live"` (`AO3_MODE=replay`),
165 selected / 314 collected (149 deselected). Окружение: эмулятор
`ao3_test_api34` (`emulator-5554`, поднят этим ходом с
`-WritableSystem`), Appium `:4723` (health-checked после smoke), APK уже
установлен. `Get-Device` и `:4723/status` сверялись до и после обрыва (ниже).

Прогон разбит на **2 сегмента** — не по плану, а вынужденно тем же классом
обрыва среды, что трижды документирован в `RUN-20260803-2012.md`/
`RUN-20260804-1624.md`/`RUN-20260805-0437.md`.

## Находка: сегмент 1 — фоновый job УБИТ ХАРНЕССОМ (рецидив, четвёртый подряд)

Первый вызов (`pytest tests -m "(p0 or p1) and not live"`, весь набор 165)
дошёл дот-прогрессом до **87%** (после `test_settings_ratings_fail_closed_unit.py`
и `test_side_panel.py`, частично внутрь `test_smoke.py`, 6 из 8 дотов) за
**~59 минут** (`01:46` → `02:45`), после чего системное `task-notification`
сообщило `status: killed`/`stopped` — сам pytest НЕ дошёл до `sessionfinish`,
в лог-файле нет ни итоговой строки, ни `PYTEST_EXIT`. Ожидание велось
СИНХРОННО `Wait-Process` (7 раундов по 500с внутри этого же хода, не
нотификацией) — обрыв всё равно произошёл, значит класс не в способе
ожидания, а в самом лимите времени жизни фонового job'а харнесса.

Позитивная сверка сразу после: `. tasks.ps1; Get-Device` → `DEVICE:
emulator-5554`; `Invoke-WebRequest http://127.0.0.1:4723/status` → `STATUS
200`. Среда ЖИВА — обрыв не связан со средой приложения/эмулятора/Appium,
это лимит самого фонового `run_in_background`-job'а (тот же диагноз, что три
предыдущих прецедента).

Дословный хвост сегмента 1 (последние строки перед обрывом):
```
tests\test_seed_db_schema_race_unit.py .....                             [ 70%]
tests\test_settings_ratings_fail_closed_unit.py .......................  [ 84%]
tests\test_side_panel.py .                                               [ 84%]
tests\test_smoke.py ......
```
(процесс убит здесь; строки суммирования и `PYTEST_EXIT` не появились)

**Реконструкция сегмента 1** (терминальный дот-прогресс, файл за файлом, до
точки обрыва): 140 тестов доведены до определённого исхода (133 passed, 7
failed) — см. таблицу падений ниже; последние 6 дотов `test_smoke.py`
(неполный файл, неоднозначно КАКИЕ 6 из 8) исключены из подсчёта и
переисполнены целиком сегментом 2. Cведение подтверждено программно по
allure-результатам (`as_id`-меткам): в `allure-results/` (директория
сегмента 1) — **146 result-файлов, 139 passed / 4 broken / 3 failed**
(разница 146 vs 140 — ровно 6 результатов `test_smoke.py`, исключённых из
подсчёта сегмента 1 и переисполненных сегментом 2 целиком: 146−6=140,
139−6=133; параметризованные дубли в архиве отдельно есть, но к этой
разнице отношения не имеют — каждый посчитан отдельным дотом прогресса).

## Находка: сегмент 2 — доведён явным списком оставшихся файлов

`pytest tests -m "(p0 or p1) and not live" tests/test_smoke.py
tests/test_tabs.py tests/test_visibility.py --alluredir=allure-results-seg2
--clean-alluredir` — покрывает test_smoke.py ПОЛНОСТЬЮ (не только
недостающий хвост), чтобы не осталось неоднозначности, какие из 8 тестов
файла уже выполнялись в сегменте 1 (тот же приём, что «disambiguation» в
`RUN-20260805-0437`). Дошёл до `sessionfinish` штатно, без единого обрыва
среды.

Дословный хвост:
```
tests\test_smoke.py ........                                             [ 32%]
tests\test_tabs.py ...........                                           [ 76%]
tests\test_visibility.py ......                                          [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
================ 25 passed, 3 deselected in 918.81s (0:15:18) =================
PYTEST_EXIT=0
```

`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` — счётчик
СЕГМЕНТА 2 (25 из 165 тестов); сегмент 1 (146 из 165, 59 мин) убит до
`pytest_terminal_summary`, его собственный счётчик recoveries НЕИЗВЕСТЕН
(строка не успела напечататься). Frontmatter `recoveries: "0/2"` относится
только к сегменту 2, не ко всему прогону — `ENV_ISSUE`-токена не было ни
разу среди того, что дошло до `sessionfinish`, но это не покрывает
непечатавшийся сегмент 1.

## Методика реконструкции 165/165

140 сегмента 1 (после исключения 6 неполных `test_smoke.py`) + 25 сегмента 2
= 165 уникальных тестов без пропусков и без двойного счёта: сегмент 2 ПОЛНОСТЬЮ
переисполнил `test_smoke.py`/`test_tabs.py`/`test_visibility.py` (25
selected — ровно столько, сколько для этих 3 файлов даёт маркер-фильтр),
поэтому любые результаты этих файлов из сегмента 1 (неполные, 6 дотов)
отброшены и заменены сегментом 2 целиком. Оставшиеся 24 файла (140 тестов)
взяты из сегмента 1 напрямую — сегмент 1 дошёл до конца КАЖДОГО из них
(последний полностью завершённый файл — `test_side_panel.py`, 84%).
Перекрёстная сверка по allure `as_id`: объединение TC-меток сегмента 1 и
сегмента 2 (сегмент 2 приоритетно перекрывает пересечение TC-002/TC-003 —
обе из `test_smoke.py`, единственное пересечение) даёт **90 уникальных
TC-xxx** с однозначным финальным статусом — таблица `tc_results` выше.

## Итог

165 уникальных тестов (по терминальному дот-прогрессу файл-за-файлом),
**158 passed, 7 failed, 0 skipped**. Полный список красных:

| Тест | TC | Файл | Allure-статус |
|---|---|---|---|
| test_rename_filter_profile_keeps_query_string | TC-085 | test_filter_profiles.py | broken |
| test_rename_filter_profile_to_duplicate_name | TC-086 | test_filter_profiles.py | broken |
| test_edit_tag_on_already_saved_work_via_panel_does_not_redownload | TC-114 | test_downloads.py | failed |
| test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload | TC-115 | test_downloads.py | failed |
| test_infinite_scroll_off_keeps_native_pagination | TC-129 | test_infinite_scroll.py | broken |
| test_infinite_scroll_on_loads_next_page_in_background | TC-130 | test_infinite_scroll.py | broken |
| test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos | TC-139 | test_rating_listing.py | failed |

## Сверка с прошлым triaged-baseline (`RUN-20260805-0437`, сборка 1.11(12), 154/165 passed)

Голый факт, вердикт (регрессия/улучшение/флейк/следствие переписанной
истории) не выношу — это failure-analyst:

- **Общие красные** (были там и здесь): TC-085, TC-086, TC-115, TC-129,
  TC-130, TC-139 (6).
- **Новое красное здесь**: TC-114 (`test_edit_tag_on_already_saved_work_via_panel_does_not_redownload`)
  — в прошлом triaged-прогоне был ЗЕЛЁНЫЙ.
- **Было красным там, зелёное здесь**: TC-022, TC-032, TC-096, TC-131,
  TC-135 (5) — из них TC-032 назван в манифесте как «ожидаем ПЕРЕПРОВЕРКУ
  зелёным» (BUG-057, Fixed) — держать в уме контекст переписанной истории
  при интерпретации остальных четырёх.
- TC-016 (карантин AT-BUG-057) в состав regression-фильтра `(p0 or p1) and
  not live` не входит (только в smoke, см. `RUN-20260810-0145.md` — там
  зелёный).

## Падения и триаж (failure-analyst, 2026-08-10T03:50:00Z)

### Шаг 4 протокола: какая сборка с какой сравнивается (правка базы сверки)

`git -C app-under-test log --oneline 63f6aac..6f884d979` — 9 коммитов:

```
6f884d9 Keep each Library tab's scroll position when switching tabs (#28)
9d1e5f5 Name dev builds after their pipeline instead of a frozen version
2ecad9b Cut releases by tagging instead of a pipeline variable
2737a1c Add a release pipeline that versions the build from the pipeline
b00a88a Sign CI builds with the same debug key as local builds
6e43b14 Open library works in a background tab from the long-press sheet (#26)
94a124b Align PROJECT.md and DESIGN.md with actual UI labels and filtering model (#1)
f1fa703 Fix CI artifact path rejected by GitLab config validation
ff19726 Add GitLab CI pipeline publishing debug APK artifacts for QA
```

Отсюда — ключевой вывод триажа, меняющий чтение ВСЕЙ таблицы «сверка с
baseline» выше: **правильная база сверки для этой сборки — не
`RUN-20260805-0437`, а `RUN-20260804-1624`.** Текущий `6f884d979` растёт из
`63f6aac` — того же коммита, что был `source_commit` сборки прогона
`RUN-20260804-1624` (1.10 (11), `6455af0c`). Ветка, на которой стояли
`77d65bc` (фикс BUG-014, панельный путь) и `bfc8f41` (переименование
заголовка диалога лимита вкладок), после force-push'а НЕ является предком
текущей: этих коммитов в истории физически нет (`git merge-base
--is-ancestor bfc8f41a 6f884d979` → не предок). Значит `RUN-20260805-0437`
описывает ПАРАЛЛЕЛЬНУЮ, ныне осиротевшую ветку, и «регрессия относительно
неё» — не регрессия, а возврат к состоянию общего предка.

Сверка с ПРАВИЛЬНОЙ базой `RUN-20260804-1624` (`runs/RUN-20260804-1624.md:59-99`):
TC-085 failed, TC-086 failed, TC-114 **failed**, TC-115 failed, TC-129 failed,
TC-130 failed, TC-139 failed — **все 7 сегодняшних красных были красными и
там, ни одного нового красного нет**. «Новое красное TC-114» из раздела выше
— артефакт сравнения с осиротевшей веткой.

### Таблица вердиктов

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| TC-085 `test_rename_filter_profile_keeps_query_string` | `TimeoutException: не кликабелен ('xpath', '(//*[@text="My saved search"]/following::*[@content-desc="Renam3"])[1]')` | **TEST_BUG** (дедуп) | долг открыт, нового не завожу | `bugs/AT-BUG-053.md` (`status: Open`); причина в тесте: `framework/screens/settings_screen.py:269` |
| TC-086 `test_rename_filter_profile_to_duplicate_name` | то же, якорь «Profile B» | **TEST_BUG** (дедуп) | тот же долг (один локатор на оба кейса) | `bugs/AT-BUG-053.md` |
| TC-114 `test_edit_tag_on_already_saved_work_via_panel_does_not_redownload` | `AssertionError: download-иконка не появилась у «A Loved Test Work»` — правка тега у уже сохранённой работы через ПАНЕЛЬ work-страницы повторно запустила авто-скачивание | **APP_BUG** (ожидаемый красный замок, НЕ новый) | нового тикета не требуется — `red_lock: "BUG-014"` в `test-cases/downloads/TC-114.md:*`; баг `Open` | `bugs/BUG-014.md` (`status: Open`, `test_cases: ["TC-114","TC-115"]`); код: `BrowserViewModel.kt:767` |
| TC-115 `test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload` | то же сообщение, путь листингового bottom-sheet | **APP_BUG** (ожидаемый красный замок) | то же — `red_lock: "BUG-014"` | `bugs/BUG-014.md`; код: `BrowserViewModel.kt:873` |
| TC-129 `test_infinite_scroll_off_keeps_native_pagination` | `TimeoutException: листинговая replay-страница не загрузилась (нет блёрбов работ)` | **TEST_BUG** (дедуп) | долг открыт | `bugs/AT-BUG-054.md` (`status: Open`); фикстура `framework/data/recordings/listing_paginated.mitm` |
| TC-130 `test_infinite_scroll_on_loads_next_page_in_background` | идентичное сообщение, тот же шаг | **TEST_BUG** (дедуп) | тот же долг (одна испорченная фикстура на оба кейса) | `bugs/AT-BUG-054.md` |
| TC-139 `test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos` | `AssertionError: data-kudo-clicked неожиданно = 1, ожидали стабильно 0 весь бюджет 3.0с` | **APP_BUG** (ожидаемый красный замок) | нового тикета не требуется — `red_lock: "BUG-015"` (`status: Open`, `known_issue: true`) | `bugs/BUG-015.md`; код: `BrowserViewModel.kt:867` и `:1064` |

Итого: 3 `APP_BUG` (все три — уже заведённые открытые баги под `red_lock`,
новых нет), 4 `TEST_BUG` (все дедупы в открытые долги). `APP_CHANGED`,
`SITE_CHANGED`, `ENV_ISSUE`, `FLAKY` не выставлены — обоснование в конце
раздела. **Новых `bugs/*.md` этим триажем не заводится**: каждое из 7 падений
покрыто существующим открытым артефактом.

### Пакеты доказательств (C2, `schemas/evidence.yaml`)

**APP_BUG — TC-114, TC-115 (BUG-014).**

- `build_hash`: `1.10 (versionCode 11)`, `source_commit 6f884d979a5c…`,
  `apk_sha256 034c0df5b348577175b1086d8a93606e4ed6a832d012a01030555341a93c283e`
  (`state/app-under-test.yaml:5,11`).
- `test_case`: TC-114 (`test-cases/downloads/TC-114.md`, `status: Automated`,
  `automation_status: active`, `red_lock: "BUG-014"`, `red_probe:
  2026-07-29T19:19:08Z`), TC-115 (то же, `red_probe: 2026-07-29T10:07:53Z`).
- `steps` (из шагов allure-результатов, дословно):
  TC-114 — открыта страница работы `900000001` → в панели рейтинга раскрыт
  раздел тегов и добавлен личный тег `re-save-probe` → чип присутствует среди
  выбранных → открыт `Library` → во вкладке `SAVE` присутствует «A Loved Test
  Work» → **[failed]** карточка показывает download-иконку;
  TC-115 — в открытом bottom-sheet листинга раскрыто поле комментария и
  сохранён текст `re-save-note` → превью свёрнуто → sheet закрыт тапом по
  затемнению → `Library` → вкладка `SAVE` → **[failed]** карточка показывает
  download-иконку. Replay-фикстуры: `work_with_download.mitm` (TC-114),
  `listing_basic.mitm` (TC-115).
- `screenshot`: `runs/RUN-20260810-0146/allure/06ce661a-9b98-48b3-abf7-c9df89088b03-attachment.png`
  (TC-114, 79 491 Б); `…/ec59b8a5-55fd-4c86-a577-c2c250ae9e7e-attachment.png`
  (TC-115, 77 121 Б).
- `logcat`: `…/d3fad240-994e-4707-a2d4-21694d38c3bd-attachment.txt` (TC-114,
  151 534 Б); `…/b1de2094-8885-4937-8c9a-62cab4735123-attachment.txt` (TC-115,
  161 909 Б).
- `page_source`: `…/eb4ab771-77ab-474b-b07f-91e7597779e9-attachment.xml`
  (TC-114, 46 732 Б); `…/398f860c-00ac-4a2a-8985-0f769af8e070-attachment.xml`
  (TC-115, 47 994 Б). Полные result.json:
  `…/56393b4f-c9de-4a21-bcdc-cd726d3613e6-result.json` (TC-114),
  `…/7c20b97c-6601-4164-b829-4cfab6009c91-result.json` (TC-115).
- `expected_actual`: ожидалось — правка ТЕГА/ЗАМЕТКИ у работы, которая уже
  имеет рейтинг SAVE и уже скачана, НЕ перезапускает скачивание, карточка в
  Library остаётся с open-иконкой; фактически — файл скачан повторно, карточка
  показала download-иконку (тест ловит именно это).
  Причина установлена ПО ИСХОДНИКУ текущей сборки (сильнее скриншота): в
  `app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt`
  ВСЕ ТРИ места вызова предиката авто-скачивания несут безусловное условие
  «рейтинг равен SAVE», без какой-либо проверки ПЕРЕХОДА рейтинга:
  строка `767` (`savePanelRating`, путь панели work-страницы для работы, уже
  существующей в Room — путь TC-114), строка `873` (`applyRating`, путь
  листингового overlay — путь TC-115), строка `1068` (`onRateWorkRequested`,
  bridge-путь первичного сохранения) — все три дословно:

  ```kotlin
  if (rating == Rating.SAVE && autoDownloadSaved) {
      downloadWork(workId)
  }
  ```

  Любое повторное сохранение рейтинг-записи (а правка тега/заметки идёт через
  тот же upsert) заново удовлетворяет предикат → ретроактивное скачивание.
  Это ровно дефект, описанный в `bugs/BUG-014.md`.

**APP_BUG — TC-139 (BUG-015).** `build_hash` — тот же. `test_case`: TC-139
(`test-cases/rating/TC-139.md`, `status: Approved`, `red_lock: "BUG-015"`).
`steps`: в bottom-sheet листинга раскрыт раздел тегов и добавлен личный тег
`re-save-kudos-probe` → чип присутствует → sheet закрыт тапом по затемнению →
`Browse` → закрыта вкладка на позиции 0 → **[failed]** узел `#kudo_submit`
держит `data-kudo-clicked="0"` стабильно 3.0с. `screenshot`:
`…/efbfc613-441f-434b-9b83-0ed7c1255d46-attachment.png` (459 811 Б);
`logcat`: `…/3a2ff29a-5d6b-424c-b697-02cc70ae71bf-attachment.txt` (106 544 Б);
`page_source`: `…/aa1c37e0-d7f2-4021-9cfb-2397b9b22f9a-attachment.xml`
(34 293 Б); result.json — `…/4ab049cd-3cff-4e6a-8453-f298b2b49da1-result.json`.
`expected_actual`: ожидалось — `data-kudo-clicked` остаётся `0` (kudos не
переклкикивается при правке тега уже «залайканной» работы); фактически `= 1`.
Код текущей сборки, `BrowserViewModel.kt:867` и `:1064`, — та же безусловная
форма:

```kotlin
if (rating == Rating.LIKE || rating == Rating.SAVE) { … kudo_submit … .click(); }
```

**TEST_BUG — TC-085, TC-086 (AT-BUG-053).**
`failing_test`: `framework/tests/test_filter_profiles.py::test_rename_filter_profile_keeps_query_string`
(allure `as_id: TC-085`, `…/3625ae83-d5e1-4264-9096-2eda27404d80-result.json`,
`broken`) и `::test_rename_filter_profile_to_duplicate_name` (`as_id: TC-086`,
`…/0c2f8fb4-aeed-4d32-baa2-d83354662d27-result.json`). Оба сломались на шаге
`When в Settings профиль «…» переименован в «…»`, предыдущие шаги зелёные.
`root_cause` — В ТЕСТЕ, не в приложении, сверено обеими сторонами:
`framework/screens/settings_screen.py:269` строит
`(//*[@text="{name}"]/following::*[@content-desc="Renam3"])[1]` — опечатка
`Renam3`; приложение рисует корректный
`app-under-test/…/ui/settings/SettingsScreen.kt:852  contentDescription = "Rename"`.
Локатор — единственный `Renam3` во всём `framework/` (позитивный контроль той
же формой grep: `autoDownloadSaved` в `--include=*.kt` даёт 11 попаданий, т.е.
инструмент/фильтр работают). `fix_or_debt`: долг уже заведён и открыт —
`bugs/AT-BUG-053.md` (`type: test_debt`, `debt_kind: weak_locator`,
`status: Open`, `test_cases: ["TC-085","TC-086"]`); фикс за test-maintainer.

**TEST_BUG — TC-129, TC-130 (AT-BUG-054).**
`failing_test`: `framework/tests/test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination`
(`as_id: TC-129`, `…/35b2354e-745c-4a33-8126-f0085d8d7429-result.json`) и
`::test_infinite_scroll_on_loads_next_page_in_background` (`as_id: TC-130`,
`…/54f2968b-2b39-4f7c-b6a8-8b74f9b0ab74-result.json`); оба `broken` на шаге
`When открыта листинговая страница (replay-фикстура) …listing_paginated`,
сообщение идентично: `листинговая replay-страница не загрузилась (нет блёрбов
работ)`. Обе настройки (`Infinite scroll` OFF у TC-129, ON у TC-130) успели
примениться зелёными шагами — расходятся только они, падает общий шаг.
`root_cause` — В ФИКСТУРЕ, не в приложении: `grep -c "work blurp"
framework/data/recordings/listing_paginated.mitm` → **5**,
`grep -c "work blurb"` того же файла → **0**; позитивный контроль тем же
вызовом на здоровой фикстуре `listing_basic.mitm` → **10** попаданий
`work blurb` (т.е. пустой результат по `blurb` в `listing_paginated.mitm` —
факт, а не промах вызова). Приложение и тест ищут `blurb`, запись отдаёт
`blurp` — страница не опознаётся как листинговая. `fix_or_debt`: долг заведён
и открыт — `bugs/AT-BUG-054.md` (`type: test_debt`,
`debt_kind: missing_fixture`, `status: Open`, `test_cases: ["TC-129","TC-130"]`).

### Триаж-заметки по флипнувшим в ЗЕЛЁНОЕ (не вердикты падений)

Пять кейсов были красными в `RUN-20260805-0437` и зелёные здесь. Ни один флип
не означает «починено» — все пять объясняются либо сменой ветки, либо природой
уже известного долга.

- **TC-022 `test_max_tabs_limit_blocks_11th_tab` и TC-131
  `test_deep_link_at_tab_limit_shows_dialog_and_drops_url` — флип из-за
  ОТКАТА текста приложения вместе с историей, тест не менялся.**
  В `RUN-20260805-0437` вердикт был `APP_CHANGED` по коммиту `bfc8f41`
  «Clarify tab-limit dialog title» (`"Tab limit reached"` →
  `"Maximum tab count reached"`), действие — «test-maintainer: обновить
  `TAB_LIMIT_TITLE`». Сейчас: приложение —
  `app-under-test/…/MainActivity.kt:624` → `"Tab limit reached"`; фреймворк —
  `framework/screens/browser_screen.py:337` → `TAB_LIMIT_TITLE = "Tab limit
  reached"`. Совпали снова. То есть **тест не был обновлён** (действие
  APP_CHANGED осталось невыполненным), а приложение вернулось к прежнему
  тексту вместе с force-push'ем. Практический вывод для test-maintainer /
  test-strategist: **обновлять `TAB_LIMIT_TITLE` под «Maximum tab count
  reached» сейчас НЕЛЬЗЯ** — это перекрасит оба кейса в красное на текущей
  ветке; вердикт `APP_CHANGED` от 2026-08-05 относится к осиротевшей ветке и
  подлежит пересмотру полным Lead, а не автоматическому исполнению.
- **TC-032 `test_auto_download_triggers_on_loved_rating` — зелёный законно,
  но это НЕ верификация фикса BUG-057.** BUG-057 описывал регрессию,
  внесённую коммитом `77d65bc`: транзишен-чек читал `previousRating` ПОСЛЕ
  апсерта, из-за чего условие `previousRating != SAVE` никогда не выполнялось.
  В ТЕКУЩЕЙ сборке токена `previousRating` нет вообще: `grep -rn
  "previousRating" --include=*.kt app-under-test/` → пусто (позитивный
  контроль той же формой: `autoDownloadSaved` → 11 попаданий), а все три
  места вызова несут дофиксовую безусловную форму `if (rating == Rating.SAVE
  && autoDownloadSaved)` (строки 767 / 873 / 1068). Значит: ветка НИКОГДА не
  содержала патча `77d65bc`, поэтому и регрессии в ней нет — это
  **not-repro-by-construction**, а не подтверждение фикса. Дополнительная
  внутренняя проверка «зелёный тест достаточно чувствителен» проходит: на
  этой же кодовой базе TC-114/TC-115 краснеют ровно на предикате
  авто-скачивания, т.е. оракул скачивания живой и различающий.
  **Расхождение для Lead/fix-verifier (не правлю, `bugs/` вне owns):**
  `bugs/BUG-057.md` несёт `status: Fixed`, `fixed_in: "1.10 (versionCode 11),
  commit fdcbad9 (revert патча A)"`, `awaiting: qa` — а коммита `fdcbad9` в
  истории приложения больше нет. Формально «фикс» существует только в
  осиротевшей ветке; верификация по текущей сборке доказывает лишь отсутствие
  СИМПТОМА. Класс BUG-057 (регрессия при попытке ввести транзишен-чек)
  вернётся, как только BUG-014 начнут чинить заново — это вход для
  test-strategist, а не «закрыто».
- **TC-096 `test_cold_start_within_relative_budget` — не воспроизвёлся,
  долг остаётся.** `bugs/AT-BUG-058.md` (`type: test_debt`,
  `debt_kind: broken_environment`, `status: Open`): замер холодного старта
  идёт ПОД активной Appium-сессией, `am start -W` не рапортует завершение →
  `TimeoutError 60s`. Долг по своей природе вероятностный (гонка сессии и
  `force-stop`/`pm clear`), и его собственная карточка фиксирует, что без
  сессии та же последовательность даёт 6/6 успешных. Зелёный прогон — просто
  выигранная гонка. Ни `fixed_in`, ни статус долга менять нельзя;
  `last_seen_in` остаётся `RUN-20260805-0437`.
- **TC-135 `test_cold_start_deep_link_reuses_single_home_tab` — не
  воспроизвёлся, кейс остаётся в карантине.**
  `test-cases/tabs/TC-135.md` несёт `automation_status: quarantined`,
  `quarantine_since: 2026-08-04T22:20:45Z`, `quarantine_owner: test-maintainer`,
  долг `bugs/AT-BUG-055.md` (`status: Open`) — слепое чтение prefs через
  `run-as cat ao3_settings.xml`, «маркер не записан» и «файл не прочитан»
  неразличимы. Один зелёный прогон карантин не снимает: критерий выхода
  `quarantined → active` — 3 зелёных подряд И только рукой test-maintainer
  (`schemas/transitions.yaml`, машина `automation`). Я карантин не трогаю.
  Побочно: `totals.quarantined: 0` во frontmatter при зелёном
  `TC-135: passed`, который числится `quarantined`, — карантинный кейс попал
  в общий счёт `passed` (см. доклад собратьев ниже).

### Почему не другие вердикты (явно)

- **не `APP_CHANGED`** ни по одному падению: из 9 коммитов диапазона
  `63f6aac..6f884d979` шесть — CI/подпись/версионирование
  (`ff19726`, `f1fa703`, `b00a88a`, `2737a1c`, `2ecad9b`, `9d1e5f5`), один —
  только документация (`94a124b`, PROJECT.md/DESIGN.md), и два продуктовых
  (`6e43b14` — открытие работы библиотеки в фоновой вкладке из long-press
  sheet; `6f884d9` — сохранение скролл-позиции вкладок Library). Ни один не
  трогает ни авто-скачивание, ни kudos-мост, ни переименование
  фильтр-профилей, ни листинговую пагинацию. Намеренного изменения
  проверяемого поведения нет — значит вердикта `APP_CHANGED` нет.
- **не `SITE_CHANGED`**: прогон целиком в `AO3_MODE=replay`, живой AO3 не
  участвует; единственные «страничные» падения (TC-129/TC-130) объяснены
  испорченной ЛОКАЛЬНОЙ записью, а не изменением DOM на сайте.
- **не `ENV_ISSUE`**: среда сверена канонической формой в самом прогоне
  (`Get-Device` → `DEVICE: emulator-5554`, `:4723/status` → `STATUS 200`
  после обрыва фонового job'а), `AT-BUG-026`-токен не печатался
  (`recoveries 0/2` в дошедшем до `sessionfinish` сегменте 2), и ни одно из
  7 падений не несёт device/adb/Appium-сигнатуры — все семь падают на
  продуктовых ассертах или локаторах. Обрыв фонового job'а харнесса — дефект
  оболочки прогона, а не причина какого-либо из 7 падений (все 7 доведены до
  определённого исхода и подтверждены allure-результатами).
- **не `FLAKY`** ни по одному из семи: каждое падение детерминировано и
  объяснено конкретной строкой кода/фикстуры, у всех семи ровно та же
  сигнатура, что в `RUN-20260804-1624` на общей базе `63f6aac`; карантина
  никому не ставлю, `automation_status` кейсов не меняю.

### Что остаётся другим ролям (не делаю сам, вне owns)

1. `bugs/BUG-014.md` — `last_seen_in: "1.11 (versionCode 12)"` устарел:
   фактически последний раз виден в `1.10 (versionCode 11)`, `6f884d97`
   (этот прогон); `runs: []` — пуст. То же для `bugs/BUG-015.md`
   (`last_seen_in: "1.11 (versionCode 12), bfc8f41a21…"` ссылается на
   коммит вне истории). Обновление — bug-reporter/Lead.
2. `bugs/AT-BUG-053.md`, `bugs/AT-BUG-054.md` — `last_seen_in:
   "RUN-20260804-1624 (2026-08-04)"`, `runs: ["RUN-20260804-1624"]`: обоих
   надо дополнить `RUN-20260805-0437` и `RUN-20260810-0146`.
3. `bugs/BUG-057.md` — фактическая нестыковка `fixed_in`/`awaiting: qa` с
   переписанной историей (разбор выше). Вход fix-verifier/Lead, не мой.
4. TC-085/086/129/130 остаются `automation_status: active` при вердикте
   `TEST_BUG`. Переход `active → needs_maintenance` формально доступен и
   failure-analyst (`schemas/transitions.yaml`, машина `automation`), но
   прошлые два триажа его не делали, и массовая смена статуса 4 кейсов —
   решение о политике сигнала, а не разбор падения: ставлю вопрос Lead,
   сам не двигаю.

## Дефекты-собратья (D-0043) — доклад

0. **Доклад failure-analyst (называю, scope не расширяю):**
   - (а) **База сверки прогона выбирается по «прошлому triaged», а не по
     предку сборки.** Оба сегодняшних отчёта и `state/app-under-test.yaml`
     сравнивают результаты с `RUN-20260805-0437` — прогоном осиротевшей ветки,
     что и породило фантом «новое красное TC-114». Класс шире одного прогона:
     процедура сверки нигде не требует проверить, что baseline-сборка —
     ПРЕДОК текущей (`git merge-base --is-ancestor`). Кандидаты на правило:
     `.claude/agents/test-runner.md` (раздел сверки с baseline),
     `.claude/agents/failure-analyst.md` (шаг 4), `scripts/impact_select.py`
     (тот же диапазон `63f6aac3..6f884d979` он резолвил «по умолчанию»).
   - (б) **Вердикты, вынесенные по осиротевшей ветке, продолжают жить как
     действующие указания.** `APP_CHANGED` по TC-022/TC-131 из
     `RUN-20260805-0437` предписывает правку `TAB_LIMIT_TITLE`, которая
     СЕГОДНЯ сломала бы два зелёных кейса; `BUG-057` числится `Fixed` по
     несуществующему коммиту. Класс: у артефактов фабрики нет ревалидации при
     смене линии сборки. Уровень размещения правила — `docs/06` (жизненный
     цикл вердикта/бага), не отдельный файл бага.
   - (в) **Карантинный кейс посчитан как обычный `passed`.** Frontmatter
     несёт `totals.quarantined: 0`, при этом `TC-135: passed` — кейс с
     `automation_status: quarantined`. Счётчик карантина в отчёте прогона
     не связан с полем кейса; тот же класс затронет любой карантинный кейс,
     попавший в набор. Место: сборка `totals` в `framework/…/reporting.py` +
     шаблон `docs/templates/run-report.md`.

1. **Фоновый job снова убит харнессом** — ЧЕТВЁРТЫЙ подряд прецедент того же
   класса (`RUN-20260803-2012` → `RUN-20260804-1624` → `RUN-20260805-0437` →
   этот), теперь на ~59 минутах, несмотря на корректное синхронное
   ожидание через повторные `Wait-Process`-раунды внутри одного хода (не
   нотификацию). Список прецедентов растёт на четвёртый временной отрезок
   (~45-60 мин каждый раз) — для Lead: лимит систематический и не связан со
   способом ожидания координатора.
2. **TC-114 — новое красное, не было в прошлом triaged-baseline** — сосед
   TC-115 в том же файле (`test_downloads.py`), оба из class «BUG-014-
   окрестностей» (та же группа, что триаж `RUN-20260805-0437` уже разбирал
   для TC-032/TC-115: три места вызова предиката авто-скачивания, из которых
   `applyRating`/панельный путь был «не тронут» фиксом BUG-014). Не
   расследую — за failure-analyst; учесть контекст переписанной истории
   сборки из манифеста.
3. **TC-085/086 (filter_profiles) и TC-129/130 (infinite_scroll) — тот же
   расклад**, что уже дважды зафиксирован (`RUN-20260804-1624`,
   `RUN-20260805-0437`), вердикты там были TEST_BUG (`AT-BUG-053`,
   `AT-BUG-054`) — если долги ещё Open, это, возможно, ТЕ ЖЕ падения, не
   новые; дедуп — за failure-analyst.
4. **Allure-артефакты сегмента 1 сохранены ДО обрыва** (этот раз, в отличие
   от трёх прошлых прецедентов) — я использовал отдельный `--alluredir` для
   сегмента 2 (`allure-results-seg2`, не default `allure-results`), поэтому
   `--clean-alluredir` сегмента 2 НЕ стёр результаты сегмента 1; оба
   смёржены в `runs/RUN-20260810-0146/allure/` (974 файла). Предлагаю этот
   приём как обходной путь для механизма архивации, который прошлые три
   прогона просили внедрить (ещё не сделано).

## Условия закрытия прогона (Closed)
- [x] Каждое из 7 падений имеет вердикт и связанное действие — 3 `APP_BUG` (`BUG-014` ×2, `BUG-015`), 4 `TEST_BUG` (`AT-BUG-053` ×2, `AT-BUG-054` ×2); все дедупы в открытые артефакты, новых баг-файлов не заведено
- [ ] `state/coverage-map.md` не перегенерирована (шаг снимка — за qa-loop)
- [x] TC-114 — **НЕ новое красное**: на правильной базе сверки (`RUN-20260804-1624`, общий предок `63f6aac`) он был красным; вердикт `APP_BUG`, дедуп `bugs/BUG-014.md`, отдельный баг не нужен
- [ ] Актуализация `last_seen_in`/`runs` у `BUG-014`/`BUG-015`/`AT-BUG-053`/`AT-BUG-054` и разбор нестыковки `BUG-057` — за bug-reporter/Lead (см. «Что остаётся другим ролям»)
