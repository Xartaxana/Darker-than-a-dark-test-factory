"""Нижняя навигация приложения (Ao3BottomNav: Browse | Library | Settings).

Особенность приложения: на вкладке BROWSE панель навигации скрыта за нижней
ручкой-пилюлей (AnimatedVisibility, visible = selectedTab != BROWSE || navExpanded,
см. app ui/browser/BottomBar.kt). Поэтому перед переключением вкладку-ручку нужно
раскрыть. После ухода с Browse навигация остаётся видимой.

Ручка не имеет content-desc — это самый нижний полноширинный кликабельный View.
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException

from framework.core.waits import wait_until
from framework.screens.base_screen import BaseScreen

BROWSE = "Browse"
LIBRARY = "Library"
SETTINGS = "Settings"


class BottomNav(BaseScreen):
    def _nav_visible(self) -> bool:
        return self.is_present(self.by_text(LIBRARY), timeout=3)

    _NONE_FOUND = object()  # сентинел «список стабилен, кандидатов нет» (не ретраить)

    # AT-BUG-019: исключаем не только элемент, чей СОБСТВЕННЫЙ класс содержит
    # "WebView" (сам контейнер android.webkit.WebView), но и любой a11y-узел,
    # у которого такой контейнер есть СРЕДИ ПРЕДКОВ — виртуальные дочерние узлы
    # живой веб-страницы (ссылки/чекбоксы/кнопки, классы android.view.View /
    # android.widget.*) неотличимы от нативных Compose-элементов по имени
    # собственного класса, но всегда потомки android.webkit.WebView в дереве.
    # ancestor-or-self — на случай, если сам контейнер WebView когда-либо
    # окажется clickable="true" (сейчас не наблюдалось, но fail-safe дешёвый).
    _PILL_CANDIDATES_XPATH = (
        '//*[@clickable="true"]'
        '[not(ancestor-or-self::*[contains(@class,"WebView")])]'
    )

    def _find_pill(self):
        """Самый нижний кликабельный не-WebView View и не-потомок WebView
        (ручка-пилюля). Дерево может меняться под рукой во время перерисовки
        WebView — читаем список + атрибуты атомарно и ретраим через wait_until
        при stale/разрыве соединения, а не падаем с первой попытки (см.
        TC-016/TC-007/TC-008: панель работы открывается сразу после навигации
        по WebView, дерево ещё «оседает»)."""
        def _snapshot(d):
            try:
                els = d.find_elements(AppiumBy.XPATH, self._PILL_CANDIDATES_XPATH)
                return max(els, key=lambda e: e.rect["y"]) if els else self._NONE_FOUND
            except (StaleElementReferenceException, WebDriverException):
                return False
        result = wait_until(self.driver, _snapshot, timeout=10,
                            message="не удалось получить стабильный список кликабельных элементов")
        return None if result is self._NONE_FOUND else result

    def _expand_pill(self) -> None:
        """Тапает нижнюю ручку-пилюлю (самый нижний кликабельный не-WebView View)."""
        pill = self._find_pill()
        if pill is None:
            return
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
