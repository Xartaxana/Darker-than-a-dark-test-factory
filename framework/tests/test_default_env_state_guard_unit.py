"""Device-free юнит-проба fail-safe снятия ОСТАТОЧНЫХ персистентных
Android-настроек font_scale/night mode (AT-BUG-066, сиблинг AT-BUG-064).

Доказывает, что `framework/core/adb.py`:
- `get_font_scale()`/`get_night_mode()` читают и парсят текущее значение
  соответствующей настройки устройства;
- на "чистом" устройстве (font_scale уже `DEFAULT_FONT_SCALE`/night mode уже
  `DEFAULT_NIGHT_MODE`, либо неразборчиво/`"null"`) `ensure_default_font_
  scale()`/`ensure_default_night_mode()` НИЧЕГО не снимают (счастливый путь —
  ноль лишних adb-записей) и возвращают `None`;
- на ОСТАТОЧНОМ значении (например, `font_scale=1.3`/`night mode=yes`,
  пережившем snapshot-boot эмулятора после аварийного завершения предыдущей
  сессии) сбрасывают его в дефолт (вторая adb-команда `put`/`cmd uimode night
  no`) и возвращают СТАРОЕ значение — вызывающий код (`conftest.py`)
  логирует находку;
- ненулевой `returncode` adb (offline/unauthorized устройство) НЕ читается
  как «дефолт» — явно отличимый `None` + предупреждение в stderr (тот же
  класс, что `mitm.get_device_proxy()` F2 / CLAUDE.md permission-hygiene
  п.6);
- зависший adb даёт явную `TimeoutError` (через уже существующий `adb._run()`
  AT-BUG-009-паттерн), не голый `subprocess.TimeoutExpired`.

Плюс: `conftest.py::_ensure_default_font_scale()`/`_ensure_default_night_
mode()` (чистые функции, тот же приём, что `_ensure_no_residual_device_
proxy` — pytest 9 запрещает прямой вызов декорированной fixture-функции)
действительно зовут `adb.ensure_default_font_scale()`/`adb.ensure_default_
night_mode()` и предупреждают `warnings.warn(...)`, когда находят остаток —
не молча.

Тот же приём монки-патча `subprocess.run`, что `test_residual_proxy_guard_
unit.py` (AT-BUG-064)/`test_mitm_proxy_reachable_unit.py` (AT-BUG-017).
Локально переопределяет РЕАЛЬНУЮ session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` no-op'ом (та иначе дёрнула бы
настоящий adb при сборе), как и остальные device-free пробы этого пакета —
реальный adb не трогается ни в одном тесте этого модуля.

Хвост файла: дополнительный блок проб доказывает, что `conftest.py::
pytest_runtest_setup()` перевзводит ОБЕ проверки ПОСЛЕ device-liveness
recovery (твин `_ensure_no_residual_device_proxy`/`_reset_ca_check`,
AT-BUG-026 F4) — без этого ветка session-scoped проверки была бы
недостижима ровно для сценария заголовка `AT-BUG-066` (остаток переживает
ПЕРЕЗАПУСК эмулятора).

Живой замер (emulator-5554, 2026-08-14, см. `bugs/AT-BUG-066.md`
«Обсуждение»): `adb shell cmd uimode night` (без аргумента) печатает
`Night mode: no`/`Night mode: yes`/`Night mode: auto` — читаемый read-back,
предпочтённый над `settings get secure ui_night_mode` (голое число 0/1/2,
раскладка которого не была полностью верифицирована).
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.core import adb
from framework.tests import conftest as _conftest


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет РЕАЛЬНУЮ session-scoped autouse-фикстуру `conftest.py`
    (та самая, что мы тестируем) — эта проба чисто локальная, устройство не
    трогаем при автоматическом инстанцировании pytest'ом. Тесты ниже зовут
    `_conftest._ensure_default_font_scale()`/`_ensure_default_night_mode()`
    НАПРЯМУЮ как функции (независимые генераторы, в обход этого override'а)
    — тот же приём, что `test_residual_proxy_guard_unit.py` для
    `_conftest._ensure_no_residual_device_proxy()`."""
    yield


def _fake_run(stdout: str, returncode: int = 0, stderr: str = ""):
    """Фейк `subprocess.run` — игнорирует конкретную shell-команду, отдаёт
    фиксированный ответ (аналог `_fake_run_get` из
    `test_residual_proxy_guard_unit.py`)."""

    def _run(args, **kw):
        return subprocess.CompletedProcess(
            args=args, returncode=returncode, stdout=stdout, stderr=stderr
        )

    return _run


# --- get_font_scale() / ensure_default_font_scale() ---


@pytest.mark.p2
@allure.id("AT-BUG-066-get-font-scale-parses-output")
@allure.title("Проба: get_font_scale() возвращает обрезанный вывод adb (device-free)")
def test_get_font_scale_strips_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("1.3\n"))

    assert adb.get_font_scale() == "1.3"


@pytest.mark.p2
@allure.id("AT-BUG-066-get-font-scale-wraps-timeout")
@allure.title("Проба: get_font_scale() падает явной TimeoutError (через adb._run, AT-BUG-009), не голым TimeoutExpired (device-free)")
def test_get_font_scale_wraps_timeout_expired(monkeypatch):
    def _hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout"))

    monkeypatch.setattr(subprocess, "run", _hang)

    with pytest.raises(TimeoutError) as exc_info:
        adb.get_font_scale()

    assert "AT-BUG-009" in str(exc_info.value)


@pytest.mark.p1
@allure.id("AT-BUG-066-get-font-scale-nonzero-returncode-returns-none")
@allure.title("Проба: get_font_scale() при returncode != 0 не бросает, возвращает None (отличимо от \"дефолт\"), варнит в stderr (device-free)")
def test_get_font_scale_nonzero_returncode_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("", returncode=1, stderr="error: device offline"),
    )

    result = adb.get_font_scale()

    assert result is None
    captured = capsys.readouterr()
    assert "AT-BUG-066" in captured.err
    assert "device offline" in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-066-get-font-scale-returncode-boundary-zero-is-success")
@allure.title("Проба (граница): returncode == 0 -- это НЕ ошибочная ветка, читает stdout как обычно (device-free)")
def test_get_font_scale_returncode_zero_is_not_error_branch(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_run("  1.0\n"))

    result = adb.get_font_scale()

    assert result == "1.0"
    captured = capsys.readouterr()
    assert "AT-BUG-066" not in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-font-scale-clean-device-noop")
@allure.title("Проба: ensure_default_font_scale() ничего не снимает, когда уже дефолт/пусто/null (device-free)")
@pytest.mark.parametrize("clean_value", ["1.0", "null", "", "  1.0  \n"])
def test_ensure_default_font_scale_noop_when_clean(monkeypatch, clean_value):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=clean_value, stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    result = adb.ensure_default_font_scale()

    # Then ничего не найдено и НИ ОДНОЙ команды "put" не ушло (только чтение)
    assert result is None
    assert len(calls) == 1
    assert "get" in calls[0][-1]


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-font-scale-unparseable-noop")
@allure.title("Проба: ensure_default_font_scale() не трогает неразборчивое непустое значение (device-free)")
def test_ensure_default_font_scale_noop_when_unparseable(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="weird-value", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    result = adb.ensure_default_font_scale()

    assert result is None
    assert len(calls) == 1  # только чтение, put не ушёл


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-font-scale-clears-stale-value")
@allure.title("Проба: ensure_default_font_scale() снимает остаточный масштаб и возвращает старое значение (device-free)")
def test_ensure_default_font_scale_clears_stale_value(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        cmd = args[-1]
        if "get" in cmd:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="1.3\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    # When устройство несёт остаточный увеличенный шрифт от предыдущей
    # аварийно завершившейся сессии (сценарий AT-BUG-066)
    result = adb.ensure_default_font_scale()

    # Then функция вернула СТАРОЕ значение и реально сбросила масштаб (get + put)
    assert result == "1.3"
    assert len(calls) == 2
    assert "get" in calls[0][-1]
    assert "put" in calls[1][-1]
    assert "1.0" in calls[1][-1]


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-font-scale-adb-failure-noop")
@allure.title("Проба: ensure_default_font_scale() ничего не делает, если get_font_scale() не смог определить значение (device-free)")
def test_ensure_default_font_scale_noop_when_adb_unreadable(monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("", returncode=1, stderr="error: device offline"),
    )

    result = adb.ensure_default_font_scale()

    # Then adb сбойнул (уже залогировано get_font_scale) -- ensure_* не
    # пытается ничего чинить на непрочитанном значении
    assert result is None


# --- get_night_mode() / ensure_default_night_mode() ---


@pytest.mark.p2
@allure.id("AT-BUG-066-get-night-mode-parses-yes")
@allure.title("Проба: get_night_mode() парсит 'Night mode: yes' из живого формата вывода (device-free)")
def test_get_night_mode_parses_yes(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("Night mode: yes\n"))

    assert adb.get_night_mode() == "yes"


@pytest.mark.p2
@allure.id("AT-BUG-066-get-night-mode-parses-no")
@allure.title("Проба: get_night_mode() парсит 'Night mode: no' (device-free)")
def test_get_night_mode_parses_no(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("Night mode: no\n"))

    assert adb.get_night_mode() == "no"


@pytest.mark.p2
@allure.id("AT-BUG-066-get-night-mode-parses-auto")
@allure.title("Проба:get_night_mode() парсит 'Night mode: auto' (device-free)")
def test_get_night_mode_parses_auto(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("Night mode: auto\n"))

    assert adb.get_night_mode() == "auto"


@pytest.mark.p1
@allure.id("AT-BUG-066-get-night-mode-unparseable-output-returns-none")
@allure.title("Проба: get_night_mode() возвращает None на неразборчивом (не 'Night mode: ...') выводе (device-free)")
def test_get_night_mode_unparseable_output_returns_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("garbage output\n"))

    assert adb.get_night_mode() is None


@pytest.mark.p2
@allure.id("AT-BUG-066-get-night-mode-wraps-timeout")
@allure.title("Проба: get_night_mode() падает явной TimeoutError (через adb._run, AT-BUG-009), не голым TimeoutExpired (device-free)")
def test_get_night_mode_wraps_timeout_expired(monkeypatch):
    def _hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout"))

    monkeypatch.setattr(subprocess, "run", _hang)

    with pytest.raises(TimeoutError) as exc_info:
        adb.get_night_mode()

    assert "AT-BUG-009" in str(exc_info.value)


@pytest.mark.p1
@allure.id("AT-BUG-066-get-night-mode-nonzero-returncode-returns-none")
@allure.title("Проба: get_night_mode() при returncode != 0 не бросает, возвращает None, варнит в stderr (device-free)")
def test_get_night_mode_nonzero_returncode_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("", returncode=1, stderr="error: device offline"),
    )

    result = adb.get_night_mode()

    assert result is None
    captured = capsys.readouterr()
    assert "AT-BUG-066" in captured.err
    assert "device offline" in captured.err


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-night-mode-clean-device-noop")
@allure.title("Проба: ensure_default_night_mode() ничего не делает, когда уже 'no' (device-free)")
def test_ensure_default_night_mode_noop_when_clean(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="Night mode: no\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    result = adb.ensure_default_night_mode()

    # Then ничего не найдено и НИ ОДНОЙ команды-переключателя не ушло
    assert result is None
    assert len(calls) == 1
    assert calls[0][-1] == "cmd uimode night"


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-night-mode-clears-stale-yes")
@allure.title("Проба: ensure_default_night_mode() сбрасывает остаточный 'yes' и возвращает старое значение (device-free)")
def test_ensure_default_night_mode_clears_stale_yes(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        cmd = args[-1]
        if cmd == "cmd uimode night":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Night mode: yes\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="Night mode: no\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    # When устройство несёт остаточную тёмную тему от предыдущей аварийно
    # завершившейся сессии (сценарий AT-BUG-066)
    result = adb.ensure_default_night_mode()

    # Then функция вернула СТАРОЕ значение и реально сбросила режим (query + set no)
    assert result == "yes"
    assert len(calls) == 2
    assert calls[0][-1] == "cmd uimode night"
    assert calls[1][-1] == "cmd uimode night no"


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-night-mode-clears-stale-auto")
@allure.title("Проба: ensure_default_night_mode() сбрасывает остаточный 'auto' -- ЛЮБОЙ отличный от дефолта режим (device-free)")
def test_ensure_default_night_mode_clears_stale_auto(monkeypatch):
    calls: list = []

    def _run(args, **kw):
        calls.append(args)
        cmd = args[-1]
        if cmd == "cmd uimode night":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Night mode: auto\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    result = adb.ensure_default_night_mode()

    assert result == "auto"
    assert calls[1][-1] == "cmd uimode night no"


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-default-night-mode-adb-failure-noop")
@allure.title("Проба: ensure_default_night_mode() ничего не делает, если get_night_mode() не смог определить значение (device-free)")
def test_ensure_default_night_mode_noop_when_adb_unreadable(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("", returncode=1, stderr="error: device offline"),
    )

    result = adb.ensure_default_night_mode()

    assert result is None


# --- conftest._ensure_default_font_scale() / _ensure_default_night_mode() ---


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-app-installed-warns-on-stale-font-scale")
@allure.title("Проба: conftest._ensure_default_font_scale() предупреждает через adb.ensure_default_font_scale, не молча (device-free)")
def test_ensure_default_font_scale_conftest_warns_on_stale_value(monkeypatch):
    # _ensure_app_installed сама -- декорированная fixture-функция (pytest 9
    # запрещает вызывать её напрямую), поэтому тестируем вынесенный из неё
    # чистый хелпер напрямую (тот же приём, что _ensure_no_residual_device_proxy).
    monkeypatch.setattr(adb, "ensure_default_font_scale", lambda: "1.3")

    with pytest.warns(UserWarning, match="AT-BUG-066"):
        _conftest._ensure_default_font_scale()


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-app-installed-silent-on-clean-font-scale")
@allure.title("Проба: conftest._ensure_default_font_scale() не предупреждает, когда устройство уже дефолтное (device-free)")
def test_ensure_default_font_scale_conftest_silent_when_clean(monkeypatch, recwarn):
    monkeypatch.setattr(adb, "ensure_default_font_scale", lambda: None)

    _conftest._ensure_default_font_scale()

    assert not any("AT-BUG-066" in str(w.message) for w in recwarn.list)


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-app-installed-warns-on-stale-night-mode")
@allure.title("Проба: conftest._ensure_default_night_mode() предупреждает через adb.ensure_default_night_mode, не молча (device-free)")
def test_ensure_default_night_mode_conftest_warns_on_stale_value(monkeypatch):
    monkeypatch.setattr(adb, "ensure_default_night_mode", lambda: "yes")

    with pytest.warns(UserWarning, match="AT-BUG-066"):
        _conftest._ensure_default_night_mode()


@pytest.mark.p1
@allure.id("AT-BUG-066-ensure-app-installed-silent-on-clean-night-mode")
@allure.title("Проба: conftest._ensure_default_night_mode() не предупреждает, когда устройство уже дефолтное (device-free)")
def test_ensure_default_night_mode_conftest_silent_when_clean(monkeypatch, recwarn):
    monkeypatch.setattr(adb, "ensure_default_night_mode", lambda: None)

    _conftest._ensure_default_night_mode()

    assert not any("AT-BUG-066" in str(w.message) for w in recwarn.list)


# --- B2-твин: перевзведение ПОСЛЕ device-liveness recovery ---
#
# Тот же приём вызова хука напрямую с фейковым `item` (duck-typing -- хуку
# нужен только `.fixturenames`), что `test_residual_proxy_guard_unit.py`
# (AT-BUG-064 B2) / `test_device_liveness_guard_unit.py` (AT-BUG-026 B1).


class _FakeItem:
    def __init__(self, fixturenames: list[str]) -> None:
        self.fixturenames = fixturenames


@pytest.mark.p1
@allure.id("AT-BUG-066-hook-rechecks-default-env-state-after-recovery")
@allure.title("Проба: pytest_runtest_setup повторно зовёт _ensure_default_font_scale()/_ensure_default_night_mode() после device-liveness recovery (device-free)")
def test_hook_rechecks_default_env_state_after_recovery(monkeypatch):
    monkeypatch.setattr(_conftest, "_pending_recovery_warning", None)
    recovered_msg = "AT-BUG-026 device-liveness guard: устройство восстановлено 1/2"
    monkeypatch.setattr(
        _conftest._DEVICE_GUARD, "ensure_ready", lambda: recovered_msg,
    )
    monkeypatch.setattr(_conftest, "_reset_ca_check", lambda: None)
    monkeypatch.setattr(_conftest, "_ensure_no_residual_device_proxy", lambda: None)
    font_scale_calls: list = []
    night_mode_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_default_font_scale",
        lambda: font_scale_calls.append(1),
    )
    monkeypatch.setattr(
        _conftest, "_ensure_default_night_mode",
        lambda: night_mode_calls.append(1),
    )

    # Сигнатура реального теста-крашера -- test_x(clean_app, replay, driver):
    # `driver` перечислен ПОСЛЕДНИМ, порядок не влияет на признак "тест
    # трогает устройство" (та же гарантия, что B1/B2 AT-BUG-064/026).
    _conftest.pytest_runtest_setup(_FakeItem(["clean_app", "replay", "driver"]))

    # Then B2-твин: recovery -- ровно сценарий заголовка AT-BUG-066 (эмулятор
    # перезапущен) -- обязан перевзвести ОБЕ проверки.
    assert font_scale_calls == [1]
    assert night_mode_calls == [1]


@pytest.mark.p1
@allure.id("AT-BUG-066-hook-no-default-env-state-recheck-without-recovery")
@allure.title("Проба: pytest_runtest_setup НЕ перевзводит проверки font_scale/night mode, если recovery не произошёл (device-free)")
def test_hook_skips_default_env_state_recheck_when_no_recovery(monkeypatch):
    monkeypatch.setattr(_conftest, "_pending_recovery_warning", None)
    monkeypatch.setattr(_conftest._DEVICE_GUARD, "ensure_ready", lambda: None)
    font_scale_calls: list = []
    night_mode_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_default_font_scale",
        lambda: font_scale_calls.append(1),
    )
    monkeypatch.setattr(
        _conftest, "_ensure_default_night_mode",
        lambda: night_mode_calls.append(1),
    )

    _conftest.pytest_runtest_setup(_FakeItem(["driver"]))

    # Then устройство было живо (recovery не потребовался) -- проверки
    # остаются на своей единственной session-scoped точке входа, повторно
    # НЕ вызываются на каждом тесте.
    assert font_scale_calls == []
    assert night_mode_calls == []


@pytest.mark.p1
@allure.id("AT-BUG-066-hook-no-default-env-state-recheck-without-driver-fixture")
@allure.title("Проба: pytest_runtest_setup НЕ трогает проверки font_scale/night mode, если 'driver' не запрошен тестом (device-free)")
def test_hook_skips_default_env_state_recheck_for_device_free_test(monkeypatch):
    monkeypatch.setattr(
        _conftest._DEVICE_GUARD, "ensure_ready", lambda: None,
    )
    font_scale_calls: list = []
    night_mode_calls: list = []
    monkeypatch.setattr(
        _conftest, "_ensure_default_font_scale",
        lambda: font_scale_calls.append(1),
    )
    monkeypatch.setattr(
        _conftest, "_ensure_default_night_mode",
        lambda: night_mode_calls.append(1),
    )

    _conftest.pytest_runtest_setup(_FakeItem(["tmp_path", "monkeypatch"]))

    assert font_scale_calls == []
    assert night_mode_calls == []
