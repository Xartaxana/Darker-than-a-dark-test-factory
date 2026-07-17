"""Device-free юнит-проба timeout-класса subprocess-вызовов — AT-BUG-009,
инкременты 1 и 2.

Доказывает, что `framework/core/adb.py::_run()`/`pull_app_file()` и
`framework/core/mitm.py::set_device_proxy`/`clear_device_proxy` оборачивают
`subprocess.TimeoutExpired` в явную `TimeoutError` с контекстом (какая команда,
сколько ждали) — конечная ошибка вместо неограниченного клина (тот же класс,
что `bugs/AT-BUG-007.md` закрыл для Appium HTTP-вызовов; находка N1 того же
бага и наблюдение №1 `bugs/AT-BUG-009.md`). Инкремент 2 добавляет пробы шва
`seed_db.ensure_db_initialized()` (наблюдение №3): `TimeoutError` из
`adb.shell("am start -W ...")` на первой строке итерации ретраится тем же
циклом, что раньше ловил только `TimeoutError` из `wait_for`.

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
from framework.data import seed_db


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
@allure.title("Проба: adb.install() использует ADB_TRANSFER_TIMEOUT для самого install, не ADB_SHELL_TIMEOUT (device-free)")
def test_adb_install_uses_transfer_timeout(monkeypatch):
    # Given subprocess.run фиксирует, с каким timeout его реально позвали.
    # AT-BUG-013 (queue-пункт 1): install() теперь СНАЧАЛА опрашивает
    # package-сервис (`pm path android`, ADB_SHELL_TIMEOUT) и только потом
    # делает сам `adb install` (ADB_TRANSFER_TIMEOUT) — фейк различает эти два
    # вызова по команде, чтобы pm-path-опрос сразу вернул "готов" (ноль retry)
    # и не мешал проверке таймаута именно install-вызова.
    seen_timeouts: list = []

    def _fake_run(*args, **kw):
        seen_timeouts.append(kw.get("timeout"))
        cmd_args = args[0]
        if "pm path android" in cmd_args:
            return subprocess.CompletedProcess(args=cmd_args, returncode=0,
                                                stdout="package:android\n", stderr="")
        return subprocess.CompletedProcess(args=cmd_args, returncode=0, stdout="Success", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # When вызывается install() — файловая операция (APK), не обычный shell-вызов
    adb.install(apk="dummy.apk")

    # Then первым ушёл опрос готовности (ADB_SHELL_TIMEOUT), последним — сам
    # install с ADB_TRANSFER_TIMEOUT (щедрее обычного shell-таймаута)
    assert seen_timeouts == [settings.ADB_SHELL_TIMEOUT, settings.ADB_TRANSFER_TIMEOUT]


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


@pytest.mark.p2
@allure.id("AT-BUG-009-adb-shell-timeout-override")
@allure.title("Проба: adb.shell(timeout=...) переопределяет ADB_SHELL_TIMEOUT (device-free)")
def test_adb_shell_accepts_timeout_override(monkeypatch):
    # Given subprocess.run фиксирует, с каким timeout его реально позвали
    seen_timeouts: list = []

    def _fake_run(*args, **kw):
        seen_timeouts.append(kw.get("timeout"))
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    # When вызывающий код (seed_db.ensure_db_initialized) передаёт свой timeout
    # (ADB_LAUNCH_TIMEOUT для `am start -W` — блокирующий вызов, другой класс,
    # чем обычный быстрый shell)
    adb.shell("am start -W -n pkg/.MainActivity", timeout=settings.ADB_LAUNCH_TIMEOUT)

    # Then ушёл именно переданный timeout, не дефолтный ADB_SHELL_TIMEOUT
    assert seen_timeouts == [settings.ADB_LAUNCH_TIMEOUT]
    assert settings.ADB_LAUNCH_TIMEOUT != settings.ADB_SHELL_TIMEOUT


@pytest.mark.p2
@allure.id("AT-BUG-009-seed-db-ensure-db-initialized-retries-launch-timeout")
@allure.title("Проба: ensure_db_initialized ретраит TimeoutError из am start -W (device-free, наблюдение №3)")
def test_ensure_db_initialized_retries_timeout_from_shell(monkeypatch):
    """Шов инкремента 1 (AT-BUG-009, наблюдение №3): ДО фикса `adb.shell(...)`
    вызывался ПЕРЕД `try:`, и `TimeoutError` из него улетал наружу немедленно,
    минуя ретрай-цикл — именно так упали 3 `ERROR at setup` на полном p0."""
    calls: list[str] = []
    db_exists_calls = {"n": 0}

    def _fake_shell(cmd, timeout=None):
        # adb.shell() уже оборачивает subprocess.TimeoutExpired в TimeoutError
        # (adb.py::_run(), инкремент 1) — seed_db видит ТОЛЬКО TimeoutError,
        # никогда сырой TimeoutExpired; фейк имитирует именно этот контракт.
        calls.append(cmd)
        if len(calls) == 1:
            raise TimeoutError(f"adb shell {cmd} не ответил за {timeout}s (AT-BUG-009)")
        return ""

    def _fake_db_exists():
        # Первый вызов (initial-check в начале ensure_db_initialized) — БД ещё
        # нет; после успешного (второго) am start -W — уже есть (wait_for
        # возвращается немедленно, без реального 40s-поллинга).
        db_exists_calls["n"] += 1
        return db_exists_calls["n"] > 1

    monkeypatch.setattr(seed_db.adb, "shell", _fake_shell)
    monkeypatch.setattr(seed_db, "_db_exists", _fake_db_exists)
    monkeypatch.setattr(seed_db.adb, "force_stop", lambda: None)

    # When первая попытка am start -W виснет TimeoutError — ретрай-цикл обязан
    # поймать её (не упасть немедленно) и повторить на attempt=1
    seed_db.ensure_db_initialized()

    # Then было ровно 2 вызова adb.shell (первый — TimeoutExpired, второй —
    # успешный retry), функция не подняла исключение наружу
    assert len(calls) == 2


@pytest.mark.p2
@allure.id("AT-BUG-009-seed-db-ensure-db-initialized-raises-after-two-timeouts")
@allure.title("Проба: ensure_db_initialized падает наружу после ДВУХ TimeoutError подряд из am start -W (device-free)")
def test_ensure_db_initialized_raises_after_two_consecutive_timeouts(monkeypatch):
    calls: list[str] = []

    def _fake_shell(cmd, timeout=None):
        # Тот же контракт, что в предыдущей пробе — adb.shell() уже кидает
        # обёрнутый TimeoutError, не сырой TimeoutExpired.
        calls.append(cmd)
        raise TimeoutError(f"adb shell {cmd} не ответил за {timeout}s (AT-BUG-009)")

    monkeypatch.setattr(seed_db.adb, "shell", _fake_shell)
    monkeypatch.setattr(seed_db, "_db_exists", lambda: False)
    monkeypatch.setattr(seed_db.adb, "force_stop", lambda: None)

    # When обе попытки (attempt 0 и attempt 1) виснут TimeoutError подряд
    # Then исключение уходит наружу (не проглатывается, не бесконечный ретрай) —
    # ретрай-цикл ловит TimeoutError на attempt 0, но на attempt 1
    # (`if attempt == 1: raise`) перевызывает его же наружу, вызывающему коду.
    with pytest.raises(TimeoutError):
        seed_db.ensure_db_initialized()

    assert len(calls) == 2
