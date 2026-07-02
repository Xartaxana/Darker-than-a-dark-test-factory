# Раннеры тестового фреймворка. Использование:
#   . D:\AO3_tests\scripts\tasks.ps1
#   Start-Emulator ; Start-Appium ; Invoke-Smoke
# Требует предварительно: . D:\AO3_tests\scripts\env.ps1 (для JAVA_HOME/ANDROID_HOME/PATH)
$ErrorActionPreference = "Stop"
$root = "D:\AO3_tests"
. "$root\scripts\env.ps1"
$venv = "$root\framework\.venv\Scripts"

function Start-Emulator {
    Start-Process -FilePath "$env:ANDROID_HOME\emulator\emulator.exe" `
        -ArgumentList "-avd","ao3_test_api34","-no-boot-anim","-gpu","swiftshader_indirect" `
        -WindowStyle Minimized
    Write-Host "Waiting for device boot..." -ForegroundColor Cyan
    & "$env:ANDROID_HOME\platform-tools\adb.exe" wait-for-device
    do { Start-Sleep 2; $b = (& "$env:ANDROID_HOME\platform-tools\adb.exe" shell getprop sys.boot_completed).Trim() } while ($b -ne "1")
    Write-Host "Emulator booted." -ForegroundColor Green
}

function Start-Appium {
    Push-Location "$root\tools\appium"
    Start-Process -FilePath "npx" `
        -ArgumentList "appium","--log-level","warn","--allow-insecure","uiautomator2:chromedriver_autodownload" `
        -WindowStyle Minimized
    Pop-Location
    Start-Sleep 6
    Write-Host "Appium started on :4723" -ForegroundColor Green
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

function Show-Report {
    Push-Location "$root\framework"
    & "$venv\python.exe" -m allure serve allure-results 2>$null
    Pop-Location
}

Write-Host "Tasks loaded: Start-Emulator, Start-Appium, Install-App, Invoke-Smoke, Invoke-Suite, Show-Report" -ForegroundColor Green
