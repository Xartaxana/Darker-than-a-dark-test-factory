"""Device-free юнит-проба bounded-ретрая `app_steps.
wait_tabs_persisted_after_cold_start_deep_link` (AT-BUG-087, критик-вход
2026-08-20, блокер Б7) — TC-135 покрыта живым устройством, но сама логика
различения «гонка AM remove-task» / «неизвестная причина смерти процесса»
(критик-блокеры Б5/Б6, тот же ход) заслуживает device-free пина по
named-конвенции этого пакета (`test_navigate_transient_race_unit.py`,
`test_in_webview_transient_race_unit.py`, `test_device_liveness_guard_unit.py`
— bounded-ретрай choke point получает свой `*_unit.py`, monkeypatch вместо
реального устройства).

Пины (докстринг шага `app_steps.py` — полный разбор):
1. Таймаут + `pidof_app() -> None` + логкэт несёт `killedByAm=true` -> ровно
   ОДИН прозрачный ретрай: `open_deep_link` вызван 2 раза (исходный +
   ретрай), `wait_tabs_persisted` вызван 2 раза, исключение НЕ долетает до
   вызывающего кода.
2. Таймаут + `pidof_app() -> "1234"` (процесс ЖИВ) -> `TimeoutError`
   пробрасывается наружу БЕЗ ретрая (`open_deep_link` вызван РОВНО 1 раз) —
   анти-маскировочный гвард: живой процесс с непроперсистенным состоянием —
   потенциальная РЕГРЕССИЯ приложения, не гонка AM.
3. Таймаут + `pidof_app() -> None` + логкэт БЕЗ `killedByAm=true` ->
   `TimeoutError` пробрасывается наружу БЕЗ ретрая (`open_deep_link` вызван
   РОВНО 1 раз) — критик-блокер Б5: мёртвый процесс без доказанной
   принадлежности гонке AM (краш приложения ИЛИ отвал adb) не маскируется
   слепым ретраем.
4. Таймаут + `pidof_app() -> None` + `killedByAm=true` в логкэте ОБА раза
   (ретрай тоже упал по той же причине) -> итоговый `TimeoutError`
   пробрасывается наружу — ретрай bounded (ОДИН раз), не бесконечный цикл.
5. Happy path (БЕЗ таймаута) -> `open_deep_link` вызван 1 раз,
   `wait_tabs_persisted` вызван 1 раз, `adb.pidof_app`/логкэт-метод НЕ
   вызывались вовсе (ветка ретрая структурно не заходит на здоровом
   прогоне).

Монки-патч module-level функций `framework.steps.app_steps.open_deep_link`/
`.wait_tabs_persisted` (не `adb.shell` напрямую — логкэт читается через
`adb.shell`, монки-патчится там же) и `framework.core.adb.pidof_app` — тот
же приём, что `test_device_liveness_guard_unit.py` монки-патчит
`adb.device_present`/`adb.is_installed`. НЕ требует устройства/эмулятора."""
from __future__ import annotations

import allure
import pytest

from framework.core import adb
from framework.steps import app_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогает (тот же приём, что остальные
    device-free пробы этого пакета)."""
    yield


def _make_wait_tabs_persisted(fail_times: int):
    """Фейковый `wait_tabs_persisted`: первые `fail_times` вызовов кидают
    `TimeoutError`, остальные — успевают (no-op)."""
    calls = {"n": 0}

    def _fake(sentinel: str, timeout: int = 10) -> None:
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise TimeoutError(f"вкладки с сентинелом {sentinel!r} не появились")

    _fake.calls = calls
    return _fake


@pytest.mark.p1
@allure.id("AT-BUG-087-cold-start-am-race-retries-when-killed-by-am")
@allure.title(
    "Проба 1: таймаут + pidof=None + killedByAm=true в логкэте -> ровно один "
    "прозрачный ретрай, исключение не долетает (device-free)"
)
def test_retries_once_when_pidof_none_and_am_kill_marker_present(monkeypatch):
    open_deep_link_calls: list = []
    monkeypatch.setattr(app_steps, "open_deep_link", lambda url: open_deep_link_calls.append(url))

    fake_wait = _make_wait_tabs_persisted(fail_times=1)
    monkeypatch.setattr(app_steps, "wait_tabs_persisted", fake_wait)

    monkeypatch.setattr(adb, "pidof_app", lambda: None)

    shell_calls: list = []

    def _fake_shell(cmd: str, timeout=None):
        shell_calls.append(cmd)
        return "... Zygote: Forked child process 4242\n" \
               "... ActivityManager: ProcessRecord{...} start not valid, " \
               "killing pid=4242, killedByAm=true\n"

    monkeypatch.setattr(adb, "shell", _fake_shell)

    # When/Then: не поднимает исключение наружу
    app_steps.wait_tabs_persisted_after_cold_start_deep_link("https://example/1", "sentinel", timeout=20)

    assert open_deep_link_calls == ["https://example/1", "https://example/1"], (
        "open_deep_link обязан быть вызван дважды: исходный + один ретрай"
    )
    assert fake_wait.calls["n"] == 2, "wait_tabs_persisted обязан быть вызван дважды"
    assert len(shell_calls) == 1, "логкэт снимается ровно один раз (перед ретраем)"


@pytest.mark.p1
@allure.id("AT-BUG-087-cold-start-no-retry-when-process-alive")
@allure.title(
    "Проба 2 (анти-маскировка): таймаут + pidof вернул живой pid -> TimeoutError "
    "пробрасывается БЕЗ ретрая — потенциальная регрессия приложения не маскируется (device-free)"
)
def test_no_retry_when_process_alive_after_timeout(monkeypatch):
    open_deep_link_calls: list = []
    monkeypatch.setattr(app_steps, "open_deep_link", lambda url: open_deep_link_calls.append(url))

    fake_wait = _make_wait_tabs_persisted(fail_times=99)
    monkeypatch.setattr(app_steps, "wait_tabs_persisted", fake_wait)

    monkeypatch.setattr(adb, "pidof_app", lambda: "1234")

    shell_calls: list = []
    monkeypatch.setattr(adb, "shell", lambda cmd, timeout=None: shell_calls.append(cmd) or "")

    with pytest.raises(TimeoutError):
        app_steps.wait_tabs_persisted_after_cold_start_deep_link("https://example/2", "sentinel", timeout=20)

    assert open_deep_link_calls == ["https://example/2"], "ретрая быть не должно -- вызван ровно 1 раз"
    assert fake_wait.calls["n"] == 1
    assert shell_calls == [], "логкэт не должен сниматься -- pidof уже доказал 'процесс жив', не гонка AM"


@pytest.mark.p1
@allure.id("AT-BUG-087-cold-start-no-retry-when-am-kill-marker-absent")
@allure.title(
    "Проба 3 (критик-блокер Б5): таймаут + pidof=None, но killedByAm=true В ЛОГКЭТЕ ОТСУТСТВУЕТ -> "
    "TimeoutError пробрасывается БЕЗ ретрая — неизвестная причина смерти процесса не маскируется (device-free)"
)
def test_no_retry_when_process_dead_but_no_am_kill_marker_in_logcat(monkeypatch):
    open_deep_link_calls: list = []
    monkeypatch.setattr(app_steps, "open_deep_link", lambda url: open_deep_link_calls.append(url))

    fake_wait = _make_wait_tabs_persisted(fail_times=99)
    monkeypatch.setattr(app_steps, "wait_tabs_persisted", fake_wait)

    monkeypatch.setattr(adb, "pidof_app", lambda: None)

    shell_calls: list = []

    def _fake_shell(cmd: str, timeout=None):
        shell_calls.append(cmd)
        # Процесс мёртв, но логкэт НЕ несёт killedByAm=true -- например,
        # реальный краш приложения (FATAL EXCEPTION) или отвал adb-транспорта.
        return "... FATAL EXCEPTION: main\n... Process: com.example.ao3_wrapper, PID: 4242\n"

    monkeypatch.setattr(adb, "shell", _fake_shell)

    with pytest.raises(TimeoutError):
        app_steps.wait_tabs_persisted_after_cold_start_deep_link("https://example/3", "sentinel", timeout=20)

    assert open_deep_link_calls == ["https://example/3"], "ретрая быть не должно -- вызван ровно 1 раз"
    assert fake_wait.calls["n"] == 1
    assert len(shell_calls) == 1, "логкэт обязан быть снят ровно один раз для попытки диагностики"


@pytest.mark.p1
@allure.id("AT-BUG-087-cold-start-retry-is-bounded")
@allure.title(
    "Проба 4: ретрай тоже упал по killedByAm=true -> итоговый TimeoutError пробрасывается "
    "наружу — ретрай bounded (один раз), не бесконечный цикл (device-free)"
)
def test_retry_is_bounded_reraises_after_second_am_kill(monkeypatch):
    open_deep_link_calls: list = []
    monkeypatch.setattr(app_steps, "open_deep_link", lambda url: open_deep_link_calls.append(url))

    # Оба вызова wait_tabs_persisted (исходный + ретрай) падают таймаутом.
    fake_wait = _make_wait_tabs_persisted(fail_times=99)
    monkeypatch.setattr(app_steps, "wait_tabs_persisted", fake_wait)

    monkeypatch.setattr(adb, "pidof_app", lambda: None)

    shell_calls: list = []

    def _fake_shell(cmd: str, timeout=None):
        shell_calls.append(cmd)
        return "... killedByAm=true\n"

    monkeypatch.setattr(adb, "shell", _fake_shell)

    with pytest.raises(TimeoutError):
        app_steps.wait_tabs_persisted_after_cold_start_deep_link("https://example/4", "sentinel", timeout=20)

    assert open_deep_link_calls == ["https://example/4", "https://example/4"], (
        "ровно исходный + один ретрай, БЕЗ второго ретрая -- bounded"
    )
    assert fake_wait.calls["n"] == 2
    # Логкэт снимается только один раз -- на самом ретрае уже НЕ ловим таймаут
    # повторно try/except'ом (второй TimeoutError от wait_tabs_persisted внутри
    # ретрай-ветки не перехватывается функцией, летит наружу как есть).
    assert len(shell_calls) == 1


@pytest.mark.p1
@allure.id("AT-BUG-087-cold-start-happy-path-no-diagnostics-touched")
@allure.title(
    "Проба 5 (happy path): без таймаута -- open_deep_link/wait_tabs_persisted вызваны по 1 разу, "
    "pidof_app/логкэт НЕ вызывались вовсе (device-free)"
)
def test_happy_path_does_not_touch_pidof_or_logcat(monkeypatch):
    open_deep_link_calls: list = []
    monkeypatch.setattr(app_steps, "open_deep_link", lambda url: open_deep_link_calls.append(url))

    fake_wait = _make_wait_tabs_persisted(fail_times=0)
    monkeypatch.setattr(app_steps, "wait_tabs_persisted", fake_wait)

    pidof_calls: list = []
    monkeypatch.setattr(adb, "pidof_app", lambda: pidof_calls.append(1) or "9999")

    shell_calls: list = []
    monkeypatch.setattr(adb, "shell", lambda cmd, timeout=None: shell_calls.append(cmd) or "")

    app_steps.wait_tabs_persisted_after_cold_start_deep_link("https://example/5", "sentinel", timeout=20)

    assert open_deep_link_calls == ["https://example/5"]
    assert fake_wait.calls["n"] == 1
    assert pidof_calls == [], "pidof_app не должен вызываться на здоровом прогоне (нет таймаута вовсе)"
    assert shell_calls == [], "логкэт не должен сниматься на здоровом прогоне (нет таймаута вовсе)"
