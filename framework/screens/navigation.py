"""Нижняя навигация приложения (Ao3BottomNav: Browse | Library | Settings).

Особенность приложения: на вкладке BROWSE панель навигации скрыта за нижней
ручкой-пилюлей (AnimatedVisibility, visible = selectedTab != BROWSE || navExpanded,
см. app ui/browser/BottomBar.kt). Поэтому перед переключением вкладку-ручку нужно
раскрыть. После ухода с Browse навигация остаётся видимой.

Ручка не имеет content-desc — это самый нижний полноширинный кликабельный View.
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.screens.base_screen import BaseScreen

BROWSE = "Browse"
LIBRARY = "Library"
SETTINGS = "Settings"


class BottomNav(BaseScreen):
    def _nav_visible(self) -> bool:
        return self.is_present(self.by_text(LIBRARY), timeout=3)

    def _expand_pill(self) -> None:
        """Тапает нижнюю ручку-пилюлю (самый нижний кликабельный не-WebView View)."""
        els = self.driver.find_elements(AppiumBy.XPATH, '//*[@clickable="true"]')
        cand = [e for e in els if "WebView" not in (e.get_attribute("class") or "")]
        if not cand:
            return
        pill = max(cand, key=lambda e: e.rect["y"])
        pill.click()

    def ensure_visible(self):
        if not self._nav_visible():
            self._expand_pill()
        return self

    def open(self, tab_label: str):
        self.ensure_visible()
        self.tap(self.by_text(tab_label))
        return self

    def go_browse(self):
        return self.open(BROWSE)

    def go_library(self):
        return self.open(LIBRARY)

    def go_settings(self):
        return self.open(SETTINGS)
