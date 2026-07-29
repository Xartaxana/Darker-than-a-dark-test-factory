"""Явные ожидания. Прямой sleep в тестах/шагах/экранах запрещён конвенцией —
всё ожидание проходит здесь (условие + таймаут из config).
"""
from __future__ import annotations

import time
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
    timeout = timeout if timeout is not None else settings.DEFAULT_TIMEOUT
    return WebDriverWait(driver, timeout, poll_frequency=0.4,
                         ignored_exceptions=_IGNORED).until(condition, message)


def wait_for(predicate: Callable[[], bool], timeout: int | None = None,
             message: str = "condition not met") -> None:
    """Ожидание произвольного предиката (например, состояния данных через adb)."""
    timeout = timeout if timeout is not None else settings.DEFAULT_TIMEOUT
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


def assert_holds_for(check: Callable[[], bool], budget_s: float, interval_s: float,
                      msg: str = "condition violated during budget") -> None:
    """Опрашивает `check()` ВЕСЬ бюджет `budget_s` (шаг `interval_s`), падает
    `AssertionError` при ПЕРВОМ нарушении — обобщение паттерна «негатив держится
    весь бюджет», введённого для `assert_top_chrome_not_darkened`
    (`framework/steps/browser_steps.py`, tap-zone guard TC-119/122). Симметрично
    `wait_until`/`wait_for` (которые возвращаются при ПЕРВОМ True) — этот примитив
    для обратного случая: доказать, что условие НЕ нарушается НИ РАЗУ за всё
    окно, в котором мог бы случиться отложенный/анимированный эффект. Один
    ранний снимок (`check()` вызван один раз сразу после действия) не доказывает
    этого — эффект, пришедший позже первого снимка, но ещё в пределах бюджета,
    иначе бы проскочил незамеченным.

    `check` — либо возвращает `bool` (`False` -> `AssertionError(msg)`), либо
    сам поднимает `AssertionError` с более информативным сообщением (диагностика
    текущего замера) — оба варианта считаются нарушением.

    Первый опрос — сразу (t=0), без начальной паузы. Последний опрос выполняется
    РОВНО в момент достижения дедлайна включительно — граница бюджета: нарушение
    ИМЕННО на этом последнем опросе ловится; нарушение, случившееся уже ПОСЛЕ
    дедлайна (строго за пределами бюджета, когда опрос больше не выполняется),
    этим вызовом не наблюдается — это осознанная граница, не дефект (симметрично
    границе `budget_s` любого `MAX_*`-таймаута в проекте)."""
    deadline = time.time() + budget_s
    while True:
        assert check(), msg
        if time.time() >= deadline:
            return
        time.sleep(interval_s)
