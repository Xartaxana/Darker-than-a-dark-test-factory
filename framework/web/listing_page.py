"""Страница-листинг AO3 (блёрбы работ) внутри WebView + элементы, инжектированные bridge."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class ListingPage(BasePage):
    def blurb_count(self) -> int:
        return len(self.css_all(selectors.WORK_BLURB))

    def has_bridge_rate_buttons(self) -> bool:
        """Признак того, что bridge отработал: инжектированы Rate-кнопки."""
        return self.exists(selectors.RATE_BUTTON)

    def badge_for(self, work_id: str) -> bool:
        blurb = selectors.blurb_by_work_id(work_id)
        return self.exists(f"{blurb} {selectors.RATING_BADGE}")

    def is_hidden(self, work_id: str) -> bool:
        """Работа скрыта фильтрацией (bridge проставляет display:none)."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(blurb)
        if not els:
            return True
        return els[0].value_of_css_property("display") == "none"
