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

    def confirm_clear_all(self):
        self.tap(self.by_text("Clear all"))
        return self

    def cancel_dialog(self):
        self.tap(self.by_text("Cancel"))
        return self

    def is_loaded(self) -> bool:
        return self.is_present(self.THEME_HEADER, timeout=10)
