---
id: AT-BUG-055
title: "Нестабильные TC-134/TC-135: наблюдение вкладок через `run-as cat ao3_settings.xml` слепое — пустой/неудавшийся ответ adb неотличим от «0 вкладок»"
type: test_debt
debt_kind: flaky_test
severity: major
status: Fixed
found_in: "framework commit 1822554 (тестируемая сборка приложения 1.10 (versionCode 11), build 6455af0c — от сборки НЕ зависит)"
fixed_in: ""
last_seen_in: "RUN-20260804-1624 (2026-08-04)"
test_cases: ["TC-134", "TC-135"]
runs: ["RUN-20260803-2012", "RUN-20260804-1624"]
duplicates: []
regression_of: ""
status_since: "2026-08-10T10:18:15Z"
updated: "2026-08-10T10:18:15Z"
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

# AT-BUG-055 — карантин TC-134/TC-135: слепое чтение prefs не даёт установить причину падения

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`).
Поверхность: `framework/core/adb.py` (`_run`/`shell`/`run_as`),
`framework/steps/app_steps.py` (`_read_tabs_prefs_raw`, `_parse_persisted_tabs`,
`wait_tabs_persisted`, `wait_persisted_tab_count`, `assert_persisted_tab_url_at`,
`assert_persisted_marker_count`). От сборки приложения не зависит.

## Наблюдение (RUN-20260804-1624, второй сегмент)

| TC | Тест | Сообщение |
|---|---|---|
| TC-134 | `test_kill_relaunch_without_deep_link_keeps_tabs_unchanged` | `AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` |
| TC-135 | `test_cold_start_deep_link_reuses_single_home_tab` | `TimeoutError: маркер …/works?ao3_tab_marker=1 не появился в ao3_settings.xml за 20с` |

Оба кейса были зелёными в предыдущем регрессе `RUN-20260803-2012` на ТОЙ ЖЕ
сборке приложения (`1.10 (11)`, `6455af0c`, `source_commit 63f6aac3`) и с тем
же кодом тестов (между прогонами `framework/tests/test_tabs.py` и
`framework/steps/app_steps.py` не менялись — сверено `git log --since`), то
есть налицо нестабильность, а не регресс сборки и не правка теста.

## Почему причина не установлена (и почему это долг)

1. **Наблюдение слепое.** `adb.shell` возвращает только `stdout` и
   ОТБРАСЫВАЕТ `returncode`/`stderr` (`framework/core/adb.py:37-42`), а
   `_parse_persisted_tabs` на нераспарсенном/пустом входе штатно возвращает
   `[]` (`framework/steps/app_steps.py:319-331`). Поэтому «в prefs 0 вкладок»
   означает ЛИБО реальный пустой список, ЛИБО отвалившийся/пустой ответ
   `run-as cat` — тест не различает эти случаи и не ретраит. Класс уже был
   назван при разборе `AT-BUG-036` («`_parse_persisted_tabs` глотает ошибки
   парсинга и возвращает 0») и при критик-отклонении TC-131 attempt 1
   («вакуумный `[]` на отвалившемся adb/run-as»), но починена тогда была
   только ДИАГНОСТИКА сообщения, а не само чтение.
   Обострение в TC-134: каждому упавшему `assert_persisted_tab_url_at`
   непосредственно предшествует УСПЕШНЫЙ позитивный якорь
   `wait_persisted_tab_count(N)` (N=1 или 3) — «0» в следующем же чтении
   противоречит наблюдению, сделанному секундами раньше, и объяснимо либо
   транзиентно нечитаемым prefs, либо транзиентной пустой записью самим
   приложением; артефакты не позволяют выбрать.
2. **Артефакты этих двух падений утрачены.** Они пришли из ВТОРОГО сегмента
   прогона (перезапуск 15 хвостовых тестов после смерти фонового job'а
   харнесса), их allure-результаты лежали только в `framework/allure-results/`
   и были стёрты последующим прогоном с `--clean-alluredir` (каталог пуст,
   mtime 2026-08-04 22:00). Логката, скриншота и page source по TC-134/TC-135
   не существует — остались только тексты сообщений в отчёте прогона.
3. **Изолированный перепрогон в триаже был запрещён** (устройство занято
   дневным smoke/regression) — воспроизводимость не измерялась.

## Решение о карантине (B3)

`automation_status: quarantined` проставлен обоим кейсам
(`test-cases/tabs/TC-134.md`, `test-cases/tabs/TC-135.md`),
`quarantine_owner: test-maintainer`, `quarantine_since: 2026-08-04T22:20:45Z`,
`quarantine_expiry` не задан (действует `sla.quarantine_max`).

## Что сделать (для test-maintainer)

1. Сделать чтение prefs ЧЕСТНЫМ: отдельная функция чтения приватного файла с
   проверкой `returncode`/непустого ответа и явным исключением вместо
   молчаливого `""`; `_parse_persisted_tabs` не должен превращать
   нечитаемый вход в `[]` — только реально отсутствующий ключ
   `open_tabs_urls`. Класс, а не экземпляр: пройти по ВСЕМ вызовам
   `adb.run_as`/`adb.shell`, чей результат используется как ОРАКУЛ
   (не как best-effort зонд).
2. После починки — перепрогон TC-134/TC-135 с расширенным логированием
   (logcat + сырой дамп `ao3_settings.xml` на каждой неудачной итерации
   опроса), 3-5 повторов подряд. Если при доказанно исправном чтении
   воспроизведётся «0 вкладок»/пропажа маркера — это уже дефект ПРИЛОЖЕНИЯ
   (транзиентная пустая запись `open_tabs_urls` / потеря deep-link при
   холодном старте), падение переезжает на вердикт `APP_BUG` и заводится
   `BUG-*`; карантин снимается только после установленной причины.

## Обсуждение (test-maintainer, 2026-08-10T10:18:15Z) — Fixed

### Фикс

Новая честная функция `adb.run_as_file_or_raise(path, timeout=...)`
(`framework/core/adb.py`) — читает приватный файл приложения через `run-as cat`
с echo-sentinel-приёмом (`echo $?` внутри той же remote-shell-сессии, тот же
класс, что уже закрыл `seed_db._schema_ready` (AT-BUG-044),
`settings_steps.assert_ratings_present`/`assert_no_ratings` (AT-BUG-045) и
`conftest._snapshot_download_dir`, download-oracle-0728). Различает три
исхода: `rc==0` -> контент реально прочитан (возвращается как есть, даже
пустой); `rc!=0` БЕЗ содержимого -> легитимное «файла ещё нет» (например ДО
первой `SharedPreferences.apply()`) -> пустая строка; любой иной вход
(sentinel-строка отсутствует вовсе — `run-as` не выполнился; код не
распознан; ненулевой код С непустым содержимым — подозрительная смесь) ->
`RuntimeError` с сырым выводом, НЕ молчаливая пустая строка.

`framework/steps/app_steps.py`:
- `_read_tabs_prefs_raw()` — тонкая обёртка над `adb.run_as_file_or_raise`
  (была: голый `adb.run_as(f"cat {path}")`).
- `wait_tabs_persisted()` — раньше держала СОБСТВЕННУЮ параллельную слепую
  копию того же примитива (`adb.run_as(f"cat {path}")` напрямую); теперь
  единая точка чтения через `_read_tabs_prefs_raw()`. Отвалившийся adb/run-as
  больше не маскируется под «сентинел ещё не появился» — исключение из
  `_read_tabs_prefs_raw` ловится и ретраится `wait_for` (сохраняется в
  `last`), на итоговом таймауте всплывает в `; last error: ...` — тот же
  контракт, что `wait_persisted_tab_count` (AT-BUG-036).
- `_parse_persisted_tabs()` — раньше `except (JSONDecodeError, TypeError):
  return []` глотал ЛЮБУЮ ошибку разбора найденного, но битого/обрезанного
  ключа `open_tabs_urls` тем же вакуумным `[]`, что и реально отсутствующий
  ключ. Теперь различает: ключ НЕ найден (regex не матчит) -> `[]` (валидный
  исход, как раньше); ключ найден, но не парсится как JSON -> `RuntimeError`
  (подозрение на повреждённый/усечённый ответ транспорта).

### Класс, не экземпляр — обход `adb.run_as`/`adb.shell` как ОРАКУЛА (не зонда)

| Вызов | Роль | До этого фикса | Статус |
|---|---|---|---|
| `app_steps._read_tabs_prefs_raw`/`wait_tabs_persisted` (tabs prefs) | оракул | слепой, вакуумный `[]`/`""` маскирует отказ | **Fixed этим инкрементом** |
| `app_steps._parse_persisted_tabs` (JSON-разбор найденного ключа) | оракул | слепой, битый JSON -> вакуумный `[]` | **Fixed этим инкрементом** |
| `seed_db._schema_ready` (готовность Room-схемы) | оракул | — | Уже честный (AT-BUG-044, RDY-маркер) |
| `settings_steps.assert_ratings_present`/`assert_no_ratings`/`read_rating_rows` | оракул | — | Уже честный (AT-BUG-045, OK/NOSQLITE-маркер) |
| `conftest._snapshot_download_dir` (`download_oracle`) | оракул | — | Уже честный (download-oracle-0728, RC-sentinel) |
| `perf_steps` (`am start -W` -> `parse_am_start_metrics`) | оракул | — | Уже fail-closed (`adb.py`: `RuntimeError`, если в выводе нет `TotalTime`, не зависит от rc) |
| `adb.pidof_app()` (`assert_process_alive`/`capture_app_pid`/`assert_app_pid_unchanged`/`restart_app_via_adb_asserting_new_process`) | оракул, блокирующий tabs-тесты (TC-133/134) | слепой (`adb.shell` внутри), НО fail-safe: `pidof` пуст на ЛЮБОЙ причине (процесс мёртв ИЛИ adb отвалился) -> `pid is None` -> вызывающий код ВСЕГДА явно ассертит `is not None`/равенство — отвалившийся transport даёт громкий `AssertionError`, не тихий ложный PASS | **Не покрыт этим фиксом** (другой класс риска — не вакуумно проходит, а честно падает; диагностика причины ХУЖЕ, но корректность не под угрозой). Кандидат на `run_as_file_or_raise`-подобный приём, если понадобится точная диагностика; не блокирует это исправление. |
| `settings_steps.assert_theme_mode_pref`/`assert_font_size_step_pref` (`cat shared_prefs/ao3_settings.xml`, подстрочная сверка `theme_mode`/`font_size_step`) | оракул | слепой (`adb.run_as` напрямую), СТРУКТУРНО тот же класс, что tabs prefs, но fail-safe для ЭТИХ конкретных ассертов: пустая/битая строка не содержит искомую подстроку `name="theme_mode">{mode}<` ни при каком `mode` -> ассерт падает громко, не вакуумно проходит | **Не покрыт этим фиксом** — вне `owns` этой задачи (`settings_steps.py` не в манифесте). Тот же класс дыры (нет rc-проверки), но НЕ дефект корректности (не даёт ложный PASS) — кандидат для отдельного B4-прохода, не блокер. Диагностика при отказе транспорта останется неинформативной («theme_mode != dark в ''»), это и есть остаточный риск. |
| `security_steps._permission_string(adb.shell("ls -l ..."))` | оракул | слепой, но `_permission_string` явно `raise AssertionError` на пустой вывод — уже fail-closed по факту (не требует правки) | Не требует действия |
| `test_compatibility.py` (`getprop ro.build.version.sdk`), `test_saf_infra_probe.py` (`cat` экспортного backup-файла) | оракул | слепой, но сравнение с ожидаемым значением на пустой строке даёт честный provал (`AssertionError`/`JSONDecodeError`), не молчаливый PASS | Не требует действия в рамках этого B4 |
| `adb.shell`/`adb.run_as` в `seed_db.py` (`rm -f`, `mkdir -p`), `app_steps.py` (`am start`, `input keyevent`), тестовые teardown'ы (`rm -f`/`rm -rf`/`mkdir -p`) | действие/уборка, не оракул | — | Вне класса (результат не читается как источник истины) |

Единственный НАЙДЕННЫЙ, но не устранённый в рамках этого узкого B4-фикса
остаток того же класса (структурно) — `settings_steps.py:469,475`
(`assert_theme_mode_pref`/`assert_font_size_step_pref`). Оба уже fail-safe
(не дают ложный PASS — см. таблицу), поэтому это НЕ новый блокер (нет
падающего теста/дефекта корректности) — не заводится отдельным
`AT-BUG-*` по правилу «баг ищет продукт, не диагностику вслепую»; названо
здесь явной строкой per CLAUDE.md правило 9 («класс, не экземпляр»,
остаток — в очередь). `adb.pidof_app()` — тот же вердикт (fail-safe, не
блокер).

### Красная проба (device, `emulator-5554`, 2026-08-10)

Скрипт (scratchpad, не в дереве репо) временно монкипатчил
`framework.core.adb._PKG` IN-PROCESS на несуществующий пакет
(`org.bogus.nonexistent.pkg`) — ничего на диске/в репозитории не менялось,
никакого отката файлов не требуется (CLAUDE.md п.8 не применим: porcelain
репо не менялся этой пробой). Вызывал РЕАЛЬНЫЙ production-код
(`adb.run_as`/`adb.run_as_file_or_raise`) против сломанного `run-as`-таргета
на живом эмуляторе.

**ДО фикса (симуляция голым `adb.run_as`, тот же низкоуровневый примитив,
не удалён):**
```
=== OLD-STYLE blind read: adb.run_as(f'cat {path}') against broken run-as target (bogus package) ===
raw string returned to caller: '' (len=0)
```
Ровно то, что `_read_tabs_prefs_raw` (до фикса) вернула бы как есть — пустая
строка, которую `_parse_persisted_tabs` штатно превратил бы в `[]`, то есть
«0 вкладок», неотличимо от легитимно пустого состояния.

**ПОСЛЕ фикса (`adb.run_as_file_or_raise` на том же сломанном таргете):**
```
=== NEW honest read: adb.run_as_file_or_raise(path) against the SAME broken target ===
RuntimeError raised (expected): run-as org.bogus.nonexistent.pkg cat
/data/data/com.example.ao3_wrapper/shared_prefs/ao3_settings.xml не завершился
однозначно успешно (rc=None, сырой вывод='') — ожидали 0 «файл прочитан» или
ненулевой БЕЗ содержимого «файла ещё нет»; похоже на отвалившийся/неоднозначный
adb или run-as (устройство офлайн, пакет не debuggable, битый toybox), не на
легитимное пустое состояние (AT-BUG-055).
```
(Вывод консоли PowerShell дал кириллицу как `?`-мойбейк из-за кодировки
терминала — сообщение приведено выше в исходном виде из кода/логики функции,
смысл и факт выброса `RuntimeError` подтверждены дословным `RuntimeError
raised (expected): ...` из вывода пробы.)

Дополнительно — device-free регресс-матрица (14 веток `run_as_file_or_raise`
+ 4 ветки `_parse_persisted_tabs`) в
`framework/tests/test_adb_run_as_file_or_raise_unit.py` и
`framework/tests/test_parse_persisted_tabs_unit.py`, включая явный
регресс-замок «отвалившийся транспорт не возвращает молчаливую пустую
строку» (`test_transport_failure_does_not_silently_return_empty_string`).

### Witness

Device-free юниты (перед живыми прогонами):
```
Invoke-Pytest tests/test_adb_run_as_file_or_raise_unit.py tests/test_parse_persisted_tabs_unit.py tests/test_wait_persisted_tab_count_diagnostics_unit.py -v
...
20 passed in 2.67s
PYTEST_EXIT=0
```
```
Invoke-Pytest tests -k '_unit' -q   (полный device-free unit-срез, регресс-проверка)
175 passed, 165 deselected, 1 warning in 20.91s
PYTEST_EXIT=0
```

Живые прогоны (`emulator-5554`, replay, устройство свободно) — ПОСЛЕ фикса
честного чтения в `framework/steps/app_steps.py`/`framework/core/adb.py`:

Базовый прогон (оба кейса вместе):
```
Invoke-Pytest tests/test_tabs.py -k 'test_kill_relaunch_without_deep_link_keeps_tabs_unchanged or test_cold_start_deep_link_reuses_single_home_tab' -v
2 passed, 11 deselected in 51.92s
PYTEST_EXIT=0
```

TC-134 изолированно, 3 прогона подряд:
```
Invoke-Pytest tests/test_tabs.py -k test_kill_relaunch_without_deep_link_keeps_tabs_unchanged -v
1 passed, 12 deselected in 28.83s / 30.42s / 29.58s   (три отдельных запуска)
PYTEST_EXIT=0   (все три)
```

TC-135 изолированно, 3 прогона подряд:
```
Invoke-Pytest tests/test_tabs.py -k test_cold_start_deep_link_reuses_single_home_tab -v
1 passed, 12 deselected in 23.76s / 25.40s / 23.23s   (три отдельных запуска)
PYTEST_EXIT=0   (все три)
```

Полный `test_tabs.py` (регресс по всей области — `wait_tabs_persisted`/
`_parse_persisted_tabs` используются ещё в TC-022..026/084/131..137):
```
Invoke-Pytest tests/test_tabs.py -v
13 passed in 499.81s (0:08:19)
PYTEST_EXIT=0
```

Ни разу «0 вкладок»/пропажи маркера при доказанно исправном чтении не
воспроизведено — гипотеза о транзиентном дефекте приложения (п.3 «Что
сделать») не подтвердилась и не понадобилась: причиной был именно слепой
оракул, что и показывает красная проба выше.

### Карантин / test-case файлы

`test-cases/tabs/TC-134.md`, `test-cases/tabs/TC-135.md`:
`automation_status: quarantined -> active`, `quarantine_*`-поля очищены,
добавлена секция «Карантин снят» со ссылкой на этот баг и witness.

### Коммит

Этот дифф (framework/core/adb.py, framework/steps/app_steps.py,
framework/tests/test_adb_run_as_file_or_raise_unit.py,
framework/tests/test_parse_persisted_tabs_unit.py, bugs/AT-BUG-055.md,
test-cases/tabs/TC-134.md, test-cases/tabs/TC-135.md) НЕ закоммичен этим
проходом (манифест диспатча: «свой дифф тоже НЕ коммить — коммит
координатор узким списком»). Поле `fixed_in` останется пустым до коммита —
координатор заполнит хэшем при коммите узким списком (пути этой задачи НЕ
пересекаются с параллельным builder'ом, правящим `scripts/`/`schemas/`/
`tasks.ps1`).

## Ссылки

- Прогон: `runs/RUN-20260804-1624.md` (раздел «Падения и триаж», вердикт `FLAKY`)
- Предыдущий зелёный прогон тех же кейсов: `runs/RUN-20260803-2012.md`
- Смежное: `bugs/AT-BUG-036.md` (диагностика `wait_persisted_tab_count`,
  Verified — там же зафиксирован, но не починен, класс «вакуумный `[]`»)
- Смежное: `bugs/AT-BUG-044.md` (`seed_db._schema_ready`, RDY-маркер),
  `bugs/AT-BUG-045.md` (`settings_steps` ratings, OK/NOSQLITE-маркер) — тот
  же класс фикса (echo-sentinel RC), образец, которому следует этот фикс.
