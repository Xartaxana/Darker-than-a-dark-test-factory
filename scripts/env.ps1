# Настройка окружения тестового стенда. Использование: . D:\AO3_tests\scripts\env.ps1
$root = "D:\AO3_tests"
$env:JAVA_HOME        = "$root\tools\jdk-21.0.11+10"
$env:ANDROID_HOME     = "$root\tools\android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_AVD_HOME = "$root\tools\avd"
$env:PATH = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:PATH"

function Start-Ao3Emulator { emulator -avd ao3_test_api34 -writable-system @args }
function Start-AppiumServer { Push-Location "$root\tools\appium"; npx appium; Pop-Location }
function Build-Ao3Apk { Push-Location "$root\app-under-test"; .\gradlew.bat assembleDebug; Pop-Location }
function Install-Ao3Apk { adb install -r "$root\app-under-test\app\build\outputs\apk\debug\app-debug.apk" }

Write-Host "AO3 test env ready: JAVA_HOME, ANDROID_HOME, adb/emulator in PATH" -ForegroundColor Green
