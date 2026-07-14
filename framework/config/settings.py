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

# --- Тестируемое приложение ---
APP_PACKAGE = "com.example.ao3_wrapper"
APP_ACTIVITY = "com.example.ao3_wrapper.MainActivity"
APK_PATH = str(REPO_ROOT / "app-under-test" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk")

# --- Appium / устройство ---
APPIUM_URL = os.environ.get("APPIUM_URL", "http://127.0.0.1:4723")
DEVICE_NAME = os.environ.get("AO3_DEVICE", "emulator-5554")
PLATFORM_VERSION = os.environ.get("AO3_PLATFORM_VERSION", "")  # пусто = любой

# --- Режим прогона: live | replay ---
MODE = os.environ.get("AO3_MODE", "live").lower()
PROXY_HOST_ALIAS = os.environ.get("AO3_PROXY", "10.0.2.2:8080")  # для replay (Фаза 1: доводка транспорта)

# --- Таймауты (сек) ---
IMPLICIT_WAIT = 0            # используем только явные ожидания
DEFAULT_TIMEOUT = int(os.environ.get("AO3_TIMEOUT", "20"))
WEBVIEW_LOAD_TIMEOUT = int(os.environ.get("AO3_WEBVIEW_TIMEOUT", "40"))
NEW_COMMAND_TIMEOUT = 300
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

# ADB_TRANSFER_TIMEOUT — операции с файлами на диске (`adb install`, `adb push`,
# `adb exec-out ... cat` при pull_app_file): дольше обычного shell-вызова (APK
# ~10-30MB), но не настолько долго, как удержание Appium-сессии. 120s — тот же
# порядок запаса, что APPIUM_HTTP_TIMEOUT (самый долгий легитимный одиночный
# блокирующий вызов в системе), явно больше типичных install/push, на порядок
# меньше наблюдавшихся многоминутных зависаний.
ADB_TRANSFER_TIMEOUT = int(os.environ.get("AO3_ADB_TRANSFER_TIMEOUT", "120"))

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
