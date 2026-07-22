"""Device-free юнит-проба ветки таймаута навигации — AT-BUG-025, attempt 2
(critic REJECT B1 на attempt 1).

Attempt 1 заявил, что `urllib3.exceptions.ReadTimeoutError` наследует
ВСТРОЕННЫЙ `TimeoutError` — это было ЛОЖНО (см. `bugs/AT-BUG-025.md`,
запись critic'а и корректирующая запись test-maintainer). Три зелёных
прогона attempt 1 проверяли только happy-path (страницы грузились в срок) —
ветка таймаута (`except TimeoutError` в `open_live_listing`/
`open_unreachable_url`) НИ РАЗУ не исполнялась, поэтому дефект (реальный
`urllib3.exceptions.ReadTimeoutError`, не пойманный `except TimeoutError`
builtins) не проявился.

Эта проба — синтетический hang БЕЗ реального устройства/сети (в духе
`test_subprocess_timeout_unit.py`, AT-BUG-009): фейковый `driver.get()`
кидает РЕАЛЬНЫЕ `urllib3.exceptions.ReadTimeoutError`/`MaxRetryError`
(не имитацию, не подкласс builtin) — так же, как это делает боевой путь
(`RemoteConnection._request`, см. AT-BUG-007). Проверяет:
1. `navigate()` перехватывает оба urllib3-класса и перебрасывает их как
   ВСТРОЕННЫЙ `TimeoutError` (контракт для `framework/steps/`).
2. `open_live_listing` (retry-цикл интерстишла) реально ЛОВИТ этот
   `TimeoutError` на каждой неудавшейся попытке навигации (`continue`
   ретрай-цикла, не крах) — вызывает `driver.get()` больше одного раза
   в пределах бюджета, прежде чем сдаться `TimeoutException`.
3. `open_unreachable_url` глотает тот же `TimeoutError` (`except
   TimeoutError: pass`) вместо падения наружу необработанным urllib3-типом.

НЕ требует устройства/эмулятора: `driver` — простой фейк, не
`webdriver.Remote`. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` — та иначе дёрнула бы `adb pm list
packages` при сборе тестов.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import allure
import pytest
from selenium.common.exceptions import TimeoutException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from framework.core.navigate import navigate
from framework.steps import browser_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


class _FakeSwitchTo:
    def __init__(self, driver: "_FakeWebviewDriver") -> None:
        self._driver = driver

    def context(self, name: str) -> None:
        self._driver._current_context = name


class _FakeWebviewDriver:
    """Минимальный фейк Appium-драйвера: достаточно атрибутов, чтобы пройти
    `contexts.in_webview` (переключение в WEBVIEW-контекст и обратно) и вызвать
    `navigate()`/`driver.get()`. `get_side_effect` — исключение, которое кидает
    КАЖДЫЙ вызов `.get()` (имитация зависшего `driver.get()`, оборванного
    client-side read-timeout — тот же путь, что и боевой код)."""

    def __init__(self, get_side_effect: Exception):
        self.command_executor = SimpleNamespace(
            _client_config=SimpleNamespace(timeout=999)
        )
        self._current_context = "NATIVE_APP"
        self.switch_to = _FakeSwitchTo(self)
        self.get_calls = 0
        self._get_side_effect = get_side_effect

    @property
    def contexts(self):
        return ["NATIVE_APP", "WEBVIEW_com.example.ao3"]

    @property
    def current_context(self):
        return self._current_context

    def get(self, url: str) -> None:
        self.get_calls += 1
        raise self._get_side_effect


def _read_timeout_error() -> ReadTimeoutError:
    return ReadTimeoutError(None, "http://fake-appium/get", "Read timed out.")


def _max_retry_error() -> MaxRetryError:
    return MaxRetryError(None, "http://fake-appium/get")


@pytest.mark.p2
@allure.id("AT-BUG-025-navigate-converts-read-timeout-error")
@allure.title("Проба: navigate() перехватывает urllib3.ReadTimeoutError и перебрасывает встроенным TimeoutError (device-free)")
def test_navigate_converts_read_timeout_error_to_builtin():
    # Given driver.get() падает РЕАЛЬНЫМ urllib3.exceptions.ReadTimeoutError
    # (НЕ наследует builtin TimeoutError — проверено эмпирически, см.
    # bugs/AT-BUG-025.md, запись critic'а)
    driver = _FakeWebviewDriver(get_side_effect=_read_timeout_error())

    # When вызван navigate() с истёкшим (сфейканным) таймаутом
    # Then наружу вылетает ВСТРОЕННЫЙ TimeoutError, не urllib3-тип
    with pytest.raises(TimeoutError) as exc_info:
        navigate(driver, "https://archiveofourown.org/tos", timeout=5)

    assert type(exc_info.value) is TimeoutError, (
        f"navigate() обязан перебрасывать builtin TimeoutError, получили "
        f"{type(exc_info.value)!r}"
    )
    assert "Read timed out" in str(exc_info.value)
    # Имя ИСХОДНОГО urllib3-класса сохранено первым токеном сообщения — иначе
    # compensating rerun (framework/pytest.ini --only-rerun
    # ReadTimeoutError|MaxRetryError) не сработает на трёх call-site'ах, что
    # НЕ оборачивают navigate() в try/except (open_stable_tall_page,
    # open_listing, open_url_and_wait_ready) — там builtin TimeoutError
    # долетает до pytest как есть, и `_try_match_error` матчит регекс против
    # `f"{type.__name__}: {value}"`.
    assert str(exc_info.value).startswith("ReadTimeoutError: ")
    # client_config.timeout восстановлен в finally несмотря на исключение
    assert driver.command_executor._client_config.timeout == 999


@pytest.mark.p2
@allure.id("AT-BUG-025-navigate-converts-max-retry-error")
@allure.title("Проба: navigate() перехватывает urllib3.MaxRetryError и перебрасывает встроенным TimeoutError (device-free)")
def test_navigate_converts_max_retry_error_to_builtin():
    # Given запасной случай из AT-BUG-007 B2 (retries где-то остались включены)
    driver = _FakeWebviewDriver(get_side_effect=_max_retry_error())

    with pytest.raises(TimeoutError) as exc_info:
        navigate(driver, "https://archiveofourown.org/tos", timeout=5)

    assert type(exc_info.value) is TimeoutError
    assert str(exc_info.value).startswith("MaxRetryError: ")
    assert driver.command_executor._client_config.timeout == 999


@pytest.mark.p2
@allure.id("AT-BUG-025-navigate-timeout-still-matches-pytest-ini-rerun-pattern")
@allure.title("Проба: TimeoutError от navigate() всё ещё матчит framework/pytest.ini --only-rerun (регресс-гвард для незащищённых call-site'ов)")
def test_navigate_timeout_message_matches_pytest_ini_rerun_regex():
    """Регресс-гвард на класс дефекта attempt 2: конвертация в builtin
    `TimeoutError` сама по себе рисковала СЛОМАТЬ compensating rerun
    (`framework/pytest.ini`, `--only-rerun ReadTimeoutError|MaxRetryError`)
    на трёх call-site'ах, которые НЕ оборачивают `navigate()` в try/except
    (`open_stable_tall_page`, `open_listing`, `open_url_and_wait_ready`) —
    там `TimeoutError` долетел бы до pytest как есть, и голое имя класса
    `"TimeoutError"` не матчит регекс `ReadTimeoutError|MaxRetryError`
    (нужен префикс Read/Max). Эта проба воспроизводит ТОЧНУЮ формулу
    матчинга `pytest_rerunfailures._try_match_error`
    (`f"{excinfo.type.__name__}: {excinfo.value}"`, `re.search` против
    паттерна из `pytest.ini`), не текст самого pytest.ini — если формула
    матчинга плагина когда-нибудь изменится, эта проба перестанет быть
    актуальной гарантией и должна быть пересмотрена вместе с ней."""
    only_rerun_pattern = "ReadTimeoutError|MaxRetryError"  # framework/pytest.ini addopts

    for side_effect in (_read_timeout_error(), _max_retry_error()):
        driver = _FakeWebviewDriver(get_side_effect=side_effect)
        with pytest.raises(TimeoutError) as exc_info:
            navigate(driver, "https://archiveofourown.org/tos", timeout=5)

        matched_text = f"{type(exc_info.value).__name__}: {exc_info.value}"
        assert re.search(only_rerun_pattern, matched_text), (
            f"builtin TimeoutError, переброшенный navigate(), не матчит "
            f"--only-rerun {only_rerun_pattern!r} (matched_text={matched_text!r}) "
            f"— compensating rerun сломался бы на незащищённых call-site'ах"
        )


@pytest.mark.p2
@allure.id("AT-BUG-025-open-live-listing-retries-on-navigate-timeout")
@allure.title("Проба: open_live_listing реально ретраит зависший driver.get() (retry-цикл ловит TimeoutError, не крашится и не съедает весь бюджет одной попыткой)")
def test_open_live_listing_retries_through_navigate_timeout():
    """Ядро дефекта attempt 1 (B1 critic'а): `except TimeoutError` (builtins) в
    retry-цикле НЕ ловил реальный `urllib3.exceptions.ReadTimeoutError` —
    первая же зависшая попытка навигации падала необработанным исключением
    наружу теста вместо `continue` ретрай-цикла. Эта проба форсирует именно
    эту ветку: КАЖДЫЙ `driver.get()` виснет (имитация), бюджет достаточен для
    НЕСКОЛЬКИХ попыток — если бы TimeoutError не ловился, тест упал бы
    необработанным `ReadTimeoutError` уже на первой попытке вместо ожидаемого
    `TimeoutException` после исчерпания бюджета."""
    driver = _FakeWebviewDriver(get_side_effect=_read_timeout_error())

    # When бюджет (1s) достаточен для нескольких быстрых попыток (фейк не спит
    # реально — каждая попытка "зависает" мгновенно и тут же кидает
    # ReadTimeoutError), но НИ ОДНА попытка не приносит блёрбы (их не будет
    # никогда — driver.get() всегда падает)
    # Then после исчерпания бюджета — ожидаемый TimeoutException ретрай-цикла
    # (НЕ необработанный urllib3.exceptions.ReadTimeoutError)
    with pytest.raises(TimeoutException) as exc_info:
        browser_steps.open_live_listing(driver, "https://archiveofourown.org/works", timeout=1)

    # И ретрай-цикл реально СДЕЛАЛ несколько попыток навигации (не упал на
    # первой же) — доказательство, что TimeoutError от navigate() ловится
    # именно тем except, что стоит в retry-цикле, а не пролетает мимо
    assert driver.get_calls >= 2, (
        f"retry-цикл open_live_listing должен был повторить navigate() "
        f"несколько раз в пределах бюджета, вызовов driver.get(): {driver.get_calls}"
    )
    # Причина финального TimeoutException — builtin TimeoutError от navigate(),
    # не сырой urllib3.exceptions.ReadTimeoutError
    assert isinstance(exc_info.value.__cause__, TimeoutError)
    assert type(exc_info.value.__cause__) is TimeoutError


@pytest.mark.p2
@allure.id("AT-BUG-025-open-unreachable-url-swallows-navigate-timeout")
@allure.title("Проба: open_unreachable_url глотает TimeoutError от navigate() вместо падения наружу")
def test_open_unreachable_url_swallows_navigate_timeout():
    driver = _FakeWebviewDriver(get_side_effect=_max_retry_error())

    # When driver.get() внутри navigate() виснет (MaxRetryError -> builtin
    # TimeoutError) Then open_unreachable_url НЕ поднимает исключение наружу
    # (except TimeoutError: pass) — реальную проверку итога делает следующий
    # шаг (assert_error_page_shown), не эта функция
    browser_steps.open_unreachable_url(driver, "https://nonexistent.invalid.test/", timeout=5)

    assert driver.get_calls == 1
