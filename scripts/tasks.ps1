# Раннеры тестового фреймворка. Использование:
#   . D:\AO3_tests\scripts\tasks.ps1
#   Start-Emulator ; Start-Appium ; Invoke-Smoke
# Требует предварительно: . D:\AO3_tests\scripts\env.ps1 (для JAVA_HOME/ANDROID_HOME/PATH)
$ErrorActionPreference = "Stop"
$root = "D:\AO3_tests"
. "$root\scripts\env.ps1"
$venv = "$root\framework\.venv\Scripts"

function Clear-EmulatorStaleLocks {
    # AT-BUG-012: крэш quickboot-буда (см. Start-Emulator) оставляет стейл-локи
    # AVD, которые путают следующий подъём. Чистим ПЕРЕД стартом (штатная
    # гигиена) и повторно после детекта крэша (перед фолбэком). Идемпотентна:
    # отсутствие файлов — не ошибка.
    #
    # AT-BUG-014: hardware-qemu.ini.lock иногда оказывается НЕПУСТОЙ ДИРЕКТОРИЕЙ
    # (внутри лежит файл pid) — так остаётся после жёсткого килла зависшего
    # qemu-system-x86_64. Remove-Item -Force без -Recurse на непустой директории
    # падает NullReferenceException, которую -ErrorAction SilentlyContinue НЕ
    # гасит, и это останавливает весь Start-Emulator. Ветвим по типу элемента.
    $avdDir = "$root\tools\avd\ao3_test_api34.avd"
    foreach ($name in @("multiinstance.lock", "hardware-qemu.ini.lock")) {
        $p = Join-Path $avdDir $name
        if (Test-Path $p) {
            if (Test-Path $p -PathType Container) {
                Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
            } else {
                Remove-Item $p -Force -ErrorAction SilentlyContinue
            }
            Write-Host "Removed stale lock: $p" -ForegroundColor Yellow
        }
    }
}

function Start-Emulator {
    # -WritableSystem: нужен для replay-режима (установка CA mitmproxy в системное
    # хранилище, scripts/install-mitm-ca.sh). Для live-прогонов не требуется.
    #
    # AT-BUG-012: quickboot-снапшот default_boot нестабилен на этом WHPX-хосте —
    # qemu-процесс тихо исчезает к ~20-й секунде буда (голый `adb wait-for-device`
    # в этом случае висит НАВСЕГДА, устройство не появится никогда), плюс после
    # крэша остаются стейл-локи. Воспроизведено 6+ раз за 2026-07-10..07-17
    # разными сессиями/агентами на одном и том же снапшоте без его пересоздания —
    # это не единичная порченая запись, а системная хрупкость снапшот-restore на
    # этом хосте (docs/environment-setup.md, AT-BUG-012). Обход дешёвый и
    # проверенный: чистый `-no-snapshot-load` поднимается штатно каждый раз.
    # Поэтому вместо блокирующего wait-for-device — поллинг с таймаутом:
    # не дождались устройства/процесс умер → автофолбэк на чистую загрузку.
    param([switch]$WritableSystem, [int]$SnapshotBootTimeoutSec = 45)
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $emu = "$env:ANDROID_HOME\emulator\emulator.exe"

    Clear-EmulatorStaleLocks

    $emuArgs = @("-avd","ao3_test_api34","-no-boot-anim","-gpu","swiftshader_indirect")
    if ($WritableSystem) { $emuArgs += "-writable-system" }

    $proc = Start-Process -FilePath $emu -ArgumentList $emuArgs -WindowStyle Minimized -PassThru
    Write-Host "Waiting for device boot (snapshot, up to ${SnapshotBootTimeoutSec}s)..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds($SnapshotBootTimeoutSec)
    $deviceUp = $false
    do {
        Start-Sleep 2
        if ($proc.HasExited) { break }
        $lines = & $adb devices
        $deviceUp = @($lines | Select-Object -Skip 1 | Where-Object { $_ -match '\sdevice$' }).Count -gt 0
    } while (-not $deviceUp -and (Get-Date) -lt $deadline)

    if (-not $deviceUp) {
        # Снапшот-буд не поднял устройство в отведённое время — по AT-BUG-012
        # это известный класс крэша quickboot на этом хосте, не зависание,
        # которое стоит пережидать дольше. Явный автофолбэк, не молча.
        Write-Warning ("Start-Emulator: снапшот-буд не поднял устройство за ${SnapshotBootTimeoutSec}s " +
            "(AT-BUG-012: известная нестабильность quickboot-снапшота default_boot на этом хосте) - " +
            "фолбэк на чистую загрузку -no-snapshot-load.")
        # AT-BUG-014 (корень): $proc — это Start-Process-launcher emulator.exe, а НЕ
        # фактический дочерний qemu-system-x86_64.exe (отдельный процесс, отдельный
        # PID). На этом хосте qemu переживает килл лаунчера (наблюдалось 30+ минут) и
        # легитимно держит hardware-qemu.ini.lock, из-за чего Clear-EmulatorStaleLocks
        # ниже спотыкается о ЖИВОЙ, а не мёртвый артефакт при каждой следующей попытке.
        # Убиваем и лаунчер, и его прямых qemu-детей, и подчищаем возможных
        # осиротевших qemu-процессов этого же AVD по командной строке (страховка на
        # случай, если родственная связь уже разорвана).
        if (-not $proc.HasExited) {
            $qemuChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match 'qemu-system' }
            foreach ($child in $qemuChildren) {
                Write-Host "Killing qemu-system child process (PID $($child.ProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'qemu-system' -and $_.CommandLine -match 'ao3_test_api34' } |
            ForEach-Object {
                Write-Host "Killing orphaned qemu-system process for ao3_test_api34 (PID $($_.ProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
        Start-Sleep 2
        Clear-EmulatorStaleLocks
        $fallbackArgs = $emuArgs + "-no-snapshot-load"
        $proc = Start-Process -FilePath $emu -ArgumentList $fallbackArgs -WindowStyle Minimized -PassThru
        & $adb wait-for-device
    }

    do { Start-Sleep 2; $b = (& $adb shell getprop sys.boot_completed).Trim() } while ($b -ne "1")
    Write-Host "Emulator booted." -ForegroundColor Green
    if ($WritableSystem) {
        # Автовызов сразу после boot_completed этого же старта — гарантированно
        # чистая загрузка (install-mitm-ca.sh рассчитан именно на неё: повторный
        # прогон без перезагрузки эмулятора копит tmpfs-mount'ы, см. шапку скрипта).
        # Поэтому идемпотентность обеспечивается местом вызова, а не самим скриптом:
        # Install-MitmCA здесь вызывается ровно один раз за один буд эмулятора.
        Write-Host "Installing mitmproxy CA (writable-system boot)..." -ForegroundColor Cyan
        Install-MitmCA
    }
}

function Install-MitmCA {
    # Ставит CA mitmproxy в системное хранилище доверия Android (scripts/install-mitm-ca.sh,
    # docs/environment-setup.md, раздел replay). Требует чистую загрузку -writable-system
    # эмулятора (см. Start-Emulator) — сам скрипт рассчитан ровно на неё.
    $caPem = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"
    if (-not (Test-Path $caPem)) {
        throw "CA PEM не найден: $caPem - сначала запусти mitmdump (он генерирует CA при первом старте), затем повтори Install-MitmCA."
    }
    $env:ADB = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $bash = (Get-Command bash -ErrorAction SilentlyContinue).Source
    if (-not $bash) { $bash = "C:\Program Files\Git\bin\bash.exe" }
    if (-not (Test-Path $bash)) { throw "bash.exe не найден (ни в PATH, ни по фоллбэку C:\Program Files\Git\bin\bash.exe), Install-MitmCA требует git-bash." }
    & $bash "$root\scripts\install-mitm-ca.sh"
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "install-mitm-ca.sh завершился с кодом $code" }
}

function Start-Appium {
    param([int]$TimeoutSeconds = 60)
    Push-Location "$root\tools\appium"
    # "npx" (без расширения) через Start-Process на некоторых машинах резолвится не в
    # npx.cmd, а в постороннюю ShellExecute-ассоциацию (наблюдалось: открывался Notepad).
    # npx.cmd — однозначный путь к реальному исполняемому файлу.
    Start-Process -FilePath "npx.cmd" `
        -ArgumentList "appium","--log-level","warn","--allow-insecure","uiautomator2:chromedriver_autodownload" `
        -WindowStyle Minimized
    Pop-Location
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep 2
        try { $ready = (Invoke-WebRequest -Uri "http://127.0.0.1:4723/status" -UseBasicParsing -TimeoutSec 3).Content -match '"ready":true' } catch { $ready = $false }
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) { throw "Appium not ready after ${TimeoutSeconds}s (http://127.0.0.1:4723/status)" }
    Write-Host "Appium started and ready on :4723" -ForegroundColor Green
}

function Stop-NodeProcesses {
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
    Write-Host "Node processes stopped." -ForegroundColor Green
}

function Wait-PackageServiceReady {
    # AT-BUG-013: sys.boot_completed=1 (см. Start-Emulator) НЕ гарантирует, что
    # гостевой package-сервис уже поднялся - Install-App сразу после буда может
    # словить `cmd: Can't find service: package`, хотя устройство по Get-Device
    # уже есть. Фактический сигнал готовности - устойчивый непустой ответ
    # `pm path android` (пустой вывод/ошибка = сервис ещё не готов). Короткий
    # поллинг с таймаутом, явное предупреждение при неудаче - НЕ молчаливый
    # бесконечный retry: вызывающий код (Install-App) сам решает, продолжать ли.
    param([int]$TimeoutSec = 30)
    $adb = "$env:ANDROID_HOME\platform-tools\adb.exe"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $ready = $false
    do {
        $out = & $adb shell pm path android 2>$null
        if ($out -and (($out -join "") -match 'package:')) { $ready = $true; break }
        Start-Sleep 1
    } while ((Get-Date) -lt $deadline)
    if (-not $ready) {
        Write-Warning ("Wait-PackageServiceReady: package-сервис гостя не ответил за ${TimeoutSec}s " +
            "('pm path android' пуст/ошибка) - AT-BUG-013: следующий Install-App может упасть " +
            "'cmd: Can't find service: package'.")
    }
    return $ready
}

function Install-App {
    # AT-BUG-013: короткое ожидание готовности package-сервиса перед первой
    # попыткой install - гонка с boot_completed=1 (см. Wait-PackageServiceReady).
    param([int]$PackageServiceTimeoutSec = 30)
    Wait-PackageServiceReady -TimeoutSec $PackageServiceTimeoutSec | Out-Null
    & "$env:ANDROID_HOME\platform-tools\adb.exe" install -r "$root\app-under-test\app\build\outputs\apk\debug\app-debug.apk"
}

function Invoke-Smoke {
    Push-Location "$root\framework"
    $env:AO3_MODE = "live"
    & "$venv\python.exe" -m pytest -m p0 @args
    Pop-Location
}

function Invoke-Suite {
    param([string]$Mark = "p0")
    Push-Location "$root\framework"
    & "$venv\python.exe" -m pytest -m $Mark @args
    Pop-Location
}

function Invoke-Pytest {
    # Каноничный запуск произвольных pytest-аргументов из framework/ (venv-python).
    # Агентам НЕ собирать свои вариации ". env.ps1; <путь к python> -m pytest ..." —
    # каждая новая форма не совпадает с allowlist и требует подтверждения.
    Push-Location "$root\framework"
    if (-not $env:AO3_MODE) { $env:AO3_MODE = "live" }
    & "$venv\python.exe" -m pytest @args
    $code = $LASTEXITCODE
    Pop-Location
    Write-Host "PYTEST_EXIT=$code"
}

function Show-Report {
    Push-Location "$root\framework"
    & "$venv\python.exe" -m allure serve allure-results 2>$null
    Pop-Location
}

function Get-Device {
    # Однозначная проверка присутствия устройства. Полный путь к adb.exe — НЕ зависит
    # от PATH, поэтому работает даже там, где голый `adb` не резолвится. Печатает по
    # строке "DEVICE: <serial>" на каждое устройство в состоянии `device`, либо ровно
    # "NO DEVICE". ВАЖНО (CLAUDE.md permission-hygiene п.6): пустой/ошибочный вывод
    # голого `adb` вне PATH НЕЛЬЗЯ принимать за «устройства нет» — эта функция даёт
    # однозначный сигнал, используй её для любого вывода о присутствии устройства.
    $lines = & "$env:ANDROID_HOME\platform-tools\adb.exe" devices
    $serials = @($lines | Select-Object -Skip 1 |
        Where-Object { $_ -match '\sdevice$' } |
        ForEach-Object { ($_ -split '\s+')[0] })
    if ($serials.Count -gt 0) { foreach ($s in $serials) { Write-Host "DEVICE: $s" } }
    else { Write-Host "NO DEVICE" }
}

Write-Host "Tasks loaded: Start-Emulator, Install-MitmCA, Start-Appium, Stop-NodeProcesses, Install-App, Invoke-Smoke, Invoke-Suite, Invoke-Pytest, Show-Report, Get-Device" -ForegroundColor Green
