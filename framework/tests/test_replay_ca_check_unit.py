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
    по исполняемому файлу (`openssl...` — вычисление хэша; `adb` — `ls`
    актуального стора), тем же способом, каким сама функция их различает.
    Не различает apex/system-ветку (не парсит команду) — годится только для
    проб, которым не важно, КАКОЙ стор реально проверялся на устройстве."""

    def _run(args, **kw):
        exe = str(args[0]).lower()
        if "openssl" in exe:
            return subprocess.CompletedProcess(args=args, returncode=0,
                                                stdout=f"{ca_hash}\n", stderr="")
        # adb shell "if [ -d apex ]; then ls apex; else ls system; fi"
        return subprocess.CompletedProcess(args=args, returncode=0,
                                            stdout=apex_listing, stderr="")

    return _run


def _fake_device_run(ca_hash: str, listing: str,
                      adb_returncode: int = 0, adb_stderr: str = ""):
    """Фейк `subprocess.run`, симулирующий РЕАЛЬНОЕ устройство (AT-BUG-095):
    различает openssl-вызов от adb-вызова так же, как `_fake_run`, но
    ДОПОЛНИТЕЛЬНО проверяет, что единственная adb-команда несёт условную
    ветку на ОБА стора (`_APEX_CACERTS_DIR` и `_SYSTEM_CACERTS_DIR` — та же
    логика, что `ca-mount.sh`) — device-free, реальный `[ -d ... ]` НЕ
    исполняется; `listing` симулирует то, что вернул бы АКТУАЛЬНЫЙ для
    устройства `ls` (какая ветка сработала на реальном устройстве — забота
    вызывающего теста, не этого фейка). `adb_returncode`/`adb_stderr` —
    симуляция ОТКАЗА adb-команды (AT-BUG-095, п.2: device offline /
    несколько устройств / недоступно)."""

    def _run(args, **kw):
        exe = str(args[0]).lower()
        if "openssl" in exe:
            return subprocess.CompletedProcess(args=args, returncode=0,
                                                stdout=f"{ca_hash}\n", stderr="")
        cmd_str = str(args[-1])
        assert mitm._APEX_CACERTS_DIR in cmd_str, (
            "adb-команда is_ca_installed() обязана нести условную ветку на "
            "apex-стор (AT-BUG-095) -- не найдена в аргументе"
        )
        assert mitm._SYSTEM_CACERTS_DIR in cmd_str, (
            "adb-команда is_ca_installed() обязана нести условную ветку на "
            "system-стор (AT-BUG-095) -- не найдена в аргументе"
        )
        if adb_returncode != 0:
            return subprocess.CompletedProcess(args=args, returncode=adb_returncode,
                                                stdout="", stderr=adb_stderr)
        return subprocess.CompletedProcess(args=args, returncode=0,
                                            stdout=listing, stderr="")

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
@allure.id("AT-BUG-095-ca-check-apex-branch")
@allure.title("Проба: is_ca_installed() находит CA через apex-ветку, когда apex-стор присутствует (device-free, регресс api34/стек1)")
def test_is_ca_installed_true_via_apex_branch_when_apex_present(tmp_path, monkeypatch):
    # Given apex-стор физически присутствует на устройстве (api34, стек 1) и
    # содержит хэш CA -- этой пробой закрывается регресс «apex-ветка не
    # трогается по логике» (критерий готовности AT-BUG-095)
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_device_run("deadbeef", "deadbeef.0\nfeedface.0\n"),
    )

    assert mitm.is_ca_installed() is True


@pytest.mark.p1
@allure.id("AT-BUG-095-ca-check-system-store-branch")
@allure.title("Проба: is_ca_installed() находит CA через system-store ветку, когда apex-стор отсутствует (device-free, api29/стек2)")
def test_is_ca_installed_true_via_system_store_when_apex_absent(tmp_path, monkeypatch):
    # Given apex-стор ОТСУТСТВУЕТ на устройстве (живой факт AT-BUG-095:
    # emulator-5556, ao3_test_api29, стек 2 -- APEX_ABSENT), CA стоит
    # исключительно в system store (139 файлов на живом устройстве, здесь --
    # достаточно двух для пробы)
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_device_run("deadbeef", "deadbeef.0\nother.0\n"),
    )

    # When/Then раньше (до AT-BUG-095) эта же on-device ситуация возвращала
    # ЛОЖНЫЙ False (apex-путь не находил хэш, т.к. каталога физически нет) --
    # теперь функция зеркалит install-mitm-ca.sh и находит CA в system store
    assert mitm.is_ca_installed() is True


@pytest.mark.p1
@allure.id("AT-BUG-095-ca-check-absent-from-active-store")
@allure.title("Проба: is_ca_installed() возвращает честный False, когда хэша CA нет в АКТУАЛЬНОМ сторе (device-free)")
def test_is_ca_installed_false_when_hash_absent_from_active_store(tmp_path, monkeypatch):
    # Given актуальный (для этого устройства) стор НЕ содержит хэш CA --
    # честное отсутствие, не путать с отказом adb-команды (следующая проба)
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_device_run("deadbeef", "feedface.0\nother.0\n"),
    )

    assert mitm.is_ca_installed() is False


@pytest.mark.p1
@allure.id("AT-BUG-095-ca-check-adb-failure-not-silent-false")
@allure.title("Проба: is_ca_installed() бросает явную ошибку на отказе adb-команды -- НЕ молчаливый False (device offline/несколько устройств)")
def test_is_ca_installed_raises_on_adb_failure_returncode(tmp_path, monkeypatch):
    # Given adb-команда (ls apex/system store) отказывает ненулевым
    # returncode -- класс «env-негатив != факт» (CLAUDE.md permission-hygiene
    # п.6): раньше пустой/ошибочный stdout читался как «хэша нет» -> False ->
    # _ensure_replay_ca() ложно сообщал «CA отсутствует» (живой прецедент: 22
    # error в RUN-20260821-1100)
    ca_pem = tmp_path / "mitmproxy-ca-cert.pem"
    ca_pem.write_text("dummy pem contents", encoding="utf-8")
    monkeypatch.setenv("AO3_MITM_CA_PEM", str(ca_pem))
    monkeypatch.setattr(
        subprocess, "run",
        _fake_device_run(
            "deadbeef", "",
            adb_returncode=1, adb_stderr="error: device offline",
        ),
    )

    # When/Then явная RuntimeError, различимая от честного «CA отсутствует» --
    # НЕ False, НЕ молчаливая деградация
    with pytest.raises(RuntimeError) as exc_info:
        mitm.is_ca_installed()

    message = str(exc_info.value)
    assert "AT-BUG-095" in message
    assert "device offline" in message


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
