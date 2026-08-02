---
id: AT-BUG-037
title: "except TimeoutError глотает исключение wait_for, env-контекст теряется"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "критик-входы gitlab-bugs-publish/AT-BUG-036, 2026-08-01/02"
fixed_in: ""
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-02T00:00:00Z"
updated: "2026-08-02T00:00:00Z"
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

- [ ] Оба экземпляра (N2 `settings_steps.py:291-297` и N2а `perf_steps.py:140-153`) переведены на образец AT-BUG-036, attempt 2 (except TimeoutError as exc + переброс исходного при пустом holder / readings).
- [ ] Device-free юниты по образцу `test_wait_persisted_tab_count_diagnostics_unit.py` (обе ветки: читаемые наблюдения + диагностика в assert; падающий predicate + пробой исходного TimeoutError с контекстом).
- [ ] Существующие вызывающие зелёные (точечный прогон TC-025/TC-125 + tests из test_perf*.py достаточны).
- [ ] arch_check/validate_frontmatter 0/0.
- [ ] Ни одно изменение не внесено в `app-under-test/`.
- [ ] Остаток класса (N3/N5) явно именован строками этого бага, в очередь, не расширять scope этого диффа.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение
Канал человек ↔ фабрика.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых багов (AT-BUG-036 — класс назван, остатки явные; AT-BUG-026/029/032/033/034 — другие классы)
- [x] Severity обоснована влиянием: minor (flaky_test класс — уводит триаж в сторону, но не роняет тест ложно)
- [x] Приложены материалы: запись критика AT-BUG-036 (попутно attempt 1 регрессии + перечень N2/N2а/N3/N5)
- [x] Нет изменений кода приложения
