---
id: AT-BUG-045
title: "settings_steps.py::assert_ratings_present/assert_no_ratings/assert_rating_rows_empty — пустой stdout (в т.ч. отказ транспорта) неотличим от 'нет sqlite3 на образе', степень тихо пропускает проверку"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "critic-вход приёмки D1 AT-BUG-044 (attempt 2, 2026-08-03): найдено при поиске сиблингов класса 'решение о состоянии по одному stdout adb.run_as/shell с отброшенным returncode, где пустота = успех' по внутренней оси framework/core/adb.py <-> потребители"
fixed_in: "3805010,PLACEHOLDER_ATTEMPT2"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-03T16:05:00Z"
updated: "2026-08-03T16:41:24Z"
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

# AT-BUG-045 — тихая деградация Then-ассертов work_ratings на пустом stdout (settings_steps.py)

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`) — не
зависит от сборки приложения, поверхность целиком в
`framework/steps/settings_steps.py`.

## Суть долга

Три Then-хелпера читают `work_ratings` через `adb.run_as` + `sqlite3` и
намеренно деградируют к UI-слою на образах без бинаря sqlite3 — приём
задокументирован докстрингами:

- `assert_ratings_present` (`settings_steps.py:323-333`): `if "NOSQLITE" in
  out or out == "": return`.
- `assert_rating_rows_empty` (`:352-368`, через `read_rating_rows`): `if
  "NOSQLITE" in out: return` (пустой `out` без `NOSQLITE` тоже проходит
  дальше в `assert out == ""`, что для этого хелпера СЛУЧАЙНО безопасно —
  пустая строка и есть ожидаемый Then).
- `assert_no_ratings` (`:371-379`): `if "NOSQLITE" in out or out == "":
  return`.

Проблема (найдена критиком при приёмке `AT-BUG-044`, тот же класс, что
там чинился): маркер деградации — `"NOSQLITE" in out or out == ""` — не
различает ДВА разных состояния:
1. Образ действительно без бинаря `sqlite3` (`2>/dev/null || echo
   NOSQLITE` сработал, задуманная деградация) — валидный no-op.
2. **Отказ ТРАНСПОРТА** (устройство недоступно/adb ошибся) — `adb.run_as`
   отбрасывает returncode (тот же механизм, что был fail-open в
   `AT-BUG-044` до фикса), `2>/dev/null` в этой команде подавляет ЛЮБОЙ
   stderr remote-стороны, стало быть тоже даёт пустой `out` — и хелпер
   МОЛЧА пропускает проверку вместо честного FAIL/ERROR.

Для `assert_ratings_present`/`assert_no_ratings` это означает: при
транзиентном отказе транспорта Then про состояние БД становится
неотличим true-skip от true-pass — тест может остаться зелёным, даже
если утверждение о БД никогда не проверялось. Не регрессия конкретного
диффа (код предшествует `AT-BUG-044`), намеренная UI-деградация
задумывалась только для случая «нет бинаря», транспортный кейс не был
рассмотрен явно.

## Критерий готовности (Fixed)

- [x] Различить два случая машинно: маркер `NOSQLITE` (реальная
  деградация "нет sqlite3") — отдельно от пустого `out` БЕЗ маркера
  (транспорт/иная ошибка, замаскированная `2>/dev/null`). Кандидат —
  убрать `2>/dev/null` из remote-команды (как в `_schema_ready`,
  `AT-BUG-044`) и завести отдельный позитивный маркер готовности, либо
  явно поднять исключение/ERROR на неопознанном пустом выводе вместо
  тихого `return`.
- [x] Красная проба: воспроизвести транспортный отказ (например,
  недоступное устройство) и показать, что ДО фикса хелпер молча
  пропускает Then, ПОСЛЕ — либо честно проверяет, либо явно ERROR (не
  ложный PASS).
- [x] Потребители (`test_settings.py`, `test_smoke.py`,
  `test_backup_restore.py` — TC-018/019/020 и смежные) остаются
  зелёными на устройстве без деградации сценария «нет sqlite3».
- [x] arch_check/validate_frontmatter — 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-03 | 1.10 (11), сборка приложения не тронута (test_debt в обвязке, якорь версии `state/app-under-test.yaml`) | Device-free branch matrix (мок `adb.run_as`, 11 веток x 3 функции: NOSQLITE/успех-непусто/успех-ноль/успех-пустые-строки/транспорт-отказ на каждой из `assert_ratings_present`, `assert_no_ratings`, `assert_rating_rows_empty`); живой зонд на `emulator-5554` (реальный успех) + `emulator-9999` (реальный отказ транспорта, тот же приём, что критик AT-BUG-044 attempt 2) через настоящий `adb.run_as`; консьюмеры: `tests/test_settings.py::test_clear_all_ratings_shows_confirmation_dialog` (TC-018), `test_cancel_clear_all_dialog_keeps_data` (TC-019), `test_clear_all_ratings_badge_resets_after_reload` (TC-020 Then б), `tests/test_smoke.py::test_clear_all_ratings`, `tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data` — 3 прогона подряд; `arch_check.py`/`validate_frontmatter.py`; `git status --porcelain -- app-under-test/` | device-free: все 11 веток совпали с ожиданием (см. Обсуждение — дословный вывод); живой зонд: emulator-5554 raw out `'1\nOK\n'`; emulator-9999 raw stdout `''`, все три хелпера подняли `RuntimeError` вместо тихого `return` (ДО фикса тот же вход по старому предикату `"NOSQLITE" in out or out == ""` дал бы `True` — проверено на ЭТОМ ЖЕ живом выводе); консьюмеры: run1 `5 passed in 260.53s`, run2 `5 passed in 330.59s`, run3 `5 passed in 252.52s`, все три `PYTEST_EXIT=0`; `arch_check: ошибок 0, предупреждений 0`; `validate_frontmatter: ошибок 0, предупреждений 0`; `git status --porcelain -- app-under-test/` — пустой вывод | Fixed (test-maintainer, до fix-verifier/critic-входа по правилу D-0037/critic-класс — ядровая логика Then-хелперов, критик-вход ОБЯЗАТЕЛЕН per CLAUDE.md правило 3) |
| 2026-08-03 | 1.10 (11), сборка приложения не тронута (attempt 2 — правка целиком в `framework/steps/settings_steps.py` + новый device-free юнит `framework/tests/test_settings_ratings_fail_closed_unit.py`, якорь версии не менялся) | Новый device-free юнит: 22 параметризованных ветки `test_branch` (NOSQLITE/count+OK/marker-only-OK/rows+OK/CRLF/**реальная sqlite3-ошибка БЕЗ маркера** — блокер 1/транспорт-пусто-или-мусор) + 1 регресс-замок `test_remote_command_uses_command_v_gate` (текст remote-команды содержит `command -v sqlite3`, хвост не оканчивается безусловным `\|\| echo NOSQLITE`) — все на РЕАЛЬНОМ коде трёх хелперов, мок только `framework.core.adb.run_as`; прежние device-free наборы (`test_seed_db_schema_race_unit.py`) перепрогнаны рядом; живой зонд на `emulator-5554` (`Get-Device` → `DEVICE: emulator-5554`): (а) успех — реальный SELECT COUNT через новую remote-команду; (б) **реальная sqlite3-ошибка при наличии бинаря** (SELECT из заведомо несуществующей таблицы `nonexistent_table_at_bug_045`) — прямое воспроизведение блокера 1; (в) сквозной вызов настоящего `settings_steps.assert_ratings_present()` на живой БД; живой консьюмер `tests/test_settings.py::test_clear_all_ratings_shows_confirmation_dialog` (TC-018); `arch_check.py`/`validate_frontmatter.py`; `git status --porcelain -- app-under-test/` | device-free: `28 passed in 1.93s`, `PYTEST_EXIT=0` (22 новых веток + 1 регресс-замок + 5 прежних `test_seed_db_schema_race_unit.py` — все зелёные, старый набор не сломан); живой зонд: (а) raw out `'0\nOK'` (SELECT реально исполнился, `work_ratings` сейчас пуста на этом сиде); (б) raw out `'Error: in prepare, no such table: nonexistent_table_at_bug_045'` — **без какого-либо маркера** (ни `NOSQLITE`, ни `OK`) — при бинаре sqlite3, реально присутствующем на образе (сверено live-зондом (а) на этом же прогоне) — на этом входе новый код поднял `RuntimeError` (не тихий `return`); контрольная реконструкция СТАРОЙ (attempt 1) remote-команды на этом же тексте ошибки: `... 2>&1 && echo OK \|\| echo NOSQLITE` дала бы хвост `NOSQLITE` (ловит ЛЮБОЙ ненулевой exit sqlite3) → все три хелпера attempt 1 молча сделали бы `return` на РЕАЛЬНОЙ ошибке БД — блокер 1 воспроизведён и закрыт на одном и том же живом выводе; (в) `assert_ratings_present()` дал честный `AssertionError` (count='0', реальные данные, не замаскировано новым `RuntimeError`); консьюмер TC-018: `1 passed in 38.46s`, `PYTEST_EXIT=0`; `arch_check: ошибок 0, предупреждений 0`; `validate_frontmatter: ошибок 0, предупреждений 0` (после исправления формата `lock` на UTC `Z`); `git status --porcelain -- app-under-test/` — пустой вывод | Fixed (test-maintainer attempt 2, до critic-входа — обязателен per CLAUDE.md правило 3, тот же класс диффа, что attempt 1) |

## Обсуждение

**2026-08-03T14:10:00Z — координатор (Sonnet, /qa-loop 10), заведение по
находке critic-входа D1 AT-BUG-044 attempt 2:** критик отметил находку как
non-blocking для AT-BUG-044 (не регрессия того диффа) и явно попросил
завести отдельным пунктом — вынесено из notes журнала в машиночитаемый
`bugs/` по правилу 9 CLAUDE.md («чини класс, а не экземпляр»; прецедент
ESC-004→AT-BUG-020, ESC-016→AT-BUG-043: прозаическая находка без
артефакта не видна B4-сканеру). Severity minor: транзиентный отказ
транспорта — тот же класс редкости, что был у `AT-BUG-044` до фикса, не
блокирует основной поток, но даёт тот же риск ложного зелёного Then.

**2026-08-03T16:05:00Z — test-maintainer, фикс (B4):** три Then-хелпера
(`framework/steps/settings_steps.py:323-379` до правки —
`assert_ratings_present`, `read_rating_rows`/`assert_rating_rows_empty`,
`assert_no_ratings`) переписаны на тот же fail-closed приём, что
`seed_db._schema_ready()` (`AT-BUG-044`): remote-команда заменена с
`... 2>/dev/null || echo NOSQLITE` на `... 2>&1 && echo OK || echo
NOSQLITE` — `2>&1` больше не подавляет stderr remote-стороны (ошибка
попадает в перехватываемый `stdout`), а суффикс `OK` печатается ТОЛЬКО
если сам SELECT реально исполнился (транспорт жив, шелл дошёл до конца
команды). Три исхода теперь различимы машинно:
1. `NOSQLITE` в выводе — легитимная деградация (реально нет бинаря
   sqlite3, либо запрос не прошёл) — сохранённое поведение, skip к
   UI-фолбэку вызывающего теста.
2. Суффикс `OK` — SELECT реально отработал, тело ДО маркера — реальные
   данные (COUNT либо сырые строки), парсим и ассертим как раньше.
3. Ни то ни другое (в т.ч. пустой `out`, где раньше это трактовалось
   как «нет sqlite3») — новый явный `RuntimeError` с сырым выводом в
   тексте — честный ERROR вместо тихого `return`.

Добавлен общий хелпер `_no_sqlite_marker_missing_error(step, out)` —
единая формулировка текста ошибки для всех трёх функций (без копипасты
трёх независимых сообщений). Константа `_RATINGS_DB_REL =
"databases/ao3_ratings.db"` вынесена на уровень модуля — та же строка,
что `seed_db._DB_REL` (не импортируется напрямую — приватная граница
модуля `seed_db`, дублирование литерала оставлено как было в файле).

`read_rating_rows()` теперь тоже несёт маркер (`OK`/`NOSQLITE`) поверх
сырых строк — единственный потребитель, `assert_rating_rows_empty`,
распаковывает его тем же приёмом; внешних потребителей у
`read_rating_rows()` нет (сверено `Grep` по репозиторию — только вызов
внутри самого `settings_steps.py`), контракт функции менять было
безопасно.

**Device-free branch matrix** (мок `framework.core.adb.run_as`, скрипт
запускался вне репозитория из scratchpad, не коммитится) — 11 веток,
дословный вывод:
```
assert_ratings_present/NOSQLITE: PASS (no exception)
assert_no_ratings/NOSQLITE: PASS (no exception)
assert_rating_rows_empty/NOSQLITE: PASS (no exception)
assert_ratings_present/count=3 (expect PASS): PASS (no exception)
assert_ratings_present/count=0 (expect AssertionError): AssertionError -> ожидали >0 рейтингов в БД (диалог ещё не подтверждён), получили: '0'
assert_no_ratings/count=0 (expect PASS): PASS (no exception)
assert_no_ratings/count=5 (expect AssertionError): AssertionError -> ожидали 0 рейтингов, в БД: '5'
assert_rating_rows_empty/empty+OK (expect PASS): PASS (no exception)
assert_rating_rows_empty/rows+OK (expect AssertionError): AssertionError -> ожидали пустую work_ratings после Clear all ratings, в БД строки: '12345|SAVE|1690000000'
assert_ratings_present/empty-out (expect RuntimeError): RuntimeError -> assert_ratings_present: не удалось прочитать work_ratings через adb (ни маркер NOSQLITE, ни OK не найдены в выводе — похоже на отказ транспорта, а не на намеренную деградацию 'нет sqlite3'), сырой вывод: ''
assert_no_ratings/empty-out (expect RuntimeError): RuntimeError -> assert_no_ratings: ...(тот же текст)...
assert_rating_rows_empty/empty-out (expect RuntimeError): RuntimeError -> assert_rating_rows_empty: ...(тот же текст)...
```
Все 11 исходов совпали с ожиданием (в т.ч. подтверждено, что реальные
бизнес-провалы — count=0/5 не в ту сторону, непустые строки после Clear
— по-прежнему честный `AssertionError`, не проглочены новым
`RuntimeError`-веткой).

**Живая красная/зелёная проба** (реальный код-путь `adb.run_as` ->
`adb.shell` -> `adb._run().stdout`, НЕ мок; тот же приём, что критик
использовал в `AT-BUG-044` attempt 2 — переключение
`settings.DEVICE_NAME` на несуществующий `emulator-9999`):
- `emulator-5554` (реальное устройство, `Get-Device` -> `DEVICE:
  emulator-5554` перед прогоном): COUNT-проба вернула `'1\nOK\n'` —
  живой sanity, что новая команда синтаксически валидна и маркер `OK`
  реально приходит с устройства.
- `emulator-9999` (несуществующее устройство, тот же путь adb.exe):
  `adb.run_as(...)` вернул `''` (пустой stdout, returncode/stderr
  отброшены `adb._run()`, как и задокументировано в
  `seed_db._schema_ready()`). На ЭТОМ живом входе:
  - `assert_ratings_present()` -> `RuntimeError: assert_ratings_present:
    не удалось прочитать work_ratings через adb (ни маркер NOSQLITE, ни
    OK не найдены в выводе — похоже на отказ транспорта...)`
  - `assert_no_ratings()` -> тот же класс `RuntimeError`
  - `assert_rating_rows_empty()` -> тот же класс `RuntimeError`
  - Контрольная проверка СТАРОГО предиката на ЭТОМ ЖЕ живом выводе:
    `("NOSQLITE" in out) or (out.strip() == "")` -> `True` — то есть ДО
    фикса все три хелпера молча сделали бы `return` (ложный PASS Then
    про состояние БД) на этом же самом отказе транспорта. Красная проба
    ДО/ПОСЛЕ выполнена на одном и том же живом захваченном выводе, не
    на реконструкции.

**Потребители** (`framework/tests/test_settings.py::
test_clear_all_ratings_shows_confirmation_dialog` [TC-018],
`test_cancel_clear_all_dialog_keeps_data` [TC-019],
`test_clear_all_ratings_badge_resets_after_reload` [TC-020, Then б —
единственный потребитель `assert_rating_rows_empty`],
`framework/tests/test_smoke.py::test_clear_all_ratings`,
`framework/tests/test_backup_restore.py::
test_backup_clear_restore_returns_original_data`) — 3 прогона подряд
канонической `Invoke-Pytest`, все три `5 passed`/`PYTEST_EXIT=0`:
run1 `5 passed in 260.53s (0:04:20)`, run2 `5 passed in 330.59s
(0:05:30)`, run3 `5 passed in 252.52s (0:04:12)`. Ни разу деградация
«нет sqlite3» не сработала на этих прогонах (образ `emulator-5554`
реально имеет бинарь sqlite3 — сверено живым зондом выше, COUNT-проба
дошла до реальных данных, суффикс `OK`) — легитимная UI-деградация
осталась НЕЗАТРОНУТОЙ (парк без sqlite3-образов у нас сейчас нет,
поэтому явный прогон именно этой ветки на потребителях недоступен;
контракт `NOSQLITE`-ветки, тем не менее, покрыт device-free-пробой
выше и не изменён кодом).

`python scripts/arch_check.py` -> `arch_check: ошибок 0, предупреждений
0`. `python scripts/validate_frontmatter.py` -> `validate_frontmatter:
ошибок 0, предупреждений 0`. `git status --porcelain --
app-under-test/` — пустой вывод (сверено до и после правки; дифф
целиком в `framework/steps/settings_steps.py`).

Новых блокеров/долгов в ходе работы не найдено — правка не вскрыла
отсутствующих фикстур/replay-записей/непокрытых системных диалогов.

**Требуется critic-вход перед приёмкой (CLAUDE.md правило 3):** этот
дифф — Sonnet-класс результат (test-maintainer), правит ядровую логику
Then-хелперов, используемых несколькими активными тест-кейсами
(TC-018/019/020 и смежные) — приёмка легальна ТОЛЬКО через вход
критика (льгота "critic: skipped" здесь недоступна per матрице «Роль ≠
ярус»). Статус оставлен `Fixed` для передачи в очередь критика/
fix-verifier; при отклонении — вернуть в `Open` с `rejected`-событием
маршрутизации.

`fixed_in: 3805010` (коммит `fix(settings_steps): AT-BUG-045 -
fail-closed work_ratings Then-helpers`) — тот же приём, что
`AT-BUG-044`: плейсхолдер заменён на фактический хэш точечной правкой
сразу после `git commit` кодового диффа.

**2026-08-03T16:41:00Z — test-maintainer, attempt 2 (critic-вход rework,
2 блокера продиктованы критиком живьём):**

**Блокер 1 (`|| echo NOSQLITE` ловит ЛЮБОЙ ненулевой exit sqlite3):**
attempt 1 закрыл ТОЛЬКО отказ транспорта — remote-команда была
`sqlite3 <db> "<SQL>" 2>&1 && echo OK || echo NOSQLITE`. Живой зонд
критика на `emulator-5554` (бинарь `sqlite3` РЕАЛЬНО присутствует,
`/system/bin/sqlite3`) показал: SELECT из несуществующей таблицы дал
`'Error: in prepare, no such table: ...\nNOSQLITE\n'` — shell-семантика
`||` не различает «команды нет» от «команда упала с ошибкой», поэтому
ЛЮБАЯ ошибка sqlite3 (нет таблицы / БД заблокирована / файл БД
отсутствует) тоже печатала `NOSQLITE`, и все три хелпера молча делали
`return` — ложный зелёный Then ровно на состоянии гонки AT-BUG-044.

Фикс (продиктован критиком, применён как есть): маркер `NOSQLITE`
вынесен в ОТДЕЛЬНЫЙ гейт ПЕРЕД самим SELECT —

```
sh -c 'command -v sqlite3 >/dev/null 2>&1 || { echo NOSQLITE; exit 0; };
sqlite3 <db> "<SQL>" 2>&1 && echo OK'
```

— `NOSQLITE` теперь печатается ТОЛЬКО когда бинаря реально нет
(`command -v` возвращает ненулевой exit ДО того, как SELECT вообще
запущен). Любая ошибка самого SELECT остаётся сырым текстом БЕЗ какого-
либо маркера и попадает в уже существующую ветку `_no_sqlite_marker_
missing_error` → `RuntimeError` (эта половина стояла с attempt 1,
переиспользована как есть). Применено ко всем трём remote-командам
(`assert_ratings_present`, `read_rating_rows`, `assert_no_ratings`) —
`framework/steps/settings_steps.py:358-360, 387-391, 444-446`.

Живой зонд attempt 2 на ТОМ ЖЕ входе, что нашёл блокер: `SELECT COUNT(*)
FROM nonexistent_table_at_bug_045` (таблицы такой нет, бинарь sqlite3
присутствует — сверено параллельным зондом успеха на этом же прогоне,
raw out `'0\nOK'`) → raw out ПОСЛЕ фикса: `'Error: in prepare, no such
table: nonexistent_table_at_bug_045'` — БЕЗ `NOSQLITE`, БЕЗ `OK`. Ручная
реконструкция СТАРОЙ (attempt 1) remote-команды на этом же тексте
ошибки — `... 2>&1 && echo OK || echo NOSQLITE` дала бы хвост
`NOSQLITE` (echo безусловно выполняется в `||`-ветке при любом
ненулевом exit `sqlite3`) → все три хелпера attempt 1 молча сделали бы
`return`. На новом входе `assert_ratings_present()`/`assert_no_ratings`/
`assert_rating_rows_empty()` не находят ни `NOSQLITE`, ни `OK` →
`RuntimeError`. Блокер воспроизведён и закрыт на одном и том же живом
выводе (до/после на одном входе, не на реконструкции с нуля).

**Блокер 2 (нет коммитнутого регресс-гейта):** матрица attempt 1 жила
только в scratchpad критика. Заведён `framework/tests/
test_settings_ratings_fail_closed_unit.py` — device-free, мокает
`framework.core.adb.run_as` НА УРОВНЕ МОДУЛЯ (не хелперы), 22
параметризованных ветки `test_branch` над РЕАЛЬНЫМ кодом трёх функций:
`NOSQLITE`/успех-с-данными (count 3, 0)/маркер-OK-без-тела (пустая
таблица)/непустые-строки-после-Clear/CRLF/**реальная sqlite3-ошибка без
маркера** (ключевая регресс-ветка блокера 1 — `sqlite-error-no-marker`
x3 функции + `sqlite-locked-no-marker`)/пустой транспорт/мусорный
транспорт/adb error-текст без маркера — плюс отдельный регресс-замок
`test_remote_command_uses_command_v_gate`, дословно проверяющий, что
текст remote-команды содержит `command -v sqlite3` и НЕ оканчивается
безусловным `|| echo NOSQLITE`. Основа — проба критика
(`scratchpad/probe/test_critic_matrix.py`), ожидания веток `*-sqlite-
error-no-marker`/`db locked`/`no such table` инвертированы под новый
fail-closed контракт (attempt 1 ожидал `pass`/skip на этих входах —
именно это и было блокером 1; attempt 2 контракт ожидает `runtime`).

**Device-free прогон:**
```
tests/test_settings_ratings_fail_closed_unit.py — 22 ветки test_branch + test_remote_command_uses_command_v_gate — все PASSED
tests/test_seed_db_schema_race_unit.py — 5 тестов — все PASSED (не сломаны)
28 passed in 1.93s, PYTEST_EXIT=0
```

**Живой зонд (реальный `adb.run_as`, `emulator-5554`, `Get-Device` →
`DEVICE: emulator-5554` перед прогоном):**
- успех: raw out `'0\nOK'` (SELECT реально исполнился; `work_ratings`
  сейчас пуста на этом сиде устройства).
- реальная sqlite3-ошибка (SELECT из несуществующей таблицы, бинарь
  ЕСТЬ): raw out `'Error: in prepare, no such table:
  nonexistent_table_at_bug_045'`, без маркера → `RuntimeError` (см.
  разбор блокера 1 выше).
- сквозной вызов настоящего `assert_ratings_present()`: `AssertionError:
  ожидали >0 рейтингов в БД (диалог ещё не подтверждён), получили: '0'`
  — честный бизнес-провал на реальных данных, НЕ замаскирован новым
  `RuntimeError`-путём.
- Отсутствие бинаря sqlite3 на живом устройстве НЕ воспроизведено (этот
  образ реально несёт `/system/bin/sqlite3` — сверено выше) — покрыто
  device-free веткой `nosqlite` (3 функции), отмечено явно per DoD п.1.

**Живой консьюмер:** `tests/test_settings.py::
test_clear_all_ratings_shows_confirmation_dialog` (TC-018) — canonical
`Invoke-Pytest`, `1 passed in 38.46s`, `PYTEST_EXIT=0`.

`python scripts/arch_check.py` → `arch_check: ошибок 0, предупреждений
0`. `python scripts/validate_frontmatter.py` → после первой правки
`lock` в non-UTC формате (`+02:00`) поймана валидатором
(`не соответствует ^$|^wip$|^...Z?$`) — исправлено на UTC `Z`
(`test-maintainer:2026-08-03T16:41:24Z`), повторный прогон →
`validate_frontmatter: ошибок 0, предупреждений 0`. `git status
--porcelain -- app-under-test/` — пустой вывод (сверено до и после
правки).

Новых блокеров/долгов в ходе attempt 2 не найдено.

**Non-blocking (заодно):** первая строка докстринга `read_rating_rows`
исправлена — «возвращает сырой вывод SELECT» → «вывод с маркером
OK/NOSQLITE» (`framework/steps/settings_steps.py:387-388`).

Статус остаётся `Fixed`, лок снят — передача в очередь критика/
fix-verifier (attempt 2).

`fixed_in` (frontmatter) обновлён на список из двух коммитов —
`3805010` (attempt 1, транспортный фикс) + плейсхолдер attempt 2,
который будет заменён фактическим хэшем точечной правкой сразу после
`git commit` этого диффа (тот же приём, что и раньше).

## Чек-лист качества (заводящий проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не пересекается с
  `AT-BUG-044` (та же ПОВЕРХНОСТЬ класса, но другой файл/другие функции;
  `AT-BUG-044` про гейт готовности БД в `seed_db.py`, этот — про Then-ассерты
  в `settings_steps.py`; фикс `AT-BUG-044` этот файл не трогал)
- [x] Severity обоснована влиянием: minor — транзиент, редкий, не блокирует
  основной поток, но маскирует реальный сбой Then под тихий skip
- [x] Приложены материалы: находка critic-входа D1 AT-BUG-044 attempt 2
  (код-трассировка трёх функций, класс назван явно)
- [x] Нет изменений кода приложения
