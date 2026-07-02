"""Создание и закрытие сессии Appium. Ядро не знает об экранах приложения."""
from __future__ import annotations

from appium import webdriver

from framework.config import capabilities, settings


def create_driver(no_reset: bool = True):
    opts = capabilities.build_options(no_reset=no_reset)
    driver = webdriver.Remote(settings.APPIUM_URL, options=opts)
    driver.implicitly_wait(settings.IMPLICIT_WAIT)
    return driver


def quit_driver(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:  # noqa: BLE001 — закрытие не должно ронять прогон
        pass
