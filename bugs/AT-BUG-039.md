---
id: AT-BUG-039
title: "browser_steps.assert_tap_to_scroll_delta: диагностика scrollY снята ДО опроса, а не после — тот же класс, что AT-BUG-036"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Open
found_in: "критик-вход D1-верификации AT-BUG-036, 2026-08-02: класс-полнота проверена целиком по поверхности message= у wait_for/wait_until в framework/"
fixed_in: ""
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-02T02:11:33Z"
updated: "2026-08-02T02:11:33Z"
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

# AT-BUG-039 — замороженная диагностика в assert_tap_to_scroll_delta

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — тот же класс, что `AT-BUG-036`: дефект не роняет тест ложно, но уводит триаж падения не туда). Не зависит от сборки приложения — фикс целиком во `framework/steps/`.

## Суть долга

`framework/steps/browser_steps.py:750-757` (`assert_tap_to_scroll_delta`):

```python
    wait_until(
        driver, _matches, timeout=timeout,
        message=(
            f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
            f"(±{tolerance_px:.1f}px) относительно scrollY до тапа={scroll_before} "
            f"за {timeout}с (текущий scrollY={get_webview_scroll_y(driver)})"
        ),
    )
```

`get_webview_scroll_y(driver)` — аргумент вызова, вычисляется Python'ом ДО входа в `wait_until`, то есть ДО единственного последующего опроса (та же WebView round-trip латентность, ради которой опрос введён — докстринг `browser_steps.py:739-742`). При таймауте текст падения несёт scrollY, снятый ДО ожидания, под подписью «текущий» — мягче, чем `None` в исходном классе `AT-BUG-036` (там опрос вообще не завершался), но так же уводит триаж: значение неактуально, читается как «текущее состояние», а не как «то, что было в момент вызова».

Найден критиком при D1-верификации `AT-BUG-036` — обход сиблингов внутренней оси `framework/steps/`, заявленный при F1-ревью батча tabs (2026-07-31), оказался неполным именно на этом экземпляре (см. `bugs/AT-BUG-036.md`, поправка координатора 2026-08-02).

## Образец фикса
`framework/steps/app_steps.py::wait_persisted_tab_count` (после `AT-BUG-036` attempt 2): опрос сохраняет последнее наблюдение в замыкание/holder ВНУТРИ предиката, диагностика читает его ПОСЛЕ `wait_for`/`wait_until`, не до.

## Критерий готовности (Fixed)

- [ ] `assert_tap_to_scroll_delta` читает `scrollY` для диагностики ПОСЛЕ опроса (последнее реально наблюдённое значение), не до вызова `wait_until`.
- [ ] Красная проба: искусственный недостижимый `expected_delta` показывает в тексте падения scrollY, снятый ПОСЛЕ опроса (не устаревшее пред-опросное значение).
- [ ] Существующие вызывающие зелёные (потребители `assert_tap_to_scroll_delta` — canary tap-zone-guard тесты).
- [ ] arch_check/validate_frontmatter 0/0.
- [ ] Ни одно изменение не внесено в `app-under-test/`.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-02T02:11:33Z — координатор (Sonnet), заведение по докладу критик-входа D1 AT-BUG-036:**
Критик прошёл всю поверхность `message=` у `wait_for`/`wait_until` в `framework/steps`, `framework/screens`, `framework/web`, `framework/core` (перечень вхождений в его вердикте) и нашёл ровно один неучтённый экземпляр — этот. Не добавлено строкой в `bugs/AT-BUG-037.md` (тот же класс «диагностика ожидания», но файл был локом `test-maintainer` в момент находки — правило 4 CLAUDE.md, чужие незакоммиченные пути не трогать) — заведён отдельным test_debt. Диспатч по B4 — следующим проходом qa-loop, после AT-BUG-037.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не совпадает с AT-BUG-036 (другой файл/функция, тот же класс — сиблинг, не дубликат), AT-BUG-037 (N2/N2а — другой приём-дефект, «глотание исключения», не «пред-опросное вычисление диагностики»)
- [x] Severity обоснована влиянием: minor (уводит триаж, не роняет тест ложно; плюс лишний WebView round-trip на каждом вызове, включая зелёные)
- [x] Приложены материалы: вердикт критика D1-верификации AT-BUG-036 (2026-08-02)
- [x] Нет изменений кода приложения
