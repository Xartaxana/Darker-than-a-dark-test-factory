"""spec-p3-second-emulator N1, критик-раунд B1 (2026-08-20): Resolve-DeviceSerial
(приоритет -Serial > $env:ANDROID_SERIAL > $env:AO3_DEVICE > "emulator-5554")
+ standalone-адресация Install-App/Wait-PackageServiceReady/Install-MitmCA как
САМОСТОЯТЕЛЬНЫХ канонических точек входа (каждая - свой powershell-процесс, НЕ
наследует $env:ANDROID_SERIAL, выставленный Start-Emulator в ДРУГОМ процессе,
констрейнт 6: tasks.ps1 дот-сорсится на каждый вызов).

Device-free: реальный adb/эмулятор НЕ запускается. Install-App/
Wait-PackageServiceReady используют -Adb seam, подставляющий
scripts/tests/fixtures/fake_adb.ps1 (заглушка, логирует адресацию в файл) -
никакой живой процесс/устройство не трогается (N1 NON-GOALS)."""
from __future__ import annotations

from pathlib import Path

from _ps1_helpers import TASKS_PS1, dot_source_prefix, run_ps

FAKE_ADB = Path(__file__).resolve().parent / "fixtures" / "fake_adb.ps1"


def _source() -> str:
    return TASKS_PS1.read_text(encoding="utf-8-sig")


# --- Resolve-DeviceSerial: приоритет параметр > ANDROID_SERIAL > AO3_DEVICE > дефолт ---


def test_explicit_serial_param_wins_over_both_env_vars():
    cp = run_ps(
        dot_source_prefix() +
        "$env:ANDROID_SERIAL = 'emulator-9998'; $env:AO3_DEVICE = 'emulator-9997'; "
        "$r = Resolve-DeviceSerial -Serial 'emulator-1234'; "
        "Write-Output \"RESULT=$r ENV=$env:ANDROID_SERIAL\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "RESULT=emulator-1234 ENV=emulator-1234" in cp.stdout


def test_android_serial_env_wins_over_ao3_device_when_no_param():
    cp = run_ps(
        dot_source_prefix() +
        "$env:ANDROID_SERIAL = 'emulator-9998'; $env:AO3_DEVICE = 'emulator-9997'; "
        "$r = Resolve-DeviceSerial; "
        "Write-Output \"RESULT=$r ENV=$env:ANDROID_SERIAL\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "RESULT=emulator-9998 ENV=emulator-9998" in cp.stdout


def test_ao3_device_used_when_android_serial_absent():
    cp = run_ps(
        dot_source_prefix() +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        "$env:AO3_DEVICE = 'emulator-5578'; "
        "$r = Resolve-DeviceSerial; "
        "Write-Output \"RESULT=$r ENV=$env:ANDROID_SERIAL\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "RESULT=emulator-5578 ENV=emulator-5578" in cp.stdout


def test_default_emulator_5554_when_nothing_set():
    cp = run_ps(
        dot_source_prefix() +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        "Remove-Item Env:\\AO3_DEVICE -ErrorAction SilentlyContinue; "
        "$r = Resolve-DeviceSerial; "
        "Write-Output \"RESULT=$r ENV=$env:ANDROID_SERIAL\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "RESULT=emulator-5554 ENV=emulator-5554" in cp.stdout


def test_empty_string_serial_param_treated_as_absent_falls_through_chain():
    """Граница: пустая строка ("" - PowerShell-дефолт непереданного -Serial) -
    НЕ валидный явный серийник, цепочка фолбэка продолжает работать (иначе
    Install-App/Wait-PackageServiceReady, вызванные БЕЗ -Serial, зафиксировали
    бы пустую строку)."""
    cp = run_ps(
        dot_source_prefix() +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        "$env:AO3_DEVICE = 'emulator-5580'; "
        "$r = Resolve-DeviceSerial -Serial ''; "
        "Write-Output \"RESULT=$r\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "RESULT=emulator-5580" in cp.stdout


# --- -Serial/-Port параметры существуют на Install-App/Wait-PackageServiceReady/Install-MitmCA ---


def test_install_app_and_wait_package_service_ready_and_install_mitm_ca_have_serial_and_port_params():
    cp = run_ps(
        dot_source_prefix() +
        "foreach ($fn in 'Install-App','Wait-PackageServiceReady','Install-MitmCA') { "
        "  $params = (Get-Command $fn).Parameters.Keys; "
        "  Write-Output \"${fn}: Serial=$('Serial' -in $params) Port=$('Port' -in $params)\" "
        "}"
    )
    assert cp.returncode == 0, cp.stderr
    for fn in ("Install-App", "Wait-PackageServiceReady", "Install-MitmCA"):
        assert f"{fn}: Serial=True Port=True" in cp.stdout, cp.stdout


# --- standalone Install-App/Wait-PackageServiceReady адресуют AO3_DEVICE (device-free, fake adb) ---


def test_standalone_install_app_with_ao3_device_env_addresses_that_serial(tmp_path):
    """B1 DoD: 'standalone Install-App при заданном AO3_DEVICE адресует именно
    его' - через тот же инжектируемый seam-приём, что у жнеца (-Adb, паттерн
    Get-AdbOutput -Adb). Новый powershell-процесс (run_ps), НЕ наследующий
    $env:ANDROID_SERIAL ни от какого предыдущего Start-Emulator - только
    AO3_DEVICE стоит в окружении ДО вызова, как если бы вызывающий (человек/
    скрипт конвейера) настроил адресацию через settings.py DEVICE_NAME без
    явного -Serial/-Port аргумента."""
    log_file = tmp_path / "fake_adb_calls.log"
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        "$env:AO3_DEVICE = 'emulator-5578'; "
        f"$env:FAKE_ADB_LOG = '{log_file}'; "
        f"Install-App -Adb '{FAKE_ADB}'; "
        "Write-Output 'CALL_DONE'"
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "CALL_DONE" in cp.stdout
    assert log_file.exists(), "fake_adb.ps1 не записал лог вызовов"
    lines = log_file.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) >= 2, f"ожидались минимум 2 вызова (pm path android + install): {lines}"
    for line in lines:
        serial, _, args = line.partition("|")
        assert serial == "emulator-5578", f"вызов адресован не туда: {line}"
    assert any("path" in l for l in lines), lines
    assert any("install" in l for l in lines), lines


def test_standalone_wait_package_service_ready_with_explicit_port_overrides_ao3_device(tmp_path):
    """-Port явно данный параметр (второй приоритет после -Serial в
    Resolve-DeviceSerial) должен адресовать `emulator-<Port>`, даже когда
    AO3_DEVICE стоит в env на другое значение."""
    log_file = tmp_path / "fake_adb_calls.log"
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        "$env:AO3_DEVICE = 'emulator-5578'; "
        f"$env:FAKE_ADB_LOG = '{log_file}'; "
        f"Wait-PackageServiceReady -Port 5556 -Adb '{FAKE_ADB}' -TimeoutSec 5 | Out-Null; "
        "Write-Output 'CALL_DONE'"
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "CALL_DONE" in cp.stdout
    lines = log_file.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) >= 1
    for line in lines:
        serial, _, _args = line.partition("|")
        assert serial == "emulator-5556", f"вызов адресован не туда: {line}"


# --- Install-MitmCA резолвит серийник ДО проверки CA PEM (device-free пин) ---


def test_install_mitm_ca_resolves_serial_before_ca_pem_check(tmp_path):
    """Полный прогон Install-MitmCA требует реальный git-bash/CA PEM (вне
    scope device-free юнит-теста) - но Resolve-DeviceSerial вызывается ПЕРВОЙ
    строкой ТЕЛА функции, до проверки CA PEM (структурно) - пин доказывает
    это ФУНКЦИОНАЛЬНО: с заведомо отсутствующим CA PEM функция бросает
    ОЖИДАЕМУЮ ошибку 'CA PEM не найден', но $env:ANDROID_SERIAL к этому
    моменту уже выставлен на -Port-переданный серийник."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Remove-Item Env:\\ANDROID_SERIAL -ErrorAction SilentlyContinue; "
        f"$env:USERPROFILE = '{tmp_path}'; "  # гарантированно нет .mitmproxy/mitmproxy-ca-cert.pem
        "try { Install-MitmCA -Port 5556 -ErrorAction Stop; Write-Output 'NO_THROW' } "
        "catch { Write-Output \"CAUGHT: $($_.Exception.Message)\" }; "
        "Write-Output \"SERIAL_AFTER=$env:ANDROID_SERIAL\""
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "CAUGHT: CA PEM не найден" in cp.stdout
    assert "SERIAL_AFTER=emulator-5556" in cp.stdout


# --- структурная сверка: Resolve-DeviceSerial вызывается первой строкой тела ---


def test_resolve_device_serial_called_first_in_install_app_and_wait_package_service_ready():
    text = _source()
    install_app_body = text.split("function Install-App", 1)[1].split("function Invoke-Smoke", 1)[0]
    wait_pkg_body = text.split("function Wait-PackageServiceReady", 1)[1].split("function Install-App", 1)[0]
    assert "Resolve-DeviceSerial -Serial" in install_app_body
    assert "Resolve-DeviceSerial -Serial" in wait_pkg_body
    # вызывается ДО первого & $Adb (иначе adb-вызов ушёл бы неадресованным)
    assert install_app_body.index("Resolve-DeviceSerial") < install_app_body.index("& $Adb")
    assert wait_pkg_body.index("Resolve-DeviceSerial") < wait_pkg_body.index("& $Adb")
