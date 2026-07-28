"""Device-free юнит-проба device-liveness guard (AT-BUG-026, контейнмент
вероятностного qemu-краха `0xc0000005` — см. `bugs/AT-BUG-026.md`, секция
«СПЕКА КОНТЕЙНМЕНТА»).

Доказывает, что `driver_factory.DeviceLivenessGuard` реализует ВСЕ ветки
спеки Lead без реального устройства/эмулятора (монки-патч
`adb.device_present`/`adb.is_installed`/`adb.install` и
`driver_factory._restart_emulator_writable_system` — тот же приём, что
остальные device-free пробы этого пакета, например
`test_replay_ca_check_unit.py`/`test_adb_install_package_wait_unit.py`):
  - устройство живо -> recovery не запускается вовсе;
  - устройство мертво -> recovery срабатывает (restart канонической формой +
    проверка установки приложения), возвращает WARN с номером попытки;
  - recovery не смог вернуть устройство в строй -> `DeviceRecoveryError`
    (сообщение начинается с `ENV_ISSUE`);
  - лимит `max_recoveries` исчерпан (на границе и ЗА ней) -> быстрый
    `DeviceRecoveryError` БЕЗ повторного restart (короткое замыкание — не
    каскад retry, класс M6: граница живёт, только если её нельзя обойти
    повторением одного и того же шага без счёта).

Переопределяет session-scoped autouse `_ensure_app_installed` (device-
фикстура conftest.py) — эта проба чисто локальная, устройство не трогает.
"""
from __future__ import annotations

import allure
import pytest

from framework.config import settings
from framework.core import adb, driver_factory


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля)."""
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретраи внутри `_verify_app_installed_with_retry` не должны ждать
    реальные секунды в юнит-пробе (тот же приём, что
    `test_adb_install_package_wait_unit.py::_no_real_sleep`) — считаем
    вызовы, но не спим."""
    calls: list = []
    monkeypatch.setattr(driver_factory.time, "sleep", lambda s: calls.append(s))
    return calls


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-device-alive-skips-recovery")
@allure.title("Проба: устройство присутствует -> guard не трогает recovery вовсе (device-free)")
def test_device_alive_skips_recovery(monkeypatch):
    monkeypatch.setattr(adb, "device_present", lambda: True)
    restart_calls: list = []
    monkeypatch.setattr(
        driver_factory, "_restart_emulator_writable_system",
        lambda *a, **kw: restart_calls.append(1),
    )
    install_calls: list = []
    monkeypatch.setattr(adb, "is_installed", lambda: install_calls.append("checked") or True)
    monkeypatch.setattr(adb, "install", lambda *a, **kw: install_calls.append("installed"))

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    # When/Then устройство живо -> None, ни restart, ни проверка установки не вызываются
    assert guard.ensure_ready() is None
    assert restart_calls == []
    assert install_calls == []
    assert guard.recovery_count == 0


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-recovery-succeeds")
@allure.title("Проба: устройство мертво -> recovery восстанавливает его, WARN несёт номер попытки/лимит (device-free)")
def test_device_dead_recovery_succeeds(monkeypatch):
    # Given: первая проверка — устройство отсутствует, ПОСЛЕ restart — снова присутствует
    presence = iter([False, True])
    monkeypatch.setattr(adb, "device_present", lambda: next(presence))
    restart_calls: list = []
    monkeypatch.setattr(
        driver_factory, "_restart_emulator_writable_system",
        lambda *a, **kw: restart_calls.append(1),
    )
    monkeypatch.setattr(adb, "is_installed", lambda: True)  # приложение пережило рестарт
    install_calls: list = []
    monkeypatch.setattr(adb, "install", lambda *a, **kw: install_calls.append(1))

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    # When
    warn = guard.ensure_ready()

    # Then: recovery выполнен РОВНО раз, приложение НЕ переустанавливалось
    # (is_installed() уже True), сообщение несёт номер попытки и лимит
    assert restart_calls == [1]
    assert install_calls == []
    assert guard.recovery_count == 1
    assert warn is not None
    assert "AT-BUG-026" in warn
    assert "1/2" in warn


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-recovery-reinstalls-app-when-missing")
@allure.title("Проба: recovery переустанавливает приложение, если оно не пережило рестарт (device-free)")
def test_recovery_reinstalls_app_when_missing(monkeypatch):
    presence = iter([False, True])
    monkeypatch.setattr(adb, "device_present", lambda: next(presence))
    monkeypatch.setattr(driver_factory, "_restart_emulator_writable_system", lambda *a, **kw: None)
    monkeypatch.setattr(adb, "is_installed", lambda: False)
    install_calls: list = []
    monkeypatch.setattr(adb, "install", lambda *a, **kw: install_calls.append(1))

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    warn = guard.ensure_ready()

    # Then: приложение отсутствовало после restart -> install() вызван ровно раз
    assert install_calls == [1]
    assert warn is not None


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-recovery-fails-raises-env-issue")
@allure.title("Проба: recovery не вернул устройство в строй -> DeviceRecoveryError (ENV_ISSUE), не молчаливая маскировка (device-free)")
def test_recovery_fails_raises_device_recovery_error(monkeypatch):
    # Given: устройство отсутствует И ДО, И ПОСЛЕ restart — recovery не удался
    monkeypatch.setattr(adb, "device_present", lambda: False)
    monkeypatch.setattr(driver_factory, "_restart_emulator_writable_system", lambda *a, **kw: None)
    monkeypatch.setattr(adb, "is_installed", lambda: True)
    monkeypatch.setattr(adb, "install", lambda *a, **kw: None)

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    with pytest.raises(driver_factory.DeviceRecoveryError) as exc_info:
        guard.ensure_ready()

    message = str(exc_info.value)
    assert message.startswith("ENV_ISSUE")
    assert "AT-BUG-026" in message
    # Попытка израсходовала лимит, даже если она провалилась (идемпотентность/класс M6)
    assert guard.recovery_count == 1


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-install-retry-succeeds-after-transient-race")
@allure.title("Проба: транзиентная гонка storage/vold на install() — bounded retry проходит, recovery не валится (device-free)")
def test_install_retry_succeeds_after_transient_race(monkeypatch, _no_real_sleep):
    """Красная проба w1 (2026-07-28, живое устройство) поймала реальный
    `RuntimeError` от `adb.install()` (StorageManager NPE) сразу после
    Start-Emulator — `_verify_app_installed_with_retry` обязан пережить N-1
    транзиентных отказов и пройти на последней попытке."""
    presence = iter([False, True])
    monkeypatch.setattr(adb, "device_present", lambda: next(presence))
    monkeypatch.setattr(driver_factory, "_restart_emulator_writable_system", lambda *a, **kw: None)
    monkeypatch.setattr(adb, "is_installed", lambda: False)
    install_calls: list = []

    def _flaky_install(*a, **kw):
        install_calls.append(1)
        if len(install_calls) < driver_factory._APP_VERIFY_RETRIES:
            raise RuntimeError("APK install failed: NullPointerException StorageManager")

    monkeypatch.setattr(adb, "install", _flaky_install)

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    warn = guard.ensure_ready()

    # Then: install() был вызван РОВНО _APP_VERIFY_RETRIES раз (последняя попытка
    # прошла), sleep был вызван между попытками (backoff), recovery не упал
    assert len(install_calls) == driver_factory._APP_VERIFY_RETRIES
    assert len(_no_real_sleep) == driver_factory._APP_VERIFY_RETRIES - 1
    assert warn is not None


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-install-retry-exhausted-raises-env-issue")
@allure.title("Проба: install() падает ВСЕ попытки -> чистый DeviceRecoveryError (ENV_ISSUE), не голый RuntimeError адб (device-free)")
def test_install_retry_exhausted_raises_clean_env_issue(monkeypatch, _no_real_sleep):
    # F6 (критик-вход attempt 3): device_present() теперь проверяется СРАЗУ
    # после restart, ДО install-retry (см. driver_factory.ensure_ready) — эта
    # проба целится именно во ВТОРОЙ отказ (install навсегда сломан НА живом
    # устройстве), поэтому мок обязан отдать True на пост-restart проверке,
    # иначе guard короткозамкнётся раньше, не дойдя до install-retry вовсе
    # (тот класс уже покрыт test_recovery_fails_raises_device_recovery_error).
    presence = iter([False, True])
    monkeypatch.setattr(adb, "device_present", lambda: next(presence))
    monkeypatch.setattr(driver_factory, "_restart_emulator_writable_system", lambda *a, **kw: None)
    monkeypatch.setattr(adb, "is_installed", lambda: False)
    install_calls: list = []

    def _always_broken_install(*a, **kw):
        install_calls.append(1)
        raise RuntimeError("APK install failed: NullPointerException StorageManager")

    monkeypatch.setattr(adb, "install", _always_broken_install)

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    with pytest.raises(driver_factory.DeviceRecoveryError) as exc_info:
        guard.ensure_ready()

    message = str(exc_info.value)
    assert message.startswith("ENV_ISSUE")
    assert len(install_calls) == driver_factory._APP_VERIFY_RETRIES
    # Попытка ВСЁ РАВНО израсходовала лимит recovery (идемпотентность/класс M6)
    assert guard.recovery_count == 1


@pytest.mark.p1
@allure.id("AT-BUG-026-guard-limit-boundary-and-beyond")
@allure.title("Проба: граница MAX_RECOVERIES_PER_SESSION (2) восстанавливает, ЗА границей (3-й) — быстрый стоп БЕЗ повторного restart (device-free)")
def test_limit_boundary_and_beyond(monkeypatch):
    """Адверсариальный тест НА границе лимита И за ней (правило 11 CLAUDE.md,
    класс M6): recovery 1/2 и 2/2 обязаны пройти (лимит ещё не превышен),
    3-я попытка (за лимитом) обязана остановиться БЕЗ нового restart —
    unit-эквивалент device-уровня w2 DoD этого бага."""
    restart_calls: list = []
    presence_state = {"device_up": False}

    def _fake_device_present() -> bool:
        return presence_state["device_up"]

    def _fake_restart(*a, **kw) -> None:
        restart_calls.append(1)
        presence_state["device_up"] = True

    monkeypatch.setattr(adb, "device_present", _fake_device_present)
    monkeypatch.setattr(driver_factory, "_restart_emulator_writable_system", _fake_restart)
    monkeypatch.setattr(adb, "is_installed", lambda: True)
    monkeypatch.setattr(adb, "install", lambda *a, **kw: None)

    guard = driver_factory.DeviceLivenessGuard(max_recoveries=2)

    # When: 1-е восстановление (recovery 1/2) — устройство было мертво, ensure_ready
    # его подняло
    presence_state["device_up"] = False
    warn1 = guard.ensure_ready()
    assert warn1 is not None
    assert "1/2" in warn1
    assert guard.recovery_count == 1
    assert restart_calls == [1]

    # And: устройство снова умирает — 2-е восстановление РОВНО НА ГРАНИЦЕ лимита (2/2)
    presence_state["device_up"] = False
    warn2 = guard.ensure_ready()
    assert warn2 is not None
    assert "2/2" in warn2
    assert guard.recovery_count == 2
    assert len(restart_calls) == 2

    # Then: устройство умирает В ТРЕТИЙ раз — лимит уже исчерпан (2/2), ЗА границей:
    # guard обязан остановиться БЫСТРО, БЕЗ третьего restart (не каскад retry)
    presence_state["device_up"] = False
    with pytest.raises(driver_factory.DeviceRecoveryError) as exc_info:
        guard.ensure_ready()

    message = str(exc_info.value)
    assert message.startswith("ENV_ISSUE")
    assert len(restart_calls) == 2  # третьего restart НЕ было — короткое замыкание
    assert guard.recovery_count == 2  # счётчик не растёт дальше лимита


# --- B1-доработка (критик-вход attempt 3): guard недостижим, если он живёт
# ТОЛЬКО в setup фикстуры `driver` — фикс переносит вызов в
# `pytest_runtest_setup(item)` (conftest.py), который срабатывает ДО setup
# ЛЮБОЙ фикстуры теста, независимо от порядка аргументов в сигнатуре. Пробы
# ниже импортируют РЕАЛЬНЫЙ модуль `framework.tests.conftest` (тот же объект,
# что pytest уже загрузил как conftest-плагин текущей сессии — sys.modules
# кеширует по полному имени) и монки-патчат его `_DEVICE_GUARD`/
# `_reset_ca_check`, вызывая хук НАПРЯМУЮ с фейковым `item` (duck-typing —
# хуку нужен только атрибут `.fixturenames`), без реального вложенного
# pytest-прогона."""

import framework.tests.conftest as _conftest_mod  # noqa: E402 — device-free, тот же модуль


class _FakeItem:
    def __init__(self, fixturenames: list[str]) -> None:
        self.fixturenames = fixturenames


@pytest.mark.p1
@allure.id("AT-BUG-026-hook-skips-tests-without-driver-fixture")
@allure.title("Проба B1: pytest_runtest_setup НЕ трогает guard, если 'driver' не запрошен тестом (device-free)")
def test_hook_skips_tests_without_driver_fixture(monkeypatch):
    ensure_calls: list = []
    monkeypatch.setattr(
        _conftest_mod._DEVICE_GUARD, "ensure_ready",
        lambda: ensure_calls.append(1) or None,
    )

    _conftest_mod.pytest_runtest_setup(_FakeItem(["tmp_path", "monkeypatch"]))

    assert ensure_calls == []


@pytest.mark.p1
@allure.id("AT-BUG-026-hook-fires-for-device-tests-regardless-of-fixture-order")
@allure.title("Проба B1: pytest_runtest_setup вызывает guard.ensure_ready(), если 'driver' в fixturenames — независимо от позиции replay/clean_app в списке (device-free)")
def test_hook_calls_guard_when_driver_in_fixturenames(monkeypatch):
    monkeypatch.setattr(_conftest_mod, "_pending_recovery_warning", None)
    ensure_calls: list = []
    recovered_msg = "AT-BUG-026 device-liveness guard: устройство восстановлено 1/2"
    monkeypatch.setattr(
        _conftest_mod._DEVICE_GUARD, "ensure_ready",
        lambda: ensure_calls.append(1) or recovered_msg,
    )
    reset_calls: list = []
    monkeypatch.setattr(_conftest_mod, "_reset_ca_check", lambda: reset_calls.append(1))

    # Сигнатура реального теста-крашера — test_x(clean_app, replay, driver):
    # `driver` перечислен ПОСЛЕДНИМ, но fixturenames — полное множество,
    # порядок не влияет на признак "тест трогает устройство".
    _conftest_mod.pytest_runtest_setup(_FakeItem(["clean_app", "replay", "driver"]))

    assert ensure_calls == [1]
    assert _conftest_mod._pending_recovery_warning == recovered_msg
    # F4: recovery произошёл в этом вызове -> кеш CA обязан сброситься
    assert reset_calls == [1]


@pytest.mark.p1
@allure.id("AT-BUG-026-hook-no-ca-reset-without-recovery")
@allure.title("Проба B1/F4: recovery НЕ произошёл (устройство было живо) -> _reset_ca_check НЕ вызывается (device-free)")
def test_hook_skips_ca_reset_when_no_recovery_happened(monkeypatch):
    monkeypatch.setattr(_conftest_mod._DEVICE_GUARD, "ensure_ready", lambda: None)
    reset_calls: list = []
    monkeypatch.setattr(_conftest_mod, "_reset_ca_check", lambda: reset_calls.append(1))

    _conftest_mod.pytest_runtest_setup(_FakeItem(["driver"]))

    assert _conftest_mod._pending_recovery_warning is None
    assert reset_calls == []


@pytest.mark.p1
@allure.id("AT-BUG-026-ca-check-reset-clears-cache")
@allure.title("Проба F4: _reset_ca_check() сбрасывает module-level кеш _ca_checked (device-free)")
def test_reset_ca_check_clears_cache(monkeypatch):
    monkeypatch.setattr(_conftest_mod, "_ca_checked", True)

    _conftest_mod._reset_ca_check()

    assert _conftest_mod._ca_checked is False


@pytest.mark.p1
@allure.id("AT-BUG-026-create-driver-quits-partial-session-before-settle-retry")
@allure.title("Проба F7: create_driver закрывает частично созданную Appium-сессию перед settle-ретраем, не оставляя утечку (device-free)")
def test_create_driver_quits_partial_session_before_retry(monkeypatch):
    """`webdriver.Remote(...)` УСПЕВАЕТ создать сессию, но следующий шаг
    (`implicitly_wait`) падает — до F7 частично созданный `driver` не
    закрывался перед повторной попыткой (утечка на Appium-сервере)."""
    quit_calls: list = []
    monkeypatch.setattr(driver_factory, "quit_driver", lambda drv: quit_calls.append(drv))
    monkeypatch.setattr(
        driver_factory.capabilities, "build_options", lambda no_reset: object()
    )

    class _FakeDriverPartial:
        """Симулирует webdriver.Remote(...), который создаётся успешно, но
        падает на implicitly_wait — ровно тот F7-сценарий."""

        def implicitly_wait(self, *_a, **_kw):
            raise RuntimeError("simulated implicitly_wait failure")

    class _FakeDriverOk:
        def implicitly_wait(self, *_a, **_kw):
            return None

    created: list = []

    def _fake_remote(*_a, **_kw):
        if not created:
            drv = _FakeDriverPartial()
        else:
            drv = _FakeDriverOk()
        created.append(drv)
        return drv

    monkeypatch.setattr(driver_factory.webdriver, "Remote", _fake_remote)
    monkeypatch.setattr(driver_factory.time, "sleep", lambda *_a, **_kw: None)

    result = driver_factory.create_driver(no_reset=True, settle_retries=1)

    # Then: вторая (settle-ретрай) попытка вернула вторую фейковую сессию,
    # и ПЕРВАЯ (частично созданная, упавшая на implicitly_wait) была закрыта
    # через quit_driver ПЕРЕД повтором — не осталась висеть на Appium
    assert result is created[1]
    assert quit_calls == [created[0]]


# --- N2 (критик-вход attempt 4): PROXY_DEVICE_REACHABLE_TIMEOUT_AFTER_RECOVERY
# введена без единого теста — `_proxy_reachable_timeout()` (conftest.py,
# извлечена из тела фикстуры `replay` РОВНО для этой пробы, см. её
# докстринг) покрывает обе ветки выбора таймаута без реального устройства/
# генератора-фикстуры (pytest 9 запрещает вызывать декорированную
# fixture-функцию напрямую).


@pytest.mark.p1
@allure.id("AT-BUG-026-proxy-timeout-after-recovery-when-pending")
@allure.title(
    "Проба N2: recovery произошёл в этом тесте -> "
    "_proxy_reachable_timeout() возвращает PROXY_DEVICE_REACHABLE_TIMEOUT_AFTER_RECOVERY (device-free)"
)
def test_proxy_reachable_timeout_after_recovery_when_pending(monkeypatch):
    monkeypatch.setattr(
        _conftest_mod, "_pending_recovery_warning",
        "AT-BUG-026 device-liveness guard: устройство восстановлено 1/2",
    )

    assert (
        _conftest_mod._proxy_reachable_timeout()
        == settings.PROXY_DEVICE_REACHABLE_TIMEOUT_AFTER_RECOVERY
    )


@pytest.mark.p1
@allure.id("AT-BUG-026-proxy-timeout-default-when-no-recovery")
@allure.title(
    "Проба N2: recovery НЕ произошёл -> _proxy_reachable_timeout() возвращает "
    "None (дефолт mitm.wait_device_proxy_reachable не меняется, device-free)"
)
def test_proxy_reachable_timeout_default_when_no_recovery(monkeypatch):
    monkeypatch.setattr(_conftest_mod, "_pending_recovery_warning", None)

    assert _conftest_mod._proxy_reachable_timeout() is None
