# Окружение тестового стенда (Windows)

Всё портативное, без прав администратора, живёт в `D:\AO3_tests\tools\`.
Настроено 2026-07-02 (Фаза 0).

## Компоненты

| Компонент | Версия | Путь |
|---|---|---|
| JDK (Temurin) | 21.0.11+10 | `tools\jdk-21.0.11+10` |
| Android cmdline-tools | 19.0 | `tools\android-sdk\cmdline-tools\latest` |
| platform-tools (adb) | 37.0.0 | `tools\android-sdk\platform-tools` |
| Android Emulator | установлен | `tools\android-sdk\emulator` |
| System image | android-34, **default** (без Google Play → есть root для CA mitmproxy) | `tools\android-sdk\system-images` |
| AVD | `ao3_test_api34` (Pixel 6) | `tools\avd` (через `ANDROID_AVD_HOME`) |
| Appium | 2.x + uiautomator2 8.0.1 | `tools\appium` (локальный npm-проект, запуск `npx appium`) |
| Python venv | 3.12: pytest 9, Appium-Python-Client 5, allure-pytest, mitmproxy 11, pytest-rerunfailures, PyYAML | `framework\.venv` |
| Приложение (исходники) | клон gitlab, **read-only по конвенции** | `app-under-test\` |

## Переменные окружения для любого запуска

```powershell
$env:JAVA_HOME    = "D:\AO3_tests\tools\jdk-21.0.11+10"
$env:ANDROID_HOME = "D:\AO3_tests\tools\android-sdk"
$env:ANDROID_AVD_HOME = "D:\AO3_tests\tools\avd"
# adb, emulator: вызывать по полному пути или добавить в PATH сессии
```

## Типовые команды

```powershell
# Сборка APK (единственное созданное нами в app-under-test — гитигнорный local.properties)
cd D:\AO3_tests\app-under-test; .\gradlew.bat assembleDebug

# Эмулятор
& "$env:ANDROID_HOME\emulator\emulator.exe" -avd ao3_test_api34

# Appium-сервер
cd D:\AO3_tests\tools\appium; npx appium

# Тесты
& D:\AO3_tests\framework\.venv\Scripts\Activate.ps1; pytest framework/tests -m p0
```

## Аппаратное ускорение эмулятора (РЕШЕНО)

История: 2026-07-02 SVM был выключен в BIOS (`emulator -accel-check` → exit 6).
Владелец включил SVM → установлен драйвер **AEHD 2.2**
(`sdkmanager "extras;google;Android_Emulator_Hypervisor_Driver"` +
`silent_install.bat` от администратора). Сейчас: служба `aehd` RUNNING,
`emulator -accel-check` → **0, «AEHD (version 2.2) is installed and usable»**.
Эмулятор `ao3_test_api34` загружается headless.

## Результаты спайков Фазы 0

| Спайк | Статус | Результат |
|---|---|---|
| Сборка APK из исходников без правок | ✅ | `app-debug.apk` 20.4 MB, v1.10 (11), см. `state/app-under-test.yaml` |
| A: WEBVIEW-контекст на debug-сборке | ✅ | Appium видит `['NATIVE_APP','WEBVIEW_com.example.ao3_wrapper']`; переключились в WebView, прочитали `https://archiveofourown.org/` / title «Home \| Archive of Our Own». Нужен флаг `appium:chromedriverAutodownload=true` (WebView Chrome 113 → chromedriver качается автоматически; сервер стартовать с `--allow-insecure uiautomator2:chromedriver_autodownload`) |
| B: mitmproxy + системный CA (для replay) | ⚠️ частично | **Механизм доказан:** rootable AVD + `adb root` + `-writable-system` + overlayfs remount ✓; CA mitmproxy внедрён в `/system/etc/security/cacerts` **и** APEX-хранилище `/apex/com.android.conscrypt/cacerts` (Android 14) ✓ (скрипт `scripts/install-mitm-ca.sh`); mitmproxy расшифровывает TLS ✓ (с хоста: CONNECT-туннель + предъявлен сертификат mitmproxy). **Открыто:** захват трафика эмулятора на этом Windows-хосте пока пустой — гость по 10.0.2.2/`-http-proxy` до mitmdump доходит по TCP, но обмен не завершается. Вероятная причина — Windows Defender Firewall (входящее на python/mitmdump) или NAT qemu. Довести в Фазе 1 (правило файрвола для mitmdump / проверка на реальном устройстве). **Не блокирует каркас фреймворка** — Фаза 1 строится в live-режиме, replay подключается позже |
| C: сидинг Room через run-as | ✅ | На debug-сборке `run-as com.example.ao3_wrapper` даёт чтение и запись `databases/` (`ao3_ratings.db`), `shared_prefs/` (`ao3_settings.xml`), `files/`. Снятие/заливка состояния — `scripts/seed-room-db.sh`. **Нюанс:** Room в WAL — тянуть/класть `*.db` + `*.db-wal` + `*.db-shm` вместе |

### Приёмы, зафиксированные в спайках (для фреймворка)
- **Git Bash + adb-пути:** экспортировать `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"`, иначе `/system/...` → `C:/Program Files/Git/system/...`.
- **Фоновые процессы (mitmdump, эмулятор):** запускать через фоновые задачи/`nohup`, а не `Start-Process` из разовой PowerShell-команды — иначе процесс умирает по завершении вызова.
- **CA-mount не переживает reboot** эмулятора — `install-mitm-ca.sh` прогонять после каждого старта.

### Что нужно от окружения перед Фазой 1
- Ничего блокирующего. Опционально для replay: добавить правило Windows Firewall,
  разрешающее входящие подключения к `mitmdump`/`python.exe` на порту прокси (нужны
  права администратора — разовое действие владельца).
