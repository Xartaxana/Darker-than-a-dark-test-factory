---
key: "RUN-20260804-1624"
project: "AO3"
issueType: "run"
status: "run-triaged"
priority: "p2"
summary: "RUN-20260804-1624"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T22:20:45Z"
updated: "2026-08-04T22:20:45Z"
archived: false
resolution: null
---

# RUN-20260804-1624

_Спроецировано из `runs/RUN-20260804-1624.md` (источник правды).
Статус в нашей машине: **Triaged**._

# RUN-20260804-1624 — regression (replay) на 1.10 (11)

## Контекст запуска

Триггер: прямая инструкция координатора — повторный «ночной плановый прогон»
репетиции тёмного дня, ЗАМЕНА `runs/RUN-20260804-1301.md` (тот прогон дал
95/165 passed + 1 failed + 69 ERROR одной сигнатурой `WinError 4551`, Smart App
Control блокировал spawn `mitmdump.exe`; причина устранена коммитом `253d3ff`
— spawn теперь через подписанный `python.exe`; живая replay-проба зелёная ДО
этого прогона). `RUN-20260804-1301.md` не трогался, остаётся как есть.

Окружение поднято заранее (не мной): эмулятор `ao3_test_api34` (`emulator-5554`,
GPU `swiftshader_indirect` дефолт — не менял), CA mitmproxy в сторе, APK v1.10
(versionCode 11), Appium на `:4723`. Сверено `Get-Device` → `DEVICE:
emulator-5554` дважды (до старта и после обоих сегментов прогона).

**Команда**: канон RUN-20260803-2012 — `pytest tests -m "(p0 or p1) and not
live" ` (`AO3_MODE=replay`), 165 selected / 313 collected (148 deselected).

## Находка: фоновый job снова убит харнессом на ~60-минутной отметке (рецидив)

Тот же класс, что зафиксирован в `runs/RUN-20260803-2012.md` («Находка»,
дефект-собрат №1): полный прогон запущен через `run_in_background`,
foreground `Wait-Process -Timeout 500` вызывался повторно (канон 07-19) —
6 раундов, ~60 минут. На последнем раунде системное `task-notification`
сообщило `status: killed`; сам pytest-процесс не дожил до `sessionfinish`
(вывод обрывается на 89%, `tests\test_tabs.py ..` без завершающей строки
файла/summary). `Get-Device` сразу после обрыва → `DEVICE: emulator-5554`
(эмулятор жив), Appium (`node.exe`) и `qemu-system-x86_64.exe` тоже живы —
обрыв НЕ связан со средой приложения, это лимит времени жизни фонового job'а
самого Bash-тула (~60 мин), теперь наблюдался дважды подряд на этом же классе
прогона (RUN-20260803-2012 и этот).

**Восстановление** (тот же метод, что в RUN-20260803-2012): `allure-results`
первого сегмента (150/165 json-результатов) забэкаплены в scratchpad ДО
перезапуска (`--clean-alluredir` иначе стёр бы их). Недостающие 15 тестов
(9 хвостовых `test_tabs.py` + весь `test_visibility.py`, 6 тестов) — сверены
явно через `--collect-only` (165 node id, порядок совпал с терминальным
выводом) и прогнаны отдельной командой с явным списком node id
(`Invoke-Pytest tests/test_tabs.py::<...> ... tests/test_visibility.py`,
без маркерного фильтра — коллекция дала ровно «collected 15 items», совпало
с ожиданием). Второй сегмент отработал штатно, дошёл до `sessionfinish`,
`PYTEST_EXIT=1` (2 failed, 13 passed, 543.16s). Результаты обоих сегментов
слиты в `framework/allure-results/` (150 + 15 = 165 уникальных, дублей нет —
разные UUID).

**Суммарная длительность**: первый сегмент ~59.7 мин (`bwy8da4vf.output`:
CreationTime 15:09:40 → LastWriteTime последнего allure-результата 16:09:19)
+ второй сегмент 9:03 (543.16s) ≈ 69 мин — укладывается в ожидаемые 60-70 мин.

**recoveries**: второй (завершившийся) сегмент напечатал терминальную строку
`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` — в
frontmatter перенесено `recoveries: "0/2"`. Первый (убитый) сегмент до
`sessionfinish` не дожил и такую строку не печатал вовсе — его recoveries
неизвестны (не «0», а не измерены), причина явно эта: обрыв процесса
харнессом, не приложением. Ни в одном из двух сегментов не было ENV_ISSUE-токена.

## Итог

165 уникальных тестов, **154 passed, 11 failed (broken+failed по Allure), 0
skipped**. Полный сравнительный дословный pytest-хвост второго сегмента (witness):

```
tests\test_tabs.py ......FF.                                             [ 60%]
tests\test_visibility.py ......                                          [100%]
...
FAILED tests/test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged[tab_markers.mitm]
FAILED tests/test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab[tab_markers.mitm]
================== 2 failed, 13 passed in 543.16s (0:09:03) ===================
PYTEST_EXIT=1
```

Первый сегмент (убит харнессом, без итоговой строки) дошёл дословно до:

```
tests\test_downloads.py ......FF.                                        [ 22%]
tests\test_filter_profiles.py FF...                                      [ 25%]
tests\test_infinite_scroll.py FF                                         [ 26%]
...
tests\test_rating_listing.py .....F....F..F..                            [ 55%]
...
tests\test_tabs.py ..
```
(обрыв здесь, без PYTEST_EXIT).

## Падения — факт + артефакты (без вердиктов, триаж — failure-analyst)

| Тест (TC) | Allure-статус | Сообщение (кратко) | Известные ссылки |
|---|---|---|---|
| test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs (TC-043) | broken | `WebDriverException: A new session could not be created ... no such execution context: loader has changed while re...` | `bugs/AT-BUG-047.md` (Open, test_debt на TC-043, найден в RUN-20260803-2012) — **сигнатура В ЭТОМ прогоне другая**, чем зафиксирована в AT-BUG-047 (там `cannot determine loading status from no such window`); дедуп/новизна — за failure-analyst |
| test_filter_profiles.py::test_rename_filter_profile_keeps_query_string (TC-085) | broken | `TimeoutException`: не найден `xpath ('My saved search' → 'Rename3')` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_filter_profiles.py::test_rename_filter_profile_to_duplicate_name (TC-086) | broken | `TimeoutException`: не найден `xpath ('Profile B' → 'Rename3')` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_rating_listing.py::test_add_freeform_tag_persists (TC-090) | broken | `TimeoutException`: не дождался DOM-элемента `li#work_900000002.work.blurb [data-ao3-rate-btn]` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_downloads.py::test_edit_tag_on_already_saved_work_via_panel_does_not_redownload (TC-114) | failed | `AssertionError: download-иконка не появилась у «A Loved Test Work»` | `red_lock: "BUG-014"` в `test-cases/downloads/TC-114.md` (намеренный замок открытого бага, тот же класс, что в RUN-20260803-2012) |
| test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload (TC-115) | failed | то же сообщение, второе место вызова | `red_lock: "BUG-014"` в `test-cases/downloads/TC-115.md` |
| test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination (TC-129) | broken | `TimeoutException`: ожидание replay-запроса не поймано (не долистали список) | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_infinite_scroll.py::test_infinite_scroll_on_loads_next_page_in_background (TC-130) | broken | `TimeoutException`: **идентичное** сообщение TC-129 (тот же шаг ожидания replay-запроса) | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged (TC-134) | failed | `AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab (TC-135) | broken | `TimeoutError`: маркер `.../works?ao3_tab_marker=1` не появился в `ao3_settings.xml` за 20с | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos (TC-139) | failed | `AssertionError: data-kudo-clicked неожиданно = 1, ожидали стабильно 0 через 3.0с` | `red_lock: "BUG-015"` в `test-cases/rating/TC-139.md` (намеренный замок открытого бага) |

Артефакты (скриншоты/logcat/page_source) — стандартно приложены фреймворком к
каждому allure-результату в `framework/allure-results/`.

## Падения и триаж (failure-analyst, 2026-08-04T22:20:45Z)

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| TC-043 `test_comment_only_visible_on_listing_and_absent_from_rating_tabs` | `WebDriverException: A new session could not be created … no such execution context: loader has changed while resolving nodes` на `switch_to.context(WEBVIEW)` в первом же `open_listing` | **TEST_BUG** | дедуп в открытый долг (нового тикета не завожу): тот же тест, тот же choke point `contexts.in_webview`, вариант сигнатуры | `bugs/AT-BUG-047.md` |
| TC-085 `test_rename_filter_profile_keeps_query_string` | `TimeoutException: не кликабелен: xpath … @content-desc="Renam3"` | **TEST_BUG** | заведён долг: локатор ищет `Renam3`, приложение рисует `Rename` | `bugs/AT-BUG-053.md` |
| TC-086 `test_rename_filter_profile_to_duplicate_name` | то же, якорь «Profile B» | **TEST_BUG** | тот же долг (один экземпляр класса, одна правка) | `bugs/AT-BUG-053.md` |
| TC-090 `test_add_freeform_tag_persists` | `TimeoutException: не найден DOM-элемент: li#work_900000002.work.blurb [data-ao3-rate-btn]` | **APP_BUG** | завести баг (bug-reporter): bridge приложения падает на `document.head.appendChild` ПОСЛЕ того, как выставил свой guard — Rate-кнопки не инжектируются вовсе | `bugs/BUG-056.md` |
| TC-114 `test_edit_tag_on_already_saved_work_via_panel_does_not_redownload` | `AssertionError: download-иконка не появилась у «A Loved Test Work»` | **APP_BUG** | ожидаемый красный замок открытого бага, нового тикета не требуется | `bugs/BUG-014.md`, `red_lock` в `test-cases/downloads/TC-114.md` |
| TC-115 `test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload` | то же сообщение, второе место вызова | **APP_BUG** | то же (второй путь того же дефекта) | `bugs/BUG-014.md`, `red_lock` в `test-cases/downloads/TC-115.md` |
| TC-129 `test_infinite_scroll_off_keeps_native_pagination` | `TimeoutException: листинговая replay-страница не загрузилась (нет блёрбов работ)` | **TEST_BUG** | заведён долг: запись `listing_paginated.mitm` несёт `class="work blurp"` вместо `blurb` | `bugs/AT-BUG-054.md` |
| TC-130 `test_infinite_scroll_on_loads_next_page_in_background` | идентичное сообщение, тот же шаг | **TEST_BUG** | тот же долг (одна испорченная фикстура на оба кейса) | `bugs/AT-BUG-054.md` |
| TC-134 `test_kill_relaunch_without_deep_link_keeps_tabs_unchanged` | `AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` | **FLAKY** | карантин кейса + долг на стабилизацию; причина не устанавливаема по артефактам (см. ниже) | `bugs/AT-BUG-055.md`, `test-cases/tabs/TC-134.md` |
| TC-135 `test_cold_start_deep_link_reuses_single_home_tab` | `TimeoutError: маркер …/works?ao3_tab_marker=1 не появился в ao3_settings.xml за 20с` | **FLAKY** | карантин кейса + тот же долг | `bugs/AT-BUG-055.md`, `test-cases/tabs/TC-135.md` |
| TC-139 `test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos` | `AssertionError: data-kudo-clicked неожиданно = 1, ожидали стабильно 0 весь бюджет 3.0с` | **APP_BUG** | ожидаемый красный замок открытого бага (`known_issue: true`) | `bugs/BUG-015.md`, `red_lock` в `test-cases/rating/TC-139.md` |

Итого: 4 `APP_BUG` (3 — известные замки, 1 новый), 5 `TEST_BUG`, 2 `FLAKY`.
`SITE_CHANGED`, `APP_CHANGED`, `ENV_ISSUE` не выставлены ни разу — обоснование
исключения ниже.

### Где лежат доказательства

Артефакты 9 из 11 падений (весь первый сегмент) заархивированы в
`runs/RUN-20260804-1624/allure/` — 53 файла: `*-result.json` + скриншот
(`.png`) + page source (`.xml`) + logcat/context/stderr (`.txt`) на каждое
падение. Это восстановление: рабочий каталог `framework/allure-results/`
на момент триажа ПУСТ (mtime 2026-08-04 22:00) — его стёр `--clean-alluredir`
последующего прогона; копия первого сегмента уцелела только в scratchpad
сессии, из неё и перенесены артефакты триажируемых падений. Артефакты
TC-134/TC-135 (второй сегмент) утрачены безвозвратно — см. «Дефекты-собратья»
п.1 и `bugs/AT-BUG-055.md`.

### Пакет доказательств — `APP_BUG` (`schemas/evidence.yaml`: 7 элементов)

**TC-090 — новый дефект (`test_add_freeform_tag_persists`).**

- `build_hash` — `1.10 (versionCode 11)`, apk `6455af0c…`, `source_commit
  63f6aac3` (`state/app-under-test.yaml` на момент прогона; новая сборка
  `1.11 (12)` зарегистрирована ПОСЛЕ прогона).
- `test_case` — TC-090 (`test-cases/rating/TC-090.md`), replay-фикстура
  `listing_basic.mitm` (не тронута порчей: 10 вхождений `blurb`, `blurp` 0).
- `steps` — `wait_ui_ready` → `open_listing(listing_basic)` (passed) →
  `tap_rate_button(900000002)` (broken): шаг ждёт
  `li#work_900000002.work.blurb [data-ao3-rate-btn]`.
- `screenshot` — `runs/RUN-20260804-1624/allure/04b14b07-8999-47bf-9489-606e1e3f5c56-attachment.png`:
  страница «Test Fixture Listing» отрисована полностью, все 4 блёрба на
  месте, Rate-кнопок нет НИ У ОДНОГО блёрба.
- `logcat` — `runs/RUN-20260804-1624/allure/d17b00ba-a449-4d1f-b61b-1def0545d157-attachment.txt`,
  строка `08-04 13:48:48.661 chromium: [INFO:CONSOLE(20)] "Uncaught
  TypeError: Cannot read properties of null (reading 'appendChild')"`.
  Строка 20 инжектируемого скрипта — это буквально
  `document.head.appendChild(noticeStyle);`
  (`app-under-test/app/src/main/assets/ao3_bridge.js:18-20`), то есть
  `document.head === null` в момент выполнения bridge'а. Рядом в том же
  логкате — деградация устройства под нагрузкой: `Choreographer: Skipped 61
  frames`, `Davey! duration=1053ms`, `Davey! duration=1898ms` за секунды до
  ошибки (это ТРИГГЕР окна гонки, но не причина падения кода).
- `page_source` — `…/d5aba7d9-6368-4187-8a69-797077e6b8ce-attachment.xml`
  (нативное дерево: WebView-контейнер приложения, состояние
  `context=NATIVE_APP` — `…/f725140a-8700-4a35-8081-1dc0fbf91867-attachment.txt`).
- `expected_actual` — **ожидалось**: bridge, инжектируемый в
  `onPageFinished` (`BrowserScreen.kt:613`), дорисовывает Rate-кнопку каждому
  `li[id^="work_"].work.blurb`; **фактически**: скрипт выставляет свой
  guard `window.__ao3Bridge = true` в строках 5-6 и умирает в строке 20 на
  `document.head === null` — guard остаётся выставленным, повторная инъекция
  для этого документа выходит по `if (window.__ao3Bridge) return;`, и
  страница остаётся БЕЗ Rate-кнопок, значков рейтинга и infinite-scroll до
  перезагрузки. Дефект приложения, а не теста: тест ждал ровно тот узел,
  который приложение обязано отрисовать, и записанная страница валидна.

**TC-114 / TC-115 / TC-139 — известные замки.** Пакет тот же по составу:
`build_hash` — та же сборка `1.10 (11)`/`6455af0c`; `test_case` — TC-114,
TC-115 (`red_lock: "BUG-014"`), TC-139 (`red_lock: "BUG-015"`,
`known_issue: "true"`); `steps` — полные деревья шагов в
`…/24a0ca1e-…-result.json`, `…/ce642741-…-result.json`,
`…/36b00127-…-result.json` (все Given/When зелёные, красный — целевой Then);
`screenshot`/`page_source`/`logcat` — `125e64c0…png` / `b1297d56….xml` /
`ada5afac….txt` (TC-114), `0b0e64f8…png` / `609bd670….xml` / `6ab5dd6c….txt`
(TC-115), `27312215…png` / `14175fe2….xml` / `befd8d95….txt` (TC-139);
`expected_actual` — TC-114/115: ожидалось, что правка тега/заметки у уже
сохранённой работы НЕ запускает повторное авто-скачивание (тогда карточка
показывает download-иконку «файл не скачан»); фактически иконка не появилась,
т.е. работа была скачана ретроактивно — ровно формулировка `BUG-014`.
TC-139: ожидалось `data-kudo-clicked="0"` стабильно 3с после правки тега у
ранее «кудошенной» работы; фактически `= 1` — ретроактивный авто-клик kudos,
ровно формулировка `BUG-015`. Новые баги не заводятся (дедуп в существующие
Open/Fixed-тикеты; `BUG-014` уже переведён человеком в `Fixed` и ждёт сборку
— на сборке ЭТОГО прогона фикса ещё нет, красный ожидаем).

### Пакет доказательств — `TEST_BUG` (`schemas/evidence.yaml`: 3 элемента)

**TC-085 / TC-086.**
`failing_test` — `framework/tests/test_filter_profiles.py::test_rename_filter_profile_keeps_query_string`
(allure `237b1d86-…`) и `::test_rename_filter_profile_to_duplicate_name`
(allure `4ff1ad91-…`); оба broken на шаге «профиль переименован».
`root_cause` — в тесте, не в приложении: локатор
`framework/screens/settings_screen.py:269` ищет `@content-desc="Renam3"`,
тогда как приложение рисует `Rename` (`SettingsScreen.kt`, зафиксировано в
`requirements` обоих кейсов). Провенанс: побайтовый дифф против копии
`rehearsal-backups/settings_screen.py` — единственное содержательное отличие
`Rename`→`Renam3`; строка изменена коммитом `2f26f8a` ТЕСТОВОГО репозитория;
сборка приложения между зелёным `RUN-20260803-2012` (оба кейса passed) и этим
прогоном не менялась. `fix_or_debt` — заведён `bugs/AT-BUG-053.md`
(`type: test_debt`, `debt_kind: weak_locator`, Open).

**TC-129 / TC-130.**
`failing_test` — `framework/tests/test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination`
(allure `dd15f724-…`) и `::test_infinite_scroll_on_loads_next_page_in_background`
(allure `47d6e46e-…`); оба broken на `open_listing(listing_paginated)`,
сообщение «листинговая replay-страница не загрузилась (нет блёрбов работ)».
`root_cause` — в фикстуре тестовой системы: `listing_paginated.mitm` несёт
`class="work blurp"` вместо `class="work blurb"` на всех 5 страницах
(побайтовый дифф против копии: ровно 5 отличий, `blurb` 5→0, `blurp` 0→5,
длина файла не изменилась). `fix_or_debt` — заведён `bugs/AT-BUG-054.md`
(`type: test_debt`, `debt_kind: missing_fixture`, Open) с требованием
перегенерации записи штатным путём и юнит-сверки записи с её генератором.

**TC-043.**
`failing_test` — `framework/tests/test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs`
(allure `951afade-…`); broken на первом же содержательном шаге
`open_listing`, трасса — `switchContext` → `startChromedriverProxy` →
`Chromedriver.handleChromedriverStartFailure`. `root_cause` — в фреймворке:
`app_steps.wait_ui_ready` не дожидается оседания стартовой загрузки home,
и следующий же `contexts.in_webview` пытается поднять chromedriver-сессию по
навигирующемуся документу. Это ровно класс открытого долга `AT-BUG-047`, на
ЭТОМ ЖЕ кейсе, причём на том самом ВТОРОМ choke point (`contexts.in_webview`),
из-за которого была отклонена attempt 2 его фикса. Сигнатура — вариант того
же механизма (`no such execution context: loader has changed while resolving
nodes` вместо `cannot determine loading status from no such window`): обе
сигнатуры уже наблюдались на одном и том же классе — см. таблицу перепрогонов
в `runs/RUN-20260804-1317.md`, где они чередовались на TC-078 при
неизменном коде. `fix_or_debt` — существующий `bugs/AT-BUG-047.md` (Open,
attempt 2 отклонён); нового тикета не завожу, чтобы не плодить дубль класса.

### Пакет доказательств — `FLAKY` (`schemas/evidence.yaml`: 3 элемента)

**TC-134 / TC-135.**
`rerun_history` — **изолированные перепрогоны в этом триаже ЗАПРЕЩЕНЫ
инструкцией координатора** (устройство занято дневным smoke/regression), так
что воспроизводимость не измерялась. Доступная история межпрогонная: оба
кейса `passed` в `RUN-20260803-2012` и `failed`/`broken` здесь — при
ИДЕНТИЧНОЙ сборке приложения (`1.10 (11)`, `6455af0c`, `source_commit
63f6aac3`) и ИДЕНТИЧНОМ коде тестов и шагов (между прогонами
`framework/tests/test_tabs.py` и `framework/steps/app_steps.py` не менялись —
сверено `git log --since="2026-08-03 20:00" -- framework/`). Перепрогон
запрошен отдельной строкой в эскалациях.
`failure_signature` — разная у двух кейсов, но одного класса (наблюдение
персистентности вкладок через `run-as cat ao3_settings.xml`): TC-134 —
`AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` при том,
что непосредственно ПРЕДШЕСТВУЮЩИЙ позитивный якорь
`wait_persisted_tab_count(N)` в том же тесте прошёл секундами раньше;
TC-135 — `TimeoutError: маркер …ao3_tab_marker=1 не появился в
ao3_settings.xml за 20с` при измеренном окне персиста 6.3-7.3с. Почему
причина НЕ устанавливается по артефактам: (а) allure-артефакты второго
сегмента прогона уничтожены (`framework/allure-results/` пуст, стёрт
`--clean-alluredir` последующего прогона) — логката/скриншота/page source по
этим двум падениям не существует; (б) сам оракул слепой —
`adb.shell` отбрасывает `returncode`/`stderr`
(`framework/core/adb.py:37-42`), а `_parse_persisted_tabs` превращает
нечитаемый ответ в `[]` (`framework/steps/app_steps.py:319-331`), поэтому
«0 вкладок»/«маркера нет» неотличимы от «файл не прочитан».
`quarantine_decision` — переход `active → quarantined` выполнен обоим кейсам:
`test-cases/tabs/TC-134.md` и `test-cases/tabs/TC-135.md` несут
`automation_status: quarantined`, `quarantine_reason` (с сигнатурой и
причиной неустановимости), `quarantine_since: "2026-08-04T22:20:45Z"`,
`quarantine_owner: test-maintainer`, `quarantine_expiry: ""` (действует
`sla.quarantine_max`); заведён долг `bugs/AT-BUG-055.md`
(`type: test_debt`, `debt_kind: flaky_test`, Open) с планом: сначала
честное чтение prefs, затем перепрогон с расширенным логированием; при
воспроизведении на доказанно исправном чтении вердикт переезжает в `APP_BUG`.

### Почему не выставлены остальные вердикты

- **не `APP_CHANGED`** ни по одному падению: прогон шёл на сборке
  `1.10 (versionCode 11)`, `apk 6455af0c`, `source_commit 63f6aac3` — той же
  самой, что и последний зелёный `RUN-20260803-2012`. Диапазон коммитов
  приложения между прогонами ПУСТ, значит намеренного изменения поведения
  между ними быть не может. (Сборка `1.11 (12)`, `source_commit bfc8f41a`
  зарегистрирована в `state/app-under-test.yaml` уже ПОСЛЕ этого прогона —
  к его красным отношения не имеет.)
- **не `SITE_CHANGED`** по TC-129/TC-130 (единственные кандидаты — «блёрб не
  найден на листинге»): изменение лежит в НАШЕЙ записи, а не на AO3.
  Позитивные контроли: (а) генератор записи
  `framework/data/recording_builder.py:279` до сих пор выпускает
  `class="work blurb group work-{wid}"` — файл разошёлся со своим
  генератором, т.е. правился руками, а не перезаписывался с живого сайта;
  (б) токена `blurp` в разметке AO3 не существует, и он не встречается ни в
  одной другой записи (`listing_basic` 10×`blurb`/0×`blurp`, `works_multi`,
  `listing_duplicate_work` — тот же расклад); (в) живой AO3 в тот же день
  зелёный (`RUN-20260804-1355`, canary 10/10 live). Диффа live↔replay «на
  стороне AO3» не существует — потому вердикт `TEST_BUG`, а не
  `SITE_CHANGED`.
- **не `ENV_ISSUE`** ни по одному падению: обязательный пакет
  (`env_check` + `retry_result` + `logs`) СОБРАТЬ НЕЛЬЗЯ — перепрогоны в этом
  диспатче запрещены (`retry_result` недостижим), а состояние среды на момент
  прогона уже не проверяемо измерением (эмулятор с тех пор перезапущен под
  дневной прогон, `hardware-qemu.ini` отражает текущий бут, не тот).
  Заявлять env-негатив без сверки канонической формой запрещено (CLAUDE.md,
  permission-hygiene п.6/F-30), поэтому `ENV_ISSUE` не выставлен даже там, где
  он правдоподобен — см. эскалацию №1 (TC-043 под `AO3_EMU_GPU=host`).
  Отдельно: токена ENV_ISSUE-детектора среды в прогоне не было ни в одном
  сегменте, `Get-Device` → `DEVICE: emulator-5554` до и после сегментов,
  `recoveries 0/2` — «среда жива» как факт зафиксирована test-runner'ом.

### Эскалации (для координатора, вне мандата failure-analyst)

1. **TC-043 — нужен один разграничивающий перепрогон.** Сигнатура падения
   буквально совпадает с TC-078 из `RUN-20260804-1317`, где вердикт был
   `ENV_ISSUE` (дефолтный GPU `swiftshader` вместо предписанного
   `AO3_EMU_GPU=host`: под swiftshader 1 зелёный из 4, под host — 4 из 4;
   класс `bugs/AT-BUG-021.md`). ЭТОТ прогон шёл на дефолтном
   `swiftshader_indirect` (заявлено test-runner'ом в разделе «Контекст
   запуска»; проверить измерением сейчас уже нельзя — эмулятор перезагружен).
   Вердикт `TEST_BUG`/AT-BUG-047 поставлен по механизму падения (барьер
   `wait_ui_ready` + choke point `contexts.in_webview`, тот же тест, тот же
   долг), но альтернатива «env» им не исключена. Разграничение стоит один
   изолированный прогон TC-043 под `AO3_EMU_GPU=host` (3-5 повторов): зелёный
   ⇒ вклад env подтверждён, красный ⇒ долг AT-BUG-047 подтверждён как
   единственная причина.
2. **TC-134/TC-135 — перепрогон с расширенным логированием** (после
   починки чтения prefs по `AT-BUG-055`): logcat + сырой дамп
   `ao3_settings.xml` на каждой неудачной итерации опроса, 3-5 повторов.
   Если красное воспроизводится при доказанно исправном чтении — падения
   переезжают на `APP_BUG` и требуют `BUG-*`.
3. **Уничтожение артефактов прогона — процессная дыра, чинится не мной.**
   `framework/allure-results/` — общий рабочий каталог, который каждый
   следующий прогон стирает `--clean-alluredir`; архивация в
   `runs/RUN-*/allure/` делается вручную и для ЭТОГО прогона сделана не была,
   поэтому доказательства двух из одиннадцати падений утрачены до триажа
   (тот же класс уже отмечен в `runs/RUN-20260804-1317.md`, «Дефекты-собратья»
   п.3 — второй прецедент подряд). Предложение: архивацию
   `framework/allure-results/` → `runs/RUN-<id>/allure/` сделать обязательным
   шагом закрытия прогона у test-runner (или pre_step qa-loop), а не
   практикой по памяти.

### Дефекты-собратья (D-0043) — доклад failure-analyst

Замечено рядом, scope не расширял, чинить не мне:

1. **Класс TC-090 внутри самого bridge'а шире одной строки.** Guard
   `window.__ao3Bridge = true` (`ao3_bridge.js:5-6`) выставляется ДО всей
   работы с DOM, а необёрнутых обращений к `document.head`/`document.body`
   в скрипте шесть: строки 20, 199, 1024, 1040, 1069 (плюс чтение
   `document.body.scrollHeight` в 900). Любое из них, поймав `null` на ещё
   не разобранном документе, убивает инициализацию целиком и оставляет
   страницу навсегда (до перезагрузки) без Rate-кнопок/бейджей/infinite
   scroll. Заводящему баг: это один класс, а не строка 20.
2. **Слепое чтение prefs — не только TC-134/TC-135.** Семейство
   `_read_tabs_prefs_raw`/`wait_tabs_persisted`/`wait_persisted_tab_count`/
   `assert_persisted_tab_url_at`/`assert_persisted_marker_count` даёт 53
   вызова-оракула в `framework/tests/test_tabs.py` (TC-025, TC-131…TC-136 и
   соседи); все они одинаково не отличают «пусто» от «не прочитано». Сегодня
   красными стали два, но экспозиция — весь tabs-набор. Учтено как требование
   классовой починки в `bugs/AT-BUG-055.md`.
3. **Порча тестовой фикстуры ловится только device-прогоном.** Ни у одной
   `.mitm`-записи нет device-free сверки «содержимое записи ↔ её генератор»
   (`recording_builder`), хотя юнит-тесты записей уже существуют
   (`framework/tests/test_recording_builder_unit.py`). Правка одного байта в
   записи стоит 40-минутного регресса, чтобы быть замеченной. Учтено в
   `bugs/AT-BUG-054.md`.
4. **Опечатка в строковой константе локатора не ловится ничем**, кроме
   прогона самого теста: `red_probe` кейсов TC-085/TC-086 снят 2026-07-21,
   до порчи, и с тех пор ничто не сверяет `content-desc`-литералы
   `framework/screens/*.py` с `contentDescription` в коде приложения. Тот же
   класс, что п.3, но на другой оси (локаторы вместо фикстур).
5. **Вторая подряд смерть фонового job'а на ~60-минутной отметке** (см.
   раздел «Находка» выше, наблюдение test-runner'а) — механизм, из-за
   которого прогон дробится на сегменты, и именно из-за дробления артефакты
   второго сегмента оказались в общем каталоге и были стёрты. Два дефекта
   (лимит job'а и неархивируемые артефакты) складываются в потерю
   доказательств — чинить стоит оба, но самостоятельным пунктом.

## Дефекты-собратья (D-0043) — доклад

1. **Рецидив «фоновый job убит харнессом ~на часовой отметке»** — см. раздел
   «Находка» выше. Уже задокументирован как дефект-собрат №1 в
   `runs/RUN-20260803-2012.md`; наблюдается второй раз подряд на этом же
   классе прогона (полный `(p0 or p1) and not live`, ~165 тестов, 60-70 мин).
   Не app-дефект — ограничение процесса test-runner'а/харнесса. Для Lead:
   канон 07-19 (foreground `Wait-Process`) фактически НЕ спасает от лимита
   времени жизни самого фонового `run_in_background`-job'а — двух прецедентов
   уже достаточно, чтобы считать лимит систематическим (~60 мин), а не
   единичным сбоем.
2. **TC-129/TC-130 — идентичная сигнатура `TimeoutException` на одном и том же
   шаге** (ожидание replay-запроса), оба теста соседние в одном файле
   (`test_infinite_scroll.py`), оба ранее (RUN-20260803-2012) были зелёными.
   Похоже на класс-кандидат (общий барьер/фикстура файла), но НЕ тотальная
   односигнатурная смерть среды (остальные файлы вокруг зелёные) — fail-fast
   не применён по инструкции координатора. Триаж — за failure-analyst.
3. **TC-085/TC-086 — соседние тесты одного файла (`test_filter_profiles.py`),
   оба упали первыми в файле** (позиции 1-2 из 5), оба искали один и тот же
   элемент `content-desc="Rename3"` по разным xpath-якорям — возможный
   класс-кандидат (общая пред-условная фикстура/состояние), тоже не
   расследовал — не моя роль (test-runner фиксирует факт).
4. **TC-043 (AT-BUG-047) — сигнатура в этом прогоне ИНАЯ**, чем
   задокументированная в открытом `bugs/AT-BUG-047.md` (там `cannot determine
   loading status from no such window`; здесь `A new session could not be
   created ... no such execution context: loader has changed`) — возможно тот
   же класс гонки (WebView/chromedriver), возможно другой; решение о
   дедупе/новом инциденте — за failure-analyst, не беру на себя вердикт.
5. **Сравнение с последним чистым regression-baseline** (`RUN-20260803-2012`,
   160/165 passed): в ЭТОМ прогоне 154/165 — на 6 failed больше, из них 3
   известных красных замка (TC-114/115 → BUG-014, TC-139 → BUG-015, ожидаемо)
   + 8 незамкнутых новых красных (TC-043, TC-085, TC-086, TC-090, TC-129,
   TC-130, TC-134, TC-135), из которых ТОЛЬКО TC-043 имеет открытый
   test_debt-тикет (AT-BUG-047) с ДРУГОЙ сигнатурой. Сборка приложения не
   менялась между прогонами (`state/app-under-test.yaml` не трогался с
   2026-08-03). Голый факт для failure-analyst, вердикт (флейк/деградация
   среды/регресс) не выношу.

## Условия закрытия прогона (Closed)

- [x] Каждое падение имеет вердикт и связанное действие — 11/11 (раздел «Падения и триаж», 2026-08-04T22:20:45Z): 4 APP_BUG, 5 TEST_BUG, 2 FLAKY
- [x] Для APP_BUG существует или создан BUG-файл — TC-114/115 (`BUG-014`), TC-139 (`BUG-015`), TC-090 (`BUG-056`) покрыты
- [x] Долги по TEST_BUG/FLAKY заведены: `AT-BUG-053` (TC-085/086), `AT-BUG-054` (TC-129/130), `AT-BUG-055` (TC-134/135, + карантин обоих кейсов); TC-043 дедуплицирован в открытый `AT-BUG-047`
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована — не выполнялось (шаг снимка за qa-loop)
