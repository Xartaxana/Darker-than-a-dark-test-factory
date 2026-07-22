---
key: "AT-BUG-025"
project: "AO3"
issueType: "bug"
status: "bug-verified"
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
created: "2026-07-22T19:45:51Z"
updated: "2026-07-22T19:45:51Z"
archived: false
resolution: "done"
---

# driver.get зависает неограниченно в WebView-контексте при отсутствии load-события (нет общего navigate-хелпера с таймаутом во всех местах browser_steps.py)

_Спроецировано из `bugs/AT-BUG-025.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-07-22 | тестовая система: framework/core/navigate.py + framework/steps/browser_steps.py (финальное состояние после attempt 2); эмулятор ao3_test_api34, приложение 1.10 (versionCode 11) не при чём (test_debt) | `framework/tests/test_navigate_timeout_unit.py` (5 тестов) x3 подряд; device-регресс: test_theme_dark_applies_instantly_without_recreating_activity, test_bridge_marker_present_replay[ao3_home_smoke.mitm], test_bridge_marker_present_live, test_work_blurb_selector_matches_replay_listing[listing_basic.mitm], test_work_blurb_selector_matches_live_listing, test_main_frame_load_error_shows_custom_error_page_with_retry (6 тестов) x3 подряд; `python -m pytest scripts/tests -q`; `python scripts/validate_frontmatter.py` | Unit: run1 `5 passed in 3.84s`, run2 `5 passed in 3.83s`, run3 `5 passed in 3.70s`, все `PYTEST_EXIT=0`. Device-регресс: run1 `6 passed in 125.46s`, run2 `6 passed in 120.54s`, run3 `6 passed in 124.92s`, все `PYTEST_EXIT=0`, ни одного RERUN. `scripts/tests`: `650 passed in 14.26s`. `validate_frontmatter`: `ошибок 0, предупреждений 0`. Grep-сверка (`grep -n 'driver\.get(' framework/steps/browser_steps.py`) — 6 совпадений, все в комментариях/докстрингах (строки 144,430,447,556,560,1125); `grep -n 'navigate(' ` — 5 реальных вызовов (147,431,449,576,1137), `from framework.core.navigate import navigate` (17). Прочитан код `navigate.py` и оба call-site'а с except TimeoutError (576, 1137) — соответствуют описанию attempt 2. | Fixed → Verified (fix-verifier, независимый прогон, все 3 пункта DoD подтверждены) |

## Обсуждение

**2026-07-22 — builder (misc-batch-0722, sibling-очередь шапки (5)):**
заведён по указанию Lead (манифест батча) — находка `driver.get`
CH-004:200-206 переведена в test_debt-баг тем же классом, что
AT-BUG-004/005/006/024 (правило 9 CLAUDE.md: блокер/долг, замеченный на
этапе разведки, заводится багом, а не остаётся жить только прозой тела
чартера). Починка мест `driver.get` — вне scope этого батча (non-goals
манифеста); только заведение.

---

**2026-07-22T16:45:00Z — test-maintainer (B4), фикс:**

**Выбор механизма.** `driver.set_page_load_timeout` не реализован
UiAutomator2-драйвером (подтверждено в CH-004) — штатного API ограничить
именно НАТИВНЫЙ вызов навигации нет. Вместо потока/таймера с последующим
`os.kill` (хрупкий побочный эффект, явно названный в диспатче как
нежелательный) переиспользован УЖЕ ПРИНЯТЫЙ в этом репозитории механизм
AT-BUG-007: `selenium.webdriver.remote.remote_connection.RemoteConnection._request`
читает `self._client_config.timeout` ЗАНОВО на КАЖДЫЙ HTTP-запрос (не
запекает его в `urllib3.PoolManager` при создании сессии — проверено чтением
`selenium/webdriver/remote/remote_connection.py:283,431,436` в
`framework/.venv`, selenium==4.45.0). Значит `AppiumClientConfig.timeout`
можно безопасно подменить ТОЛЬКО на время вызова `driver.get()` и
восстановить в `finally`, не пересоздавая сессию — тот же приём, что
`driver_factory.create_driver` уже использует ГЛОБАЛЬНО для
`settings.APPIUM_HTTP_TIMEOUT`.

Исключение при истечении таймаута НЕ конвертируется в `TimeoutException`:
боевой путь (с `retries=False` из AT-BUG-007) отдаёт
`urllib3.exceptions.ReadTimeoutError`, которая наследует ВСТРОЕННЫЙ
`TimeoutError` (`class ReadTimeoutError(TimeoutError, RequestError)`,
`urllib3/exceptions.py`) — `framework/pytest.ini`
(`--only-rerun ReadTimeoutError|MaxRetryError`) продолжает матчить её по
имени класса, компенсирующий rerun не сломан. Вызывающему коду, которому
нужно перехватить именно этот таймаут, достаточно `except TimeoutError` —
без импорта `urllib3.exceptions` в `framework/steps/`.

**Реализация.**
- Новый модуль `framework/core/navigate.py` — функция `navigate(driver,
  url, timeout)`: временно понижает `driver.command_executor._client_config.timeout`
  до `timeout`, вызывает `driver.get(url)`, восстанавливает исходное
  значение в `finally`. Полное обоснование и альтернативы — в докстринге
  модуля.
- `framework/steps/browser_steps.py` — все 5 мест из «Сути долга» переведены
  на `navigate(...)`:
  1. `open_stable_tall_page:143` → `navigate(driver, STABLE_TALL_LIVE_URL,
     settings.WEBVIEW_LOAD_TIMEOUT)`.
  2. `open_listing:362` → `navigate(driver, url, settings.WEBVIEW_LOAD_TIMEOUT)`.
  3. `open_url_and_wait_ready:377` → `navigate(driver, url, timeout or
     settings.WEBVIEW_LOAD_TIMEOUT)` (тот же бюджет, что уже был у
     последующего `wait_until`).
  4. `open_live_listing` retry-цикл (было :489) — `remaining` теперь
     считается ДО навигации; сам `driver.get(url)` тоже ограничен
     `min(attempt_timeout, remaining)` через `navigate(...)`, его
     `TimeoutError` перехватывается как неудавшаяся попытка (`continue`),
     наравне с `TimeoutException` от `wait_until` — иначе зависший
     `driver.get()` на первой попытке съедал бы весь бюджет retry-цикла, не
     давая ему сработать вообще (собственно суть долга в этом месте).
  5. `open_unreachable_url` (было :1035) — `navigate(driver, url, timeout or
     settings.WEBVIEW_LOAD_TIMEOUT)` в `try`; `except TimeoutError: pass`
     добавлен РЯДОМ с существующим `except WebDriverException` (гасящим
     `net::ERR*`) — оба исхода трактуются одинаково: реальную проверку
     итога делает следующий шаг `assert_error_page_shown`.
- Прямых вызовов `driver.get(` в `framework/steps/browser_steps.py` не
  осталось — `Select-String -Path framework\steps\browser_steps.py -Pattern
  'driver\.get\('` находит только упоминания в комментариях/докстрингах
  (строки 144, 367, 384, 493, 497, 1059); единственный реальный вызов —
  внутри `framework/core/navigate.py::navigate`, вне `framework/steps/`.

**Witness (дословно).**
`python -m pytest scripts/tests -q` (после фикса, без регресса обвязки):
`650 passed in 13.90s`.

Точечный прогон затронутых тестов (эмулятор `ao3_test_api34`,
`-WritableSystem` + `Install-MitmCA`, `Start-Appium`), 3 прогона подряд —
все зелёные, `PYTEST_EXIT=0` каждый раз:
```
tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity PASSED   (open_stable_tall_page)
tests/canary/test_ao3_selectors.py::test_bridge_marker_present_replay[ao3_home_smoke.mitm] PASSED  (open_url_and_wait_ready, replay)
tests/canary/test_ao3_selectors.py::test_bridge_marker_present_live PASSED                     (open_url_and_wait_ready, live)
tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_replay_listing[listing_basic.mitm] PASSED  (open_listing)
tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_live_listing PASSED       (open_live_listing retry-цикл)
tests/test_errors.py::test_main_frame_load_error_shows_custom_error_page_with_retry PASSED     (open_unreachable_url)
```
Run #1: `6 passed in 121.59s`. Run #2: `6 passed in 120.17s`. Run #3:
`6 passed in 122.35s`. (Один изолированный ранний прогон до этой серии
поймал `TimeoutError: mitmdump не занял порт 8080 за 15s` в
`test_bridge_marker_present_replay` при setup fixture'ы `replay` сразу после
другого replay-теста в том же сеансе — это порт-race тулинга `mitm.py`
(`_wait_listening`/`start_replay`), НЕ связан с изменением: ошибка падает в
`conftest.py::_ensure_replay_ca`/`mitm.start_replay` до входа в код
`browser_steps`; повторный изолированный прогон сразу после — `PASSED`, и
все 3 прогона серии выше зелёные без этой ошибки.)

**Побочные находки (доклад, НЕ в scope, D-0037 — не чиню):**
- `framework/screens/browser_screen.py:62` (`BrowserScreen.open_work`) —
  `self.driver.get(f"https://archiveofourown.org/works/{work_id}")` без
  bounded-обёртки. Тот же класс риска (WebView может не выдать
  load-событие), другой модуль — вне списка «пяти мест» диспатча.
- `framework/steps/perf_steps.py:60` (`measure_home_page_load_time`) —
  `driver.get(browser_steps.HOME_URL)` без обёртки; здесь сам вызов —
  ЧАСТЬ измеряемого интервала (TC-097), обёртка потребовала бы отдельного
  решения, не мешающего замеру (не переиспользовать бездумно значение
  `settings.WEBVIEW_LOAD_TIMEOUT` как таймаут — тогда замер того же
  порядка мог бы упереться в собственный лимит). Оба — кандидаты в
  отдельный B4-проход того же класса, что этот баг; не расширяю scope
  самостоятельно.

Критерий готовности выполнен по всем 3 пунктам, подтверждён дословным
выводом прогонов выше. **Open → Fixed.**

---

**2026-07-22T14:39:00Z — critic (правило 3а, REJECTED attempt 1):**
блокер B1 — центральное утверждение выше («`ReadTimeoutError` наследует
ВСТРОЕННЫЙ `TimeoutError`») ЛОЖНО. Эмпирика critic'а в `framework/.venv`
(urllib3 2.7.0): `issubclass(urllib3.exceptions.ReadTimeoutError,
builtins.TimeoutError)` → **False**. `urllib3/exceptions.py:124` определяет
СОБСТВЕННЫЙ `class TimeoutError(HTTPError)` в своём модуле — `ReadTimeoutError`
наследует ЕГО, не питоновский встроенный (misread: строка
`class ReadTimeoutError(TimeoutError, RequestError)` использует локальное
имя, ошибочно принятое за builtin).

**Следствие:** `except TimeoutError` (builtins, urllib3 не импортирован в
`browser_steps.py`) в `open_live_listing` (retry-цикл интерстишл, строка
~511) и `open_unreachable_url` (строка ~1072) НЕ ловит реальный
`urllib3.exceptions.ReadTimeoutError`, который бросает `navigate()` на
таймауте. Ветка зависания (ради которой заведён весь баг) не работает:
retry-цикл аварийно падает на первой зависшей попытке вместо `continue`;
`open_unreachable_url` не глотает таймаут. 3 зелёных прогона witness'а
исполняли только happy-path (страницы грузились в срок) — ветка таймаута
ни разу не исполнялась, поэтому дефект не проявился.

Статус откачен `Fixed → Open` (правка НЕ ратифицирована координатором).
Attempt 2 — тем же воркером: (1) `navigate()` ловит
`urllib3.exceptions.ReadTimeoutError` внутри и перебрасывает встроенным
`TimeoutError` (чистый контракт для `steps/`, без импорта urllib3 в
call-site'ах) — ЛИБО call-site'ы ловят реальный urllib3-тип; (2) тест НА
саму ветку таймаута (синтетический hang, ветка сейчас ничем не покрыта);
(3) исправить ложную формулировку о наследовании в docstring `navigate.py`
и в этом файле (секции выше, где утверждается «наследует встроенный»).

Зона 1 (механизм save/restore timeout), зона 2 (pytest.ini rerun по имени
класса — не сломан), зона 3 (полнота 5 мест) — приняты critic'ом без
замечаний. Сиблинги `browser_screen.py:62`/`perf_steps.py:60` подтверждены
critic'ом тем же классом — вынесены в `bugs/AT-BUG-027.md` (координатор,
чтобы не испарились из очереди).

---

**2026-07-22T17:30:00Z — test-maintainer, attempt 2 (после critic REJECT B1):**

**Корректирующая запись (НЕ переписывает секцию attempt 1 выше — та
остаётся как есть, историческая; это отдельная запись).** Утверждение
attempt 1 «`ReadTimeoutError` наследует ВСТРОЕННЫЙ `TimeoutError`» —
ЛОЖНО, подтверждено эмпирически ещё раз (`framework/.venv`, urllib3==2.7.0):
`issubclass(urllib3.exceptions.ReadTimeoutError, builtins.TimeoutError)` →
`False`; то же для `urllib3.exceptions.MaxRetryError` (он вообще не
наследует ни один `TimeoutError`, только `RequestError`). Причина ошибки —
одноимённые классы в разных областях видимости: `urllib3/exceptions.py:124`
определяет СОБСТВЕННЫЙ `class TimeoutError(HTTPError)` в своём модуле,
`ReadTimeoutError(TimeoutError, RequestError)` наследует ИМЕННО его.

**Фикс B1.** `framework/core/navigate.py::navigate()` теперь ЯВНО
перехватывает `urllib3.exceptions.ReadTimeoutError` И
`urllib3.exceptions.MaxRetryError` (второй — запасной случай AT-BUG-007 B2)
и перебрасывает их как ВСТРОЕННЫЙ `TimeoutError` (`raise TimeoutError(str(exc))
from exc`), внутри `finally`, восстанавливающего `client_config.timeout` —
контракт для `framework/steps/` остаётся чистым (`except TimeoutError`, без
импорта `urllib3.exceptions` в call-site'ах), но теперь это ГАРАНТИРОВАНО
кодом хелпера, а не случайным совпадением имён классов. Докстринг
`navigate.py` переписан: исправлена ложная формулировка, добавлен раздел
«Raises» с явным описанием перехвата. Ложная формулировка исправлена также в
докстрингах `open_live_listing`/`open_unreachable_url`
(`framework/steps/browser_steps.py`) — те же слова были продублированы
туда в attempt 1, тот же класс дефекта (правило 9 CLAUDE.md — чиню класс, а
не только первое найденное место).

**Новый тест на ветку таймаута (пункт 2 critic'а).**
`framework/tests/test_navigate_timeout_unit.py` — device-free синтетический
hang (фейковый `driver.get()`, кидающий РЕАЛЬНЫЕ
`urllib3.exceptions.ReadTimeoutError`/`MaxRetryError`, не имитацию/подкласс
builtin), 4 пробы:
1. `navigate()` конвертирует `ReadTimeoutError` → builtin `TimeoutError`,
   восстанавливает `client_config.timeout` в `finally`.
2. То же для `MaxRetryError`.
3. `open_live_listing` — retry-цикл РЕАЛЬНО ловит `TimeoutError` от
   `navigate()` (`driver.get_calls >= 2`, доказательство, что ретрай
   произошёл, а не съеден одной зависшей попыткой) и в итоге поднимает
   ожидаемый `TimeoutException` (не сырой urllib3-тип) с
   `__cause__` типа именно builtin `TimeoutError`.
4. `open_unreachable_url` — глотает `TimeoutError` от `navigate()`
   (`except TimeoutError: pass`), не падает наружу.

**Самокоррекция в ходе attempt 2 (до сдачи, не отдельный REJECT).** Первая
версия фикса (`raise TimeoutError(str(exc)) from exc`, без имени исходного
класса в сообщении) сама несла риск того же СЕМЕЙСТВА дефекта, что и B1:
`framework/pytest.ini` (`--only-rerun ReadTimeoutError|MaxRetryError`)
матчит регекс через `pytest_rerunfailures._try_match_error` против
`f"{excinfo.type.__name__}: {excinfo.value}"` — на ТРЁХ call-site'ах,
которые НЕ оборачивают `navigate()` в try/except (`open_stable_tall_page`,
`open_listing`, `open_url_and_wait_ready`), builtin `TimeoutError` долетел
бы до pytest КАК ЕСТЬ, и голое имя класса `"TimeoutError"` НЕ матчит регекс
`ReadTimeoutError|MaxRetryError` (нужен префикс Read/Max) — compensating
rerun сломался бы именно там. Исправлено ДО сдачи (не отдельная REJECT-
итерация): сообщение переброшенного `TimeoutError` теперь несёт имя
исходного urllib3-класса первым токеном
(`f"{type(exc).__name__}: {exc}"` → `"ReadTimeoutError: ..."`/
`"MaxRetryError: ..."`), итоговая строка матчинга `_try_match_error`
(`"TimeoutError: ReadTimeoutError: ..."`) снова содержит нужную подстроку.
Добавлен отдельный регресс-гвард
`test_navigate_timeout_message_matches_pytest_ini_rerun_regex`,
воспроизводящий ТОЧНУЮ формулу матчинга плагина.

**Witness (дословно, финальное состояние кода).**

Новая проба (5 тестов, включая регресс-гвард на pytest.ini), 3 прогона
подряд (`Invoke-Pytest tests/test_navigate_timeout_unit.py -v`):
Run #1: `5 passed in 4.09s`. Run #2: `5 passed in 3.80s`. Run #3:
`5 passed in 3.81s`. Все `PYTEST_EXIT=0`.

Регресс — те же 6 device-тестов из attempt 1, ПОСЛЕ финального состояния
`navigate.py` (эмулятор `ao3_test_api34`, `Install-MitmCA` + `Install-App`,
`Start-Appium`), 3 прогона подряд:
```
tests/test_settings.py::test_theme_dark_applies_instantly_without_recreating_activity PASSED
tests/canary/test_ao3_selectors.py::test_bridge_marker_present_replay[ao3_home_smoke.mitm] PASSED
tests/canary/test_ao3_selectors.py::test_bridge_marker_present_live PASSED
tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_replay_listing[listing_basic.mitm] PASSED
tests/canary/test_ao3_selectors.py::test_work_blurb_selector_matches_live_listing PASSED
tests/test_errors.py::test_main_frame_load_error_shows_custom_error_page_with_retry PASSED
```
Run #1: `6 passed in 126.43s`. Run #2: `6 passed in 122.85s`. Run #3:
`6 passed, 1 rerun in 219.78s` — `test_work_blurb_selector_matches_replay_listing`
поймал один `RERUN` (compensating rerun сработал и восстановился, тот же
класс разового port-race replay-тулинга, что уже отмечен в witness'е
attempt 1 выше; не таймаут-ветка `navigate()` — вклад изменений этого фикса
в этот конкретный RERUN не исключён отдельным изолирующим прогоном, но
класс совпадает с уже задокументированным флейком тулинга mitm.py), итог
`PASSED`. `PYTEST_EXIT=0` во всех 3 прогонах.

`python -m pytest scripts/tests -q` (финальное состояние, обвязка не
затронута): `650 passed in 13.39s`. `python scripts/validate_frontmatter.py`:
`validate_frontmatter: ошибок 0, предупреждений 0`.

Все 9 device-free unit-модулей `framework/tests/*_unit.py` (включая новый)
прогнаны вместе одним вызовом — коллизий фикстур/сборки не обнаружено:
`32 passed in 8.93s`.

Все требования critic'а (B1: реальный urllib3-тип ловится и перебрасывается
builtin-совместимо БЕЗ потери compensating rerun; тест на ветку таймаута;
исправление ложной формулировки) выполнены дословным witness'ом, включая
содержательный прогон именно ветки таймаута (не только happy-path).
**Open → Fixed.**

---

**2026-07-22T19:45:51Z — fix-verifier (D1, независимая верификация):**

Прочитан файл целиком (полная история attempt 1 → B1 → attempt 2). Проверил
все 3 пункта критерия готовности НЕЗАВИСИМО, не доверяя пересказу:

1. **Хелпер.** Прочитан `framework/core/navigate.py` целиком: временная
   подмена `client_config.timeout`, `try: driver.get(url) / except
   (ReadTimeoutError, MaxRetryError) as exc: raise TimeoutError(...) from exc
   / finally: restore`. Соответствует описанию attempt 2 (не attempt 1 с
   ложным наследованием) — докстринг явно фиксирует исправление B1.
2. **Пять мест.** `grep -n 'driver\.get(' framework/steps/browser_steps.py`
   — 6 совпадений (строки 144, 430, 447, 556, 560, 1125), все внутри
   комментариев/докстрингов (проверил контекст каждой строки — реальных
   вызовов `driver.get(` нет). `grep -n 'navigate(' framework/steps/
   browser_steps.py` — 5 реальных вызовов хелпера (147, 431, 449, 576, 1137)
   + импорт на строке 17. Прочитаны оба call-site'а с обработкой исключения
   (retry-цикл `open_live_listing` строка ~576/577: `except TimeoutError as
   exc: last_exc = exc; continue`; `open_unreachable_url` строка
   ~1137/1141: `except TimeoutError: pass`) — оба ловят именно builtin
   `TimeoutError`, как и утверждает discussion.
3. **Прогоны (все свежие, дословный witness ниже, не пересказ):**
   - `tests/test_navigate_timeout_unit.py` x3 подряд: `5 passed in 3.84s` /
     `3.83s` / `3.70s`, `PYTEST_EXIT=0` каждый раз.
   - 6 device-тестов из discussion x3 подряд (эмулятор `ao3_test_api34`,
     свежий `Install-MitmCA`+`Install-App`+`Start-Appium` в этой сессии):
     `6 passed in 125.46s` / `120.54s` / `124.92s`, `PYTEST_EXIT=0` каждый
     раз, ни одного RERUN (в отличие от прогона test-maintainer'а, где Run #3
     поймал один RERUN на порт-race replay-тулинга — в моих 3 прогонах этот
     флейк не проявился, но он и не входит в скоуп фикса).
   - `python -m pytest scripts/tests -q`: `650 passed in 14.26s`.
   - `python scripts/validate_frontmatter.py`: `ошибок 0, предупреждений 0`.

Расхождений с описанием test-maintainer'а не найдено. Все 3 пункта DoD
подтверждены свежим независимым прогоном на актуальном коде (не на сборке
приложения — `type: test_debt`, фикс тестовой системы). Cleanup выполнен:
`Stop-NodeProcesses`, `adb emu kill`, `Get-Device` → `NO DEVICE`.

Сиблинги `browser_screen.py:62`/`perf_steps.py:60`, отмеченные в attempt 1 и
уже вынесенные координатором в `bugs/AT-BUG-027.md` — подтверждаю, что они
действительно вне текущего фикса (не проверял отдельно, вне скоупа этой
верификации).

**Fixed → Verified.**
