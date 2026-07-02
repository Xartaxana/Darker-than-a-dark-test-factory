"""Страница работы AO3 (/works/{id}) внутри WebView."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class WorkPage(BasePage):
    def current_work_id(self) -> str | None:
        url = self.driver.current_url or ""
        import re
        m = re.search(r"/works/(\d+)", url)
        return m.group(1) if m else None

    def has_badge(self) -> bool:
        return self.exists(selectors.RATING_BADGE)

    def title_text(self) -> str:
        el = self.css("h2.title") if self.exists("h2.title") else None
        return el.text.strip() if el else ""
