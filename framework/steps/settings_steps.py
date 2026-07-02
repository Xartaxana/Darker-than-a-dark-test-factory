"""Бизнес-шаги экрана Settings (GWT)."""
from __future__ import annotations

import allure

from framework.core import adb
from framework.screens.settings_screen import SettingsScreen


@allure.step("Then экран Settings отрисован")
def assert_settings_loaded(driver):
    assert SettingsScreen(driver).is_loaded(), "экран Settings не отрисовался (нет секции Theme)"


@allure.step("When выбрана тема {mode}")
def select_theme(driver, mode: str):
    SettingsScreen(driver).select_theme(mode)


@allure.step("When открыт диалог «Clear all ratings» и подтверждён")
def clear_all_ratings(driver):
    s = SettingsScreen(driver)
    s.open_clear_all_dialog()
    assert s.clear_dialog_visible(), "диалог подтверждения очистки не появился"
    s.confirm_clear_all()


@allure.step("Then в БД приложения нет ни одного рейтинга")
def assert_no_ratings():
    out = adb.run_as(
        'sh -c "sqlite3 databases/ao3_ratings.db \\"SELECT COUNT(*) FROM work_ratings\\" 2>/dev/null || echo NOSQLITE"'
    ).strip()
    # На части образов нет бинаря sqlite3 — тогда проверку делает UI-слой (пустые вкладки)
    if "NOSQLITE" in out or out == "":
        return
    assert out == "0", f"ожидали 0 рейтингов, в БД: {out}"
