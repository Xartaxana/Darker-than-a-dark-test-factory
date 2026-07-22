---
key: "AT-BUG-025"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "driver.get зависает неограниченно в WebView-контексте при отсутствии load-события (нет общего navigate-хелпера с таймаутом во всех местах browser_steps.py)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T00:00:00Z"
updated: "2026-07-22T00:00:00Z"
archived: false
resolution: null
---

# driver.get зависает неограниченно в WebView-контексте при отсутствии load-события (нет общего navigate-хелпера с таймаутом во всех местах browser_steps.py)

_Спроецировано из `bugs/AT-BUG-025.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-025 — `driver.get` без общего таймаут-хелпера виснет неограниченно в WebView

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: flaky_test`) — класс зависаний/таймаутов навигации, не баг
приложения. Обнаружен разведкой (`exploratory-charters/CH-004.md`) при
попытке живой навигации `driver.get` на `archiveofourown.org/tos`.

## Суть долга

`exploratory-charters/CH-004.md:200-206` («Обход инструмента (дизамбигуация,
не находка)»):

> `driver.get` в WebView-контексте этого приложения зависает намертво
> (load-event не наступает); `driver.set_page_load_timeout`
> UiAutomator2-драйвером НЕ реализован («Not implemented yet for
> pageLoad»). Навигация сделана через `driver.get` в try + собственный
> поллинг `document.readyState`/наличия блёрбов — так регаю контроль без
> 120с-виса.

Зависание воспроизведено ДВАЖДЫ на живой навигации (`archiveofourown.org/tos`,
120с клиентский таймаут Appium каждый раз) — CH-004:186-193. Тот же
`driver.get` завис и в REPLAY-режиме (proxy подтверждённо слушал,
`wait_device_proxy_reachable` прошёл), то есть корень — сам `driver.get`,
зависающий на WebView этого приложения при отсутствии load-события, а не
специфика живой сети/Cloudflare.

Поскольку `driver.set_page_load_timeout` не реализован драйвером
(UiAutomator2), единственный доступный обход — обёртка `driver.get` в
`try` с собственным поллингом `document.readyState` (или другого признака
готовности) и КОНЕЧНЫМ таймаутом. Такая обёртка уже существует в ОДНОМ
месте `framework/steps/browser_steps.py` — `open_url_and_wait_ready`
(строки 371-383): `driver.get(url)`, затем `wait_until` на
`document.readyState == "complete"` с `settings.WEBVIEW_LOAD_TIMEOUT`.
Сам вызов `driver.get()` внутри неё, однако, ничем не ограничен — таймаут
навешен только на ПОСЛЕДУЮЩИЙ опрос; если сам `driver.get()` зависнет (как
воспроизведено в CH-004), ограничение `wait_until` не наступит вовсе,
потому что `wait_until` не начнёт выполняться, пока не вернётся `driver.get()`.
Остальные места модуля вызывают `driver.get` без даже этой обёртки:

- `framework/steps/browser_steps.py:143` (открытие статической live-страницы
  `/tos`, `open_stable_tall_page`) — `wait_until` идёт следом, но сам
  `driver.get(STABLE_TALL_LIVE_URL)` не защищён.
- `framework/steps/browser_steps.py:362` (`open_listing`, replay-навигация
  на листинг) — та же форма: `driver.get(url)` без ограничения, `wait_until`
  на блёрбы следом.
- `framework/steps/browser_steps.py:377` (`open_url_and_wait_ready`) — тот
  же паттерн; ближе всех к обходу (try+readyState-поллинг ЗАЯВЛЕН как
  эталонный в CH-004:203-205), но сам вызов `driver.get()` тем не менее не
  обёрнут таймаутом.
- `framework/steps/browser_steps.py:489` (внутри retry-цикла с интерстишл-
  повторами, `attempt_timeout=8` — таймаут есть у ПОСЛЕДУЮЩЕГО `wait_until`,
  не у самого `driver.get(url)` на каждой попытке).
- `framework/steps/browser_steps.py:1035` (навигация на заведомо
  недоступный URL для проверки нативной error-page) — `driver.get(url)`
  обёрнут в `try/except WebDriverException`, что гасит `net::ERR*`, но НЕ
  гасит зависание без исключения (WebView, у которого просто нет
  load-события).

Ни одно из пяти мест не даёт `driver.get()` конечный верхний предел
времени независимо от появления load-события — при воспроизведении
класса из CH-004 (WebView не шлёт load-event) любое из них может
зависнуть на полный клиентский таймаут Appium (120с) без возможности
прервать раньше средствами теста.

## Критерий готовности (Fixed)

- Заведён общий navigate-хелпер (в `browser_steps.py` или выделенном
  модуле) — `driver.get` внутри него оборачивается механизмом с конечным
  верхним пределом ожидания самого вызова навигации (не только
  последующего `wait_until`), независимо от появления load-события; приём
  try+readyState-поллинг (`open_url_and_wait_ready:377-383`) — отправная
  точка, но таймаут должен покрывать САМ `driver.get()`, а не только опрос
  после него.
- Все перечисленные выше пять мест `driver.get` в `framework/steps/`
  переведены на этот общий хелпер; прямых вызовов `driver.get` вне хелпера
  в `framework/steps/` не остаётся — проверяемо `grep -n "driver\.get("
  framework/steps/browser_steps.py` (ожидается ровно вхождения внутри
  определения самого хелпера).
- Точечный зелёный прогон затронутых тестов (модули, использующие
  `open_stable_tall_page`, `open_listing`, `open_url_and_wait_ready`, вызовы
  с retry на интерстишл, error-page тест) после перевода — без регресса.

Починка — НЕ в этом батче (misc-batch-0722); подхватывается конвейером по
правилу 14/B4 (test_debt, `framework env`).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| | | | | (D1 fix-verifier — общим правилом, после Fixed) |

## Обсуждение

**2026-07-22 — builder (misc-batch-0722, sibling-очередь шапки (5)):**
заведён по указанию Lead (манифест батча) — находка `driver.get`
CH-004:200-206 переведена в test_debt-баг тем же классом, что
AT-BUG-004/005/006/024 (правило 9 CLAUDE.md: блокер/долг, замеченный на
этапе разведки, заводится багом, а не остаётся жить только прозой тела
чартера). Починка мест `driver.get` — вне scope этого батча (non-goals
манифеста); только заведение.
