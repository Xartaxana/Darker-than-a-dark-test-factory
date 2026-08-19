"""Device-free юнит-проба `mitm.start_replay(..., capture_out=, capture_url_substr=)`
(AT-BUG-073, критерий готовности п.4 — критик-вход attempt 4, блокер 2:
fail-fast на несогласованную пару `capture_url_substr` БЕЗ `capture_out`).

Обе стороны границы (замечание критика «тест на обе стороны границы»):
  - `capture_url_substr` задан, `capture_out=None` -> `ValueError` СРАЗУ, ДО
    любого `Popen`/`--server-replay` (несогласованная пара — раньше молча НЕ
    грузила addon вовсе, без диагностики);
  - та же `capture_url_substr`, но с `capture_out` заданным -> НЕ бросает,
    addon подключается (`-s`) с ОБОИМИ `--set`.
Плюс обе исходные "неактивные" комбинации (оба `None`/пусты; только
`capture_out` без `capture_url_substr`, т.е. "перехватывать всё") остаются
рабочими без исключения — регрессия к прежнему поведению исключена.

`subprocess.Popen`/`socket.socket` мокнуты (тот же приём, что
`test_mitm_port_race_unit.py`) — ни один mitmdump/порт 8080 не поднимается.
"""
from __future__ import annotations

import allure
import pytest

from framework.core import mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем (тот же приём, что соседние
    `test_mitm_*_unit.py`)."""
    yield


@pytest.fixture(autouse=True)
def _reset_proc_state():
    mitm._proc = None
    yield
    mitm._proc = None


class _FakeListeningProc:
    returncode = None

    def poll(self):
        return None


class _FakeListeningSocket:
    """connect_ex сразу успешен -- имитирует mitmdump, поднявший порт с
    первой же попытки (счастливый путь, не тестируем ретраи здесь -- те уже
    покрыты `test_mitm_port_race_unit.py`)."""

    def settimeout(self, t):
        pass

    def connect_ex(self, addr):
        return 0

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def _fake_successful_spawn(monkeypatch):
    """Мокает `subprocess.Popen`/`socket.socket` так, что ЛЮБОЙ вызов
    `_spawn_and_wait_listening` внутри `start_replay` немедленно "успешен" —
    возвращает `_FakeListeningProc`, порт "слушается" с первого опроса.
    Возвращает список ФАКТИЧЕСКИ переданных в `Popen` args (список списков,
    один на вызов) для проверки построения командной строки."""
    calls: list[list[str]] = []

    def fake_popen(args, *a, **kw):
        calls.append(list(args))
        return _FakeListeningProc()

    monkeypatch.setattr(mitm.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mitm.socket, "socket", lambda *a, **kw: _FakeListeningSocket())
    monkeypatch.setattr(mitm, "_assert_own_listener", lambda: None)
    return calls


@pytest.mark.p1
@allure.id("AT-BUG-073-start-replay-substr-without-out-raises")
@allure.title("Проба: start_replay(capture_url_substr=...) БЕЗ capture_out бросает ValueError СРАЗУ, ДО любого Popen (критик-вход attempt 4, блокер 2) (device-free)")
def test_start_replay_substr_without_capture_out_raises_before_spawn(monkeypatch):
    spawned = {"n": 0}

    def _counting_popen(*a, **kw):
        spawned["n"] += 1
        return _FakeListeningProc()

    monkeypatch.setattr(mitm.subprocess, "Popen", _counting_popen)

    with pytest.raises(ValueError) as exc_info:
        mitm.start_replay("fake.mitm", capture_url_substr="/api/v4/snippets")

    assert "capture_url_substr" in str(exc_info.value)
    assert "capture_out" in str(exc_info.value)
    assert spawned["n"] == 0
    assert mitm._proc is None


@pytest.mark.p1
@allure.id("AT-BUG-073-start-replay-substr-with-out-does-not-raise")
@allure.title("Проба: та же capture_url_substr С заданным capture_out — НЕ бросает, addon подключается с ОБОИМИ --set (device-free)")
def test_start_replay_substr_with_capture_out_does_not_raise(tmp_path, _fake_successful_spawn):
    capture_out = tmp_path / "cap.jsonl"

    mitm.start_replay("fake.mitm", capture_url_substr="/api/v4/snippets", capture_out=capture_out)

    assert len(_fake_successful_spawn) == 1
    args = _fake_successful_spawn[0]
    assert "-s" in args
    assert str(mitm._CAPTURE_ADDON_PATH) in args
    assert f"capture_out={capture_out}" in args
    assert "capture_url_substr=/api/v4/snippets" in args


@pytest.mark.p1
@allure.id("AT-BUG-073-start-replay-neither-capture-arg-unchanged")
@allure.title("Проба: без capture_out И без capture_url_substr (оба default) — НЕ бросает, addon НЕ подключается (прежнее поведение, регрессия исключена) (device-free)")
def test_start_replay_no_capture_args_unchanged_behavior(_fake_successful_spawn):
    mitm.start_replay("fake.mitm")

    assert len(_fake_successful_spawn) == 1
    args = _fake_successful_spawn[0]
    assert "-s" not in args
    assert not any(a.startswith("capture_out=") for a in args)
    assert not any(a.startswith("capture_url_substr=") for a in args)


@pytest.mark.p1
@allure.id("AT-BUG-073-start-replay-capture-out-without-substr-means-capture-all")
@allure.title("Проба: capture_out БЕЗ capture_url_substr — валидно, addon подключается с пустой capture_url_substr ('перехватывать всё') (device-free)")
def test_start_replay_capture_out_without_substr_is_valid(tmp_path, _fake_successful_spawn):
    capture_out = tmp_path / "cap.jsonl"

    mitm.start_replay("fake.mitm", capture_out=capture_out)  # capture_url_substr default ""

    args = _fake_successful_spawn[0]
    assert "-s" in args
    assert "capture_url_substr=" in args  # пустое значение -- "перехватывать всё"
