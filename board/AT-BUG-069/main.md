---
key: "AT-BUG-069"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "Двойной раздельный seed()-round-trip после AT-BUG-044-фикса эмпирически дал 'no such table: work_ratings' один раз (не воспроизведено изолирующим экспериментом 20/20) — кандидат: _pull_baseline игнорирует возврат pull_app_file для -wal/-shm"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-187", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T02:07:28Z"
updated: "2026-08-16T02:07:28Z"
archived: false
resolution: "done"
---

# Двойной раздельный seed()-round-trip после AT-BUG-044-фикса эмпирически дал 'no such table: work_ratings' один раз (не воспроизведено изолирующим экспериментом 20/20) — кандидат: _pull_baseline игнорирует возврат pull_app_file для -wal/-shm

_Спроецировано из `bugs/AT-BUG-069.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-069 — рецидив сигнатуры AT-BUG-044 на двойном seed()-round-trip, кандидат-причина не подтверждена изолирующим экспериментом

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`) — не
зависит от сборки приложения, весь код в `framework/data/seed_db.py`.

## Суть долга

При разработке Given-фикстуры TC-187 (`metadata_fetch_stop_queue_seeded`,
`framework/tests/test_settings.py`) два ПОСЛЕДОВАТЕЛЬНЫХ вызова
`seed_db.seed()`/`app_steps.seed_library` (каждый со своим
`force_stop()`/`ensure_db_initialized()` round-trip) один раз дали
`sqlite3.OperationalError: no such table: work_ratings` на ВТОРОМ вызове
(2026-08-14, живой прогон) — та же СИГНАТУРА ошибки, что закрывал
`bugs/AT-BUG-044.md` (`fixed_in: d8062c5`, статус `Verified`).

Немедленный обход того же хода: `seed_db._insert_rows_ordered`/
`seed_ordered` схлопывают Given TC-187 в ОДИН device round-trip вместо
двух (снижает экспозицию к классу гонки в ЭТОМ конкретном кейсе, не
устраняет саму гонку в общем механизме, если она реальна).

**Это НЕ регрессия фикса `AT-BUG-044`.** Код-трассировка (rework attempt 2,
2026-08-14) показала: коммит `d8062c5` правил ТОЛЬКО `_schema_ready()`
(гейт готовности схемы после `pm clear`+relaunch, `seed_db.py:40-94`) —
`_pull_baseline` (`seed_db.py:132-146`) им НЕ затронут и остаётся
неизменным с момента до `AT-BUG-044`. **Исправление (критик-вход раунда 2,
2026-08-14): поле `regression_of` СНЯТО из frontmatter** — документированная
семантика поля (`docs/templates/bug-report.md`, `docs/06-dark-factory.md`
D7: «фикс сломал что-то другое») означает буквальную регрессию конкретного
фикса, что здесь неверно (см. выше — `d8062c5` не касается `_pull_baseline`).
Родство по симптому («тот же видимый класс `no such table`, тот же общий
механизм «сидинг гонится с Room-инициализацией схемы»»), а не regression —
остаётся ЗДЕСЬ, в прозе, единственным носителем связи с `AT-BUG-044`.

## Кандидат-причина (не подтверждена)

`_pull_baseline` (`seed_db.py:132-146`):
```python
def _pull_baseline(dst_dir: Path) -> Path:
    db = dst_dir / "ao3_ratings.db"
    ok = adb.pull_app_file(_DB_REL, db)
    if not ok:
        raise RuntimeError(...)
    # WAL/SHM могут отсутствовать — это нормально
    adb.pull_app_file(_WAL, dst_dir / "ao3_ratings.db-wal")
    adb.pull_app_file(_SHM, dst_dir / "ao3_ratings.db-shm")
    con = sqlite3.connect(db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    ...
```
Возврат `pull_app_file()` для `-wal`/`-shm` полностью ИГНОРИРУЕТСЯ. Сам
`pull_app_file` (`framework/core/adb.py:405-424`) молча возвращает `False`
и на «файла легитимно нет» (`cp.returncode != 0`, типично `run-as cat`
на отсутствующий WAL), и на РЕАЛЬНУЮ неудачу пулла (транзиентный
adb/транспорт-сбой) — не различает эти два исхода.

Гипотеза (critic-вход приёмки TC-186-188, rework attempt 1): device-side
`_schema_ready()` читает БД через `sqlite3` НА УСТРОЙСТВЕ — эта команда
видит main+WAL СКОМБИНИРОВАННО (штатное поведение SQLite в WAL-режиме),
поэтому может вернуть `True` («…RDY»), даже если схема физически лежит
ТОЛЬКО в непричекпойнченном WAL, а не в основном файле БД. Если в этот
момент отдельный host-side пулл WAL-файла (три РАЗДЕЛЬНЫХ device
round-trip: main/wal/shm) реально не удастся (не «файла нет», а
транспортная ошибка) — локальная реконструкция (main без таблицы +
отсутствующий локальный WAL) осталась бы БЕЗ таблицы, несмотря на
«зелёный» `_schema_ready()`, воспроизводя ровно `no such table:
work_ratings` при следующей вставке.

## Изолирующий эксперимент (rework attempt 2, 2026-08-14, тот же ход)

20 живых прогонов на `emulator-5554` (прямой вызов продакшн-кода из
`framework/.venv`, без прослойки bash/powershell-ретокенизации):

- **12×** одиночный `ensure_db_initialized()` (ждёт `_schema_ready()==True`)
  -> НЕМЕДЛЕННЫЙ ручной пулл (main/wal/shm по одному, как в
  `_pull_baseline`), проверка наличия таблицы В ОДНОМ main-файле (без
  WAL/checkpoint). Результат: `ok_wal=True` 12/12, таблица УЖЕ присутствует
  в main-файле-как-есть 12/12 (`table_in_main_alone=True` во всех
  итерациях) — WAL к моменту `_schema_ready()==True` в этих 12 прогонах не
  требовался вовсе.
- **8×** буквальная реконструкция ДВУХ последовательных
  `force_stop()+ensure_db_initialized()+_pull_baseline+_insert_rows`
  round-trip'ов (ровно паттерн, который дал живой фейл 2026-08-14, ДО
  перехода на `seed_ordered`) на одном `pm clear`. Результат: 0/8
  исключений, `ok_wal=True` на ОБОИХ вызовах во всех 8 итерациях.

**Итог: 0/20 воспроизведений, ни одного `pull_app_file(-wal)==False`.**
Эксперимент СНИЖАЕТ вероятность, что именно эта гипотеза — доминирующая
причина единичного живого фейла 2026-08-14, но при N=20 НЕ исключает
редкую/трудновоспроизводимую гонку целиком (правило 14 CLAUDE.md:
«вклад X не исключён» без исчерпывающего прогона). Возможные альтернативные
объяснения единичного фейла (не проверены отдельно): транзиентная
перегрузка эмулятора/adb в момент конкретного живого прогона, не связанная
с кодовым путём `_pull_baseline` вовсе.

## Критерий готовности (Fixed)

- [x] `_pull_baseline` различает «WAL/SHM легитимно отсутствуют» (штатно —
  файл не создавался Room, не ошибка) от «пулл реально не удался»
  (returncode/транспорт) — на втором случае fail-closed (raise/retry), а не
  молчаливое продолжение. Симметрично `_schema_ready()` (AT-BUG-044) и
  `run_as_file_or_raise` (AT-BUG-055) — тот же принцип: логически
  критичные операции проверяют возврат явно, не полагаются на «пусто =
  нормально».
- [x] Красная/зелёная проба на новую ветку.
- [x] Все текущие потребители `_pull_baseline` (`seed*`, `read_*`) остаются
  зелёными, регресс не внесён.
- [x] `arch_check.py`/`validate_frontmatter.py` — 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.

## Фикс (test-maintainer, 2026-08-16)

**Живая эмпирика ПЕРЕД правкой (5 сценариев на `emulator-5554`, скрипт в
транскрипте хода) показала, что кандидат-причина из шапки бага была
СФОРМУЛИРОВАНА НЕТОЧНО, но правка того же духа закрывает и уточнённую
причину.** `adb exec-out` не транслирует returncode/stderr удалённой
команды: и реальное содержимое файла, и текст ошибки `cat`
(«No such file or directory»), и текст ошибки самого `run-as`
(«unknown package») попадают в ОДИН и тот же локальный `cp.stdout` с
`cp.returncode == 0` во всех трёх случаях. Старая проверка
`cp.returncode != 0 or not cp.stdout` (`framework/core/adb.py`, было
:405-424) была готова записать текст ошибки `run-as`/`cat` в `dest` КАК
БУДТО это содержимое файла (непустой `cp.stdout`, `returncode == 0`) — это
даже ХУЖЕ исходной гипотезы «тихо возвращает False» (то тоже происходит на
пустом `stdout`, но НЕ на непустом с текстом ошибки).

**Фикс** — `pull_app_file` (`framework/core/adb.py:405-...`): удалённая
команда теперь `run-as PKG sh -c 'cat REL; printf "\nAT_BUG_069_PULL_RC=%d" $?'`
— явный rc-маркер дописывается ПОСЛЕ содержимого в ТОТ ЖЕ бинарный
`stdout` (тот же приём, что `run_as_file_or_raise`/AT-BUG-055, только на
бинарном канале — `>&2` НЕ помогает, живой пробой подтверждено: `exec-out`
сливает remote stdout+stderr в один локальный stdout, редирект на удалённой
стороне на это не влияет). `rfind()` маркера с конца:
- маркер найден, `rc==0`, контент непуст -> реальные байты файла -> `True`.
- маркер найден, `rc!=0` ИЛИ контент пуст -> `cat` сам не смог прочитать
  (легитимное отсутствие WAL/SHM) -> `False`, текст ошибки `cat`
  ИГНОРИРУЕТСЯ (не пишется в `dest`).
- маркер ОТСУТСТВУЕТ вовсе -> `run-as`/remote-shell не выполнились
  (устройство офлайн, пакет не debuggable/не установлен, битый toybox) ->
  `RuntimeError`, fail-closed — САМ БЛОКЕР этого бага.

Сигнатура `pull_app_file(rel_path, dest) -> bool` НЕ менялась — рефакторинг
вызывающих мест НЕ потребовался (3 вызова, все в `seed_db._pull_baseline`);
`RuntimeError` теперь может прилететь оттуда же, откуда раньше прилетал бы
для main-db-ветки (`if not ok: raise RuntimeError(...)`), просто раньше он
не мог случиться на WAL/SHM-ветках вовсе (возврат игнорировался), теперь
может — и это ЖЕЛАЕМОЕ поведение (fail-closed), не расширение контракта,
требующее правки `_pull_baseline`.

**Свидетельства (полный вывод в транскрипте хода):**
- Живая 5-сценарная сверка на `emulator-5554` (реальный файл /
  синтетически-отсутствующий путь / легитимно-пустой WAL / несуществующий
  пакет для `run-as` / несуществующая серийка устройства) — обосновала
  дизайн ДО правки.
- Новый device-free юнит-тест
  `framework/tests/test_pull_app_file_fail_closed_unit.py` — 10 кейсов
  (матрица + регресс-замок), GREEN после фикса; тот же регресс-замок
  проверен и вручную (`scratchpad/red_green_pull_app_file.py`) против
  ДОСЛОВНОЙ старой ветки логики из `git show HEAD` — RED (старый код
  возвращал `True` и писал текст ошибки как байты файла) до фикса,
  GREEN после.
- `framework/tests/test_seed_db_full_baseline_live.py` (живой, использует
  `_pull_baseline` напрямую, без Appium) — 3/3 зелёных прогона подряд на
  `emulator-5554` после фикса.
- Живая реконструкция ОРИГИНАЛЬНОГО паттерна бага (два последовательных
  `seed()`/`force_stop()`/`ensure_db_initialized()` round-trip на одном
  `pm clear`, `scratchpad/double_seed_roundtrip_probe.py`) — 8/8 итераций
  без исключений после фикса.
- `python -m pytest framework/tests -k unit` — 290 passed (device-free
  regressиона нет).
- `python -m pytest scripts/tests -q` — 1297 passed, 1 skipped (0 failed;
  единственный сбой в первом прогоне — утечка `AO3_LOOP_HOLDER` из
  ПАРАЛЛЕЛЬНОГО heartbeat-процесса в env текущей bash-сессии, не связана с
  этим диффом — подтверждено повтором с очищенным env).
- `python scripts/arch_check.py` — 0 ошибок (4 предупреждения, все —
  ранее известные allowlist-исключения/несвязанный rule3-пункт TC-176).
- `python scripts/validate_frontmatter.py` — 0/0.

**Область правки:** только `framework/core/adb.py` (одна функция) +
новый тест-файл. `_pull_baseline`/`seed_db.py` НЕ тронуты (правка
изолирована в `pull_app_file`, ниже по стеку — соответствует
предупреждению координатора о ядровой природе `_pull_baseline`: сам
`_pull_baseline` не менялся вовсе, только функция, которую он вызывает).
`app-under-test/` не тронут.

**Rework attempt 2 (test-maintainer, критик-вход rework attempt 1, два
блокера B1/B2):**

- **B1 (механический):** frontmatter `status_since`/`updated` были
  `2026-08-16T00:50:00Z` — на +57 минут В БУДУЩЕМ относительно
  фактического UTC на момент критик-прогона (`2026-08-15T23:52:26Z`).
  Исправлено на фактическое время этого хода
  (`2026-08-15T23:59:07Z`, реальный вывод `datetime.now(timezone.utc)`).
  `lock` снят (было `test-maintainer:2026-08-16T01:05:00Z`).
- **B2 (регрессия, суть):** `pull_app_file` (`framework/core/adb.py`)
  интерполировала `rel_path` в удалённую `sh -c '...'`-строку БЕЗ кавычек
  — критик живьём подтвердил на `emulator-5554` три поломки: (1) путь с
  пробелом (существующий читаемый файл) молча давал `False` вместо
  `True`+байты — та же путаница «легитимно нет» vs «сбой», которую весь
  фикс должен был устранить, регресс; (2) пустой/пробельный `rel_path` —
  `cat` без операнда читает STDIN -> hang до `ADB_TRANSFER_TIMEOUT`
  (120s); (3) метасимволы (`;`) в `rel_path` -> удалённое исполнение
  произвольной команды. Исправлено: `rel_path` теперь заквочен
  одинарными кавычками (`cat '{rel_path}'; printf ...`) — критик-кандидат,
  живьём проверенный им (путь с пробелом -> корректные байты; пустой
  `rel_path` -> мгновенная ошибка ~0.1s, не hang). Одинарная кавычка
  ВНУТРИ `rel_path` (сломала бы само квотирование) — явный `ValueError`
  ДО похода на устройство (`rel_path` всегда module-level константа
  `seed_db._DB_REL`/`_WAL`/`_SHM`, но fail-closed правильнее молчаливой
  поломки).

  Собственная live-переверификация этого хода
  (`scratchpad/rework2_verify_pull_app_file.py`, реальная production-
  функция, `emulator-5554`) воспроизвела результаты критика на
  исправленном коде: путь с пробелом (`files/rework2_sp ace.bin`) ->
  `ok=True`, байты совпали точно; пустой `rel_path` -> `ok=False` за
  0.08s (не hang); кавычка-инъекция -> `ValueError` мгновенно, до
  `subprocess.run`.

  Новые device-free юнит-кейсы (критик указал: старые 10 мокают
  `subprocess.run` целиком готовым `CompletedProcess` и не видят класс
  «argv не заквотирован») в
  `framework/tests/test_pull_app_file_fail_closed_unit.py`:
  `test_rel_path_with_space_is_single_quoted_in_remote_command` (проверяет
  СОСТАВ построенной remote-команды — путь обёрнут в кавычки, а не
  голый), `test_empty_rel_path_is_quoted_not_left_bare_for_stdin_cat`
  (пустой `rel_path` остаётся явным `''`, не голым `cat ;`),
  `test_rel_path_with_single_quote_rejected_fail_closed_before_subprocess`
  (`ValueError` до `subprocess.run`, файл `subprocess.run` вообще не
  вызывается).

  **Опционально, НЕ сделано в этом ходе (критик пометил non-blocking):**
  `2>/dev/null` на `cat` по симметрии с `run_as_file_or_raise`
  (`adb.py:378`) — сейчас stderr-текст `cat` при УСПЕШНОМ пулле
  теоретически мог бы примешаться в бинарный `content` (redirect на
  удалённой стороне уже подтверждён неэффективным для разделения
  каналов в докстринге функции — `exec-out` сливает remote stdout+stderr
  в один локальный stdout независимо от редиректа, так что `2>/dev/null`
  дал бы эффект только на СОБСТВЕННО STDERR remote-`cat`, не на общую
  проблему смешения каналов; сейчас маркер-подход уже отделяет ошибку от
  контента по `rc`, так что практическая ценность этого добавления мала).
  Оставлено координатору как возможное мелкое улучшение, не блокер.

  **Witness rework attempt 2 (дословно):**
  - `Invoke-Pytest tests/test_pull_app_file_fail_closed_unit.py -q` ->
    `13 passed in 0.23s`, `PYTEST_EXIT=0` (было 10, +3 новых).
  - `Invoke-Pytest tests -k unit -q` -> `293 passed, 187 deselected, 3
    warnings in 22.84s`, `PYTEST_EXIT=0` (было 290, +3 новых кейса; 3
    предупреждения — известный AT-BUG-026 device-liveness guard шум, не
    связаны с этим диффом).
  - `python scripts/arch_check.py` -> `ошибок 0, предупреждений 4` (4 —
    те же ранее известные allowlist-исключения, что и до rework).
  - `python scripts/validate_frontmatter.py` -> `validate_frontmatter:
    ошибок 0, предупреждений 0` (0/0 — критик поймал attempt1 на этом
    гейте с некорректным future-timestamp'ом B1, в этом заходе чисто).

**Явно НЕ в этом ходе (по прямому указанию диспатча, не расширяю scope):**
4 сиблинга композитных seed-вызовов (`library_mixed_download_status_seeded`,
`library_favorite_and_files_scroll_seeded`, `library_downloaded_only_seeded`,
`backup_restore_seeded`) и класс «единый timestamp» (`_insert_rows`/
`_insert_rows_full`/`_insert_rows_with_download`/
`_insert_rows_full_with_download`/`seed_filter_profiles`) — оба остаются в
очереди координатору, как и было помечено при заведении бага.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-16 | framework HEAD `72a0243` (фикс `0107bf1`, `framework/core/adb.py::pull_app_file`); `type: test_debt` — независим от версии приложения | `framework/tests/test_pull_app_file_fail_closed_unit.py` (device-free юнит на rc-маркер + квотирование `rel_path`, 13 кейсов); `TC-187` = `framework/tests/test_settings.py::test_fetch_missing_metadata_stop_mid_process` (Given-фикстура `metadata_fetch_stop_queue_seeded`, где проявлялся рецидив), device-прогон на `emulator-5554` | `Invoke-Pytest tests/test_pull_app_file_fail_closed_unit.py -q` -> `13 passed in 0.21s`, `PYTEST_EXIT=0`; `Invoke-Pytest tests/test_settings.py -k test_fetch_missing_metadata_stop_mid_process -q` -> `1 passed, 10 deselected in 42.20s`, `PYTEST_EXIT=0` | Verified — независимый прогон fix-verifier подтверждает: rc-маркер юниты зелёные (13/13, счёт совпадает с заявленным в «Фикс»), TC-187 зелёный на живом устройстве, `validate_frontmatter` 0/0 |

## Обсуждение

**2026-08-14T02:40:00Z — test-automator, rework attempt 2 (критик-вход
приёмки TC-186-188, блокеры B1/B2):** заведён по прямому указанию критика.
Решено НЕ reopen'ить `AT-BUG-044` (её фикс правит другую функцию —
`_schema_ready()` — и работает корректно, изолирующий эксперимент это
подтверждает косвенно: гейт стабильно даёт `True` ровно в момент, когда
схема уже в main-файле). Решено НЕ чинить `_pull_baseline` в этом же ходе:
правка ядровой логики сидинга (`framework/data/seed_db.py`) заметного
размера/затрагивающая общий для всех кейсов механизм требует
самостоятельного critic-входа (CLAUDE.md правило 3) и выходит за
заявленный скоуп диспатча test-automator (автоматизация TC-186/187/188,
не рефакторинг `_pull_baseline`) — D-0037, не расширять scope
самостоятельно. Заведён как отдельный test_debt для очереди B4
(`state/rules.yaml`).

Обход для TC-187 (`seed_ordered`, ОДИН round-trip вместо двух) и для
TC-062 (`seed_with_comment_ordered`, тот же приём для
`_insert_rows_full`-семейства) применены этим же ходом — снижают
экспозицию к классу в ДВУХ конкретных кейсах, не закрывают сам механизм.

**Остаток класса (исправлено критик-входом раунда 2, 2026-08-14: полный
AST-свип `framework/`, а не выборочный обход `conftest.py`) — ЧЕТЫРЕ,
не два, незакрытых сиблинга «несколько последовательных
seed-round-trip»:**
1. `framework/tests/conftest.py::library_mixed_download_status_seeded`
   (~607) — составной вызов РАЗНЫХ seed-функций (не только
   `timestamp`-упорядочение).
2. `framework/tests/conftest.py::library_favorite_and_files_scroll_seeded`
   (~655) — тот же класс композиции.
3. `framework/tests/conftest.py::library_downloaded_only_seeded` (~465,
   владеет TC-028) — `seed_library` + `seed_downloaded_work`, два подряд
   round-trip; докстринг самой фикстуры (`:471`) буквально называет
   паттерн: «Сидинг в ДВА последовательных вызова».
4. `framework/tests/test_backup_restore.py::backup_restore_seeded` (~80) —
   `seed_with_comment` + `seed_filter_profiles`, оба несут собственный
   `force_stop()`+`ensure_db_initialized()`+`_pull_baseline` round-trip;
   вне `conftest.py`, поэтому пропущен первым обходом.

Ни один из четырёх НЕ мигрирован в этом ходе (составные вызовы РАЗНЫХ
seed-функций ради контента, не `timestamp`-упорядочение одной функции —
`seed_with_comment_ordered`/`seed_ordered` к ним не отображаются
напрямую, нужен отдельный дизайн) — доклад координатору, в очередь.

**Отдельный незакрытый класс той же поверхности (найдено критик-входом
раунда 2): «все строки ОДНОГО вызова получают ОДИН `timestamp`».** Твины
(`_insert_rows_ordered`/`_insert_rows_full_ordered`) закрывают только ДВА
члена семейства insert-хелперов. Остальные четыре продолжают присваивать
единый `now` всему списку — недетерминизм `ORDER BY` среди равных
timestamp остаётся их свойством:
- `seed_db.py::_insert_rows` (~158)
- `seed_db.py::_insert_rows_full` (~182)
- `seed_db.py::_insert_rows_with_download` (~566)
- `seed_db.py::_insert_rows_full_with_download` (~628)
- (плюс `seed_filter_profiles`, ~530, тот же паттерн для профилей)

**НЕ чинить сейчас** — универсальный `base_now + i` сделал бы
детерминированным то, что сегодня произвольно, и может ПЕРЕВЕРНУТЬ текущие
зелёные ассерты ~25 фикстур, построенных на этом семействе — отдельный
critic-вход на плане нужен до кода (правило 3 CLAUDE.md, «критик на
план»). Класс поставлен в очередь координатору этой строкой.

## Чек-лист качества (заводящий проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не дубль `AT-BUG-044`
  (тот закрывает `_schema_ready()`, эта — кандидат-дефект в
  `_pull_baseline`, код-трассировкой подтверждено, что коммит `d8062c5`
  этот участок не менял); родство по симптому, не идентичность, отражено
  прозой в «Суть долга» — не полем `regression_of` (снято критик-входом
  раунда 2, документированная семантика поля означает буквальную
  регрессию конкретного фикса)
- [x] Severity обоснована влиянием: minor — 0/20 живых воспроизведений в
  изолирующем эксперименте, единичный живой инцидент, обход (`*_ordered`)
  уже снижает экспозицию в затронутых кейсах
- [x] Приложены материалы: код-трассировка коммита `d8062c5` +
  20-прогонный изолирующий эксперимент этого хода (raw-результаты в
  транскрипте test-automator rework attempt 2)
- [x] Нет изменений кода приложения
