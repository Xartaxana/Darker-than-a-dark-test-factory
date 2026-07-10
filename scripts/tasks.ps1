# Раннеры тестового фреймворка. Использование:
#   . D:\AO3_tests\scripts\tasks.ps1
#   Start-Emulator ; Start-Appium ; Invoke-Smoke
# Требует предварительно: . D:\AO3_tests\scripts\env.ps1 (для JAVA_HOME/ANDROID_HOME/PATH)
$ErrorActionPreference = "Stop"
$root = "D:\AO3_tests"
. "$root\scripts\env.ps1"
$venv = "$root\framework\.venv\Scripts"

function Start-Emulator {
    # -WritableSystem: нужен для replay-режима (установка CA mitmproxy в системное
    # хранилище, scripts/install-mitm-ca.sh). Для live-прогонов не требуется.
    param([switch]$WritableSystem)
    $emuArgs = @("-avd","ao3_test_api34","-no-boot-anim","-gpu","swiftshader_indirect")
    if ($WritableSystem) { $emuArgs += "-writable-system" }
    Start-Process -FilePath "$env:ANDROID_HOME\emulator\emulator.exe" `
        -ArgumentList $emuArgs `
        -WindowStyle Minimized
    Write-Host "Waiting for device boot..." -ForegroundColor Cyan
    & "$env:ANDROID_HOME\platform-tools\adb.exe" wait-for-device
    do { Start-Sleep 2; $b = (& "$env:ANDROID_HOME\platform-tools\adb.exe" shell getprop sys.boot_completed).Trim() } while ($b -ne "1")
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

function Install-App {
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
