---
id: AT-BUG-058
title: "TC-096 замеряет холодный старт (force-stop+pm clear+am start -W) ПОД активной Appium-сессией — запуск не рапортует завершение, TimeoutError 60s; та же последовательность без сессии — 6/6 успешных, ~6.0-6.3s"
type: test_debt
debt_kind: broken_environment
severity: major
status: Fixed
found_in: "framework commit 8e4ff25 (тестируемая сборка приложения 1.11 (versionCode 12), build bfc8f41a — от сборки НЕ зависит, см. «Контрольный замер»)"
fixed_in: "framework (test-maintainer, 2026-08-10) — framework/tests/test_performance.py, framework/steps/perf_steps.py"
last_seen_in: "RUN-20260805-0437 (2026-08-05)"
test_cases: ["TC-096"]
runs: ["RUN-20260805-0437"]
duplicates: []
regression_of: ""
status_since: "2026-08-10T11:38:00Z"
updated: "2026-08-10T11:38:00Z"
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

# AT-BUG-058 — TC-096: замер холодного старта под живой Appium-сессией виснет на 60s

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: broken_environment`).
Поверхность: `framework/tests/test_performance.py::test_cold_start_within_relative_budget`
(`@pytest.mark.p1`, `@allure.id("TC-096")`), `framework/steps/perf_steps.py:26-44`
(`measure_cold_start`/`cold_start_baseline`), `framework/core/adb.py:20-45`
(`_run`, `ADB_LAUNCH_TIMEOUT=60`). Эмулятор `ao3_test_api34` (`emulator-5554`,
API 34, uptime 14.5ч на момент разбора), Appium `:4723`.

## Наблюдение

`RUN-20260805-0437` (regression на 1.11 (12)), disambiguation-сегмент, артефакты
СОХРАНЕНЫ (`runs/RUN-20260805-0437/allure/2176578a-…-result.json`, статус `broken`):

```
TimeoutError: adb -s emulator-5554 shell am start -W -n com.example.ao3_wrapper/
com.example.ao3_wrapper.MainActivity не вернул за 60s (AT-BUG-009)
steps/perf_steps.py:35 (measure_cold_start) ← perf_steps.py:44 (cold_start_baseline)
← tests/test_performance.py:50 (Given baseline)
```

Скриншот момента падения: приложение стоит на СИСТЕМНОМ splash (иконка AO3), то
есть первый кадр активити не отрисован к 60-й секунде. Приложенный лог сессии
несёт парный симптом UiAutomator2: `Timed out after 10251ms waiting for the root
AccessibilityNodeInfo in the active window`.

Изолированные перепрогоны (failure-analyst, 2026-08-05, та же сборка/эмулятор):

| # | Условие | Результат |
|---|---|---|
| 1 | `Invoke-Pytest -k test_cold_start_within_relative_budget -v` | FAILED, та же сигнатура, 83.89s |
| 2 | то же, ПОСЛЕ `Stop-NodeProcesses` + `Start-Appium` (свежий сервер, health-checked) | FAILED, та же сигнатура, 84.88s |

Оба раза падение — на ПЕРВОМ же замере baseline (полная длительность теста ≈
создание сессии + один 60-секундный таймаут).

## Контрольный замер (та же последовательность БЕЗ Appium-сессии)

`adb shell am force-stop` + `adb shell pm clear` + `adb shell am start -W`,
6 циклов подряд, тот же APK 1.11 (12), тот же эмулятор, ~10 минут спустя:

```
CYCLE 1 OK wall=7461ms TotalTime: 6264
CYCLE 2 OK wall=962ms            (тёплый no-op: вывод БЕЗ TotalTime, см. п.3 ниже)
CYCLE 3 OK wall=6766ms TotalTime: 6279
CYCLE 4 OK wall=6285ms TotalTime: 5797
CYCLE 5 OK wall=6674ms TotalTime: 6166
CYCLE 6 OK wall=6363ms TotalTime: 6028
```

6/6 без единого зависания. Логи системы для успешного цикла:
`ActivityTaskManager: Displayed com.example.ao3_wrapper/.MainActivity for user 0:
+6s231ms`. То есть приложение 1.11 (12) стартует холодно за ~6s, и цикл
«force-stop + pm clear + am start -W» сам по себе устойчив.

**Вывод:** различающая переменная — НАЛИЧИЕ ЖИВОЙ Appium/UiAutomator2-сессии во
время замера, а не сборка, не эмулятор и не сам примитив `am start -W`.

## Почему это долг тестовой системы, а не дефект приложения

1. Приложение опровергнуто контрольным замером выше (6/6, ~6s) и диффом сборки:
   1.11 = `77d65bc` (предикат авто-скачивания) + `bfc8f41` (строка заголовка
   диалога) — ни одна строка не касается запуска, Compose-инициализации, Room или
   WebView.
2. Код теста/фреймворка с прошлого ЗЕЛЁНОГО прогона TC-096 (`RUN-20260804-1624`)
   не менялся по существу: единственный коммит по этим путям —
   `8e4ff25`, и он лишь ДОБАВЛЯЕТ `adb.screen_density()` (24 строки, TC-148).
   Значит тест был красно-хрупким и раньше, а сорвался, когда среда стала
   медленнее (историческая калибровка автора теста: холодный старт 3728ms;
   сейчас bare ≈ 6100ms, x1.6).
3. Конструктивная причина в самом тесте: `test_cold_start_within_relative_budget`
   ДЕРЖИТ Appium-сессию (фикстура `driver`) все 6 циклов замера, хотя использует
   её ровно один раз — последней строкой `app_steps.wait_ui_ready(driver)`.
   Приложение под сессией повторно поднимается после `pm clear`, и завершение
   запуска системе не рапортуется в пределах `ADB_LAUNCH_TIMEOUT=60`
   (точный механизм не доказан; кандидаты: конкурирующий перезапуск приложения
   самой сессией и удержание UI-потока дампером UiAutomator2 — ровно тот симптом,
   что в приложенном логе).

## Что сделать (test-maintainer)

1. Развязать замер и сессию: делать `cold_start_baseline`/`measure_cold_start` БЕЗ
   активной Appium-сессии (например, сессия создаётся только для финального
   `wait_ui_ready`, или проверка «приложение фактически запущено» делается через
   adb, без `driver`).
2. Пока развязки нет — не маскировать таймаут увеличением `ADB_LAUNCH_TIMEOUT`:
   60s против 6s bare — это не «мало времени», это отсутствие рапорта.
3. Побочная находка того же замера (не причина падения, но ложный красный
   рядом): цикл 2 контрольного прогона вернул вывод БЕЗ `TotalTime` («тёплый»
   no-op старт) — на таком выводе `adb.parse_am_start_metrics` штатно бросает
   `RuntimeError`. `measure_cold_start` защищается предварительным
   `force_stop()`+`clear_app_data()`, но гонка наблюдалась даже с ними — стоит
   ретраить цикл при отсутствии `TotalTime`, а не падать.

## Обсуждение (test-maintainer, 2026-08-10T11:38:00Z) — Fixed

### Фикс

`framework/tests/test_performance.py::test_cold_start_within_relative_budget`
(руководство бага п.1 — развязка замера и сессии): `driver` остаётся
запрошенным параметром фикстуры (НЕ убран из сигнатуры теста) — иначе
device-liveness guard (B1, `conftest.py::pytest_runtest_setup`, триггерится
по `"driver" in item.fixturenames`, докстринг хука явно заявляет этот
инвариант «каждый device-тест запрашивает driver» как grep-проверенный) не
сработал бы перед setup ЭТОГО теста. Вместо изменения признака хука тест
сам немедленно закрывает полученную сессию (`driver_factory.quit_driver
(driver)`) ДО baseline/observed-замеров — измерение всех
`BASELINE_RUNS + 1` холодных стартов идёт полностью БЕЗ активной Appium-
сессии. Финальный `app_steps.wait_ui_ready` (проверка «приложение
фактически запущено») по-прежнему нужен через Appium-элемент
(`android.webkit.WebView` в дереве) — для него сессия создаётся ЗАНОВО
(`driver_factory.create_driver(no_reset=True)`) уже ПОСЛЕ всех замеров и
закрывается в `finally`.

`framework/steps/perf_steps.py::measure_cold_start` (руководство бага
п.3, побочная находка): добавлен капнутый ретрай
(`COLD_START_TOTALTIME_RETRIES=3`) на случай, если `am start -W` вернул
вывод без `TotalTime` (тёплый no-op старт) даже после
`force_stop()`+`clear_app_data()` — та самая гонка цикла 2 контрольного
замера этого бага. Честная попытка исчерпания: после 3 попыток поднимается
`RuntimeError` с исходной ошибкой в цепочке (`raise ... from last_exc`), не
молчаливый проброс единственной последней гонки и не бесконечный retry.
`cold_start_baseline` переиспользует ту же защиту без изменений (вызывает
`measure_cold_start` в цикле).

Пункт 2 руководства («не маскировать увеличением `ADB_LAUNCH_TIMEOUT`»):
таймаут не трогался, `settings.ADB_LAUNCH_TIMEOUT=60` не менялся.

### Верификация (test-maintainer, до передачи fix-verifier)

Изолированный прогон `Invoke-Pytest -k test_cold_start_within_relative_budget`
3 раза подряд, ПОСЛЕ фикса выше (framework/tests/test_performance.py +
framework/steps/perf_steps.py, НЕ app-under-test):

| # | Wall time | PYTEST_EXIT |
|---|---|---|
| 1 | 43.64s | 0 |
| 2 | 46.25s | 0 |
| 3 | 45.39s | 0 |

Никакого зависания на baseline (характерный симптом бага — единичный
60s-таймаут на ПЕРВОМ же замере, полная длительность прогона ≈84-85s) — все
три прогона укладываются в ~44-46s, порядка величины «5 холодных стартов ~6s
+ 1 observed + 1 создание/закрытие Appium-сессии для wait_ui_ready», без
следа TimeoutError. Бюджет не подгонялся (`BUDGET_MULTIPLIER`/
`BASELINE_RUNS`/`MIN_COLD_START_BUDGET_MS` не менялись) — все три прогона
прошли по относительному бюджету на честном замере, вопрос протухшей
исторической калибровки (baseline автора 3728ms vs текущий bare ~6100ms) не
материализовался как красный.

### Проверка на сиблингов (класс, не экземпляр — CLAUDE.md правило 9)

Класс: блокирующий `am start -W` под активной Appium/UiAutomator2-сессией.
Единственный ДРУГОЙ вызывающий тот же примитив — `app_steps.
restart_app_via_adb` (используется `test_tabs.py` TC-025,
`test_reading_ux.py` TC-125, `app_steps.
restart_app_via_adb_asserting_new_process` — TC-133/134), тоже вызывается
ПОКА `driver`-сессия теста ещё жива (сигнатура `restart_app_via_adb(driver)`
принимает параметр, но фактически им не пользуется — сам факт похож на этот
класс). Разница: `restart_app_via_adb` не делает предшествующий `pm clear`,
и в кодовой базе уже задокументировано (докстринг
`restart_app_via_adb_asserting_new_process`, `app_steps.py:606-613`), что
`measure_cold_start`/TC-096 — «независимый путь», отдельный от этого
вызывающего. Никаких открытых/исторических багов с зависанием TC-025/125/
133/134 на `am start -W` не найдено (`Grep bugs/` по
`restart_app_via_adb|TC-025|TC-134` — только AT-BUG-032, другой класс:
недоказанная смерть процесса, не таймаут). Без воспроизведённого/
наблюдённого зависания на этом вызывающем — новый test_debt-баг здесь НЕ
заводится (нет evidence, не спекуляция); при первом наблюдаемом
зависании `am start -W` на TC-025/125/133/134 см. этот раздел за
диагностической зацепкой.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
