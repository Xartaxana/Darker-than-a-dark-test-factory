"""Device-free юнит-проба fail-fast проверки mitm-CA (AT-BUG-011).

Доказывает, что `mitm.is_ca_installed()` и завязанная на неё
`conftest._ensure_replay_ca()` дают МГНОВЕННЫЙ явный отказ при отсутствии CA в
системном APEX-сторе доверия — не 120–240с `ReadTimeoutError`, которым раньше
умирал КАЖДЫЙ replay-тест на среде без CA (доказанная стоимость: 65-минутная
сессия fix-verifier, ложный Reopened AT-BUG-006, эскалация ESC-001, см.
`bugs/AT-BUG-011.md`).

Монки-патчит `subprocess.run` (тот же приём, что `test_subprocess_timeout_unit.py`)
— не требует устройства/эмулятора. Переопределяет session-scoped autouse-фикстуру
`_ensure_app_installed` из `conftest.py` (та иначе дёрнула бы `adb pm list
packages` при сборе тестов), как и остальные device-free пробы этого пакета.
"""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.core import mitm
from framework.tests import conftest as _conftest


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture(autouse=True)
def _reset_ca_cache(monkeypatch):
    """`_ca_checked` в conftest.py — module-level кеш на сессию (AT-BUG-011,
    критерий п.2). Сбрасываем перед КАЖДЫМ тестом этого модуля, чтобы пробы не
    зависели от порядка запуска/друг от друга."""
    monkeypatch.setattr(_conftest, "_ca_checked", False)


def _fake_run(ca_hash: str, apex_listing: str):
    """Фейк `subprocess.run`, различающий два реальных вызова `is_ca_installed()`
    по исполняемому файлу (`openssl...` — вычисление хэша; `adb` — `ls` APEX-стора),
    тем же способом, каким сама функция их различает."""

    def _run(args, **kw):
        exe = str(args[0]).lower()
        if "openssl" in exe:
            return subprocess.CompletedProcess(args=args, returncode=0,
                                                stdout=f"{ca_hash}\n", stderr="")
        # adb shell ls /apex/com.android.conscrypt/cacerts/
        return subprocess.CompletedProcess(args=args, returncode=0,
                                            stdout=apex_listing, stderr="")

    return _run


@pytest.mark.p1
@allure.id("AT-BUG-011-ca-check-present")
@allure.title("Проба: is_ca_installed() возвращает True, когда хэш CA есть в APEX-сторе (device-free)")
def test_is_ca_installed_true_when_hash_present(tmp_path, monkeypatch):
    # Given валидный (с точки зрения проверки) CA PEM-файл и adb-вывод, СОДЕРЖАЩИЙ
    # хэш этого CA среди файлов APEX-стора
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("deadbeef", "deadbeef.0\nfeedface.0\n"),
    )

    # When/Then проверка мгновенно (без device) находит хэш и возвращает True
    assert mitm.is_ca_installed() is True


@pytest.mark.p1
@allure.id("AT-BUG-011-ca-check-absent")
@allure.title("Проба: is_ca_installed() возвращает False, когда хэша CA нет в APEX-сторе (device-free)")
def test_is_ca_installed_false_when_hash_absent(tmp_path, monkeypatch):
    # Given тот же CA PEM, но adb-вывод НЕ содержит его хэш (CA стёрт ребутом —
    # ровно сценарий AT-BUG-011)
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("deadbeef", "feedface.0\nother.0\n"),
    )

    assert mitm.is_ca_installed() is False


@pytest.mark.p1
@allure.id("AT-BUG-011-ensure-replay-ca-passes-when-present")
@allure.title("Проба: _ensure_replay_ca() не падает, когда CA присутствует (device-free)")
def test_ensure_replay_ca_passes_when_ca_present(tmp_path, monkeypatch):
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("deadbeef", "deadbeef.0\n"),
    )

    # When/Then здоровая среда — фикстура-предусловие проходит молча
    _conftest._ensure_replay_ca()


@pytest.mark.p1
@allure.id("AT-BUG-011-ensure-replay-ca-fails-fast-when-absent")
@allure.title("Проба: _ensure_replay_ca() падает МГНОВЕННО явной ошибкой (не таймаутом), когда CA отсутствует (device-free)")
def test_ensure_replay_ca_fails_fast_when_ca_absent(tmp_path, monkeypatch):
    # Given CA отсутствует в APEX-сторе (симулирует среду, поднятую без
    # -WritableSystem/после ребута) — корневой сценарий AT-BUG-011
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run("deadbeef", "feedface.0\nother.0\n"),
    )

    # When/Then явная RuntimeError с рецептом и ссылкой на баг — НЕ TimeoutError,
    # НЕ ReadTimeoutError, никакого реального ожидания (мгновенно в рамках юнит-теста)
    with pytest.raises(RuntimeError) as exc_info:
        _conftest._ensure_replay_ca()

    message = str(exc_info.value)
    assert "AT-BUG-011" in message
    assert "Start-Emulator -WritableSystem" in message
    assert "Install-MitmCA" in message


@pytest.mark.p1
@allure.id("AT-BUG-011-ensure-replay-ca-caches-per-session")
@allure.title("Проба: _ensure_replay_ca() кеширует успешную проверку — второй вызов НЕ бьёт adb/openssl снова (device-free)")
def test_ensure_replay_ca_caches_after_success(tmp_path, monkeypatch):
    # Given CA присутствует; фейк считает реальные вызовы subprocess.run
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    calls: list = []

    def _counting_run(args, **kw):
        calls.append(args)
        exe = str(args[0]).lower()
        if "openssl" in exe:
            return subprocess.CompletedProcess(args=args, returncode=0,
                                                stdout="deadbeef\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0,
                                            stdout="deadbeef.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _counting_run)

    # When вызывается дважды подряд (имитация двух replay-тестов одной сессии)
    _conftest._ensure_replay_ca()
    calls_after_first = len(calls)
    _conftest._ensure_replay_ca()

    # Then второй вызов не добавил новых subprocess.run — кеш на сессию (критерий п.2)
    assert len(calls) == calls_after_first
    assert calls_after_first > 0
