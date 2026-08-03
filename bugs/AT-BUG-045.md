---
id: AT-BUG-045
title: "settings_steps.py::assert_ratings_present/assert_no_ratings/assert_rating_rows_empty — пустой stdout (в т.ч. отказ транспорта) неотличим от 'нет sqlite3 на образе', степень тихо пропускает проверку"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "critic-вход приёмки D1 AT-BUG-044 (attempt 2, 2026-08-03): найдено при поиске сиблингов класса 'решение о состоянии по одному stdout adb.run_as/shell с отброшенным returncode, где пустота = успех' по внутренней оси framework/core/adb.py <-> потребители"
fixed_in: "3805010"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-03T16:05:00Z"
updated: "2026-08-03T16:05:00Z"
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
