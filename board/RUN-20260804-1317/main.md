---
key: "RUN-20260804-1317"
project: "AO3"
issueType: "run"
status: "run-needstriage"
priority: "p2"
summary: "RUN-20260804-1317"
assignee: "failure-analyst"
reporter: "qa-agents"
labels: ["run", "wip:failure-analyst"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T11:20:00Z"
updated: "2026-08-04T11:20:00Z"
archived: false
resolution: null
---

# RUN-20260804-1317

_Спроецировано из `runs/RUN-20260804-1317.md` (источник правды).
Статус в нашей машине: **NeedsTriage**._

# RUN-20260804-1317 — canary (live baseline) на 1.10 (11)

## Контекст запуска

Триггер: прямое слово владельца — canary-baseline (live) как предусловие
включения canary-половины в репетицию тёмного дня (docs/11 §1, гейт
«Canary»: «live-baseline зелёный И правило "Ежедневный canary" включено
в rules.yaml, ЛИБО явное решение владельца репетировать без дневной
canary-половины»).

Окружение уже было поднято этой же сессией ДО диспатча (не поднималось
заново): эмулятор `ao3_test_api34` (emulator-5554, `-WritableSystem`, CA
mitmproxy в apex store — подтверждено при исходном буте сессии), APK
переустановлен (`Install-App` → Success), Appium на `:4723`. Позитивная
сверка перед прогоном: `. D:\AO3_tests\scripts\tasks.ps1; Get-Device` →
`DEVICE: emulator-5554`. Фреймворк на коммите `c03aa93e` (2026-08-03), HEAD
репо `252120b2`.

**Набор/маркер**: канонический вид canary по `.claude/skills/run-suite/
SKILL.md` — `pytest -m live` внутри `tests/canary` (`Invoke-Pytest
tests/canary -m live`). Коллекция: 23 items в `tests/canary`, 13
deselected (replay-парные тесты того же файла), 10 selected — все с
`@allure.id` TC-066/068/070/072/074/076/078/080/082/118, соответствуют
таблице `test_ao3_selectors.py`. Минимальный live-набор (10 тестов), как
и предписано (AO3 — сторонний сайт, без нагрузки).

**Мелкая находка при запуске (известный класс, не новая):** попытка
экспортировать `$env:AO3_MODE='live'` через Bash-тул тем же путём, что и
ранее в `RUN-20260803-2012` («Дефекты-собратья», пункт 2), снова разбилась
об экранирование `$` — переменная не установилась, PowerShell вернула
`CommandNotFoundException` на первой строке лога. **Функционально не
повлияло**: `framework/config/settings.py:46` — `MODE = os.environ.get(
"AO3_MODE", "live").lower()`, дефолт уже `"live"`, что и требовалось; сам
`-m live` маркер-фильтр в pytest отобрал ровно live-тесты независимо от
значения `AO3_MODE`. Отмечаю как повторный экземпляр уже известного
классового наблюдения (не чиню — это чужая находка для Lead, см.
`RUN-20260803-2012` пункт 2 «Дефекты-собратья»).

## Итог

10 уникальных canary/live тестов, **9 passed, 1 failed**, 0 skipped, 0
quarantined. Длительность (по терминальной сводке pytest): 236.80s
(0:03:56). `AT-BUG-026 device-liveness guard: recoveries this session =
0/2` — guard ни разу не срабатывал за прогон.

**PYTEST_EXIT=1** — witness (дословный хвост вывода):

```
tests\canary\test_ao3_selectors.py ......F...                            [100%]

================================== FAILURES ===================================
________________ test_main_pairing_checkbox_availability_live _________________
...
tests\canary\test_ao3_selectors.py:319:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
steps\browser_steps.py:1710: in open_live_sort_filter_form_relationship_ready
    open_live_listing(driver, url)
steps\browser_steps.py:1307: in open_live_listing
    with contexts.in_webview(driver):
core\contexts.py:39: in in_webview
    driver.switch_to.context(name)
E       selenium.common.exceptions.WebDriverException: Message: A new session could not be created. Details: session not created
E       from no such execution context: loader has changed while resolving nodes
E         (Session info: chrome=113.0.5672.136)
.venv\Lib\site-packages\appium\webdriver\errorhandler.py:125: WebDriverException
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
=========================== short test summary info ===========================
FAILED tests/canary/test_ao3_selectors.py::test_main_pairing_checkbox_availability_live
=========== 1 failed, 9 passed, 13 deselected in 236.80s (0:03:56) ============
PYTEST_EXIT=1
```

Полный лог сохранён (scratchpad сессии,
`canary_run.log`); `allure-results/` (44 файла) в
`framework/allure-results/` — источник `tc_results` выше (сверка
`@allure.id` каждого result-файла напрямую, allure-статус упавшего теста
— `broken`, в `tc_results` записан как `failed` по словарю схемы
run.schema.yaml, который не различает broken/failed).

**Cloudflare bot-check (R-03):** сигнатура НЕ встречена ни в одном из 10
прогонов (ни в тексте ошибки/стектрейса, ни в терминальном выводе) —
проверено просмотром полного лога. Факт, не вердикт.

## Падения (факт, без вердикта — триаж вне мандата test-runner)

| Тест (TC) | Ошибка (кратко) | Allure-статус | Артефакты |
|---|---|---|---|
| test_main_pairing_checkbox_availability_live (TC-078) | `selenium.common.exceptions.WebDriverException: session not created from no such execution context: loader has changed while resolving nodes` при переключении в WEBVIEW-контекст (`contexts.in_webview` → `driver.switch_to.context`) на живой странице Sort&Filter AO3 | broken | logcat `test_main_pairing_checkbox_availability_live_logcat.txt` (66569 байт) + скриншот/page-source, собраны conftest'ом в `framework/allure-results/` |

## Дефекты-собратья (D-0043) — доклад

1. **Сигнатура падения TC-078 совпадает с уже задокументированным
   транзиентным классом.** `bugs/AT-BUG-022.md` (раздел «Верификация»,
   запись 2026-07-21T12:01:54Z) описывает ровно ту же ошибку — `no such
   execution context: loader has changed while resolving nodes` — как
   «транзиентный chromedriver-флейк при переключении WEBVIEW-контекста»,
   пойманный на TC-024 в отдельном прогоне и не повторившийся при
   изолированном перезапуске. Здесь — второй известный экземпляр того же
   класса, на другом тесте (TC-078) и в другом наборе (canary/live, а не
   TC-024/replay). Fail-fast порог (2 ИДЕНТИЧНЫХ отказа ПОСРЕДИ этого же
   прогона) не достигнут — за весь canary-набор это единственное падение,
   Blocked не ставлю. Оставляю как факт для failure-analyst/Lead: класс
   переживает уже второй независимый прогон в разных наборах, возможно
   заслуживает собственного AT-BUG (test_debt/инфраструктурный флейк) с
   критерием на класс, а не одноразового списания как FLAKY.
2. **Повтор известной находки про `$env:` в Bash-туле** (см. выше,
   «Мелкая находка при запуске») — тот же класс, что пункт 2
   «Дефекты-собратья» `RUN-20260803-2012`. Второй зафиксированный
   экземпляр за двое суток; кандидат на явную строку в CLAUDE.md
   («Дисциплина команд»), решение за Lead.

## Условия закрытия прогона (Closed)

- [ ] Падение TC-078 не имеет вердикта/действия (за failure-analyst — не
  мандат test-runner)
- [ ] Для APP_BUG/TEST_BUG/ENV_ISSUE ничего не заведено — решение за
  failure-analyst
- [ ] Карта покрытия (`state/coverage-map.md`) не перегенерировалась
  этим ходом

**Статус:** `NeedsTriage` — единственное падение требует вердикта
failure-analyst (гейт репетиции docs/11 §1 требует «live-baseline
зелёный»; 9/10 пока не зелёный baseline целиком).
