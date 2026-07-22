---
id: AT-BUG-027
title: "Незащищённый driver.get() вне framework/steps/ — browser_screen.py (open_work) и perf_steps.py (measure_home_page_load_time), тот же класс, что AT-BUG-025"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "framework env, не зависит от сборки приложения; текущая тестируемая сборка 1.10 (versionCode 11), 6455af0cfc2c937e81975f59a250476c77aecb73"
fixed_in: "тестовая система: framework/screens/browser_screen.py (open_work -> navigate()) + framework/steps/perf_steps.py (measure_home_page_load_time -> navigate() + settings.PERF_MEASUREMENT_HANG_GUARD) + framework/config/settings.py (новая константа), 2026-07-22 (test-maintainer); сборка приложения не при чём"
last_seen_in: "1.10 (versionCode 11)"
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-22T18:15:00Z"
updated: "2026-07-22T18:15:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-027 — driver.get() без bounded-обёртки вне framework/steps/ (сиблинг AT-BUG-025)

## Окружение
Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: flaky_test`) — тот же класс, что `bugs/AT-BUG-025.md`
(`driver.get` может зависнуть неограниченно в WebView-контексте без
load-события, `driver.set_page_load_timeout` не реализован драйвером).
Обнаружен test-maintainer'ом при работе над AT-BUG-025 (доклад, вне scope
того диспатча, D-0037), подтверждён critic-входом при ревью того же диффа.

## Суть долга

Два места вызывают `driver.get()` напрямую, без `navigate()`-хелпера
(`framework/core/navigate.py`, вводимого AT-BUG-025):

- **`framework/screens/browser_screen.py:62`** (`BrowserScreen.open_work`) —
  `self.driver.get(f"https://archiveofourown.org/works/{work_id}")`. Тот же
  класс риска, тривиальный однослойный вызов — по оценке critic'а,
  переводится на `navigate(..., WEBVIEW_LOAD_TIMEOUT)` тем же паттерном,
  что уже применён к `open_stable_tall_page` в AT-BUG-025. Используется
  точечно (не в P0-smoke).
- **`framework/steps/perf_steps.py:60`** (`measure_home_page_load_time`) —
  `driver.get(browser_steps.HOME_URL)` — сам вызов ЯВЛЯЕТСЯ измеряемым
  интервалом (TC-097, performance). Наивное оборачивание
  `WEBVIEW_LOAD_TIMEOUT` испортит замер (тот же порядок величины) —
  требуется отдельный measurement-safe дизайн (например: bounded-таймаут
  СУЩЕСТВЕННО выше ожидаемого времени загрузки, только как fail-safe от
  вечного зависания, не как рабочий предел). НЕ чинить как AT-BUG-025 —
  своя спека.

## Критерий готовности (Fixed)

- `browser_screen.py:62` переведён на `navigate()` (или эквивалент) —
  bounded-таймаут на сам `driver.get()`, зелёный регресс использующих
  `open_work` тестов.
- `perf_steps.py:60` получил ОТДЕЛЬНОЕ measurement-safe решение (fail-safe
  верхний предел, не искажающий замер TC-096-099) — решение по дизайну за
  test-maintainer/Lead при диспатче, задокументировать выбор.
- Полнота: `grep -rn "driver\.get(" framework/` вне `navigate.py` не
  показывает необёрнутых вызовов (кроме обоснованно исключённых, если
  такие останутся — назвать явно).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| | | | | (D1 fix-verifier — общим правилом, после Fixed) |

## Обсуждение

**2026-07-22T14:40:00Z — координатор (Sonnet, degraded-режим):** заведено
по докладу test-maintainer (AT-BUG-025, D-0037 — не расширял scope сам) и
рекомендации critic-входа при ревью того диффа (подтвердил: оба места —
тот же класс, `browser_screen.py:62` тривиален и годен для батча
следующего B4-прохода, `perf_steps.py:60` требует отдельного дизайна и
чинить сейчас не стоит). Правило 4б/9: очередь пункта живёт в читаемом
носителе (bugs/*.md, не только в notes AT-BUG-025) — заведён явным
артефактом, чтобы не испариться.

---

**2026-07-22T18:15:00Z — test-maintainer (B4), фикс:**

**1. `framework/screens/browser_screen.py::BrowserScreen.open_work` (тривиальный
случай).** Переведено на уже принятый в этом репозитории хелпер
`framework.core.navigate.navigate` — тем же паттерном, что
`open_stable_tall_page` в `browser_steps.py` (AT-BUG-025): импорт
`from framework.core.navigate import navigate` и `from framework.config
import settings`, вызов заменён на
`navigate(self.driver, f"https://archiveofourown.org/works/{work_id}",
settings.WEBVIEW_LOAD_TIMEOUT)`. Единственный call-site (`rating_steps.py::
open_work_page`) параметра timeout не пробрасывает — сигнатура
`open_work(work_id)` не менялась.

**2. `framework/steps/perf_steps.py::measure_home_page_load_time` (measurement-safe
дизайн).** Голый `driver.get(browser_steps.HOME_URL)` — ЧАСТЬ измеряемого
интервала (TC-097, `time.monotonic()` вокруг него), поэтому наивная обёртка
`settings.WEBVIEW_LOAD_TIMEOUT` (40s) не годится: этот бюджет — тот же
порядок величины, что и наблюдаемые загрузки (2-3s) x возможный
`BUDGET_MULTIPLIER` (2.5) на РЕАЛЬНОЙ (не зависшей) деградации — обрезка на
этом пороге превратила бы информативный «загрузка заняла Xs, бюджет
провален» в голый `TimeoutError` без числа.

Вместо этого заведена ОТДЕЛЬНАЯ константа `settings.PERF_MEASUREMENT_
HANG_GUARD` (дефолт 60s, `AO3_PERF_HANG_GUARD` для переопределения) —
на порядок больше самой `WEBVIEW_LOAD_TIMEOUT` (которая уже щедрый запас
над наблюдаемыми единицами секунд: red-проба test-reviewer TC-097.md,
2026-07-22 — 2.42s) и заметно МЕНЬШЕ глобального `APPIUM_HTTP_TIMEOUT`
(120s, которым и без того ограничен любой HTTP-вызов к Appium, включая
голый `driver.get()`, через `client_config.timeout` в `driver_factory.
create_driver`) — то есть guard не расширяет риск-профиль, а сужает его:
ловит генуинный хенг (класс AT-BUG-025) раньше и с понятной,
perf-специфичной семантикой (`TimeoutError`, сконвертированный `navigate()`
из `ReadTimeoutError`/`MaxRetryError`, по-прежнему матчащий
`pytest.ini --only-rerun`), не дожидаясь общего 120s+compensating rerun.
Любое конечное (пусть и заметно деградировавшее) измерение остаётся на
порядок ниже этой границы и замеряется точно — измерение не искажено.
Полное обоснование числа — в комментарии к константе в `settings.py`.

`measure_home_page_load_time` теперь: `with contexts.in_webview(driver,
timeout): navigate(driver, browser_steps.HOME_URL,
settings.PERF_MEASUREMENT_HANG_GUARD)` — таймер (`time.monotonic()`) и
последующий `screen.wait_home_page_loaded(timeout)` не тронуты, замеряемый
интервал тот же, что и раньше, в happy-path.

**Полнота (grep-сверка).** `grep -rn 'driver\.get(' framework/ --include=*.py`
(вне `.venv`) — совпадения только в: `framework/core/navigate.py`
(реальный вызов внутри хелпера + докстринги), комментарии/докстринги
`framework/config/settings.py`, `framework/core/mitm.py`,
`framework/screens/browser_screen.py` (новый комментарий у `open_work` +
существующий комментарий про WEBVIEW-контекст, строка 325),
`framework/steps/app_steps.py`, `framework/steps/browser_steps.py`
(комментарии из AT-BUG-025), `framework/steps/perf_steps.py` (новый
докстринг), `framework/tests/test_errors.py` (комментарий, не вызов),
`framework/tests/test_navigate_timeout_unit.py`/`test_tabs.py` (упоминания
в докстрингах тестов/мок-объектов синтетического hang). Ни одного
реального необёрнутого вызова `driver.get(` вне `navigate.py` не осталось.

**Witness (дословно).**

`python -m pytest scripts/tests -q` (после фикса, обвязка не задета):
`650 passed in 13.68s`.

`python D:/AO3_tests/scripts/validate_frontmatter.py`: `ошибок 0,
предупреждений 0`.

`scripts/arch_check.py` (проверка архитектурных правил после правки
`browser_screen.py`/`perf_steps.py`/`settings.py`): `arch_check: ошибок 0,
предупреждений 0`.

`framework/tests/test_navigate_timeout_unit.py` (регресс-гвард на сам
хелпер `navigate()`, не тронут этим фиксом, сверка "не сломан"):
`5 passed in 4.37s`, `PYTEST_EXIT=0`.

Точечный прогон затронутых тестов (эмулятор `ao3_test_api34`,
`Install-MitmCA` + `Install-App` + `Start-Appium`), 3 прогона подряд каждый,
все зелёные, `PYTEST_EXIT=0`:

TC-097 (`perf_steps.py` фикс) —
`tests/test_performance.py::test_webview_first_load_within_relative_budget[ao3_home_smoke.mitm]`:
Run #1 `1 passed in 31.41s`. Run #2 `1 passed in 28.39s`. Run #3
`1 passed in 29.05s`. Тайминги в том же диапазоне, что до фикса
(TC-097.md ревью: «~29-30s каждый») — измерение не искажено новым
fail-safe.

TC-007/TC-008 (`browser_screen.py` фикс, after autotest locator fix,
не app-under-test) —
`tests/test_rating.py::test_rate_work_from_work_page_panel` (5 параметризаций)
+ `test_deselect_rating_on_work_page_panel`: Run #1 `6 passed in 206.87s`.
Run #2 `6 passed in 205.71s`. Run #3 `6 passed in 200.71s`.

Дополнительно (не входит в требование 3х, разовая сверка отсутствия
регресса по всей области нефункциональных TC-096-099 одним прогоном) —
`tests/test_performance.py` целиком: `4 passed in 138.69s`
(`test_cold_start_within_relative_budget`,
`test_webview_first_load_within_relative_budget`,
`test_no_crash_or_anr_during_smoke_path` — этот тест тоже проходит через
`rating_steps.open_work_page`/`browser_screen.py::open_work`, косвенно ещё
раз сверяет п.1 —, `test_memory_trend_recovers_after_closing_tabs`).

Cleanup выполнен: `Stop-NodeProcesses`, `adb emu kill`, `Get-Device` →
`NO DEVICE`.

Критерий готовности выполнен по всем 3 пунктам (оба места переведены на
bounded-навигацию/measurement-safe fail-safe, grep-сверка полноты чиста,
затронутые TC зелёные 3х подряд без искажения baseline). **Open → Fixed.**
