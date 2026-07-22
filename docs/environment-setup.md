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
| System image (второй AVD, E3) | android-29, **google_apis** (без Play Store, rootable; сменён с android-26 — AT-BUG-028, EOL WebView) | `tools\android-sdk\system-images` |
| AVD | `ao3_test_api34` (Pixel 6); второй — `ao3_test_api29` (Pixel 6, AT-BUG-024/AT-BUG-028; старый `ao3_test_api26` оставлен на диске, не используется) | `tools\avd` (через `ANDROID_AVD_HOME`) |

**Выбор образа для WebView-AVD (урок AT-BUG-024, 2026-07-22):** AOSP
`default`-образ на API 26 НЕ несёт пакета WebView вообще — приложение
падает на старте (`MissingWebViewPackageException`), это не «старый
WebView», а его отсутствие. Для любого AVD под WebView-приложение на
нижних API брать `google_apis` (без Play Store — root сохраняется);
`default` допустим только там, где WebView заведомо есть (на api34 —
есть). Запуск второго AVD: `Start-Emulator -WritableSystem -AvdName
ao3_test_api26`; CA на API<29 ставится в system-store (признак
готовности «CA visible in system store: OK» — apex-стора там нет).

**Второй AVD переведён API 26 -> API 29 (AT-BUG-028, 2026-07-22):**
embedded System WebView образа `ao3_test_api26` (google_apis, API 26) —
Chrome 69.0.3497 (EOL ~2018); `appium:chromedriverAutodownload`
(дефолт для api34, Chrome 113) не находит совместимый chromedriver для
этой версии (`No Chromedriver found that can automate Chrome
69.0.3497`).

Сверка `sdkmanager --list` (2026-07-22) подтвердила: для API 26
доступен только один Google-без-Play образ (`google_apis;x86_64`, уже
использованный AT-BUG-024) — альтернативного канала с более свежим
WebView на этом API level нет (`google_apis_playstore` — только x86, не
x86_64, и добавляет Google Play, что противоречит rootable/без-Google-Play
требованию §4).

**Опробован и ОТВЕРГНУТ путь «legacy chromedriver вручную»** (скачан
`ChromeDriver 2.41.578737`, `Supports Chrome v67-69`, с
`https://chromedriver.storage.googleapis.com/2.41/chromedriver_win32.zip`,
распакован в `tools\chromedriver-legacy\chromedriver.exe`, zip —
`tools\downloads\chromedriver_2.41_win32.zip`) — эмпирическая проверка
(запуск бинарника локально, прямой GET `/status`) вскрыла СТРУКТУРНУЮ,
не версийную причину провала: текущий `appium-chromedriver`
(`node_modules\...\appium-chromedriver\build\lib\commands\process.js::
waitForOnline`) жёстко требует поле `status.ready === true` в ответе
`/status`. Проверены локально бинарники 2.41/2.42/2.43/2.44 (все — Chrome
v67-71, диапазон, покрывающий 69.0.3497): ни один не несёт поля `ready`
в `/status` (`{"build":{"version":"alpha"},...}`, без `ready`). Первая
версия с полем `ready` — **2.45** (`Supports Chrome v70-72`) — уже НЕ
покрывает Chrome 69. Вывод: ЛЮБОЙ chromedriver, совместимый с Chrome 69,
структурно не проходит readiness-проверку современного Appium — путь
"в" тупиковый по конструкции, не просто «трудно найти бинарник».
Механика осталась в коде как общая возможность
(`framework/config/settings.py::CHROMEDRIVER_EXECUTABLE`,
`AO3_CHROMEDRIVER_EXECUTABLE` env → `appium:chromedriverExecutable`
capability вместо autodownload в `framework/config/capabilities.py`) —
пуста по умолчанию, api34 не регрессирует; не используется в текущем
решении TC-109.

**Рабочее решение — путь "б" критерия готовности:** второй AVD переведён
на `system-images;android-29;google_apis;x86_64` (тот же класс образа,
что и раньше — rootable, `PlayStore.enabled = no`, подтверждено в
`config.ini`). Embedded WebView этого образа — **Chrome 74.0.3729.185**
(`adb shell dumpsys package com.google.android.webview`), для него
`appium:chromedriverAutodownload` штатно находит совместимый
chromedriver (2.45+, несёт `ready`) — без ручных капабилити. Это НЕ
буквальная нижняя граница `minSdk` (26) — ближайший практичный уровень
API ≥26, явно разрешённый критерием готовности AT-BUG-028/AT-BUG-024
(«если 26 недоступен как ЖИЗНЕСПОСОБНЫЙ канал»; здесь образ API 26
физически доступен, но структурно недоступен современному Appium ни
одним совместимым chromedriver — тот же класс непригодности, что
`default`-образ без WebView вовсе в AT-BUG-024). Отмечено для прохода
test-strategist (см. `bugs/AT-BUG-028.md`).

AVD: `tools\avd\ao3_test_api29.ini` + `tools\avd\ao3_test_api29.avd\`
(создан из `system-images;android-29;google_apis;x86_64`, `-d pixel_6`,
тот же приём, что `ao3_test_api26`). Старый `ao3_test_api26.ini`/
`.avd` оставлен на диске (не удалён — не мешает, `tasks.ps1`
параметризован `-AvdName`, ничего по умолчанию на него не ссылается),
но НЕ используется TC-109 больше.

```powershell
. D:\AO3_tests\scripts\tasks.ps1
Start-Emulator -WritableSystem -AvdName ao3_test_api29
Install-App
Start-Appium
Invoke-Pytest -k test_smoke_path_on_api26_no_regression
```
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

## Аппаратное ускорение эмулятора (РЕШЕНО; текущее = WHPX)

> **ТЕКУЩЕЕ СОСТОЯНИЕ (с 2026-07-09): гипервизор — WHPX; AEHD удалён
> владельцем 2026-07-10.** Абзац ниже — история первоначальной настройки;
> миграция и её причины — раздел «Стабильность хоста» ниже.

История: 2026-07-02 SVM был выключен в BIOS (`emulator -accel-check` → exit 6).
Владелец включил SVM → установлен драйвер **AEHD 2.2**
(`sdkmanager "extras;google;Android_Emulator_Hypervisor_Driver"` +
`silent_install.bat` от администратора). На тот момент: служба `aehd` RUNNING,
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

### Полный canary-регресс (batch C, TC-078..083) — `-Gpu host` обязателен

Полный прогон canary-регресса включает live-версии TC-078/080/082
(`@pytest.mark.live`, реальный тяжёлый рендер `archiveofourown.org/tags/
Fluff/works` в эмуляторном WebView) — под дефолтным GPU-бэкендом
(`swiftshader_indirect`) этот рендер провоцирует краш
`qemu-system-x86_64.exe` (`0xc0000005`), устранённый (config-mitigation)
как `bugs/AT-BUG-021.md`. Собственная наблюдаемая на уровне теста
сигнатура AT-BUG-021 — `WebDriverException: disconnected: not connected
to DevTools`, сразу за которым `adb: device not found` (mid-test); связь
именно с qemu-крашем `0xc0000005` как непосредственной причиной
установлена и подтверждена диагностикой critic внутри самого бага
(Event Log witness, Id=1000, два краша в окне инцидента) — AT-BUG-021
подтверждённый (не гипотетический) сиблинг `bugs/AT-BUG-016.md` по
механизму краша, тот же класс «рендер тяжёлых live-страниц AO3 в
эмуляторном WebView», а не отдельный DevTools/adb-класс сам по себе.
Без явного флага прогонщик заново натыкается на уже устранённый
инцидент. Поднимать эмулятор под этот регресс:

```powershell
. D:\AO3_tests\scripts\tasks.ps1; Start-Emulator -Gpu host
# либо переменной окружения на всю сессию: $env:AO3_EMU_GPU = "host"
```

`swiftshader_indirect` (дефолт `tasks.ps1`) остаётся верным выбором для
replay-сиблингов (TC-079/081/083) и всех остальных прогонов — там
живого тяжёлого рендера нет, менять дефолт незачем (см. `bugs/AT-BUG-021.md`,
раздел «Рекомендация Lead»).

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
