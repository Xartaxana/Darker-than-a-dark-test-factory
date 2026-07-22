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
матчить, compensating rerun не сломан ни на одном из 5 call-site'ов."""
from __future__ import annotations

from urllib3.exceptions import MaxRetryError, ReadTimeoutError


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
            `framework/pytest.ini --only-rerun`)."""
    client_config = driver.command_executor._client_config
    original_timeout = client_config.timeout
    client_config.timeout = timeout
    try:
        driver.get(url)
    except (ReadTimeoutError, MaxRetryError) as exc:
        raise TimeoutError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        client_config.timeout = original_timeout
