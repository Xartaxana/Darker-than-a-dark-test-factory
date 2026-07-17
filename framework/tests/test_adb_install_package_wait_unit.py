"""Device-free юнит-проба ожидания готовности package-сервиса перед `adb
install` (AT-BUG-013, queue-пункт 1 docs/HANDOFF.md — замеченный critic'ом на
приёмке AT-BUG-013 аналог класса, ранее закрытого только для канонического
пути `tasks.ps1::Install-App`/`Wait-PackageServiceReady`).

Доказывает, что `framework/core/adb.py::install()` (реальный путь конвейера
при fresh-boot через `conftest.py::_ensure_app_installed`, минуя tasks.ps1)
теперь опрашивает `pm path android` перед первой попыткой установки:
- сервис готов сразу -> install идёт без единой доп. задержки (ноль `sleep`);
- сервис не готов N раз, потом готов -> install всё равно проходит (ретрай
  внутри `_wait_package_service_ready`, не наружу вызывающему коду);
- сервис никогда не готов -> явная `RuntimeError` с понятным текстом (что
  ждали, сколько попыток, ссылка на AT-BUG-013), НЕ таймаут-мусор и НЕ голый
  `TimeoutError`/`subprocess.TimeoutExpired`.

НЕ требует устройства/эмулятора: монки-патчит `subprocess.run` (тот же приём,
что `test_subprocess_timeout_unit.py`) и `time.sleep` внутри `adb`-модуля,
чтобы «N попыток» не ждали реальные секунды между опросами. Переопределяет
session-scoped autouse-фикстуру `_ensure_app_installed` из `conftest.py` (та
иначе дёрнула бы `adb pm list packages` при сборе тестов) — тот же приём, что
и остальные device-free пробы этого пакета.
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.core import adb


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретраи внутри `_wait_package_service_ready` не должны ждать реальные
    секунды в юнит-пробе — считаем вызовы, но не спим."""
    calls = {"n": 0}
    monkeypatch.setattr(adb.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


def _fake_run_factory(pm_path_ready_after: int):
    """Фейк `subprocess.run`, различающий опрос готовности (`pm path android`)
    от самого `adb install` — сервис "готов" начиная с `pm_path_ready_after`-го
    опроса (0 = готов сразу)."""
    state = {"pm_path_calls": 0}

    def _run(args, **kw):
        if "pm path android" in args:
            state["pm_path_calls"] += 1
            if state["pm_path_calls"] > pm_path_ready_after:
                return subprocess.CompletedProcess(args=args, returncode=0,
                                                    stdout="package:android\n", stderr="")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        # `adb install -r dummy.apk`
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="Success", stderr="")

    return _run, state


@pytest.mark.p2
@allure.id("AT-BUG-013-adb-install-package-service-ready-immediately")
@allure.title("Проба: install() не тратит ни одного sleep, если package-сервис готов сразу (device-free)")
def test_install_no_extra_delay_when_service_ready_immediately(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(pm_path_ready_after=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    adb.install(apk="dummy.apk")

    # Then счастливый путь: ровно один опрос pm path, ни одного sleep
    assert state["pm_path_calls"] == 1
    assert _no_real_sleep["n"] == 0


@pytest.mark.p2
@allure.id("AT-BUG-013-adb-install-package-service-ready-after-retries")
@allure.title("Проба: install() ретраит опрос N раз, потом проходит, когда сервис становится готов (device-free)")
def test_install_retries_until_service_ready(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(pm_path_ready_after=3)
    monkeypatch.setattr(subprocess, "run", fake_run)

    # When первые 3 опроса пусты, 4-й — готов; install() не должен упасть
    adb.install(apk="dummy.apk", package_service_timeout=5)

    assert state["pm_path_calls"] == 4
    assert _no_real_sleep["n"] == 3


@pytest.mark.p2
@allure.id("AT-BUG-013-adb-install-package-service-never-ready")
@allure.title("Проба: install() падает явной RuntimeError (не таймаут-мусором), если сервис так и не готов (device-free)")
def test_install_raises_clear_error_when_service_never_ready(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(pm_path_ready_after=float("inf"))  # никогда не готов
    monkeypatch.setattr(subprocess, "run", fake_run)

    # When таймаут короткий (не ждём реальные 30s дефолта) — сервис никогда не отвечает
    with pytest.raises(RuntimeError) as exc_info:
        adb.install(apk="dummy.apk", package_service_timeout=0.05)

    message = str(exc_info.value)
    assert "package-сервис" in message
    assert "AT-BUG-013" in message
    assert "0.05" in message
    # Ошибка явная и осмысленная — не голый TimeoutError/subprocess.TimeoutExpired
    assert not isinstance(exc_info.value, TimeoutError)
