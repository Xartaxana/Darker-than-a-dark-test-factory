"""Device-free юнит-проба verification-ветки AT-BUG-062 rework (attempt 2,
критик-вход opus, 2026-08-11) — блокер «новые ветки отказа не исполнены ни
разу»: все 4 контрольных прогона attempt 1 (`enter_rename_name` verification
poll, `assert_filter_profile_listed` DB-truth на провале) были зелёными, сам
новый код ни разу не сработал по КРАСНОЙ ветке. Эта проба исполняет обе новые
ветки отказа фейковым driver'ом/фейковой БД, без устройства.

Покрывает:
1. `SettingsScreen.enter_rename_name`: поле после `clear()`+`send_keys` весь
   бюджет (1.5с) показывает ДРУГОЙ текст -> падает `AssertionError` с
   диагностическим сообщением (не таймаут/не сырое исключение Selenium).
2. `enter_rename_name`: поле «догоняет» ожидаемое значение В ПРЕДЕЛАХ бюджета
   (settle) -> зелёный, исключение не поднимается.
3. `enter_rename_name`: чтение поля для diagnostic-сообщения ЗАЩИЩЕНО —
   `IMPLICIT_WAIT=0` (`framework/config/settings.py`) означает, что
   незащищённое чтение stale/исчезнувшего поля кинуло бы сырой
   `NoSuchElementException` вместо диагностического `AssertionError`
   (попутный дефект, найденный критиком при rework); эта проба симулирует
   поле, ставшее недоступным, и проверяет, что наружу уходит именно
   `AssertionError` с placeholder-текстом, а не сырое исключение Selenium.
4. `settings_steps.assert_filter_profile_listed`: сообщение на провале несёт
   ФАКТИЧЕСКИЙ список имён из БД (`seed_db.read_filter_profiles`, мокнута),
   не только факт отсутствия — различает гипотезу 1 (имя другое) от
   гипотезы 2 (строка не поймана прокруткой, AT-BUG-048).

Фейковые часы (`_FakeClock`) — тот же приём, что
`test_swipe_to_text_settle_unit.py` (AT-BUG-048): подставлены вместо
`framework.core.waits.time`, единственного места реального ожидания внутри
`poll_for` (используемого `enter_rename_name`).

Не требует устройства/эмулятора. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (тот же приём, что
`test_swipe_to_text_settle_unit.py`/`test_navigate_timeout_unit.py`,
AT-BUG-025) — та иначе дёрнула бы `adb pm list packages` при сборе тестов.
"""
from __future__ import annotations

import allure
import pytest
from selenium.common.exceptions import NoSuchElementException

from framework.core import waits
from framework.data import seed_db
from framework.screens.settings_screen import SettingsScreen
from framework.steps import settings_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


class _FakeClock:
    """Подставляется вместо `framework.core.waits.time` — `poll_for`
    (единственное место реального ожидания внутри `enter_rename_name`)
    продвигает эти часы через `.sleep()`, а не спит по-настоящему."""

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _fake_clock(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(waits, "time", clock)
    return clock


class _FakeRenameFieldElement:
    def __init__(self, driver: "_FakeRenameDriver") -> None:
        self._driver = driver

    def clear(self) -> None:  # содержимое отслеживает сам driver через resolve_text
        pass

    def send_keys(self, value: str) -> None:
        del value
        self._driver.send_time = self._driver.clock.time()

    def get_attribute(self, name: str):
        return self._driver.current_field_text() if name == "text" else None


class _FakeRenameDriver:
    """Минимальный фейк Appium-драйвера для `SettingsScreen.enter_rename_name`.

    `resolve_text(elapsed)` — что реально показывает поле через `elapsed`
    фейковых секунд ПОСЛЕ `send_keys` (симулирует расхождение ввода/задержку
    recomposition). `raise_find_element`, если задан, заставляет ВТОРОЙ и
    последующие вызовы `find_element` кидать это исключение (симулирует
    поле, ставшее stale/исчезнувшее к моменту diagnostic-чтения) — ПЕРВЫЙ
    вызов (начальный `self.find(...)` внутри `enter_rename_name`) всегда
    успешен, иначе `wait_until` реально ждал бы `DEFAULT_TIMEOUT` секунд
    настоящим `time.sleep` (WebDriverWait использует свой собственный
    `time`, не патченные фейковые часы этого модуля)."""

    def __init__(self, clock: _FakeClock, resolve_text,
                raise_find_element: Exception | None = None) -> None:
        self.clock = clock
        self.current_context = "NATIVE_APP"
        self.resolve_text = resolve_text
        self.send_time: float | None = None
        self.raise_find_element = raise_find_element
        self.find_element_calls = 0

    def find_element(self, by, value):
        del by, value
        self.find_element_calls += 1
        if self.find_element_calls > 1 and self.raise_find_element is not None:
            raise self.raise_find_element
        return _FakeRenameFieldElement(self)

    def current_field_text(self) -> str:
        if self.send_time is None:
            return "My saved search"  # предзаполнено текущим именем до send_keys
        return self.resolve_text(self.clock.time() - self.send_time)


@pytest.mark.p1
@allure.id("AT-BUG-062-enter-rename-name-mismatch-raises-diagnostic")
@allure.title("Проба: enter_rename_name падает диагностическим AssertionError, если поле не догнало имя за бюджет 1.5с (TC-085)")
def test_enter_rename_name_raises_assertion_with_diagnostic_on_mismatch(_fake_clock):
    # Given поле весь бюджет (1.5с) показывает ДРУГОЙ текст, чем введённый
    # (симулирует гонку ввода/неполный send_keys, AT-BUG-062 гипотеза 1)
    driver = _FakeRenameDriver(_fake_clock, resolve_text=lambda elapsed: "My renamed searc")
    screen = SettingsScreen(driver)

    # When/Then enter_rename_name падает диагностическим AssertionError, не
    # таймаутом/не сырым исключением Selenium
    with pytest.raises(AssertionError) as exc_info:
        screen.enter_rename_name("My renamed search")

    msg = str(exc_info.value)
    assert "AT-BUG-062" in msg, f"сообщение не несёт диагностическую ссылку: {msg!r}"
    assert "My renamed searc" in msg, f"фактический (неверный) текст поля не в сообщении: {msg!r}"
    assert "My renamed search" in msg, f"ожидаемое имя не в сообщении: {msg!r}"
    # Бюджет реально исчерпан (не короткое замыкание на первой же проверке) —
    # доказывает, что settle-поллинг отработал весь budget=1.5с
    assert _fake_clock.now >= 1.5, f"budget не исчерпан: fake clock={_fake_clock.now}"


@pytest.mark.p1
@allure.id("AT-BUG-062-enter-rename-name-catches-up-within-budget")
@allure.title("Проба: enter_rename_name зелёный, если поле догоняет имя в пределах бюджета 1.5с (TC-085)")
def test_enter_rename_name_succeeds_when_field_catches_up_within_budget(_fake_clock):
    # Given поле «догоняет» ожидаемое значение в пределах бюджета 1.5с
    # (интервал опроса 0.3с — совпадение ловится на 4-м опросе, t=0.9с)
    def resolve(elapsed: float) -> str:
        return "My renamed search" if elapsed >= 0.9 else "My renamed sear"

    driver = _FakeRenameDriver(_fake_clock, resolve_text=resolve)
    screen = SettingsScreen(driver)

    # When/Then исключение не поднимается, метод возвращает self (chaining)
    result = screen.enter_rename_name("My renamed search")

    assert result is screen
    assert _fake_clock.now < 1.5, (
        f"должен был поймать совпадение ДО исчерпания бюджета: fake clock={_fake_clock.now}"
    )


@pytest.mark.p1
@allure.id("AT-BUG-062-enter-rename-name-protects-stale-read")
@allure.title("Проба: enter_rename_name не протекает NoSuchElementException при stale-поле — только диагностический AssertionError (TC-085)")
def test_enter_rename_name_protects_diagnostic_read_against_stale_field(_fake_clock):
    # Given поле становится недоступным (NoSuchElementException) при КАЖДОМ
    # чтении после начального `self.find(...)` — симулирует stale/исчезнувший
    # узел (IMPLICIT_WAIT=0, framework/config/settings.py:50) в момент, когда
    # verification-поллинг/diagnostic-сообщение пытаются прочитать текст
    driver = _FakeRenameDriver(
        _fake_clock, resolve_text=lambda elapsed: "irrelevant",
        raise_find_element=NoSuchElementException("stale element reference"),
    )
    screen = SettingsScreen(driver)

    # When/Then наружу уходит диагностический AssertionError (защищённое
    # чтение поймало исключение и подставило placeholder), а НЕ сырой
    # NoSuchElementException — pytest.raises(AssertionError) сам провалит
    # тест, если наружу протечёт исключение другого типа
    with pytest.raises(AssertionError) as exc_info:
        screen.enter_rename_name("My renamed search")

    msg = str(exc_info.value)
    assert "AT-BUG-062" in msg
    assert "недоступно" in msg, f"ожидали placeholder защищённого чтения в сообщении: {msg!r}"


@pytest.mark.p1
@allure.id("AT-BUG-062-assert-filter-profile-listed-reports-db-names")
@allure.title("Проба: assert_filter_profile_listed на провале сообщает фактические имена профилей из БД (TC-085)")
def test_assert_filter_profile_listed_reports_actual_db_names_on_failure(monkeypatch, _fake_clock):
    # Given UI-поиск профиля не находит его (has_filter_profile -> False), а
    # БД реально содержит ДРУГИЕ имена (гипотеза 1: профиль сохранён под
    # другим именем) — мокаем оба источника без устройства
    monkeypatch.setattr(SettingsScreen, "has_filter_profile",
                        lambda self, name, timeout=None: False)
    monkeypatch.setattr(
        seed_db, "read_filter_profiles",
        lambda: [
            {"name": "My saved search", "queryString": "q1"},
            {"name": "Another profile", "queryString": "q2"},
        ],
    )
    driver = _FakeRenameDriver(_fake_clock, resolve_text=lambda elapsed: "")

    # When/Then провал несёт ФАКТИЧЕСКИЙ список имён из БД, не только факт
    # отсутствия искомого профиля в UI
    with pytest.raises(AssertionError) as exc_info:
        settings_steps.assert_filter_profile_listed(driver, "My renamed search")

    msg = str(exc_info.value)
    assert "My renamed search" in msg
    assert "My saved search" in msg, f"фактические имена БД не в сообщении: {msg!r}"
    assert "Another profile" in msg, f"фактические имена БД не в сообщении: {msg!r}"
