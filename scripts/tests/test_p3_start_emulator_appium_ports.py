"""spec-p3-second-emulator N1: `Start-Emulator -Port`/`Start-Appium -Port`
адверсариальная батарея + `-Memory` + back-compat "занятый порт = явная
ошибка" + `Set-EmulatorSessionState` ключевание by_serial + qemu-килл якорь
`-avd\\s+<name>\\b` (B5).

НИКАКОГО реального emulator.exe/npx/adb не запускается: невалидные -Port
падают на PARAMETER BINDING (ДО тела функции - штатное поведение PowerShell
для [ValidateRange]/[ValidateScript], проверено эмпирически) - безопасно
вызывать функции напрямую с battery-значениями. Валидные граничные значения
(1/65535 для Appium; 5554/5584 для эмулятора) проверяются РЕФЛЕКСИЕЙ на
атрибутах параметра (без вызова тела) - вызов с валидным портом запустил бы
реальный процесс (npx/emulator.exe), что запрещено (N1: БЕЗ live-прогона).
"""
from __future__ import annotations

from _ps1_helpers import dot_source_prefix, run_ps


# --- Start-Appium -Port: 0/1/65535/65536/-1/"abc"/пусто/пробел ---


def test_start_appium_port_out_of_range_throws_at_binding():
    for bad in ("0", "-1", "65536"):
        cp = run_ps(
            dot_source_prefix() +
            f"try {{ Start-Appium -Port {bad} -ErrorAction Stop; Write-Output 'NO_THROW' }} "
            "catch { Write-Output 'THROWN' }"
        )
        assert cp.returncode == 0
        assert "THROWN" in cp.stdout, f"port={bad}: {cp.stdout}/{cp.stderr}"
        assert "NO_THROW" not in cp.stdout


def test_start_appium_port_non_numeric_throws_at_binding():
    for bad in ("'abc'", "''", "' '"):
        cp = run_ps(
            dot_source_prefix() +
            f"try {{ Start-Appium -Port {bad} -ErrorAction Stop; Write-Output 'NO_THROW' }} "
            "catch { Write-Output 'THROWN' }"
        )
        assert cp.returncode == 0
        assert "THROWN" in cp.stdout, f"port={bad}: {cp.stdout}/{cp.stderr}"


def test_start_appium_port_valid_boundaries_are_in_domain():
    """1 и 65535 - валидные граничные значения (НЕ вызываем тело функции -
    реальный npx не должен запускаться в юнит-тесте)."""
    cp = run_ps(
        dot_source_prefix() +
        "(Get-Command Start-Appium).Parameters['Port'].Attributes | "
        "Where-Object { $_ -is [System.Management.Automation.ValidateRangeAttribute] } | "
        "ForEach-Object { Write-Output \"MIN=$($_.MinRange) MAX=$($_.MaxRange)\" }"
    )
    assert cp.returncode == 0
    assert "MIN=1 MAX=65535" in cp.stdout


# --- -TimeoutSeconds дефолт 150 (батч мелочей П3, 2026-08-21): холодный
# npx-старт ВТОРОГО Appium (:4725) занимал ~90-120с, 60с не хватало
# (runs/N3-p3-postmerge-device-witness-2026-08-21.md §1). Пин - СТАТИЧЕСКИЙ
# разбор текста/AST tasks.ps1, НЕ живой вызов Start-Appium (реальный npx
# порождать в юнит-тесте запрещено).


def test_start_appium_timeout_seconds_default_is_150():
    """Дефолт параметра -TimeoutSeconds - 150 (было 60). Читаем DefaultValue
    прямо из AST параметра рефлексией - НЕ вызываем тело функции."""
    cp = run_ps(
        dot_source_prefix() +
        "$ast = (Get-Command Start-Appium).ScriptBlock.Ast; "
        "$p = $ast.Body.ParamBlock.Parameters | "
        "  Where-Object { $_.Name.VariablePath.UserPath -eq 'TimeoutSeconds' }; "
        "Write-Output \"DEFAULT=$($p.DefaultValue.Extent.Text)\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "DEFAULT=150" in cp.stdout


def test_start_appium_timeout_seconds_flows_into_deadline_not_hardcoded():
    """Граница M6: явный -TimeoutSeconds на вызове ПОБЕЖДАЕТ дефолт - параметр
    не хардкожен, тело функции использует переменную `$TimeoutSeconds`
    (не литерал), значит явный аргумент действительно течёт в дедлайн-цикл.
    Проверено рефлексией параметра (ParameterMetadata.SwitchParameter=False,
    обычный позиционно-независимый параметр без ValidateScript, запрещающего
    произвольные значения) + структурным разбором источника - без реального
    вызова (живой npx под юнит-тестом запрещён)."""
    cp = run_ps(
        dot_source_prefix() +
        "$param = (Get-Command Start-Appium).Parameters['TimeoutSeconds']; "
        "Write-Output \"TYPE=$($param.ParameterType.Name)\"; "
        "Write-Output \"HAS_VALIDATE_SCRIPT=$(($param.Attributes | "
        "  Where-Object { $_ -is [System.Management.Automation.ValidateScriptAttribute] }).Count -gt 0)\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "TYPE=Int32" in cp.stdout
    assert "HAS_VALIDATE_SCRIPT=False" in cp.stdout  # ничто не отбраковывает явный аргумент
    text = _ps1_helpers_source()
    start_appium_body = text.split("function Start-Appium", 1)[1].split("function Get-DeviceSerials", 1)[0]
    # дедлайн строится ИЗ переменной параметра, не из literal 60/150 -
    # явный -TimeoutSeconds на вызове реально долетает до цикла ожидания.
    assert "$deadline = (Get-Date).AddSeconds($TimeoutSeconds)" in start_appium_body
    assert "AddSeconds(60)" not in start_appium_body
    assert "AddSeconds(150)" not in start_appium_body


# --- Start-Emulator -Port: домен свой (чётный, 5554-5584) ---


def test_start_emulator_port_boundary_and_beyond():
    cp = run_ps(
        dot_source_prefix() +
        "$vsa = (Get-Command Start-Emulator).Parameters['Port'].Attributes | "
        "Where-Object { $_ -is [System.Management.Automation.ValidateScriptAttribute] }; "
        "foreach ($v in 5552,5554,5555,5584,5586) { "
        "  try { $v | ForEach-Object $vsa.ScriptBlock | Out-Null; Write-Output \"$v=OK\" } "
        "  catch { Write-Output \"$v=THROWN\" } "
        "}"
    )
    assert cp.returncode == 0, cp.stderr
    out = cp.stdout
    assert "5552=THROWN" in out   # ниже диапазона (чётный, но вне 5554-5584)
    assert "5554=OK" in out       # нижняя граница
    assert "5555=THROWN" in out   # нечётный внутри диапазона
    assert "5584=OK" in out       # верхняя граница
    assert "5586=THROWN" in out   # выше диапазона


def test_start_emulator_repeated_launch_on_occupied_port_is_explicit_error(tmp_path):
    """Back-compat-строка плана: РАНЬШЕ эмулятор тихо уезжал на следующий
    свободный порт; ТЕПЕРЬ повторный запуск на занятом консольном порте -
    явная ошибка, до Clear-EmulatorStaleLocks/Start-Process (никакого
    процесса не порождается)."""
    port = 5566
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        f"$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, {port}); "
        "$listener.Start(); "
        "try { "
        f"  try {{ Start-Emulator -Port {port} -AvdName 'fake_avd_for_test' "
        # RAM-гейт выключен явно - порт != 5554 включает дефолт 3.5 GB, и под
        # нагрузкой хоста (параллельные сессии/эмуляторы) проба абортила бы
        # на РЕАЛЬНОЙ RAM ДО occupancy-throw (3-й M1-спутник, найдено критик-
        # входом батча миграции 2026-08-21: РАНЬШЕ все 5 ассертов проходили
        # даже под RAM-abort, потому что его сообщение тоже содержит номер
        # порта и тоже не создаёт state-файл — ложно-зелёная проба).
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 0 "
        "-ErrorAction Stop; "
        "        Write-Output 'NO_THROW' } "
        "  catch { Write-Output \"THROWN: $($_.Exception.Message)\" } "
        "} finally { $listener.Stop() }; "
        f"Write-Output \"STATE_FILE_EXISTS=$(Test-Path '{tmp_path}\\state\\emulator-session.json')\""
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "THROWN:" in cp.stdout
    assert "NO_THROW" not in cp.stdout
    assert f"{port}" in cp.stdout  # сообщение называет занятый порт
    # Различающий оракул (не просто номер порта — RAM-гейт тоже его называет,
    # см. комментарий выше): текст occupancy-throw специфичен ("уже занят"),
    # RAM-гейт называет причину иначе ("RAM-гейт", "free ... GB").
    assert "уже занят" in cp.stdout
    assert "RAM-гейт" not in cp.stdout
    # Occupancy-check стоит ДО Set-EmulatorSessionState -> state-файл не появился
    assert "STATE_FILE_EXISTS=False" in cp.stdout


def test_start_emulator_occupancy_check_is_conditional_not_unconditional_throw():
    """Граница ЗА пределами занятости: occupancy-throw структурно УСЛОВЕН
    (`if ($portOwner) { ... if ($isOrphan) { ... } else { throw ... } }`), НЕ
    вызывается напрямую с валидным свободным портом - живой Start-Process/
    emulator.exe запрещён в юнит-тесте (N1: БЕЗ live-прогона, NON-GOALS).
    Сверка по исходнику, не по вызову."""
    text = _ps1_helpers_source()
    start_emulator_body = text.split("function Start-Emulator", 1)[1].split("function Install-MitmCA", 1)[0]
    assert "if ($portOwner) {" in start_emulator_body
    assert "if ($isOrphan) {" in start_emulator_body
    assert "уже занят" in start_emulator_body


# --- B2 (критик-раунд, 2026-08-20): орфан-qemu port-occupancy ветка ---
# Test-QemuPortOwnerIsOrphan - ЧИСТАЯ функция (см. tasks.ps1), тестируется
# напрямую БЕЗ Start-Process/emulator.exe/реального adb - никакой live-
# процесс не порождается ни в одном сценарии ниже.


def test_orphan_qemu_without_live_device_is_orphan():
    """AT-BUG-012/014 класс: владелец порта - НАШ qemu (anchor совпал), но
    'adb devices' НЕ показывает наш серийник как device -> орфан, самолечение
    (НЕ throw)."""
    cp = run_ps(
        dot_source_prefix() +
        "$r = Test-QemuPortOwnerIsOrphan -OwnerIsOwnQemu $true -Serial 'emulator-5566' "
        "-AdbDevicesLines @('List of devices attached', ''); "
        "Write-Output \"ORPHAN=$r\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "ORPHAN=True" in cp.stdout


def test_own_qemu_with_live_device_is_not_orphan():
    """Владелец - наш qemu, И устройство ЖИВОЕ на этом серийнике в adb
    devices -> НЕ орфан (throw, живое устройство реально занимает порт)."""
    cp = run_ps(
        dot_source_prefix() +
        "$r = Test-QemuPortOwnerIsOrphan -OwnerIsOwnQemu $true -Serial 'emulator-5566' "
        "-AdbDevicesLines @('List of devices attached', 'emulator-5566   device', ''); "
        "Write-Output \"ORPHAN=$r\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "ORPHAN=False" in cp.stdout


def test_foreign_or_non_qemu_owner_is_never_orphan_regardless_of_adb_output():
    """Владелец - НЕ наш qemu (чужой процесс / другой AVD) -> НИКОГДА не
    орфан (throw), даже если adb devices пуст (граница: не подставляем чужой
    процесс под самолечение)."""
    cp = run_ps(
        dot_source_prefix() +
        "$r = Test-QemuPortOwnerIsOrphan -OwnerIsOwnQemu $false -Serial 'emulator-5566' "
        "-AdbDevicesLines @(); "
        "Write-Output \"ORPHAN=$r\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "ORPHAN=False" in cp.stdout


def test_orphan_branch_wired_via_injectable_seams_reaches_orphan_cleaner_not_throw(tmp_path):
    """Функциональный (не только структурный) пин на саму Start-Emulator:
    инжектируем -PortListenerResolver/-ProcessInfoResolver/-AdbDevicesProvider/
    -OrphanCleaner так, что владелец порта - ФЕЙКОВЫЙ 'наш' qemu без живого
    устройства - и убеждаемся, что OrphanCleaner ВЫЗВАН (не throw). Прогон
    останавливается ДО реального Start-Process: -OrphanCleaner сам бросает
    маркерное исключение сразу после отметки вызова - функция гарантированно
    не доходит до живого emulator.exe (N1 NON-GOALS: без live-прогона)."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "try { "
        "Start-Emulator -Port 5566 -AvdName 'fake_avd_for_test' "
        # RAM-гейт выключен явно: порт != 5554 включает дефолт 3.5 GB, и под
        # нагрузкой хоста (2 эмулятора соседних сессий) проба абортила бы на
        # РЕАЛЬНОЙ RAM до мокнутых швов (класс M1-спутников, найдено батчем
        # миграции 2026-08-21).
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 0 "
        "-PortListenerResolver { param($P) [pscustomobject]@{ OwningProcess = 4242 } } "
        "-ProcessInfoResolver { param($ProcId) [pscustomobject]@{ Name = 'qemu-system-x86_64.exe'; "
        "    CommandLine = 'qemu-system-x86_64.exe -avd fake_avd_for_test -no-boot-anim' } } "
        "-AdbDevicesProvider { param($AdbPath) @('List of devices attached', '') } "
        "-OrphanCleaner { param($Avd) Write-Output \"ORPHAN_CLEANER_CALLED_FOR=$Avd\"; "
        "    throw 'STOP_BEFORE_LIVE_START_PROCESS_MARKER' } "
        "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' "
        "} catch { Write-Output \"CAUGHT: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "ORPHAN_CLEANER_CALLED_FOR=fake_avd_for_test" in cp.stdout
    assert "CAUGHT: STOP_BEFORE_LIVE_START_PROCESS_MARKER" in cp.stdout
    assert "уже занят" not in cp.stdout  # НЕ throw-ветка (не foreign/live-device)


def test_live_device_or_foreign_owner_still_throws_via_seams_not_orphan_cleaner(tmp_path):
    """Симметричный контроль: владелец похож на наш qemu, но 'adb devices'
    показывает серийник ЖИВЫМ -> throw (OrphanCleaner НЕ вызывается вовсе -
    маркер её вызова отсутствует в выводе)."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "try { "
        "Start-Emulator -Port 5566 -AvdName 'fake_avd_for_test' "
        # RAM-гейт выключен явно - см. комментарий в тесте выше (тот же класс).
        "-MinFreeGBPreStart 0 -MinFreeGBPostStart 0 "
        "-PortListenerResolver { param($P) [pscustomobject]@{ OwningProcess = 4242 } } "
        "-ProcessInfoResolver { param($ProcId) [pscustomobject]@{ Name = 'qemu-system-x86_64.exe'; "
        "    CommandLine = 'qemu-system-x86_64.exe -avd fake_avd_for_test -no-boot-anim' } } "
        "-AdbDevicesProvider { param($AdbPath) @('List of devices attached', 'emulator-5566   device', '') } "
        "-OrphanCleaner { param($Avd) Write-Output \"ORPHAN_CLEANER_CALLED_FOR=$Avd\" } "
        "-ErrorAction Stop; "
        "Write-Output 'NO_THROW' "
        "} catch { Write-Output \"CAUGHT: $($_.Exception.Message)\" }"
    )
    cp = run_ps(cmd, timeout=30)
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert "ORPHAN_CLEANER_CALLED_FOR" not in cp.stdout
    assert "CAUGHT:" in cp.stdout and "уже занят" in cp.stdout


# --- Set-EmulatorSessionState: ключевание by_serial (констрейнт 3в) ---


def test_set_emulator_session_state_keys_by_serial_preserving_other_stacks(tmp_path):
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Set-EmulatorSessionState -Gpu 'host' -AvdName 'ao3_test_api34' -Port 5554; "
        "Set-EmulatorSessionState -Gpu 'swiftshader_indirect' -AvdName 'ao3_corridor_api34' -Port 5556; "
        f"$raw = [System.IO.File]::ReadAllText('{tmp_path}\\state\\emulator-session.json'); "
        "Write-Output $raw"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    import json
    payload = json.loads(cp.stdout.strip().splitlines()[-1])
    # флэт top-level поля - back-compat, "последний записавший стек"
    assert payload["gpu"] == "swiftshader_indirect"
    assert payload["avd_name"] == "ao3_corridor_api34"
    # by_serial несёт ОБА стека независимо
    assert payload["by_serial"]["emulator-5554"]["gpu"] == "host"
    assert payload["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api34"
    assert payload["by_serial"]["emulator-5556"]["gpu"] == "swiftshader_indirect"
    assert payload["by_serial"]["emulator-5556"]["avd_name"] == "ao3_corridor_api34"


def test_set_emulator_session_state_default_port_is_5554_backward_compat(tmp_path):
    """Пинованный AT-BUG-063 тест (framework/tests/test_device_liveness_guard_unit.py)
    зовёт `Set-EmulatorSessionState -Gpu -AvdName` БЕЗ -Port и читает флэт
    top-level поля - дефолт -Port=5554 обязан оставить их поведение
    неизменным (по факту -Port лишь определяет КЛЮЧ by_serial, не трогает
    флэт-поля)."""
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Set-EmulatorSessionState -Gpu 'host' -AvdName 'ao3_test_api29'; "
        f"$raw = [System.IO.File]::ReadAllText('{tmp_path}\\state\\emulator-session.json'); "
        "Write-Output $raw"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    import json
    payload = json.loads(cp.stdout.strip().splitlines()[-1])
    assert payload["gpu"] == "host"
    assert payload["avd_name"] == "ao3_test_api29"
    assert payload["by_serial"]["emulator-5554"]["avd_name"] == "ao3_test_api29"


def test_set_emulator_session_state_no_bom(tmp_path):
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Set-EmulatorSessionState -Gpu 'host' -AvdName 'ao3_test_api34' -Port 5554"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    raw_bytes = (tmp_path / "state" / "emulator-session.json").read_bytes()
    assert raw_bytes[:3] != b"\xef\xbb\xbf", "BOM обнаружен - json.loads на python-стороне упадёт (AT-BUG-063)"


def test_set_emulator_session_state_corrupted_existing_file_falls_back_gracefully(tmp_path):
    """by_serial read-modify-write не должен падать на нечитаемом существующем
    файле - секция начинается заново, WARNING печатается, запись всё равно
    происходит."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "emulator-session.json").write_text("{ not valid json !!!", encoding="utf-8")
    cmd = (
        dot_source_prefix(fake_root=tmp_path) +
        "Set-EmulatorSessionState -Gpu 'host' -AvdName 'ao3_test_api34' -Port 5554; "
        f"$raw = [System.IO.File]::ReadAllText('{tmp_path}\\state\\emulator-session.json'); "
        "Write-Output $raw"
    )
    cp = run_ps(cmd)
    assert cp.returncode == 0, cp.stderr
    import json
    lines = [l for l in cp.stdout.strip().splitlines() if l.strip().startswith("{")]
    payload = json.loads(lines[-1])
    assert payload["gpu"] == "host"
    assert payload["by_serial"]["emulator-5554"]["gpu"] == "host"


# --- qemu-килл якорь (B5): -avd\s+<name>\b не матчит клон с общим префиксом ---


def test_qemu_kill_anchor_does_not_match_prefixed_clone_name():
    """B5: substring-матч БЕЗ анкера заматчил бы `ao3_test_api34_2` при
    поиске `ao3_test_api34`. Регекс-паттерн, реально используемый в
    Start-Emulator (`-avd\\s+<name>\\b`), тестируется в изоляции (та же
    конструкция, что и в коде)."""
    cp = run_ps(
        dot_source_prefix() +
        "$avdName = 'ao3_test_api34'; "
        "$anchor = \"-avd\\s+$([regex]::Escape($avdName))\\b\"; "
        "$cloneCmdline = 'emulator.exe -avd ao3_test_api34_2 -no-boot-anim'; "
        "$ownCmdline = 'emulator.exe -avd ao3_test_api34 -no-boot-anim'; "
        "Write-Output \"CLONE_MATCH=$($cloneCmdline -match $anchor)\"; "
        "Write-Output \"OWN_MATCH=$($ownCmdline -match $anchor)\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "CLONE_MATCH=False" in cp.stdout
    assert "OWN_MATCH=True" in cp.stdout


def test_qemu_kill_anchor_present_in_source_replacing_unanchored_escape():
    """Структурная сверка: старый небезопасный паттерн (голый
    `[regex]::Escape($AvdName)` БЕЗ `-avd\\s+...\\b`-обёртки применительно к
    qemu-килл ветке) больше не используется для этой цели - новый anchored
    паттерн присутствует в источнике."""
    text = _ps1_helpers_source()
    assert r'"-avd\s+$([regex]::Escape($AvdName))\b"' in text


def _ps1_helpers_source() -> str:
    from _ps1_helpers import TASKS_PS1
    return TASKS_PS1.read_text(encoding="utf-8-sig")


# --- boot-oracle: матч ИМЕННО свой серийник, не "любое устройство" (N0) ---


def test_boot_oracle_regex_matches_only_own_serial_not_any_device():
    """N0-проба (2026-08-20) нашла молчаливый ложный успех: старый оракул
    матчил ЛЮБУЮ строку `\\sdevice$`, объявляя буд по ЧУЖОМУ устройству.
    Новый паттерн (`^<serial>\\s+device$`) должен матчить ТОЛЬКО свой
    серийник, не соседний/offline/иной статус."""
    cp = run_ps(
        dot_source_prefix() +
        "$serial = 'emulator-5556'; "
        "$pattern = \"^$([regex]::Escape($serial))\\s+device$\"; "
        "$ownDevice = 'emulator-5556   device'; "
        "$foreignDevice = 'emulator-5554   device'; "
        "$ownOffline = 'emulator-5556   offline'; "
        "Write-Output \"OWN_DEVICE=$($ownDevice -match $pattern)\"; "
        "Write-Output \"FOREIGN_DEVICE=$($foreignDevice -match $pattern)\"; "
        "Write-Output \"OWN_OFFLINE=$($ownOffline -match $pattern)\""
    )
    assert cp.returncode == 0, cp.stderr
    assert "OWN_DEVICE=True" in cp.stdout
    assert "FOREIGN_DEVICE=False" in cp.stdout
    assert "OWN_OFFLINE=False" in cp.stdout


def test_boot_oracle_anchored_pattern_present_in_source_not_unanchored_any_device():
    text = _ps1_helpers_source()
    assert r'"^$([regex]::Escape($serial))\s+device$"' in text
    # старый небезопасный паттерн ('\sdevice$' без anchor к серийнику,
    # использованный БЕЗ Select-Object -Skip 1 фильтра на заголовок) не
    # должен остаться в теле boot-оракула Start-Emulator.
    start_emulator_body = text.split("function Start-Emulator", 1)[1].split("function Install-MitmCA", 1)[0]
    assert "Select-Object -Skip 1 | Where-Object { $_ -match '\\sdevice$' }" not in start_emulator_body
