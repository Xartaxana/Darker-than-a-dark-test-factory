"""Переключение между нативным контекстом и WebView. Гибридная природа приложения
(Compose + WebView AO3) изолирована здесь, чтобы экраны и страницы не дублировали логику.

**AT-BUG-047, attempt 3 (choke point 2 из 2 — критик-диагноз 2026-08-04,
`bugs/AT-BUG-047.md`, обсуждение).** Второй choke point того же класса
гонки «`wait_ui_ready` не гарантирует оседание стартовой загрузки Home»:
переключение в WEBVIEW-контекст (`driver.switch_to.context(name)` внутри
`in_webview`) внутри себя стартует chromedriver-прокси
(`AndroidUiautomator2Driver.setContext` -> `startChromedriverProxy` ->
`Chromedriver.start()`), и под той же нагрузкой стартовая Home-навигация
ещё "in flight" может сорвать ЭТОТ шаг с РОДСТВЕННОЙ, но ОТЛИЧНОЙ от
`core/navigate.py` сигнатурой:

```
selenium.common.exceptions.WebDriverException: A new session could not be
created. Details: session not created from no such execution context:
loader has changed while resolving nodes
```

Свой узкий маркер ретрая (НЕ переиспользует `navigate._TRANSIENT_RACE_SIGNATURE`
— критик явно указал на это как на причину, почему attempt 2 не закрыл
класс: «классификация заново» вместо повторного использования барьера,
который начинал attempt 1). Bounded retry — тот же класс решения, что и
`core/navigate.py::navigate` (см. её докстринг) и
`driver_factory._verify_app_installed_with_retry` (AT-BUG-026): окно гонки
— единицы секунд, не структурная поломка переключения контекста.

**Рецидив НОВОЙ сигнатурой (test-maintainer, 2026-08-11, `runs/RUN-20260811-0405.md`,
триаж failure-analyst, TC-009).** Тот же choke point, тот же механизм гонки
(chromedriver-прокси не успевает подняться, пока стартовая Home-загрузка ещё
"in flight"), но chromedriver в этот раз оборвал handshake ДРУГИМ хвостом
сообщения:

```
selenium.common.exceptions.WebDriverException: A new session could not be
created. Details: session not created from no such execution context:
uniqueContextId not found
```

Маркер ретрая расширен с ОДНОЙ литеральной строки до НАБОРА известных
сигнатур этого choke point'а (`_WEBVIEW_SWITCH_RACE_SIGNATURES`) — классовая
форма (правило 9 CLAUDE.md), не общий `except WebDriverException` (это была
бы маскировка, прямой запрет `AT-BUG-047`). Любая ДРУГАЯ, не входящая в
набор, сигнатура `WebDriverException` по-прежнему перебрасывается на первой
же попытке.
"""
from __future__ import annotations

import contextlib
import logging
import time

from selenium.common.exceptions import WebDriverException

from framework.config import settings
from framework.core.waits import wait_until

logger = logging.getLogger(__name__)

NATIVE = "NATIVE_APP"

# AT-BUG-047 choke point 2: НАБОР известных узких сигнатур гонки
# chromedriver-старта при переключении в WEBVIEW ПОКА стартовая загрузка
# Home ещё не осела. Классовая форма (правило 9 CLAUDE.md, рецидив
# 2026-08-11, RUN-20260811-0405/TC-009): один и тот же choke point рвёт
# handshake РАЗНЫМИ хвостами сообщения в зависимости от того, в какой
# момент прокси-старта его застигла гонка — набор растёт по мере
# наблюдаемых экземпляров, НЕ общим `except WebDriverException`. НЕ путать
# с сигнатурой `core/navigate.py` (`cannot determine loading status from no
# such window`) — разные choke points, разные маркеры (см. докстринг
# модуля).
_WEBVIEW_SWITCH_RACE_SIGNATURES = (
    "loader has changed while resolving nodes",
    "uniqueContextId not found",
)
_WEBVIEW_SWITCH_RACE_RETRIES = 3
_WEBVIEW_SWITCH_RACE_BACKOFF = 1.0


def _matched_webview_switch_race_signature(exc: WebDriverException) -> str | None:
    """Сигнатура набора `_WEBVIEW_SWITCH_RACE_SIGNATURES`, сматчившая `exc`,
    либо None — используется и предикатом `_is_webview_switch_race`, и
    log-строкой ретрая (N4, критик-вход TC-009: молчаливый ретрай без следа
    какая именно сигнатура сработала)."""
    message = str(exc)
    for signature in _WEBVIEW_SWITCH_RACE_SIGNATURES:
        if signature in message:
            return signature
    return None


def _is_webview_switch_race(exc: WebDriverException) -> bool:
    """True, если `exc` — один из известных экземпляров choke point 2
    (см. `_WEBVIEW_SWITCH_RACE_SIGNATURES`)."""
    return _matched_webview_switch_race_signature(exc) is not None


def _switch_to_webview_with_race_retry(driver, name: str) -> None:
    """`driver.switch_to.context(name)` с bounded-ретраем на набор узких
    транзиентных сигнатур AT-BUG-047 choke point 2 (см. докстринг модуля).
    Любой ДРУГОЙ `WebDriverException` перебрасывается на первой же попытке
    — это НЕ общая ловушка WebView-гонок, только этот конкретный choke
    point."""
    last_race_exc: WebDriverException | None = None
    for attempt in range(1, _WEBVIEW_SWITCH_RACE_RETRIES + 1):
        try:
            driver.switch_to.context(name)
            return
        except WebDriverException as exc:
            matched_signature = _matched_webview_switch_race_signature(exc)
            if matched_signature is None:
                raise
            last_race_exc = exc
            # N4 (критик-вход TC-009): ретрай раньше срабатывал молча —
            # log-строка несёт choke point и СМАТЧЕННУЮ сигнатуру набора
            # (не меняет ни логику, ни сами сигнатуры).
            logger.warning(
                "AT-BUG-047 choke point 2 (in_webview/_switch_to_webview_with_race_retry): "
                "попытка %d/%d провалена транзиентной сигнатурой %r, ретраю",
                attempt, _WEBVIEW_SWITCH_RACE_RETRIES, matched_signature,
            )
            if attempt < _WEBVIEW_SWITCH_RACE_RETRIES:
                time.sleep(_WEBVIEW_SWITCH_RACE_BACKOFF)
    raise last_race_exc


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
    """Временно переключается в WebView и гарантированно возвращается в нативный контекст.

    Переключение (`driver.switch_to.context`) идёт через
    `_switch_to_webview_with_race_retry` — bounded-ретрай узкой транзиентной
    гонки AT-BUG-047 choke point 2 (см. докстринг модуля); наружу не долетает,
    вызывающему коду ничего не нужно менять."""
    name = wait_for_webview(driver, timeout)
    _switch_to_webview_with_race_retry(driver, name)
    try:
        yield name
    finally:
        to_native(driver)
