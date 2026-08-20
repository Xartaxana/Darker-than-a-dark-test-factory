---
id: AT-BUG-088
title: "Три settings-prefs Then-хелпера (assert_theme_mode_pref/assert_auto_apply_filter_pref/assert_font_size_step_pref) читали через голый adb.run_as — rc/stderr отбрасывались, отказ adb был неотличим от несовпадения значения (AT-BUG-055 класс, remnant после AT-BUG-086); пофикшено переводом _poll_settings_prefs на adb.run_as_file_or_raise, Verified"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Verified
found_in: "критик-гейт B4 AT-BUG-086, 2026-08-20"
fixed_in: "source_commit fdd3f72884105d1453448e0c9a7f2b109588b182, version_code 12 (state/app-under-test.yaml) — фикс в фреймворке (framework/steps/settings_steps.py, framework/tests/test_theme_mode_pref_settle_unit.py), сборка приложения не менялась"
last_seen_in: ""
test_cases: ["TC-005", "TC-181", "TC-050", "TC-051"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-20T11:25:29Z"
updated: "2026-08-20T11:25:29Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-088 — settings-prefs Then-хелперы БЫЛИ слепы к отказу adb (rc/stderr не проверялись, remnant класса AT-BUG-055); `_poll_settings_prefs` переведён на `adb.run_as_file_or_raise`, Verified

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/settings_steps.py::_poll_settings_prefs` (единая точка чтения
после фикса AT-BUG-086) и три вызывающих Then-хелпера: `assert_theme_mode_pref`,
`assert_auto_apply_filter_pref`, `assert_font_size_step_pref`.

## Обнаружено

Критик-гейт B4 AT-BUG-086 (2026-08-20): фикс AT-BUG-086 добавил settle-опрос
поверх `adb.run_as("cat shared_prefs/ao3_settings.xml")`, но чтение на тот
момент оставалось "голым" — rc/stderr отбрасывались, только stdout сверялся
подстрокой (класс закрыт фиксом этого тикета — см. ниже). Тот же
класс дыры, что `AT-BUG-055` уже нашёл и назвал для ЭТИХ ЖЕ ТРЁХ функций
(`assert_theme_mode_pref`/`assert_font_size_step_pref`, «кандидат для отдельного
B4-прохода, не блокер»), но НЕ завёл живым тикетом — только прозой внутри уже
`Verified`-артефакта. `AT-BUG-086` (уходящий в `Verified`) повторил ту же
прозаическую отсылку вместо тикета. Живого `Open`-артефакта под класс не было
(сверено поиском по `bugs/*.md`), поэтому remnant решено завести отдельно и
явно, а не третий раз оставить прозой в терминальном статусе.

Соседний оракул `app_steps._read_tabs_prefs_raw` уже переведён на
`adb.run_as_file_or_raise` фиксом `AT-BUG-055` — это референс-паттерн для
фикса здесь.

**Дополнительный аргумент чинить не откладывая бесконечно** (критик-гейт
AT-BUG-086, Б3): после AT-BUG-086 появилась ЕДИНАЯ точка чтения
(`_poll_settings_prefs`) — правка теперь локальна (один вызов внутри одной
функции, а не три места). **До фикса этого тикета** полл слегка ухудшал
диагностику: мёртвый adb-транспорт 3 секунды крутился в цикле и падал как
«theme_mode != SYSTEM в SharedPreferences: ''», то есть отказ adb выдавался за
дефект продукта под видом settle-таймаута. **После фикса** (см. «Критерий
готовности»/«Верификация» ниже) отказ adb/run-as всплывает `RuntimeError`
СРАЗУ, без прокручивания 3-секундного settle-бюджета (`:108-110`) —
диагностическая путаница снята.

## Критерий готовности (Fixed)

- [x] `_poll_settings_prefs` переведён на `adb.run_as_file_or_raise` (или
      эквивалент, различающий «rc!=0/пустой stdout от adb» и «файл прочитан,
      но искомое значение ещё не появилось») — по образцу
      `app_steps._read_tabs_prefs_raw` (референс AT-BUG-055).
- [x] Различающий unit-тест: adb-отказ (rc!=0/exception) даёт отдельное
      сообщение об ошибке, отличное от settle-таймаута по значению.
- [x] Живой регресс: TC-005/TC-181/TC-050/TC-051 (или минимум TC-005 +
      test_smoke.py) зелёный минимум 2 раза подряд после правки.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-20 | test_debt, сборка приложения не менялась — фикс целиком во фреймворке; state/app-under-test.yaml на момент прогона: source_commit `fdd3f72884105d1453448e0c9a7f2b109588b182` (== `fixed_in`), version_name `dev-local`, version_code 12, apk_sha256 `6bc924f9e3536615b1bcbb5f9533ea9dde0a38e6e31372e39e290c1b68b8b179` (уже установленная сборка, отдельная переустановка не требовалась) | `framework/tests/test_theme_mode_pref_settle_unit.py` (device-free юнит, DoD п.1) + живые `tests/test_smoke.py::test_theme_toggle_stable` (TC-005) и `tests/test_side_panel.py::test_font_size_increase_instant_and_persists` (TC-051) (device, Appium, DoD п.2). TC-181 (`assert_auto_apply_filter_pref`) и TC-050 живьём не гонялись этим ходом — та же граница, что test-maintainer явно назвал в записи Fixed (за пределами объявленного DoD-минимума TC-005 + один из TC-181/TC-050/TC-051); покрыты тем же device-free различающим тестом на общей точке чтения `_poll_settings_prefs`, сигнатура/логика хелперов не менялись | `Invoke-Pytest tests/test_theme_mode_pref_settle_unit.py -q` — дословно: `......` [100%], `AT-BUG-026 device-liveness guard: recoveries this session = 0/2`, `6 passed in 0.20s`, `PYTEST_EXIT=0`. `Invoke-Pytest tests/test_smoke.py::test_theme_toggle_stable tests/test_side_panel.py::test_font_size_increase_instant_and_persists -q` — дословно: `..` [100%], `AT-BUG-026 device-liveness guard: recoveries this session = 0/2`, `2 passed in 138.75s (0:02:18)`, `PYTEST_EXIT=0`. Оба прогона независимо исполнены этой сессией (не переприняты по отчёту test-maintainer), среда сверена канонической формой перед прогоном (`. tasks.ps1; Get-Device` → `DEVICE: emulator-5554`) | Verified |

## Обсуждение

**[координатор @ 2026-08-20T06:00:00Z]** Заведён по прямому предписанию
критик-гейта B4 AT-BUG-086 (блокер Б3): остаток класса AT-BUG-055 на тех же
трёх функциях был задекларирован только прозой внутри терминальных
артефактов (AT-BUG-055 Verified, затем AT-BUG-086 повторил) — без живого
Open-носителя находка теряется при каждой приёмке. Не чиню сам этим ходом
(правило 8а — лимит диспатчей прохода 4 близок к исчерпанию; B4-очередь
подберёт следующим проходом первым кандидатом).

**[test-maintainer @ 2026-08-20T08:11:23Z]** Fixed.

- `_poll_settings_prefs` (`framework/steps/settings_steps.py`) переведён с
  голого `adb.run_as("cat shared_prefs/ao3_settings.xml")` на
  `adb.run_as_file_or_raise(_SETTINGS_PREFS_PATH)` — тот же примитив чтения,
  что `app_steps._read_tabs_prefs_raw` уже применяет к ЭТОМУ ЖЕ файлу
  (`AT-BUG-055`), но НЕ буквально тот же паттерн полностью (критик-гейт
  round1, N2): референс `app_steps.wait_tabs_persisted` оборачивает чтение в
  `waits.wait_for`, который ЛОВИТ и РЕТРАИТ `RuntimeError`, выдавая его лишь
  на итоговом таймауте (`; last error: …`); `_poll_settings_prefs`
  пробрасывает `RuntimeError` СРАЗУ с первого чтения, без ретрая. Расхождение
  оправданное (в этом и смысл фикса — не проглатывать отказ адб полл-циклом),
  но остаточный риск: одиночный ТРАНЗИЕНТНЫЙ сбой adb в середине полла (не
  систематический, не гонка AM) теперь превращает прошедший бы TC-005/051/181
  прогон в жёсткий `ERROR` вместо тихого ретрая на следующей итерации —
  не наблюдалось на живых прогонах этого хода, но не исключено формально.
  Все три Then-хелпера
  (`assert_theme_mode_pref`/`assert_auto_apply_filter_pref`/
  `assert_font_size_step_pref`) идут через эту единую точку чтения — правка
  одной строки вызова закрывает класс сразу для всех троих. Отказ adb/run-as
  теперь всплывает `RuntimeError` СРАЗУ (на первом же чтении, без
  прокручивания 3-секундного settle-бюджета `SETTINGS_PREFS_POLL_TIMEOUT`),
  структурно отличным от `AssertionError` settle-таймаута по несовпадению
  значения — эти два разных отказа (инструмент vs продукт) больше не
  маскируют друг друга в тексте ошибки.
- Device-free различающий тест добавлен в существующий файл
  `framework/tests/test_theme_mode_pref_settle_unit.py`
  (`test_assert_theme_mode_pref_adb_failure_raises_distinct_runtime_error`):
  мокает `adb.run_as_file_or_raise`, чтобы бросить `RuntimeError` на первом
  чтении, и проверяет, что наружу приходит именно `RuntimeError` (НЕ
  `AssertionError`, текст НЕ содержит `"theme_mode !="`). Существующие три
  «поллит до совпадения» + один «settle-таймаут» теста того же файла
  переведены на новый мок `_fake_run_as_file_or_raise_sequence` (мокает
  `adb.run_as_file_or_raise` вместо старого `adb.run_as`) — красная проба
  `test_pre_fix_single_read_would_have_failed_on_recorded_race` оставлена
  как есть (она байтовая копия pre-fix кода AT-BUG-086, который вызывал
  именно `adb.run_as`, к текущей реализации `_poll_settings_prefs` отношения
  не имеет). Прогон `Invoke-Pytest tests/test_theme_mode_pref_settle_unit.py
  -q` — 6 passed.
- `python -m pytest scripts/tests -q` — 1704 passed, 1 skipped, без
  регрессий.
- Живой регресс (эмулятор `emulator-5554`, dev-local build version_code 12,
  source_commit `fdd3f728...`): `tests/test_smoke.py::test_theme_toggle_stable`
  (TC-005, читает `assert_theme_mode_pref`) +
  `tests/test_side_panel.py::test_font_size_increase_instant_and_persists`
  (TC-051, читает `assert_font_size_step_pref`) — 2 подряд прогона, оба
  `2 passed` (123.70s и 118.70s). `assert_auto_apply_filter_pref` (TC-181)
  живьём в этом ходе не гонялась (за пределами объявленного DoD-минимума
  TC-005 + один из TC-181/TC-050/TC-051), но покрыта тем же device-free
  различающим тестом выше и не тронута классово — рефакторинг задел только
  общую точку чтения `_poll_settings_prefs`, сигнатура и логика самого
  хелпера не менялись.

**Классовая полнота (D-0043, пункт 8 DoD):** сплошной grep `adb.run_as(` по
`framework/` не нашёл новых «голых» мест на КРИТИЧНОМ (assert-driving) пути
за пределами уже переведённых трёх хелперов и `app_steps._read_tabs_prefs_raw`
(AT-BUG-055). Оставшиеся вызовы `adb.run_as` в `framework/data/seed_db.py` —
1. `_db_exists()` (строка 36, `test -f ... && echo YES || echo NO`) —
   **пересмотрено критик-гейтом round1 (N3): НЕ того же класса.** У функции
   ноль продакшн-вызывающих (grep по `framework/`+`scripts/` даёт только её
   определение + докстринг-упоминания в `_schema_ready` + тесты), и её
   полярность отказа — fail-CLOSED, не fail-open: `"".endswith("YES")` →
   `False` на мёртвом транспорте, а `_schema_ready` (докстринг, строки 71-77)
   прямо называет это ПРАВИЛЬНОЙ полярностью. Честная диспозиция — мёртвый
   код, кандидат на удаление отдельным housekeeping-ходом, НЕ следующий
   B4-фикс класса AT-BUG-088/055 (маскирующий fail-open). Не чиню и не
   удаляю этим ходом (вне мандата) — снимаю прежнюю неточную рекомендацию.
2. Серия `adb.run_as(f"rm -f {_WAL} {_SHM}")`/`mkdir -p` cleanup-вызовов —
   fire-and-forget, ни один assert/oracle не зависит от их вывода, поэтому
   структурно НЕ тот же класс (нет риска «отказ инструмента маскируется под
   дефект продукта», раз результат никем не проверяется) — упомянуто для
   полноты сверки, кандидатом B4 не считаю.

**[критик-гейт @ 2026-08-20T11:35:00Z] Дополнение классовой полноты.**
Собственный сплошной поиск `adb.run_as(` нашёл ещё два места, не включённые
в перечисление выше: `settings_steps.py:433`/`:520` — оба несут позитивный
маркер (`OK`/`RDY`) и `2>&1`, т.е. fail-closed по протоколу AT-BUG-045/044,
структурно НЕ класс AT-BUG-055/088 (та же полярность, что `seed_db.py`
пункт 1 выше). Перечисление было неполным (упоминало только `seed_db.py`),
хотя существо негатива «новых голых мест на assert-driving пути нет» —
верно.

`next_rules`: если B4-проход захочет добить класс до конца, следующий
кандидат — `seed_db._db_exists()` (пункт 1 выше), по тому же референс-паттерну
`run_as_file_or_raise`; проверить перед этим, не станет ли она тогда
избыточной (`ensure_db_initialized` уже не полагается на неё).

**[fix-verifier @ 2026-08-20T11:25:29Z]** `status: Fixed → Verified` (D1).
`type: test_debt` — сборка приложения не требовалась (фикс целиком во
фреймворке, `state/app-under-test.yaml` не менялся с `found_in`,
`source_commit` совпадает с `fixed_in`). Независимо исполнены оба пункта
DoD этим ходом (не переприняты по отчёту test-maintainer):
1. `Invoke-Pytest tests/test_theme_mode_pref_settle_unit.py -q` — `6 passed
   in 0.20s`, `PYTEST_EXIT=0`.
2. Живой регресс `TC-005` + `TC-051` — `Invoke-Pytest
   tests/test_smoke.py::test_theme_toggle_stable
   tests/test_side_panel.py::test_font_size_increase_instant_and_persists
   -q` — `2 passed in 138.75s (0:02:18)`, `PYTEST_EXIT=0`.

Оба зелёные → критерий D1 закрыт, репро не повторилось. Полный дословный
вывод — таблица «Верификация» выше. `TC-181`/`TC-050` живьём не гонялись
(та же явно названная граница, что и в записи Fixed) — не блокер: покрыты
device-free различающим тестом на единой точке чтения, логика хелперов не
менялась после фикса.

Заголовок (`title`) и H1 переведены с хвоста «, Fixed» на «, Verified»
(класс CLASS-MECHANISM-STALE-TEXT-AFTER-STATUS-TRANSITION). **Критик-гейт
2026-08-20 (переход Fixed→Verified) поймал 8й экземпляр того же класса,
пропущенный этой репликой** — `## Обнаружено` несла настоящее время о
непочиненном состоянии («текущий полл слегка ухудшает...», «теперь 3 секунды
крутится», «выдаётся за дефект продукта»), прямо противоречащее содержимому
того же артефакта (`:108-110`, «теперь всплывает `RuntimeError` СРАЗУ»);
секции — не только title/H1 — исправлены координатором тем же ходом
(датированы/переведены в прошедшее время). `last_seen_in` также приведён к
задокументированной семантике (docs/templates/bug-report.md — «сборка, где
репро подтверждено», не список зелёных прогонов). `known_issue` уже был
`"false"` — сбрасывать не потребовалось.

`app-under-test/` не тронут. Дефектов-собратьев (D-0043) при верификации
не замечено сверх уже задокументированных в теле бага (`seed_db.py`,
пункты 1-2 «Классовой полноты» выше).

`lock` снят.
