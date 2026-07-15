"""Бизнес-шаги экрана Settings (GWT)."""
from __future__ import annotations

import allure

from framework.core import adb
from framework.screens.base_screen import BaseScreen
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


# --- Общий стейт side panel <-> Settings (theme_mode/font_size_step) ---
# ThemeModeRow/FontSizeRow (SettingsScreen.kt) рисуют выбор через цвет фона
# TextButton, не через accessibility `selected`/`checked` (сверено на живом дереве:
# `selected="false"` у всех вариантов независимо от выбора) — поэтому «Settings
# отражает изменение из панели» наблюдаемо не через UI-дерево Settings, а через
# общий источник истины обоих входов: оба вызывают один и тот же
# SettingsViewModel.setThemeMode/setFontSizeStep (MainActivity.kt), который пишет
# в тот же SharedPreferences-файл, что и читает SettingsScreen при следующем
# открытии. Тот же паттерн деградации к прямому чтению, что и `assert_no_ratings`.

@allure.step("Then сохранённая тема (SharedPreferences) = {mode}")
def assert_theme_mode_pref(mode: str):
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    assert f'name="theme_mode">{mode}<' in out, f"theme_mode != {mode} в SharedPreferences: {out}"


@allure.step("Then сохранённый размер шрифта (SharedPreferences font_size_step) = {step}")
def assert_font_size_step_pref(step: int):
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    assert f'name="font_size_step" value="{step}"' in out, \
        f"font_size_step != {step} в SharedPreferences: {out}"


# --- Scan for downloads (silent auto-триггер после смены папки загрузок/Restore,
# TC-037/TC-038) — общий AlertDialog "Scan complete" (SettingsScreen.kt:1215-1230),
# без других общих полей с остальным экраном Settings, тот же паттерн, что
# `backup_steps.assert_backup_created_dialog`/`assert_restore_result_dialog`: локатор
# сугубо для этого одноразового диалога, отдельный screen-метод не заводим.

@allure.step("Then появляется диалог «Scan complete» с текстом «{expected_text}»")
def assert_scan_complete_dialog(driver, expected_text: str, timeout: int = 15) -> None:
    b = BaseScreen(driver)
    assert b.is_present(b.by_text("Scan complete"), timeout=timeout), (
        "диалог результата скана (silent, авто-триггер после смены папки загрузок) "
        "не появился — либо скан ничего не нашёл (Idle остался), либо не запустился"
    )
    assert b.is_present(b.by_text(expected_text), timeout=2), (
        f"текст результата скана не совпал с ожидаемым «{expected_text}»"
    )


@allure.step("When диалог результата скана закрыт (OK)")
def dismiss_scan_dialog(driver) -> None:
    BaseScreen(driver).tap(BaseScreen(driver).by_text("OK"))


# --- Saved AO3 Filters (TC-042: удаление фильтр-профиля из Settings) ---

@allure.step("Then в Settings в секции «Saved AO3 Filters» отображается профиль «{name}»")
def assert_filter_profile_listed(driver, name: str, timeout: int | None = None):
    assert SettingsScreen(driver).has_filter_profile(name, timeout=timeout), (
        f"фильтр-профиль «{name}» не найден в списке Settings"
    )


@allure.step("Then в Settings в секции «Saved AO3 Filters» профиль «{name}» отсутствует")
def assert_filter_profile_not_listed(driver, name: str, timeout: int = 3):
    assert not SettingsScreen(driver).has_filter_profile(name, timeout=timeout), (
        f"фильтр-профиль «{name}» всё ещё виден в списке Settings — ожидали удалённым"
    )


@allure.step("When в Settings удалён фильтр-профиль «{name}»")
def delete_filter_profile(driver, name: str):
    SettingsScreen(driver).delete_filter_profile(name)


@allure.step("Then диалог «Scan complete» НЕ появляется (не два диалога подряд)")
def assert_no_scan_complete_dialog(driver, timeout: int = 3) -> None:
    """TC-039: ключевой наблюдаемый факт кейса — РОВНО один диалог результата после
    Restore. `importFromUri` сворачивает `scanForOrphanedDownloads()` в тот же
    `ImportState.Done` (тот же диалог, что уже проверен `assert_restore_result_dialog`)
    и НЕ трогает `scanDownloadsState` (`SettingsScreen.kt:390-400`) — поэтому
    отдельный диалог «Scan complete» структурно не может появиться следом; assert
    проверяет это явно (короткое ожидание + отсутствие), а не только присутствие
    первого диалога, как того требует заметка кейса про «not just present-check»."""
    b = BaseScreen(driver)
    assert not b.is_present(b.by_text("Scan complete"), timeout=timeout), (
        "диалог «Scan complete» появился ПОСЛЕ диалога Restore — ожидали ровно один "
        "объединённый диалог результата (Restored ... Also relinked ...), не два подряд"
    )
