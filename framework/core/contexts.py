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


def _current_window_handle_or_none(driver) -> str | None:
    """AT-BUG-070 rework (критик round1, блокер B2): фиксирует УЖЕ выбранное
    chromedriver-окно НА ВХОДЕ в `in_webview_matching`/`in_webview_handle`, ДО
    того как они переключат его — используется для восстановления в `finally`.

    Без этого выход из этих примитивов молча оставлял driver переключённым на
    ПОСЛЕДНЕЕ проитерированное (`in_webview_matching`, включая оба отказных
    пути — `NoMatchingWebviewWindow`/`AssertionError` на цикле) либо адресованное
    (`in_webview_handle`) окно — обычный ПОСЛЕДУЮЩИЙ `contexts.in_webview` на
    эту же chromedriver-сессию (window handles живут на уровне chromedriver,
    не Appium `contexts`, см. докстринг `in_webview_matching` — переключение в
    NATIVE и обратно в WEBVIEW их не сбрасывает) молча читал/исполнял бы JS на
    оставленной, не активной вкладке.

    `None`, если на входе ещё нет ни одного выбранного окна (WebDriverException
    — самый первый вызов на этой chromedriver-сессии, восстанавливать нечего)."""
    try:
        return driver.current_window_handle
    except WebDriverException:
        return None


@contextlib.contextmanager
def in_webview_handle(driver, handle: str, timeout: int | None = None):
    """AT-BUG-070 — переключается на УЖЕ ИЗВЕСТНЫЙ `window_handles`-handle
    (см. `in_webview_matching`) напрямую, без повторного матчинга по
    predicate. Нужен, когда вызывающий код уже один раз адресовал нужную
    вкладку (например, по нативному заголовку чипа ДО навигации) и должен
    вернуться к ТОЙ ЖЕ вкладке ПОСЛЕ действия, которое могло изменить
    матчащий признак (напр. `document.title`/URL после навигации внутри
    страницы) — эмпирически подтверждено (test-maintainer, 2026-08-16):
    набор `window_handles` идентичен (тот же `set`) после выхода из
    `in_webview` и повторного входа, т.е. сам handle остаётся валиден и
    адресует ТУ ЖЕ живую WebView независимо от смены её url/title.

    AT-BUG-070 rework (критик round1, блокер B2): восстанавливает РАНЕЕ
    выбранное окно (см. `_current_window_handle_or_none`) в `finally` на
    выходе — не оставляет driver прилипшим к `handle` для последующих,
    независимых вызовов `in_webview`."""
    with in_webview(driver, timeout):
        original_handle = _current_window_handle_or_none(driver)
        try:
            driver.switch_to.window(handle)
            yield handle
        finally:
            if original_handle is not None:
                driver.switch_to.window(original_handle)


class NoMatchingWebviewWindow(RuntimeError):
    """AT-BUG-070: ни один `driver.window_handles` не удовлетворил предикату
    адресации — несёт список кандидатов (url, title) для диагностики, не
    просто "не нашли"."""


@contextlib.contextmanager
def in_webview_matching(driver, predicate, timeout: int | None = None, description: str = ""):
    """AT-BUG-070 (test_debt, Fixed) — адресует `execute_script`/`driver.get`/
    чтение DOM-состояния к КОНКРЕТНОЙ живой `android.webkit.WebView`, пока
    ДРУГИЕ WebView (в т.ч. вкладка-0) тоже живы, БЕЗ свёртки числа вкладок к
    одной (reduce-to-one).

    Класс проблемы (`browser_screen.py`, докстринг у `tab_chip_locator`,
    AT-BUG-018/019/022): при >1 живом `android.webkit.WebView` Appium/
    chromedriver экспонирует РОВНО ОДИН **контекст** `WEBVIEW_<pkg>`
    (`driver.contexts`/`webview_name()` выше) вне зависимости от числа
    вкладок — переключение `driver.switch_to.context(...)` не может выбрать
    конкретную вкладку. НО chromedriver, однажды подключённый к ЭТОМУ
    контексту, видит остальные живые WebView-инстансы того же процесса как
    ОТДЕЛЬНЫЕ **окна** (CDP targets) — Selenium-уровневый
    `driver.window_handles`/`driver.switch_to.window(handle)` (НЕ Appium
    `contexts` API) даёт РОВНО один handle НА КАЖДУЮ живую вкладку, включая
    вкладку-0. Эмпирически подтверждено (test-maintainer, 2026-08-16, живой
    прогон, 3 вкладки — Home/marker1/marker2):
    - `driver.window_handles` внутри `in_webview` вернул 3 РАЗНЫХ handle;
      `switch_to.window(h)` + `current_url`/`title` на каждом дал 3 РАЗНЫХ
      пары (Home/marker1/marker2) — не одно и то же "прилипшее" значение;
    - ИЗОЛЯЦИЯ: JS-глобал (`window.__probe`), записанный на handle вкладки
      2, НЕ виден на handle вкладки 1 или вкладки 0 (`None`/`undefined`) —
      подтверждает, что это НЕЗАВИСИМЫЕ JS-контексты, не общий sticky-объект;
    - `window.scrollTo` на handle вкладки 2 НЕ изменил `scrollY`, прочитанный
      на handle вкладки 1 (0 -> 0) — та же изоляция для скролла;
    - СТАБИЛЬНОСТЬ: набор handle идентичен (тот же `set`) после выхода из
      `in_webview` (`to_native`) и повторного входа — можно закэшировать
      handle между отдельными `in_webview`-блоками в рамках одного теста
      (не проверено между РАЗНЫМИ вкладками/действиями, вызывающими
      создание/уничтожение WebView — новый `open_tab`/закрытие вкладки может
      изменить набор, матчить заново после таких действий).

    `predicate(url, title)` — функция сопоставления; НЕ `current_url`-
    угадывание (критерий готовности AT-BUG-070 явно требует "другого
    способа") — вызывающий код обязан знать признак цели ЗАРАНЕЕ (известный
    URL/URL-подстрока, известный `document.title` — на практике совпадает с
    нативным `TabInfo.title` чипа, см. `tab_chip_title_at`/`onReceivedTitle`
    в докстринге `tab_chip_locator`). Бросает `NoMatchingWebviewWindow` со
    списком ВСЕХ (handle, url, title)-кандидатов, если предикат не
    удовлетворён НИ ОДНИМ (диагностируемый отказ, не тихий no-op) — либо
    `AssertionError` с тем же списком, если предикату удовлетворяют ≥2
    (адресация неоднозначна, вызывающий код обязан сузить предикат).

    Оставляет driver переключённым на найденное окно ВНУТРИ `with`-блока;
    как и `in_webview`, гарантированно возвращает в нативный контекст на
    выходе (через вложенный `in_webview`).

    AT-BUG-070 rework (критик round1, блокер B2): восстанавливает РАНЕЕ
    выбранное окно (см. `_current_window_handle_or_none`) в `finally` на
    выходе — покрывает И успешный путь, И ОБА отказных (`NoMatchingWebviewWindow`
    при 0 совпадений, `AssertionError` при ≥2), которые иначе оставляли driver
    переключённым на ПОСЛЕДНЕЕ проитерированное в цикле окно, ломая молча
    ПОСЛЕДУЮЩИЙ независимый `in_webview`."""
    with in_webview(driver, timeout) as ctx_name:
        original_handle = _current_window_handle_or_none(driver)
        try:
            candidates = []
            matched = []
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                url = driver.current_url
                title = driver.title
                candidates.append((handle, url, title))
                if predicate(url, title):
                    matched.append(handle)
            if not matched:
                raise NoMatchingWebviewWindow(
                    f"ни одно окно WebView не удовлетворило предикату"
                    f"{f' ({description})' if description else ''}; кандидаты "
                    f"(handle, url, title): {candidates}"
                )
            if len(matched) > 1:
                raise AssertionError(
                    f"предикату{f' ({description})' if description else ''} удовлетворили "
                    f"{len(matched)} окон WebView одновременно — адресация неоднозначна; "
                    f"кандидаты (handle, url, title): {candidates}"
                )
            driver.switch_to.window(matched[0])
            yield matched[0]
        finally:
            if original_handle is not None:
                driver.switch_to.window(original_handle)
