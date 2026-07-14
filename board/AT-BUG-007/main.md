---
key: "AT-BUG-007"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Нет таймаут-гейта на висящие Appium-вызовы: зависший in-flight запрос вешает весь suite вместо падения одного теста (нет pytest-timeout / client read-timeout)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-14T10:47:39Z"
updated: "2026-07-14T10:47:39Z"
archived: false
resolution: "done"
---

# Нет таймаут-гейта на висящие Appium-вызовы: зависший in-flight запрос вешает весь suite вместо падения одного теста (нет pytest-timeout / client read-timeout)

_Спроецировано из `bugs/AT-BUG-007.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-007 — Suite виснет вместо падения одного теста (нет таймаут-гейта)

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: broken_environment`). Проявился 2026-07-09 дважды подряд на
  p0 smoke (WHPX, live AO3), но класс — универсальный: ЛЮБОЙ тест, чей
  Appium-вызов завис (умерший процесс приложения, сетевой ступор,
  Cloudflare), вешает весь прогон навечно.

## Суть долга

Диагноз critic (2026-07-09, независимое ревью; трасса воспроизводима по коду):

- `framework/config/settings.py:33-36`: `IMPLICIT_WAIT=0`,
  `NEW_COMMAND_TIMEOUT=300` — последний лишь серверный idle-таймаут Appium
  (закрывает сессию при отсутствии НОВЫХ команд) и НЕ прерывает уже
  висящий in-flight вызов.
- Явные ожидания — `WebDriverWait` (20с, `framework/core/waits.py:22-25`) —
  проверяют дедлайн только МЕЖДУ поллами; одиночный блокирующий HTTP-вызов
  к Appium (классика — `driver.contexts` из `contexts.to_native`,
  вызывается в `BaseScreen.__init__`) при мёртвом процессе приложения
  виснет на серверной стороне навсегда — 20с не применяются.
- `pytest-timeout` в окружении НЕТ (плагины: allure-pytest,
  rerunfailures) — ничто не ограничивает тест по стене → виснет весь suite.

Следствие: единичная флаки-смерть приложения (см. [[AT-BUG-008]] /
bugs/AT-BUG-008.md) превращается из «один retriable fail» в «клин всего
прогона + ручное вмешательство оператора». Уже стоило дважды по ~20 минут
+ два ручных убийства дерева процессов за один вечер 2026-07-09.

## Критерий готовности (Fixed)

- Per-test wall-clock гейт: `pytest-timeout` добавлен (`--timeout` с
  разумным запасом к самому долгому легитимному тесту, `timeout-method`,
  совместимый с Appium-тредами) И/ИЛИ client-side read-timeout на
  `command_executor` Appium-драйвера в driver_factory — выбор и обоснование
  за исполнителем, но результат один: висящий in-flight вызов обязан
  завершаться ошибкой за конечное время.
- `framework/requirements.txt` обновлён в том же изменении (permission-
  hygiene п.5), если ставится пакет.
- Доказательство: синтетический висящий тест (НЕ коммитится или помечен
  как инструмент) падает по таймауту вместо зависания; существующие suites
  без регресса (минимум: replay-проба и юнит-пробы зелёные; полный p0 —
  по доступности эмулятора).
- После фикса `pytest-rerunfailures` (уже установлен) автоматически
  ретраит упавший по таймауту тест — связка задокументирована.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-14 | test_debt — фикс во фреймворке (не привязан к сборке приложения); приложение: app-debug.apk текущего HEAD, установлено на ao3_test_api34 (API 34) | Синтетическая проба AT-BUG-007 (независимая, НЕ из репозитория, scratchpad, удалена по завершении) + `tests/test_replay_infra_probe.py` + `tests/test_seed_filter_profiles_unit.py` (×3) + `scripts/tests` + полный p0 (`-m p0`, 18 TC) | Синт. проба: hang→`ReadTimeoutError` за 2.02-2.03s (=1x `AO3_APPIUM_HTTP_TIMEOUT=2`, не 4x/8x) → `RERUN`→`FAILED` (`1 failed, 1 rerun in 5.81s`); `assert False` контроль → `FAILED` БЕЗ `RERUN` (`1 failed in 0.69s`) — семантика триажа подтверждена. Регресс: 3 прогона `test_replay_infra_probe.py`+`test_seed_filter_profiles_unit.py` подряд — все `PASSED`, `PYTEST_EXIT=0` (первая попытка поймала известный класс UI-флака bottom-sheet на холодном cold-boot эмуляторе — не таймаут-класс, не смэтчился `--only-rerun`, прошёл со второй попытки и 3/3 подряд после); `python -m pytest scripts/tests -q` — 294 passed. Полный p0 (`-m p0`, 18 отобранных) — 18 passed, 0 упавших/зависших, `575.22s` (~9.5 мин), `PYTEST_EXIT=0`; таймаут-гейт ни разу не сработал боевым образом (в т.ч. известный флаки AT-BUG-008 в этом прогоне не проявился) — suite прошёл штатно от начала до конца. | **Verified**. Все 4 пункта критерия Fixed подтверждены независимым прогоном: (1) висящий in-flight вызов падает за конечное предсказуемое время (~1x таймаут) и ретраится ровно один раз согласно `--reruns 1 --only-rerun`; (2) обычное падение не ретраится; (3) регресс отсутствует; (4) полный p0 прошёл целиком, суть долга (клин suite) устранена. |

## Обсуждение

**2026-07-09T18:40:00Z — Lead (Fable), заведение по вердикту critic:**
Найден critic'ом как корневой, воспроизводимый дефект при диагнозе
двойного зависания p0 (задача 2 ревью инкремента 1 AT-BUG-005): сам
триггер — флаки-смерть процесса на живом AO3 (AT-BUG-008), но КЛИН suite
вместо fail одного теста — целиком этот долг. Чинится независимо от
AT-BUG-008 и важнее его: с таймаут-гейтом любые будущие флаки такого рода
деградируют до retriable-fail. Диспатч по B4 — следующим проходом.

**2026-07-10 — test-maintainer (at-bug-007), фикс:**

Выбор: **(б) client-side read-timeout на `command_executor`**, БЕЗ
`pytest-timeout`. Обоснование отказа от pytest-timeout: два штатных
`timeout-method` несовместимы со средой/целью задачи —
`method=signal` требует `SIGALRM`, недоступен на Windows (среда
прогона — Windows 11); `method=thread` по достижении дедлайна дампит
стек всех потоков и завершает процесс `os._exit()` — это ГЛОБАЛЬНО
убивает весь pytest-процесс, т.е. воспроизводит ровно тот симптом,
который чиним («один зависший вызов кладёт весь suite»), только через
другой механизм. `И/ИЛИ` в критерии готовности допускает одиночное
решение — client-timeout закрывает диагностированный critic'ом разрыв
полностью и без этого риска.

Реализация:
- `framework/config/settings.py`: новая константа `APPIUM_HTTP_TIMEOUT`
  (default 120s, переопределяется `AO3_APPIUM_HTTP_TIMEOUT`). Величина:
  заведомо больше самого долгого легитимного ОДИНОЧНОГО блокирующего
  вызова (создание Appium-сессии — запуск uiautomator2-сервера +
  возможная докачка chromedriver, по дефолтам Appium укладывается в
  60-90с) и на порядок меньше реально наблюдавшихся зависаний (19+
  минут).
- `framework/core/driver_factory.py::create_driver`: `webdriver.Remote`
  теперь получает `client_config=AppiumClientConfig(remote_server_addr=...,
  timeout=settings.APPIUM_HTTP_TIMEOUT)`. Это единственная точка создания
  драйвера в фреймворке (`framework/tests/conftest.py::driver` — фикстура
  на тест). `ClientConfig.timeout` передаётся в urllib3 на КАЖДЫЙ HTTP-запрос
  (`selenium/webdriver/remote/remote_connection.py::_request`), не только
  на создание сессии — значит гейт покрывает и `driver.contexts`
  (`contexts.to_native`, названный critic'ом как классическое место
  зависания), и любой другой Appium-вызов, а не только конкретный.
  `WebDriverWait` (`waits.py`, дедлайн между поллами) не менялся — не был
  причиной, это была вложенная в один полл HTTP-блокировка.

~~Связка с `pytest-rerunfailures` (уже установлен...): retry срабатывает
автоматически без дополнительной конфигурации.~~ **ИСПРАВЛЕНО attempt 2
(critic REJECT, B1) — эта запись была ЛОЖНОЙ.** `pytest-rerunfailures`
без `--reruns N` — no-op; нигде в конфигурации (`pytest.ini`, `tasks.ps1`,
промпты) ретрай не был включён. Также ложным было утверждение, что
исключение «обёрнуто `WebDriverException`»: `webdriver.execute()`
(selenium `remote/webdriver.py:489`) НЕ оборачивает ошибку
`command_executor.execute()` в try/except — `MaxRetryError`/
`ReadTimeoutError` долетают до теста как есть, без обёртки. См. запись
attempt 2 ниже — оба факта исправлены по факту измерения.

Доказательство (witness):
- Синтетический висящий тест (инструмент, НЕ в репозитории — в scratchpad
  сессии, не собирается pytest'ом фреймворка): TCP-заглушка принимает
  соединение и никогда не отвечает (имитация мёртвого процесса
  приложения); `AppiumConnection` с `client_config.timeout=2s` бьёт по
  `/status` — падает `MaxRetryError`/`ReadTimeoutError` за ~8с (retry
  urllib3 × read_timeout), конечное и предсказуемое время вместо
  зависания. `EXITCODE=0` (проба сама себя валидирует: OK, если время до
  ошибки в разумных кратных `read_timeout`).
- Без регресса: `Invoke-Pytest tests/test_replay_infra_probe.py
  tests/test_seed_filter_profiles_unit.py -v` — 3 прогона подряд, все
  зелёные (`PASSED`, `PYTEST_EXIT=0`); replay-проба реально проходит
  создание сессии + серию Appium-вызовов через новый `client_config` без
  ложных срабатываний таймаута. `python -m pytest scripts/tests -q` —
  262 passed (обвязка не затронута, sanity).

Полный p0 не гонялся (решение Lead — отдельным проходом).

Замеченный аналог класса (не в скоупе, ДОКЛАД по D-0043/D-0037):
`framework/core/adb.py::_run()` — `subprocess.run(...)` без `timeout=`
на КАЖДЫЙ `adb shell`-вызов (`shell`, `force_stop`, `clear_app_data`,
`logcat_dump` и др.) и отдельно в `pull_app_file`/`push_app_file`.
Зависший/мёртвый adb-сервер или устройство в неотвечающем состоянии
подвесит эти вызовы так же безусловно, как голый Appium HTTP-вызов до
этого фикса — та же ось «блокирующий вызов без таймаута», другая
транспортная труба. В очередь для отдельного B4/аналогичного прохода.

---

**2026-07-10 — test-maintainer (at-bug-007), attempt 2 (после REJECT critic):**

Вердикт critic (attempt 1): REJECT, 2 блокера (B1, B2) + 2 некритичных
(N1, N2). Разбор и закрытие каждого:

**B1 (устранено) — ретрай был ЛОЖНО заявлен «включённым по умолчанию».**
`pytest-rerunfailures` без `--reruns N`/`@pytest.mark.flaky` — no-op;
проверено критиком по всем точкам конфигурации, ретрай нигде не был
включён. Решение Lead выполнено: `framework/pytest.ini` `addopts`
дополнены `--reruns 1` и `--only-rerun ReadTimeoutError|MaxRetryError`.
Паттерн выведен из ФАКТИЧЕСКОЙ поверхности исключения на боевом пути
(измерено attempt 2, не выведено умозрительно): `pytest_rerunfailures`
матчит регекс против `f"{type(exc).__name__}: {exc}"`
(`_try_match_error`, `pytest_rerunfailures.py:461-469`); реальный вызов
через `webdriver.execute()` → `RemoteConnection._request` (тот же путь,
что и `driver.contexts`) отдаёт `ReadTimeoutError` (POST, и GET — после
исправления B2 ниже) или `MaxRetryError` (запасной случай, если retries
где-то останутся включены) — оба варианта матчатся одним паттерном.
Witness: синтетический тест (`webdriver.Remote` против зависшего TCP-сервера,
не в репозитории) — вывод `RERUN` → `FAILED`, `1 failed, 1 rerun in 4.72s`;
синтетический `assert False` — `FAILED` БЕЗ `RERUN`, `1 failed in 0.27s` (без
пометки `rerun`) — обычные падения по-прежнему не ретраятся, семантика
триажа не изменена.

**B2 (устранено) — граница 120с была честна лишь отчасти.**
Critic измерил на этом venv (`urllib3==2.7.0`): GET по умолчанию ретраится
до 3 раз при read-timeout (`MaxRetryError` за ~4x timeout), POST — без
ретраев (`ReadTimeoutError` за ~1x). Висящий `driver.contexts` (GET) —
реально ~480с (8 мин) при `APPIUM_HTTP_TIMEOUT=120`, тот же порядок, что
19-минутные зависания, а не «на порядок меньше», как было написано.
Исправление — штатным параметром `ClientConfig` (НЕ монки-патч):
`AppiumClientConfig(..., init_args_for_pool_manager={"init_args_for_pool_manager":
{"retries": False}})` (`framework/core/driver_factory.py`) — эта настройка
уходит в `urllib3.PoolManager(retries=False, ...)`
(`selenium/webdriver/remote/remote_connection.py::_get_connection_manager`).
Измерено ПОСЛЕ фикса: и GET, и POST против зависшего сервера теперь падают
`ReadTimeoutError` РОВНО за 1x `read_timeout` (было: GET x4, POST x1).
Итоговый честный худший случай зависшего вызова: `(1 + reruns) x
APPIUM_HTTP_TIMEOUT` = `2 x 120 = 240с` (4 мин) — теперь ДЕЙСТВИТЕЛЬНО на
порядок меньше 19 минут. Комментарий в `settings.py` переписан на эти
цифры (было/стало, честная арифметика). Побочный эффект (задокументирован
в коде, не скрыт): `retries=False` убирает урллиб3-ретраи не только на
read-timeout, но и на прочие транзиентные сетевые сбои внутри одной
HTTP-попытки — компенсирующий ретрай теперь только на уровне теста
(`--reruns 1 --only-rerun ReadTimeoutError|MaxRetryError` из B1),
таргетированно на класс инфраструктурных таймаутов.

**N1 (выполнено, расширен доклад аналогов).** Проверено самостоятельно
(не просто скопирован вердикт critic — один пункт не подтвердился):
- `framework/core/mitm.py:97-98` (`set_device_proxy`) и `:103-104`
  (`clear_device_proxy`) — `subprocess.run([settings.ADB, "shell",
  "settings", "put", ...])` БЕЗ `timeout=` — реальный аналог, тот же
  класс, что `adb.py::_run()` выше (зависший/неотвечающий adb-shell
  подвесит переключение replay-прокси на неопределённое время).
- `framework/core/mitm.py:40-42` (`_wait_listening`) — ПРОВЕРЕНО и НЕ
  подтвердилось как отдельный аналог: `s.settimeout(0.5)` (строка 41)
  уже ограничивает попытку `connect_ex` (строка 42) по времени, а
  внешний цикл дополнительно ограничен `deadline = time.time() +
  timeout` (`_READY_TIMEOUT=15s`) — это НЕ неограниченный блокирующий
  вызов. Не добавляю в очередь как ложную находку — честность записи
  важнее полноты списка.

Обе реальные строки (`mitm.py:97-98`, `:103-104`) — в очередь вместе с
`adb.py::_run()` для отдельного B4-прохода (не в скоупе этой задачи).

**N2 (выполнено).** Известный риск задокументирован в
`framework/config/settings.py` (комментарий у `APPIUM_HTTP_TIMEOUT`):
холодная докачка chromedriver может произойти на `SET_CONTEXT` при первом
переключении в WebView (одиночный POST, без ретрая после B2) и
потенциально превысить 120с на медленной сети/первом прогоне на чистой
машине — тогда легитимный вызов ошибочно словит таймаут. Смягчение:
`AO3_APPIUM_HTTP_TIMEOUT` увеличивается без правки кода. Количественный
замер докачки — вне скоупа этого фикса.

Witness attempt 2 (полный, все синтетические пробы НЕ в репозитории,
удалены по завершении):
1. Timeout-класс: `webdriver.Remote` против зависшего TCP-сервера
   (`APPIUM_URL` переопределён на `127.0.0.1:18888`,
   `AO3_APPIUM_HTTP_TIMEOUT=2`) → `RERUN` → `FAILED`,
   `urllib3.exceptions.ReadTimeoutError: ... (read timeout=2)`,
   `1 failed, 1 rerun in 4.72s`, `PYTEST_EXIT=1` (ожидаемо — сервер
   зависает навсегда, поэтому и повтор падает; в реальном флаки-сценарии
   вторая попытка новой сессии обычно проходит).
2. Ordinary-assert: `assert False` → `FAILED` без `RERUN`,
   `1 failed in 0.27s`, `PYTEST_EXIT=1` — НЕ матчит `--only-rerun`,
   ретрая нет.
3. Без регресса, 3 прогона подряд С НОВЫМ `pytest.ini`:
   `Invoke-Pytest tests/test_replay_infra_probe.py
   tests/test_seed_filter_profiles_unit.py -v` → `3 passed` каждый раз
   (20.11s / 20.36s / 20.81s), `PYTEST_EXIT=0` все три. `python -m pytest
   scripts/tests -q` → `262 passed` (sanity, обвязка не затронута).

status: Fixed подтверждён после закрытия B1/B2 (это исправление).

---

**2026-07-14T10:47:39Z — fix-verifier, mode=verify, вердикт Verified:**

Независимо (без опоры на цифры test-maintainer) воспроизвёл обе синтетические
пробы attempt 2 в scratchpad-сессии (TCP-заглушка, принимает соединение и не
отвечает; НЕ в репозитории, удалена по завершении), через реальный
`driver_factory.create_driver()` + `AppiumClientConfig` фреймворка (не
переизобретал таймаут-логику руками):

- Hang-класс: `AO3_APPIUM_HTTP_TIMEOUT=2` → `webdriver.Remote` против
  зависшего стаба → `urllib3.exceptions.ReadTimeoutError: ... (read
  timeout=2)` за **2.02-2.03s** (замерено `time.monotonic()`), т.е. РОВНО 1x
  таймаут, не 4x/8x — граница B2 подтверждена независимым измерением. С
  `framework/pytest.ini` addopts (`--reruns 1 --only-rerun
  ReadTimeoutError|MaxRetryError`) — `RERUN` → `FAILED`,
  `1 failed, 1 rerun in 5.81s`.
- Control-класс: `assert False` → `FAILED` БЕЗ `RERUN`, `1 failed in 0.69s` —
  ретрай не сматчился, семантика триажа не задета.
- Побочная находка тулинга (НЕ дефект фикса, отчёт для будущих fix-verifier
  сессий): при первом прогоне пробы путь лежал на другом диске (`C:`) от
  `rootdir` (`D:\AO3_tests\framework`) — `framework/pytest.ini` `addopts`
  (в т.ч. `--reruns`) молча НЕ применялись без явных флагов на командной
  строке (rootdir/inifile нашёлся, но addopts — нет; вероятно, cross-drive
  ломает вычисление common-ancestor для discovery). Обошёл явной передачей
  тех же флагов, что в `pytest.ini`, — цифры выше сняты именно с них, так что
  вердикт не пострадал. Отдельно: разные пути того же требования, что чинит
  сам AT-BUG-007 (проверка ретрая) — не сама область бага.

Регресс (после подъёма эмулятора `-writable-system` и установки CA,
`Install-App`+`Install-MitmCA`, `Start-Appium`):
`tests/test_replay_infra_probe.py` + `tests/test_seed_filter_profiles_unit.py`
— первая попытка поймала `AssertionError` на bottom-sheet
(`rating_steps.rate_via_listing_overlay`) на холодном (`-no-snapshot-load`,
после порчи снапшота предыдущими некорректными `adb emu kill`) первом
прогоне WebView — НЕ таймаут-класс (не матчится `--only-rerun`, не
относится к AT-BUG-007), похоже на разовый cold-start флак; 3 последующих
прогона подряд — все `PASSED`, `PYTEST_EXIT=0`. `python -m pytest
scripts/tests -q` — 294 passed (выросло с 262 у test-maintainer — новые
скрипт-тесты появились со времени фикса, ожидаемо).

Полный p0 (`-m p0`, 18 отобранных из 40, критерий Fixed — «по
доступности», эмулятор поднят): **18 passed, 0 failed, 575.22s (~9.5 мин),
PYTEST_EXIT=0**. Suite прошёл от начала до конца без единого зависания;
известный флаки AT-BUG-008
(`test_rate_work_from_work_page_panel`) в этом прогоне не проявился —
косвенно ничего не доказывает про AT-BUG-008, но подтверждает главное: даже
после нескольких дней вебсим/окружения (в т.ч. свежая порча снапшота
эмулятора в ходе этой самой верификационной сессии, устранённая
`-no-snapshot-load` холодной загрузкой) suite ни разу не заклинил.

Критерий Fixed выполнен по всем 4 пунктам независимым прогоном. **Fixed →
Verified.**
