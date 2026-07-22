"""Appium capabilities. Единственное место, где описано подключение к устройству —
смена AVD на реальное устройство/CI трогает только этот файл.
"""
from __future__ import annotations

from appium.options.android import UiAutomator2Options

from framework.config import settings


def build_options(no_reset: bool = True) -> UiAutomator2Options:
    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    opts.automation_name = "UiAutomator2"
    opts.device_name = settings.DEVICE_NAME
    opts.app_package = settings.APP_PACKAGE
    opts.app_activity = settings.APP_ACTIVITY
    if settings.PLATFORM_VERSION:
        opts.platform_version = settings.PLATFORM_VERSION

    # Не переустанавливаем и не чистим приложение автоматически — состоянием
    # управляют фикстуры (clean_app / seeded_library) осознанно и явно.
    opts.no_reset = no_reset
    opts.full_reset = False

    opts.new_command_timeout = settings.NEW_COMMAND_TIMEOUT
    opts.auto_grant_permissions = True

    # WebView приложения — Chrome 113 на основном AVD (api34); chromedriver
    # докачивается автоматически (сервер должен быть запущен с --allow-insecure
    # uiautomator2:chromedriver_autodownload). AT-BUG-028: второй AVD
    # (ao3_test_api26) несёт EOL Chrome 69.0.3497 — autodownload для него не
    # находит совместимый chromedriver. Если settings.CHROMEDRIVER_EXECUTABLE
    # задан (AO3_CHROMEDRIVER_EXECUTABLE env, прогон на api26), используем явный
    # путь к legacy-бинарнику ВМЕСТО autodownload; иначе — прежнее поведение
    # (api34 не регрессирует, capability не выставляется вовсе).
    if settings.CHROMEDRIVER_EXECUTABLE:
        opts.set_capability("appium:chromedriverExecutable", settings.CHROMEDRIVER_EXECUTABLE)
    else:
        opts.set_capability("appium:chromedriverAutodownload", True)
    opts.set_capability("appium:ensureWebviewsHavePages", True)
    opts.set_capability("appium:nativeWebScreenshot", True)

    # Стабильность
    opts.set_capability("appium:disableWindowAnimation", True)
    opts.set_capability("appium:ignoreHiddenApiPolicyError", True)
    return opts
