"""Device-free юнит-проба AT-BUG-043 (гонка teardown(stop())/startup
(start_replay|start_record) порта 8080 в `framework/core/mitm.py` на
Windows — `bugs/AT-BUG-043.md`, `state/escalations.md` ESC-016).

Красная проба живой гонки (scratchpad этой сессии: ~150 циклов
stop()->start() в изоляции + под искусственной CPU-нагрузкой + 31 живой
переход между соседними replay-тестами на реальном устройстве) НЕ смогла
детерминированно воспроизвести исходный WinError 10048 — механизм
подтверждён только по коду/диагнозу (`Popen.wait()` на Windows может
сигнализировать код завершения процесса раньше полной ОС-очистки порта),
не по факту повторной красной пробы (см. `bugs/AT-BUG-043.md`,
Обсуждение). Эта проба поэтому доказывает МЕХАНИКУ фикса на управляемых
фейках (device-free, тот же приём, что `test_mitm_upstream_guard_unit.py`/
`test_mitm_proxy_reachable_unit.py`), а не сам живой race:
1. `_wait_port_released()` ретраит bind() до успеха и не сообщает об
   успехе преждевременно; при не-освобождении порта — явная `TimeoutError`
   с AT-BUG-043 в тексте.
2. `_spawn_and_wait_listening()` ретраит `Popen`, когда СВОЙ процесс
   немедленно умирает, ничего не заслушав (конфликт bind), и НЕ ретраит,
   когда процесс жив, но просто медленно стартует (не гонка порта —
   прежнее поведение `TimeoutError` без ретрая).
3. Семантика замка ESC-009 (`_assert_own_listener`, чужой слушатель) не
   тронута: если порт становится connectable раньше, чем свой процесс
   поспевает умереть, `_spawn_and_wait_listening()` возвращает `proc`
   немедленно, БЕЗ ретрая — ловит подмену вызывающий код (`_assert_own_
   listener()`), как и раньше.

ATTEMPT 2 (критик-вход, `bugs/AT-BUG-043.md`, два блокера device-free
пробой критика):
4. Блокер 1 (teardown-цепочка) — `_wait_port_released()` БОЛЬШЕ НЕ бросает
   `TimeoutError` на исчерпании ожидания: пишет предупреждение в stderr и
   возвращается, чтобы `stop()` никогда не срывал `conftest.py`-teardown
   (`mitm.stop()`/`mitm.clear_device_proxy()`, теперь раздельным
   `try/finally` — второй, независимый слой той же защиты). Видимый сигнал
   ретрая (детектор рецидива, правило 10в CLAUDE.md) печатается и на
   счастливом пути С ретраями, и на исчерпании таймаута.
5. Блокер 2 (владение хэндлом) — модуль-уровневый `_proc` присваивается
   СРАЗУ после каждого `Popen()` внутри `_spawn_and_wait_listening()`, не
   только при успешном возврате — ветка «процесс жив, но порт не поднялся
   за `ready_timeout`» больше не оставляет сироту; ветка «ретраи
   исчерпаны, процесс мёртв» явно сбрасывает `_proc` в `None` (мёртвый
   хэндл не нужен, ничейного ЖИВОГО процесса не остаётся).

Переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` (устройство не трогаем) — тот же приём, что соседние
`test_mitm_*_unit.py`.
"""
from __future__ import annotations

import allure
import pytest

from framework.core import mitm


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем."""
    yield


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Ретраи внутри проверяемых функций не должны ждать реальные секунды
    в юнит-пробе — считаем вызовы, но не спим (тот же приём, что
    `test_mitm_proxy_reachable_unit.py`)."""
    calls = {"n": 0}
    monkeypatch.setattr(mitm.time, "sleep", lambda s: calls.__setitem__("n", calls["n"] + 1))
    return calls


@pytest.fixture(autouse=True)
def _reset_proc_state():
    """Attempt 2, блокер 2: `_proc` теперь пишется несколькими путями
    внутри `_spawn_and_wait_listening()` — изолируем модульное состояние
    между тестами этого файла (и от возможной утечки из соседних юнит-проб
    в том же pytest-процессе)."""
    mitm._proc = None
    yield
    mitm._proc = None


# --- _wait_port_released ---


def _fake_bind_socket_factory(bind_errors: int):
    """Фейк `socket.socket(...)` для `_wait_port_released`: первые
    `bind_errors` вызовов `.bind()` бросают WinError-10048-подобный
    `OSError`, дальше `.bind()` успевает."""
    state = {"bind_calls": 0}

    class _FakeSock:
        def bind(self, addr):
            state["bind_calls"] += 1
            if state["bind_calls"] <= bind_errors:
                raise OSError(10048, "address already in use")

        def close(self):
            pass

    def factory(*args, **kwargs):
        return _FakeSock()

    factory.state = state
    return factory


@pytest.mark.p1
@allure.id("AT-BUG-043-wait-port-released-retries-then-succeeds")
@allure.title("Проба: _wait_port_released() ретраит bind() до успеха и возвращается без исключения (device-free)")
def test_wait_port_released_retries_then_succeeds(monkeypatch, _no_real_sleep):
    factory = _fake_bind_socket_factory(bind_errors=2)
    monkeypatch.setattr(mitm.socket, "socket", factory)

    mitm._wait_port_released(8080, timeout=5.0)

    assert factory.state["bind_calls"] == 3
    assert _no_real_sleep["n"] == 2


@pytest.mark.p1
@allure.id("AT-BUG-043-wait-port-released-warns-not-raises")
@allure.title("Проба: _wait_port_released() attempt 2 (критик-вход, блокер 1) НЕ бросает исключение на исчерпании таймаута -- пишет предупреждение в stderr и возвращается (device-free)")
def test_wait_port_released_warns_without_raising_on_timeout(monkeypatch, _no_real_sleep, capsys):
    # Given порт никогда не освобождается -- ДО attempt 2 это оканчивалось
    # TimeoutError, который stop() пробрасывал в conftest.py teardown БЕЗ
    # try/finally, срывая clear_device_proxy() (блокер 1)
    factory = _fake_bind_socket_factory(bind_errors=10**6)
    monkeypatch.setattr(mitm.socket, "socket", factory)

    mitm._wait_port_released(8080, timeout=0.05)  # не должно бросить

    captured = capsys.readouterr()
    assert "AT-BUG-043" in captured.err
    assert "WARNING" in captured.err
    assert "8080" in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-043-wait-port-released-signal-on-retry")
@allure.title("Проба: _wait_port_released() печатает видимый сигнал ретрая в stderr, когда порт освободился НЕ с первой попытки (детектор рецидива, attempt 2) (device-free)")
def test_wait_port_released_prints_signal_on_successful_retry(monkeypatch, _no_real_sleep, capsys):
    factory = _fake_bind_socket_factory(bind_errors=2)
    monkeypatch.setattr(mitm.socket, "socket", factory)

    mitm._wait_port_released(8080, timeout=5.0)

    captured = capsys.readouterr()
    assert "AT-BUG-043" in captured.err
    assert "3" in captured.err  # число попыток (bind_errors=2 + успешная 3-я)


@pytest.mark.p1
@allure.id("AT-BUG-043-wait-port-released-no-signal-happy-path")
@allure.title("Проба: _wait_port_released() НЕ печатает сигнал, если порт освободился с первой попытки (счастливый путь, ноль лишнего шума) (device-free)")
def test_wait_port_released_no_signal_when_no_retry_needed(monkeypatch, _no_real_sleep, capsys):
    factory = _fake_bind_socket_factory(bind_errors=0)
    monkeypatch.setattr(mitm.socket, "socket", factory)

    mitm._wait_port_released(8080, timeout=5.0)

    captured = capsys.readouterr()
    assert captured.err == ""


@pytest.mark.p1
@allure.id("AT-BUG-043-stop-does-not-raise-on-occupied-port")
@allure.title("Проба: stop() с занятым портом (после смерти своего процесса) НЕ бросает исключение -- инвариант teardown-цепочки conftest.py (attempt 2, блокер 1) (device-free)")
def test_stop_does_not_raise_when_port_stays_occupied(monkeypatch, _no_real_sleep):
    class _DeadFakeProc:
        returncode = 0

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    mitm._proc = _DeadFakeProc()
    monkeypatch.setattr(mitm, "_PORT_RELEASE_TIMEOUT", 0.05)  # timeout=None резолвится ВНУТРИ тела -- monkeypatch виден
    factory = _fake_bind_socket_factory(bind_errors=10**6)  # порт никогда не освобождается
    monkeypatch.setattr(mitm.socket, "socket", factory)

    mitm.stop()  # не должно бросить

    assert mitm._proc is None  # stop() всё равно сбрасывает хэндл на выходе


# --- _spawn_and_wait_listening ---


class _FakeProc:
    """Фейк `subprocess.Popen`-хэндла: `dies` — умирает ли этот процесс
    немедленно (конфликт bind), не дожидаясь `_wait_listening`-поллинга."""

    def __init__(self, dies: bool, returncode: int = 1):
        self.returncode = returncode if dies else None
        self._dies = dies

    def poll(self):
        return self.returncode


def _fake_popen_factory(behaviors: list[bool]):
    """behaviors[i] — умирает ли i-й по счёту (0-based) Popen-вызов
    немедленно. Возвращает фабрику + мутируемое состояние (счётчик
    попыток, последний созданный `_FakeProc`)."""
    state = {"attempt": 0, "last_proc": None}

    def factory(args, *a, **kw):
        idx = state["attempt"]
        dies = behaviors[idx] if idx < len(behaviors) else behaviors[-1]
        proc = _FakeProc(dies=dies)
        state["attempt"] += 1
        state["last_proc"] = proc
        return proc

    return factory, state


class _FakeConnectSocket:
    """Фейк сокета для connect_ex-поллинга внутри `_spawn_and_wait_listening`.
    `listens_from_attempt` — с какой попытки (1-based, по числу уже
    сделанных `Popen`) сокет начинает отвечать «слушается» (connect_ex==0)."""

    def __init__(self, state: dict, listens_from_attempt: int):
        self._state = state
        self._listens_from_attempt = listens_from_attempt

    def settimeout(self, t):
        pass

    def connect_ex(self, addr):
        return 0 if self._state["attempt"] >= self._listens_from_attempt else 111

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-retries-on-bind-conflict")
@allure.title("Проба: _spawn_and_wait_listening() ретраит Popen, когда СВОЙ процесс сразу умирает (конфликт bind), и возвращает proc второй попытки (device-free)")
def test_spawn_retries_when_own_process_dies_immediately(monkeypatch, _no_real_sleep):
    # Given первая попытка Popen -- сразу умирает (конфликт bind, никто не
    # слушает), вторая -- живёт и порт становится connectable
    popen_factory, state = _fake_popen_factory(behaviors=[True, False])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _FakeConnectSocket(state, listens_from_attempt=2),
    )

    proc = mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=1)

    assert state["attempt"] == 2
    assert proc is state["last_proc"]
    assert proc.poll() is None  # вторая попытка жива -- наш процесс


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-no-retry-on-slow-legit-startup")
@allure.title("Проба: _spawn_and_wait_listening() НЕ ретраит, когда процесс жив, но просто не поднял порт за ready_timeout (не гонка bind) (device-free)")
def test_spawn_does_not_retry_on_genuine_slow_startup(monkeypatch, _no_real_sleep):
    # Given единственная попытка Popen: процесс ЖИВ весь ready_timeout, но
    # порт так и не становится connectable -- НЕ конфликт bind (тот роняет
    # процесс почти мгновенно), ретрая быть не должно
    popen_factory, state = _fake_popen_factory(behaviors=[False])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _FakeConnectSocket(state, listens_from_attempt=10**6),
    )

    with pytest.raises(TimeoutError) as exc_info:
        mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=0.05)

    assert state["attempt"] == 1  # ни одного ретрая
    assert "AT-BUG-043" not in str(exc_info.value)  # прежнее поведение, не наш новый диагноз


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-exhausts-retry-budget")
@allure.title("Проба: _spawn_and_wait_listening() исчерпывает бюджет ретраев явной RuntimeError с AT-BUG-043, если конфликт bind не проходит (device-free)")
def test_spawn_raises_after_retry_budget_exhausted(monkeypatch, _no_real_sleep):
    # Given КАЖДАЯ попытка Popen сразу умирает (постоянный конфликт bind);
    # бюджет ретраев сжат, чтобы проба не ждала реальные 10s
    monkeypatch.setattr(mitm, "_START_RETRY_BUDGET", 0.05)
    popen_factory, state = _fake_popen_factory(behaviors=[True])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _FakeConnectSocket(state, listens_from_attempt=10**6),
    )

    with pytest.raises(RuntimeError) as exc_info:
        mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=1)

    message = str(exc_info.value)
    assert "AT-BUG-043" in message
    assert state["attempt"] >= 2  # хотя бы один ретрай состоялся до исчерпания бюджета
    # Attempt 2, блокер 2: последний процесс мёртв -- не оставляем ничейный
    # ЖИВОЙ хэндл (proba критика: "процессов порождено: 1; mitm._proc после
    # отказа: None" -- это было СТАРОЕ поведение бага, здесь проверяем ФИКС)
    assert mitm._proc is None


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-foreign-listener-no-retry")
@allure.title("Проба: _spawn_and_wait_listening() НЕ ретраит и возвращает proc сразу, если порт слушается ЧУЖИМ процессом -- ESC-009 замок ловит это выше (device-free)")
def test_spawn_returns_immediately_on_foreign_listener(monkeypatch, _no_real_sleep):
    # Given СВОЙ процесс сразу умер, НО порт немедленно connectable (чужой
    # слушатель) -- та же ситуация, что живой прецедент ESC-009 сессии
    # 2026-07-30: `_spawn_and_wait_listening` не должен ретраить (нет
    # смысла — порт занят, но раскрытие "свой/чужой" остаётся за
    # `_assert_own_listener()` вызывающего кода, семантика не тронута)
    popen_factory, state = _fake_popen_factory(behaviors=[True])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _FakeConnectSocket(state, listens_from_attempt=1),
    )

    proc = mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=1)

    assert state["attempt"] == 1  # НИ одного ретрая
    assert proc.poll() is not None  # свой процесс мёртв -- _assert_own_listener() поймает это выше


# --- _spawn_and_wait_listening: владение хэндлом (attempt 2, блокер 2) ---


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-owns-proc-before-listening-confirmed")
@allure.title("Проба: _spawn_and_wait_listening() присваивает _proc СРАЗУ после Popen -- до подтверждения слушателя (attempt 2, критик-вход, блокер 2) (device-free)")
def test_spawn_owns_proc_before_listening_confirmed(monkeypatch, _no_real_sleep):
    # Given единственный Popen, живой сразу -- наблюдаем состояние mitm._proc
    # В МОМЕНТ первого connect_ex-поллинга (до `listening=True`), а не после
    # возврата функции -- старая семантика ("присвоить только на успешный
    # return") оставила бы mitm._proc None здесь
    popen_factory, state = _fake_popen_factory(behaviors=[False])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    observed = {}

    class _ObservingSocket(_FakeConnectSocket):
        def connect_ex(self, addr):
            if "proc_at_first_poll" not in observed:
                observed["proc_at_first_poll"] = mitm._proc
            return super().connect_ex(addr)

    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _ObservingSocket(state, listens_from_attempt=1),
    )

    proc = mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=1)

    assert observed["proc_at_first_poll"] is proc  # владение -- ДО connect_ex, не после return
    assert mitm._proc is proc


@pytest.mark.p1
@allure.id("AT-BUG-043-spawn-no-orphan-on-slow-legit-startup")
@allure.title("Проба: _spawn_and_wait_listening() оставляет _proc указывающим на живой процесс на ветке 'медленный легитимный старт' -- не сирота, stop() сможет его остановить (attempt 2, блокер 2) (device-free)")
def test_spawn_leaves_proc_owned_when_process_alive_but_not_listening(monkeypatch, _no_real_sleep):
    # Given процесс ЖИВ весь ready_timeout, порт так и не стал connectable
    # (не гонка bind -- прежнее поведение TimeoutError без ретрая). ДО
    # attempt 2 вызывающий код (`start_replay`) присваивал `_proc` только
    # на успешный ВОЗВРАТ этой функции -- на этой ветке она БРОСАЕТ, и
    # `_proc` оставался None, хотя процесс живой (сирота, регрессия против
    # до-фиксового кода -- bugs/AT-BUG-025.md:206-213)
    popen_factory, state = _fake_popen_factory(behaviors=[False])
    monkeypatch.setattr(mitm.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(
        mitm.socket, "socket",
        lambda *a, **kw: _FakeConnectSocket(state, listens_from_attempt=10**6),
    )

    with pytest.raises(TimeoutError):
        mitm._spawn_and_wait_listening(["fake-mitmdump"], ready_timeout=0.05)

    assert mitm._proc is state["last_proc"]
    assert mitm._proc.poll() is None  # живой -- НЕ сирота, stop() сможет его остановить
