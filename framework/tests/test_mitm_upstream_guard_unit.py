"""Device-free юнит-проба fail-fast guard'ов ESC-009
(`framework/core/mitm.py::assert_upstream_fast` и `_assert_own_listener`).

Диагноз (state/escalations.md ESC-009, «Корень 3»): мёртвый IPv6-транзит
хоста заставляет mitmproxy платить ~21с Windows TCP-connect-таймаута ЗА
КАЖДЫЙ мёртвый IPv6-адрес апстрима, суммарно давая ~166с `ReadTimeoutError`
на первой replay-навигации вместо мгновенного диагноза. Эта проба доказывает
две вещи БЕЗ устройства и без реальной сети:
1. `assert_upstream_fast()` реально измеряет connect() к первому адресу
   резолва — недостижимый адрес с крошечным бюджетом падает БЫСТРО явной
   `RuntimeError` с текстом ESC-009; достижимый (локальный listening-сокет
   теста) проходит молча.
2. `_assert_own_listener()` (замок против чужого слушателя порта, прецедент
   Errno 10048 сессии 2026-07-30) падает `RuntimeError`, когда `_proc.poll()`
   сообщает о завершившемся процессе.

Переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` (устройство не трогаем) — тот же приём, что
`test_replay_ca_check_unit.py`/`test_mitm_proxy_reachable_unit.py`.
"""
from __future__ import annotations

import socket

import allure
import pytest

from framework.core import mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем."""
    yield


# --- assert_upstream_fast ---


@pytest.mark.p1
@allure.id("ESC-009-upstream-guard-unreachable")
@allure.title("Проба: assert_upstream_fast() падает RuntimeError с ESC-009 в тексте, когда первый адрес недостижим за крошечный бюджет (device-free)")
def test_assert_upstream_fast_raises_when_unreachable(monkeypatch):
    # Given RFC 5737-адрес документации (гарантированно не отвечает, TEST-NET-1)
    # и крошечный бюджет — недостижимость должна проявиться БЫСТРО, не ждать
    # реальный ОС-таймаут
    monkeypatch.setattr(mitm, "UPSTREAM_CONNECT_BUDGET", 0.2)

    with pytest.raises(RuntimeError) as exc_info:
        mitm.assert_upstream_fast(host="192.0.2.1", port=443)

    message = str(exc_info.value)
    assert "ESC-009" in message
    assert "192.0.2.1" in message


@pytest.mark.p1
@allure.id("ESC-009-upstream-guard-reachable")
@allure.title("Проба: assert_upstream_fast() проходит молча, когда первый адрес резолва достижим (device-free, локальный listening-сокет)")
def test_assert_upstream_fast_passes_when_reachable():
    # Given реальный локальный TCP-сервер, слушающий на 127.0.0.1:<свободный порт>
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        # When/Then соединение реально устанавливается — проверка не бросает
        mitm.assert_upstream_fast(host="127.0.0.1", port=port)
    finally:
        listener.close()


# --- _assert_own_listener (poll-замок против чужого слушателя) ---


class _FakeProc:
    def __init__(self, returncode):
        self._returncode = returncode

    def poll(self):
        return self._returncode


@pytest.mark.p1
@allure.id("ESC-009-own-listener-lock-dead-proc")
@allure.title("Проба: _assert_own_listener() падает RuntimeError, когда _proc уже завершился (poll() != None) — прецедент Errno 10048 (device-free)")
def test_assert_own_listener_raises_when_proc_dead(monkeypatch):
    # Given _proc, чей poll() сообщает о завершении с кодом 10048 (Errno
    # прецедента: порт уже занят чужим процессом)
    monkeypatch.setattr(mitm, "_proc", _FakeProc(returncode=10048))

    with pytest.raises(RuntimeError) as exc_info:
        mitm._assert_own_listener()

    message = str(exc_info.value)
    assert "10048" in message
    assert "ЧУЖОЙ" in message


@pytest.mark.p1
@allure.id("ESC-009-own-listener-lock-alive-proc")
@allure.title("Проба: _assert_own_listener() проходит молча, когда _proc ещё жив (poll() == None) (device-free)")
def test_assert_own_listener_passes_when_proc_alive(monkeypatch):
    # Given _proc, чей poll() сообщает «ещё жив» (None) — штатный happy path
    monkeypatch.setattr(mitm, "_proc", _FakeProc(returncode=None))

    # When/Then замок не бросает
    mitm._assert_own_listener()
