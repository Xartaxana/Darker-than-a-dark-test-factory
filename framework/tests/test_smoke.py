"""P0 smoke — гоняется на каждой новой сборке.

Дизайн: минимизируем обращения к живому AO3 (сторонний сайт — не тестируем и не
нагружаем). Единственная неизбежная загрузка AO3 — стартовая домашняя страница.
Проверки Library строятся на сидинге данных (детерминизм, без сети).
"""
from __future__ import annotations

import allure
import pytest

from framework.core import contexts
from framework.steps import app_steps, library_steps, settings_steps


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-001")
@allure.title("Запуск приложения и загрузка AO3 в WebView")
def test_app_launches_and_loads_ao3(clean_app, driver):
    # Given чистое приложение установлено
    # When приложение запущено
    url = app_steps.wait_app_ready(driver)
    # Then WebView показывает страницу AO3
    assert "archiveofourown.org" in url


@pytest.mark.p0
@allure.id("TC-002")
@allure.title("Нижняя навигация переключает основные экраны")
def test_bottom_nav_switches_screens(clean_app, driver):
    app_steps.wait_ui_ready(driver)
    # When открыт экран Settings
    app_steps.open_tab(driver, "Settings")
    # Then экран Settings отрисован
    settings_steps.assert_settings_loaded(driver)
    # When открыт экран Library
    app_steps.open_tab(driver, "Library")
    # Then виден таб Favorite (Library загрузился)
    library_steps.assert_library_loaded(driver)


@pytest.mark.p0
@allure.id("TC-003")
@allure.title("Засеянная работа попадает в свою вкладку Library")
@pytest.mark.parametrize("rating,attr", [
    ("SAVE", "LOVED"), ("LIKE", "KUDOSED"), ("READ", "READ"),
    ("PENDING", "PENDING"), ("DISLIKE", "DISLIKED"),
])
def test_seeded_work_appears_in_correct_tab(seeded_library, driver, rating, attr):
    work = getattr(seeded_library, attr)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    # Then работа с этим рейтингом присутствует в соответствующей вкладке
    library_steps.assert_work_in_tab(driver, rating, work.title)


@pytest.mark.p0
@allure.id("TC-004")
@allure.title("Clear all ratings очищает библиотеку")
def test_clear_all_ratings(seeded_library, driver):
    app_steps.wait_ui_ready(driver)
    # When в Settings подтверждён Clear all ratings
    app_steps.open_tab(driver, "Settings")
    settings_steps.clear_all_ratings(driver)
    # Then в БД не осталось рейтингов
    settings_steps.assert_no_ratings()
    # And вкладка Favorite больше не содержит засеянную работу
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "SAVE", seeded_library.LOVED.title)


@pytest.mark.p0
@allure.id("TC-005")
@allure.title("Переключение темы не роняет приложение")
def test_theme_toggle_stable(clean_app, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    # When последовательно выбраны Dark, Light, System
    for mode in ("DARK", "LIGHT", "SYSTEM"):
        settings_steps.select_theme(driver, mode)
    # Then экран Settings по-прежнему отрисован (не крашнулись)
    settings_steps.assert_settings_loaded(driver)
    # And финально выбранный режим (System) отражён как выбранный (misc-batch-0722):
    # ThemeModeRow рисует выбор цветом фона TextButton, НЕ через accessibility
    # selected/checked (сверено на живом дереве — settings_steps.py:116-124,
    # selected="false" у всех вариантов независимо от выбора) — единственный
    # наблюдаемый источник истины финально выбранного режима, тот же для обоих
    # входов (Settings/side panel), это SharedPreferences, читаемая
    # `assert_theme_mode_pref`. Проверка НЕ дублирует глубокое применение темы
    # (перекраска UI/WebView — TC-047/048/049/059, side_panel_steps/browser_steps
    # цветовые ассерты): здесь проверяется только факт, что System сохранился как
    # финальный выбор, а не собственно визуальный эффект System-режима.
    settings_steps.assert_theme_mode_pref("SYSTEM")
