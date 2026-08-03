---
id: AT-BUG-044
title: "data/seed_db.py::ensure_db_initialized ждёт появления ФАЙЛА БД, а не схемы — окно 'no such table: work_ratings' при сидинге сразу после pm clear"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "critic-вход приёмки D1 AT-BUG-042 + два независимых воспроизведения в D1-прогонах fix-verifier (AT-BUG-042 setup-фейл, AT-BUG-039 раунд 2 TC-127 ERROR), 2026-08-03; framework env, сборка 1.10 (versionCode 11)"
fixed_in: "PENDING_COMMIT_ATTEMPT2"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-03T13:55:00Z"
updated: "2026-08-03T14:20:00Z"
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
| 2026-08-03 | 1.10 (11) | device-free: 14 юнит-проб (framework/tests/test_seed_db_schema_race_unit.py x2, test_subprocess_timeout_unit.py x8, test_seed_null_wordcount_unit.py x2, test_seed_filter_profiles_unit.py x2); live: on-device tight-loop red/green race repro (6/6 red hits "no such table: work_ratings" на файловом гейте, 0/6 на гейте по схеме); replay TC-141 (`loved_work_seeded`) x3 | 14 passed device-free (PYTEST_EXIT=0); live red 6/6, live green 0/6 fails; TC-141 3/3 PASSED | Fixed (test-maintainer, до fix-verifier/critic-входа по правилу D-0037/critic-класс) — **rejected** critic-входом (attempt 1): `_schema_ready()` fail-OPEN на отказе транспорта |
| 2026-08-03 | 1.10 (11) | Rework attempt 2: 4 живых зонда `_schema_ready()` через реальный код-путь (`adb.run_as`/`_run`) на emulator-5554/фиктивный emulator-9999 (см. Обсуждение); device-free: 17 юнит-проб (framework/tests/test_seed_db_schema_race_unit.py x5 [замена тавтологичного теста на параметризованный на реальном предикате], test_subprocess_timeout_unit.py x8, test_seed_null_wordcount_unit.py x2, test_seed_filter_profiles_unit.py x2); replay TC-141 (`loved_work_seeded`) x1 | 4/4 живых ветки совпали с диагнозом критика (RDY->True, no-such-table->False, device-unavailable->False [БЛОКЕР закрыт], db-file-missing->False); 17 passed device-free (PYTEST_EXIT=0); TC-141 1/1 PASSED; arch_check/validate_frontmatter 0/0 | Fixed (test-maintainer attempt 2, до повторного critic-входа) |

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

`fixed_in: 96734d8` (коммит `fix(seed_db): AT-BUG-044 ...`) — attempt 1,
ОТКЛОНЁН critic-входом. Правка ограничена `framework/data/seed_db.py` +
двумя тестовыми файлами — сама `_db_exists()` оставлена как отдельный
примитив (диагностика/будущие вызовы), просто больше не используется как
гейт готовности.

**2026-08-03T14:20:00Z — test-maintainer, rework attempt 2 (по
critic-вердикту, единственный блокер):** `_schema_ready()`
(`framework/data/seed_db.py`) переписана на проверенную критиком
fail-closed форму — remote-команда после успешного SELECT явно печатает
маркер:

```python
out = adb.run_as(
    f"sh -c 'sqlite3 {_DB_REL} \"SELECT 1 FROM work_ratings LIMIT 0\" 2>&1 && echo RDY'"
).strip()
return out.endswith("RDY")
```

Позитивный контракт вместо прежнего негативного (`out == ""`): непустой
суффикс `RDY` появляется в stdout ТОЛЬКО если весь remote pipeline реально
исполнился (SELECT прошёл без ошибки, шелл жив, транспорт не отказал) —
отказ транспорта (устройство offline/adb упал) теперь даёт пустую строку
БЕЗ маркера, что читается как «не готово» (fail-closed), а не как «готово»
(старый fail-OPEN баг attempt 1). Докстринг `_schema_ready()` дополнен
инкрементом 2 с этим разбором (исходная прозаическая формулировка «пустой
вывод = готово» помечена ложной).

Живой зонд 4 веток РЕАЛЬНОГО кода (не ручная реконструкция через
несколько слоёв локального шелла — та подошла бы неверно из-за
многослойного re-tokenizing Bash→PowerShell→adb; зонд шёл питон-скриптом,
вызывающим `seed_db._schema_ready()`/`adb.run_as()` напрямую тем же путём,
что и продакшн-код, канонической venv `framework/.venv`), emulator-5554 +
фиктивный `emulator-9999` для ветки отказа транспорта:
- схема готова (`emulator-5554`, реальный `_DB_REL`): `_schema_ready()` ->
  `True` (сырой вывод оканчивается `RDY`).
- таблицы нет (запрос к заведомо отсутствующей таблице
  `no_such_table_xyz` через тот же `sh -c '...2>&1 && echo RDY'`):
  `'Error: in prepare, no such table: no_such_table_xyz\n'`, `endswith
  RDY` -> `False`.
- файла БД нет (`databases/no_such_db_xyz.db`, несуществующий путь):
  `'Error: in prepare, no such table: work_ratings\n'` (sqlite3 на этом
  образе тихо создаёт новый пустой файл БД по несуществующему пути и тут
  же падает на отсутствующей таблице, а не текстом «unable to open
  database file», как в зонде критика на другом варианте пути — эффект тот
  же: непустой вывод без `RDY`), `endswith RDY` -> `False`. Артефакт-файл
  `databases/no_such_db_xyz.db`, созданный этим зондом, удалён с
  устройства сразу после проверки (`run-as ... rm -f`).
- **устройство недоступно (`-s emulator-9999`, САМ БЛОКЕР attempt 1)**:
  `adb.exe: device 'emulator-9999' not found` в stderr, `returncode=1`,
  `stdout=''` — то самое пустое `stdout`, что `_schema_ready()` реально
  получил бы через `adb.run_as`/`adb.shell`/`adb._run(...).stdout` (эти
  функции отбрасывают returncode и stderr). `''.strip().endswith("RDY")`
  -> `False` — блокер закрыт: раньше `out == ""` вернуло бы `True`.

Все 4 ветки совпадают с диагнозом критика (RDY/no-such-table/db-missing/
device-unavailable), включая различие фактического текста ошибки на ветке
«файла БД нет» (объяснено выше) — оно не меняет исход предиката.

Device-free юнит: тавтологичный `test_file_only_gate_reports_ready_before_schema_exists`
(`test_seed_db_schema_race_unit.py`, ассертивший только на
`_FakeDeviceTimeline`, не способный поймать регресс в реальном коде)
заменён на параметризованный `test_schema_ready_fail_closed_on_recorded_outputs`
— 4 монки-патч-кейса с ДОСЛОВНЫМИ записанными live-выводами (см. зонд
выше) на САМ `seed_db._schema_ready()`, плюс ассерт, что отправленная в
`adb.run_as` команда содержит `2>&1` (иначе находка про stdout/stderr
ничем не охраняется). Второй тест файла
(`test_ensure_db_initialized_waits_past_the_file_ready_tick`, критик
подтвердил содержательным) не менялся. Полный device-free набор —
17/17 зелёных (`Invoke-Pytest tests/test_seed_db_schema_race_unit.py
tests/test_subprocess_timeout_unit.py tests/test_seed_null_wordcount_unit.py
tests/test_seed_filter_profiles_unit.py -v` -> `17 passed`,
`PYTEST_EXIT=0`).

Потребитель `loved_work_seeded` — replay `TC-141`
(`tests/test_rating.py::test_edit_tag_on_already_saved_work_via_panel_does_not_click_kudos`)
— 1/1 PASSED (DoD attempt 2 требует минимум 1 зелёный при неизменном по
сути DoD-наборе attempt 1, полный повторный 3/3 не обязателен).
`arch_check.py`/`validate_frontmatter.py` — 0/0. `git status --porcelain
-- app-under-test/` — пусто (сверено до и после правки).

Non-blocking пункты critic-вердикта (перенос `_schema_ready()` внутрь
`try` цикла ретрая `ensure_db_initialized`; устаревшие ссылки на строки в
`app_steps.py:541-543`) НЕ применены в этом ходе — не обязательны для
приёмки, оставлены как есть по явному разрешению DoD.

`fixed_in` обновится на реальный хэш этого коммита в этом же ходе (тот же
приём, что `96734d8` — сам файл коммитится вместе с кодовым диффом,
placeholder заменяется на фактический хэш немедленно после коммита).

**Требуется повторный critic-вход перед приёмкой (CLAUDE.md правило 3):**
этот дифф — Sonnet-класс результат (test-maintainer); builder-класс
правка ядровой логики сидинга (framework/data/seed_db.py) — приёмка
легальна ТОЛЬКО через вход критика (льгота "critic: skipped" здесь
недоступна per матрице "Роль ≠ ярус"). Статус оставлен `Fixed` для
передачи в очередь fix-verifier/critic; при отклонении — вернуть в `Open`
с `rejected`-событием маршрутизации.

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
