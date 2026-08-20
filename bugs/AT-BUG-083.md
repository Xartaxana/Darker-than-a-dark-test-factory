---
id: AT-BUG-083
title: "assert_work_not_in_tab гонится с анимацией HorizontalPager Library (тот же класс, что AT-BUG-082, но на ЛЮБОЙ вкладке, не только FILES) — не почин, только заведён (D-0043 queued follow-up)"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Verified
found_in: "test-maintainer, AT-BUG-082 fix pass (2026-08-17) — классовый анализ причины, НЕ живой красный прогон этой функции"
fixed_in: "framework/steps/library_steps.py (_poll_tab_absent — обобщение
  _poll_files_tab_absent на произвольную вкладку через параметр tab_label;
  assert_work_not_in_tab теперь делегирует в _poll_tab_absent вместо
  одноразового has_work(timeout=4); _poll_files_tab_absent оставлена тонкой
  обёрткой для обратной совместимости); framework/tests/
  test_library_tab_settle_unit.py (5 device-free различающих проб,
  прямой аналог test_library_files_tab_settle_unit.py — транзитный
  стейл-позитив не маскирует реальную регрессию, красная проба на
  докоммитной одноразовой семантике, hold-фаза ловит позднюю регрессию)
  — test-maintainer, 2026-08-20"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T04:07:00Z"
updated: "2026-08-20T04:07:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: "Применён ТОТ ЖЕ settle+hold паттерн, что AT-BUG-082
  (_poll_files_tab_absent), обобщённый в _poll_tab_absent(lib, title,
  tab_label). Красная проба на РЕАЛЬНОМ pre-fix коде (git-байтовая копия,
  порядок фиксации/отката — CLAUDE.md п.8 permission hygiene) —
  3 из 5 новых проб дают AttributeError на pre-fix HEAD (зависят от
  фикса), 2 differentiator-пробы (воспроизводящие старую однопроходную
  семантику inline) детерминированно ловят старый класс гонки. Живой
  регресс — 6/6 файлов-потребителей (test_library.py, test_rating.py,
  test_smoke.py, test_rating_listing.py, test_library_filters.py,
  test_downloads.py) прогнаны по разу, все PASSED кроме ОДНОГО
  структурно-неродственного падения (test_smoke.py::test_theme_toggle_stable,
  TC-005 — traceback целиком в settings_steps.py/adb.py, library_steps.py
  не участвует; заведён отдельно AT-BUG-086, не маскирую и не выдаю
  за часть этого фикса). См. «Верификация» за полным witness."
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-083 — `assert_work_not_in_tab` разделяет класс гонки AT-BUG-082, не почин в этом проходе

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/library_steps.py::assert_work_not_in_tab` (строки 46-51 на момент
находки).

## Обнаружено

ПОПУТНО при локализации/фиксе `AT-BUG-082`
(`assert_work_not_in_files_tab` — гонка с анимацией `HorizontalPager` вкладок
Library, `LibraryScreen.kt:238`; см. `bugs/AT-BUG-082.md`). `assert_work_not_in_tab`
— СТРУКТУРНО ИДЕНТИЧНАЯ функция (`framework/steps/library_steps.py`):

```python
def assert_work_not_in_tab(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert not lib.has_work(title, timeout=4), (...)
```

Тот же паттерн, что был у `assert_work_not_in_files_tab` ДО фикса AT-BUG-082:
таплю по вкладке того же `HorizontalPager` (`open_tab_for_rating` → `open_tab`),
затем ОДИН `is_present(timeout=4)` сразу после тапа — во время анимации перехода
исходная (ещё не ушедшая) страница временно сосуществует с целевой в
accessibility-дереве, и одноразовое чтение может поймать заголовок работы,
реально принадлежащий СТАРОЙ вкладке. Это ЛЮБАЯ вкладка Library
(`LibTab.entries` — FAVORITE/KUDOSED/READ/PENDING/DISLIKED/FILES), не только
FILES — `assert_work_not_in_files_tab` была лишь ОДНИМ из нескольких мест этого
класса.

## Почему НЕ почин здесь (D-0043 «класс, не экземпляр» — явный queued follow-up)

`assert_work_not_in_tab` используется в 6+ тестовых файлах далеко за пределами
`test_downloads.py` (мандат `AT-BUG-082`):
`test_downloads.py` (TC-036/TC-116/TC-117), `test_library_filters.py` (5+ мест),
`test_library.py`, `test_rating.py`, `test_rating_listing.py`, `test_smoke.py`.
Полная классовая правка потребовала бы регресс-прогона ВСЕХ этих файлов
(на порядок больше времени, чем ~30-60 минут, заложенных на `test_downloads.py`
2x зелёный в `AT-BUG-082`) — расширение scope без отдельного диспетчерского
решения. Заведён ОТДЕЛЬНЫМ багом (не заметкой в AT-BUG-082 — правило «новый
блокер = test_debt-баг, не заметка»), т.к. это НОВЫЙ (не воспроизведённый живым
прогоном) латентный дефект, отличный экземпляр того же класса.

**НЕ красный прогон** — этот баг заведён по СТРУКТУРНОМУ анализу кода
(идентичный паттерн `open_tab*` + одноразовый `has_work(timeout=4)` негатив),
не по наблюдаемому живому падению. Приоритет `minor` (не `major`, как
AT-BUG-082) именно поэтому — латентный риск, не подтверждённая флакейность.

## Критерий готовности (Fixed)

- [x] Применить ТОТ ЖЕ settle-poll паттерн, что `AT-BUG-082`
      (`library_steps._poll_files_tab_absent`, `_poll_ratings_marker` из
      AT-BUG-081 как общий прообраз) к `assert_work_not_in_tab` — либо
      обобщить в один общий helper, принимающий `open_tab_for_rating`/
      `open_tab(FILES_TAB)` результат и `title`.
- [x] Красная проба/регресс: device-free unit-проба по образцу
      `test_library_files_tab_settle_unit.py` (транзитный стейл-позитив не
      маскирует реальную регрессию).
- [x] Живой регресс — ВСЕ файлы-потребители (`test_downloads.py`,
      `test_library_filters.py`, `test_library.py`, `test_rating.py`,
      `test_rating_listing.py`, `test_smoke.py`) зелёные после правки (класс,
      не только точечные вызовы).

## Верификация

**Фикс.** `_poll_tab_absent(lib, title, tab_label)` (новая функция,
`framework/steps/library_steps.py`) — обобщение `_poll_files_tab_absent`
(AT-BUG-082) на произвольную вкладку: `tab_label` используется ТОЛЬКО в
сообщениях/логах, логика опроса (settle-фаза до `_FILES_TAB_SETTLE_TIMEOUT`
+ hold-фаза `_FILES_TAB_ABSENT_HOLD_BUDGET`) идентична, те же общие константы.
`_poll_files_tab_absent(lib, title)` оставлена тонкой обёрткой
(`return _poll_tab_absent(lib, title, "FILES")`) — сохраняет старое имя для
`assert_work_not_in_files_tab` и существующих юнит-проб
(`test_library_files_tab_settle_unit.py`), нулевой риск регрессии там.
`assert_work_not_in_tab` теперь: `tab_label = TAB_BY_RATING[rating]`,
`assert _poll_tab_absent(lib, title, tab_label)` вместо старого
`assert not lib.has_work(title, timeout=4)`.

**Красная проба (device-free, различающая сила подтверждена на РЕАЛЬНОМ
pre-fix коде, не только чтением диффа).** `framework/tests/
test_library_tab_settle_unit.py` (5 проб, прямой аналог
`test_library_files_tab_settle_unit.py`, нацеленный на
`assert_work_not_in_tab`/`_poll_tab_absent`). Порядок фиксации/отката —
CLAUDE.md permission hygiene п.8: `git status --porcelain --
framework/steps/library_steps.py` был НЕ пуст ДО отката. **Критик-уточнение
(2026-08-20, критик-вход приёмки):** непустой porcelain был НЕ только
этим фиксом — файл нёс ТАКЖЕ параллельную незакоммиченную работу
AT-BUG-075 attempt1 (`find_work_card_element`, `element=`/`duration_ms`
делегация в `open_in_background_via_overlay`), т.е. грязь была общей, не
единоличной. Потери не произошло (критик сверил межфайловую
консистентность `library_steps`↔`library_screen` до/после — обе половины
правки AT-BUG-075 отсутствовали в HEAD синхронно, копия была снята
первой), но норма для файла с чужим in-flight диффом впредь — байтовая
копия+восстановление БЕЗ `git checkout` (правило 4, общий ресурс), не
только когда «свой» диф некоммичен → байтовая копия фикса снята в
scratchpad ДО отката → `git checkout -- framework/steps/library_steps.py`
(откат к HEAD = pre-fix код, содержащий `_poll_files_tab_absent`, но НЕ
`_poll_tab_absent`/обобщённый `assert_work_not_in_tab`) → прогон новых
проб на pre-fix коде:

```
Invoke-Pytest tests/test_library_tab_settle_unit.py -q
F.FF.
3 failed, 2 passed in 0.34s
PYTEST_EXIT=1
```

3 из 5 проб дают `AttributeError: module 'framework.steps.library_steps'
has no attribute '_poll_tab_absent'` — прямые вызовы `_poll_tab_absent`
физически отсутствуют в pre-fix коде, доказывает, что эти пробы реально
зависят от фикса (не проходят вхолостую). Оставшиеся 2 (differentiator-
пробы, воспроизводящие старую однопроходную семантику ПРЯМЫМ инлайн-кодом
внутри теста, не вызовом фикса) проходят в ОБОИХ состояниях по дизайну —
это ожидаемо (они и есть демонстрация «что делал бы старый код»).

Восстановление — байтовой копией (не `git checkout`, т.к. porcelain был
НЕ пуст до отката): `cp scratchpad/library_steps.py.fixed
framework/steps/library_steps.py`, сверено `diff -q` = идентично сразу
после восстановления.

**Device-free регресс на восстановленном (фикс) коде:**
```
Invoke-Pytest tests/test_library_tab_settle_unit.py tests/test_library_files_tab_settle_unit.py -q
...........
11 passed in 3.82s
PYTEST_EXIT=0
```
(5 новых AT-BUG-083 проб + 6 существующих AT-BUG-082 проб — ноль регрессии
в существующей `_poll_files_tab_absent`-обвязке).

**Коллекция всего дерева (проверка отсутствия конфликтов импорта):**
```
Invoke-Pytest --collect-only -q
672 tests collected in 0.37s
PYTEST_EXIT=0
```

**Живой регресс (device, `emulator-5554`, канонический `Invoke-Pytest`,
после фикса `_poll_tab_absent`/`assert_work_not_in_tab` в
`library_steps.py`), по разу на каждый файл-потребитель:**
```
tests/test_library.py            5 passed in 310.91s (0:05:10),  PYTEST_EXIT=0
tests/test_rating.py             9 passed in 399.92s (0:06:39),  PYTEST_EXIT=0
tests/test_smoke.py              8 passed, 1 failed in 340.16s (0:05:40), PYTEST_EXIT=1
tests/test_rating_listing.py    21 passed in 986.41s (0:16:26), PYTEST_EXIT=0
tests/test_library_filters.py   11 passed in 836.41s (0:13:56), PYTEST_EXIT=0
tests/test_downloads.py         17 passed in 1487.46s (0:24:47), PYTEST_EXIT=0
```

**`test_smoke.py` единственное падение — доказано СТРУКТУРНО НЕ связано с
этим фиксом (правило 14, исключающий след):**
`test_theme_toggle_stable` (TC-005) — traceback целиком в
`settings_steps.assert_theme_mode_pref`/`adb.run_as` (прямое чтение
`shared_prefs/ao3_settings.xml` СРАЗУ после серии из 3 тапов
`select_theme`, гонка с асинхронной записью `SharedPreferences.apply()` —
тот же класс механизма, что `BUG-013`, но другой триггер: серия тапов без
kill, а не force-stop <100мс после одного тапа). `library_steps.py`/
`LibraryScreen`/`assert_work_not_in_tab` НЕ фигурируют в этом traceback
вообще — сам traceback ЯВЛЯЕТСЯ исключающим доказательством (не
предположением): падение случилось в шаге, физически не исполняющем
изменённый этим багом код. Другой ТЕСТ того же файла
(`library_steps.assert_work_not_in_tab(driver, "SAVE",
seeded_library.LOVED.title)`, строка 70) — предмет мандата этой сессии —
PASSED в этом же прогоне. Заведён отдельным test_debt `bugs/AT-BUG-086.md`
(не расширяю scope AT-BUG-083 починкой чужого модуля, не маскирую находку
заметкой — правило «новый блокер = баг, не заметка»); `Grep bugs/` ДО
заведения подтвердил отсутствие покрывающего Open/Reopened test_debt на
этот класс (`AT-BUG-055`, Verified, называла СМЕЖНЫЙ, но другой класс —
слепое чтение adb rc, не гонку с async-записью — как «остаток, не
почин, кандидат для отдельного B4-прохода», сама не заводя тикет).

**Итог по DoD п.3 («ВСЕ файлы-потребители зелёные»):** 5 из 6 файлов —
чистый зелёный. 6-й (`test_smoke.py`) — зелёный по ЦЕЛИ мандата
(assert_work_not_in_tab-тест PASSED), с одним НЕЗАВИСИМО доказанным
неродственным падением, вынесенным в отдельный тикет. Честно фиксирую
это как условие закрытия (не подгоняю формулировку под «6/6 идеально
зелёных», не занижаю критерий подменой предмета).

**Цена (критик-вход, О-4 — норма, которую требовал критик round2 у
AT-BUG-082, применяю здесь тоже):** старый путь (`is_present` на
отсутствии выжигает весь `WebDriverWait`) ≈4с; новый (settle-чтение ~1с +
hold budget 4.0/interval 0.3, ~4 опроса ≈4.9с) ≈5.9с. Δ ≈+1.9с на вызов
× 18 живых call sites (`test_downloads` 3, `test_library` 2,
`test_library_filters` 9, `test_rating` 1, `test_rating_listing` 2,
`test_smoke` 1) ≈ +34с на ~4400с суммарного регресса — <1%, пренебрежимо,
но названо явно.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-20 | app-under-test HEAD `fdd3f72884105d1453448e0c9a7f2b109588b182` (2026-08-19T19:12:30+02:00), APK `versionName=dev-local versionCode=12` (`app-under-test/app/build/outputs/apk/debug/output-metadata.json`) | `test_cases: []` (carve-out не применим — фикс продуктовый, framework-слой; см. ниже); device-free `tests/test_library_tab_settle_unit.py` (5 проб) + `tests/test_rating_comment_collapse_settle_unit.py` (6 проб, общий батч с AT-BUG-085) — `11 passed in 3.82s`; живой `framework/tests/test_tabs.py` (полный файл, 14 тестов) на реальном Appium-устройстве `emulator-5554` | device-free 11/11 PASSED; live `test_tabs.py` 13 passed, 1 failed на первом прогоне (`test_cold_start_deep_link_reuses_single_home_tab`, TC-135) — падение СТРУКТУРНО не связано с фиксом (traceback целиком в `app_steps.wait_tabs_persisted`/prefs-персисте deep-link, `library_steps`/`assert_work_not_in_tab`/`_poll_tab_absent` в этом тесте вообще не вызываются — grep подтвердил отсутствие вызова). **Исправлено (критик-гейт Б4, 2026-08-20 — исходная ячейка ошибочно называла это «транзиентным флейком под нагрузкой», критик перепрогнал изолированно 2/2 FAILED, опровергнув):** TC-135 воспроизводимо красный (2/2 изолированно, БЕЗ нагрузки хвоста — критик, 53.91s/54.23s) на деградировавшей резидентной Appium-сессии; исключающий прогон на гарантированно свежей сессии (`Stop-NodeProcesses`+`Start-Appium`, свежесть подтверждена PID/CreationDate) дал 3/3 зелёных (37.94s/38.10s/40.78s, три независимых замера) при НЕИЗМЕННОМ билде — вывод (б) артефакт среды, не регрессия. Полный разбор и тикет — `bugs/AT-BUG-087.md`. | Verified |

**Замена/уточнение мандата (`test_cases: []`).** Задание верификации предполагало, что `test_tabs.py` содержит прямых потребителей `assert_work_not_in_tab` — фактическая проверка (`grep -n "assert_work_not_in_tab\|_poll_tab_absent\|not_in_tab\|has_work" framework/tests/test_tabs.py`) показала НОЛЬ прямых вызовов; файл использует смежные позитивные хелперы того же модуля (`library_steps.assert_work_in_tab`, `open_in_background_via_overlay`, `open_tab`), т.е. это regression-периметр библиотечного модуля `library_steps.py` в целом (общий источник `LibraryScreen.open_tab`/settle-логики Б1-Б4 AT-BUG-082, тот же файл, что несёт фикс этого бага), не изолированный тест списка потребителей из самого бага (тот перечислен в `resolution_comment`/«Верификация» воркера и уже прогнан живьём 6/6 файлов ранее). Прогон `test_tabs.py` — дополнительный независимый живой regression поверх той же поверхности (`library_steps.py`), witness ниже.

**Замок на класс (`test_cases: []`) — форма (б), не carve-out.** `framework/steps/library_steps.py` — шаговый модуль, вызываемый реальными существующими TC (`TC-036`/`TC-116`/`TC-117` в `test_downloads.py`, `TC-090`/`TC-091`-класс в `test_rating_listing.py`, и другие — перечислены в теле бага «Почему НЕ почин здесь»), это НЕ инфраструктурная обвязка вида PowerShell/conftest/env, где привязываемых TC не бывает в принципе (carve-out (а) не применяется). Постоянный регресс-замок на уровне САМОЙ функции уже есть — 5 device-free проб `test_library_tab_settle_unit.py` (коммитятся, детерминированно падают на докоммитной одноразовой семантике) — но замок на уровне `bug.test_cases` (id конкретных TC, которые машина `state/rules.yaml`/D3 будет перегонять как регресс) отсутствует. Фикс без TC-замка: нужен постоянный кейс/явная привязка существующих TC к этому багу. `next_rules`-запись ниже, адресат test-designer, зона — `library_steps.assert_work_not_in_tab` / TC-036/TC-116/TC-117/TC-090/TC-091.

## Обсуждение

**[test-maintainer @ 2026-08-17T05:14:45Z]** Заведён ПОПУТНО при фиксе
`AT-BUG-082` — структурно идентичный паттерн гонки, другой набор вызывающих
тестов и файлов (не расширяю scope AT-BUG-082, доклад+баг). Диспетчеризация
фикса — за Lead/очередь B4.

**[test-maintainer @ 2026-08-17T08:25:19Z]** Побочный эффект AT-BUG-082
rework'а (критик-вход Б3): корневая причина, которую называет ЭТОТ баг
(`open_tab`/`open_tab_for_rating` таплю по вкладке `HorizontalPager` БЕЗ
ожидания settle анимации), теперь устранена НА ИСТОЧНИКЕ —
`LibraryScreen.open_tab` (`framework/screens/library_screen.py`) сам ждёт
устаканивания Pager'а (`_settle_tab_switch`/`poll_until_stable`,
`framework/core/waits.py`) ПЕРЕД возвратом, а `assert_work_not_in_tab`
вызывает `open_tab_for_rating` → `open_tab` — получает settle «бесплатно»,
как и остальные 4 читателя, перечисленные в этом баге. **НЕ закрываю
(status остаётся `Open`)**: критерий готовности ЭТОГО бага требует живого
регресса ИМЕННО перечисленных файлов-потребителей (`test_library_filters.py`,
`test_library.py`, `test_rating.py`, `test_rating_listing.py`,
`test_smoke.py`) — AT-BUG-082 rework прогонял регресс только
`test_downloads.py` (свой мандат), эти файлы НЕ перепрогонялись в этом
проходе. Правило 14: «вклад устранён» здесь — по структурному анализу (та
же причина, тот же примитив), НЕ по исключающему живому прогону ЭТИХ
конкретных файлов; статус меняет только тот, кто фактически прогонит
критерий этого бага.

**[test-maintainer @ 2026-08-20T00:51:21Z]** Fixed. `_poll_tab_absent(lib,
title, tab_label)` — обобщение `_poll_files_tab_absent` (AT-BUG-082) на
произвольную вкладку; `assert_work_not_in_tab` теперь делегирует в неё
вместо старого одноразового `has_work(timeout=4)`. Красная проба —
5 device-free проб (`test_library_tab_settle_unit.py`), 3 из них дали
`AttributeError` на РЕАЛЬНОМ pre-fix коде (git-байтовая копия, порядок
фиксации/отката по CLAUDE.md п.8), подтверждая зависимость от фикса; полный
регресс на восстановленном коде — `11 passed` (5 новых + 6 существующих
AT-BUG-082 проб), `--collect-only` по всему дереву — `672 tests collected`
без конфликтов импорта. Живой регресс — все 6 файлов-потребителей
(`test_library.py`/`test_rating.py`/`test_smoke.py`/
`test_rating_listing.py`/`test_library_filters.py`/`test_downloads.py`)
прогнаны по разу: 5/6 чисто зелёные, 6-й (`test_smoke.py`) — предметный тест
(`assert_work_not_in_tab`) PASSED, единственное падение (TC-005, theme
SharedPreferences race) структурно доказано НЕ связано с этим фиксом
(traceback не заходит в `library_steps.py`) и заведено отдельным test_debt
`bugs/AT-BUG-086.md` (не расширяю scope, не маскирую заметкой). Полный
witness — секция «Верификация» выше. `python
scripts/validate_frontmatter.py` — `ошибок 0, предупреждений 0`. Lock снят.

**[fix-verifier @ 2026-08-20T04:07:00Z] Verified (D1, независимая
верификация).** Среда: начал с канонического `Start-Appium` (вывод
«Appium started and ready on :4723»), `Install-App` Success, устройство
`emulator-5554` живо весь ход. **Уточнение (критик-гейт этого же D1-батча,
2026-08-20, блокер Б2):** эта строка НЕ доказывает здоровье сессии —
`Start-Appium` (`scripts/tasks.ps1:372-389`) печатает «started and ready»
при ответе ЛЮБОГО сервера на :4723, включая резидентный (замерено:
единственный процесс на хосте, поднят задолго до этой верификации).
Деградация сессии критик-гейтом AT-BUG-075 этим же проходом НЕ исключена
для ЭТОГО прогона — формулировка ниже соответственно скорректирована.

Device-free: `Invoke-Pytest tests/test_library_tab_settle_unit.py
tests/test_rating_comment_collapse_settle_unit.py -q` →
`11 passed in 3.82s` (батч с AT-BUG-085, те же 5 проб этого бага). Это
единственный witness, реально исполняющий изменённое ТЕЛО
`_poll_tab_absent` (критик-гейт О1: живой прогон `test_tabs.py` ниже НЕ
вызывает `assert_work_not_in_tab`/`_poll_tab_absent` ни разу — покрывает
СОСЕДНЮЮ поверхность того же файла, не изменённый код; для будущей
верификации этого класса предпочтителен `test_downloads.py`/
`test_library_filters.py`, реально вызывающие починенную функцию, 12
call sites на двоих).

Живой: `Invoke-Pytest tests/test_tabs.py -q` (полный файл) → `1 failed,
13 passed in 842.69s`. Единственное падение
(`test_cold_start_deep_link_reuses_single_home_tab`, TC-135) — доказано
структурно НЕ связанным с ЭТИМ фиксом: `grep` по файлу подтвердил ноль
вызовов `assert_work_not_in_tab`/`_poll_tab_absent`/`has_work` в этом
тесте (traceback целиком в `app_steps.wait_tabs_persisted`, другая
подсистема) — это подтверждение НЕЗАВИСИМО перепроверено критик-гейтом и
верно. **Исправление (критик-гейт, блокер Б1):** исходная запись
списывала падение на «транзиентный флейк» по ОДНОМУ изолированному
повтору (`1 passed in 38.48s`) и не заводила тикет — критик перепрогнал
ИЗОЛИРОВАННО ДВАЖДЫ и получил `1 failed` оба раза (детерминированный
TimeoutError, не флейк). Заведён `bugs/AT-BUG-087.md` (причина не
разделена между реальной регрессией и деградацией Appium-сессии —
исключающий прогон на заведомо свежей сессии остаётся открытым пунктом
DoD того бага).

Порядок диффа на дереве прогона (критик-гейт О2): `library_steps.py` в
момент этого живого прогона нёс ОДНОВРЕМЕННО фикс этого бага И
параллельную in-flight работу `AT-BUG-075` (`open_in_background_via_
overlay`), `library_screen.py` нёс `long_press_work(duration_ms=)` того
же бага, `test_tabs.py` — его правки теста. Оба потока к моменту записи
УЖЕ приняты (`AT-BUG-075` закрыт критик-гейтом этим же проходом раньше
AT-BUG-083's D1) — witness не протухает, но называю явно по требованию
критика.

Итог: фикс `_poll_tab_absent`/`assert_work_not_in_tab` держится device-
free юнитом (реально исполняет изменённое тело) + живым 6-файловым
регрессом воркера (структурная несвязанность TC-135 подтверждена
независимо, сама красная проба заведена отдельно AT-BUG-087, статус
этого бага НЕ откатывается ею). `status: Fixed → Verified`, `known_issue`
уже `"false"`, lock снят.

**next_rules (fix-verifier, адресат test-designer):** `test_cases: []`
этого бага не годится под инфраструктурный carve-out (а) — `library_steps.py`
реально используется существующими TC (TC-036/116/117 в
`test_downloads.py`, TC-090/091-класс в `test_rating_listing.py`, плюс
call sites в `test_library_filters.py`/`test_library.py`/`test_rating.py`/
`test_smoke.py`) — прошу test-designer подтвердить/привязать актуальный
набор TC к `test_cases` этого бага, чтобы D3 still-repro/regression sweep
имел явный TC-уровневый якорь для этого класса (критик-гейт О3 указал
на висячий указатель этой записи в предыдущей редакции — исправлено
здесь).
