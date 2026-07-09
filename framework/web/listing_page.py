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
        """Работе W проставлен рейтинг — наблюдаемо по НЕПРОЗРАЧНОМУ фону
        инжектированной Rate-кнопки (`ao3_bridge.js::updateRateButton` красит
        `RATE_BUTTON` цветом `BADGE[rating].bg`, отдельного элемента-«бейджа» в
        разметке нет — см. AT-BUG-004 инкремент 3, `selectors.py` про
        `[data-ao3-badge]`). Непрозрачность проверяется по вычисленному
        `background-color`: до простановки рейтинга — `rgba(0, 0, 0, 0)`
        (эмпирически сверено на живом дереве, transparent-инлайн-стиль браузер
        нормализует в rgba с нулевой альфой)."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(f"{blurb} {selectors.RATE_BUTTON}")
        if not els:
            return False
        bg = els[0].value_of_css_property("background-color")
        return bg not in ("", "transparent", "rgba(0, 0, 0, 0)")

    def is_hidden(self, work_id: str) -> bool:
        """Работа скрыта фильтрацией (bridge проставляет display:none)."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(blurb)
        if not els:
            return True
        return els[0].value_of_css_property("display") == "none"

    def rate_button(self, work_id: str):
        """Инжектированная Rate-кнопка (`ao3_bridge.js::makeRateButton`) в блёрбе
        работы — клик по ней открывает нативный `RatingOverlay` (bottom-sheet)."""
        blurb = selectors.blurb_by_work_id(work_id)
        return self.wait_css(f"{blurb} {selectors.RATE_BUTTON}")
