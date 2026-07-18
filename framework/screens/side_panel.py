"""Экран Side panel на вкладке Browse (app-under-test ui/browser/BrowseSidePanel.kt).
Узкая ручка-«гамбургер» у левого края (`PanelSide.LEFT` по умолчанию) разворачивает
панель с Contrast (тема) и A-/A+ (шрифт). Панель рендерится только когда активна
вкладка Browse (MainActivity.kt: `if (selectedTab == AppTab.BROWSE) BrowseSidePanel(...)`),
поэтому вызывающий код обязан быть на Browse до использования этого экрана.

Особенность Compose: когда панель свёрнута, весь Row (контент + ручка) сдвинут
через `animateDpAsState`/`offset`, и контент панели уезжает за левый край экрана
(`x < 0`) — узел по-прежнему присутствует в дереве (`is_present` его найдёт), но
не кликабелен, пока не завершится анимация разворота (~200ms). `tap()` (через
`element_to_be_clickable`) сам дожидается этого.
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.screens.base_screen import BaseScreen

TO_DARK = "Switch to dark mode"
TO_LIGHT = "Switch to light mode"
HOME_DESC = "AO3 home"
EXPAND_DESC = "Expand panel"
ENTER_FULLSCREEN = "Enter fullscreen"
EXIT_FULLSCREEN = "Exit fullscreen"


class SidePanel(BaseScreen):
    def is_expanded(self) -> bool:
        return self.is_present(self.by_desc("Collapse panel"), timeout=2)

    def expand(self):
        if not self.is_expanded():
            self.tap(self.by_desc("Expand panel"))
        return self

    def collapse(self):
        # Важно перед переключением нижней навигации (BottomNav): пока панель
        # развёрнута, её собственные кнопки (иконки рейтингов внизу колонки)
        # оказываются НИЖЕ на экране, чем нижняя ручка-пилюля, и эвристика
        # BottomNav._find_pill (самый нижний кликабельный не-WebView View)
        # промахивается мимо пилюли по кнопке панели.
        if self.is_expanded():
            self.tap(self.by_desc("Collapse panel"))
        return self

    def theme_desc_visible(self, desc: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc(desc), timeout=timeout or 5)

    def tap_contrast(self):
        # Одна и та же иконка Contrast — content-desc зависит от текущей темы
        # (BrowseSidePanel.kt: "Switch to light mode" в тёмной / "Switch to dark
        # mode" в светлой). Кликаем по тому варианту, что сейчас в дереве.
        if self.is_present(self.by_desc(TO_DARK), timeout=2):
            self.tap(self.by_desc(TO_DARK))
        else:
            self.tap(self.by_desc(TO_LIGHT))
        return self

    def increase_font(self):
        self.tap(self.by_text("A+"))
        return self

    def decrease_font(self):
        self.tap(self.by_text("A-"))
        return self

    def _button_container(self, text: str):
        # `enabled` на границе диапазона выставлен Compose на кликабельном
        # родителе TextButton (clickable=true), а не на дочернем TextView с
        # самим текстом «A+»/«A-» — тот всегда отдаёт enabled="true" независимо
        # от реального состояния кнопки (сверено на живом дереве page_source).
        # Родитель — единственный узел, где enabled отражает fontSizeStep-границу.
        return (AppiumBy.XPATH, f'//*[@text="{text}"]/..')

    def is_increase_enabled(self) -> bool:
        return self.is_enabled(self._button_container("A+"))

    def is_decrease_enabled(self) -> bool:
        return self.is_enabled(self._button_container("A-"))

    # --- Home (BrowseSidePanel.kt PanelIconButton Home, TC-057) ---
    def home_icon_visible(self, timeout: int | None = None) -> bool:
        # contentDescription фиксирован ("AO3 home") — не переключается по стейту,
        # в отличие от Contrast/Fullscreen (см. заметки TC-057.md).
        return self.is_present(self.by_desc(HOME_DESC), timeout=timeout or 5)

    def tap_home(self):
        self.tap(self.by_desc(HOME_DESC))
        return self

    # --- Fullscreen (BrowseSidePanel.kt PanelIconButton Fullscreen/FullscreenExit,
    # TC-058) — та же content-desc-переключаемая иконка, что Contrast: подпись
    # зависит от isFullscreen ("Enter fullscreen" / "Exit fullscreen"). ---
    def fullscreen_desc_visible(self, desc: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc(desc), timeout=timeout or 5)

    def tap_fullscreen(self):
        # Тот же паттерн, что tap_contrast: кликаем по варианту, что сейчас в дереве.
        if self.is_present(self.by_desc(ENTER_FULLSCREEN), timeout=2):
            self.tap(self.by_desc(ENTER_FULLSCREEN))
        else:
            self.tap(self.by_desc(EXIT_FULLSCREEN))
        return self

    def is_collapsed(self, timeout: int | None = None) -> bool:
        # Позитивная проверка ("Expand panel" появился) быстрее негативной (ждать
        # исчезновения "Collapse panel" пришлось бы до полного timeout) — ручка
        # переключает contentDescription синхронно с panelExpanded (см. docstring
        # модуля и BrowseSidePanel.kt:154), поэтому проверка не гонка.
        return self.is_present(self.by_desc(EXPAND_DESC), timeout=timeout or 5)
