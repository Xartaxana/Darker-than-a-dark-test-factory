"""Bounded-навигация WebView: единая точка вызова `driver.get()` для степов
`framework/steps/browser_steps.py` (AT-BUG-025).

Суть долга (полный разбор — `bugs/AT-BUG-025.md`): `driver.get` в WebView-
контексте этого приложения может зависнуть НАМЕРТВО (load-событие не наступает
вовсе — воспроизведено дважды на живой навигации и один раз в REPLAY-режиме,
CH-004:186-193). `driver.set_page_load_timeout` НЕ реализован UiAutomator2-
драйвером ("Not implemented yet for pageLoad") — навесить таймаут штатным
Selenium/Appium API на САМ вызов навигации нельзя.

Механизм этого хелпера — НЕ новый: временная подмена
`AppiumClientConfig.timeout` на время одного вызова, тот же приём, что
`framework/core/driver_factory.py::create_driver` уже применяет ГЛОБАЛЬНО для
`settings.APPIUM_HTTP_TIMEOUT` (AT-BUG-007). Это безопасно, потому что
`selenium.webdriver.remote.remote_connection.RemoteConnection._request`
читает `self._client_config.timeout` ЗАНОВО на КАЖДЫЙ HTTP-запрос (не
запекает значение в `urllib3.PoolManager` при создании сессии — см.
`_request`, `timeout=self._client_config.timeout` передаётся в
`conn.request(...)` каждый раз) — временную подмену можно безопасно
восстановить в `finally`, не трогая саму сессию/pool manager.

Почему НЕ поток/таймер с последующим `os.kill`/отменой: сам вызов идёт через
единственную HTTP-сессию Appium-сервера — убить/прервать ЕГО клиентской
стороной, не убив саму Appium-сессию (или не оставив её в неопределённом
состоянии на середине обработки команды сервером), штатными средствами
`appium-python-client` нельзя; отдельный поток с принудительным прерыванием
System-уровня добавил бы куда более хрупкий и непредсказуемый побочный эффект,
чем переиспользование уже принятого в AT-BUG-007 риска (сервер может ещё
доигрывать команду в фоне после клиентского таймаута — тот же риск-профиль,
что и у ГЛОБАЛЬНОГО `APPIUM_HTTP_TIMEOUT`, ничего нового не вносится).

**ИСПРАВЛЕНИЕ (attempt 2, critic REJECT B1 на attempt 1):** предыдущая
версия этого докстринга ЛОЖНО утверждала, что
`urllib3.exceptions.ReadTimeoutError` «наследует ВСТРОЕННЫЙ `TimeoutError`».
Это неверно — `urllib3/exceptions.py:124` определяет СОБСТВЕННЫЙ
`class TimeoutError(HTTPError)` в своём модуле, и
`ReadTimeoutError(TimeoutError, RequestError)` наследует ИМЕННО его (по
модульной области видимости), а не питоновский builtin. Проверено
эмпирически (`framework/.venv`, urllib3==2.7.0):
`issubclass(urllib3.exceptions.ReadTimeoutError, builtins.TimeoutError)` →
`False`; то же для `urllib3.exceptions.MaxRetryError` (запасной случай,
если retries где-то останутся включены — см. AT-BUG-007 B2) — он вообще не
наследует ни один `TimeoutError`, только `RequestError`.

Поэтому эта функция ЯВНО перехватывает оба urllib3-класса и перебрасывает их
как ВСТРОЕННЫЙ `TimeoutError` — контракт для `framework/steps/` остаётся
чистым (`except TimeoutError`, без импорта `urllib3.exceptions` в
call-site'ах), но теперь это ГАРАНТИРОВАНО правкой здесь, а не случайным
совпадением имён классов в разных модулях.

**Важно для `framework/pytest.ini` (`--only-rerun
ReadTimeoutError|MaxRetryError`).** `pytest_rerunfailures._try_match_error`
матчит регекс через `re.search` против `f"{excinfo.type.__name__}: {excinfo.value}"`
— ПОСЛЕ перехвата этой функцией тип исключения, долетающего до pytest на
ТРЁХ call-site'ах `browser_steps.py`, что НЕ оборачивают `navigate()` в
`try/except` (`open_stable_tall_page`, `open_listing`,
`open_url_and_wait_ready`), стал бы builtin `TimeoutError`, а не
`ReadTimeoutError`/`MaxRetryError` — тогда `excinfo.type.__name__` дало бы
голое `"TimeoutError"`, НЕ матчащее регекс `ReadTimeoutError|MaxRetryError`
(тот требует префикс `Read`/`Max`), и compensating rerun сломался бы именно
там, где `navigate()` не перехватывается локально. Поэтому сообщение
переброшенного `TimeoutError` НЕСЁТ имя исходного urllib3-класса первым
токеном (`f"{type(exc).__name__}: {exc}"`, реализовано ниже) — итоговая
строка матчинга `_try_match_error` выглядит как
`"TimeoutError: ReadTimeoutError: <исходное сообщение>"`, и подстрока
`ReadTimeoutError`/`MaxRetryError` в ней присутствует — regex продолжает
матчить, compensating rerun не сломан ни на одном из 5 call-site'ов.

**AT-BUG-047, attempt 3 (choke point 1 из 2 — реконструкция attempt 2 после
утраты байтовой копии, см. `bugs/AT-BUG-047.md`, критик-диагноз и обсуждение
2026-08-04).** `wait_ui_ready` (`framework/steps/app_steps.py`) — барьер
только по присутствию нативной оболочки (`android.webkit.WebView` в дереве),
БЕЗ ожидания оседания стартовой загрузки домашней вкладки. Под нагрузкой
длинного прогона это открывает узкое окно гонки: следующий же шаг зовёт
`navigate()` (`driver.get`), пока WebView-процесс/страница ещё "in flight",
и chromedriver теряет цель:

```
selenium.common.exceptions.WebDriverException: Message: unknown error:
cannot determine loading status from no such window
```

Ретрай — ТОЧЕЧНЫЙ и РЕАКТИВНЫЙ: перехватывается ТОЛЬКО эта узкая сигнатура
(подстрока сообщения), не любой `WebDriverException` — иначе это была бы
маскировка (CLAUDE.md test-maintainer: «не чини падение маскировкой»),
глушащая настоящие поломки навигации под тем же общим типом исключения.
Bounded retry (не sleep вместо ожидания, а сам `driver.get()` пробуется
заново — тот же класс решения, что и `driver_factory._verify_app_installed_with_retry`,
AT-BUG-026): окно гонки — единицы секунд (WebView-процесс догружается), не
структурная поломка навигации."""
from __future__ import annotations

import logging
import time

from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

logger = logging.getLogger(__name__)

# AT-BUG-047: узкая сигнатура транзиентной гонки "wait_ui_ready ещё не
# гарантирует оседание стартовой загрузки Home" — см. докстринг модуля.
# НЕ переиспользуется в contexts.py::in_webview (там ДРУГОЙ choke point,
# ДРУГАЯ сигнатура — критик-диагноз AT-BUG-047 явно требует раздельных
# маркеров ретрая, не одной общей "WebView race" ловушки).
_TRANSIENT_RACE_SIGNATURE = "cannot determine loading status from no such window"
_TRANSIENT_RACE_RETRIES = 3
_TRANSIENT_RACE_BACKOFF = 1.0


def navigate(driver, url: str, timeout: float) -> None:
    """Аналог `driver.get(url)`, ограничивающий САМ вызов навигации `timeout`
    секундами (client-side HTTP read-timeout), независимо от появления
    load-события в WebView. Используется ВМЕСТО прямого `driver.get()` во
    всех местах `framework/steps/browser_steps.py` — см. `bugs/AT-BUG-025.md`
    за перечнем переведённых мест и обоснованием значений `timeout` на каждом
    call site (обычно `settings.WEBVIEW_LOAD_TIMEOUT`, либо доля бюджета
    retry-цикла интерстишла).

    Raises:
        TimeoutError: если сам вызов `driver.get()` не уложился в `timeout`
            секунд (клиентский read-timeout сработал раньше load-события).
            Перехватывает `urllib3.exceptions.ReadTimeoutError`/`MaxRetryError`
            (НИ ОДИН из них не наследует встроенный `TimeoutError` — см.
            докстринг модуля) и перебрасывает их как встроенный `TimeoutError`,
            чтобы вызывающему коду в `framework/steps/` не требовался импорт
            `urllib3.exceptions`. Сообщение несёт имя ИСХОДНОГО urllib3-класса
            первым токеном (см. докстринг модуля — почему это важно для
            `framework/pytest.ini --only-rerun`).

    Транзиентная гонка `wait_ui_ready` vs стартовая загрузка Home
    (AT-BUG-047, см. докстринг модуля) поглощается ВНУТРИ этой функции
    bounded-ретраем узкой сигнатуры `cannot determine loading status from
    no such window` — наружу не долетает, вызывающему коду ничего не
    нужно менять. Любой ДРУГОЙ `WebDriverException` (в т.ч. родственная,
    но иная сигнатура choke point'а `contexts.in_webview`) перебрасывается
    как есть, без ретрая — это НЕ общая ловушка WebView-гонок."""
    client_config = driver.command_executor._client_config
    original_timeout = client_config.timeout
    client_config.timeout = timeout
    last_race_exc: WebDriverException | None = None
    try:
        for attempt in range(1, _TRANSIENT_RACE_RETRIES + 1):
            try:
                driver.get(url)
                return
            except (ReadTimeoutError, MaxRetryError) as exc:
                raise TimeoutError(f"{type(exc).__name__}: {exc}") from exc
            except WebDriverException as exc:
                if _TRANSIENT_RACE_SIGNATURE not in str(exc):
                    raise
                last_race_exc = exc
                # N4 (критик-вход TC-009), симметрично contexts.py: ретрай
                # раньше срабатывал молча — log-строка несёт choke point и
                # сматченную сигнатуру (сигнатура здесь одна, набор не
                # меняется — только видимость).
                logger.warning(
                    "AT-BUG-047 choke point 1 (navigate): попытка %d/%d провалена "
                    "транзиентной сигнатурой %r, ретраю",
                    attempt, _TRANSIENT_RACE_RETRIES, _TRANSIENT_RACE_SIGNATURE,
                )
                if attempt < _TRANSIENT_RACE_RETRIES:
                    time.sleep(_TRANSIENT_RACE_BACKOFF)
        raise last_race_exc
    finally:
        client_config.timeout = original_timeout
