"""p3-n4-udid-pin-binding-guard (критик-эскалация TC-149, вердикт подтверждён
решающим замером Lead M2): Appium-сессия при двух живых устройствах
биндилась на `devices[0]` вместо адресованного, потому что caps не несли
`appium:udid` — `appium-android-driver` выбирает устройство только по
udid/avd/platformVersion ("grab the first device we see" при их отсутствии).
Замер M2 (env стека 2: AO3_DEVICE=emulator-5556, APPIUM_URL=:4725) дал
bound deviceUDID=emulator-5554, platformVersion=14 — сессия ушла НЕ туда.

Два независимых слоя фикса, каждый со своей пробой ниже:
  1. `capabilities.py::build_options` теперь ВСЕГДА выставляет
     `appium:udid` == `settings.DEVICE_NAME` (устройство привязывается
     до попытки создать сессию).
  2. `driver_factory.py::create_driver` — fail-fast гвардия СРАЗУ после
     `webdriver.Remote(...)`, сверяющая `driver.capabilities["deviceUDID"]`
     с адресованным `settings.DEVICE_NAME`: расхождение — `quit_driver` +
     `DeviceBindingMismatchError` (маркер `DEVICE_BINDING_MISMATCH`);
     пустой/отсутствующий `deviceUDID` — НЕ падение (WARN, не все бэкенды
     его отдают); совпадение — сессия не тронута.

Device-free: `webdriver.Remote`/`build_options` монки-патчатся тем же
приёмом, что `test_device_liveness_guard_unit.py::
test_create_driver_quits_partial_session_before_retry` (F7 проба, тот же
модуль)."""
from __future__ import annotations

import allure
import pytest

from framework.config import capabilities, settings
from framework.core import driver_factory


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогает (тот же приём, что
    test_device_liveness_guard_unit.py/test_device_lease_checkpoint_unit.py)."""
    yield


@pytest.fixture(autouse=True)
def _no_lease_checkpoint(monkeypatch):
    """Чокпоинт лизы (N3) не имеет отношения к M2-фиксу — обнуляем его, чтобы
    пробы не зависели от того, распознаётся ли device-free settings.APPIUM_URL
    как известный стек на хосте прогона."""
    monkeypatch.setattr(driver_factory, "check_device_lease", lambda: None)


class _FakeDriver:
    def __init__(self, caps: dict):
        self.capabilities = caps
        self.implicitly_wait_calls: list = []
        self.quit_calls = 0

    def implicitly_wait(self, *_a, **_kw):
        self.implicitly_wait_calls.append(1)

    def quit(self):
        self.quit_calls += 1


# --- (а) build_options содержит appium:udid == DEVICE_NAME ---


@pytest.mark.p1
@allure.id("P3-N4-build-options-sets-udid-equal-device-name")
@allure.title("build_options: appium:udid == settings.DEVICE_NAME (device-free)")
def test_build_options_sets_udid_equal_to_device_name(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5556", raising=False)
    opts = capabilities.build_options()
    assert opts.get_capability("appium:udid") == "emulator-5556"
    # deviceName остаётся (спека п.1: "существующий deviceName оставить")
    assert opts.get_capability("appium:deviceName") == "emulator-5556"


@pytest.mark.p2
@allure.id("P3-N4-build-options-udid-tracks-other-device-name")
@allure.title("build_options: appium:udid следует за ЛЮБЫМ settings.DEVICE_NAME, не только дефолтным (device-free)")
def test_build_options_udid_tracks_other_device_name(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5554", raising=False)
    opts = capabilities.build_options()
    assert opts.get_capability("appium:udid") == "emulator-5554"


# --- (б) create_driver-гвардия: mismatch -> RuntimeError и quit вызван ---


@pytest.mark.p1
@allure.id("P3-N4-create-driver-guard-mismatch-raises-and-quits")
@allure.title("create_driver: deviceUDID != DEVICE_NAME -> DeviceBindingMismatchError, сессия закрыта (device-free)")
def test_create_driver_guard_mismatch_raises_and_quits(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5556", raising=False)
    monkeypatch.setattr(capabilities, "build_options", lambda no_reset: object())

    fake = _FakeDriver({"deviceUDID": "emulator-5554", "platformVersion": "14"})
    monkeypatch.setattr(driver_factory.webdriver, "Remote", lambda *a, **kw: fake)

    with pytest.raises(driver_factory.DeviceBindingMismatchError) as exc_info:
        driver_factory.create_driver(no_reset=True, settle_retries=0)

    message = str(exc_info.value)
    assert message.startswith("DEVICE_BINDING_MISMATCH")
    assert "emulator-5554" in message
    assert "emulator-5556" in message
    assert fake.quit_calls >= 1
    # Гвардия срабатывает ДО implicitly_wait (спека: "сразу после webdriver.Remote")
    assert fake.implicitly_wait_calls == []


@pytest.mark.p1
@allure.id("P3-N4-create-driver-guard-mismatch-is-runtime-error")
@allure.title("DeviceBindingMismatchError — подкласс RuntimeError (спека п.2, greppable маркер) (device-free)")
def test_device_binding_mismatch_error_is_runtime_error():
    assert issubclass(driver_factory.DeviceBindingMismatchError, RuntimeError)


# --- (в) совпадение -> сессия не тронута ---


@pytest.mark.p1
@allure.id("P3-N4-create-driver-guard-match-session-untouched")
@allure.title("create_driver: deviceUDID == DEVICE_NAME -> сессия возвращается, quit НЕ вызван (device-free)")
def test_create_driver_guard_match_session_untouched(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5556", raising=False)
    monkeypatch.setattr(capabilities, "build_options", lambda no_reset: object())

    fake = _FakeDriver({"deviceUDID": "emulator-5556", "platformVersion": "10"})
    monkeypatch.setattr(driver_factory.webdriver, "Remote", lambda *a, **kw: fake)

    result = driver_factory.create_driver(no_reset=True, settle_retries=0)

    assert result is fake
    assert fake.quit_calls == 0
    assert fake.implicitly_wait_calls == [1]


# --- (г) deviceUDID отсутствует -> WARN-путь, не падение ---


@pytest.mark.p1
@allure.id("P3-N4-create-driver-guard-missing-udid-warns-not-fails")
@allure.title("create_driver: deviceUDID отсутствует в capabilities ответа -> WARN, сессия возвращается (device-free)")
def test_create_driver_guard_missing_udid_warns_not_fails(monkeypatch, capsys):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5556", raising=False)
    monkeypatch.setattr(capabilities, "build_options", lambda no_reset: object())

    fake = _FakeDriver({"platformVersion": "10"})  # НЕТ deviceUDID вовсе
    monkeypatch.setattr(driver_factory.webdriver, "Remote", lambda *a, **kw: fake)

    result = driver_factory.create_driver(no_reset=True, settle_retries=0)

    assert result is fake
    assert fake.quit_calls == 0
    captured = capsys.readouterr()
    assert "deviceUDID" in captured.err  # WARN-диагностика ушла в stderr


@pytest.mark.p2
@allure.id("P3-N4-create-driver-guard-empty-string-udid-warns-not-fails")
@allure.title("create_driver: deviceUDID == '' (пустая строка) трактуется как отсутствующий -> WARN, не падение (device-free)")
def test_create_driver_guard_empty_string_udid_warns_not_fails(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_NAME", "emulator-5556", raising=False)
    monkeypatch.setattr(capabilities, "build_options", lambda no_reset: object())

    fake = _FakeDriver({"deviceUDID": "", "platformVersion": "10"})
    monkeypatch.setattr(driver_factory.webdriver, "Remote", lambda *a, **kw: fake)

    result = driver_factory.create_driver(no_reset=True, settle_retries=0)

    assert result is fake
    assert fake.quit_calls == 0
