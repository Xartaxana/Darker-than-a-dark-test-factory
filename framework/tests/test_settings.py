"""Тесты экрана Settings (app-under-test ui/settings/SettingsScreen.kt): переключение
темы Light/Dark/System и его мгновенное применение к нативному Compose UI и к WebView
(fragile-область, см. app-under-test/CLAUDE.md «Dark mode has broken four times»).

Дизайн следует test_side_panel.py: тема приводится к известному состоянию (Light)
через Settings перед каждым сценарием, зависимость от живого AO3 неизбежна (WebView
должен реально догрузить страницу, чтобы проверять её визуальный результат).
"""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps, browser_steps, settings_steps, side_panel_steps


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-047")
@allure.title("Переключение Dark в Settings применяется мгновенно, Activity не пересоздаётся")
def test_theme_dark_applies_instantly_without_recreating_activity(clean_app, driver):
    # Given приложение в светлой теме, на вкладке Browse отображается загруженная страница
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")
    url_before = app_steps.wait_app_ready(driver)

    # When пользователь в Settings выбирает тему "Dark"
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "DARK")
    app_steps.open_tab(driver, "Browse")

    # Then нативные Compose-экраны немедленно перекрашиваются в тёмную схему (side panel
    # мгновенно отражает новую тему — без перезапуска приложения, тот же прокси, что TC-050)
    side_panel_steps.expand(driver)
    side_panel_steps.assert_theme_is_dark(driver)
    side_panel_steps.collapse(driver)

    # And после возврата на экран Browse открытая вкладка/URL остаются теми же, что были
    # до переключения — наблюдаемый прокси отсутствия recreation Activity (см. заметки TC-047:
    # прямая проверка PID/instance не UI-наблюдаема и не подходит для black-box теста)
    url_after = app_steps.wait_app_ready(driver)
    assert url_after == url_before, (
        f"URL вкладки Browse изменился после переключения темы (похоже на recreation): "
        f"{url_before} -> {url_after}"
    )


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-048")
@allure.title("WebView dark mode применяется мгновенно вместе с остальным UI (без холодного рестарта)")
def test_webview_dark_mode_applies_instantly(clean_app, driver):
    # Given приложение в светлой теме, страница AO3 в WebView отображается светлой
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")
    app_steps.wait_app_ready(driver)
    baseline_luma = browser_steps.measure_webview_luma(driver)

    # When пользователь переключает тему на Dark в Settings и возвращается на экран
    # Browse без перезапуска приложения
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "DARK")
    app_steps.open_tab(driver, "Browse")

    # Then содержимое WebView немедленно переходит в тёмную цветовую схему — наблюдаемый
    # визуальный результат (алгоритмическое затемнение), не internal API; опрос даёт время
    # на программный reload()+перерисовку (см. заметки TC-048 по таймингу)
    browser_steps.assert_webview_darkened(driver, baseline_luma)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-049")
@allure.title("Тема System переключается вместе с системной темой ОС")
def test_system_theme_follows_os_dark_mode(clean_app, driver):
    try:
        # Given в приложении выбрана тема "System", системная тема ОС — Light, нативные
        # экраны приложения отображаются светлыми
        app_steps.wait_ui_ready(driver)
        app_steps.set_system_dark_mode(False)
        app_steps.open_tab(driver, "Settings")
        settings_steps.select_theme(driver, "SYSTEM")
        app_steps.open_tab(driver, "Browse")
        side_panel_steps.expand(driver)
        side_panel_steps.assert_theme_is_light(driver)

        # When системная тема ОС переключается на Dark (без действий пользователя внутри
        # приложения)
        app_steps.set_system_dark_mode(True)

        # Then нативные Compose-экраны приложения отображаются в тёмной схеме без
        # дополнительных действий пользователя внутри приложения (следование за System,
        # configChanges="uiMode" не пересоздаёт Activity)
        side_panel_steps.assert_theme_is_dark(driver)
    finally:
        # Системная тема ОС — общий ресурс эмулятора, переживающий тест; возвращаем её
        # к Light, чтобы не протекало в другие тесты (не полагающиеся на System-тему).
        app_steps.set_system_dark_mode(False)
