"""Device-free юнит-проба bounded-ретрая choke point 2/2 AT-BUG-047
(`core/contexts.py::in_webview` / `_switch_to_webview_with_race_retry`) —
attempt 3. Критик-диагноз (`bugs/AT-BUG-047.md`, обсуждение
2026-08-04T19:31:00Z): attempt 2 закрыл ТОЛЬКО choke point 1
(`core/navigate.py`); полный `test_rating_listing.py` + `test_visibility.py`
дал 2 падения РОДСТВЕННОЙ, но ОТЛИЧНОЙ сигнатуры на переключении в
WEBVIEW-контекст (`AndroidUiautomator2Driver.setContext` ->
`startChromedriverProxy` -> `Chromedriver.start()`):

```
selenium.common.exceptions.WebDriverException: A new session could not be
created. Details: session not created from no such execution context:
loader has changed while resolving nodes
```

**Рецидив НОВОЙ сигнатурой (test-maintainer, 2026-08-11, `runs/RUN-20260811-0405.md`,
TC-009).** Тот же choke point оборвал handshake ДРУГИМ хвостом сообщения:

```
selenium.common.exceptions.WebDriverException: A new session could not be
created. Details: session not created from no such execution context:
uniqueContextId not found
```

Маркер расширен с одной строки до НАБОРА известных сигнатур
(`_WEBVIEW_SWITCH_RACE_SIGNATURES`) — классовая форма, не общий `except
WebDriverException`.

Эта проба — синтетическая гонка БЕЗ реального устройства (тот же паттерн,
что `test_navigate_transient_race_unit.py` для choke point 1): фейковый
`driver.switch_to.context()` кидает РЕАЛЬНЫЙ `WebDriverException` заданное
число раз перед успехом/никогда. Проверяет:
1. Обе известные сигнатуры набора ретраятся по отдельности, `in_webview`
   прозрачно восстанавливается (yield происходит, `to_native` вызывается в
   finally как обычно).
2. Ретрай bounded — исчерпание попыток поднимает исходный
   `WebDriverException` наружу `in_webview`.
3. ЛЮБАЯ ДРУГАЯ сигнатура `WebDriverException` (в т.ч. родственная
   сигнатура choke point 1, `core/navigate.py`) НЕ ретраится — падает на
   первой же попытке (раздельные маркеры — прямое требование критик-
   диагноза, не общая ловушка WebView-гонок).
4. При исчерпании бюджета/посторонней ошибке `in_webview` не успевает
   войти в контекст — `to_native` в `finally` НЕ падает (переключение в
   NATIVE — no-op, если контекст уже NATIVE).

НЕ требует устройства/эмулятора. Переопределяет session-scoped autouse-
фикстуру `_ensure_app_installed` из `conftest.py`, как и
`test_navigate_timeout_unit.py`."""
from __future__ import annotations

from types import SimpleNamespace

import allure
import pytest
from selenium.common.exceptions import WebDriverException

from framework.core.contexts import (
    _WEBVIEW_SWITCH_RACE_RETRIES,
    _WEBVIEW_SWITCH_RACE_SIGNATURES,
    in_webview,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретрай `_switch_to_webview_with_race_retry()` не должен ждать
    реальные секунды в юнит-пробе — считаем вызовы, но не спим (тот же
    приём, что `test_mitm_port_race_unit.py`, AT-BUG-043)."""
    calls = {"n": 0}
    import framework.core.contexts as contexts_module
    monkeypatch.setattr(contexts_module.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


class _FakeSwitchTo:
    def __init__(self, driver: "_FakeContextRacingDriver") -> None:
        self._driver = driver

    def context(self, name: str) -> None:
        if name == self._driver.webview_context_name:
            self._driver.switch_calls += 1
            if self._driver.switch_calls <= self._driver._fail_times:
                raise self._driver._exc_factory()
        self._driver._current_context = name


class _FakeContextRacingDriver:
    """Фейковый Appium-драйвер: переключение в WEBVIEW-контекст
    (`switch_to.context(<webview name>)`) падает `exc_factory()` на первые
    `fail_times` вызовов, затем "успевает". Переключение обратно в
    NATIVE_APP (`to_native`) всегда успешно — тот choke point вне скоупа
    этой пробы. `switch_calls` считает ТОЛЬКО попытки переключения в
    webview (не финальный возврат в NATIVE_APP из `finally`)."""

    webview_context_name = "WEBVIEW_com.example.ao3"

    def __init__(self, exc_factory, fail_times: int):
        self._current_context = "NATIVE_APP"
        self.switch_to = _FakeSwitchTo(self)
        self.switch_calls = 0
        self._exc_factory = exc_factory
        self._fail_times = fail_times

    @property
    def contexts(self):
        return ["NATIVE_APP", self.webview_context_name]

    @property
    def current_context(self):
        return self._current_context


def _webview_switch_race_exc() -> WebDriverException:
    return WebDriverException(
        "A new session could not be created. Details: session not created "
        "from no such execution context: loader has changed while "
        "resolving nodes"
    )


def _webview_switch_race_exc_unique_context_id() -> WebDriverException:
    """Рецидив 2026-08-11 (`RUN-20260811-0405.md`, TC-009) — ТОТ ЖЕ choke
    point, ДРУГОЙ хвост сообщения chromedriver."""
    return WebDriverException(
        "A new session could not be created. Details: session not created "
        "from no such execution context: uniqueContextId not found "
        "(chrome=113.0.5672.136)"
    )


def _unrelated_webdriver_exc() -> WebDriverException:
    return WebDriverException("Message: chrome not reachable")


def _navigate_race_signature_exc() -> WebDriverException:
    """Родственная, но ОТЛИЧНАЯ сигнатура choke point 1 (`core/navigate.py`,
    AT-BUG-047) — доказывает, что `in_webview` не подхватывает чужой маркер."""
    return WebDriverException(
        "Message: unknown error: cannot determine loading status from no "
        "such window\n  (Session info: chrome=113.0.5672.136)"
    )


@pytest.mark.p2
@allure.id("AT-BUG-047-in-webview-retries-narrow-race-signature")
@allure.title("Проба: in_webview() ретраит набор из двух узких сигнатур choke point 2 и входит в контекст без исключения (device-free)")
@pytest.mark.parametrize(
    "exc_factory",
    [_webview_switch_race_exc, _webview_switch_race_exc_unique_context_id],
    ids=["loader-has-changed", "unique-context-id-not-found"],
)
def test_in_webview_retries_and_recovers_from_race_signature(exc_factory):
    assert _WEBVIEW_SWITCH_RACE_RETRIES >= 3, "проба рассчитана на бюджет >=3 попыток"
    driver = _FakeContextRacingDriver(exc_factory, fail_times=2)

    with in_webview(driver, timeout=5) as name:
        assert name == driver.webview_context_name
        assert driver.current_context == driver.webview_context_name

    # finally вернул контекст в NATIVE_APP как обычно
    assert driver.current_context == "NATIVE_APP"
    assert driver.switch_calls == 3, (
        f"ожидались ровно 2 неудачные + 1 успешная попытка switch_to.context(), "
        f"получили {driver.switch_calls}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-047-in-webview-race-retry-is-bounded")
@allure.title("Проба: ретрай choke point 2 bounded — исчерпание попыток поднимает исходное исключение наружу in_webview")
@pytest.mark.parametrize(
    "exc_factory, expected_signature",
    [
        (_webview_switch_race_exc, "loader has changed while resolving nodes"),
        (_webview_switch_race_exc_unique_context_id, "uniqueContextId not found"),
    ],
    ids=["loader-has-changed", "unique-context-id-not-found"],
)
def test_in_webview_race_retry_bounded_reraises_after_exhaustion(exc_factory, expected_signature):
    driver = _FakeContextRacingDriver(
        exc_factory, fail_times=_WEBVIEW_SWITCH_RACE_RETRIES + 5
    )

    with pytest.raises(WebDriverException) as exc_info:
        with in_webview(driver, timeout=5):
            pytest.fail("контекст не должен быть достигнут — все попытки провалены")

    # N1 (критик-вход TC-009): сверяем СИГНАТУРУ, СООТВЕТСТВУЮЩУЮ параметру
    # exc_factory — не "любую из набора" (`any(...)` не поймал бы проброс
    # "не той" сигнатуры набора при параметризации).
    assert expected_signature in str(exc_info.value), (
        f"переброшенное исключение обязано нести СВОЮ сигнатуру `{expected_signature}` "
        f"(exc_factory={exc_factory.__name__}), получили: {exc_info.value}"
    )
    assert driver.switch_calls == _WEBVIEW_SWITCH_RACE_RETRIES, (
        f"ретрай обязан быть bounded ровно {_WEBVIEW_SWITCH_RACE_RETRIES} "
        f"попытками, получили {driver.switch_calls}"
    )
    # НЕ переключились в webview ни разу успешно
    assert driver.current_context == "NATIVE_APP"


@pytest.mark.p2
@allure.id("AT-BUG-047-in-webview-does-not-retry-unrelated-webdriver-exception")
@allure.title("Проба: in_webview() НЕ ретраит посторонний WebDriverException — не маскирует настоящую поломку")
def test_in_webview_does_not_retry_unrelated_webdriver_exception():
    driver = _FakeContextRacingDriver(_unrelated_webdriver_exc, fail_times=1)

    with pytest.raises(WebDriverException) as exc_info:
        with in_webview(driver, timeout=5):
            pytest.fail("контекст не должен быть достигнут")

    assert "chrome not reachable" in str(exc_info.value)
    assert driver.switch_calls == 1


@pytest.mark.p2
@allure.id("AT-BUG-047-in-webview-does-not-retry-navigate-race-signature")
@allure.title("Проба: in_webview() НЕ ретраит родственную сигнатуру choke point 1 (core/navigate.py) — раздельные маркеры")
def test_in_webview_does_not_retry_navigate_race_signature():
    """Регресс-гвард класса: критик-диагноз AT-BUG-047 явно требует
    РАЗДЕЛЬНЫХ узких маркеров ретрая для двух choke points, не одной общей
    ловушки «WebView race». `in_webview()` не должен подхватывать сигнатуру
    `core/navigate.py` (свой маркер и своя проба —
    `test_navigate_transient_race_unit.py`)."""
    driver = _FakeContextRacingDriver(_navigate_race_signature_exc, fail_times=1)

    with pytest.raises(WebDriverException) as exc_info:
        with in_webview(driver, timeout=5):
            pytest.fail("контекст не должен быть достигнут")

    assert "cannot determine loading status from no such window" in str(exc_info.value)
    assert driver.switch_calls == 1
