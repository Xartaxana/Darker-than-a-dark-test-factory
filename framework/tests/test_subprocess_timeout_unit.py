"""Device-free юнит-проба timeout-класса subprocess-вызовов — AT-BUG-009,
инкремент 1 (закрытие кандидата «subprocess-вызовы без timeout»).

Доказывает, что `framework/core/adb.py::_run()`/`pull_app_file()` и
`framework/core/mitm.py::set_device_proxy`/`clear_device_proxy` оборачивают
`subprocess.TimeoutExpired` в явную `TimeoutError` с контекстом (какая команда,
сколько ждали) — конечная ошибка вместо неограниченного клина (тот же класс,
что `bugs/AT-BUG-007.md` закрыл для Appium HTTP-вызовов; находка N1 того же
бага и наблюдение №1 `bugs/AT-BUG-009.md`).

НЕ требует устройства/эмулятора: монки-патчит `subprocess.run`, имитируя
зависший/неотвечающий adb-shell. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (та иначе дёрнула бы `adb pm list
packages` при сборе тестов) — тот же приём, что и
`test_seed_filter_profiles_unit.py`.
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.config import settings
from framework.core import adb, mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


def _raise_timeout_expired(cmd, timeout):
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)


@pytest.mark.p2
@allure.id("AT-BUG-009-adb-run-timeout")
@allure.title("Проба: adb._run() оборачивает зависший subprocess в TimeoutError с контекстом (device-free)")
def test_adb_run_wraps_timeout_expired(monkeypatch):
    # Given subprocess.run внутри adb._run() зависает и падает TimeoutExpired
    # (имитация мёртвого/неотвечающего adb-shell — без реального устройства)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _raise_timeout_expired(a[0], kw.get("timeout")),
    )

    # When вызывается любой shell-вызов через _run() (дефолтный ADB_SHELL_TIMEOUT)
    with pytest.raises(TimeoutError) as exc_info:
        adb.shell("pm list packages")

    # Then исключение — TimeoutError (не голый TimeoutExpired), сообщение несёт
    # контекст: саму команду и сколько ждали (критерий задачи п.1)
    message = str(exc_info.value)
    assert "shell" in message
    assert str(settings.ADB_SHELL_TIMEOUT) in message
    assert "AT-BUG-009" in message


@pytest.mark.p2
@allure.id("AT-BUG-009-adb-install-transfer-timeout")
@allure.title("Проба: adb.install() использует ADB_TRANSFER_TIMEOUT, не ADB_SHELL_TIMEOUT (device-free)")
def test_adb_install_uses_transfer_timeout(monkeypatch):
    # Given subprocess.run фиксирует, с каким timeout его реально позвали
    seen_timeouts: list = []

    def _fake_run(*args, **kw):
        seen_timeouts.append(kw.get("timeout"))
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="Success", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # When вызывается install() — файловая операция (APK), не обычный shell-вызов
    adb.install(apk="dummy.apk")

    # Then применён ADB_TRANSFER_TIMEOUT (щедрее обычного shell-таймаута), не дефолт
    assert seen_timeouts == [settings.ADB_TRANSFER_TIMEOUT]


@pytest.mark.p2
@allure.id("AT-BUG-009-adb-pull-app-file-timeout")
@allure.title("Проба: adb.pull_app_file() (мимо _run) оборачивает TimeoutExpired в TimeoutError (device-free)")
def test_adb_pull_app_file_wraps_timeout_expired(monkeypatch, tmp_path):
    # Given pull_app_file зовёт subprocess.run НАПРЯМУЮ (не через _run — нужны
    # сырые байты без text=True), но тем же ADB_TRANSFER_TIMEOUT
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _raise_timeout_expired(a[0], kw.get("timeout")),
    )

    # When/Then зависший exec-out тоже падает явной TimeoutError с контекстом
    with pytest.raises(TimeoutError) as exc_info:
        adb.pull_app_file("databases/app.db", tmp_path / "app.db")

    message = str(exc_info.value)
    assert "run-as" in message
    assert str(settings.ADB_TRANSFER_TIMEOUT) in message


@pytest.mark.p2
@allure.id("AT-BUG-009-mitm-set-proxy-timeout")
@allure.title("Проба: mitm.set_device_proxy() оборачивает зависший adb в TimeoutError (device-free)")
def test_mitm_set_device_proxy_wraps_timeout_expired(monkeypatch):
    # Given зависший `adb shell settings put http_proxy` (кандидат в корень
    # наблюдения №1 AT-BUG-009 — переключение replay-прокси на нагруженной
    # длинной сессии)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _raise_timeout_expired(a[0], kw.get("timeout")),
    )

    with pytest.raises(TimeoutError) as exc_info:
        mitm.set_device_proxy()

    message = str(exc_info.value)
    assert "set_device_proxy" in message
    assert str(settings.ADB_SHELL_TIMEOUT) in message


@pytest.mark.p2
@allure.id("AT-BUG-009-mitm-clear-proxy-timeout")
@allure.title("Проба: mitm.clear_device_proxy() падает TimeoutError несмотря на check=False (device-free)")
def test_mitm_clear_device_proxy_wraps_timeout_expired(monkeypatch):
    # Given clear_device_proxy зовёт subprocess.run(..., check=False) — но
    # TimeoutExpired это исключение (не ненулевой returncode), check=False его
    # не подавляет: teardown обязан падать явной ошибкой, не висеть молча
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _raise_timeout_expired(a[0], kw.get("timeout")),
    )

    with pytest.raises(TimeoutError) as exc_info:
        mitm.clear_device_proxy()

    message = str(exc_info.value)
    assert "clear_device_proxy" in message
