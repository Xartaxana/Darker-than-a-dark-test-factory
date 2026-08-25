---
key: "RUN-20260821-1100"
project: "AO3"
issueType: "run"
status: "run-needstriage"
priority: "p2"
summary: "RUN-20260821-1100"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-21T11:02:11Z"
updated: "2026-08-21T11:02:11Z"
archived: false
resolution: null
---

# RUN-20260821-1100

_Спроецировано из `runs/RUN-20260821-1100.md` (источник правды).
Статус в нашей машине: **NeedsTriage**._

# RUN-20260821-1100 — smoke на dev-local (12), build fdd3f728

## Контекст запуска

Триггер: **p3-n4-pilot-stack1-smoke** — прогон smoke-suite на стеке 1 как
параллельная нагрузка пилота N4 (два device-стека одновременно). Стек 1
(emulator-5554, AVD ao3_test_api34, `-WritableSystem`, CA — по манифесту
координатора уже установлен) поднят координатором ДО старта; я не вызывал
`Start-Emulator`/`Start-Appium`, только `Use-DeviceStack -N 1` (адопция
своей же лизы, `owner=user@WIN-35QE0JOJJUA`) + `Install-App` (Streamed
Install: Success, идемпотентно) в каждой команде.

Параллельно на хосте всё это время шёл стек 2 (emulator-5556, Appium
:4725) под отдельным воркером — по условию задачи не трогался (эмулятор,
порт, лиза, `framework/allure-results-2` не затрагивались ни одной моей
командой).

Suite: `Invoke-Pytest -m p0` (= smoke, см. `Invoke-Smoke`/`pytest.ini`
markers), `AO3_MODE=replay` (тот же режим, что baseline-прогон
RUN-20260819-1818 — CA/`-WritableSystem` требуются именно для replay).
Команда (канонической формой, `Set-Item Env:` вместо `$env:` — избегает
схлопывания `$env:` Bash-тулом, класс AT-BUG-091):

```
. D:\AO3_tests\scripts\env.ps1; . D:\AO3_tests\scripts\tasks.ps1;
Use-DeviceStack -N 1; Set-Item -Path Env:AO3_MODE -Value replay;
Invoke-Pytest -m p0
```

Запущено в фоне (`run_in_background`), дождался завершения синхронно тем
же ходом (`Wait-Process -Id 22684` дважды, 500с+500с — процесс живой
python.exe венва фреймворка).

## Witness — дословный итог pytest

```
collected 778 items / 729 deselected / 49 selected
...
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
=========================== short test summary info ===========================
[22 ERROR, 7 FAILED — полный список см. allure/ и лог ниже]
==== 7 failed, 20 passed, 729 deselected, 22 errors in 1003.26s (0:16:43) =====
PYTEST_EXIT=1
```

**Recovery-WARN/DeviceLivenessGuard:** ровно одна строка, счётчик **0/2**
(без токена `ENV_ISSUE`) — по критерию пилота это НОЛЬ recovery-событий.
Дублирую дословно, как требует DoD: `AT-BUG-026 device-liveness guard:
recoveries this session = 0/2`.

Итог: **20 passed / 7 failed / 22 errors** из 49 selected (729 deselected),
729 не в scope p0. `PYTEST_EXIT=1`.

## Наблюдение по корневой причине (НЕ вердикт — факт + собственная эмпирическая проверка)

Я НЕ триажу и не выношу вердиктов (это failure-analyst), но зафиксирую то,
что проверил сам, дословно — это прямо относится к цели пилота N4
(интерференция двух параллельных device-стеков).

**22 из 22 ERROR** — идентичный `RuntimeError` в `_ensure_replay_ca()`
(`tests/conftest.py:1038` → `core/mitm.py:952`):
```
RuntimeError: mitm-CA не обнаружен в системном хранилище доверия
(инструктирует прогнать Start-Emulator -WritableSystem / Install-MitmCA).
```
Проверил сам, независимо от pytest, ДВУМЯ вызовами (тот же canonical
`Use-DeviceStack -N 1` префикс) на живом стеке 1:
```
adb.exe shell ls /apex/com.android.conscrypt/cacerts/
  → adb.exe: more than one device/emulator
adb.exe -s emulator-5554 shell ls /apex/com.android.conscrypt/cacerts/
  → 01419da9.0
    04f60c28.0
    0d69c7e1.0
    10531352.0
    1ae85e5e.0
    ...
```
То есть CA **физически присутствует** на emulator-5554 (манифест
координатора верен) — но `framework/core/mitm.py::is_ca_installed()`
(строка 86) вызывает `adb shell ls ...` **без `-s <serial>`**, полагаясь
на `$env:ANDROID_SERIAL`, который `Use-DeviceStack` **не выставляет**
(выставляет только `AO3_DEVICE`/`APPIUM_URL`/`ALLURE_RESULTS`). При ДВУХ
одновременно подключённых устройствах (5554+5556, стек 2 живой) голый
`adb shell` падает `more than one device/emulator`; `ls_cp.stdout` при
этом пуст, код НЕ проверяет `returncode`, просто делает `"<hash>.0" in
stdout` → тихо False → «CA не установлен».

Ту же сигнатуру `adb.exe: more than one device/emulator` (уже дословно
напечатанную самим фреймворком, не моей проверкой) вижу и в stderr
одного из FAILED — `test_bridge_marker_present_live` (TC-066):
```
AT-BUG-064 WARNING: adb shell settings get http_proxy вернул код 1
(устройство offline/unauthorized?) -- stderr: 'adb.exe: more than one
device/emulator' -- get_device_proxy() не смог однозначно определить
текущий прокси, возвращаю None...
```
— это тот же паттерн (`core/mitm.py::get_device_proxy()`, строка 663,
тоже голый `adb shell` без `-s`).

**Дефекты-собратья (D-0043, доклад, не диагноз):** в `framework/core/mitm.py`
ещё МИНИМУМ 3 функции с тем же паттерном голого `adb shell` без `-s`:
`wait_device_proxy_reachable` (L526), `set_device_proxy` (L612),
`clear_device_proxy` (L630) — на фоне того, что `framework/core/adb.py:521`
в аналогичном месте уже явно адресуется `-s settings.DEVICE_NAME`. Похоже
на тот же класс B3 («голые adb-вызовы без адресации при двух устройствах
ломаются»), который манифест этой задачи явно называл риском для МОИХ
собственных команд, — но здесь он воспроизвёлся ВНУТРИ самого
фреймворка/приложения-под-тестом при параллельной работе двух стеков.

**Важная сверка для triage:** `source_commit` этого прогона (fdd3f728)
БУКВАЛЬНО совпадает с `source_commit` последнего Closed smoke
(RUN-20260819-1818, 49/49 passed) — сборка не менялась. Совпадение
build+resource, но 20/49 passed вместо 49/49, при том что практически все
падения группируются вокруг одного технического паттерна (адресация adb
при двух устройствах) — сильный сигнал в пользу ENV_ISSUE именно класса
«два стека одновременно», не регрессии приложения. Финальный вердикт по
каждому TC — за failure-analyst.

Остальные 5 FAILED (`test_backup_clear_restore_returns_original_data`,
`test_comment_only_not_in_any_rating_tab`, `test_no_crash_or_anr_during_smoke_path`,
`test_deselect_rating_on_work_page_panel`, `test_tag_button_present_iff_custom_tag_live`,
`test_main_pairing_checkbox_availability_live`) — `TimeoutException` на
поиске элементов bottom-nav pill / `UnknownError: cannot be proxied to
UiAutomator2 server because the instrumentation process is not running
(probably crashed)`. Не проверял их причину отдельно (не мой мандат) —
дословные трейсы лежат в allure/ и в фоновом выводе; называю как
кандидата на ту же ось «двух стеков» (ресурсная конкуренция CPU/host при
двух живых эмуляторах+Appium), НЕ утверждаю.

## Падения и триаж

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| 22× ERROR (18 distinct TC: TC-009,013,014,015,067,069,071,073,075,077,079,081,083,099,119,120,121,122 — полный список см. `tc_results`) | ERROR at setup: `RuntimeError: mitm-CA не обнаружен` из `_ensure_replay_ca` (`conftest.py:1038`→`mitm.py:952`); см. «Наблюдение по корневой причине» — CA физически на устройстве есть, `is_ca_installed()` бьётся о `adb.exe: more than one device/emulator` при голом `adb shell` без `-s` | не мой мандат (test-runner) | триаж → failure-analyst | allure/ |
| TC-066, TC-076, TC-078 (`*_live`, FAILED) | `TimeoutException` на `wait_ui_ready`/`assert_blurb_selector_matches_headings`; у TC-066 в stderr дословно `adb.exe: more than one device/emulator` (AT-BUG-064 warning, `get_device_proxy()`) | не мой мандат | триаж → failure-analyst | allure/ |
| TC-021 (`test_backup_clear_restore_returns_original_data`, FAILED) | трейс не разбирал детально (не мой мандат) — см. allure | не мой мандат | триаж → failure-analyst | allure/ |
| TC-017 (`test_comment_only_not_in_any_rating_tab`, FAILED) | `selenium...` (см. allure) | не мой мандат | триаж → failure-analyst | allure/ |
| TC-098 (`test_no_crash_or_anr_during_smoke_path`, FAILED) | `TimeoutException` на `open_tab(Library)`/`BottomNav._find_pill`; на соседнем тесте того же файла — `UnknownError: cannot be proxied to UiAutomator2 server because the instrumentation process is not running (probably crashed)` | не мой мандат | триаж → failure-analyst | allure/ |
| TC-008 (`test_deselect_rating_on_work_page_panel`, FAILED) | `TimeoutException` на `open_tab(Library)`/`BottomNav._find_pill` | не мой мандат | триаж → failure-analyst | allure/ |

Полный дословный вывод (2226 строк, все 29 не-passed трейсов) — в фоновом
логе `bbbk2mc9n.output` (артефакт сессии) и структурированно в
`runs/RUN-20260821-1100/allure/`.

## Условия закрытия прогона (Closed)
- [ ] Каждое падение имеет вердикт и связанное действие (баг / фикс теста / карантин) — НЕ выполнено, это работа failure-analyst
- [ ] Для APP_BUG существует или создан BUG-файл — н/п пока нет вердиктов
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована — не выполнялось (не мой шаг в этом ходе)

## Baseline-сверка (правило Lead 2026-08-11)

Последний Closed smoke с `source_commit` — RUN-20260819-1818 (fdd3f728).
Проверка предковости — СВОИМ вызовом этого хода, репо `app-under-test/`
(локальный чекаут app-under-test/.git):
```
git -C D:/AO3_tests/app-under-test merge-base --is-ancestor \
  fdd3f72884105d1453448e0c9a7f2b109588b182 \
  fdd3f72884105d1453448e0c9a7f2b109588b182
EXIT=0
```
`EXIT=0` — предковость держится ТРИВИАЛЬНО: `source_commit` текущего
прогона буквально совпадает с `source_commit` baseline (сборка не
менялась между прогонами). Это усиливает вывод раздела «Наблюдение по
корневой причине»: без единого изменения кода приложения тот же p0-набор
ушёл с 49/49 на 20/49 — расхождение объясняется средой прогона (пилот N4,
два одновременных device-стека), не приложением.

## Обновление state

`smoke_status` в `state/app-under-test.yaml` НЕ трогал этим ходом — задача
явно рамочена как пилотный/нештатный прогон («Это НЕ штатный фабричный
тик»), а причина мессового красного явно средовая (см. выше), не проверка
самой сборки. Решение обновлять ли `smoke_status` по этому прогону — за
координатором пилота/failure-analyst.
