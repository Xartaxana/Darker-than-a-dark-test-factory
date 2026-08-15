---
id: AT-BUG-078
title: "TC-026 (long-press ссылки в WebView) не ассертирует ТЕКСТ снекбара «Opened in background (N tabs)» — дверь (б) BUG-059 наблюдаемо не покрыта"
type: test_debt
debt_kind: missing_evidence
severity: minor
status: Open
found_in: "fix-verifier, D1-верификация BUG-059 (task RUN-D1-BUG-059-verify), 2026-08-15"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-026"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-15T21:19:00Z"
updated: "2026-08-15T21:19:00Z"
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

# AT-BUG-078 — `test_long_press_link_opens_background_tab_without_switching` (TC-026) не проверяет текст снекбара фонового открытия

## Окружение

Не зависит от конкретной сборки приложения: долг тестовой системы
(`type: test_debt`, `debt_kind: missing_evidence` — недостающий ассерт в
автотесте, не дефект продукта). Обнаружено при D1-верификации BUG-059 на
`source_commit 59be96c6398786d33c878dbce33cb1ecde269374` (dev-local 12,
`built_at 2026-08-14T23:14:07Z`, содержит фикс `7a43fab8`).

## Суть долга

`bugs/BUG-059.md` («## Анализ», последний абзац) явно называет ДВЕ
независимые двери открытия фоновой вкладки, которые обязан закрывать фикс:
(а) long-press по карточке в Library, (б) long-press по ссылке внутри
WebView-страницы (`BrowserScreen.kt:718`, кейс TC-026).

Дверь (а) наблюдаемо покрыта: `TC-176`
(`framework/tests/test_tabs.py::test_background_open_snackbar_counts_background_opens_not_total`)
дословно ассертирует текст снекбара через
`browser_steps.assert_opened_in_background_snackbar_text` — зелёный прогон
на этой сборке подтверждает burst-семантику счётчика.

Дверь (б) автоматизирована (`TC-026`,
`framework/tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching`,
строки 279-316), но её Then-цепочка проверяет ТОЛЬКО:
- `browser_steps.assert_tab_strip_visible` (факт появления вкладки в strip);
- `browser_steps.assert_active_tab_url` (исходная вкладка осталась активной);
- после переключения — что фоновая вкладка показывает корректный URL.

Ни разу не вызывается `assert_opened_in_background_snackbar_text` — текст
снекбара («Opened in background (N tabs)») на этом пути тестом НЕ читается
вовсе. Grep по телу теста (`grep -n
"test_long_press_link_opens_background_tab_without_switching" -A 40
framework/tests/test_tabs.py`) подтверждает отсутствие вызова.

## Почему это осталось приемлемым для верификации BUG-059, но не закрывает риск навсегда

Код-эмпирика (не заменяет device-witness, но легитимна для D1 carve-out
недостающего наблюдения по конкретной паре кейс/тест): оба входа фонового
открытия используют ОДНУ и ту же функцию `BrowserViewModel.openTab` —

- `BrowserScreen.kt:718` (дверь б, long-press ссылки в WebView):
  `viewModel.openTab(url, background = true)`
- `MainActivity.kt:607` (дверь а, `onOpenInBackground` из Library-overlay):
  `browserViewModel.openTab(url, background = true)`

Внутри `openTab` (`BrowserViewModel.kt:271-298`) сигнал строится ОДНИМ
общим приватным счётчиком burst'а: `BackgroundTabOpen(++backgroundOpenSeq,
++backgroundOpenBurst)` (`:281`), без ветвления по источнику вызова. Это
структурно подтверждает, что фикс коммита `7a43fab8` («Both doors route
through openTab, so one counter covers both» — дословно из commit message)
покрывает дверь (б) тем же механизмом, что зелёно подтверждён для двери (а)
через TC-176. Но это чтение кода, НЕ живой прогон — дверь (б) остаётся
наблюдаемо непокрытой: регрессия, которая сломала бы ТОЛЬКО ветку
`BrowserScreen.kt:718` (например, будущий рефакторинг, разводящий вызов
через отдельный путь без `openTab`), не будет поймана ни одним
существующим автотестом.

## Критерий готовности (Fixed)

- `test_long_press_link_opens_background_tab_without_switching` (или новый
  выделенный тест TC-026) добавляет вызов
  `browser_steps.assert_opened_in_background_snackbar_text(driver, "Opened
  in background (1 tab)")` сразу после `long_press_work_link` и до
  переключения на фоновую вкладку (примитив уже существует и используется
  в TC-176 — переиспользовать, не дублировать).
- Красная проба: временный откат счётчика на `newTabs.size` (или
  эквивалентная порча) даёт `AssertionError` именно на новом ассерте —
  подтверждает различающую силу для двери (б) отдельно от двери (а).
- `arch_check.py` + `python -m pytest scripts/tests -q` — без регресса.
- Ревью test-reviewer (F1) на добавленный ассерт.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-15 — fix-verifier, заведение при D1-верификации BUG-059.**
DoD диспатча прямо предписывал: если дверь (б) не ассертирует число
дословным способом — завести test_debt-баг, связанный с BUG-059, по
образцу `AT-BUG-077.md` (D-0043, «доложи аналог», не молчаливый пропуск).
Дверь (б) кодово подтверждена как закрытая тем же фиксом (см. «Почему это
осталось приемлемым» выше), но наблюдаемое покрытие — неполное; это и есть
предмет долга. `BUG-059` переводится в `Verified` на основании (i)
device-witness двери (а) через TC-176 и (ii) код-эмпирики общего
`openTab`-пути для двери (б) — остаточный риск двери (б) полностью
переносится в этот долг, отдельно не блокирует верификацию продуктового
бага.

## Чек-лист качества
- [x] Проверены дубликаты: grep `bugs/` по `TC-026`/`assert_opened_in_background_snackbar_text` — единственное упоминание отсутствия ассерта до этого файла.
- [x] Суть долга ясна и воспроизводима: точные номера строк теста и продуктового кода приложены, grep-команда для проверки отсутствия вызова названа.
- [x] Severity: minor — не блокирует ни один существующий зелёный TC, дверь (а) полностью покрыта; риск — будущая нераспознанная регрессия именно на двери (б).
- [x] Ни одно изменение не внесено в `app-under-test/` (только чтение кода).
- [x] id — max+1 существующих в намespace AT-BUG (`AT-BUG-077` был максимальным на момент заведения).
