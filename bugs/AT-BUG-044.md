---
id: AT-BUG-044
title: "data/seed_db.py::ensure_db_initialized ждёт появления ФАЙЛА БД, а не схемы — окно 'no such table: work_ratings' при сидинге сразу после pm clear"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "critic-вход приёмки D1 AT-BUG-042 + два независимых воспроизведения в D1-прогонах fix-verifier (AT-BUG-042 setup-фейл, AT-BUG-039 раунд 2 TC-127 ERROR), 2026-08-03; framework env, сборка 1.10 (versionCode 11)"
fixed_in: "PENDING_COMMIT"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-03T13:55:00Z"
updated: "2026-08-03T13:55:00Z"
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

# AT-BUG-044 — гонка инициализации схемы БД в seed_db.ensure_db_initialized

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`) — не
зависит от сборки приложения, фикс целиком в `framework/data/seed_db.py`.

## Суть долга

`framework/data/seed_db.py:35-65` (`ensure_db_initialized`): после
`pm clear` функция ждёт ПОЯВЛЕНИЯ ФАЙЛА БД (`test -f`), а не появления
СХЕМЫ в нём, и сразу делает `force_stop`. Room создаёт файл БД раньше, чем
прогоняет миграции/создание таблиц — есть окно, в котором `_pull_baseline`
снимает файл БД без таблиц, и последующий `_insert_rows` падает
`sqlite3.OperationalError: no such table: work_ratings`.

Диагноз — critic-вход приёмки D1 `AT-BUG-042` (2026-08-03, код-трассировка);
подтверждён двумя НЕЗАВИСИМЫМИ живыми воспроизведениями того же прохода:
- fix-verifier D1 `AT-BUG-042`: transient-фейл «пустая `work_ratings` на
  пересеянной БД» в setup (отбракован как env, тест прошёл изолированно);
- fix-verifier D1 `AT-BUG-039`, раунд 2: `TC-127` ERROR
  `sqlite3.OperationalError: no such table: work_ratings` в seed-фикстуре.

Критик также прогнал Grep с позитивным контролем: сигнатура «no such table»
нигде в `bugs/` не была заведена — класс жил незаписанным. Структурно дефект
ПРОТИВОПОЛОЖЕН механизму `AT-BUG-042`/`BUG-022` (тот СОЗДАЁТ строку, этот
роняет отсутствующую таблицу) — не дубликат.

## Критерий готовности (Fixed)

- [x] `ensure_db_initialized` ждёт готовности СХЕМЫ (`sqlite3 <db> "SELECT 1
  FROM work_ratings LIMIT 0" 2>&1` через `adb run-as`, новая `_schema_ready()`
  в `framework/data/seed_db.py`), а не существования файла.
- [x] Красная проба: воспроизведено окно ДО фикса (форсированный снимок
  сразу после появления файла) и устранено ПОСЛЕ.
- [x] Существующие потребители seed-фикстур зелёные (replay-тест TC-141 с
  `loved_work_seeded` — 3/3 подряд).
- [x] arch_check/validate_frontmatter — 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-03 | 1.10 (11) | device-free: 14 юнит-проб (framework/tests/test_seed_db_schema_race_unit.py x2, test_subprocess_timeout_unit.py x8, test_seed_null_wordcount_unit.py x2, test_seed_filter_profiles_unit.py x2); live: on-device tight-loop red/green race repro (6/6 red hits "no such table: work_ratings" на файловом гейте, 0/6 на гейте по схеме); replay TC-141 (`loved_work_seeded`) x3 | 14 passed device-free (PYTEST_EXIT=0); live red 6/6, live green 0/6 fails; TC-141 3/3 PASSED | Fixed (test-maintainer, до fix-verifier/critic-входа по правилу D-0037/critic-класс) |

## Обсуждение

**2026-08-03T10:46:00Z — полный Lead (Fable), заведение (разбор очереди
Lead):** предложено критиком при приёмке `AT-BUG-042` (non-blocking находка,
решение оставлено координатору), эскалировано в заведение после второго
живого воспроизведения в том же проходе (D1 `AT-BUG-039` раунд 2). Severity
minor: сбой транзиентный (retry/изолированный перезапуск проходит), уводит
триаж в env-шум, но не блокирует очередь так, как `AT-BUG-043` (портовая
гонка). Диспатч — B4 штатным проходом, ПОСЛЕ `AT-BUG-043` (лексикографический
порядок правила это и так обеспечивает).

**2026-08-03T13:55:00Z — test-maintainer, фикс (B4):** гейт
`ensure_db_initialized` (`framework/data/seed_db.py`) заменён с
`_db_exists()` (`test -f`, только файл) на новую `_schema_ready()` —
`sqlite3 {databases/ao3_ratings.db} 'SELECT 1 FROM work_ratings LIMIT 0'
2>&1` через `adb run-as`. `sqlite3` CLI подтверждён живой сверкой на образе
(`adb shell which sqlite3` → `/system/bin/sqlite3` 3.39.2, emulator-5554).
Важный нюанс, найденный при реализации: `adb.run_as`/`adb.shell` возвращают
ТОЛЬКО `stdout` (`adb._run()`) — `adb shell` форвардит remote stdout/stderr в
РАЗНЫЕ локальные потоки, а sqlite3 CLI пишет ошибки в stderr; без `2>&1`
ВНУТРИ remote-команды `run_as()` видел пустую строку что при успехе, что при
ошибке (ложный always-ready) — обнаружено и исправлено ДО зелёного прогона,
живой сверкой (пустой вывод при ошибке без редиректа, непустой текст ошибки
с редиректом).

Красная/зелёная живая проба (emulator-5554, on-device tight-loop —
host-driven поллинг через adb не годится, окно уже сетевой задержки
round-trip'а): `pm clear` + `am start` (без `-W`, чтобы не ждать полной
прорисовки) + on-device цикл `while [ ! -f databases/ao3_ratings.db ]; do
:; done; sqlite3 ... 'SELECT 1 FROM work_ratings LIMIT 0' 2>&1` — 6/6
прогонов дали `Error: in prepare, no such table: work_ratings` СРАЗУ по
появлении файла (~330-350k итераций пустого цикла, т.е. окно короче network
round-trip, но не короче on-device syscall-цикла) — это и есть форсированный
снимок «сразу после появления файла», воспроизводящий диагноз буквально.
Тот же цикл с условием `sqlite3 ... 2>&1` вместо `test -f` (эквивалент
нового `_schema_ready`) — 0/6 попаданий, ~240-260 итераций КАЖДАЯ из которых
дороже (полный fork/exec sqlite3), т.е. схема готова вскоре после файла, но
гейт по файлу успевает соврать раньше. Дополнено device-free
детерминированной пробой `framework/tests/test_seed_db_schema_race_unit.py`
(тот же механизм на одном таймлайне, воспроизводимо без флейка тайминга на
каждом прогоне) — обе новые тестовые функции + 2 переписанных монки-патча в
`framework/tests/test_subprocess_timeout_unit.py` (гейт `_db_exists` ->
`_schema_ready` в фейках) зелёные, 14/14 device-free юнит-проб PYTEST_EXIT=0.

Потребитель seed-фикстур (`loved_work_seeded`) — replay `TC-141`
(`tests/test_rating.py::test_edit_tag_on_already_saved_work_via_panel_does_not_click_kudos`)
— 3/3 подряд PASSED (Invoke-Pytest, канонической формой). `arch_check.py` и
`validate_frontmatter.py` — 0/0 ошибок. `git status --porcelain --
app-under-test/` — пусто (проверено до и после фикса).

Владение fixed_in обновится в этом же ходе на реальный хэш коммита. Правка
ограничена `framework/data/seed_db.py` + двумя тестовыми файлами — сама
`_db_exists()` оставлена как отдельный примитив (диагностика/будущие
вызовы), просто больше не используется как гейт готовности.

## Чек-лист качества (заводящий проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не пересекается с
  AT-BUG-043 (bind-гонка порта 8080, другой механизм), AT-BUG-042/BUG-022
  (структурно противоположный эффект), AT-BUG-020 (детерминированный фейл
  конкретного узла TC-009, не seed-окно)
- [x] Severity обоснована влиянием: minor — транзиент, чинится retry,
  но даёт ложный env-шум в триаже
- [x] Приложены материалы: код-трассировка критика (приёмка AT-BUG-042),
  два независимых живых воспроизведения (D1-прогоны 2026-08-03)
- [x] Нет изменений кода приложения
