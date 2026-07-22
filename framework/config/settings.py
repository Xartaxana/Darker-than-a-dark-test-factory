"""Слой конфигурации: единая точка правды для окружения прогона.

Все значения переопределяются переменными окружения (см. scripts/env.ps1 и tasks.ps1),
чтобы один и тот же код гонялся локально, в live и в replay без правок.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Корни ---
REPO_ROOT = Path(__file__).resolve().parents[2]          # D:\AO3_tests
FRAMEWORK_ROOT = REPO_ROOT / "framework"
TOOLS = REPO_ROOT / "tools"
ANDROID_HOME = Path(os.environ.get("ANDROID_HOME", TOOLS / "android-sdk"))
ADB = str(ANDROID_HOME / "platform-tools" / "adb.exe")
# aapt — статическая инспекция AndroidManifest.xml (security area, TC-100/101/104:
# misc-batch-0722, замечание critic прохода (5) — `dumpsys package` неполон/косвенен
# для атрибутов exported/cleartextTraffic/fullBackupContent, `aapt dump xmltree` даёт
# их напрямую из скомпилированного бинарного манифеста).
AAPT = str(ANDROID_HOME / "build-tools" / "36.0.0" / "aapt.exe")

# --- Тестируемое приложение ---
APP_PACKAGE = "com.example.ao3_wrapper"
APP_ACTIVITY = "com.example.ao3_wrapper.MainActivity"
APK_PATH = str(REPO_ROOT / "app-under-test" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk")

# --- Appium / устройство ---
APPIUM_URL = os.environ.get("APPIUM_URL", "http://127.0.0.1:4723")
DEVICE_NAME = os.environ.get("AO3_DEVICE", "emulator-5554")
PLATFORM_VERSION = os.environ.get("AO3_PLATFORM_VERSION", "")  # пусто = любой

# CHROMEDRIVER_EXECUTABLE — AT-BUG-028: embedded System WebView образа
# `ao3_test_api26` (google_apis, API 26, см. AT-BUG-024) — Chrome 69.0.3497
# (EOL ~2018); appium:chromedriverAutodownload (см. build_options ниже) не
# находит совместимый chromedriver для этой версии ('No Chromedriver found
# that can automate Chrome 69.0.3497'). Пусто по умолчанию — основной AVD
# (api34, Chrome 113) продолжает автозагрузку без изменений. Прогон на
# api26 задаёт `AO3_CHROMEDRIVER_EXECUTABLE` (см. docs/environment-setup.md) —
# явный legacy-бинарник (chromedriver 2.41, ChromeDriver 2.41.578737,
# `Supports Chrome v67-69`, https://chromedriver.storage.googleapis.com/
# 2.41/notes.txt) вместо autodownload.
CHROMEDRIVER_EXECUTABLE = os.environ.get("AO3_CHROMEDRIVER_EXECUTABLE", "")

# --- Режим прогона: live | replay ---
MODE = os.environ.get("AO3_MODE", "live").lower()
PROXY_HOST_ALIAS = os.environ.get("AO3_PROXY", "10.0.2.2:8080")  # для replay (Фаза 1: доводка транспорта)

# --- Таймауты (сек) ---
IMPLICIT_WAIT = 0            # используем только явные ожидания
DEFAULT_TIMEOUT = int(os.environ.get("AO3_TIMEOUT", "20"))
WEBVIEW_LOAD_TIMEOUT = int(os.environ.get("AO3_WEBVIEW_TIMEOUT", "40"))
NEW_COMMAND_TIMEOUT = 300

# PERF_MEASUREMENT_HANG_GUARD — fail-safe (НЕ рабочий предел измерения) для
# `perf_steps.measure_home_page_load_time` (TC-097, AT-BUG-027, сиблинг
# AT-BUG-025). Тот же класс риска: голый `driver.get()` в WebView-контексте
# этого приложения может зависнуть без load-события. Отличие от остальных
# call-site'ов `framework/steps/browser_steps.py` — сам вызов `driver.get()`
# ЯВЛЯЕТСЯ измеряемым интервалом (`time.monotonic()` вокруг него), поэтому
# НАИВНОЕ переиспользование `WEBVIEW_LOAD_TIMEOUT` (40s) как таймаута этого
# вызова рискованно: бюджет TC-097 (`test_performance.py::BUDGET_MULTIPLIER`
# x медиана, пол 1.0s) в принципе мог бы приблизиться к тому же порядку при
# реальной (не зависшей, просто медленной) деградации — обрезка на 40s
# превратила бы информативный "загрузка заняла Xs, бюджет провален" в голый
# `TimeoutError` без числа X.
#
# Поэтому здесь ОТДЕЛЬНАЯ константа, СУЩЕСТВЕННО больше любого правдоподобного
# значения самого измерения: наблюдаемые загрузки — единицы секунд (red-проба
# test-reviewer TC-097.md, 2026-07-22: 2.42s; TC-096 холодный старт baseline
# на этом же эмуляторе — единицы секунд). 60s — на порядок больше самой
# WEBVIEW_LOAD_TIMEOUT (сама уже щедрый запас над наблюдаемыми единицами
# секунд) и заметно МЕНЬШЕ глобального `APPIUM_HTTP_TIMEOUT` (120s), которым
# и без того ограничен ЛЮБОЙ HTTP-вызов к Appium (см. ниже) — то есть этот
# guard не расширяет риск-профиль, а сужает его: ловит зависание раньше и с
# понятной семантикой (perf-специфичный `TimeoutError`, конвертируемый
# `navigate()` из `ReadTimeoutError`/`MaxRetryError`, matчащийся
# `pytest.ini --only-rerun`), не дожидаясь общего 120s+compensating rerun.
# Только ГЕНУИННЫЙ бесконечный/близкий-к-бесконечному хенг (класс AT-BUG-025)
# пересечёт эту границу — любое конечное, пусть и деградировавшее, измерение
# остаётся ниже неё на порядок и не искажается.
PERF_MEASUREMENT_HANG_GUARD = int(os.environ.get("AO3_PERF_HANG_GUARD", "60"))
# Client-side read-timeout на КАЖДЫЙ HTTP-вызов к Appium (AT-BUG-007): без него
# WebDriverWait (waits.py) проверяет дедлайн только МЕЖДУ поллами — единичный
# блокирующий вызов (классика: driver.contexts из contexts.to_native) при мёртвом
# процессе приложения виснет на серверной стороне навсегда, NEW_COMMAND_TIMEOUT
# тут не помогает (это idle-таймаут МЕЖДУ командами, не таймаут одной команды).
#
# Честная граница (critic, ревью attempt 1, измерено на этом venv/urllib3 2.7.0):
# по умолчанию urllib3 ретраит GET (в т.ч. сам driver.contexts) при read-timeout
# до 3 раз (падает MaxRetryError за ~4x timeout), а POST — без ретраев (падает
# ReadTimeoutError за ~1x timeout). driver_factory.create_driver отключает эти
# урллиб3-ретраи (client_config.init_args_for_pool_manager -> retries=False,
# штатный параметр ClientConfig, не монки-патч) — И GET, И POST теперь падают
# ReadTimeoutError ровно за 1x APPIUM_HTTP_TIMEOUT. Компенсирующий ретрай — на
# уровне теста (framework/pytest.ini: --reruns 1 --only-rerun
# ReadTimeoutError|MaxRetryError), не на уровне HTTP; поэтому итоговый худший
# случай зависшего вызова — до (1 + reruns) x APPIUM_HTTP_TIMEOUT = 2x120=240с
# (4 мин) — на порядок меньше наблюдавшихся реальных зависаний (19+ минут,
# AT-BUG-005 инкремент 1, 2026-07-09), а не 8x/16x, как было бы без retries=False.
#
# 120с по умолчанию — запас на самый долгий легитимный ОДИНОЧНЫЙ вызов: создание
# сессии (POST) — запуск uiautomator2-сервера, по дефолтам Appium укладывается в
# 60-90с. ИЗВЕСТНЫЙ РИСК (не устранён, N2 ревью critic): холодная докачка
# chromedriver может происходить на SET_CONTEXT при первом переключении в WebView
# (тоже одиночный POST, без ретрая после этого фикса) и потенциально превысить
# 120с на медленной сети/первом прогоне на чистой машине — тогда легитимный вызов
# ошибочно словит таймаут. Смягчение: `AO3_APPIUM_HTTP_TIMEOUT` увеличивается без
# правки кода; отдельный количественный замер докачки — вне скоупа этого фикса.
APPIUM_HTTP_TIMEOUT = int(os.environ.get("AO3_APPIUM_HTTP_TIMEOUT", "120"))

# adb-подпроцессы без timeout (AT-BUG-009, тот же класс блокирующего вызова, что
# AT-BUG-007 закрыл для Appium HTTP): framework/core/adb.py::_run() и
# framework/core/mitm.py::set_device_proxy/clear_device_proxy зовут
# subprocess.run(adb ...) без ограничения по времени — зависший/неотвечающий
# adb-сервер (кандидат в корень AT-BUG-009, наблюдение №1: ReadTimeoutError на
# TC-013 внутри driver.get() ПОСЛЕ переключения replay-прокси на нагруженной
# длинной сессии) подвесит вызов навсегда, как и голый Appium HTTP-вызов до
# фикса AT-BUG-007. Истечение таймаута — явная ошибка с контекстом (какая
# команда, сколько ждали), не молчаливый retry.
#
# ADB_SHELL_TIMEOUT — обычные быстрые shell-команды (settings put http_proxy,
# pm clear, am force-stop, logcat -d, run-as cp/rm): по наблюдениям локальных
# прогонов укладываются в доли секунды — единицы секунд даже на нагруженном/
# холодном эмуляторе. 30s — на порядок больше нормы, но конечный: зависший
# `adb shell` (симптом-кандидат AT-BUG-009) падает за 30s явной ошибкой вместо
# неопределённого клина.
ADB_SHELL_TIMEOUT = int(os.environ.get("AO3_ADB_SHELL_TIMEOUT", "30"))

# ADB_LAUNCH_TIMEOUT — `am start -W` (запуск Activity с ожиданием полной
# прорисовки окна/onResume, используется `seed_db.ensure_db_initialized()`):
# AT-BUG-009, инкремент 2 (наблюдение №3). Инкремент 1 классифицировал ВСЕ
# `adb.shell()`-вызовы под `ADB_SHELL_TIMEOUT` (обоснование там перечисляло
# только `settings put`/`pm clear`/`force-stop`/`logcat -d` — «быстрые»
# команды, доли секунды) — `am start -W` семантически ДРУГОЙ класс: он ЖДЁТ
# (флаг `-W` в самой команде), не просто отправляет запрос и возвращается;
# 30s (`ADB_SHELL_TIMEOUT`) оказался тесен под нагрузкой длинной сессии (3
# `ERROR at setup` на полном p0, наблюдение №3 — сам таймаут сработал корректно,
# не молчаливый клин, но неретраемый на первой строке цикла до фикса шва).
# Не переиспользуем `ADB_TRANSFER_TIMEOUT` (120s) — это бюджет файловых
# операций (APK/push), другая природа задержки (I/O объёма, не отрисовка UI).
# 60s — между `ADB_SHELL_TIMEOUT` и `ADB_TRANSFER_TIMEOUT`: вдвое больше
# `ADB_SHELL_TIMEOUT`, запас на прорисовку под нагрузкой, но не настолько
# щедрый, чтобы маскировать реальное зависание рендера на минуты.
ADB_LAUNCH_TIMEOUT = int(os.environ.get("AO3_ADB_LAUNCH_TIMEOUT", "60"))

# ADB_TRANSFER_TIMEOUT — операции с файлами на диске (`adb install`, `adb push`,
# `adb exec-out ... cat` при pull_app_file): дольше обычного shell-вызова (APK
# ~10-30MB), но не настолько долго, как удержание Appium-сессии. 120s — тот же
# порядок запаса, что APPIUM_HTTP_TIMEOUT (самый долгий легитимный одиночный
# блокирующий вызов в системе), явно больше типичных install/push, на порядок
# меньше наблюдавшихся многоминутных зависаний.
ADB_TRANSFER_TIMEOUT = int(os.environ.get("AO3_ADB_TRANSFER_TIMEOUT", "120"))

# PACKAGE_SERVICE_WAIT_TIMEOUT — Python-эквивалент PowerShell
# `tasks.ps1::Wait-PackageServiceReady` (принят на приёмке AT-BUG-013): гонка
# «adb install сразу после boot_completed=1, пока гостевой package-сервис ещё не
# поднялся» — `pm path android` пуст/`cmd: Can't find service: package`, `adb
# install` следом ловит ту же ошибку. Закрыт для канонического пути установки
# (`Install-App` в tasks.ps1); этот таймаут закрывает parallel-путь
# `framework/core/adb.py::install()` (реальный вызов при fresh-boot из
# `conftest.py::_ensure_app_installed`, минуя tasks.ps1) — замеченный, но не
# устранённый аналог класса (queue-пункт 1, docs/HANDOFF.md, находка critic на
# приёмке AT-BUG-013). Тот же дефолт 30s, что и PowerShell-версия — тот же
# сигнал готовности (первый непустой `pm path android` с `package:`; «устойчивость»
# из нескольких подряд успехов НЕ требуется — обе реализации возвращают на первом),
# тот же порядок ожидания. НАМЕРЕННАЯ разность на пути исчерпания: PS-версия —
# fail-soft (Write-Warning, install всё равно пробуется), Python — fail-fast
# (RuntimeError, install не пробуется); это не рассинхрон порта, а решение приёмки.
PACKAGE_SERVICE_WAIT_TIMEOUT = int(os.environ.get("AO3_PACKAGE_SERVICE_WAIT_TIMEOUT", "30"))

# PROXY_DEVICE_REACHABLE_TIMEOUT — AT-BUG-017: `mitm._wait_listening` (start_replay)
# проверяет только, что mitmdump слушает порт на ХОСТЕ — недостаточно, наблюдался
# интермиттентный `net::ERR_PROXY_CONNECTION_FAILED` на первой навигации ПОСЛЕ
# `set_device_proxy()`+`start_replay()`, хотя хост-порт уже подтверждённо слушал
# (race NAT-уровня qemu / задержка применения системной настройки прокси
# Android'ом). `mitm.wait_device_proxy_reachable()` поллит TCP-достижимость
# `PROXY_HOST_ALIAS` СО СТОРОНЫ УСТРОЙСТВА (`adb shell nc`) — 10s с тем же
# порядком запаса, что `PACKAGE_SERVICE_WAIT_TIMEOUT` (аналогичный класс гонки
# «сервис технически поднят, но потребитель ещё не видит его готовность»),
# явная `TimeoutError` при исчерпании, не молчаливый клин.
PROXY_DEVICE_REACHABLE_TIMEOUT = int(os.environ.get("AO3_PROXY_DEVICE_REACHABLE_TIMEOUT", "10"))

# --- Артефакты ---
RUNS_DIR = REPO_ROOT / "runs"
ALLURE_RESULTS = Path(os.environ.get("ALLURE_RESULTS", FRAMEWORK_ROOT / "allure-results"))

# --- Данные ---
DATA_DIR = FRAMEWORK_ROOT / "data"
SEEDS_DIR = DATA_DIR / "seeds"
RECORDINGS_DIR = DATA_DIR / "recordings"


def is_replay() -> bool:
    return MODE == "replay"


def is_live() -> bool:
    return MODE == "live"
