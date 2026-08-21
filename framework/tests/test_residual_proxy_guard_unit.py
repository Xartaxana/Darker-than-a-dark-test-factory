"""Device-free юнит-проба fail-safe снятия ОСТАТОЧНОГО device-прокси
(AT-BUG-064, кандидат фикса (а)).

Доказывает, что `framework/core/mitm.py::get_device_proxy()`/
`ensure_no_residual_proxy()`:
- читают/парсят текущее значение `global http_proxy` устройства;
- на "чистом" устройстве (`"null"`/`":0"`/пусто) НИЧЕГО не снимают (счастливый
  путь — ноль лишних adb-записей) и возвращают `None`;
- на ОСТАТОЧНОМ прокси (например, `10.0.2.2:8080`, переживший snapshot-boot
  эмулятора после аварийного завершения предыдущей сессии) снимают его
  (`clear_device_proxy()`, вторая adb-команда `put ... :0`) и возвращают
  СТАРОЕ значение — вызывающий код (`conftest.py::_ensure_app_installed`)
  логирует находку;
- зависший `adb shell settings get` даёт явную `TimeoutError` с тегом
  AT-BUG-064, не голый `subprocess.TimeoutExpired`.

Плюс: `conftest.py::_ensure_no_residual_device_proxy()` (чистая функция,
вынесенная из fixture-тела `_ensure_app_installed` — pytest 9 запрещает
прямой вызов декорированной fixture-функции, тот же приём, что
`_ensure_replay_ca`/`_ensure_upstream_fast`) действительно зовёт
`mitm.ensure_no_residual_proxy()` и предупреждает `warnings.warn(...)`, когда
находит остаток — не молча.

Тот же приём монки-патча `subprocess.run`, что `test_mitm_proxy_reachable_unit.py`
(AT-BUG-017)/`test_replay_ca_check_unit.py` (AT-BUG-011). Локально
переопределяет РЕАЛЬНУЮ session-scoped autouse-фикстуру `_ensure_app_installed`
из `conftest.py` no-op'ом (та иначе дёрнула бы настоящий adb при сборе), как и
остальные device-free пробы этого пакета — реальный adb не трогается ни в
одном тесте этого модуля.

B2 (критик-вход rework attempt 2, хвост файла): дополнительный блок проб
доказывает, что `conftest.py::pytest_runtest_setup()` перевзводит проверку
остаточного прокси ПОСЛЕ device-liveness recovery (твин `_reset_ca_check`,
AT-BUG-026 F4) — без этого ветка session-scoped проверки была недостижима
ровно для сценария заголовка бага (прокси переживает ПЕРЕЗАПУСК эмулятора).

F2 (критик-вход на AT-BUG-064, батч мелочей 0812): `get_device_proxy()`
больше не молчит на ненулевом `returncode` adb (offline/unauthorized
устройство) — раньше пустой `stdout` такого сбоя читался как «прокси
нет» (fail-open, класс permission-hygiene п.6 CLAUDE.md). Теперь варнит в
stderr и возвращает `None`, отличимый от «чисто» (`""`/`"null"`/`":0"`);
два теста ниже покрывают саму ветку и её границу (`returncode == 0` —
штатный путь, не ошибка).
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.core import mitm
from framework.tests import conftest as _conftest


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет РЕАЛЬНУЮ session-scoped autouse-фикстуру `conftest.py`
    (та самая, что мы тестируем) — эта проба чисто локальная, устройство не
    трогаем при автоматическом инстанцировании pytest'ом. Тесты ниже зовут
    `_conftest._ensure_app_installed()` НАПРЯМУЮ как функцию (независимый
    генератор, в обход этого override'а) — тот же приём, что
    `test_replay_ca_check_unit.py` для `_conftest._ensure_replay_ca()`."""
    yield


def _fake_run_get(value: str):
    """Фейк `subprocess.run` для `adb shell settings get global http_proxy`."""

    def _run(args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=value, stderr="")

    return _run


@pytest.mark.p2
@allure.id("AT-BUG-064-get-device-proxy-parses-output")
@allure.title("Проба: get_device_proxy() возвращает обрезанный вывод adb (device-free)")
def test_get_device_proxy_strips_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run_get("10.0.2.2:8080\n"))

    assert mitm.get_device_proxy() == "10.0.2.2:8080"


@pytest.mark.p2
@allure.id("AT-BUG-064-get-device-proxy-wraps-timeout")
@allure.title("Проба: get_device_proxy() падает явной TimeoutError с тегом AT-BUG-064, не голым TimeoutExpired (device-free)")
def test_get_device_proxy_wraps_timeout_expired(monkeypatch):
    def _hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout"))

    monkeypatch.setattr(subprocess, "run", _hang)

    with pytest.raises(TimeoutError) as exc_info:
        mitm.get_device_proxy()

    assert "AT-BUG-064" in str(exc_info.value)


@pytest.mark.p1
@allure.id("AT-BUG-064-get-device-proxy-nonzero-returncode-returns-none")
@allure.title("Проба F2: get_device_proxy() при returncode != 0 не бросает, возвращает None (отличимо от \"чисто\"), варнит в stderr (device-free)")
def test_get_device_proxy_nonzero_returncode_returns_none(monkeypatch, capsys):
    def _run(args, **kw):
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="error: device offline"
        )

    monkeypatch.setattr(subprocess, "run", _run)

    # When adb сбоит (offline/unauthorized) -- returncode != 0, пустой stdout
    result = mitm.get_device_proxy()

    # Then НЕ бросает, возвращает None (отличимо от "" -- "чисто") и варнит
    assert result is None
    captured = capsys.readouterr()
    assert "AT-BUG-064" in captured.err
    assert "device offline" in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-064-get-device-proxy-returncode-boundary-zero-is-success")
@allure.title("Проба F2 (граница): returncode == 0 -- это НЕ ошибочная ветка, читает stdout как обычно (device-free)")
def test_get_device_proxy_returncode_zero_is_not_error_branch(monkeypatch, capsys):
    def _run(args, **kw):
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="  :0\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)

    result = mitm.get_device_proxy()

    # Then граница returncode == 0 остаётся штатным путём -- значение читается,
    # предупреждения F2 нет
    assert result == ":0"
    captured = capsys.readouterr()
    assert "AT-BUG-064" not in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-064-ensure-no-residual-proxy-clean-device-noop")
@allure.title("Проба: ensure_no_residual_proxy() ничего не снимает на чистом устройстве (device-free)")
@pytest.mark.parametrize("clean_value", ["null", ":0", "", "  null  \n"])
def test_ensure_no_residual_proxy_noop_when_clean(monkeypatch, clean_value):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=clean_value, stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    result = mitm.ensure_no_residual_proxy()

    # Then ничего не найдено и НИ ОДНОЙ команды "put" не ушло (только чтение)
    assert result is None
    assert len(calls) == 1
    assert calls[0][5] == "get"


@pytest.mark.p1
@allure.id("AT-BUG-064-ensure-no-residual-proxy-clears-stale-proxy")
@allure.title("Проба: ensure_no_residual_proxy() снимает остаточный прокси и возвращает старое значение (device-free)")
def test_ensure_no_residual_proxy_clears_stale_value(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        if args[5] == "get":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="10.0.2.2:8080\n", stderr="")
        # settings put global http_proxy :0
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    # When устройство несёт остаточный прокси от предыдущей аварийно
    # завершившейся сессии (сценарий AT-BUG-064)
    result = mitm.ensure_no_residual_proxy()

    # Then функция вернула СТАРОЕ значение и реально сняла прокси (get + put)
    assert result == "10.0.2.2:8080"
    assert len(calls) == 2
    assert calls[0][5] == "get"
    assert calls[1][5] == "put"
    assert calls[1][-1] == ":0"


@pytest.mark.p1
@allure.id("AT-BUG-064-ensure-app-installed-warns-on-stale-proxy")
@allure.title("Проба: conftest._ensure_no_residual_device_proxy() предупреждает через mitm.ensure_no_residual_proxy, не молча (device-free)")
def test_ensure_no_residual_device_proxy_warns_on_stale_proxy(monkeypatch):
    # Given mitm.ensure_no_residual_proxy() нашёл остаток (симулируем прямо на
    # уровне conftest — сама функция mitm уже доказана отдельными пробами выше).
    # _ensure_app_installed сама — декорированная fixture-функция (pytest 9
    # запрещает вызывать её напрямую), поэтому тестируем вынесенный из неё
    # чистый хелпер напрямую (тот же приём, что _ensure_replay_ca/
    # _ensure_upstream_fast — см. их докстринги).
    monkeypatch.setattr(mitm, "ensure_no_residual_proxy", lambda: "10.0.2.2:8080")

    # When/Then предупреждает явным warnings.warn с тегом бага, не молчит
    with pytest.warns(UserWarning, match="AT-BUG-064"):
        _conftest._ensure_no_residual_device_proxy()


@pytest.mark.p1
@allure.id("AT-BUG-064-ensure-app-installed-silent-on-clean-device")
@allure.title("Проба: conftest._ensure_no_residual_device_proxy() не предупреждает, когда устройство уже чистое (device-free)")
def test_ensure_no_residual_device_proxy_silent_when_clean(monkeypatch, recwarn):
    monkeypatch.setattr(mitm, "ensure_no_residual_proxy", lambda: None)

    _conftest._ensure_no_residual_device_proxy()

    # Then ни одного предупреждения про AT-BUG-064 не выпущено (счастливый путь)
    assert not any("AT-BUG-064" in str(w.message) for w in recwarn.list)


# --- B2 (критик-вход rework attempt 2): проверка остаточного прокси
# перевзводится ПОСЛЕ device-liveness recovery, твин уже существующего
# паттерна `_reset_ca_check()` в `pytest_runtest_setup()` (conftest.py).
# Без этого фикса сценарий из ЗАГОЛОВКА бага (прокси переживает ПЕРЕЗАПУСК
# эмулятора) оставался недостижим для session-scoped проверки (а) attempt 1
# ИМЕННО на пути device-liveness recovery -- эмулятор перезапускается через
# тот же snapshot-boot `tasks.ps1::Start-Emulator`, но session-scoped
# `_ensure_app_installed` инстанцируется РОВНО РАЗ на весь прогон и уже
# отработала до этого recovery. Тот же приём вызова хука напрямую с
# фейковым `item` (duck-typing -- хуку нужен только `.fixturenames`), что
# `test_device_liveness_guard_unit.py` (AT-BUG-026 B1, владеет тем файлом
# параллельный AT-BUG-063 rework -- пробы ниже НЕ дублируют его файл,
# только вызывают тот же публичный хук `conftest.pytest_runtest_setup`).


class _FakeItem:
    def __init__(self, fixturenames: list[str]) -> None:
        self.fixturenames = fixturenames


@pytest.mark.p1
@allure.id("AT-BUG-064-hook-rechecks-residual-proxy-after-recovery")
@allure.title("Проба B2: pytest_runtest_setup повторно зовёт _ensure_no_residual_device_proxy() после device-liveness recovery -- твин _reset_ca_check (device-free)")
def test_hook_rechecks_residual_proxy_after_recovery(monkeypatch):
    monkeypatch.setattr(_conftest, "_pending_recovery_warning", None)
    recovered_msg = "AT-BUG-026 device-liveness guard: устройство восстановлено 1/2"
    monkeypatch.setattr(
        _conftest._DEVICE_GUARD, "ensure_ready", lambda: recovered_msg,
    )
    # _reset_ca_check не под пробой здесь (уже покрыт AT-BUG-026 B1/F4 в
    # своём файле) -- нейтрализуем, чтобы не трогать реальный module-level
    # `_ca_checked` этой pytest-сессии.
    monkeypatch.setattr(_conftest, "_reset_ca_check", lambda: None)
    proxy_check_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_no_residual_device_proxy",
        lambda: proxy_check_calls.append(1),
    )

    # Сигнатура реального теста-крашера -- test_x(clean_app, replay, driver):
    # `driver` перечислен ПОСЛЕДНИМ, порядок не влияет на признак "тест
    # трогает устройство" (та же гарантия, что B1).
    _conftest.pytest_runtest_setup(_FakeItem(["clean_app", "replay", "driver"]))

    # Then B2: recovery -- ровно сценарий заголовка AT-BUG-064 (эмулятор
    # перезапущен) -- обязан перевзвести проверку остаточного прокси.
    assert proxy_check_calls == [1]


@pytest.mark.p1
@allure.id("AT-BUG-064-hook-no-residual-proxy-recheck-without-recovery")
@allure.title("Проба B2: pytest_runtest_setup НЕ перевзводит проверку остаточного прокси, если recovery не произошёл (device-free)")
def test_hook_skips_residual_proxy_recheck_when_no_recovery(monkeypatch):
    monkeypatch.setattr(_conftest, "_pending_recovery_warning", None)
    monkeypatch.setattr(_conftest._DEVICE_GUARD, "ensure_ready", lambda: None)
    proxy_check_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_no_residual_device_proxy",
        lambda: proxy_check_calls.append(1),
    )

    _conftest.pytest_runtest_setup(_FakeItem(["driver"]))

    # Then устройство было живо (recovery не потребовался) -- проверка
    # остаточного прокси остаётся на своей единственной session-scoped
    # точке входа, повторно НЕ вызывается на каждом тесте.
    assert proxy_check_calls == []


@pytest.mark.p1
@allure.id("AT-BUG-064-hook-no-residual-proxy-recheck-without-driver-fixture")
@allure.title("Проба B2: pytest_runtest_setup НЕ трогает проверку остаточного прокси, если 'driver' не запрошен тестом (device-free)")
def test_hook_skips_residual_proxy_recheck_for_device_free_test(monkeypatch):
    ensure_calls: list = []
    monkeypatch.setattr(
        _conftest._DEVICE_GUARD, "ensure_ready",
        lambda: ensure_calls.append(1) or None,
    )
    proxy_check_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_no_residual_device_proxy",
        lambda: proxy_check_calls.append(1),
    )

    _conftest.pytest_runtest_setup(_FakeItem(["tmp_path", "monkeypatch"]))

    assert ensure_calls == []
    assert proxy_check_calls == []
