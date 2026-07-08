"""Измерение относительного размера текста в WebView (для textZoom/fontSizeStep,
см. app-under-test BrowserScreen.kt LaunchedEffect(fontSizeStep) — `wv.settings.textZoom`
масштабирует рендеринг текста на уровне WebView, а не CSS, поэтому единственный
наблюдаемый признак — geometry отрендеренного элемента (getBoundingClientRect),
не document.body.style/getComputedStyle)."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class ReaderPage(BasePage):
    def heading_height(self) -> float:
        el = self.wait_css(selectors.PAGE_HEADING)
        return el.rect["height"]
