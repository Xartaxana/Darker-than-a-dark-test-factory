"""Юнит-тесты doctor (scripts/doctor.py) на фейковом окружении."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import pytest

import doctor as dr


@pytest.fixture()
def env(repo, monkeypatch):
    """Минимальное «здоровое» окружение в tmp: все файлы на месте, сабпроцессы ok."""
    root = repo.root
    monkeypatch.setattr(dr, "REPO", root, raising=True)
    monkeypatch.setattr(dr, "VENV_PY", root / "venv" / "python.exe", raising=True)
    monkeypatch.setattr(dr, "ENV_PS1", root / "scripts" / "env.ps1", raising=True)
    monkeypatch.setattr(dr, "APP", root / "app-under-test", raising=True)
    monkeypatch.setattr(dr, "AUT_PATH", root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(dr, "ESCALATIONS_PATH", root / "state" / "escalations.md", raising=True)
    monkeypatch.setattr(dr, "LOCK_FILE", root / "state" / "loop.lock", raising=True)
    monkeypatch.setattr(dr, "SLA_PATH", root / "state" / "sla.yaml", raising=True)
    monkeypatch.setattr(dr, "_run", lambda args, timeout=60: (0, "deps-ok"), raising=True)
    monkeypatch.setattr(dr, "_which", lambda name: f"C:/fake/{name}", raising=True)
    # spec-factory-window v6 К5в: fake быстрого/детерминированного ридера
    # задачи планировщика — реальный powershell.exe НЕ вызываем в каждом
    # тесте doctor (медленно, environment-dependent); Disabled -> н/п,
    # держит test_healthy_env_all_ok зелёным независимо от машины.
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Disabled", None, None), raising=True)

    def touch(rel: str, text: str = "x") -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    touch("venv/python.exe")
    touch("scripts/env.ps1",
          '$root = "IGNORED"\n'
          '$env:JAVA_HOME        = "$root\\tools\\jdk"\n'
          '$env:ANDROID_HOME     = "$root\\tools\\android-sdk"\n'
          '$env:ANDROID_AVD_HOME = "$root\\tools\\avd"\n')
    touch("tools/jdk/bin/java.exe")
    touch("tools/android-sdk/platform-tools/adb.exe")
    touch(f"tools/avd/{dr.AVD_NAME}.ini")
    touch("tools/appium/package.json")
    touch("app-under-test/gradlew.bat")
    touch("state/rules.yaml")
    touch("state/sla.yaml")
    touch("schemas/transitions.yaml")
    apk_p = touch("app-under-test/app.apk")
    import hashlib
    apk_sha = hashlib.sha256(apk_p.read_bytes()).hexdigest()
    touch("state/app-under-test.yaml",
          f'apk_path: app-under-test/app.apk\napk_sha256: "{apk_sha}"\n'
          f'version_name: "1.10"\nversion_code: 11\n')
    # env.ps1 использует $root репозитория — подменяем подстановку на tmp-корень
    monkeypatch.setattr(dr, "_env_paths", lambda: {
        "JAVA_HOME": root / "tools" / "jdk",
        "ANDROID_HOME": root / "tools" / "android-sdk",
        "ANDROID_AVD_HOME": root / "tools" / "avd",
    }, raising=True)
    return touch


def test_healthy_env_all_ok(repo, env):
    checks = dr.run_checks()
    assert all(c.ok for c in checks), [f"{c.name}: {c.detail}" for c in checks if not c.ok]
    assert dr.main([]) == 0
    assert not (repo.root / "state" / "escalations.md").exists()


def test_missing_adb_fails_and_escalates(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    assert dr.main([]) == 1

    esc = repo.read_artifact("state/escalations.md")
    assert "**DOCTOR**" in esc and "adb" in esc


def test_escalation_deduplicated(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    dr.main([])
    dr.main([])

    esc = repo.read_artifact("state/escalations.md")
    assert esc.count("**DOCTOR**") == 1


def test_missing_apk_is_warn_not_fail(repo, env):
    (repo.root / "app-under-test" / "app.apk").unlink()

    checks = dr.run_checks()
    apk = next(c for c in checks if c.name == "APK по apk_path")
    assert not apk.ok and apk.warn
    assert dr.main([]) == 0            # WARN не валит doctor


# ---------------------------------------------------------------------------
# A2/C1 (spec-build-source-dual-mode v4): sha256-чек APK против yaml —
# ТРИ состояния границы, не наивный FAIL.
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def test_apk_sha256_check_missing_file_is_warn(repo, env):
    """Файла нет -> WARN (отдаётся существующему чеку «APK по apk_path»)."""
    (repo.root / "app-under-test" / "app.apk").unlink()

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert not chk.ok and chk.warn
    assert "файла нет" in chk.detail
    assert dr.main([]) == 0


def test_apk_sha256_check_empty_yaml_sha_is_warn(repo, env):
    """apk_sha256 пуст в yaml -> WARN (сверка невозможна), не FAIL."""
    env("state/app-under-test.yaml",
        'apk_path: app-under-test/app.apk\napk_sha256: ""\n')

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert not chk.ok and chk.warn
    assert dr.main([]) == 0


def test_apk_sha256_check_unknown_yaml_sha_is_warn(repo, env):
    env("state/app-under-test.yaml",
        'apk_path: app-under-test/app.apk\napk_sha256: unknown\n')

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert not chk.ok and chk.warn
    assert dr.main([]) == 0


def test_apk_sha256_check_unknown_versions_is_warn(repo, env):
    """M-B.2: версии 'unknown' (незавершённая запись сборки) -> WARN, даже
    если apk_sha256 формально заполнен."""
    apk = repo.root / "app-under-test" / "app.apk"
    sha = _sha256_hex(apk.read_bytes())
    env("state/app-under-test.yaml",
        f'apk_path: app-under-test/app.apk\napk_sha256: "{sha}"\n'
        f'version_name: "unknown"\nversion_code: unknown\n')

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert not chk.ok and chk.warn
    assert dr.main([]) == 0


def test_apk_sha256_check_matching_sha_is_ok(repo, env):
    apk = repo.root / "app-under-test" / "app.apk"
    sha = _sha256_hex(apk.read_bytes())
    env("state/app-under-test.yaml",
        f'apk_path: app-under-test/app.apk\napk_sha256: "{sha}"\n'
        f'version_name: "1.10"\nversion_code: 11\n')

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert chk.ok and not chk.warn
    assert dr.main([]) == 0


def test_apk_sha256_check_mismatch_is_fail_with_recovery_path(repo, env):
    """ОБА присутствуют И различаются -> FAIL с текстом пути восстановления."""
    env("state/app-under-test.yaml",
        'apk_path: app-under-test/app.apk\n'
        'apk_sha256: "0000000000000000000000000000000000000000000000000000000000000000"\n'
        'version_name: "1.10"\nversion_code: 11\n')

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "APK sha256 соответствует yaml")
    assert not chk.ok and not chk.warn
    assert "build_watch.py" in chk.detail and "--provided" in chk.detail

    assert dr.main([]) == 1   # FAIL валит doctor
    esc = repo.read_artifact("state/escalations.md")
    assert "APK sha256 соответствует yaml" in esc


def test_shallow_clone_check_is_informational_not_fail(repo, env, monkeypatch):
    """docs/09 «Мелкое хозяйство» п.3: shallow-клон app-under-test — видимая
    информация для человека, но НИКОГДА не FAIL/WARN (ожидаемое состояние;
    build_watch.py устойчив к нему своим guard'ом)."""
    def fake_run(args, timeout=60):
        if "--is-shallow-repository" in args:
            return 0, "true\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    depth = next(c for c in checks if c.name == "app-under-test git-глубина")

    assert depth.ok and not depth.warn                 # никогда не эскалирует
    assert "shallow" in depth.detail
    assert dr.main([]) == 0
    assert not (repo.root / "state" / "escalations.md").exists()


def test_non_git_app_under_test_labeled_not_git_repo(repo, env, monkeypatch):
    """Батч-пункт 3 (косметика, наблюдение critic 07-18): каталог
    app-under-test существует, но git-плюмбинг не подтверждает репозиторий
    (rc != 0, как в реальном не-git каталоге) — раньше это молча читалось
    как "полный клон"; теперь формулировка отдельная и не путается с
    настоящим полным (не-shallow) клоном."""
    def fake_run(args, timeout=60):
        if "--is-shallow-repository" in args:
            return 128, "fatal: not a git repository\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    depth = next(c for c in checks if c.name == "app-under-test git-глубина")

    assert depth.ok and not depth.warn          # по-прежнему только инфо, не FAIL/WARN
    assert "не git-репозиторий" in depth.detail
    assert "полный клон" not in depth.detail
    assert "shallow" not in depth.detail
    assert dr.main([]) == 0
    assert not (repo.root / "state" / "escalations.md").exists()


def test_guest_ipv4_pin_ok(repo, env, monkeypatch):
    """env-ipv4-pin-0803 (ESC-015): устройство присутствует, `ip -6 addr` без
    inet6-строк — чек OK. Эффектный критерий (не отдельный агрегатный флаг
    `conf/all/disable_ipv6`) — см. test_guest_ipv4_pin_warn_on_stale_interface_pin
    ниже, находка живой верификации 2026-08-03, почему это важно."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n"
        if args[-3:] == ["ip", "-6", "addr"]:
            return 0, ""
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert pin.ok and not pin.warn
    assert "emulator-5554" in pin.detail
    assert dr.main([]) == 0


def test_guest_ipv4_pin_warn_when_not_pinned(repo, env, monkeypatch):
    """Устройство есть, но `ip -6 addr` несёт inet6-строки (пин не применён/
    слетел) — WARN, не FAIL (doctor не роняет прогон), подсказка ведёт на
    Start-Emulator."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n"
        if args[-3:] == ["ip", "-6", "addr"]:
            return 0, (
                "16: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500\n"
                "    inet6 fec0::a829:2fab:7fe3:bff6/64 scope site temporary dynamic\n"
            )
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert not pin.ok and pin.warn
    assert "Start-Emulator" in pin.detail
    assert "inet6" in pin.detail
    assert dr.main([]) == 0            # WARN не валит doctor


def test_guest_ipv4_pin_warn_on_stale_interface_pin(repo, env, monkeypatch):
    """Находка живой верификации 2026-08-03 (attempt 2, полный холодный
    рестарт на реальном устройстве): Android асинхронно (~60с после буда, вне
    контроля Start-Emulator) переустанавливает per-interface
    `conf/wlan0/disable_ipv6` обратно в 0, ПОКА `conf/all/disable_ipv6`
    остаётся 1 (воспроизведено эмпирически). Старый чек (`cat .../all/
    disable_ipv6`) на этом сценарии давал ЛОЖНЫЙ OK; новый (`ip -6 addr`,
    эффект) обязан поймать WARN даже когда агрегатный флаг `all` здоров. Тест
    эмулирует ИМЕННО такое расхождение: fake_run не отвечает на чтение
    `all`-флага вовсе (только на `ip -6 addr`) — падает AssertionError, если
    реализация вернётся к чтению агрегатного флага."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n"
        if args[-3:] == ["ip", "-6", "addr"]:
            return 0, (
                "16: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500\n"
                "    inet6 fec0::c6de:d4ee:3a0d:ae94/64 scope site temporary dynamic\n"
                "    inet6 fe80::6455:48c9:c820:ef8d/64 scope link stable-privacy\n"
            )
        if any("disable_ipv6" in str(a) for a in args):
            raise AssertionError(f"чек не должен читать conf/all/disable_ipv6 напрямую: {args}")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert not pin.ok and pin.warn
    assert "2 шт." in pin.detail


def test_guest_ipv4_pin_skipped_when_no_device(repo, env, monkeypatch):
    """Устройства нет (эмулятор не поднят) - чек н/п (skip), НЕ FAIL: doctor
    не поднимает эмулятор сам."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert pin.ok and not pin.warn
    assert "н/п" in pin.detail
    assert dr.main([]) == 0


# ---------------------------------------------------------------------------
# _adb_device_serial — адресация устройства при возможных ДВУХ device-стеках
# (spec-p3-second-emulator N3; доложено критиком, docs/tasks/
# p3-second-emulator.md:395: раньше бралась ПЕРВАЯ строка `adb devices`,
# что могло судить не тот стек)
# ---------------------------------------------------------------------------

def _clear_device_env(monkeypatch):
    monkeypatch.delenv("AO3_DEVICE", raising=False)
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)


def test_adb_device_serial_zero_devices_no_warning(env, monkeypatch):
    """Граница снизу: 0 устройств — None, БЕЗ warning (легитимное «эмулятор
    не поднят», отличается от неоднозначности)."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial is None
    assert warning is None


def test_adb_device_serial_run_failure_returns_none_none_regardless_of_env(env, monkeypatch):
    """M6-дырка (rework, критик-вход): `adb devices` сам не выполнился
    (rc != 0 — не «промах формы вызова», а реальный отказ инструмента) —
    (None, None), БЕЗ warning, даже если env-адресация выставлена (нечего
    сверять — список серийников недоступен, не «env не найден среди
    пустого списка»)."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 1, "adb: command failed"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    monkeypatch.setenv("AO3_DEVICE", "emulator-5554")

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial is None
    assert warning is None


def test_adb_device_serial_env_set_zero_devices_no_warning(env, monkeypatch):
    """M6-дырка (rework, критик-вход): env-адресация ВЫСТАВЛЕНА, но живых
    устройств 0 — пин порядка веток: «нет устройств» проверяется РАНЬШЕ
    env-адресации, поэтому это тихий (None, None) («эмулятор не поднят»),
    НЕ WARNING «AO3_DEVICE не найден среди живых устройств ()» с пустым
    списком в тексте."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    monkeypatch.setenv("AO3_DEVICE", "emulator-5554")

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial is None
    assert warning is None


def test_adb_device_serial_one_device_no_env_uses_it(env, monkeypatch):
    """Прежнее (легаси) поведение сохранено: ровно одно устройство без
    env-адресации используется молча."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial == "emulator-5554"
    assert warning is None


def test_adb_device_serial_two_devices_no_env_ambiguous_warns(env, monkeypatch):
    """M6-граница за пределом 1: >1 устройство без env-адресации — None +
    WARNING (не первое из списка молча, как было до N3-фикса)."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, ("List of devices attached\n"
                        "emulator-5554\tdevice\nemulator-5556\tdevice\n")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial is None
    assert warning is not None
    assert "emulator-5554" in warning and "emulator-5556" in warning
    assert "Use-DeviceStack" in warning


def test_adb_device_serial_env_points_to_present_serial(env, monkeypatch):
    """env указывает на ПРИСУТСТВУЮЩИЙ серийник среди двух живых — берём
    именно его (не первый), молча."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, ("List of devices attached\n"
                        "emulator-5554\tdevice\nemulator-5556\tdevice\n")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE", "emulator-5556")

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial == "emulator-5556"
    assert warning is None


def test_adb_device_serial_android_serial_fallback(env, monkeypatch):
    """AO3_DEVICE не выставлен — ANDROID_SERIAL тоже валиден как явная
    адресация (та же пара, что Use-DeviceStack per-стек выставляет)."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, ("List of devices attached\n"
                        "emulator-5554\tdevice\nemulator-5556\tdevice\n")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)
    monkeypatch.setenv("ANDROID_SERIAL", "emulator-5554")

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial == "emulator-5554"
    assert warning is None


def test_adb_device_serial_env_points_to_absent_serial_warns_not_none_silently(env, monkeypatch):
    """env указывает на ОТСУТСТВУЮЩИЙ серийник (протухшая переменная/чужой
    стек погашен) — None + объясняющий WARNING, а НЕ молчаливый откат на
    первое присутствующее устройство (дух doctor: env-ложь не даёт права
    судить по случайному другому устройству)."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE", "emulator-9999")

    serial, warning = dr._adb_device_serial(Path("C:/fake/adb.exe"))
    assert serial is None
    assert warning is not None
    assert "emulator-9999" in warning
    assert "emulator-5554" in warning  # перечисляет реально живые серийники


def test_device_package_check_ambiguous_serial_differs_from_no_device(env):
    """Прямой юнит на `_device_package_check` (B2, критик-вход батча миграции
    2026-08-21): `serial=None` С `ambiguous=True` (2 устройства без явной
    адресации) даёт ДРУГОЙ текст, чем `serial=None` БЕЗ ambiguous (0
    устройств) — самопротиворечие «устройства нет» рядом с WARN про 2
    устройства больше не воспроизводится."""
    ambiguous = dr._device_package_check(True, None, None, None, "", ambiguous=True)
    assert ambiguous.ok and not ambiguous.warn
    assert "неоднозначна" in ambiguous.detail
    assert "устройства нет" not in ambiguous.detail

    no_device = dr._device_package_check(True, None, None, None, "", ambiguous=False)
    assert no_device.ok and not no_device.warn
    assert "устройства нет" in no_device.detail
    assert "неоднозначна" not in no_device.detail


def test_run_checks_two_devices_no_env_adds_addressing_warn_not_fail(repo, env, monkeypatch):
    """Интеграционный уровень: run_checks() несёт отдельный WARN-чек
    «устройство: однозначная адресация», guest IPv4 pin отмечается н/п с
    объяснением (не «устройства нет»), и doctor остаётся exit 0 (WARN, не
    FAIL) — не молча первое, но и не роняет прогон."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, ("List of devices attached\n"
                        "emulator-5554\tdevice\nemulator-5556\tdevice\n")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)

    checks = dr.run_checks()
    addressing = next(c for c in checks if c.name == "устройство: однозначная адресация")
    assert not addressing.ok and addressing.warn
    assert "Use-DeviceStack" in addressing.detail
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert pin.ok and not pin.warn
    assert "неоднозначна" in pin.detail
    # B2 (критик-вход батча миграции 2026-08-21): 2-й потребитель serial=None
    # (mech-device-build-check) раньше самопротиворечиво писал «устройства
    # нет» рядом с WARN «2 устройств без адресации» — теперь тоже
    # «адресация неоднозначна», не «устройства нет».
    pkg = next(c for c in checks if c.name == "пакет на устройстве соответствует yaml")
    assert pkg.ok and not pkg.warn
    assert "неоднозначна" in pkg.detail
    assert "устройства нет" not in pkg.detail
    assert dr.main([]) == 0


def test_run_checks_env_addressed_device_no_warn(repo, env, monkeypatch):
    """Позитивный контроль интеграционного уровня: env корректно адресует
    один из двух устройств — НЕТ WARN-чека адресации, guest IPv4 pin
    работает по адресованному серийнику как обычно."""
    def fake_run(args, timeout=60):
        if args[-1] == "devices":
            return 0, ("List of devices attached\n"
                        "emulator-5554\tdevice\nemulator-5556\tdevice\n")
        if args[-3:] == ["ip", "-6", "addr"]:
            return 0, ""
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)
    _clear_device_env(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE", "emulator-5556")

    checks = dr.run_checks()
    assert not any(c.name == "устройство: однозначная адресация" for c in checks)
    pin = next(c for c in checks if c.name == "guest IPv4 pin")
    assert pin.ok and not pin.warn
    assert "emulator-5556" in pin.detail
    assert dr.main([]) == 0


def test_no_escalate_flag(repo, env):
    (repo.root / "tools" / "android-sdk" / "platform-tools" / "adb.exe").unlink()

    assert dr.main(["--no-escalate"]) == 1
    assert not (repo.root / "state" / "escalations.md").exists()


# ---------------------------------------------------------------------------
# _heartbeat_lock_dead_pid_check — M1/R4 (plan-m1-m4.md v3, 2026-08-09)
# ---------------------------------------------------------------------------

def _write_lock(repo, *, holder: str, pid, ts: str) -> Path:
    p = repo.root / "state" / "loop.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"holder": holder, "pid": pid, "ts": ts}), encoding="utf-8")
    return p


def _now_stamp(delta_hours: float = 0.0) -> str:
    ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=delta_hours)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_heartbeat_lock_dead_pid_warns(repo, env, monkeypatch):
    """LIVE лок с holder=heartbeat:* и мёртвым pid -> WARN (не FAIL)."""
    _write_lock(repo, holder="heartbeat:2026-08-09T10:00:00Z:ab12cd34",
                pid=999999, ts=_now_stamp())

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            return 0, "INFO: No tasks are running which match the specified criteria.\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert not chk.ok and chk.warn
    assert "999999" in chk.detail
    assert dr.main([]) == 0                     # WARN не валит doctor


def test_interactive_lock_dead_pid_not_applicable(repo, env, monkeypatch):
    """Тот же мёртвый pid, но holder НЕ heartbeat:* (интерактивный CLI-лок,
    умирает мгновенно штатно) -> проверка н/п, tasklist даже не зовётся."""
    _write_lock(repo, holder="qa-loop:2026-08-09T10:00:00Z", pid=999999, ts=_now_stamp())

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            raise AssertionError("не должен звать tasklist для НЕ-heartbeat holder")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert chk.ok and not chk.warn
    assert dr.main([]) == 0


def test_heartbeat_lock_alive_pid_ok(repo, env, monkeypatch):
    _write_lock(repo, holder="heartbeat:2026-08-09T10:00:00Z:ab12cd34",
                pid=os.getpid(), ts=_now_stamp())

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            return 0, f"python.exe   {os.getpid()} Console  1  10,000 K\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert chk.ok and not chk.warn


def test_heartbeat_lock_missing_is_not_applicable(repo, env):
    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert chk.ok and not chk.warn
    assert "н/п" in chk.detail


def test_heartbeat_lock_naive_ts_does_not_crash_and_still_warns(repo, env, monkeypatch):
    """Критик-фикс (класс 2а, 2026-08-09): naive ISO ts (без 'Z') раньше
    ронял run_checks() TypeError'ом (naive - aware). Naive трактуется как
    UTC — свежий naive ts даёт LIVE + мёртвый pid -> WARN, не крах."""
    naive_ts = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")  # без 'Z'
    _write_lock(repo, holder="heartbeat:2026-08-09T10:00:00Z:ab12cd34",
                pid=999999, ts=naive_ts)

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            return 0, "INFO: No tasks are running which match the specified criteria.\n"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()                     # не должно бросить TypeError
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert not chk.ok and chk.warn
    assert "999999" in chk.detail


def test_heartbeat_lock_tasklist_error_is_unknown_not_dead(repo, env, monkeypatch):
    """Критик-фикс п.4: ошибка САМОГО tasklist (rc!=0) — «неизвестно», не
    «мёртв». Раньше схлопывалось в False -> ложный WARN осиротевшего лока
    на банальном сбое инструмента."""
    _write_lock(repo, holder="heartbeat:2026-08-09T10:00:00Z:ab12cd34",
                pid=999999, ts=_now_stamp())

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            return 1, "ERROR: tasklist недоступен (симуляция)"
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert chk.ok and not chk.warn                # НЕ WARN — просто "недоступна"
    assert "недоступна" in chk.detail
    assert dr.main([]) == 0


def test_heartbeat_lock_stale_ttl_not_applicable(repo, env, monkeypatch):
    """STALE лок (возраст > TTL sla.yaml, дефолт 2ч) — проверка НЕ
    применяется (TTL-страховка снимет его сама на следующем acquire);
    tasklist не должен вызываться вовсе."""
    _write_lock(repo, holder="heartbeat:old:ab12cd34", pid=999999, ts=_now_stamp(delta_hours=5))

    def fake_run(args, timeout=60):
        if args[:1] == ["tasklist"]:
            raise AssertionError("STALE-лок не должен доходить до tasklist")
        return 0, "deps-ok"
    monkeypatch.setattr(dr, "_run", fake_run, raising=True)

    checks = dr.run_checks()
    chk = next(c for c in checks if c.name == "живой loop.lock с мёртвым pid")
    assert chk.ok and not chk.warn


# --- К5в (spec-factory-window v6, 2026-08-16): LastRunTime задачи -------

def _lastrun_check(checks):
    return next(c for c in checks
                if c.name.startswith(f"LastRunTime задачи {dr.HEARTBEAT_TASK_NAME}"))


def test_lastrun_check_query_failed_is_not_applicable(repo, env, monkeypatch):
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(False, None, None, "boom"), raising=True)

    chk = _lastrun_check(dr.run_checks())

    assert chk.ok and not chk.warn
    assert "н/п" in chk.detail and "boom" in chk.detail
    assert dr.main([]) == 0


def test_lastrun_check_disabled_is_not_applicable(repo, env, monkeypatch):
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Disabled", None, None), raising=True)

    chk = _lastrun_check(dr.run_checks())

    assert chk.ok and not chk.warn
    assert "н/п" in chk.detail and "Disabled" in chk.detail


def test_lastrun_check_never_ran_is_not_applicable(repo, env, monkeypatch):
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", None, None), raising=True)

    chk = _lastrun_check(dr.run_checks())

    assert chk.ok and not chk.warn
    assert "н/п" in chk.detail


def test_lastrun_check_fresh_is_ok(repo, env, monkeypatch):
    fresh = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", fresh, None), raising=True)

    chk = _lastrun_check(dr.run_checks())

    assert chk.ok and not chk.warn
    assert dr.main([]) == 0


def test_lastrun_check_boundary_exactly_two_hours_is_ok(repo, env, monkeypatch):
    """Граница НА пороге (ровно 2ч) — ok (<=, не строго <). `now` инжектится
    явно (доктор поддерживает optional now= на этой функции, см. образец
    _lock_age_hours) — избегает флейка от системного времени между
    вычислением фикстуры и вызовом проверки."""
    now = datetime.datetime(2026, 8, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)
    on_boundary = now - datetime.timedelta(hours=dr.HEARTBEAT_TASK_LAST_RUN_MAX_H)
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", on_boundary, None), raising=True)

    chk = dr._heartbeat_task_last_run_check(now=now)

    assert chk.ok and not chk.warn


def test_lastrun_check_boundary_just_past_two_hours_warns(repo, env, monkeypatch):
    """Граница ЗА порогом (2ч + 1мин) — WARN, не FAIL."""
    now = datetime.datetime(2026, 8, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)
    past_boundary = now - datetime.timedelta(hours=dr.HEARTBEAT_TASK_LAST_RUN_MAX_H, minutes=1)
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", past_boundary, None), raising=True)

    chk = dr._heartbeat_task_last_run_check(now=now)

    assert not chk.ok and chk.warn
    # WARN не валит doctor (прецедент :180) — сверка через полный run_checks/main
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", past_boundary, None), raising=True)
    assert dr.main([]) == 0


def test_lastrun_check_naive_last_run_treated_as_utc(repo, env, monkeypatch):
    naive_fresh = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) \
        - datetime.timedelta(minutes=5)
    monkeypatch.setattr(
        dr.str_reader, "read_task_state",
        lambda name, **kw: dr.str_reader.TaskState(True, "Ready", naive_fresh, None), raising=True)

    chk = _lastrun_check(dr.run_checks())

    assert chk.ok and not chk.warn
