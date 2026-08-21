"""Device-free юнит-проба адресации adb-вызовов `-s <serial>` в
`framework/core/mitm.py` (задача mitm-adb-serial-class-fix).

Класс B3 (найден пилотом N4 — на хосте теперь штатно ДВА эмулятора): голые
adb-команды без `-s <serial>` ломаются при двух подключённых устройствах —
`adb` либо падает («more than one device/emulator»), либо (для команд с
`check=False`/чтением stdout) молча деградирует. Эталон адресации —
`framework/core/adb.py`, где КАЖДЫЙ вызов несёт `-s settings.DEVICE_NAME`.

Пробы ниже доказывают, что все adb-вызовы `mitm.py` (класс, не экземпляр —
пройдено по ВСЕМУ файлу, не только по трём функциям из спеки) строят команду
с `-s settings.DEVICE_NAME` сразу после `settings.ADB`:
- `set_device_proxy()` / `clear_device_proxy()` / `get_device_proxy()` —
  основной инстанс класса из манифеста задачи;
- `is_ca_installed()` (`adb shell ls <apex cacerts dir>`, AT-BUG-011) и
  `wait_device_proxy_reachable()` (`adb shell nc ...`, AT-BUG-017) —
  замеченные аналоги того же класса в том же файле.

Тот же приём монки-патча `subprocess.run` и переопределения session-scoped
autouse-фикстуры `_ensure_app_installed`, что у соседей этого пакета
(`test_residual_proxy_guard_unit.py`, `test_mitm_proxy_reachable_unit.py`,
`test_replay_ca_check_unit.py`) — реальный adb/устройство не трогается ни в
одном тесте этого модуля.
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.config import settings
from framework.core import mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем."""
    yield


def _capturing_run(calls: list):
    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    return _run


@pytest.mark.p1
@allure.id("mitm-adb-serial-class-fix-set-device-proxy")
@allure.title("Проба: set_device_proxy() адресует adb-команду -s settings.DEVICE_NAME (device-free)")
def test_set_device_proxy_addresses_serial(monkeypatch):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _capturing_run(calls))

    mitm.set_device_proxy()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == settings.ADB
    assert cmd[1] == "-s"
    assert cmd[2] == settings.DEVICE_NAME
    assert cmd[3] == "shell"


@pytest.mark.p1
@allure.id("mitm-adb-serial-class-fix-clear-device-proxy")
@allure.title("Проба: clear_device_proxy() адресует adb-команду -s settings.DEVICE_NAME (device-free)")
def test_clear_device_proxy_addresses_serial(monkeypatch):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _capturing_run(calls))

    mitm.clear_device_proxy()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == settings.ADB
    assert cmd[1] == "-s"
    assert cmd[2] == settings.DEVICE_NAME
    assert cmd[3] == "shell"


@pytest.mark.p1
@allure.id("mitm-adb-serial-class-fix-get-device-proxy")
@allure.title("Проба: get_device_proxy() адресует adb-команду -s settings.DEVICE_NAME (device-free)")
def test_get_device_proxy_addresses_serial(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=":0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    mitm.get_device_proxy()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == settings.ADB
    assert cmd[1] == "-s"
    assert cmd[2] == settings.DEVICE_NAME
    assert cmd[3] == "shell"


@pytest.mark.p2
@allure.id("mitm-adb-serial-class-fix-is-ca-installed-analog")
@allure.title("Проба (замеченный аналог класса): is_ca_installed() адресует adb shell ls -s settings.DEVICE_NAME (device-free)")
def test_is_ca_installed_addresses_serial(tmp_path, monkeypatch):
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))

    calls: list = []

    def _run(args, **kw):
        exe = str(args[0]).lower()
        if "openssl" in exe:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="deadbeef\n", stderr="")
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="deadbeef.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    mitm.is_ca_installed()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == settings.ADB
    assert cmd[1] == "-s"
    assert cmd[2] == settings.DEVICE_NAME
    assert cmd[3] == "shell"


@pytest.mark.p2
@allure.id("mitm-adb-serial-class-fix-wait-proxy-reachable-analog")
@allure.title("Проба (замеченный аналог класса): wait_device_proxy_reachable() адресует adb shell nc -s settings.DEVICE_NAME (device-free)")
def test_wait_device_proxy_reachable_addresses_serial(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="AO3_PROXY_REACHABLE\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    mitm.wait_device_proxy_reachable()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == settings.ADB
    assert cmd[1] == "-s"
    assert cmd[2] == settings.DEVICE_NAME
    assert cmd[3] == "shell"
