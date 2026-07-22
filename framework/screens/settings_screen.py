"""Экран Settings (ui/settings/SettingsScreen.kt). Тексты сверены с исходником."""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.screens.base_screen import BaseScreen

THEME_LABELS = {"LIGHT": "Light", "DARK": "Dark", "SYSTEM": "System"}


class SettingsScreen(BaseScreen):
    # Заголовок секции темы
    THEME_HEADER = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Theme")')

    def scroll_to_text(self, text: str):
        return self.driver.find_element(
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiScrollable(new UiSelector().scrollable(true))'
            f'.scrollIntoView(new UiSelector().text("{text}"))',
        )

    def select_theme(self, mode: str):
        self.tap(self.by_text(THEME_LABELS[mode]))
        return self

    # --- Clear all ratings ---
    # Кнопка подписана «Clear…» (юникод-многоточие). В Compose клик висит на
    # родителе, а не на текстовом узле, поэтому находим сам текстовый узел
    # (не равный неклик. лейблу «Clear all ratings») и кликаем по его координатам.
    def open_clear_all_dialog(self):
        assert self.swipe_to_text("Clear all ratings"), "секция «Clear all ratings» не найдена прокруткой"
        els = self.driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textStartsWith("Clear")')
        target = next((e for e in els if e.text.strip() != "Clear all ratings"), None)
        assert target is not None, "кнопка «Clear…» не найдена"
        target.click()
        return self

    def clear_dialog_visible(self) -> bool:
        return self.is_present(self.by_text("Clear all ratings?"))

    # TC-018: тело диалога подтверждения (SettingsScreen.kt showClearDialog
    # AlertDialog `text`) — отдельный от заголовка узел, сверено с исходником.
    def clear_dialog_body_visible(self) -> bool:
        return self.is_present(self.by_text_contains("permanently delete all work ratings"))

    def confirm_clear_all(self):
        self.tap(self.by_text("Clear all"))
        return self

    def cancel_dialog(self):
        self.tap(self.by_text("Cancel"))
        return self

    def is_loaded(self) -> bool:
        return self.is_present(self.THEME_HEADER, timeout=10)

    # --- TC-107: font scaling smoke — presence/clickability без реального тапа
    # (изменение выбранной темы/шрифта не входит в сценарий кейса). Text-узел
    # сам по себе всегда несёт `clickable="false"` в этом экране (сверено живым
    # деревом, 2026-07-22) — `tap()`/`select_theme` попадают по нему только
    # потому, что Appium кликает по границам элемента, лежащим ВНУТРИ
    # кликабельного родителя; для честного чтения атрибута `clickable` нужен
    # именно родитель, тот же приём, что `_display_mode_button_locator`.
    def theme_button_locator(self, mode: str):
        return (AppiumBy.XPATH, f'//*[@text="{THEME_LABELS[mode]}"]/..')

    def font_size_button_locator(self, step: int):
        label = f"{100 + step * 15}%"
        return (AppiumBy.XPATH, f'//*[@text="{label}"]/..')

    BRIGHTNESS_SLIDER = (AppiumBy.CLASS_NAME, "android.widget.SeekBar")

    # --- Auto-download toggle (секция "Data", SettingsScreen.kt SettingsSwitchRow —
    # Compose Switch без text/content-desc). Тот же приём XPath `following::`, что и
    # `_delete_button_locator` ниже: ближайший checkable-узел ПОСЛЕ подписи строки в
    # document order (сверено живым деревом test-automator при автоматизации TC-032,
    # 2026-07-18 — строка "DATA" -> title TextView "Auto-download favorite works" ->
    # subtitle TextView -> сам Switch `class="android.view.View" checkable="true"`,
    # без промежуточных checkable-узлов между title и самим Switch). ---
    _AUTO_DOWNLOAD_SWITCH = (
        AppiumBy.XPATH,
        '(//*[@text="Auto-download favorite works"]/following::*[@checkable="true"])[1]',
    )

    def is_auto_download_checked(self, timeout: int | None = None) -> bool:
        el = self.find(self._AUTO_DOWNLOAD_SWITCH, timeout)
        return el.get_attribute("checked") == "true"

    def set_auto_download(self, enabled: bool):
        """Тумблер — таплю только если текущее состояние не совпадает с желаемым
        (идемпотентно, тот же приём, что `LibraryScreen.set_downloaded_only`)."""
        if self.is_auto_download_checked() != enabled:
            self.tap(self._AUTO_DOWNLOAD_SWITCH)
        return self

    # --- Per-rating "Hide {rating} works" toggle (секция "Content Visibility",
    # SettingsScreen.kt:718-759, TC-015) — тот же приём XPath `following::`, что и
    # `_AUTO_DOWNLOAD_SWITCH`: Compose `Switch` без text/content-desc, ближайший
    # checkable-узел ПОСЛЕ подписи строки в document order. `swipe_to_text` перед
    # поиском — тот же паттерн, что `open_clear_all_dialog`/`_swipe_to_profile`:
    # секция "Content Visibility" ниже "fold" сразу после открытия Settings.
    def _hide_rating_switch_locator(self, rating_label: str):
        return (
            AppiumBy.XPATH,
            f'(//*[@text="Hide {rating_label} works"]/following::*[@checkable="true"])[1]',
        )

    def is_rating_hidden(self, rating_label: str, timeout: int | None = None) -> bool:
        assert self.swipe_to_text(f"Hide {rating_label} works"), (
            f"строка «Hide {rating_label} works» не найдена прокруткой (Content Visibility)"
        )
        el = self.find(self._hide_rating_switch_locator(rating_label), timeout)
        return el.get_attribute("checked") == "true"

    def set_hide_rating(self, rating_label: str, enabled: bool):
        """Тумблер — таплю только если текущее состояние не совпадает с желаемым
        (идемпотентно, тот же приём, что `set_auto_download`)."""
        if self.is_rating_hidden(rating_label) != enabled:
            self.tap(self._hide_rating_switch_locator(rating_label))
        return self

    # --- Display mode Hide/Dim (секция "Content Visibility", SettingsScreen.kt:779-798,
    # TC-092/093) — `TextButton` с текстом ровно "Hide"/"Dim" (label из
    # `listOf("hide" to "Hide", "dim" to "Dim")`), клик висит на кликабельном
    # РОДИТЕЛЕ, не на дочернем `Text` — тот же приём, что `SidePanel._button_container`
    # (`framework/screens/side_panel.py`) использует для A-/A+. "Display mode" —
    # отдельная строка ниже per-rating тумблеров, `swipe_to_text` перед поиском
    # обязателен (та же ситуация "fold", что у `is_rating_hidden`/`_swipe_to_profile`).
    def _display_mode_button_locator(self, label: str):
        return (AppiumBy.XPATH, f'//*[@text="{label}"]/..')

    def tap_display_mode(self, label: str):
        assert self.swipe_to_text("Display mode"), (
            "секция «Display mode» не найдена прокруткой (Content Visibility)"
        )
        self.tap(self._display_mode_button_locator(label))
        return self

    # --- Saved AO3 Filters (секция "SAVED AO3 FILTERS", SettingsScreen.kt) — TC-042 ---
    # `Rename`/`Delete` IconButton каждой строки делят ОДИН и тот же content-desc
    # на весь экран (Compose IconButton не мержит семантику Icon-child со своим
    # clickable-родителем — сверено живым деревом, scripts/ui_snapshot.py: узел
    # content-desc="Delete" — отдельный ЛИСТ с clickable="false", кликабелен сам
    # родительский View БЕЗ описания). При >1 засеянном профиле `by_desc("Delete")`
    # неоднозначен — единственный надёжный способ взять "чужой" Delete: XPath
    # `following::` от текстового узла с ИМЕНЕМ профиля до БЛИЖАЙШЕГО следующего
    # content-desc="Delete" в document order (порядок в дереве строго
    # name -> summary -> Rename -> Delete -> [следующий профиль] — сверено тем же
    # снапшотом). Appium `.click()` тапает по bounds листа независимо от его
    # собственного атрибута `clickable` — тап попадает в touch-область родительской
    # IconButton (тот же приём, что `SettingsScreen.open_clear_all_dialog` уже
    # использует для некликабельного текстового узла).
    # `has_filter_profile`/`delete_filter_profile` СНАЧАЛА свайпают к тексту профиля
    # (`swipe_to_text`, тот же приём, что `open_clear_all_dialog`) — секция
    # «SAVED AO3 FILTERS» ниже "fold" сразу после открытия Settings (сверено живым
    # деревом: строки профилей физически ОТСУТСТВУЮТ в дампе, пока не проскроллено —
    # это НЕ просто bounds за экраном, узлов нет вовсе, `is_present` без свайпа
    # детерминированно возвращает False).
    def _swipe_to_profile(self, name: str) -> bool:
        """Свайп вниз, а если не нашли (например, экран уже проскроллен НИЖЕ секции
        предыдущим вызовом — свайп вверх/вниз не сбрасывает позицию сам) — фолбэк
        свайпом вверх."""
        return self.swipe_to_text(name) or self.swipe_up_to_text(name)

    def has_filter_profile(self, name: str, timeout: int | None = None) -> bool:
        if not self._swipe_to_profile(name):
            return False
        return self.is_present(self.by_text(name), timeout=timeout if timeout is not None else 8)

    def _delete_button_locator(self, name: str):
        return (AppiumBy.XPATH, f'(//*[@text="{name}"]/following::*[@content-desc="Delete"])[1]')

    def delete_filter_profile(self, name: str):
        assert self._swipe_to_profile(name), f"профиль «{name}» не найден прокруткой"
        self.tap(self._delete_button_locator(name))
        return self

    def count_filter_profile_occurrences(self, name: str) -> int:
        """Считает узлы `by_text(name)`, а не `is_present` — нужно для TC-086, где
        два профиля могут одновременно носить одинаковое имя (переименование в
        имя-дубликат не проверяется на уникальность, см. `confirmRenameFilter`) и
        обычные локаторы по имени неразличимы между строками."""
        assert self._swipe_to_profile(name), f"профиль «{name}» не найден прокруткой"
        return len(self.driver.find_elements(*self.by_text(name)))

    # --- Rename filter profile (SettingsScreen.kt requestRenameFilter/
    # confirmRenameFilter, диалог "Rename filter") — TC-085/TC-086. Тот же приём
    # disambiguation, что `_delete_button_locator`: XPath `following::` от
    # текстового узла с именем профиля до БЛИЖАЙШЕГО content-desc="Rename" в
    # document order (порядок в дереве name -> summary -> Rename -> Delete, см.
    # комментарий выше) — Rename стоит ПЕРЕД Delete, тот же класс неоднозначности
    # при >1 засеянном профиле.
    # Поле диалога — `InputField` (BasicTextField-обёртка, ui/components/InputField.kt),
    # тот же native-рендер `android.widget.EditText`, что и `OutlinedTextField`
    # диалога "Save filter" (`browser_screen.py::_FILTER_NAME_FIELD`) — переиспользуем
    # тот же локатор по className (на экране активен только один диалог одновременно).
    # Поле диалога предзаполнено ТЕКУЩИМ именем (`dialogName by remember(filter.id)
    # { mutableStateOf(filter.name) }`) — `.clear()` обязателен перед вводом нового
    # имени, иначе получится конкатенация (см. заметки TC-085.md).
    _RENAME_NAME_FIELD = (AppiumBy.ANDROID_UIAUTOMATOR,
                          'new UiSelector().className("android.widget.EditText")')

    def _rename_button_locator(self, name: str):
        return (AppiumBy.XPATH, f'(//*[@text="{name}"]/following::*[@content-desc="Rename"])[1]')

    def open_rename_dialog(self, name: str):
        assert self._swipe_to_profile(name), f"профиль «{name}» не найден прокруткой"
        self.tap(self._rename_button_locator(name))
        return self

    def rename_dialog_visible(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text("Rename filter"), timeout=timeout if timeout is not None else 5)

    def enter_rename_name(self, new_name: str):
        field = self.find(self._RENAME_NAME_FIELD)
        field.clear()
        field.send_keys(new_name)
        return self

    def confirm_rename(self):
        self.tap(self.by_text("Rename"))
        return self

    def rename_filter_profile(self, old_name: str, new_name: str):
        self.open_rename_dialog(old_name)
        self.enter_rename_name(new_name)
        self.confirm_rename()
        return self
