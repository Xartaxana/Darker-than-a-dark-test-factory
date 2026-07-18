"""Device-free юнит-проба ожидания достижимости replay-прокси СО СТОРОНЫ
УСТРОЙСТВА (AT-BUG-017).

Доказывает, что `framework/core/mitm.py::wait_device_proxy_reachable()`:
- прокси достижим сразу -> ноль лишней задержки (ноль `sleep`, ровно один
  опрос `adb shell nc`);
- прокси недостижим N раз, потом достижим -> проходит без исключения (ретрай
  внутри самой функции, не наружу вызывающей `replay`-фикстуре);
- прокси никогда не достижим -> явная `TimeoutError` с контекстом (какой
  прокси, сколько ждали, сколько попыток, ссылка на AT-BUG-017) — не голый
  `subprocess.TimeoutExpired`, не молчаливый клин.

Тот же приём, что `test_adb_install_package_wait_unit.py` (AT-BUG-013): монки-
патчит `subprocess.run` и `time.sleep` внутри `mitm`-модуля, чтобы ретраи не
ждали реальные секунды. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (устройство не трогаем).
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


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретраи внутри `wait_device_proxy_reachable` не должны ждать реальные
    секунды в юнит-пробе — считаем вызовы, но не спим."""
    calls = {"n": 0}
    monkeypatch.setattr(mitm.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


def _fake_run_factory(reachable_after: int):
    """Фейк `subprocess.run` для `adb shell nc ...` — прокси "достижим"
    начиная с `reachable_after`-й попытки (0 = достижим сразу)."""
    state = {"calls": 0}

    def _run(args, **kw):
        state["calls"] += 1
        if state["calls"] > reachable_after:
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="AO3_PROXY_REACHABLE\n", stderr="",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="NOPE\n", stderr="")

    return _run, state


@pytest.mark.p2
@allure.id("AT-BUG-017-mitm-proxy-reachable-immediately")
@allure.title("Проба: wait_device_proxy_reachable() не тратит ни одного sleep, если прокси достижим сразу (device-free)")
def test_reachable_no_extra_delay_when_ready_immediately(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(reachable_after=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    mitm.wait_device_proxy_reachable()

    assert state["calls"] == 1
    assert _no_real_sleep["n"] == 0


@pytest.mark.p2
@allure.id("AT-BUG-017-mitm-proxy-reachable-after-retries")
@allure.title("Проба: wait_device_proxy_reachable() ретраит опрос N раз, потом проходит, когда прокси становится достижим (device-free)")
def test_reachable_retries_until_ready(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(reachable_after=3)
    monkeypatch.setattr(subprocess, "run", fake_run)

    # When первые 3 опроса — NOPE, 4-й — достижим; функция не должна упасть
    mitm.wait_device_proxy_reachable(timeout=5)

    assert state["calls"] == 4
    assert _no_real_sleep["n"] == 3


@pytest.mark.p2
@allure.id("AT-BUG-017-mitm-proxy-never-reachable")
@allure.title("Проба: wait_device_proxy_reachable() падает явной TimeoutError с контекстом, если прокси так и не достижим (device-free)")
def test_reachable_raises_clear_error_when_never_ready(monkeypatch, _no_real_sleep):
    fake_run, state = _fake_run_factory(reachable_after=10**6)  # никогда не достижим
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(TimeoutError) as exc_info:
        mitm.wait_device_proxy_reachable(timeout=0.05)

    message = str(exc_info.value)
    assert settings.PROXY_HOST_ALIAS in message
    assert "AT-BUG-017" in message
    assert "0.05" in message


@pytest.mark.p2
@allure.id("AT-BUG-017-mitm-proxy-reachable-wraps-timeout-expired")
@allure.title("Проба: wait_device_proxy_reachable() трактует зависший adb shell nc как неудачную попытку, не падает голым TimeoutExpired (device-free)")
def test_reachable_treats_hung_adb_as_failed_attempt(monkeypatch, _no_real_sleep):
    # Given adb shell nc виснет и падает subprocess.TimeoutExpired на КАЖДОЙ
    # попытке (не только один раз) — функция обязана трактовать это как
    # "пока не достижимо" и продолжать ретраить, а не пробрасывать голый
    # TimeoutExpired наружу.
    def _hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout"))

    monkeypatch.setattr(subprocess, "run", _hang)

    with pytest.raises(TimeoutError) as exc_info:
        mitm.wait_device_proxy_reachable(timeout=0.05)

    # Then это НАША TimeoutError с контекстом AT-BUG-017 (не голый
    # subprocess.TimeoutExpired, не какое-то другое исключение)
    assert "AT-BUG-017" in str(exc_info.value)
