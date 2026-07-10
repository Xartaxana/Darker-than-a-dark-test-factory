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
| B: mitmproxy + системный CA (для replay) | ✅ РЕШЁН (2026-07-03) | Доказан полный цикл **record→replay** HTTPS-трафика WebView. 48 флоу записано (22 к archiveofourown.org, расшифрованы html/css/json), затем те же страницы отданы приложению из записи (`[replay] << 200 OK` на `GET https://archiveofourown.org/`). Ноль ошибок доверия. См. подробный разбор ниже (§Спайк B — как решён). Recording-фикстура: `framework/data/recordings/ao3_home_smoke.mitm`. Разблокирует TC-009/013/014/015 |
| C: сидинг Room через run-as | ✅ | На debug-сборке `run-as com.example.ao3_wrapper` даёт чтение и запись `databases/` (`ao3_ratings.db`), `shared_prefs/` (`ao3_settings.xml`), `files/`. Снятие/заливка состояния — `scripts/seed-room-db.sh`. **Нюанс:** Room в WAL — тянуть/класть `*.db` + `*.db-wal` + `*.db-shm` вместе |

**Доведение спайка B до продукта (AT-BUG-004, инкремент 1, 2026-07-08):** механизм
record→replay подключён к `framework/tests/conftest.py::replay` (fixture, маркер
`replay`, teardown возвращает прокси и глушит mitmdump). Записи с блёрбами
синтетических `ao3_id` (`framework/data/works.py`) физически невозможно снять живым
`mitmdump`-прогоном (таких работ не существует на archiveofourown.org) — они
собираются программно: `framework/data/recording_builder.py` (тот же `.mitm`-формат,
HTML 1:1 повторяет проверенную разметку AO3) + генератор
`python scripts/build_replay_recordings.py`. Базовая листинговая запись —
`framework/data/recordings/listing_basic.mitm` (5 блёрбов, разблокирует
TC-013/014/015/043/045). Остаток батча (TC-032/033 — запись download-flow;
TC-012 — вариация с дублированным `ao3_id`) — в очереди, см. `bugs/AT-BUG-004.md`.
Каждый прогон с `-writable-system` требует свежего `bash scripts/install-mitm-ca.sh`
(mount не переживает reboot эмулятора, см. ниже).

### Приёмы, зафиксированные в спайках (для фреймворка)
- **Git Bash + adb-пути:** экспортировать `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"`, иначе `/system/...` → `C:/Program Files/Git/system/...`.
- **Фоновые процессы (mitmdump, эмулятор):** запускать через фоновые задачи/`nohup`, а не `Start-Process` из разовой PowerShell-команды — иначе процесс умирает по завершении вызова.
- **CA-mount не переживает reboot** эмулятора — `install-mitm-ca.sh` прогонять после каждого старта.
- **`getExternalFilesDir` (app-specific external storage) НЕ доступен ни `adb push`,
  ни `run-as` на Android 11+/API 34** — прямой `adb push` в
  `/storage/emulated/0/Android/data/<pkg>/files/...` падает
  (`remote secure_mkdirs failed: Operation not permitted`), а `run-as <pkg> cat/ls`
  того же пути даёт `Permission denied`, даже когда UID совпадает — adb-процесс не
  получает нужный FUSE/scoped-storage mount, который есть только у самого
  app-процесса. Для фикстур файлов, на которые указывает `downloadPath` в Room
  (TC-034/035/036), кладите файл во ВНУТРЕННЮЮ песочницу приложения
  (`run-as <pkg> mkdir -p files/...` + `push_app_file`, `/data/user/0/<pkg>/files/...`)
  — приложение читает/удаляет `downloadPath` голым `File(path)`, не проверяя, что
  путь лежит именно под external storage, так что для black-box теста это
  эквивалентно (см. `framework/data/seed_db.py::seed_with_download`).
- **Несколько открытых WebView-вкладок = ОДИН общий Appium-контекст
  `WEBVIEW_<package>`** (не по контексту на вкладку) — `driver.current_url`/DOM после
  `switch_to.context` могут спонтанно указывать на любую из открытых страниц
  (`mobile: getContexts` показывает все `pages[]` внутри одного `webview`-процесса).
  Если сценарий открывает новую вкладку поверх уже существующей (например,
  `BrowserViewModel.openTab` из Library `onOpenFile` — всегда ДОБАВЛЯЕТ вкладку,
  никогда не заменяет стартовую Home-вкладку), закройте лишние вкладки перед любой
  DOM-проверкой (см. `framework/screens/browser_screen.py::close_leftmost_tab`),
  иначе проверки недетерминированно попадают не в ту вкладку.

### Что нужно от окружения перед Фазой 1
- Ничего блокирующего.

## Спайк B — как решён (2026-07-03)

Прошлая гипотеза («пустой захват из-за Windows Firewall») оказалась **неверной**.
Реальных причин было две, обе — не в сети хоста:

1. **Методика проверки.** Первый «пустой захват» был артефактом теста: `nc` в госте
   закрывал сокет по EOF раньше, чем mitmproxy успевал сходить на сервер. HTTP-прокси
   через `10.0.2.2:8080` работает сразу (qemi NAT-ит гостя в loopback хоста —
   в логе mitmdump клиент виден как `127.0.0.1:xxxxx`). Firewall ни при чём.

2. **Главный блокер — доверие к CA в mount-namespace приложения (Android 14).**
   Системный CA-стор переехал в APEX-модуль conscrypt. tmpfs-mount поверх
   `/apex/com.android.conscrypt/cacerts`, сделанный из `adb shell su`, попадает в
   mount-namespace **init'а**, а уже запущенные zygote и приложение живут в
   **отдельных** namespace и наш CA не видят. WebView/Chromium через Conscrypt
   валидировал цепочку по своему (немодифицированному) стору → `Trust anchor for
   certification path not found`. Проверка `ls ... | grep hash` в install-скрипте
   проходила в том же adb-namespace, где монтировали, — оттого ложное «OK».

**Рабочее решение** (`scripts/install-mitm-ca.sh` + `scripts/ca-mount.sh`):
- эмулятор стартует с `-writable-system` (`Start-Emulator -WritableSystem`);
- CA + системные сертификаты монтируются tmpfs'ом поверх **обоих** каталогов доверия
  в **init-namespace** (adb shell = namespace init'а);
- **перезапуск фреймворка** (`stop && start`): новый zygote форкается из init и
  **наследует** mount (после рестарта zygote64 оказывается в namespace init'а —
  проверено). nsenter не годится: в toybox 0.8.9-android флаг `-t` всегда даёт pid 0;
- **критично для стабильности:** самим каталогам-точкам монтирования нужно вернуть
  SELinux-контекст `system_security_cacerts_file` (не только файлам). Иначе
  system_server не может прочитать каталог доверия → `NullPointerException: get length
  of null array` → крэш-луп загрузки. (Контекст `system_file`, который казался
  правильным по родителю APEX, приводит к тому же крэшу — эталон снят с чистой
  загрузки: и каталог, и файлы = `system_security_cacerts_file:s0`.)

**Workflow записи/воспроизведения** (обёрнут в `framework/core/mitm.py`):
- запись: `mitmdump -w rec.mitm`, прокси гостя на `10.0.2.2:8080`, прогнать сценарий;
- воспроизведение: `mitmdump --server-replay rec.mitm --set server_replay_reuse=true
  --set server_replay_extra=forward --set connection_strategy=lazy`.

**Не переживает reboot эмулятора** — mount'ы tmpfs исчезают при каждом ребуте.
Автовызов: `scripts/tasks.ps1` → `Start-Emulator -WritableSystem` сам вызывает
`Install-MitmCA` сразу после чистого буда (скрипт сам перезапускает фреймворк и
проверяет CA); ручной прогон `install-mitm-ca.sh`/`Install-MitmCA` — только как
fallback, если нужно повторить установку без пересоздания эмулятора (например,
сразу после отдельного ребута тем же -writable-system).

## Стабильность хоста: эмулятор (aehd) + локальный GPU-инференс не совмещать

2026-07-09 15:02:41 — BSOD `SYSTEM_SERVICE_EXCEPTION (0x3B)` в `aehd.sys`
(Android Emulator Hypervisor Driver, версия от 26.03.2024; минидамп
`C:\Windows\Minidump\070926-7359-01.dmp`). Эмулятор в тот момент был поднят
конвейером (простаивал между воркерами); параллельно на машине шли процессы
второй сессии (node/litellm/Pi CLI, потенциально GPU-инференс). Краш — в
kernel-драйвере гипервизора; userspace-процессы уронить его не могут, но
совокупная нагрузка — правдоподобный триггер.

Правило (согласовано со второй сессией, её Environment Notes): на этой машине
НЕ гонять одновременно Android-эмулятор и локальный LLM-инференс на GPU;
прогоны/верификации, требующие эмулятора, планировать, когда инференс не
работает (и наоборот).

Проверка обновлений AEHD (2026-07-09): обновления НЕТ и не будет. Установлена
2.2 — последний релиз (02.04.2024); после него в master только README-коммит
(12.11.2025) с сообщением о деприкации: «Android Emulator hypervisor driver
will be sunset on December 31, 2026», рекомендация Google — переход на
Windows Hypervisor Platform (WHPX). На этой машине HypervisorPlatform /
VirtualMachinePlatform / Hyper-V сейчас ВЫКЛЮЧЕНЫ (InstallState=Disabled).
План: включить WHPX (действие владельца: админ-PowerShell
`Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All`
+ перезагрузка; эмулятор подхватит WHPX сам, aehd после этого можно
остановить/удалить). До перехода единственная митигация краша —
правило выше (не совмещать эмулятор с GPU-инференсом).

### Миграция на WHPX выполнена (2026-07-09 ~16:15-17:00) — работает

Владелец включил HypervisorPlatform + VirtualMachinePlatform и перезагрузил
машину (обе Enabled; `Enable-WindowsOptionalFeature` из pwsh 7 падает
«Класс не зарегистрирован» — включать через `dism.exe` или PowerShell 5.1).
`emulator -accel-check` → `WHPX(10.0.26200) is installed and usable`.
Эмулятор `ao3_test_api34` грузится и работает на WHPX штатно.

**Ложный след при первом старте (важно как класс).** Первые ~40 минут
выглядели как «нестабильность WHPX»: `adb devices` флаппал
`offline`↔`device` (12–23 смены за 90–150с, transport_id рос),
`sys.boot_completed` не отдавал 1 — одинаково на `-gpu swiftshader_indirect`
и `-gpu host`, и с квикбут-снапшотом, и на холодной загрузке. Истинная
причина (найдена через `-show-kernel`): **kernel panic геста
`EXT4-fs (device dm-38): panic forced after error` на ~49с загрузки —
userdata был повреждён BSOD'ом 15:02** (эмулятор стоял поднятым в момент
краха хоста; журнал ФС зафиксировал «error recorded from previous mount:
IO failure», авто-e2fsck не вылечил). Гест уходил в бесконечный
panic→reboot цикл — отсюда флаппинг adb. WHPX ни при чём.

Лечение: `emulator ... -wipe-data` (factory reset userdata) → загрузка
стабильна (boot за ~2 мин, включая first-boot). После wipe обязательны:
`bash scripts/install-mitm-ca.sh` (как после любого старта; в Bash-туле —
с `ADB=<полный путь к adb.exe>`) и `Install-App`. Выполнено, окружение
рабочее.

Уроки/факты:
- **После аварийного падения хоста с поднятым эмулятором первым делом
  подозревай ФС геста, не гипервизор**: диагностика — `-show-kernel`
  (повторные баннеры `Linux version` = boot-loop; grep `Kernel panic`).
  Флаппинг `offline`↔`device` с растущим transport_id = гест циклически
  перезагружается.
- **AEHD и WHPX взаимоисключающи на живой системе**: при включённом WHPX
  служба `aehd` не стартует, `accel-check` перестаёт упоминать AEHD.
  Фоллбэк «переключиться на aehd без перезагрузки» не существует; откат =
  отключить HypervisorPlatform/VirtualMachinePlatform + ребут. Пока WHPX
  стабилен — не нужен; удаление aehd (sunset 31.12.2026) — за владельцем.
- **AEHD УДАЛЁН владельцем 2026-07-10** (`sc delete aehd` → успех; сверено:
  `sc query aehd` → 1060 «не существует», WHPX usable, эмулятор жив под
  нагрузкой). Evidence стабильности WHPX на момент удаления: полный p0
  18/18 (2026-07-09) + два дня прогонов конвейера без инцидентов
  гипервизора. Файл `C:\Windows\System32\drivers\aehd.sys` мог остаться
  на диске — мёртвый груз, без службы не загружается. Переустановка при
  необходимости отката: инсталлятор на месте (`tools\android-sdk\extras\
  google\Android_Emulator_Hypervisor_Driver\silent_install.bat` от
  администратора; `-u` — удаление) + отключить HypervisorPlatform + ребут.
  Ловушка деинсталлятора: запуск БЕЗ `-u` ПЕРЕустанавливает драйвер и
  пытается стартовать службу (install-ветка .bat) — так и произошло при
  первой попытке удаления 2026-07-10.
- Правило «эмулятор + локальный GPU-инференс не совмещать» остаётся в силе
  (сам BSOD случился на aehd.sys, но совокупная нагрузка — фактор);
  дополнительная мотивация гасить эмулятор при пустой эмуляторной очереди —
  меньше окно уязвимости userdata к падениям хоста.
- **Quickboot-снапшот `default_boot` может быть битым** (обнаружено
  2026-07-10 при боевой проверке mitm-ca-autoinstall): эмулятор пишет
  `Failed to load snapshot 'default_boot'` → `Error -1 while loading VM
  state` и ТИХО гаснет с кодом 0, не дойдя до буда — снаружи это выглядит
  как «Start-Emulator висит на wait-for-device» без единой ошибки.
  Диагностика: запустить emulator.exe напрямую с redirect stdout/stderr.
  Лечение: разовый старт с `-no-snapshot-load` (холодный бут; при
  следующем штатном гашении снапшот пересохранится) либо удалить снапшот
  AVD. ОТЛОЖЕННЫЙ WITNESS: интегрированный прогон «один вызов
  `Start-Emulator -WritableSystem` → авто-CA встал» целиком не прогнан
  из-за этого снапшота (логика идентична доказанному прямому вызову
  `Install-MitmCA`) — перепрогнать при следующем здоровом replay-подъёме.
