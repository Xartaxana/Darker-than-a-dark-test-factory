"""spec-p3-second-emulator N1: `Test-AppiumHealthy` дефолт -AppiumUrl из
параметра/env; `Start-Emulator -Memory`; ANDROID_SERIAL как единая адресация
(структурная сверка исходника - живой adb/emulator не запускается, N1 БЕЗ
live-прогона)."""
from __future__ import annotations

from _ps1_helpers import TASKS_PS1, dot_source_prefix, run_ps


def _source() -> str:
    return TASKS_PS1.read_text(encoding="utf-8-sig")


def test_test_appium_healthy_env_default_actually_reaches_listening_socket(tmp_path):
    """РЕАЛЬНЫЙ вызов (device-free, безопасный): без явного -AppiumUrl функция
    обязана бить именно по $env:APPIUM_URL. Синхронный TcpListener (не
    Start-Job - устраняет гонку планировщика раннера, найденную живым
    прогоном) на свободном порту доказывает: если /status ЗАПРОС ФИЗИЧЕСКИ
    ДОШЁЛ до этого порта (TCP accept произошёл), дефолт реально ушёл на
    env-адрес, а не на литерал :4723."""
    cp = run_ps(
        dot_source_prefix() +
        "$fakePort = 28724; "
        "$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $fakePort); "
        "$listener.Start(); "
        "$env:APPIUM_URL = \"http://127.0.0.1:$fakePort\"; "
        "$acceptTask = $listener.AcceptTcpClientAsync(); "
        # Test-AppiumHealthy бьёт по /status и получит connection-reset (никто
        # не пишет HTTP-ответ) - нас интересует ТОЛЬКО факт TCP-соединения,
        # не успешный HTTP-ответ (для этого хватит accept, полный HTTP-сервер
        # не нужен - устраняет фрагильность живого прогона выше).
        "try { Test-AppiumHealthy | Out-Null } catch {}; "
        "$accepted = $acceptTask.Wait(3000); "
        "$listener.Stop(); "
        "Write-Output \"ACCEPTED=$accepted\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "ACCEPTED=True" in cp.stdout, f"запрос не дошёл до env-порта: {cp.stdout}/{cp.stderr}"


def test_test_appium_healthy_source_default_reads_param_or_env():
    """Структурная сверка (эквивалент живого вызова без реального Appium-
    сервера): дефолт -AppiumUrl в исходнике читает $env:APPIUM_URL, не
    жёсткий литерал."""
    text = _source()
    func_body = text.split("function Test-AppiumHealthy", 1)[1].split("\n$shallowOk", 1)[0]
    assert "$env:APPIUM_URL" in func_body
    assert "http://127.0.0.1:4723" in func_body  # литерал-фолбэк остаётся


def test_test_appium_healthy_deep_caps_include_udid_pinned_to_device_name():
    """p3-n4-udid-pin-binding-guard: deep-слой Test-AppiumHealthy шлёт
    `appium:udid`, привязанный к тому же `$deviceName`, что и
    `appium:deviceName` — сиблинг оси framework/config/capabilities.py
    ::build_options (M2: без udid Appium при двух живых устройствах
    биндится на devices[0], не на адресованное)."""
    text = _source()
    func_body = text.split("function Test-AppiumHealthy", 1)[1].split("\n$shallowOk", 1)[0]
    assert '"appium:udid"            = $deviceName' in func_body


# --- Start-Emulator -Memory ---


def test_start_emulator_memory_param_exists_and_defaults_empty():
    cp = run_ps(
        dot_source_prefix() +
        "$p = (Get-Command Start-Emulator).Parameters['Memory']; "
        "Write-Output \"TYPE=$($p.ParameterType.Name)\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "TYPE=String" in cp.stdout


def test_start_emulator_memory_appended_to_emu_args_when_set():
    """Структурная сверка: `-Memory` транслируется в `-memory` аргумент
    emulator.exe ТОЛЬКО когда задан (пустая строка - без аргумента, обратная
    совместимость с вызовами без -Memory)."""
    text = _source()
    start_emulator_body = text.split("function Start-Emulator", 1)[1].split("function Install-MitmCA", 1)[0]
    assert 'if ($Memory) { $emuArgs += @("-memory","$Memory") }' in start_emulator_body


# --- ANDROID_SERIAL единая адресация (констрейнт 4) ---


def test_android_serial_set_before_getprop_and_ipv4_pin_calls():
    """Структурная сверка порядка: ANDROID_SERIAL выставляется (через
    Resolve-DeviceSerial, B1 критик-раунда) РАНЬШЕ Set-GuestIPv4Pin/getprop-
    цикла (единая адресация без пообъектного -s)."""
    text = _source()
    start_emulator_body = text.split("function Start-Emulator", 1)[1].split("function Install-MitmCA", 1)[0]
    serial_idx = start_emulator_body.index('Resolve-DeviceSerial -Serial $serial')
    # Постмерж N3: IPv4-пин уехал за шов `-GuestPinner` (тот же класс M1, что
    # getprop ниже — прямой вызов вешал "device-free" пробу на голых
    # `adb root`/`adb wait-for-device` ВНУТРИ Set-GuestIPv4Pin в главном
    # чекауте). Якорь — на МЕСТЕ ВЫЗОВА; дефолт шва проверяется ниже.
    guest_pin_idx = start_emulator_body.index('& $GuestPinner $adb')
    # M1 (критик-раунд 3): getprop-цикл теперь идёт ЧЕРЕЗ ШОВ
    # `-BootCompletedProvider` (device-free юнит post-start ветки был иначе
    # недостижим - цикл БЕЗЛИМИТЕН и вешал пробу). Якорь переставлен на МЕСТО
    # ВЫЗОВА: прежний литерал `Get-AdbOutput -Adb $adb -AdbArgs @("shell",
    # "getprop"...)` уехал в ДЕФОЛТ параметра, а дефолты объявлены в param-блоке
    # ВЫШЕ Resolve-DeviceSerial - матч по нему проверял бы порядок ОБЪЯВЛЕНИЯ
    # вместо порядка ИСПОЛНЕНИЯ. Проверяемое утверждение не изменилось:
    # ANDROID_SERIAL выставлен РАНЬШЕ, чем adb-путь его читает.
    getprop_idx = start_emulator_body.index('& $BootCompletedProvider $adb')
    assert serial_idx < guest_pin_idx
    assert serial_idx < getprop_idx
    # Дефолт шва остаётся ТЕМ ЖЕ вызовом (адресация - через env, без -s)
    assert 'Get-AdbOutput -Adb $AdbPath -AdbArgs @("shell", "getprop", "sys.boot_completed")' in start_emulator_body
    # Дефолт шва пина - дословно прежний вызов (живой прогон не меняется)
    assert 'Set-GuestIPv4Pin -Adb $AdbPath' in start_emulator_body


def test_boot_oracle_adb_devices_call_not_addressed_by_s_flag():
    """Констрейнт 4 исключение (1): оракул буда - `adb devices` БЕЗ -s (её
    ANDROID_SERIAL всё равно не фильтрует, adb devices её игнорирует по
    конструкции) - явный anchored-матч серийника в выводе, не адресация."""
    text = _source()
    start_emulator_body = text.split("function Start-Emulator", 1)[1].split("function Install-MitmCA", 1)[0]
    boot_oracle_section = start_emulator_body.split("$deviceUp = $false", 1)[1].split("if (-not $deviceUp)", 1)[0]
    # M1 (критик-раунд 3): оракул буда зовёт `adb devices` ЧЕРЕЗ объявленный шов
    # `-AdbDevicesProvider` (раньше - прямой `& $adb devices` МИМО шва, из-за
    # чего "device-free" пробы доезжали до реального adb). Дефолт шва -
    # ДОСЛОВНО прежний `& $AdbPath devices`, так что проверяемое свойство
    # (адресация НЕ через -s, а anchored-матчем серийника в выводе) сохранено.
    assert "& $AdbDevicesProvider $adb" in boot_oracle_section
    assert "-s $serial" not in boot_oracle_section
    assert "& $AdbPath devices" in start_emulator_body, "дефолт шва обязан остаться голым 'adb devices'"


def test_install_mitm_ca_relies_on_bare_adb_env_var_addressing():
    """install-mitm-ca.sh уже использует `ADB="${ADB:-adb}"` (голый adb,
    честно читает нативно понимаемый adb-переменной ANDROID_SERIAL из
    унаследованного env) - НЕ требует правки, класс-фикс закрывается
    Resolve-DeviceSerial (B1 критик-раунда) в Install-MitmCA/Start-Emulator
    (констрейнт 4)."""
    install_mitm_ca_sh = (TASKS_PS1.parent / "install-mitm-ca.sh").read_text(encoding="utf-8")
    assert 'ADB="${ADB:-adb}"' in install_mitm_ca_sh
    # Совет критика (критик-раунд, 2026-08-20): узкая сверка - только строки,
    # реально ВЫЗЫВАЮЩИЕ $ADB (не весь текст файла, где " -s " мог бы
    # встретиться где угодно вне контекста адресации), не несут явный -s
    # серийника (адресация - через унаследованный env, не CLI-флаг).
    adb_call_lines = [
        line for line in install_mitm_ca_sh.splitlines()
        if "$ADB" in line and line.strip().startswith("$ADB")
    ]
    assert len(adb_call_lines) >= 5, f"ожидалось несколько строк вызова $ADB, найдено: {adb_call_lines}"
    offending = [line for line in adb_call_lines if " -s " in line]
    assert offending == [], f"строки вызова $ADB с явным -s серийником: {offending}"
