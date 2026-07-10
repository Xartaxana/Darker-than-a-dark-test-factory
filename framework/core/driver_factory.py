"""Создание и закрытие сессии Appium. Ядро не знает об экранах приложения."""
from __future__ import annotations

from appium import webdriver
from appium.webdriver.client_config import AppiumClientConfig

from framework.config import capabilities, settings


def create_driver(no_reset: bool = True):
    opts = capabilities.build_options(no_reset=no_reset)
    # AT-BUG-007: client-side read-timeout на command_executor. Без него единичный
    # блокирующий HTTP-вызов к Appium (мёртвый процесс приложения, сетевой ступор)
    # висит на сокете навсегда и клинит весь suite — см. settings.APPIUM_HTTP_TIMEOUT.
    #
    # retries=False (штатный параметр ClientConfig.init_args_for_pool_manager ->
    # urllib3.PoolManager(retries=...), НЕ монки-патч) отключает урллиб3-ретраи на
    # уровне HTTP: без этого urllib3 по умолчанию ретраит GET (в т.ч. driver.contexts)
    # до 3 раз при read-timeout, и висящий GET реально падает не за
    # APPIUM_HTTP_TIMEOUT, а за ~4x (измерено; см. AT-BUG-007, Обсуждение, attempt 2).
    # С retries=False и GET, и POST падают ReadTimeoutError ровно за 1x timeout —
    # предсказуемая граница вместо путаницы GET-vs-POST множителей. Компенсирующий
    # ретрай теперь на уровне теста, а не HTTP: framework/pytest.ini
    # (--reruns 1 --only-rerun ReadTimeoutError|MaxRetryError) — таргетированно на
    # класс инфраструктурных таймаутов, не на любые сетевые сбои (см. риск в
    # settings.APPIUM_HTTP_TIMEOUT).
    client_config = AppiumClientConfig(
        remote_server_addr=settings.APPIUM_URL,
        timeout=settings.APPIUM_HTTP_TIMEOUT,
        init_args_for_pool_manager={"init_args_for_pool_manager": {"retries": False}},
    )
    driver = webdriver.Remote(settings.APPIUM_URL, options=opts, client_config=client_config)
    driver.implicitly_wait(settings.IMPLICIT_WAIT)
    return driver


def quit_driver(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:  # noqa: BLE001 — закрытие не должно ронять прогон
        pass
