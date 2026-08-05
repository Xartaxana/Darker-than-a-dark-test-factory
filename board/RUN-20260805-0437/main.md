---
key: "RUN-20260805-0437"
project: "AO3"
issueType: "run"
status: "run-triaged"
priority: "p2"
summary: "RUN-20260805-0437"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
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

# RUN-20260805-0437

_Спроецировано из `runs/RUN-20260805-0437.md` (источник правды).
Статус в нашей машине: **Triaged**._

# RUN-20260805-0437 — regression (replay) на 1.11 (12)

## Контекст запуска

Триггер: продолжение того же дневного дispатча, что `RUN-20260805-0432`
(smoke) — E1, новая сборка 1.11 (12). Команда координатора дала прямой
полный marker-фильтр (`selection.mode: full`, без impact-препроверки —
тот же канон, что RUN-20260804-1624/RUN-20260803-2012).

**Команда**: `pytest tests -m "(p0 or p1) and not live"` (`AO3_MODE=replay`),
165 selected / 314 collected (149 deselected). Окружение: эмулятор
`ao3_test_api34` (`emulator-5554`), Appium `:4723` (перезапущен после smoke,
health-checked), APK 1.11 (12) уже установлен. `Get-Device` сверялся перед
каждым сегментом ниже.

Прогон разбит на **4 сегмента** — не по плану, а вынужденно двумя разными
классами обрыва среды (см. «Находки»). Итоговая таблица ниже — РЕКОНСТРУКЦИЯ
по 165 уникальным тестам, сведённая из дословных хвостов всех сегментов
(методика ниже).

## Находка 1: сегмент 1 — Appium упал посреди прогона (тот же класс, что smoke)

Первый полный прогон (165 selected) дошёл до `sessionfinish` за 3420.27s, но
начиная примерно с 22% дал длинную серию `urllib3.exceptions.
NewConnectionError … port=4723 … [WinError 10061]` — **71 ERROR** вперемешку
с 5 реальными `FAILED` и 89 `PASSED`. Позитивная сверка сразу после:
`Get-Device` → `DEVICE: emulator-5554`; `:4723/status` → отказ соединения;
`node.exe` Appium — процесса нет. Тот же класс, что первая попытка smoke
(`RUN-20260805-0432`, «Находка»). Восстановление: `Stop-NodeProcesses` +
`Start-Appium` (health-checked) + `Get-Device`.

Дословный хвост сегмента 1 (сокращён):
```
tests\canary\test_ao3_selectors.py .........                             [  5%]
...
tests\test_downloads.py FF..                                             [ ~20%]
tests\test_filter_profiles.py FF...                                      [ ~23%]
tests\test_infinite_scroll.py FF                                         [ ~25%]
...
=== 5 failed, 89 passed, 149 deselected, 3 warnings, 71 errors in 3420.27s (0:57:00) ===
PYTEST_EXIT=1
```
71 ERROR — сплошь `NewConnectionError`/`TimeoutException` одной сигнатуры на
проваленном соединении к Appium, не индивидуальные падения приложения.

## Находка 2: сегмент 2 — фоновый job УБИТ ХАРНЕССОМ (рецидив, третий раз подряд)

Перезапустил Appium, запустил `pytest ... --lf` (76 = 5+71 из сегмента 1) для
пересверки errored-тестов. На ~50% (после `test_rating_listing.py`, начало
`test_reading_ux.py`) системное `task-notification` сообщило `status: killed`
— сам pytest НЕ дошёл до `sessionfinish` (нет итоговой строки/`PYTEST_EXIT`).
`Get-Device` и `:4723/status` сразу после — оба здоровы (`DEVICE:
emulator-5554`, `STATUS 200`): обрыв НЕ связан со средой приложения, это
лимит времени жизни самого фонового `run_in_background`-job'а (~45-50 мин).

**Это ровно дефект-собрат, уже дважды задокументированный** —
`runs/RUN-20260803-2012.md` (находка №1) и `runs/RUN-20260804-1624.md`
(находка, рецидив №1) — **сейчас рецидив №2 подряд**, тот же класс прогона
(`(p0 or p1) and not live`, ~165 тестов, многочасовой). Два прецедента уже
хватало, чтобы Lead счёл лимит систематическим (~60 мин) — этот, третий,
подтверждает то же самое на другом временном отрезке (~45-50 мин).

Частичный (нефинализированный) прогресс сегмента 2 использован ТОЛЬКО как
навигационная подсказка (какие файлы уже прошли), не как источник
результатов (без `sessionfinish` точные исходы неизвестны для отдельных
тестов внутри многострочных файлов) — переисполнены явно сегментом 3.

## Находка 3/4: сегменты 3 и 4 — довели прогон до конца явным списком файлов

Вместо повторного `--lf` (риск того же лимита на ~76 тестах) — явный список
ОСТАВШИХСЯ файлов (`test_reading_ux.py` … `test_visibility.py`, 39 тестов):
дошёл до `sessionfinish`, 3102.70s (51:43), `3 failed, 36 passed, 11
deselected`, `PYTEST_EXIT=1`. Осталась неоднозначность внутри
`test_performance.py`/`test_rating_listing.py` (дот-прогресс сегмента 2 не
называл, КАКОЙ из тестов упал) — добит отдельным verbose-прогоном этих двух
файлов (19 тестов, `-v`): дошёл до `sessionfinish`, 1433.68s (23:54), `2
failed, 17 passed`, `PYTEST_EXIT=1`, среда стабильна весь прогон.

Дословный хвост финального (verbose disambiguation) сегмента:
```
tests/test_performance.py::test_cold_start_within_relative_budget FAILED [  5%]
tests/test_performance.py::test_webview_first_load_within_relative_budget[ao3_home_smoke.mitm] PASSED [ 10%]
tests/test_performance.py::test_memory_trend_recovers_after_closing_tabs[listing_basic.mitm] PASSED [ 15%]
...
=========================== short test summary info ===========================
FAILED tests/test_performance.py::test_cold_start_within_relative_budget - Ti...
FAILED tests/test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos[listing_basic.mitm]
=========== 2 failed, 17 passed, 6 deselected in 1433.68s (0:23:53) ===========
PYTEST_EXIT=1
```
`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` печаталась
во ВСЕХ трёх сегментах, дошедших до `sessionfinish` (1, 3, disambiguation);
токена `ENV_ISSUE` не было ни разу.

## Методика реконструкции 165/165

Итоговая таблица (`tc_results`, «Итог» ниже) собрана так: 89 passed + 5
failed сегмента 1 — напрямую (именованы в его `sessionfinish`); из 71
errored сегмента 1 — 60 переисполнены сегментом 3 (именованы) и 19
переисполнены disambiguation-сегментом (именованы, verbose); ИТОГО 89+5+60+19
= 165 (60+19=79 — на 8 больше формального «71 error», т.к. файловый список
сегмента 3 захватывал целиком файлы, где часть тестов уже была `passed` в
сегменте 1 напрямую — переисполнены повторно, результат идентичен, конфликтов
между сегментами НЕ обнаружено программной сверкой). Ни один узел не остался
без именованного исхода.

## Итог

165 уникальных тестов, **154 passed, 11 failed, 0 skipped**. Полный список
красных (имя теста → TC, без вердикта):

| Тест | TC | Файл |
|---|---|---|
| test_auto_download_triggers_on_loved_rating | TC-032 | test_downloads.py |
| test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload | TC-115 | test_downloads.py |
| test_rename_filter_profile_keeps_query_string | TC-085 | test_filter_profiles.py |
| test_rename_filter_profile_to_duplicate_name | TC-086 | test_filter_profiles.py |
| test_infinite_scroll_on_loads_next_page_in_background | TC-130 | test_infinite_scroll.py |
| test_infinite_scroll_off_keeps_native_pagination | TC-129 | test_infinite_scroll.py |
| test_cold_start_within_relative_budget | TC-096 | test_performance.py |
| test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos | TC-139 | test_rating_listing.py |
| test_max_tabs_limit_blocks_11th_tab | TC-022 | test_tabs.py |
| test_deep_link_at_tab_limit_shows_dialog_and_drops_url | TC-131 | test_tabs.py |
| test_cold_start_deep_link_reuses_single_home_tab | TC-135 | test_tabs.py |

## Сверка с ожиданиями диспатча

Диспатч называл ожидаемые красные: «tabs-тесты по заголовку диалога лимита»,
«downloads-тесты классов BUG-014/окрестностей», «известные замки TC-139 и
бэклог». Факт:
- **Совпало**: TC-022/TC-131 (оба буквально «Tab limit reached dialog» —
  `assert_tab_limit_dialog_shown`), TC-115 (downloads/BUG-014-класс,
  `red_lock` в `test-cases/downloads/TC-115.md` — намеренный замок), TC-139
  (docstring теста прямо ссылается на BUG-015/TC-139.md, ожидаемый замок).
- **НЕ названо в ожиданиях, но красное**: TC-032 (downloads, СОСЕДНИЙ тест
  того же файла, что TC-115, но другое имя/сценарий — не входил в
  перечисленный класс «BUG-014/окрестности» явно, хотя может быть тем же
  классом), TC-085/TC-086 (filter_profiles), TC-129/TC-130 (infinite_scroll),
  TC-096 (performance/cold_start), TC-135 (tabs, НЕ про диалог лимита — про
  cold-start deep-link reuse; докстрока теста САМА описывает известную
  историю флакующей синхронизации persist prefs, см. `test_tabs.py:657-687`).
- **Ожидалось, но теперь ЗЕЛЁНОЕ** (не красное в этом прогоне): TC-114
  (downloads, сосед TC-115 из той же пары BUG-014) — passed здесь.

Вердиктов (APP_BUG/TEST_BUG/FLAKY/новая регрессия сборки) не выношу — это
факт для failure-analyst; сравнение приведено, чтобы не потерять расхождение
с ожиданиями диспатча.

## Артефакты

Allure-результаты сохранились ТОЛЬКО для последнего (disambiguation)
сегмента — 19/165 файлов, заархивированы в `runs/RUN-20260805-0437/allure/`
ДО следующего прогона. Результаты сегментов 1 и 3 (146/165, включая все 9 из
11 падений) стёрты `--clean-alluredir` последующих вызовов `Invoke-Pytest` —
архивация вручную сделана не была (не успел между сегментами при
многочасовом прогоне). Тот же класс, что уже дважды описан в
`runs/RUN-20260804-1624.md`.

## Дефекты-собратья (D-0043) — доклад

1. **Фоновый job снова убит харнессом (см. Находка 2)** — ТРЕТИЙ подряд
   прецедент того же класса (`RUN-20260803-2012` → `RUN-20260804-1624` →
   этот), теперь на другом временном отрезке (~45-50 мин вместо ~60). Для
   Lead: список прецедентов растёт, лимит явно систематический, не разовый
   сбой одной сессии.
2. **Appium падает целиком посреди сессии (WinError 10061)** — см. «Находка
   1» здесь и «Находка» в `RUN-20260805-0432.md` (smoke, та же сборка/сессия,
   первая попытка). Наблюдалось ДВАЖДЫ за одну эту дневную сессию (smoke
   попытка 1, regression сегмент 1), НИ РАЗУ в остальных 5 успешных сегментах
   — механизм неясен, не диагностирую (не моя роль).
3. **Уничтожение allure-артефактов `--clean-alluredir`** — рецидив, третий
   случай подряд (см. п.2 «Дефекты-собратья» `RUN-20260805-0432.md`),
   ПОЛНОСТЬЮ повторяет предложение из `RUN-20260804-1624.md`: обязательная
   архивация как шаг закрытия прогона, до сих пор не внедрена механизмом.
4. **TC-032/TC-115 — соседние тесты одного файла (`test_downloads.py`), оба
   красные, оба из «BUG-014-окрестностей»** (диспатч явно предсказал ЭТОТ
   класс) — при этом TC-114 (третий тест той же пары/класса в прошлых
   прогонах) сейчас ЗЕЛЁНЫЙ. Возможная частичная починка BUG-014, возможен
   флейк — не расследовал, за failure-analyst.
5. **TC-085/TC-086 (filter_profiles) и TC-129/TC-130 (infinite_scroll) —
   идентичный расклад тому, что уже зафиксирован в `RUN-20260804-1624.md`
   («Дефекты-собратья» пп.2-3 там же)**: те же 4 TC были красными и в том
   прогоне (сборка 1.10/11), с вердиктами TEST_BUG (`AT-BUG-053`,
   `AT-BUG-054`). Если те долги ещё Open — это, возможно, ТЕ ЖЕ самые
   падения, не новые; сверка/дедуп — за failure-analyst.
6. **Сравнение с последним триаженным baseline** (`RUN-20260804-1624`,
   154/165 passed, сборка 1.10/11): этот прогон — тоже 154/165, но НЕ тот же
   набор красных. Общие: TC-085, TC-086, TC-129, TC-130, TC-115, TC-135,
   TC-139 (7). Новые здесь: TC-032, TC-096, TC-022, TC-131 (4). Зелёные
   здесь, но красные там: TC-043, TC-090, TC-114, TC-134 (4). Голый факт,
   вердикт (регрессия/улучшение/флейк) не выношу.

## Падения и триаж (failure-analyst, 2026-08-05T03:20:00Z)

Диапазон коммитов сборки (шаг 4 протокола, `git -C app-under-test log --oneline
63f6aac..bfc8f41`, прошлый triaged-baseline `RUN-20260804-1624` — 1.10 (11),
`source_commit 63f6aac3`):

- `77d65bc` «Fix BUG-014: trigger favorite auto-download only on rating transition
  (panel path); bump version to 1.11 (12)» — `BrowserViewModel.kt` (+ версия);
- `bfc8f41` «Clarify tab-limit dialog title» — `MainActivity.kt:619`, одна строка.

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| TC-022 `test_max_tabs_limit_blocks_11th_tab` | диалог лимита не найден: локатор ищет ТЕКСТ «Tab limit reached» (`browser_screen.py:337` `TAB_LIMIT_TITLE`, `by_text` — точное совпадение), приложение с 1.11 рисует «Maximum tab count reached» | **APP_CHANGED** | test-maintainer: обновить `TAB_LIMIT_TITLE` (+ негативные ассерты, см. собратья); test-strategist: зафиксировать намеренное изменение без тикета (docs/06 D9) | `bfc8f41` `MainActivity.kt:619`, `framework/screens/browser_screen.py:337` |
| TC-131 `test_deep_link_at_tab_limit_shows_dialog_and_drops_url` | то же: `assert_tab_limit_dialog_shown` падает на проверке ЗАГОЛОВКА раньше, чем сверяет дословный текст сообщения (сообщение коммитом не менялось) | **APP_CHANGED** | тот же (одна константа на оба кейса) | тот же коммит, `framework/steps/browser_steps.py:1929` |
| TC-032 `test_auto_download_triggers_on_loved_rating` | авто-скачивание НЕ запускается: `assert_open_icon_shown` не дожидается open-иконки (файл не скачан) | **APP_BUG** (новый, регрессия фикса BUG-014) | завести баг (bug-reporter): `BrowserViewModel.kt:1063` читает `previousRating` ПОСЛЕ `upsertWorkRating` — «прошлый» рейтинг всегда равен только что сохранённому, условие `previousRating != SAVE` никогда не истинно, авто-скачивание не срабатывает ВООБЩЕ на этом пути → **BUG-057** | `77d65bc`, `BrowserViewModel.kt:1058-1066`; `regression_of: BUG-014` |
| TC-115 `test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload` | `AssertionError: download-иконка не появилась у «A Loved Test Work»` (повторное скачивание случилось) | **APP_BUG** (ожидаемый красный замок) | нового тикета не требуется — `red_lock: BUG-014`. Факт для D1/fix-verifier: фикс `77d65bc` НЕ трогал третье место вызова предиката — `applyRating`, `BrowserViewModel.kt:866` (`if (rating == Rating.SAVE && autoDownloadSaved)`), ровно ту строку, на которую ссылается `requirements` TC-115 → замок остаётся красным законно | `bugs/BUG-014.md`, `red_lock` в `test-cases/downloads/TC-115.md`; артефакты прошлого репро — `runs/RUN-20260804-1624/allure/` |
| TC-139 `test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos` | `AssertionError: data-kudo-clicked неожиданно = 1, ожидали стабильно 0 весь бюджет 3.0с` | **APP_BUG** (ожидаемый красный замок) | нового тикета не требуется — `red_lock: BUG-015` (`status: Open`, `known_issue`) | `bugs/BUG-015.md`, артефакт: `runs/RUN-20260805-0437/allure/c57cb651-76bf-403a-8338-13db7a1d217a-result.json` |
| TC-085 `test_rename_filter_profile_keeps_query_string` | падение на шаге переименования профиля (локатор `content-desc="Renam3"`) | **TEST_BUG** (дедуп) | долг уже открыт, нового не завожу | `bugs/AT-BUG-053.md` (Open, `last_seen_in: RUN-20260804-1624` → обновить на этот прогон) |
| TC-086 `test_rename_filter_profile_to_duplicate_name` | то же, якорь «Profile B» | **TEST_BUG** (дедуп) | тот же долг | `bugs/AT-BUG-053.md` |
| TC-129 `test_infinite_scroll_off_keeps_native_pagination` | листинговая replay-страница не опознаётся (нет блёрбов) | **TEST_BUG** (дедуп) | долг уже открыт | `bugs/AT-BUG-054.md` (Open, `class="work blurp"` в `listing_paginated.mitm`) |
| TC-130 `test_infinite_scroll_on_loads_next_page_in_background` | то же | **TEST_BUG** (дедуп) | тот же долг | `bugs/AT-BUG-054.md` |
| TC-135 `test_cold_start_deep_link_reuses_single_home_tab` | падение на слепом чтении prefs (`run-as cat ao3_settings.xml`) | **FLAKY** (дедуп) | кейс УЖЕ в карантине с прошлого триажа, долг открыт — нового карантина/долга не требуется | `bugs/AT-BUG-055.md`, `test-cases/tabs/TC-135.md` (`automation_status: quarantined`) |
| TC-096 `test_cold_start_within_relative_budget` | `TimeoutError: adb … am start -W … не вернул за 60s (AT-BUG-009)` на ПЕРВОМ замере baseline; на скриншоте — системный splash, первый кадр не отрисован | **TEST_BUG** (новый) | заведён долг: тест держит Appium-сессию всё время замера; та же последовательность БЕЗ сессии — 6/6 успешных, ~6.0-6.3s | `bugs/AT-BUG-058.md`; артефакты: `runs/RUN-20260805-0437/allure/2176578a-…-result.json` + `runs/RUN-20260805-0437/allure/rerun-tc096-20260805T0252Z/` |

Итого: 2 `APP_CHANGED`, 3 `APP_BUG` (1 новый, 2 — известные замки), 5 `TEST_BUG`
(1 новый, 4 дедупа), 1 `FLAKY` (дедуп). `SITE_CHANGED` и `ENV_ISSUE` не выставлены
ни разу — обоснование в конце раздела.

### Пакеты доказательств (C2, `schemas/evidence.yaml`)

**APP_CHANGED (TC-022, TC-131).** `commit_range`: `63f6aac..bfc8f41` (два коммита,
перечислены выше; прошлая сборка — 1.10 (11), `6455af0c`, `source_commit
63f6aac3`, см. историю `state/app-under-test.yaml`). `changed_behavior` — дословно
`git -C app-under-test show bfc8f41`:

```diff
 app/src/main/java/com/example/ao3_wrapper/MainActivity.kt @@ -616,7 +616,7 @@
             title = {
                 Text(
-                    "Tab limit reached",
+                    "Maximum tab count reached",
```

Коммит НАМЕРЕННЫЙ и точечный: заголовок диалога переименован сознательно
(«Clarify tab-limit dialog title»), других изменений в нём нет — это не поломка
поведения, а другое поведение без тикета (docs/06 D9). `affected_tc`: TC-022,
TC-131 (красные здесь) + TC-137 (`test_library_card_open_at_tab_limit_shows_dialog_and_switches_screen`,
тот же локатор, в этот прогон не попал — не p0/p1) + все негативные проверки
(см. собратья). Оба кейса были ЗЕЛЁНЫМИ на 1.10 (11) в `RUN-20260804-1624` —
разделение «до/после сборки» чистое.

**APP_BUG (TC-032, новый).** `build_hash`: 1.11 (versionCode 12), `bfc8f41a`
(`apk_sha256 7e9230ad…`). `test_case`: TC-032. `steps`: Settings → включить
«Auto-download favorite works» → Browse → открыть страницу работы без рейтинга →
через панель `RatingMenu` поставить Loved (SAVE) → Library. `expected_actual`:
ожидалось — авто-скачивание стартует, карточка получает open-иконку
(`test-cases/downloads/TC-032.md`); фактически — иконка не появилась, файл не
скачан. Причина установлена ПО ИСХОДНИКУ (сильнее скриншота): в
`onRateWorkRequested` (путь панели работы для записи, которой ещё нет в Room:
`savePanelRating` → `pendingPanelSave` → bridge → `onRateWorkRequested`)
транзишен-чек читает рейтинг ПОСЛЕ апсерта —

```kotlin
repo.upsertWorkRating(WorkRating(… rating = rating …))   // :1031
…
val previousRating = repo.getWorkRating(workId)?.rating   // :1063 — уже НОВОЕ значение
if (previousRating != Rating.SAVE && rating == Rating.SAVE && autoDownloadSaved) { downloadWork(workId) }  // :1064
```

— тогда как в парном месте (`savePanelRating`, `existing` :742, апсерт :746,
предикат :760) фикс сделан ПРАВИЛЬНО
(`existing` прочитан ДО апсерта, что прямо декларирует комментарий коммита: «same
transition-only guard as savePanelRating (see above)»). Намерение коммита —
сохранить скачивание на переходе в Favorite, а не отключить его; следовательно
это ДЕФЕКТ фикса, а не намеренное изменение (не `APP_CHANGED`).
`regression_of: BUG-014`. **Пробел пакета:** `screenshot`/`logcat`/`page_source`
недоступны — артефакты сегмента 1 стёрты `--clean-alluredir` (см. «Артефакты»),
а изолированный перепрогон TC-032 диспатчем не разрешён (устройство
сериализовано под D1). Три недостающих id восполняет bug-reporter при репро
(`next_rules`).

**APP_BUG (TC-115, TC-139 — известные замки).** Дедуп-строка вместо полного
пакета: оба теста несут `red_lock` на открытые баги, чьи пакеты собраны при
заведении (`bugs/BUG-014.md`, `bugs/BUG-015.md`) и подтверждены в
`RUN-20260804-1624` (артефакты — `runs/RUN-20260804-1624/allure/`). Для TC-139
артефакт ЭТОГО прогона сохранён (см. таблицу), сигнатура идентична прошлой.

**TEST_BUG (TC-085/086, TC-129/130).** `failing_test` — имена в таблице;
`root_cause` — установлен и зафиксирован в прошлом триаже (локатор `Renam3`;
`class="work blurp"` в записи `listing_paginated.mitm`), от сборки не зависит,
на 1.11 воспроизвёлся идентично; `fix_or_debt` — `AT-BUG-053`/`AT-BUG-054`, оба
`status: Open`.

**TEST_BUG (TC-096, новый).** `failing_test`:
`tests/test_performance.py::test_cold_start_within_relative_budget`,
allure-артефакт прогона сохранён. `root_cause`: замер холодного старта
(`force-stop` + `pm clear` + `am start -W`) выполняется, ПОКА жива
Appium/UiAutomator2-сессия (фикстура `driver`, нужная тесту одной последней
строкой). Контроль без сессии на той же сборке и том же эмуляторе — 6/6 успешных
запусков (`TotalTime` 5797…6279 ms, `Displayed … +6s231ms` в logcat); под сессией
— 3/3 зависание >60s (прогон + 2 изолированных перепрогона, второй после
`Stop-NodeProcesses`+`Start-Appium`). Приложение и сборка опровергнуты этим
контролем и диффом (1.11 не трогает старт); код теста с прошлого зелёного
прогона по существу не менялся (единственный коммит по путям — `8e4ff25`,
добавляет `adb.screen_density()`). `fix_or_debt`: `bugs/AT-BUG-058.md`.

**FLAKY (TC-135, дедуп).** `rerun_history`: зелёный в `RUN-20260803-2012`,
красный в `RUN-20260804-1624` и здесь. `failure_signature`: сверить с прошлой не
удалось — артефакты сегмента 3 стёрты; дедуп сделан по тождеству кейса и уже
принятому вердикту. `quarantine_decision`: выполнен ПРОШЛЫМ триажем —
`test-cases/tabs/TC-135.md` уже `automation_status: quarantined` с
`quarantine_reason/since/owner`, долг `AT-BUG-055` открыт; повторный карантин не
требуется. (Наблюдение для qa-loop: карантинный кейс всё равно попал в выборку —
`totals.quarantined: 0` при красном TC-135; deselect карантина фильтром маркеров
не работает.)

### Почему НЕ выставлены SITE_CHANGED и ENV_ISSUE

- `SITE_CHANGED` — прогон целиком `replay` (`AO3_MODE=replay`), живой AO3 не
  участвовал; ни одно из 11 падений не про DOM-селекторы AO3. Падения
  TC-129/130 приходят от ЗАПИСИ (`listing_paginated.mitm` с `blurp`), а это
  дефект фикстуры, уже квалифицированный как TEST_BUG (`AT-BUG-054`).
- `ENV_ISSUE` — среда сверена канонически (CLAUDE.md, permission hygiene п.6):
  `. tasks.ps1; Get-Device` → `DEVICE: emulator-5554`; `:4723/status` → 200;
  `df /data` — 6% занято; `loadavg` 1.31/1.77/1.81; MemAvailable 1.18 ГБ;
  uptime 14:32. Два обрыва среды, описанные runner'ом (падение Appium в сегменте
  1 и убитый харнессом фоновый job в сегменте 2), НЕ дали ни одного из 11
  засчитанных падений: все 11 получены в сегментах, дошедших до `sessionfinish`,
  все errored-тесты переисполнены. Для TC-096, где `ENV_ISSUE` был главным
  кандидатом, перезапуск среды (свежий Appium) падение НЕ снял, а контрольный
  замер без сессии прошёл 6/6 — среда исключена измерением.

### Дефекты-собратья (D-0043) — доклад

1. **Класс «фикс BUG-014 не закрыт по всем местам вызова».** Предикат
   авто-скачивания имеет ТРИ места вызова
   (`git grep -n autoDownloadSaved` на `bfc8f41`): `savePanelRating:760` —
   исправлено верно; `onRateWorkRequested:1064` — исправлено НЕВЕРНО (чтение
   после апсерта → TC-032); `applyRating:866` — НЕ ТРОНУТО вовсе
   (`if (rating == Rating.SAVE && autoDownloadSaved)`), это ровно точка кода
   из `requirements` TC-115. Итог: 1 из 3 мест закрыт. Для bug-reporter/D1 —
   один класс, а не три случайных падения.
2. **Сиблинг того же класса в соседней фиче: BUG-015 (авто-kudos).** Тот же
   level-предикат без транзишен-проверки в тех же двух функциях
   (`onRateWorkRequested:1053-1056` — `if (rating == LIKE || rating == SAVE)`
   → клик kudos; зеркало в `applyRating`), коммитами 1.11 не тронут — TC-139
   красный законно. Чинить стоит одним классом с BUG-014, иначе тот же цикл
   повторится.
3. **Негативные ассерты диалога лимита стали тавтологически истинными.** После
   переименования заголовка `assert_tab_limit_dialog_not_shown`
   (`browser_steps.py:1945`) ищет исчезнувший текст и теперь ПРОХОДИТ всегда —
   ложно-зелёный в TC-022 (проверка «до достижения лимита», `test_tabs.py:53`),
   TC-137 (`test_tabs.py:772`) и `test_performance.py:165`. Правка одной
   константы `TAB_LIMIT_TITLE` чинит и позитив, и негатив, но КРАСНУЮ ПРОБУ
   после правки надо делать именно на негативных ассертах.
4. **TC-137 — четвёртый экземпляр того же APP_CHANGED**, не попавший в выборку
   (нет маркера p0/p1): упадёт при первом же прогоне, который его включит.
   Учесть в правке test-maintainer, чтобы не ловить второй раз.
5. **Уничтожение allure-артефактов `--clean-alluredir`** (п.3 доклада runner'а) —
   подтверждаю ПОСЛЕДСТВИЕ на триаже: 9 из 11 падений разобраны БЕЗ
   скриншота/logcat/page source; для нового APP_BUG (TC-032) пакет доказательств
   формально неполон по трём id и достраивается только репро bug-reporter'а.
   Третий рецидив подряд; архивация `framework/allure-results/` шагом закрытия
   прогона нужна механизмом, а не дисциплиной.
6. **Карантин не исключает кейс из прогона:** TC-135 (`quarantined` с
   2026-08-04) отработал и упал в общем регрессе, при `totals.quarantined: 0` —
   маркер карантина не влияет на выборку. Класс: поле кейса без исполнителя в
   коде отбора (тот же шов, что «red_lock не влияет на отчётность»).

## Условия закрытия прогона (Closed)
- [x] Каждое из 11 падений имеет вердикт и связанное действие
- [ ] `state/coverage-map.md` не перегенерирована (шаг снимка — за qa-loop)
- [ ] Новый `APP_BUG` (TC-032) ждёт заведения bug-reporter'ом (в `next_rules`)
