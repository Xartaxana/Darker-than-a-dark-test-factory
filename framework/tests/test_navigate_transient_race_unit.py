"""Device-free юнит-проба bounded-ретрая choke point 1/2 AT-BUG-047
(`core/navigate.py::navigate`) — attempt 3, реконструкция attempt 2 после
утраты байтовой копии по протоколу байтовой копии (housekeeping п.8
CLAUDE.md; провенанс — `bugs/AT-BUG-047.md`, запись координатора
2026-08-04T19:31:00Z).

Гонка: `wait_ui_ready` (`framework/steps/app_steps.py`) — барьер только по
присутствию нативной оболочки, БЕЗ ожидания оседания стартовой загрузки
Home. Следующий же `navigate()` (`driver.get`) может застать WebView-цель
ещё не готовой — chromedriver кидает:

```
selenium.common.exceptions.WebDriverException: Message: unknown error:
cannot determine loading status from no such window
```

Эта проба — синтетическая гонка БЕЗ реального устройства (в духе
`test_navigate_timeout_unit.py`, AT-BUG-025 и `test_mitm_port_race_unit.py`):
фейковый `driver.get()` кидает РЕАЛЬНЫЙ `selenium.common.exceptions.
WebDriverException` с ТОЧНОЙ сигнатурой падения (или другой, контрольной)
заданное число раз перед успехом/никогда. Проверяет:
1. Ровно эта сигнатура — ретраится, узкое окно закрывается прозрачно для
   вызывающего кода (`navigate()` возвращается без исключения).
2. Ретрай bounded — исчерпание попыток поднимает исходный
   `WebDriverException` (не глотается навечно, не маскировка).
3. ЛЮБАЯ ДРУГАЯ сигнатура `WebDriverException` (в т.ч. родственная
   сигнатура choke point 2, `contexts.in_webview`) НЕ ретраится — падает на
   первой же попытке. Это регресс-гвард класса «не превращать точечный
   реактивный ретрай в общую ловушку WebView-гонок» (CLAUDE.md
   test-maintainer: «не чини падение маскировкой»).
4. Ретрай не ломает существующую ветку `ReadTimeoutError`/`MaxRetryError`
   (AT-BUG-025) — те продолжают конвертироваться в builtin `TimeoutError`
   на первой же попытке, без лишних вызовов `driver.get()`.

НЕ требует устройства/эмулятора. Переопределяет session-scoped autouse-
фикстуру `_ensure_app_installed` из `conftest.py`, как и
`test_navigate_timeout_unit.py`."""
from __future__ import annotations

from types import SimpleNamespace

import allure
import pytest
from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from framework.core.navigate import (
    _TRANSIENT_RACE_RETRIES,
    _TRANSIENT_RACE_SIGNATURE,
    navigate,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретрай `navigate()` не должен ждать реальные секунды в юнит-пробе —
    считаем вызовы, но не спим (тот же приём, что `test_mitm_port_race_unit.py`,
    AT-BUG-043)."""
    calls = {"n": 0}
    import framework.core.navigate as navigate_module
    monkeypatch.setattr(navigate_module.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


class _FakeRacingDriver:
    """Фейковый Appium-драйвер: `.get()` кидает `get_side_effect` на первые
    `fail_times` вызовов, затем "успевает" (успешный no-op возврат)."""

    def __init__(self, exc_factory, fail_times: int):
        self.command_executor = SimpleNamespace(
            _client_config=SimpleNamespace(timeout=999)
        )
        self.get_calls = 0
        self._exc_factory = exc_factory
        self._fail_times = fail_times

    def get(self, url: str) -> None:
        self.get_calls += 1
        if self.get_calls <= self._fail_times:
            raise self._exc_factory()
        return None


def _race_signature_exc() -> WebDriverException:
    return WebDriverException(
        "Message: unknown error: cannot determine loading status from no "
        "such window\n  (Session info: chrome=113.0.5672.136)"
    )


def _unrelated_webdriver_exc() -> WebDriverException:
    return WebDriverException("Message: element not interactable")


def _webview_switch_race_exc() -> WebDriverException:
    """Родственная, но ОТЛИЧНАЯ сигнатура choke point 2 (`contexts.in_webview`,
    AT-BUG-047) — доказывает, что navigate() не проглатывает чужой маркер."""
    return WebDriverException(
        "A new session could not be created. Details: session not created "
        "from no such execution context: loader has changed while "
        "resolving nodes"
    )


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-retries-narrow-race-signature")
@allure.title("Проба: navigate() ретраит ТОЛЬКО узкую сигнатуру AT-BUG-047 и возвращается без исключения (device-free)")
def test_navigate_retries_and_recovers_from_race_signature():
    # Given первые 2 вызова driver.get() падают ТОЧНОЙ сигнатурой гонки,
    # 3-й (в пределах bounded-бюджета) — успевает
    driver = _FakeRacingDriver(_race_signature_exc, fail_times=2)
    assert _TRANSIENT_RACE_RETRIES >= 3, "проба рассчитана на бюджет >=3 попыток"

    # When/Then navigate() не поднимает исключение наружу — ретрай закрыл гонку
    navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert driver.get_calls == 3, (
        f"ожидались ровно 2 неудачные + 1 успешная попытка driver.get(), "
        f"получили {driver.get_calls}"
    )
    # client_config.timeout восстановлен после всех попыток
    assert driver.command_executor._client_config.timeout == 999


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-race-retry-is-bounded")
@allure.title("Проба: ретрай узкой сигнатуры bounded — исчерпание попыток поднимает исходное исключение, не маскирует")
def test_navigate_race_retry_bounded_reraises_after_exhaustion():
    # Given driver.get() падает узкой сигнатурой ВСЕГДА (гонка не проходит
    # в пределах bounded-бюджета — например структурная поломка, а не транзиент)
    driver = _FakeRacingDriver(_race_signature_exc, fail_times=_TRANSIENT_RACE_RETRIES + 5)

    with pytest.raises(WebDriverException) as exc_info:
        navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert _TRANSIENT_RACE_SIGNATURE in str(exc_info.value)
    assert driver.get_calls == _TRANSIENT_RACE_RETRIES, (
        f"ретрай обязан быть bounded ровно {_TRANSIENT_RACE_RETRIES} попытками, "
        f"получили {driver.get_calls}"
    )
    # timeout восстановлен несмотря на итоговое исключение
    assert driver.command_executor._client_config.timeout == 999


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-does-not-retry-unrelated-webdriver-exception")
@allure.title("Проба: navigate() НЕ ретраит посторонний WebDriverException — не маскирует настоящую поломку")
def test_navigate_does_not_retry_unrelated_webdriver_exception():
    driver = _FakeRacingDriver(_unrelated_webdriver_exc, fail_times=1)

    with pytest.raises(WebDriverException) as exc_info:
        navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert "element not interactable" in str(exc_info.value)
    # Ни одной повторной попытки — падает на первой же
    assert driver.get_calls == 1


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-does-not-retry-webview-switch-race-signature")
@allure.title("Проба: navigate() НЕ ретраит родственную сигнатуру choke point 2 (contexts.in_webview) — раздельные маркеры")
def test_navigate_does_not_retry_webview_switch_race_signature():
    """Регресс-гвард класса: критик-диагноз AT-BUG-047 явно требует
    РАЗДЕЛЬНЫХ узких маркеров ретрая для двух choke points, не одной общей
    ловушки «WebView race». `navigate()` не должен подхватывать сигнатуру
    `contexts.in_webview` (свой маркер и своя проба — см.
    `test_in_webview_transient_race_unit.py`)."""
    driver = _FakeRacingDriver(_webview_switch_race_exc, fail_times=1)

    with pytest.raises(WebDriverException) as exc_info:
        navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert "loader has changed while resolving nodes" in str(exc_info.value)
    assert driver.get_calls == 1


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-read-timeout-error-still-not-retried-as-race")
@allure.title("Проба: ветка ReadTimeoutError/MaxRetryError (AT-BUG-025) не задета новым ретраем — падает на первой попытке")
def test_navigate_read_timeout_error_branch_unaffected_by_race_retry():
    driver = _FakeRacingDriver(lambda: ReadTimeoutError(None, "http://fake-appium/get", "Read timed out."), fail_times=1)

    with pytest.raises(TimeoutError) as exc_info:
        navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert type(exc_info.value) is TimeoutError
    assert str(exc_info.value).startswith("ReadTimeoutError: ")
    assert driver.get_calls == 1
    assert driver.command_executor._client_config.timeout == 999


@pytest.mark.p2
@allure.id("AT-BUG-047-navigate-max-retry-error-still-not-retried-as-race")
@allure.title("Проба: MaxRetryError (AT-BUG-025 запасной случай) не задет новым ретраем — падает на первой попытке")
def test_navigate_max_retry_error_branch_unaffected_by_race_retry():
    driver = _FakeRacingDriver(lambda: MaxRetryError(None, "http://fake-appium/get"), fail_times=1)

    with pytest.raises(TimeoutError) as exc_info:
        navigate(driver, "https://archiveofourown.org/works", timeout=5)

    assert type(exc_info.value) is TimeoutError
    assert str(exc_info.value).startswith("MaxRetryError: ")
    assert driver.get_calls == 1
