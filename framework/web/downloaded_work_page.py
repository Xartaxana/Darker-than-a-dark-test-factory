"""DOM локально открытого (file://) скачанного файла работы — проверка инжекции
из BrowserScreen.kt `loadTabContent`/`injectReaderCss` (TC-034): мобильный viewport
+ `<style id="ao3-reader-css">`, применённые в обход WebViewClient (см. комментарий
в app-under-test)."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class DownloadedWorkPage(BasePage):
    def wait_viewport_meta(self, timeout: int | None = None):
        return self.wait_css(selectors.VIEWPORT_META, timeout=timeout)

    def wait_reader_css(self, timeout: int | None = None):
        return self.wait_css(selectors.READER_CSS_STYLE, timeout=timeout)

    def probe_link(self, timeout: int | None = None):
        """TC-103 (security/file-access): ссылка `#probe-link`, встроенная только в
        HTML-фикстуру этого кейса (см. `test_security_file_access.py`), целится в
        internal-файл приложения вне директории загрузок."""
        return self.wait_css(selectors.PROBE_LINK, timeout=timeout)
