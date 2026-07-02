"""Переключение между нативным контекстом и WebView. Гибридная природа приложения
(Compose + WebView AO3) изолирована здесь, чтобы экраны и страницы не дублировали логику.
"""
from __future__ import annotations

import contextlib

from framework.config import settings
from framework.core.waits import wait_until

NATIVE = "NATIVE_APP"


def webview_name(driver) -> str | None:
    for ctx in driver.contexts:
        if "WEBVIEW" in ctx:
            return ctx
    return None


def wait_for_webview(driver, timeout: int | None = None) -> str:
    name = wait_until(
        driver, lambda d: webview_name(d),
        timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
        message="WEBVIEW-контекст не появился",
    )
    return name


def to_native(driver) -> None:
    if driver.current_context != NATIVE:
        driver.switch_to.context(NATIVE)


@contextlib.contextmanager
def in_webview(driver, timeout: int | None = None):
    """Временно переключается в WebView и гарантированно возвращается в нативный контекст."""
    name = wait_for_webview(driver, timeout)
    driver.switch_to.context(name)
    try:
        yield name
    finally:
        to_native(driver)
