---
key: "AT-BUG-078"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "TC-026 (long-press ссылки в WebView) не ассертирует ТЕКСТ снекбара «Opened in background (N tabs)» — дверь (б) BUG-059 наблюдаемо не покрыта"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-026", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-18T09:05:00Z"
updated: "2026-08-18T09:05:00Z"
archived: false
resolution: "done"
---

# TC-026 (long-press ссылки в WebView) не ассертирует ТЕКСТ снекбара «Opened in background (N tabs)» — дверь (б) BUG-059 наблюдаемо не покрыта

_Спроецировано из `bugs/AT-BUG-078.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-08-18 | dev-local 12 (без пересборки — правка только тестового кода) | TC-026 (`test_long_press_link_opens_background_tab_without_switching`) | 4× PASSED подряд (см. witness ниже); красная проба AssertionError на новом ассерте, откат байтовой копией подтверждён `git status --porcelain` пуст-до/пуст-после для чистого diff; `arch_check.py` — 0 ошибок (5 предзнак. warning не связаны); `python -m pytest scripts/tests -q` — 1494 passed, 1 skipped | test-maintainer: работа готова к верификации fix-verifier |
| 2026-08-18 | dev-local 12, source_commit `aa377e0ec9664fcd5439fec9391638fabf94f448` (без пересборки — верификация долга тестового кода, продукт не менялся; `state/app-under-test.yaml` built_at 2026-08-16T17:53:45Z) | TC-026 (`test_long_press_link_opens_background_tab_without_switching`) | Независимый живой прогон fix-verifier (`Invoke-Pytest tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching -v`): `tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching[listing_basic.mitm] PASSED [100%]`, `AT-BUG-026 device-liveness guard: recoveries this session = 0/2`, `1 passed in 35.01s`, `PYTEST_EXIT=0`. Чтением исходника подтверждён вызов `browser_steps.assert_opened_in_background_snackbar_text(driver, "Opened in background (1 tab)")` на `tests/test_tabs.py:307-308`, сразу после `long_press_work_link` (строка 297) и до `assert_tab_strip_visible` (строка 311) — ассерт из «Критерия готовности» действительно исполняется в этом прогоне, не только присутствует в диффе | **Verified** |

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

**2026-08-18 — test-maintainer, B4 fix.** Добавлен вызов
`browser_steps.assert_opened_in_background_snackbar_text(driver, "Opened
in background (1 tab)")` в `test_long_press_link_opens_background_tab_without_switching`
(`framework/tests/test_tabs.py:299-308`), сразу после `long_press_work_link`
и до `assert_tab_strip_visible`/переключения на фоновую вкладку — примитив
переиспользован без дублирования (используется также в TC-176). Текст
"(1 tab)" (единственное число) подтверждён по `MainActivity.kt:344-345`
(`plural = if (signal.openedCount == 1) "tab" else "tabs"`) — в этом
сценарии ровно ОДНО фоновое открытие за burst, в отличие от TC-176 (2
открытия, "(2 tabs)").

Живой прогон на текущей сборке (dev-local 12, без пересборки — правка
только тестового кода): 3× PASSED подряд ДО красной пробы + 1× PASSED
ПОСЛЕ отката красной пробы (итого 4× зелёных). Witness (дословный хвост
последнего прогона):
```
tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching[listing_basic.mitm] PASSED [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
============================= 1 passed in 34.41s ==============================
PYTEST_EXIT=0
```

Красная проба: временно подменил ожидаемый текст на `"Opened in
background (2 tabs)"` (тестовый код, `app-under-test/` не трогал — правка
продуктового счётчика недоступна агенту test-maintainer по границам
роли). Прогон дал `FAILED`, AssertionError ИМЕННО на новом ассерте:
`AssertionError: текст snackbar не совпадает дословно: 'Opened in
background (1 tab)' != 'Opened in background (2 tabs)'`
(`steps\browser_steps.py:2375`, вызван из `tests\test_tabs.py:307`) —
подтверждает различающую силу ассерта отдельно от двери (а). Откат —
байтовой копией (`scratchpad/test_tabs.py.AT-BUG-078.pre-redprobe.bak`,
снятой ДО порчи с уже применённым фиксом): `git status --porcelain --
framework/tests/test_tabs.py` до порчи и после отката — одинаковый
результат `M framework/tests/test_tabs.py` (тот же чистый diff фикса,
diff байтовых копий — `IDENTICAL`).

`arch_check.py`: 0 ошибок, 5 предсуществующих warning (2 allowlisted
tests-import исключения, 1 rule3-warning на TC-176 — не связаны с этой
правкой). `python -m pytest scripts/tests -q`: 1494 passed, 1 skipped —
без регресса.

Статус переведён `Open → Fixed` (guard-переход B4). Верификация —
fix-verifier (сборку приложения ждать не нужно, продуктовый код не
менялся).

**2026-08-18 — fix-verifier, D1.** Независимый живой прогон (не reuse-witness
test-maintainer'а) той же командой из DoD: `Invoke-Pytest
tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching
-v` — `PASSED`, `PYTEST_EXIT=0`, полный вывод в таблице выше. Сверено чтением
`tests/test_tabs.py:299-308`: вызов `assert_opened_in_background_snackbar_text`
с дословным ожидаемым текстом `"Opened in background (1 tab)"` присутствует и
исполнен именно ЗА тем прогоном, что дал PASSED (не только в диффе фикса).
Продуктовая сборка не менялась (`state/app-under-test.yaml`, source_commit
`aa377e0e`, built_at 2026-08-16) — это ожидаемо для `test_debt`-долга: критерий
D1 «сборка новее found_in» здесь не применим буквально (found_in —
verify-сессия BUG-059 от 2026-08-15 на этой же сборке; сама сборка не
менялась ни там, ни здесь, менялся только тестовый код framework/tests) —
DoD диспатча явно предписал прогон на текущей сборке без ожидания
пересборки, это и сделано. `status: Fixed → Verified`, `known_issue`
остаётся `"false"` (был `"false"` уже до этого — не «известная проблема»,
это закрытый тестовый долг). Лок снят.

**Дефекты-собратья (D-0043):** аналог не замечен — область (снекбар фонового
открытия вкладки) исчерпана двумя дверьми (а)/(б), обе теперь наблюдаемо
покрыты (TC-176 и TC-026 соответственно).

## Чек-лист качества
- [x] Проверены дубликаты: grep `bugs/` по `TC-026`/`assert_opened_in_background_snackbar_text` — единственное упоминание отсутствия ассерта до этого файла.
- [x] Суть долга ясна и воспроизводима: точные номера строк теста и продуктового кода приложены, grep-команда для проверки отсутствия вызова названа.
- [x] Severity: minor — не блокирует ни один существующий зелёный TC, дверь (а) полностью покрыта; риск — будущая нераспознанная регрессия именно на двери (б).
- [x] Ни одно изменение не внесено в `app-under-test/` (только чтение кода).
- [x] id — max+1 существующих в намespace AT-BUG (`AT-BUG-077` был максимальным на момент заведения).
