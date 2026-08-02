---
key: "AT-BUG-037"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "except TimeoutError глотает исключение wait_for, env-контекст теряется"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-085", "test_case:TC-086", "test_case:TC-099", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-02T02:41:00Z"
updated: "2026-08-02T02:41:00Z"
archived: false
resolution: "done"
---

# except TimeoutError глотает исключение wait_for, env-контекст теряется

_Спроецировано из `bugs/AT-BUG-037.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-037 — долг класса TimeoutError-глотания при опросе

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — класс порчи окружающего контекста дефектом фреймворка: потеря env-диагностики при ошибке опроса). Не зависит от сборки приложения — фикс целиком во `framework/steps/`.

## Суть долга

Остаток класса, вскрытого критик-входом приёмки AT-BUG-036 (attempt 2, попутно fix-attempt-1 регрессии): оборотень приём `except TimeoutError: pass` встречается в двух других местах фреймворка, **строже, чем в уже исправленном** `wait_persisted_tab_count` — опрос может упасть полностью, а исходное исключение (несущее диагностику `; last error: ...` для fail-fast-детектора среды AT-BUG-009) теряется.

### Экземпляр N2 — образец, откуда приём был скопирован в app_steps
`framework/steps/settings_steps.py:291-297` (`assert_filter_profile_count`): тот же приём `except TimeoutError: pass` — именно отсюда он был скопирован в `wait_persisted_tab_count` при attempt 1 AT-BUG-036. САМ settings_steps НЕ исправлен (правка attempt 2 легла только в `app_steps.py`); этот экземпляр — предмет ЭТОГО бага. [Уточнено Lead при приёмке 2026-08-02: исходная формулировка читалась как «уже исправлен».]

### Экземпляр N2а — новый, найден критиком attempt 2
`framework/steps/perf_steps.py:140-153` (`wait_memory_settled`): **строже, чем N2**. На предикате, падающем на каждом опросе (например, зависший `adb.total_pss_kb()`), `readings` остаётся пустым:
```python
except TimeoutError: pass
return readings[-1]  # IndexError, если readings пуст
```
Падение выглядит багом самого фреймворка, а не деградацией среды — env-причина уничтожена полностью (не просто ослаблена, как в N2).

### Примыкающие классы — не входят в скоуп
- **N3**: вакуумный класс «последнее наблюдение: 0» при мёртвом adb неотличимо от честного нуля (предсуществует, не введён AT-BUG-036).
- **N5**: смешанная ветка (≥1 успешное наблюдение, затем зависший adb) в ИСПРАВЛЕННОМ `wait_persisted_tab_count` даёт `AssertionError` в тексте, но БЕЗ литерала `TimeoutError`/`ReadTimeoutError` (риск для fail-fast-детектора; не блокер, контекст сохранён).

Критерий готовности (Fixed) НЕ требует правку N3/N5, они именуются явными строками остатка в этом баге.

## Критерий готовности (Fixed)

- [x] Оба экземпляра (N2 `settings_steps.py:291-297` и N2а `perf_steps.py:140-153`) переведены на образец AT-BUG-036, attempt 2 (except TimeoutError as exc + переброс исходного при пустом holder / readings).
- [x] Device-free юниты по образцу `test_wait_persisted_tab_count_diagnostics_unit.py` (обе ветки: читаемые наблюдения + диагностика в assert; падающий predicate + пробой исходного TimeoutError с контекстом).
- [x] Существующие вызывающие зелёные (точечный прогон TC-025/TC-125 + tests из test_perf*.py достаточны). **Уточнение по факту:** ни TC-025 (`test_tabs.py`), ни TC-125 (`test_reading_ux.py`) фактически НЕ вызывают `settings_steps`/`perf_steps` (оба используют только `app_steps`/`browser_steps`) — прогон этих двух ничего не верифицировал бы про этот фикс. Реальные вызывающие: `settings_steps.assert_filter_profile_count` — TC-085/TC-086 (`test_filter_profiles.py`); `perf_steps.wait_memory_settled` — TC-099 (`test_performance.py`, буквально уже назван в критерии как «tests из test_perf*.py»). Верифицировано этой парой (см. таблицу ниже), 3 прогона подряд зелёные.
- [x] arch_check/validate_frontmatter 0/0.
- [x] Ни одно изменение не внесено в `app-under-test/`.
- [x] Остаток класса (N3/N5) явно именован строками этого бага, в очередь, не расширять scope этого диффа (правки не вносились).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-02 | app-debug.apk (без изменений app-under-test, переустановлена после fix во framework/) | Device-free: `framework/tests/test_assert_filter_profile_count_diagnostics_unit.py` (2), `framework/tests/test_wait_memory_settled_diagnostics_unit.py` (2), `test_wait_persisted_tab_count_diagnostics_unit.py` (2, регресс-гвард образца) — `PYTEST_EXIT=0`, 6 passed. Live (emulator-5554, `Start-Emulator -WritableSystem` → `Install-App` → `Start-Appium`): TC-085+TC-086 (`test_filter_profiles.py`) и TC-099 (`test_performance.py::test_memory_trend_recovers_after_closing_tabs`) — 3 прогона подряд, каждый `PYTEST_EXIT=0` (прогон 1: TC-085/TC-086 отдельно `2 passed in 132.60s`, TC-099 отдельно в составе `test_performance.py` `4 passed in 154.58s`; прогон 2: TC-085+TC-086+TC-099 вместе `3 passed in 165.70s`; прогон 3: те же три `3 passed in 164.06s`). `arch_check.py`: ошибок 0, предупреждений 0. `validate_frontmatter.py`: ошибок 0, предупреждений 0. | Все прогоны зелёные, диагностика подтверждена unit-тестами (реальное последнее наблюдение вместо None/IndexError; исходный TimeoutError с `; last error: ...`-контекстом при пустых наблюдениях) | Fixed |
| 2026-08-02 | app-debug.apk (переустановлена этим прогоном через `Install-App`, без изменений app-under-test — только `framework/steps/settings_steps.py`+`framework/steps/perf_steps.py`) | **Независимая верификация fix-verifier** (таблица выше — самопрогон test-maintainer, не заменяет). Код: прочитан `settings_steps.py::assert_filter_profile_count` (291-317) и `perf_steps.py::wait_memory_settled` (117-174) — оба несут `except TimeoutError as exc`/`except TimeoutError:` с проверкой `last["value"] is None`/`not readings` и `raise` без аргументов (проброс исходного TimeoutError целиком) при пустом наблюдении; иначе честный `AssertionError` (settings_steps, с `; ожидание прервано: {wait_err}`) / `return readings[-1]` (perf_steps). Device-free (свой прогон, эмулятор не поднимался для этого шага): `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_assert_filter_profile_count_diagnostics_unit.py tests/test_wait_memory_settled_diagnostics_unit.py -v"` → `test_assert_filter_profile_count_shows_last_observation_on_readable_timeout PASSED`, `test_assert_filter_profile_count_preserves_timeout_context_on_failing_predicate PASSED`, `test_wait_memory_settled_returns_last_observation_when_never_settles PASSED`, `test_wait_memory_settled_preserves_timeout_context_on_failing_predicate PASSED` — `4 passed in 4.88s`, `PYTEST_EXIT=0` (обе ветки каждой функции). Live (свой независимый прогон, свежий цикл `Start-Emulator -WritableSystem` → `Get-Device`→`DEVICE: emulator-5554` → `Install-App`→`Success` → `Start-Appium`→ready:4723): `Invoke-Pytest tests/test_filter_profiles.py -v` → 5 passed in 304.53s, включая `test_rename_filter_profile_keeps_query_string[listing_basic.mitm] PASSED` (TC-085) и `test_rename_filter_profile_to_duplicate_name PASSED` (TC-086), `PYTEST_EXIT=0`; `Invoke-Pytest tests/test_performance.py::test_memory_trend_recovers_after_closing_tabs -v` → `test_memory_trend_recovers_after_closing_tabs[listing_basic.mitm] PASSED`, `1 passed in 38.53s`, `PYTEST_EXIT=0` (TC-099). `arch_check.py`: ошибок 0, предупреждений 0. `validate_frontmatter.py`: ошибок 0, предупреждений 0. Сверка скоупа: `git diff HEAD -- framework/steps/app_steps.py` пуст — N3/N5 (в `app_steps.py::wait_persisted_tab_count`) не тронуты этим диффом. | Все связанные TC (TC-085/TC-086/TC-099) прогнаны независимо и зелёные; unit-пробы (обе ветки на функцию) зелёные; N3/N5 подтверждённо не тронуты | **Verified** |

## Обсуждение
Канал человек ↔ фабрика.

test-maintainer (2026-08-02): N2 (`settings_steps.assert_filter_profile_count`) и N2а (`perf_steps.wait_memory_settled`) переведены на образец `app_steps.wait_persisted_tab_count` (AT-BUG-036 attempt 2) — `except TimeoutError as exc`, проброс исходного `TimeoutError` целиком (`raise` без аргументов), если наблюдений не было вовсе, иначе честный `AssertionError`/возврат последнего наблюдения. Критерий готовности п.3 (TC-025/TC-125) уточнён по факту кода — эти два теста не используют исправленные функции; верификация проведена реальными вызывающими (TC-085/TC-086/TC-099), см. таблицу выше. N3/N5 не тронуты (вне скоупа, как и было названо при заведении бага). Новых блокеров/долгов не обнаружено.

fix-verifier (2026-08-02, независимая верификация D1): подтверждаю самопрогон test-maintainer собственным прогоном (см. вторую строку таблицы) — код обеих функций сверен построчно, оба unit-файла прогнаны заново (обе ветки каждой функции, `4 passed`), TC-085/TC-086/TC-099 прогнаны на свежем цикле эмулятора независимо (не переиспользовал вывод test-maintainer), `arch_check`/`validate_frontmatter` 0/0, N3/N5 (`app_steps.py`) подтверждённо не тронуты (`git diff` пуст). `status: Fixed → Verified`. Дополнительно по классу (D-0043, «чини класс — доклад аналогов»): прошёл `grep -rn "except TimeoutError"` и `except.*:\s*pass` по `framework/steps/` и `framework/core/` целиком в поисках ещё не названных экземпляров, кроме N2/N2а/N3/N5. Найдено два кандидата, но оба — НЕ этот класс: (1) `browser_steps.py:1796` (`open_unreachable_url`, `except TimeoutError: pass`) — НЕ этот класс, но обоснование ниже исправлено критиком при приёмке (2026-08-02): исходная формулировка ошибочно ссылалась на «собственный `wait_for`-контекст `; last error: ...`» у следующего шага — на деле `assert_error_page_shown` использует `wait_until`/selenium `TimeoutException`, литерал `; last error:` производит только `core/waits.py::wait_for`. Верный механизм: пойманный здесь `TimeoutError` — ОЖИДАЕМЫЙ исход сценария (URL недостижим), не единственный env-сигнал; он рождается только в `core/navigate.py:97-98` из `ReadTimeoutError`/`MaxRetryError`, а зависший HTTP-канал на следующем шаге воспроизводится сырым `ReadTimeoutError`, которого нет в `_IGNORED` (`core/waits.py:20`) — летит наружу без подавления и матчит fail-fast-детектор напрямую; мёртвая сессия даёт `WebDriverException` уже в самом `navigate`, который перебрасывается. Точки безвозвратной потери, как в N2/N2а, здесь нет. (2) `adb.py:100` (`device_present`) и `adb.py:131` (`_wait_package_service_ready`) — оба возвращают явный сентинел (`False`/`""`), не глотают исключение молча в духе N2/N2а: `device_present` — это САМ guard среды (AT-BUG-026), а не caller-facing `wait_for`-обёртка, которой нужна пробрасываемая диагностика; `_wait_package_service_ready` — намеренный fail-soft внутри собственного poll-цикла с финальным `RuntimeError`, несущим контекст (сколько попыток/сколько ждали) — не теряет диагностику, формирует свою. Ни один из двух кандидатов не требует правки в рамках этого бага; называю их явно, чтобы не оставлять молчаливым — если Lead сочтёт иначе, оба — кандидаты на новый task_id, не расширение скоупа AT-BUG-037.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых багов (AT-BUG-036 — класс назван, остатки явные; AT-BUG-026/029/032/033/034 — другие классы)
- [x] Severity обоснована влиянием: minor (flaky_test класс — уводит триаж в сторону, но не роняет тест ложно)
- [x] Приложены материалы: запись критика AT-BUG-036 (попутно attempt 1 регрессии + перечень N2/N2а/N3/N5)
- [x] Нет изменений кода приложения
