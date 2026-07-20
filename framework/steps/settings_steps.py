"""Бизнес-шаги экрана Settings (GWT)."""
from __future__ import annotations

import allure

from framework.core import adb
from framework.core.waits import wait_for
from framework.data import seed_db
from framework.screens.base_screen import BaseScreen
from framework.screens.settings_screen import SettingsScreen


@allure.step("Then экран Settings отрисован")
def assert_settings_loaded(driver):
    assert SettingsScreen(driver).is_loaded(), "экран Settings не отрисовался (нет секции Theme)"


@allure.step("When выбрана тема {mode}")
def select_theme(driver, mode: str):
    SettingsScreen(driver).select_theme(mode)


@allure.step("Given в Settings включена опция «Auto-download favorite works»")
def enable_auto_download(driver):
    SettingsScreen(driver).set_auto_download(True)


@allure.step("When в Settings тумблер «Hide {rating_label} works» установлен в {enabled}")
def set_hide_rating(driver, rating_label: str, enabled: bool):
    SettingsScreen(driver).set_hide_rating(rating_label, enabled)


@allure.step("Then в Settings тумблер «Hide {rating_label} works» показывает {expected}")
def assert_rating_hidden(driver, rating_label: str, expected: bool):
    """TC-094: проверка состояния, установленного ДРУГИМ входом (side panel) — читает
    то же самое `uiState.isHidden(rating)`, что и `set_hide_rating`/TC-015."""
    actual = SettingsScreen(driver).is_rating_hidden(rating_label)
    assert actual == expected, (
        f"тумблер «Hide {rating_label} works» показывает {actual}, ожидали {expected}"
    )


@allure.step("When в Settings Display mode установлен в «{label}»")
def set_display_mode(driver, label: str):
    SettingsScreen(driver).tap_display_mode(label)


@allure.step("When открыт диалог «Clear all ratings» и подтверждён")
def clear_all_ratings(driver):
    s = SettingsScreen(driver)
    s.open_clear_all_dialog()
    assert s.clear_dialog_visible(), "диалог подтверждения очистки не появился"
    s.confirm_clear_all()


# --- TC-018/TC-019: диалог подтверждения Clear all ratings отдельно от полного
# цикла (`clear_all_ratings` выше, используется TC-004) — открытие/отмена/тексты
# проверяются по отдельности, без побочного эффекта подтверждения. ---

@allure.step("When пользователь нажимает кнопку «Clear…» (секция Data)")
def open_clear_all_dialog(driver):
    SettingsScreen(driver).open_clear_all_dialog()


@allure.step("Then появляется диалог подтверждения «Clear all ratings?»")
def assert_clear_all_dialog_visible(driver):
    assert SettingsScreen(driver).clear_dialog_visible(), (
        "диалог подтверждения «Clear all ratings?» не появился после нажатия «Clear…»"
    )


@allure.step("Then текст диалога предупреждает об удалении всех рейтингов")
def assert_clear_all_dialog_body(driver):
    assert SettingsScreen(driver).clear_dialog_body_visible(), (
        "текст диалога про удаление всех рейтингов не найден"
    )


@allure.step("When в диалоге «Clear all ratings?» нажат Cancel")
def cancel_clear_all_dialog(driver):
    SettingsScreen(driver).cancel_dialog()


@allure.step("Then диалог «Clear all ratings?» закрыт")
def assert_clear_all_dialog_closed(driver, timeout: int = 3):
    assert not SettingsScreen(driver).is_present(
        SettingsScreen(driver).by_text("Clear all ratings?"), timeout=timeout
    ), "диалог подтверждения остался открыт после Cancel"


@allure.step("Then в БД приложения рейтинги ещё присутствуют (диалог не подтверждён)")
def assert_ratings_present():
    """Обратная проверка к `assert_no_ratings` — тот же деградационный приём
    (образ без бинаря sqlite3 не блокирует Then, проверку тогда делает UI-слой
    вызывающего теста, см. `assert_no_ratings`)."""
    out = adb.run_as(
        'sh -c "sqlite3 databases/ao3_ratings.db \\"SELECT COUNT(*) FROM work_ratings\\" 2>/dev/null || echo NOSQLITE"'
    ).strip()
    if "NOSQLITE" in out or out == "":
        return
    assert out not in ("0", ""), f"ожидали >0 рейтингов в БД (диалог ещё не подтверждён), получили: {out}"


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


# --- Saved AO3 Filters (TC-085/TC-086: переименование фильтр-профиля) ---

@allure.step("When в Settings профиль «{old_name}» переименован в «{new_name}»")
def rename_filter_profile(driver, old_name: str, new_name: str):
    SettingsScreen(driver).rename_filter_profile(old_name, new_name)


@allure.step("Then в Settings ровно {expected} строк(и) с именем «{name}»")
def assert_filter_profile_count(driver, name: str, expected: int, timeout: int | None = None):
    """`confirmRenameFilter` пишет в Room асинхронно (`viewModelScope.launch(Dispatchers.IO)`,
    SettingsScreen.kt) — recomposed список отстаёт от тапа по "Rename" на короткое,
    но ненулевое окно (тот же класс гонки, что `browser_steps.assert_active_tab_url`
    описывает для `pendingNavigationUrl`). `SettingsScreen.count_filter_profile_occurrences`
    делает разовое `find_elements` без ожидания — одноразовое чтение сразу после
    `rename_filter_profile` было бы гонкой; здесь опрашиваем, пока счётчик не
    совпадёт с ожидаемым или не истечёт таймаут."""
    screen = SettingsScreen(driver)
    last: dict[str, int | None] = {"value": None}

    def _matches() -> bool:
        last["value"] = screen.count_filter_profile_occurrences(name)
        return last["value"] == expected

    try:
        wait_for(_matches, timeout=timeout, message=f"количество строк с именем «{name}» не сошлось")
    except TimeoutError:
        pass
    assert last["value"] == expected, (
        f"ожидали {expected} строк(и) с именем «{name}» в Settings, реально {last['value']}"
    )


@allure.step("Then в БД `filter_profiles` присутствуют записи с name=«{name}» и queryString {expected_query_strings}")
def assert_filter_profiles_have_query_strings(name: str, expected_query_strings: list[str]):
    """TC-086: после переименования в имя-дубликат обе строки таблицы `filter_profiles`
    обязаны иметь одинаковый `name`, но РАЗЛИЧНЫЕ исходные `queryString`
    (`confirmRenameFilter` — Upsert по `id`, меняет только `name` ОДНОЙ строки,
    `queryString` ни своей, ни чужой строки не трогает) — host-side чтение
    `seed_db.read_filter_profiles()`, тот же приём, что
    `backup_steps.assert_filter_profiles_match` использует для TC-021 (НЕ
    on-device sqlite3-бинарь — деградация `assert_no_ratings` к UI-фолбэку здесь
    неприменима: у этого кейса нет UI-фолбэка по построению, две одноимённые
    строки Settings не различить иначе, чем прямым чтением БД)."""
    actual = seed_db.read_filter_profiles()
    matching = [row for row in actual if row["name"] == name]
    assert len(matching) == len(expected_query_strings), (
        f"ожидали {len(expected_query_strings)} строк(и) с name=«{name}» в filter_profiles, "
        f"реально {len(matching)}: {matching}"
    )
    actual_query_strings = sorted(row["queryString"] for row in matching)
    assert actual_query_strings == sorted(expected_query_strings), (
        f"queryString записей с name=«{name}» не совпали: ожидали "
        f"{sorted(expected_query_strings)}, реально {actual_query_strings}"
    )


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
