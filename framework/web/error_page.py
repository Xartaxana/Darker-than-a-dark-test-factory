"""DOM кастомной themed error page приложения (BrowserScreen.kt buildErrorHtml) —
показывается вместо дефолтной страницы ошибки WebView/Chrome при `onReceivedError`
главного фрейма (TC-046). Загружена через `loadDataWithBaseURL("about:blank", ...)`
— не попадает в историю навигации, `driver.current_url` после показа остаётся
`about:blank` (см. `browser_steps.assert_error_page_shown`)."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class ErrorPage(BasePage):
    def wait_heading(self, timeout: int | None = None):
        return self.wait_css(selectors.ERROR_PAGE_HEADING, timeout=timeout)

    def retry_link(self, timeout: int | None = None):
        return self.wait_css(selectors.ERROR_PAGE_RETRY_LINK, timeout=timeout)
