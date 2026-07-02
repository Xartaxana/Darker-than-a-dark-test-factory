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
