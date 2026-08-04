---
key: "RUN-20260804-1317"
project: "AO3"
issueType: "run"
status: "run-triaged"
priority: "p2"
summary: "RUN-20260804-1317"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T11:44:09Z"
updated: "2026-08-04T11:44:09Z"
archived: false
resolution: null
---

# RUN-20260804-1317

_Спроецировано из `runs/RUN-20260804-1317.md` (источник правды).
Статус в нашей машине: **Triaged**._

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

## Падения и триаж (failure-analyst, 2026-08-04T11:44:09Z)

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| test_main_pairing_checkbox_availability_live (TC-078) | `WebDriverException: session not created — no such execution context: loader has changed while resolving nodes` при `switch_to.context(WEBVIEW)` на живой Sort&Filter (`/tags/Fluff/works`) | **ENV_ISSUE** | прогон нарушил ОБЯЗАТЕЛЬНУЮ env-предпосылку кейса (`AO3_EMU_GPU=host`); эмулятор перезапущен под `-Gpu host`, TC-078 live под ней **4/4 зелёный**; баг не заводится — класс уже покрыт `AT-BUG-021` | `bugs/AT-BUG-021.md`, `test-cases/canary/TC-078.md` («Заметки для автоматизации», решение Lead 2026-07-19) |

### Пакет доказательств (`schemas/evidence.yaml`, ENV_ISSUE)

**`env_check` — окружение прогона НЕ соответствовало контракту кейса.**
`test-cases/canary/TC-078.md` (строки 58-66) предписывает: live-прогон этого
кейса поднимает эмулятор **ТОЛЬКО** под `AO3_EMU_GPU=host`
(`Start-Emulator -Gpu host`) — решение Lead 2026-07-19 по `bugs/AT-BUG-021.md`
(«прогон под дефолтом = известный env-риск»). Позитивная сверка по артефакту
эмулятора (не по пересказу): `tools/avd/ao3_test_api34.avd/hardware-qemu.ini`
(mtime `2026-08-04T12:50:38` — буто́вка эмулятора ЭТОГО прогона, до старта
canary в 13:11) нёс

```
hw.gpu.enabled = true
hw.gpu.mode = swiftshader
```

Позитивный контроль того же артефакта после перезапуска под `-Gpu host`
(mtime `2026-08-04T13:36:58`): `hw.gpu.mode = host` — файл действительно
отражает флаг, значит `swiftshader` в прогоне — факт, а не артефакт чтения.
Прочие компоненты среды на момент прогона были исправны: `. tasks.ps1;
Get-Device` → `DEVICE: emulator-5554`, Appium `/status` → `{"ready":true}`
(build 3.5.2), CA mitmproxy установлен, guard `AT-BUG-026` — `recoveries 0/2`
(устройство ни разу не терялось за canary-прогон). То есть «среда жива», но
**конфигурация среды не та, которую требует кейс**.

**`retry_result` — изолированные перепрогоны (2 конфигурации).**

| # | GPU-бэкенд | Результат | Сигнатура |
|---|---|---|---|
| исходный (canary) | `swiftshader` | FAILED | `session not created … loader has changed while resolving nodes` (attach chromedriver в `in_webview`) |
| rerun 1 (13:29) | `swiftshader` | FAILED | `unknown error: cannot determine loading status from no such window` (`driver.get` внутри WEBVIEW) |
| rerun 2 | `swiftshader` | **PASSED** (26.28s) | — |
| rerun 3 (13:30) | `swiftshader` | FAILED | `disconnected: not connected to DevTools` → **эмулятор умер** |
| host-1 (13:38) | `host` | ERROR (setup) | `APK install failed: NullPointerException … StorageManager.getVolumes()` — неустоявшийся свежий бут, НЕ класс WebView |
| host-2 | `host` | ERROR (setup) | `Appium Settings app is not running after 30000ms` — тот же класс «бут не устоялся» |
| host-3 | `host` | **PASSED** (25.06s) | — |
| host-4/5/6 (устоявшееся устройство) | `host` | **PASSED / PASSED / PASSED** (30.32s / 21.12s / 21.31s), `PYTEST_EXIT=0` каждый | — |

Итого: под дефолтным `swiftshader` — **1 зелёный из 4**; под предписанным
кейсу `host` — **4 зелёных из 4** (два ERROR'а — фикстурные, на первых
секундах после бута, класс WebView/chromedriver не повторился ни разу);
`Get-Device` после серии — `DEVICE: emulator-5554`, guard `recoveries 0/2`.

**`logs` — логи окружения на момент падения.**
- `runs/RUN-20260804-1317/allure/test_main_pairing_checkbox_availability_live_logcat.txt`
  (66569 байт, сохранённая копия): в момент падения (`11:14:23`) в WebView
  жил **Cloudflare-челлендж**, а не целевая страница —
  `I chromium: [INFO:CONSOLE(3)] "Failed to create WebGPU Context Provider",
  source: https://archiveofourown.org/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1?ray=a25d23609cb904a7`;
  скриншот падения (`d839b061-…-attachment.png`) — пустая белая страница
  (интерстишл), page source — нативное дерево без контента AO3. Логкат
  rerun 1 несёт ту же картину плюс `challenges.cloudflare.com/turnstile/v0/…`.
  То есть chromedriver подключался/навигировал в момент, когда страницу
  перезагружал Cloudflare (R-03) — отсюда «loader has changed» / «no such
  window».
- Журнал Windows, `Application`, id 1000, **`2026-08-04T13:30:53` (локально)**:
  `qemu-system-x86_64.exe … код исключения 0xc0000005` — **ровно сигнатура
  `AT-BUG-021`**; это rerun 3. Подтверждения: логкат-вложение rerun 3 нулевой
  длины (conftest уже не смог снять logcat — устройства не было),
  `. tasks.ps1; Get-Device` → **`NO DEVICE`** (каноническая сверка, не голый
  adb), при следующем бутe `Start-Emulator` снял осиротевшие
  `multiinstance.lock` / `hardware-qemu.ini.lock`. За 6 предшествующих часов
  в журнале — ровно ОДИН такой crash-эвент, то есть исходное падение canary
  (13:14) прошло БЕЗ краша qemu (эмулятор пережил его: остальные 9 тестов
  прогона зелёные).

### Почему именно ENV_ISSUE (исключение остальных вердиктов)

- **не `APP_BUG`** — до кода приложения дело не дошло: падение в транспорте
  Appium↔chromedriver на шаге Given, ни один Then не исполнялся; сборка та же
  (`1.10 (11)`, `6455af0c`), что и в зелёных прогонах TC-078 ранее.
- **не `APP_CHANGED`** — `state/app-under-test.yaml` не менялся
  (`source_commit 63f6aac3`, `built_at 2026-07-02`); новых коммитов приложения
  между прошлым зелёным и этим прогоном нет, диапазон пустой.
- **не `SITE_CHANGED`** — DOM AO3 не опрашивался вовсе; селекторы кейса не
  участвовали. В ТОМ ЖЕ прогоне TC-080 и TC-082 ходят на ТУ ЖЕ живую
  страницу `/tags/Fluff/works` и зелёные.
- **не `TEST_BUG`** — логика теста и шага не менялась и даёт 4/4 зелёных, как
  только среда соответствует контракту кейса.
- **не `FLAKY`** — «нестабильность без установленной причины» здесь не
  применима: причина установлена и конфигурационна (GPU-бэкенд эмулятора
  вопреки явной предпосылке кейса + внешний Cloudflare-челлендж на живой
  странице). Карантин TC-078 не оформляется: тест исправен, чинить надо
  запуск. Это же — ответ на вопрос «второй ли это экземпляр класса
  `AT-BUG-022`»: см. «Дефекты-собратья» п.4.

### Действие (для координатора, вне мандата failure-analyst)

1. Canary-baseline на этой сборке следует **перепрогнать целиком под
   `AO3_EMU_GPU=host`** — тогда 10/10 достижимо; текущий 9/10 получен на
   конфигурации, которую кейс запрещает.
2. `state/app-under-test.yaml::canary_status` несёт комментарий «триаж не
   выполнен» — устарел после этого триажа (поле test-runner/координатора, не
   трогаю).
3. Среда изменена этим триажом: эмулятор перезапущен
   (`Start-Emulator -WritableSystem -Gpu host`), CA переустановлен
   (`store=134 apex=134`), APK на месте, Appium `:4723` жив,
   `Get-Device` → `DEVICE: emulator-5554`.

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

### Доклад failure-analyst (D-0043, скоуп НЕ расширяю — только называю)

3. **Логкат прогона затирается любым следующим прогоном того же теста —
   класс «потеря доказательств триажа».** `core/reporting.py:46` пишет
   `Path(settings.ALLURE_RESULTS) / f"{safe}_logcat.txt"`, а
   `config/settings.py:223` — `ALLURE_RESULTS = env ALLURE_RESULTS |
   framework/allure-results`, то есть путь НЕ следует за pytest-овым
   `--alluredir` и имя файла фиксировано на тест. Доказано на этом прогоне:
   `framework/allure-results/test_main_pairing_checkbox_availability_live_logcat.txt`
   стал **0 байт** (13:31) — его перезаписал мой изолированный перепрогон,
   хотя тот гнался с `--alluredir` в scratchpad. Исходные 66569 байт уцелели
   только потому, что каталог прогона был заранее заархивирован и закоммичен
   координатором в `runs/RUN-20260804-1317/allure/` (коммит `bae7fa7`; сверка:
   моя защитная копия того же каталога дала пустой `git diff` — байты
   совпали). Без этой привычки триаж остался бы без логката. Плюс в
   `pytest.ini` addopts стоит
   `--clean-alluredir`: любой прогон без переопределения `--alluredir`
   вычищает каталог прошлого прогона целиком. Кандидат для test-maintainer
   (архивирование артефактов в `runs/RUN-*/allure/` при закрытии прогона либо
   уважение `--alluredir`).
4. **Про «второй экземпляр класса AT-BUG-022» — уточнение владения классом.**
   `bugs/AT-BUG-022.md` — это долг про **observability-примитив активной
   вкладки** (`debt_kind: missing_fixture`, Verified); сигнатура
   «loader has changed while resolving nodes» упомянута там лишь как побочная
   строка в таблице «Верификация» (TC-024, 2026-07-21) и НИКОГДА не была его
   предметом. То есть класс сегодняшнего падения **не принадлежит AT-BUG-022**
   — считать это «вторым экземпляром AT-BUG-022» неверно; верно, что это
   второе ЗАПИСАННОЕ наблюдение той же сигнатуры. Владеющий артефакт класса —
   **`bugs/AT-BUG-021.md`** (`broken_environment`, Verified): та же живая
   страница `/tags/Fluff/works`, та же связка «`disconnected: not connected to
   DevTools` → устройство пропало», тот же митигейшн `AO3_EMU_GPU=host`. У него
   `last_seen_in: ""`, а сегодня класс наблюдался живьём (crash-эвент
   `13:30:53`, `0xc0000005`) — вопрос «переоткрыть / проставить `last_seen_in`
   / оставить Verified как known-env-риск» выношу Lead: переход из `Verified`
   мне не принадлежит (`schemas/transitions.yaml` — только human /
   fix-verifier / qa-loop-rollback).
5. **Ретрай-цикл R-03 не ловит Cloudflare-класс отказов.**
   `open_live_listing` (`browser_steps.py:1307-1331`) считает неудачной
   попыткой только `TimeoutError`/`TimeoutException`, а Cloudflare-гонка
   приходит как `WebDriverException` (`loader has changed…`, `no such
   window`, `disconnected: not connected to DevTools`) — и на attach
   (`contexts.in_webview`, который ВНЕ цикла), и на `driver.get` внутри него.
   `pytest.ini` (`--only-rerun ReadTimeoutError|MaxRetryError`) их тоже не
   покрывает. Кандидат на упрочнение (test-maintainer), не чиню.
6. **Фикстурные отказы первых секунд после бута** (наблюдение из перепрогонов,
   не относится к вердикту): 2 из 2 первых прогонов сразу после
   `Start-Emulator` упали на setup — `APK install failed: NullPointerException
   … StorageManager.getVolumes()` и `Appium Settings app is not running after
   30000ms`; после «устаканивания» — 3/3 зелёных. Кандидат на settle-ожидание
   в `Start-Emulator`/фикстурах.

## Условия закрытия прогона (Closed)

- [x] Падение TC-078 получило вердикт `ENV_ISSUE` с пакетом доказательств
  (`env_check` / `retry_result` / `logs` — см. раздел «Падения и триаж»)
- [x] Для ENV_ISSUE баг не заводится: класс уже покрыт `bugs/AT-BUG-021.md`;
  действие — перепрогон canary под `AO3_EMU_GPU=host` (координатор)
- [ ] Карта покрытия (`state/coverage-map.md`) не перегенерировалась
  этим ходом
- [ ] Перепрогон canary-baseline под предписанной GPU-конфигурацией не
  выполнен (вне мандата failure-analyst — вход решения координатора/Lead)

**Статус:** `Triaged` — единственное падение атрибутировано (`ENV_ISSUE`).
**Вход в гейт репетиции (docs/11 §1, решение за Lead, не мой статус):** этот
canary-baseline я НЕ считаю ни «зелёным с известным транзиентом», ни
«нестабильным» — он **прогнан на неверной конфигурации** (эмулятор под
`swiftshader` вопреки обязательной для TC-078 предпосылке `AO3_EMU_GPU=host`),
и как baseline не годится ни в ту, ни в другую сторону. На предписанной
конфигурации TC-078 live даёт 4/4 зелёных, класс отказа не воспроизводится —
то есть ожидаемый исход корректного перепрогона 10/10, но он ещё не сделан.
