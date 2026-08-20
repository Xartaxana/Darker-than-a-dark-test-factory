# spec-p3-second-emulator N1, критик-раунд B1 (2026-08-20): device-free
# заглушка adb.exe для scripts/tests - НЕ версия реального инструмента,
# используется ТОЛЬКО инжектированной через -Adb seam (Install-App/
# Wait-PackageServiceReady) в device-free юнит-тестах, доказывающих
# standalone-адресацию (Resolve-DeviceSerial) без реального устройства.
#
# Логирует "$env:ANDROID_SERIAL|<args>" ОДНОЙ строкой на КАЖДЫЙ вызов в файл
# $env:FAKE_ADB_LOG (тест читает его после вызова и проверяет серийник,
# которым адресовался вызывающий код) и отвечает каноническими фейковыми
# ответами на команды, которые реально шлют Install-App/Wait-PackageServiceReady,
# чтобы их поллинг/логика завершались быстро и детерминированно.
$logPath = $env:FAKE_ADB_LOG
if ($logPath) {
    "$($env:ANDROID_SERIAL)|$($args -join ' ')" | Add-Content -Path $logPath -Encoding UTF8
}
if ($args -contains 'path') {
    Write-Output 'package:/system/app/Fake.apk'
} elseif ($args -contains 'install') {
    Write-Output 'Success'
} elseif ($args -contains 'uninstall') {
    Write-Output 'Success'
} else {
    Write-Output ''
}
