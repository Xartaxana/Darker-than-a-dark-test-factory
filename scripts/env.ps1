# Настройка окружения тестового стенда. Использование: . D:\AO3_tests\scripts\env.ps1
$root = "D:\AO3_tests"
$env:JAVA_HOME        = "$root\tools\jdk-21.0.11+10"
$env:ANDROID_HOME     = "$root\tools\android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_AVD_HOME = "$root\tools\avd"
$env:PATH = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:PATH"

# Start-Ao3Emulator и Install-Ao3Apk УДАЛЕНЫ (2026-07-18, Lead-диспатч,
# AT-BUG-013/014 класс): незащищённые дубли канонических Start-Emulator /
# Install-App из scripts/tasks.ps1 - без гигиены локов, фолбэка, mitm-CA,
# ожидания готовности package-сервиса (Wait-PackageServiceReady). Не вызывались
# ни одним агентом/скриптом репозитория (сверено grep'ом перед удалением) -
# только эти дубли-функции сами по себе. Используй канонические:
#   . D:\AO3_tests\scripts\tasks.ps1; Start-Emulator -WritableSystem
#   . D:\AO3_tests\scripts\tasks.ps1; Install-App
function Start-AppiumServer { Push-Location "$root\tools\appium"; npx appium; Pop-Location }
function Build-Ao3Apk { Push-Location "$root\app-under-test"; .\gradlew.bat assembleDebug; Pop-Location }

Write-Host "AO3 test env ready: JAVA_HOME, ANDROID_HOME, adb/emulator in PATH" -ForegroundColor Green
