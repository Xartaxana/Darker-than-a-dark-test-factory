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
3. `enter_rename_name`: чтение поля ПОСЛЕ `send_keys` для diagnostic-сообщения
   ЗАЩИЩЕНО (инъекция сужена флагом `raise_only_after_send_keys` — иначе
   исключение срубает первое чтение pre-poll'а и проба зеленеет по совпадению
   текстов сообщений, критик-вход B4) —
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
5. (rework attempt 3, критик-вход B2) `enter_rename_name`: pre-poll ветка
   (СРАЗУ после `clear()`, ДО `send_keys`) — поле НЕ пустеет весь бюджет
   (`clear()` не сработал в фейке) -> `AssertionError` про содержимое
   ПОСЛЕ `clear()` (сообщение «после clear() содержит», не «после
   clear()+send_keys» — другая ветка, другое сообщение), `send_keys`
   не вызывается вовсе.
6. (rework attempt 3, критик-вход B2) `enter_rename_name`: поле пустеет НЕ
   сразу, а на N-м опросе pre-poll (catch-up ДО `send_keys`, в пределах
   бюджета) -> `send_keys` вызывается ТОЛЬКО когда поле реально уже пусто,
   тест зелёный.

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

    def clear(self) -> None:
        """Rework attempt 3 (rework3 B1 fix): `clear()` теперь МОДЕЛИРУЕТ реальную
        очистку — фиксирует момент вызова, а `current_field_text()` после него
        отдаёт `resolve_clear_text(elapsed)` (по умолчанию пусто СРАЗУ, elapsed=0),
        а не «предзаполненное имя» до самого `send_keys`. Раньше поле оставалось
        непустым ДО `send_keys` даже после `clear()` — недостижимое состояние для
        нового pre-poll (`_field_text() == ""` СРАЗУ после `clear()`), из-за чего
        pre-poll всегда исчерпывал бюджет и падал (критик B1, 2 failed из 4)."""
        self._driver.clear_time = self._driver.clock.time()
        self._driver.send_time = None

    def send_keys(self, value: str) -> None:
        del value
        self._driver.send_time = self._driver.clock.time()

    def get_attribute(self, name: str):
        return self._driver.current_field_text() if name == "text" else None


class _FakeRenameDriver:
    """Минимальный фейк Appium-драйвера для `SettingsScreen.enter_rename_name`.

    `resolve_text(elapsed)` — что реально показывает поле через `elapsed`
    фейковых секунд ПОСЛЕ `send_keys` (симулирует расхождение ввода/задержку
    recomposition при вводе). `resolve_clear_text(elapsed)` — симметрично, что
    показывает поле через `elapsed` секунд ПОСЛЕ `clear()`, ДО `send_keys`
    (симулирует задержку catch-up самого `clear()`/recomposition очистки);
    по умолчанию — пусто немедленно (`elapsed -> ""`), совпадает с прежним
    поведением фейка для всех проб, не передающих этот параметр явно.
    `raise_find_element`, если задан, заставляет ВТОРОЙ и последующие вызовы
    `find_element` кидать это исключение (симулирует поле, ставшее stale/
    исчезнувшее к моменту diagnostic-чтения) — ПЕРВЫЙ вызов (начальный
    `self.find(...)` внутри `enter_rename_name`) всегда успешен, иначе
    `wait_until` реально ждал бы `DEFAULT_TIMEOUT` секунд настоящим
    `time.sleep` (WebDriverWait использует свой собственный `time`, не
    патченные фейковые часы этого модуля).

    `raise_only_after_send_keys` (критик-вход B4, rework3 раунд 3) сужает окно
    инъекции: исключение начинает срабатывать ТОЛЬКО ПОСЛЕ `send_keys`. Без
    этого флага инъекция срубает уже ПЕРВОЕ чтение pre-poll'а (введён в
    attempt 3) — проба про пост-`send_keys` diagnostic-чтение падала бы в
    ДРУГОЙ (pre-poll) ветке и оставалась зелёной по СОВПАДЕНИЮ текстов
    сообщений, не исполняя ветку, ради которой заведена."""

    def __init__(self, clock: _FakeClock, resolve_text, resolve_clear_text=None,
                raise_find_element: Exception | None = None,
                raise_only_after_send_keys: bool = False) -> None:
        self.clock = clock
        self.current_context = "NATIVE_APP"
        self.resolve_text = resolve_text
        self.resolve_clear_text = resolve_clear_text or (lambda elapsed: "")
        self.clear_time: float | None = None
        self.send_time: float | None = None
        self.raise_find_element = raise_find_element
        self.raise_only_after_send_keys = raise_only_after_send_keys
        self.find_element_calls = 0

    def find_element(self, by, value):
        del by, value
        self.find_element_calls += 1
        if self.find_element_calls > 1 and self.raise_find_element is not None:
            if not self.raise_only_after_send_keys or self.send_time is not None:
                raise self.raise_find_element
        return _FakeRenameFieldElement(self)

    def current_field_text(self) -> str:
        if self.send_time is not None:
            return self.resolve_text(self.clock.time() - self.send_time)
        if self.clear_time is not None:
            return self.resolve_clear_text(self.clock.time() - self.clear_time)
        return "My saved search"  # предзаполнено текущим именем ДО clear()


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
    # Given поле становится недоступным (NoSuchElementException) при каждом
    # чтении ПОСЛЕ `send_keys` — симулирует stale/исчезнувший узел
    # (IMPLICIT_WAIT=0, framework/config/settings.py:50) ровно в тот момент,
    # ради которого проба заведена: пост-`send_keys` verification-поллинг и
    # diagnostic-сообщение пытаются прочитать текст.
    # Критик-вход B4 (rework3, раунд 3): БЕЗ `raise_only_after_send_keys`
    # инъекция срубала ПЕРВОЕ чтение pre-poll'а (введён в attempt 3), проба
    # падала в pre-poll ветке и оставалась зелёной по СОВПАДЕНИЮ (оба
    # сообщения несут «AT-BUG-062» и «недоступно»), не исполняя пост-
    # `send_keys` чтение вовсе. Явные ассерты ниже (`send_time is not None` +
    # текст именно пост-`send_keys` ветки) ловят такой регресс достижимости.
    driver = _FakeRenameDriver(
        _fake_clock, resolve_text=lambda elapsed: "irrelevant",
        raise_find_element=NoSuchElementException("stale element reference"),
        raise_only_after_send_keys=True,
    )
    screen = SettingsScreen(driver)

    # When/Then наружу уходит диагностический AssertionError (защищённое
    # чтение поймало исключение и подставило placeholder), а НЕ сырой
    # NoSuchElementException — pytest.raises(AssertionError) сам провалит
    # тест, если наружу протечёт исключение другого типа
    with pytest.raises(AssertionError) as exc_info:
        screen.enter_rename_name("My renamed search")

    msg = str(exc_info.value)
    # `is not None`, а НЕ truthiness: send_time может быть ровно 0.0
    assert driver.send_time is not None, (
        "ветка пост-`send_keys` чтения не достигнута — инъекция сработала "
        "раньше (pre-poll); проба не покрывает то, ради чего заведена"
    )
    assert "после clear()+send_keys" in msg, (
        f"ожидали сообщение пост-send_keys ветки, получили: {msg!r}"
    )
    assert "AT-BUG-062" in msg
    assert "недоступно" in msg, f"ожидали placeholder защищённого чтения в сообщении: {msg!r}"


@pytest.mark.p1
@allure.id("AT-BUG-062-enter-rename-name-pre-poll-never-clears-raises-diagnostic")
@allure.title("Проба: enter_rename_name падает диагностическим AssertionError про clear(), если поле не опустело за бюджет 1.5с (TC-085, rework attempt 3)")
def test_enter_rename_name_raises_diagnostic_when_field_never_clears(_fake_clock):
    # Given поле весь бюджет (1.5с) ПОСЛЕ clear() продолжает показывать старое
    # имя (симулирует clear(), который не применился — recomposition не
    # догнал ни разу в пределах pre-poll budget)
    driver = _FakeRenameDriver(
        _fake_clock, resolve_text=lambda elapsed: "irrelevant",
        resolve_clear_text=lambda elapsed: "My saved search",
    )
    screen = SettingsScreen(driver)

    # When/Then enter_rename_name падает ДО send_keys, с диагностикой именно
    # про clear() (не про clear()+send_keys — другая ветка/сообщение)
    with pytest.raises(AssertionError) as exc_info:
        screen.enter_rename_name("My renamed search")

    msg = str(exc_info.value)
    assert "AT-BUG-062" in msg, f"сообщение не несёт диагностическую ссылку: {msg!r}"
    assert "после clear() содержит" in msg, (
        f"ожидали сообщение pre-poll ветки («после clear() содержит»), "
        f"получили другое (возможно, сработала пост-send_keys ветка): {msg!r}"
    )
    assert "после clear()+send_keys" not in msg, (
        f"сработала пост-send_keys ветка вместо pre-poll: {msg!r}"
    )
    assert "My saved search" in msg, f"фактический (неочищенный) текст поля не в сообщении: {msg!r}"
    assert driver.send_time is None, "send_keys не должен вызываться — поле так и не очистилось"
    assert _fake_clock.now >= 1.5, f"pre-poll budget не исчерпан: fake clock={_fake_clock.now}"


@pytest.mark.p1
@allure.id("AT-BUG-062-enter-rename-name-pre-poll-catches-up-within-budget")
@allure.title("Проба: enter_rename_name вызывает send_keys только после реального опустошения поля (TC-085, rework attempt 3)")
def test_enter_rename_name_send_keys_waits_for_field_to_clear_within_budget(_fake_clock):
    # Given поле опустошается НЕ сразу, а на 4-м опросе pre-poll (интервал
    # 0.3с -> t=0.9с), в пределах бюджета 1.5с
    def resolve_clear(elapsed: float) -> str:
        return "" if elapsed >= 0.9 else "My saved search"

    driver = _FakeRenameDriver(
        _fake_clock, resolve_text=lambda elapsed: "My renamed search",
        resolve_clear_text=resolve_clear,
    )
    screen = SettingsScreen(driver)

    # When/Then send_keys вызывается ТОЛЬКО когда поле реально уже пусто
    # (не раньше t=0.9с), тест зелёный
    result = screen.enter_rename_name("My renamed search")

    assert result is screen
    assert driver.send_time is not None, "send_keys должен был быть вызван"
    assert driver.send_time >= 0.9, (
        f"send_keys вызван ДО того, как поле реально очистилось: send_time={driver.send_time}"
    )
    assert driver.clear_time is not None and driver.send_time - driver.clear_time >= 0.9, (
        "pre-poll должен был реально прождать catch-up ДО send_keys"
    )


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
