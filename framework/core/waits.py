"""Явные ожидания. Прямой sleep в тестах/шагах/экранах запрещён конвенцией —
всё ожидание проходит здесь (условие + таймаут из config).
"""
from __future__ import annotations

from typing import Callable, TypeVar

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait

from framework.config import settings

T = TypeVar("T")

_IGNORED = (NoSuchElementException, StaleElementReferenceException, WebDriverException)


def wait_until(driver, condition: Callable[[object], T], timeout: int | None = None,
               message: str = "") -> T:
    timeout = timeout or settings.DEFAULT_TIMEOUT
    return WebDriverWait(driver, timeout, poll_frequency=0.4,
                         ignored_exceptions=_IGNORED).until(condition, message)


def wait_for(predicate: Callable[[], bool], timeout: int | None = None,
             message: str = "condition not met") -> None:
    """Ожидание произвольного предиката (например, состояния данных через adb)."""
    import time
    timeout = timeout or settings.DEFAULT_TIMEOUT
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.4)
    raise TimeoutError(f"{message} (after {timeout}s){f'; last error: {last}' if last else ''}")
