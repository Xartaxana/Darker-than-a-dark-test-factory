---
id: AT-BUG-009
title: "FLAKY(?): test_disliked_hidden_on_listing (TC-013, replay) — ReadTimeoutError к локальному Appium внутри driver.get() при полном p0 после длинной сессии; в изоляции ранее многократно зелёный за 20-25s"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "test-maintainer (AT-BUG-005, финальный инкремент — верификация 'Smoke без регресса'), 2026-07-14, полный p0-прогон (-m p0, 19 отобранных: 18 прежних + новый TC-021) после установки app-debug.apk на свежепойманном эмуляторе"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-013"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-14T13:37:03Z"
updated: "2026-07-14T21:00:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-009 — TC-013 (replay) ловит ReadTimeoutError к Appium внутри полного p0

## Окружение
- Эмулятор `ao3_test_api34` (API 34), свежий буд, `app-debug.apk` (текущий HEAD)
  переустановлен непосредственно перед прогоном; Appium поднят заново
  (`Start-Appium`). Полный `Invoke-Pytest -m p0` (19 отобранных: 18 прежних
  p0-тестов + новый `test_backup_restore.py::test_backup_clear_restore_returns_original_data`,
  TC-021, добавлен тем же днём test-automator'ом).

## Суть

`tests/test_visibility.py::test_disliked_hidden_on_listing[listing_basic.mitm]`
(TC-013, `@pytest.mark.replay`) — тест с долгой историей стабильности:
многократно документирован зелёным за 20-25s изолированно и внутри p0 в
истории `AT-BUG-004` (инкременты 1-3, включая независимые прогоны critic'а и
fix-verifier'а). В этом прогоне упал ПОСЛЕ таймаут-гейта AT-BUG-007
(`--reruns 1 --only-rerun ReadTimeoutError|MaxRetryError`, `pytest.ini`):
первая попытка помечена pytest как `R` (rerun matched), повторная попытка
упала тем же классом — `urllib3.exceptions.ReadTimeoutError:
HTTPConnectionPool(host='127.0.0.1', port=4723): Read timed out. (read
timeout=120)` — РОВНО на границе `APPIUM_HTTP_TIMEOUT` (settings.py default
120s), внутри `browser_steps.open_listing` → `driver.get(url)`, первый
существенный Appium-вызов теста (сразу после `app_steps.wait_ui_ready`).

Итоговое время всего прогона (19 тестов): `1525.73s` (~25.5 мин) против
известного базового `~575-633s` (~10 мин) для сопоставимого состава — почти
трёхкратное удлинение, целиком за счёт двух попыток этого теста.

Диагностика на месте (после падения, до какой-либо правки):
- Процесс приложения ЖИВ (`adb shell pidof com.example.ao3_wrapper` →
  непустой pid), `mCurrentFocus` — приложение в фокусе. Это НЕ класс
  AT-BUG-008 (тихая смерть процесса на splash) — там `pidof` был пуст.
- `adb shell logcat -d -b crash` содержит один краш-стек, но с device-time
  заметно РАНЬШЕ начала этого прогона (стейл-запись от более ранней сессии
  этого же дня, не относится к текущему падению).
- Фикстура `replay` (`conftest.py:160-188`) поднимает СВОЙ mitmdump на
  каждый тест (`mitm.set_device_proxy()` / `mitm.start_replay()` /
  `mitm.stop()` / `mitm.clear_device_proxy()`, не общий процесс) — падение
  не объясняется утечкой состояния прокси МЕЖДУ тестами напрямую, но каждый
  из этих вызовов сам — `subprocess.run(adb shell ...)` БЕЗ `timeout=`
  (уже задокументированный, но НЕ исправленный аналог в
  `bugs/AT-BUG-007.md`, находка N1: `framework/core/mitm.py:97-98`
  (`set_device_proxy`), `:103-104` (`clear_device_proxy`)) — на нагруженной/
  долго живущей сессии (19 тестов подряд, ~25 мин к моменту этого теста;
  предыдущий поднятый python/appium/adb процесс-парк уже накопился) это
  правдоподобный, но НЕ подтверждённый кандидат в корень: если `adb shell
  settings put ...` для смены прокси завис или сильно замедлился, WebView
  внутри `driver.get()` могла ждать прокси-редирект дольше обычного,
  упираясь в `APPIUM_HTTP_TIMEOUT` уже на стороне Appium-HTTP слоя.

Не установлено экспериментально (не входит в этот инкремент — только
доклад): единичное наблюдение, не подтверждена системность (флаки vs
детерминированная поломка). Полный повторный p0-прогон для проверки
устойчивости НЕ гонялся (стоимость ~25+ мин за попытку, не в скоупе
верификации AT-BUG-005).

## Критерий готовности (Fixed)

- Диагностирован корень (в частности, проверить кандидата: зависание/
  замедление `adb shell settings put` в `mitm.set_device_proxy`/
  `clear_device_proxy` под нагрузкой длинной сессии — см. также очередь
  `adb.py::_run()` без `timeout=`, тот же класс, задокументированный в
  `bugs/AT-BUG-007.md`).
- Минимум 2 полных p0-прогона подряд (после диагностики/фикса, если он
  нужен) без проявления этого класса на TC-013, ЛИБО обоснованное решение
  test-designer/Lead о карантине теста (по аналогии с критерием
  `bugs/AT-BUG-008.md`), если флаки подтвердится системным, но
  неустранимым в разумные сроки.
- Smoke (`-m p0`) укладывается в разумное время без аномального удлинения
  (ориентир — прежний базовый порядок ~10 мин на сопоставимый состав).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-14T13:37:03Z — test-maintainer (AT-BUG-005, финальный инкремент,
доклад по правилу «новый блокер = test_debt-баг»):** Обнаружено при
обязательной по DoD задачи проверке «Smoke без регресса» для AT-BUG-005
(TC-021 несёт `@pytest.mark.p0`, состав smoke изменился после прогона
fix-verifier'а 10:50 → потребовался собственный полный `-m p0`). Результат:
18/19 passed, 1 failed (TC-013, класс — ReadTimeoutError к Appium, таймаут-
гейт AT-BUG-007 сработал штатно — не бесконечное зависание — но повторная
попытка тоже не уложилась). Не смешиваю с самим AT-BUG-005 (эта область —
`test_visibility.py`, SAF/backup инфраструктура AT-BUG-005 не участвует) и
не чиню сам (scope не расширяется, D-0037) — заведён отдельным test_debt-
багом, диспетчеризация дальнейшего разбора за Lead. Полный вывод прогона
(traceback, тайминги) приложен в отчёте задачи AT-BUG-005.

**2026-07-14T14:52:00Z — Lead (Fable), наблюдение №2 (доклад test-reviewer,
F1-ревью f1-library-tc027-030-review, тот же день):** при независимом прогоне
`tests/test_library_filters.py` ПЕРВАЯ Appium-сессия зависла на создании
(~44 мин, тест не дошёл до результата); снята киллом + рестартом Appium,
повторный прогон целиком зелёный за 193.92s (4 passed). Отличие от
наблюдения №1: зависание на СОЗДАНИИ сессии (до driver.get), не внутри
теста, и rerun-гейт AT-BUG-007 его не поймал (гейт работает на
ReadTimeoutError уже открытой сессии). Класс тот же — деградация связки
Appium/эмулятор, проявление №2 за день, разные тесты, разные фазы →
системность становится правдоподобнее, «единичное наблюдение» из «Не
установлено» выше уже неверно. Диагностика корня — по критерию Fixed;
кандидат mitm.py без timeout к наблюдению №2 не применим (test_library_filters
не использует replay/mitm — фикстуры чистого сидинга), что СУЖАЕТ поиск:
общий знаменатель — длинная живая сессия эмулятора/Appium, не прокси.

**2026-07-14T20:20:00Z — test-maintainer, инкремент 1 (закрытие кандидата
«subprocess-вызовы без timeout»):**

Область: ТОЛЬКО кандидат из критерия Fixed — `subprocess.run(adb shell ...)`
без `timeout=` в `framework/core/mitm.py` (`set_device_proxy`/
`clear_device_proxy`) и очередь `framework/core/adb.py::_run()`, обе
задокументированы находкой N1 `bugs/AT-BUG-007.md` (2026-07-10, НЕ
исправлены тогда — явно поставлены в очередь для отдельного B4-прохода).
Диагностика корня наблюдения №1 (сработал ли этот кандидат ФАКТИЧЕСКИ на
TC-013) и 2 чистых p0 подряд / решение о карантине — НЕ этот инкремент,
`status` остаётся `Open`.

Правки (`framework/core/adb.py`, `framework/core/mitm.py`,
`framework/config/settings.py`):
- `adb.py::_run()` — добавлен параметр `timeout: float =
  settings.ADB_SHELL_TIMEOUT`; `subprocess.TimeoutExpired` оборачивается в
  `TimeoutError` с контекстом (полная команда, сколько ждали, ссылка на
  AT-BUG-009). Файловые операции (`install()`, `push_app_file()`) передают
  `timeout=settings.ADB_TRANSFER_TIMEOUT` явно (щедрее обычного shell-вызова).
  `pull_app_file()` не идёт через `_run()` (нужны сырые байты без
  `text=True`) — тот же `ADB_TRANSFER_TIMEOUT` применён напрямую в отдельном
  `try/except`.
- `mitm.py::set_device_proxy`/`clear_device_proxy` — тот же `ADB_SHELL_TIMEOUT`,
  та же обёртка в `TimeoutError` с контекстом. Явно отмечено в докстринге
  `clear_device_proxy`: `check=False` подавляет только ненулевой
  `returncode`, НЕ `TimeoutExpired` — teardown падает явной ошибкой, не висит
  молча.
- Новые константы в `settings.py`: `ADB_SHELL_TIMEOUT=30` (env
  `AO3_ADB_SHELL_TIMEOUT`) — обычные быстрые shell-команды (`settings put`,
  `pm clear`, `force-stop`, `logcat -d`), по наблюдениям укладываются в доли
  секунды даже на нагруженном эмуляторе; 30s — на порядок больше нормы, но
  конечный. `ADB_TRANSFER_TIMEOUT=120` (env `AO3_ADB_TRANSFER_TIMEOUT`) —
  файловые операции (`install`/`push`/`exec-out cat`), тот же порядок запаса,
  что `APPIUM_HTTP_TIMEOUT` (AT-BUG-007). Оба обоснования — в комментарии
  рядом с константами (докстринг-стиль, как у `APPIUM_HTTP_TIMEOUT`).

Классовая полнота (правило 9 CLAUDE.md, D-0043 OS-репо) — пройдено по
`framework/core` и `framework/tests/conftest.py` (owns задачи):
- `adb.py`: помимо `_run()`, отдельный прямой `subprocess.run` в
  `pull_app_file()` — тот же класс, тоже исправлен (см. выше).
- `mitm.py`: `start_replay`/`start_record` (`subprocess.Popen`) — НЕ
  блокирующие вызовы (Popen возвращает управление сразу), таймаут не нужен;
  `_wait_listening` уже ограничена `_READY_TIMEOUT=15s` (проверено N1
  ревью AT-BUG-007 attempt 2 — не подтвердилось отдельной находкой); `stop()`
  уже использует `Popen.wait(timeout=5)` с фолбэком на `kill()` — уже
  конечный.
- `framework/tests/conftest.py` (реальный путь фикстуры `replay`, задача
  называла `framework/conftest.py` — такого файла нет, конвенция pytest:
  `framework/tests/conftest.py`) — сама фикстура вызывает только
  `mitm.set_device_proxy/start_replay/stop/clear_device_proxy` и не делает
  собственных `subprocess`-вызовов; класс закрыт транзитивно через правки
  `mitm.py` выше.

Остаток класса (НЕ исправлен в этом инкременте — вне `owns`, `framework/tests/`
разрешён только для НОВОЙ device-free пробы): `framework/tests/
test_saf_infra_probe.py::_adb_push()` — прямой `subprocess.run([...,
"push", ...])` без `timeout=` (AT-BUG-005 инфраструктурная проба, не
затронутый этой задачей тестовый модуль). Тот же класс, тот же паттерн фикса
(`timeout=settings.ADB_TRANSFER_TIMEOUT` + обёртка в `TimeoutError`) —
перечисляю как остаток по правилу 9, не чиню (scope не расширяется, D-0037).
Отдельного нового test_debt-бага не завожу: это тот же класс, что уже
покрыт критерием Fixed этого самого AT-BUG-009 (не НОВЫЙ блокер) — остаток
дополнит следующий инкремент/проход по этому же багу.

Witness:
- Device-free: новая проба `framework/tests/test_subprocess_timeout_unit.py`
  (5 тестов, монки-патчит `subprocess.run` — TimeoutExpired на зависший
  adb-shell/install/push/pull, проверяет оборачивание в `TimeoutError` с
  контекстом И корректный выбор `ADB_SHELL_TIMEOUT` vs `ADB_TRANSFER_TIMEOUT`
  по типу операции). 3 прогона подряд:
  `Invoke-Pytest tests/test_subprocess_timeout_unit.py -v` → `5 passed`
  каждый раз (0.40s / 0.06s / 0.40s), `PYTEST_EXIT=0` все три.
  `python -m pytest scripts/tests -q` → `344 passed` (обвязка не затронута).
- Device-регресс (эмулятор `ao3_test_api34`, cold boot `-no-snapshot-load`
  после порчи снапшота `default_boot` — тот же класс порчи, что описан в
  верификации AT-BUG-007 fix-verifier'ом 2026-07-14, не относится к этой
  правке; `-writable-system` + `Install-MitmCA`, `app-debug.apk` текущего
  HEAD установлен, `Start-Appium`):
  `Invoke-Pytest tests/test_replay_infra_probe.py -v` → `1 passed, 33.76s`,
  `PYTEST_EXIT=0` (replay-путь реально проходит через правленые
  `mitm.set_device_proxy`/`start_replay`/`stop`/`clear_device_proxy`).
  `Invoke-Pytest tests/test_visibility.py -v` → TC-013
  (`test_disliked_hidden_on_listing`, сам флаки-тест наблюдения №1, в
  изоляции) → `1 passed, 23.59s`, `PYTEST_EXIT=0`. Полный p0 НЕ гонялся
  (стоимость, критерий Fixed остаётся открытым по задаче). Эмулятор погашен
  после (`adb emu kill`, `Get-Device` → `NO DEVICE`).
- `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`.

Что этот инкремент НЕ закрывает (важно не читать как Fixed): наблюдение №2
AT-BUG-009 (зависание СОЗДАНИЯ Appium-сессии, ~44 мин, `test_library_filters`,
БЕЗ replay/mitm) остаётся вне этого фикса — сам корень уже сужен предыдущей
записью Lead до «длинная живая сессия Appium/эмулятора», не прокси/adb; этот
инкремент закрывает только subprocess-без-timeout кандидат наблюдения №1.
Диагностика корня наблюдения №1 (зависание/замедление `adb shell settings
put` ПОДТВЕРДИЛОСЬ ли фактически как причина ReadTimeoutError на TC-013) не
проводилась экспериментально в этом инкременте — только устранён сам
кандидат-риск (subprocess без timeout), критерий Fixed («диагностирован
корень» + «2 чистых p0 подряд») остаётся открытым, `status: Open` не
меняется.

**2026-07-14T21:00:00Z — test-maintainer, наблюдение №3 (повторная попытка
финального инкремента AT-BUG-005, полный p0 ПОСЛЕ инкремента 1):**

Область задачи — сверка «Smoke без регресса» для `bugs/AT-BUG-005.md`
(SAF/backup не участвует). Среда: `Start-Emulator` (обычный буд, не
writable-system/cold), `Start-Appium`, `Install-App` (`app-debug.apk`
текущего HEAD), устройство подтверждено `Get-Device` → `emulator-5554`
ДО и ПОСЛЕ поднятия. `Invoke-Pytest -m p0` — **collected 46 items / 27
deselected / 19 selected** (5 новых item — `test_subprocess_timeout_unit.py`
инкремента 1, не p0, не в составе; 19 selected совпадает с прошлым разом) →
**16 passed, 3 errors**, `16 passed, 27 deselected, 3 errors in 644.99s
(0:10:44)`, `PYTEST_EXIT=1`.

Это НЕ повтор наблюдения №1 тем же классом (см. задача test-maintainer:
«TC-013 падает тем же классом» требовало бы `ReadTimeoutError` внутри
`browser_steps.open_listing`→`driver.get`, В ТЕЛЕ теста, после
`wait_ui_ready`) — это другой класс, другая фаза, и задел шире одного
TC-013:

- `tests/test_rating.py::test_rate_work_from_work_page_panel[SAVE-placeholder_seeded_work0]`
  — `ERROR at setup` (тест не запускался вовсе).
- `tests/test_rating.py::test_rate_work_from_work_page_panel[READ-placeholder_seeded_work2]`
  — `ERROR at setup`.
- `tests/test_visibility.py::test_disliked_hidden_on_listing[listing_basic.mitm]`
  (TC-013, тот же тест, что наблюдение №1) — теперь ТОЖЕ `ERROR at setup`,
  не `FAILED` в теле.

Все три — идентичный traceback:
`placeholder_seeded_work`/`seeded_library` фикстура → `app_steps.
seed_with_comment`/`seed_library` → `seed_db.ensure_db_initialized()` →
`adb.shell("am start -W -n com.example.ao3_wrapper/...MainActivity")` →
`core/adb.py::_run()` → `TimeoutError: adb -s emulator-5554 shell am start
-W ... не уложился за 30s (AT-BUG-009)` — та самая обёртка, добавленная
инкрементом 1 ЭТОГО бага.

Точный механизм (прочитан код `framework/data/seed_db.py:35-51`,
`ensure_db_initialized`): существующий ретрай-цикл вызывает `adb.shell(...)`
(`am start -W`) ПЕРВОЙ строкой каждой итерации, а `try/except TimeoutError:`
оборачивает ТОЛЬКО последующий `wait_for(_db_exists, timeout=40)` —
задуман для повтора именно долгого появления Room-БД («один ретрай на
случай, если эмулятор был занят», докстринг). `TimeoutError`, который
теперь может прилететь из самого `adb.shell()` (новое поведение инкремента
1), возникает ДО входа в `try:` и потому НЕ перехватывается этим ретраем
вообще — распространяется наружу немедленно, независимо от `attempt`.
Это НЕ баг инкремента 1 как такового (задача инкремента — не молчать,
не виснуть бесконечно, и с этим справляется), а АРХИТЕКТУРНЫЙ ПРОБЕЛ
СТЫКА: `ensure_db_initialized` был написан в расчёте на мир БЕЗ timeout
у `adb.shell()` (единственный источник `TimeoutError` тогда — `wait_for`);
после инкремента 1 у функции появился второй, неретраемый источник того
же типа исключения на первой же строке цикла.

Диагностика на месте (после падения, эмулятор ещё жив, до останова):
- `adb shell pidof com.example.ao3_wrapper` → пусто (процесс НЕ жив сразу
  после конца прогона).
- `adb shell echo ping` (тривиальная команда) → `0.070s` — adb-сервер и
  канал к устройству в целом отвечают быстро, НЕ деградированы глобально
  в момент проверки.
- Ручной повтор `adb shell am start -W -n com.example.ao3_wrapper/
  .MainActivity` СРАЗУ ПОСЛЕ прогона → `ELAPSED_S=0.076`, `TotalTime: 0,
  WaitTime: 8, Complete` — НЕ воспроизвелось на разовую попытку постфактум
  (согласуется с флаки, не с детерминированной поломкой; но три попадания
  в ОДНОМ прогоне на разных позициях — рано, ~3-4-й тест из 19, и поздно,
  19-й/последний — говорят за системный, не единичный характер).

Значимо: время всего прогона (644.99s/~10:44) МЕНЬШЕ базового наблюдения
№1 (1525.73s/~25:25) — но это НЕ улучшение, а следствие того, что
`TimeoutError` (adb-shell, добавлен инкрементом 1) НЕ входит в фильтр
rerun-гейта AT-BUG-007 (`--only-rerun ReadTimeoutError|MaxRetryError`,
`pytest.ini`) — ошибки просто убивают тест на 30s без повторной попытки,
вместо того чтобы зависнуть на 120s дважды, как раньше с
`ReadTimeoutError`. Меньше времени, но ХУЖЕ покрытие (16/19 против 18/19)
— не путать со «стало лучше».

Дополнительный вопрос к диагностике корня (не решается в этом инкременте,
`framework/` не трогаю — scope задачи явно исключает правки framework):
классификация `ADB_SHELL_TIMEOUT=30` в докстринге инкремента 1 перечисляла
«обычные быстрые shell-команды (`settings put`, `pm clear`, `force-stop`,
`logcat -d`)» как обоснование константы — `am start -W` семантически ДРУГОЙ
класс: явно БЛОКИРУЮЩАЯ команда (ждёт полной прорисовки окна/onResume), не
гарантированно «быстрая» под нагрузкой/деградацией. Не берусь решать здесь,
верна ли сама константа для этого вызова, или 30s-таймаут корректно вскрыл
реальное зависание (что подтвердило бы гипотезу Lead — «длинная живая
сессия деградирует adb/Appium», наблюдение №2, — и расширило бы её
до `am start -W`/`seed_db.py`, ЛЮБОЙ сидинг-фикстуры, не только replay).
Оставляю оба варианта диагностике следующего инкремента.

Критерий Fixed по-прежнему не выполнен ни по одному пункту («диагностирован
корень», «2 чистых p0 подряд», «smoke без аномального удлинения» — этот
прогон формально уложился в разумное время, но ценой пропуска покрытия, что
не тот же критерий). `status` НЕ меняю — остаётся `Open` (по прямому
non-goal задачи test-maintainer). Полный вывод (traceback трёх ошибок)
приложен в отчёте задачи AT-BUG-005 этого же хода.
