"""Device-free юнит-проба device-liveness guard (AT-BUG-026, контейнмент
вероятностного qemu-краха `0xc0000005` — см. `bugs/AT-BUG-026.md`, секция
«СПЕКА КОНТЕЙНМЕНТА»).

AT-BUG-063 rework attempt 2 добавила `import json`/`import subprocess`
модулю ниже (см. хвост файла) — `json` для сборки/чтения фейкового
state-файла в пробах, `subprocess` ТОЛЬКО для одной real-PowerShell пробы
(`test_tasks_ps1_set_emulator_session_state_writes_resolved_params`), не
для монки-патча `driver_factory.subprocess` (тот остаётся `driver_factory.subprocess`,
как в остальном файле).

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

import json
import subprocess as _real_subprocess

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


# --- AT-BUG-063 (test_debt, B4, rework attempt 2 — критик-вход отклонил
# attempt 1). Attempt 1 читал ТОЛЬКО `AO3_EMU_GPU` из окружения python-
# процесса и интерполировал сырое значение в строку `-Command` — критик
# показал ЭМПИРИЧЕСКИ, что (а) это поведенчески идентично коду ДО фикса для
# ЛЮБОГО значения `AO3_EMU_GPU` (`tasks.ps1` и так фолбэчится на неё, и
# `subprocess.run` без `env=` и так наследует окружение), и (б) реальный
# воспроизведённый сценарий (RUN-20260811-0405: `-Gpu host` явным CLI-
# параметром НАЧАЛЬНОМУ `Start-Emulator`, БЕЗ переменной окружения на
# сессию) не закрывался вовсе; плюс injection-риск (F3) в самой строковой
# интерполяции и потерю `-AvdName` (F4, TC-109/AT-BUG-028: recovery мог
# молча поднять ЧУЖОЙ AVD).
#
# Этот блок пробует НОВЫЙ механизм: `state/emulator-session.json`, которое
# `tasks.ps1::Start-Emulator` пишет СРАЗУ после разрешения `-Gpu`/`-AvdName`
# (параметр > env > дефолт) — recovery читает уже РАЗРЕШЁННОЕ значение,
# видит и явный CLI-флаг, и env-переменную, и дефолт одинаково. Значения
# передаются в recovery-подпроцесс ЧЕРЕЗ `env=` (`AO3_RECOVERY_GPU`/
# `AO3_RECOVERY_AVD_NAME`), НЕ строковой интерполяцией — сама `-Command`
# строка ФИКСИРОВАННЫЙ литерал, проверяемый ниже как инвариант (структурное
# доказательство отсутствия инъекции, не просто "не упало").


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


# Фиксированный литерал `-Command`, который `_restart_emulator_writable_system`
# ОБЯЗАНА собирать НЕЗАВИСИМО от значений gpu/avd_name (см. докстринг функции) —
# используется как структурный инвариант в пробах F3 ниже: если бы значение
# интерполировалось в текст, этот литерал менялся бы вместе с ним.
_EXPECTED_PS_COMMAND_SUFFIX = (
    "$seArgs = @{ WritableSystem = $true }; "
    "if ($env:AO3_RECOVERY_GPU) { $seArgs.Gpu = $env:AO3_RECOVERY_GPU }; "
    "if ($env:AO3_RECOVERY_AVD_NAME) { $seArgs.AvdName = $env:AO3_RECOVERY_AVD_NAME }; "
    "Start-Emulator @seArgs"
)


@pytest.fixture
def isolated_state_file(monkeypatch, tmp_path):
    """Отвязывает `_EMULATOR_SESSION_STATE_FILE` от реального `state/`
    репозитория — тесты не должны зависеть от того, поднимал ли кто-то
    реальный эмулятор на этой машине (и не должны его состояние трогать).
    Возвращает путь; по умолчанию файл НЕ существует (штатный "state-файла
    ещё нет" случай)."""
    path = tmp_path / "emulator-session.json"
    monkeypatch.setattr(driver_factory, "_EMULATOR_SESSION_STATE_FILE", path)
    return path


def _capture_run(monkeypatch):
    calls: list = []

    def _fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "env": kwargs.get("env") or {}})
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(driver_factory.subprocess, "run", _fake_run)
    return calls


# --- Backward-compat фолбэк на AO3_EMU_GPU (без state-файла) ---


@pytest.mark.p1
@allure.id("AT-BUG-063-recovery-env-fallback-gpu-when-no-state-file")
@allure.title(
    "Проба AT-BUG-063: нет state-файла, AO3_EMU_GPU=host в окружении -> "
    "recovery пробрасывает 'host' через env дочернего процесса (backward-compat, device-free)"
)
def test_recovery_env_fallback_gpu_when_no_state_file(monkeypatch, isolated_state_file):
    assert not isolated_state_file.exists()  # штатный случай: файла ещё нет
    monkeypatch.setenv("AO3_EMU_GPU", "host")
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    assert len(calls) == 1
    assert calls[0]["env"].get("AO3_RECOVERY_GPU") == "host"
    assert "AO3_RECOVERY_AVD_NAME" not in calls[0]["env"]
    ps_command = calls[0]["cmd"][-1]
    assert ps_command.endswith(_EXPECTED_PS_COMMAND_SUFFIX)
    # F3 структурный инвариант: сырое значение НЕ появляется в тексте команды
    assert "host" not in ps_command


@pytest.mark.p1
@allure.id("AT-BUG-063-recovery-no-gpu-when-state-and-env-absent")
@allure.title(
    "Проба AT-BUG-063: ни state-файла, ни AO3_EMU_GPU -> recovery не передаёт "
    "AO3_RECOVERY_GPU вовсе (tasks.ps1 применит собственный дефолт, device-free)"
)
def test_recovery_no_gpu_when_state_and_env_absent(monkeypatch, isolated_state_file):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    assert len(calls) == 1
    assert "AO3_RECOVERY_GPU" not in calls[0]["env"]
    assert "AO3_RECOVERY_AVD_NAME" not in calls[0]["env"]
    ps_command = calls[0]["cmd"][-1]
    assert ps_command.endswith(_EXPECTED_PS_COMMAND_SUFFIX)


# --- F1/F4: сценарий RUN-20260811-0405 (CLI-параметр мимо env), через state-файл ---


@pytest.mark.p1
@allure.id("AT-BUG-063-recovery-reads-gpu-and-avdname-from-state-file")
@allure.title(
    "Проба AT-BUG-063 (F1+F4): state-файл несёт gpu=host, avd_name=ao3_test_api29 "
    "БЕЗ AO3_EMU_GPU в окружении -> recovery пробрасывает ОБА (device-free)"
)
def test_recovery_reads_gpu_and_avdname_from_state_file(monkeypatch, isolated_state_file):
    # Given: РОВНО критик-сценарий -- Start-Emulator был поднят явным CLI-
    # параметром (что и записало state-файл), переменная окружения сессии
    # НЕ выставлена вовсе.
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    isolated_state_file.write_text(
        json.dumps({"gpu": "host", "avd_name": "ao3_test_api29"}), encoding="utf-8"
    )
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    assert len(calls) == 1
    assert calls[0]["env"].get("AO3_RECOVERY_GPU") == "host"
    assert calls[0]["env"].get("AO3_RECOVERY_AVD_NAME") == "ao3_test_api29"
    ps_command = calls[0]["cmd"][-1]
    assert ps_command.endswith(_EXPECTED_PS_COMMAND_SUFFIX)
    assert "host" not in ps_command
    assert "ao3_test_api29" not in ps_command


@pytest.mark.p1
@allure.id("AT-BUG-063-red-probe-cli-param-without-env-scenario")
@allure.title(
    "Red probe AT-BUG-063: без state-механизма (мир attempt 1) CLI-параметр -Gpu host "
    "мимо AO3_EMU_GPU ТЕРЯЕТСЯ; с ним (этот фикс) -- пробрасывается (device-free)"
)
def test_red_probe_cli_param_without_env_scenario(monkeypatch, isolated_state_file):
    """Изолирует причинный фактор (state-файл) монки-патчем
    `_read_emulator_session_state`, а не файловой порчей — исключающий
    прогон в духе калибровки CLAUDE.md п.6 (каузальное заявление доказано
    ИМЕННО контрастом "механизм выключен" vs "механизм включён", тот же
    сценарий, тот же env)."""
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)  # критик-сценарий: нет env на сессию

    # --- Мир attempt 1: механизма state-файла как будто нет вовсе ---
    monkeypatch.setattr(driver_factory, "_read_emulator_session_state", lambda: {})
    calls_before = _capture_run(monkeypatch)
    driver_factory._restart_emulator_writable_system()
    assert "AO3_RECOVERY_GPU" not in calls_before[0]["env"]  # БАГ воспроизведён: host потерян

    # --- Этот фикс: state-файл реально нёс -Gpu host (CLI-параметр) ---
    monkeypatch.setattr(driver_factory, "_read_emulator_session_state", lambda: {"gpu": "host"})
    calls_after = _capture_run(monkeypatch)
    driver_factory._restart_emulator_writable_system()
    assert calls_after[0]["env"].get("AO3_RECOVERY_GPU") == "host"  # ФИКС: host пробрасывается


# --- F3: адверсариальная батарея (правило 11 CLAUDE.md) — значение из
# state-файла с пробелом/`;`/кавычкой/пустое/валидное — каждое даёт
# ПРЕДСКАЗУЕМЫЙ результат (дропнуто санитизацией ИЛИ передано как есть),
# НИКОГДА не меняет текст `-Command` (структурный инвариант, доказывающий
# отсутствие инъекции на уровне механизма передачи, не только "не упало").


@pytest.mark.parametrize(
    "raw_gpu,should_pass",
    [
        pytest.param("host swiftshader_indirect", False, id="space-breaks-binding"),
        pytest.param("host; Remove-Item C:\\evil -Recurse -Force", False, id="semicolon-injection"),
        pytest.param('host" ; taskkill /F /IM explorer.exe #', False, id="quote-injection"),
        pytest.param("", False, id="empty"),
        pytest.param("not_a_real_backend", False, id="unknown-value"),
        pytest.param("host", True, id="valid-host"),
        pytest.param("angle_indirect", True, id="valid-angle_indirect"),
        pytest.param("swiftshader_indirect", True, id="valid-swiftshader_indirect"),
    ],
)
@pytest.mark.p1
@allure.id("AT-BUG-063-f3-gpu-adversarial-battery")
@allure.title("Проба F3 (адверсариальная батарея): GPU-значение из state-файла -> предсказуемый исход, команда не меняется")
def test_f3_gpu_adversarial_battery(monkeypatch, isolated_state_file, raw_gpu, should_pass):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    isolated_state_file.write_text(json.dumps({"gpu": raw_gpu}), encoding="utf-8")
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()  # НЕ должно бросить/упасть парсером

    assert len(calls) == 1
    ps_command = calls[0]["cmd"][-1]
    assert ps_command.endswith(_EXPECTED_PS_COMMAND_SUFFIX)  # команда НЕИЗМЕННА для любого значения
    if should_pass:
        assert calls[0]["env"].get("AO3_RECOVERY_GPU") == raw_gpu
    else:
        assert "AO3_RECOVERY_GPU" not in calls[0]["env"]


@pytest.mark.parametrize(
    "raw_avd,should_pass",
    [
        pytest.param("ao3_test_api29 -no-boot-anim", False, id="space-breaks-binding"),
        pytest.param("ao3_test_api29; Remove-Item C:\\evil", False, id="semicolon-injection"),
        pytest.param('ao3_test_api29" ; whoami #', False, id="quote-injection"),
        pytest.param("", False, id="empty"),
        pytest.param("ao3_test_api29", True, id="valid-second-avd"),
        pytest.param("ao3_test_api34", True, id="valid-primary-avd"),
    ],
)
@pytest.mark.p1
@allure.id("AT-BUG-063-f4-avdname-adversarial-battery")
@allure.title("Проба F4 (адверсариальная батарея): AvdName из state-файла -> предсказуемый исход, команда не меняется")
def test_f4_avdname_adversarial_battery(monkeypatch, isolated_state_file, raw_avd, should_pass):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    isolated_state_file.write_text(json.dumps({"avd_name": raw_avd}), encoding="utf-8")
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    assert len(calls) == 1
    ps_command = calls[0]["cmd"][-1]
    assert ps_command.endswith(_EXPECTED_PS_COMMAND_SUFFIX)
    if should_pass:
        assert calls[0]["env"].get("AO3_RECOVERY_AVD_NAME") == raw_avd
    else:
        assert "AO3_RECOVERY_AVD_NAME" not in calls[0]["env"]


@pytest.mark.p1
@allure.id("AT-BUG-063-corrupted-state-file-falls-back-gracefully")
@allure.title("Проба: битый/не-JSON state-файл -> recovery не падает, откатывается на env-фолбэк (device-free)")
def test_corrupted_state_file_falls_back_gracefully(monkeypatch, isolated_state_file):
    isolated_state_file.write_text("{ not valid json !!!", encoding="utf-8")
    monkeypatch.setenv("AO3_EMU_GPU", "host")
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()  # не должно бросить исключение

    assert len(calls) == 1
    assert calls[0]["env"].get("AO3_RECOVERY_GPU") == "host"  # откатилось на env-фолбэк


@pytest.mark.p1
@allure.id("AT-BUG-063-state-file-not-a-json-object")
@allure.title("Проба: state-файл валидный JSON, но не объект (напр. список) -> трактуется как пусто (device-free)")
def test_state_file_not_a_json_object(monkeypatch, isolated_state_file):
    isolated_state_file.write_text(json.dumps(["host", "ao3_test_api29"]), encoding="utf-8")
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    assert len(calls) == 1
    assert "AO3_RECOVERY_GPU" not in calls[0]["env"]
    assert "AO3_RECOVERY_AVD_NAME" not in calls[0]["env"]


# --- B3 (критик-вход rework attempt 3): диагностика применённых параметров.
# До неё python-сторона механизма молчала полностью — «применил host из
# state», «откатился на дефолт, потому что файла нет» и «отбросил значение
# вне белого списка» были неотличимы в логе прогона, при том что сам баг
# называется «молча деградирует», а PS-сторона уже пишет Write-Warning.


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-report-applied-values-and-source")
@allure.title(
    "Проба B3: recovery печатает ФАКТИЧЕСКИ применённые gpu/avd и их источник "
    "(state) — деградация больше не молчаливая (device-free)"
)
def test_b3_diagnostics_report_applied_values_and_source(
    monkeypatch, isolated_state_file, capsys
):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    isolated_state_file.write_text(
        json.dumps({"gpu": "host", "avd_name": "ao3_test_api29"}), encoding="utf-8"
    )
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert "gpu=host (source: state)" in err
    assert "avd=ao3_test_api29 (source: state)" in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-report-default-source")
@allure.title(
    "Проба B3: нет ни state-файла, ни env -> в логе явно сказано, что применён "
    "дефолт tasks.ps1 (а не тишина, device-free)"
)
def test_b3_diagnostics_report_default_source(monkeypatch, isolated_state_file, capsys):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    assert not isolated_state_file.exists()
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert "gpu=<tasks.ps1 default> (source: default)" in err
    assert "avd=<tasks.ps1 default> (source: default)" in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-warn-on-rejected-state-value")
@allure.title(
    "Проба B3: значение из state-файла вне белого списка -> ГРОМКИЙ WARNING об "
    "отбрасывании, не молчаливый дроп (device-free)"
)
def test_b3_diagnostics_warn_on_rejected_state_value(
    monkeypatch, isolated_state_file, capsys
):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    isolated_state_file.write_text(
        json.dumps({"gpu": "not_a_real_backend", "avd_name": "bad name; rm"}),
        encoding="utf-8",
    )
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert "gpu='not_a_real_backend'" in err and "ОТБРОШЕН" in err
    assert "avd_name='bad name; rm'" in err
    # и итоговая строка честно называет применённый дефолт
    assert "gpu=<tasks.ps1 default> (source: default)" in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-warn-on-corrupted-state-file")
@allure.title(
    "Проба B3: битый state-файл -> WARNING о нечитаемом файле, затем честный "
    "источник применённого значения (device-free)"
)
def test_b3_diagnostics_warn_on_corrupted_state_file(
    monkeypatch, isolated_state_file, capsys
):
    isolated_state_file.write_text("{ not valid json !!!", encoding="utf-8")
    monkeypatch.setenv("AO3_EMU_GPU", "host")
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert "нечитаем/битый" in err
    assert "gpu=host (source: env AO3_EMU_GPU)" in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-silent-when-state-file-absent")
@allure.title(
    "Проба B3 (граница шума): отсутствующий state-файл — ШТАТНЫЙ случай, "
    "WARNING о битом файле НЕ печатается (device-free)"
)
def test_b3_no_corrupt_warning_when_state_file_absent(
    monkeypatch, isolated_state_file, capsys
):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    assert not isolated_state_file.exists()
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert "нечитаем/битый" not in err
    assert "ОТБРОШЕН" not in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-warn-on-env-vs-state-conflict")
@allure.title(
    "Проба B3 (риск «инверсия приоритета»): state перекрывает AO3_EMU_GPU текущей "
    "сессии -> ЯВНЫЙ WARNING о конфликте, а не молчаливое гашение env (device-free)"
)
def test_b3_diagnostics_warn_on_env_vs_state_conflict(
    monkeypatch, isolated_state_file, capsys
):
    # Given: сессия ЗАЯВИЛА host каноническим способом (runbook), но state
    # помнит ПРОШЛЫЙ подъём на swiftshader_indirect
    monkeypatch.setenv("AO3_EMU_GPU", "host")
    isolated_state_file.write_text(
        json.dumps({"gpu": "swiftshader_indirect"}), encoding="utf-8"
    )
    calls = _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    # Then: приоритет НЕ изменён (state побеждает — семантика ядра), но
    # расхождение названо вслух
    assert calls[0]["env"].get("AO3_RECOVERY_GPU") == "swiftshader_indirect"
    err = capsys.readouterr().err
    assert "КОНФЛИКТ источников GPU" in err
    assert "'host'" in err and "'swiftshader_indirect'" in err


@pytest.mark.p1
@allure.id("AT-BUG-063-b3-diagnostics-report-state-age")
@allure.title(
    "Проба B3 (риск «протухание»): updated_utc из state-файла попадает в "
    "диагностику возрастом; отсутствие/мусор не роняет recovery (device-free)"
)
def test_b3_diagnostics_report_state_age(monkeypatch, isolated_state_file, capsys):
    monkeypatch.delenv("AO3_EMU_GPU", raising=False)
    stale = "2020-01-01T00:00:00.0000000Z"
    isolated_state_file.write_text(
        json.dumps({"gpu": "host", "updated_utc": stale}), encoding="utf-8"
    )
    _capture_run(monkeypatch)

    driver_factory._restart_emulator_writable_system()

    err = capsys.readouterr().err
    assert stale in err
    assert "возраст" in err

    # И граница: мусорный updated_utc — диагностика деградирует, recovery нет
    isolated_state_file.write_text(
        json.dumps({"gpu": "host", "updated_utc": "не-дата"}), encoding="utf-8"
    )
    calls = _capture_run(monkeypatch)
    driver_factory._restart_emulator_writable_system()
    assert calls[0]["env"].get("AO3_RECOVERY_GPU") == "host"
    assert "возраст state неизвестен" in capsys.readouterr().err


# --- tasks.ps1-сторона: real PowerShell, device-free (не запускает эмулятор) ---


@pytest.mark.p1
@allure.id("AT-BUG-063-tasksps1-set-emulator-session-state-writes-resolved-params")
@allure.title(
    "Проба AT-BUG-063 (real PowerShell, device-free): Set-EmulatorSessionState "
    "фиксирует РАЗРЕШЁННЫЕ -Gpu/-AvdName -- без запуска реального эмулятора"
)
def test_tasks_ps1_set_emulator_session_state_writes_resolved_params(tmp_path):
    """Дот-сорсит `tasks.ps1` (только определения функций + `env.ps1`
    env-переменные -- никакого device-взаимодействия) и вызывает
    `Set-EmulatorSessionState` НАПРЯМУЮ теми же значениями, которые
    `Start-Emulator` передала бы ПОСЛЕ разрешения `-Gpu host` (явный CLI-
    параметр, БЕЗ `$env:AO3_EMU_GPU` -- ровно сценарий RUN-20260811-0405).

    B2 (критик-вход rework attempt 3): проба БОЛЬШЕ НЕ пишет в РАБОЧИЙ
    `state/emulator-session.json` репозитория. Прежняя версия звала функцию
    как есть, а та резолвит путь как `"$root\\state"` (`$root` задан строкой 6
    `tasks.ps1`) -- то есть проба перетирала продакшен-state и полагалась на
    восстановление в `finally`; жёсткое завершение процесса (kill/крэш/
    прерывание прогона) оставило бы ЧУЖИЕ параметры (`ao3_test_api29`)
    источником истины для СЛЕДУЮЩЕГО device-liveness recovery -- ровно тот
    класс отказа (F4: recovery поднимает не тот AVD), который этот баг и
    закрывает. Теперь `$root` переопределяется на `tmp_path` СРАЗУ ПОСЛЕ
    дот-сорсинга: PowerShell резолвит `$root` внутри функции по цепочке
    областей ПРИ КАЖДОМ вызове, поэтому исполняется ровно тот же код той же
    функции (покрытие real-PowerShell, включая BOM-поведение записи, не
    теряется), но запись уходит во временный каталог теста.

    Изоляция проверяется ЯВНО (не декларативно): байты/наличие реального
    state-файла сверяются до и после -- проба сама доказывает, что продакшен-
    state не тронут."""
    tasks_ps1 = settings.REPO_ROOT / "scripts" / "tasks.ps1"
    real_state_file = settings.REPO_ROOT / "state" / "emulator-session.json"
    real_existed_before = real_state_file.exists()
    real_bytes_before = real_state_file.read_bytes() if real_existed_before else None

    fake_root = tmp_path / "fake_repo_root"
    fake_root.mkdir()
    ps_command = (
        f". \"{tasks_ps1}\"; "
        f"$root = '{fake_root}'; "
        "Set-EmulatorSessionState -Gpu 'host' -AvdName 'ao3_test_api29'"
    )
    cp = _real_subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
        capture_output=True, text=True, timeout=30,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"

    written = fake_root / "state" / "emulator-session.json"
    assert written.exists(), (
        f"Set-EmulatorSessionState не создала {written}\n"
        f"stdout={cp.stdout}\nstderr={cp.stderr}"
    )
    # utf-8 (НЕ utf-8-sig): проба целится ровно в BOM-баг, найденный красной
    # пробой attempt 2 -- если запись снова начнёт класть BOM, json.loads
    # упадёт здесь, а не будет молча прощён лояльным чтением.
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["gpu"] == "host"
    assert data["avd_name"] == "ao3_test_api29"

    # И НИ БАЙТА в реальном state репозитория (сам класс F4-риска)
    assert real_state_file.exists() == real_existed_before
    if real_existed_before:
        assert real_state_file.read_bytes() == real_bytes_before
