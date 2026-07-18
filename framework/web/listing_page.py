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

    def note_button(self, work_id: str):
        """Инжектированная Note-кнопка (карандаш, `ao3_bridge.js::makeNoteButton`) —
        рендерится только при непустом `comment`. ВНИМАНИЕ: клик по НЕЙ лишь
        показывает всплывающую подсказку с текстом заметки (`showTooltip`), не
        открывает overlay напрямую — см. `note_tooltip` (TC-044)."""
        blurb = selectors.blurb_by_work_id(work_id)
        return self.wait_css(f"{blurb} {selectors.NOTE_BUTTON}")

    def note_tooltip(self):
        """Всплывающая подсказка Note-кнопки — клик по НЕЙ (не по самой кнопке)
        вызывает `signalRateWithNote`, открывающий нативный overlay с развёрнутым
        комментарием (см. `note_button`, TC-044)."""
        return self.wait_css(selectors.NOTE_TOOLTIP)

    def rated_button_count(self, work_id: str) -> int:
        """Количество Rate-кнопок среди ВСЕХ вхождений блёрба `work_id` на странице
        (может быть >1 — TC-012, `listing_duplicate_work.mitm`), у которых бейдж уже
        проставлен (непрозрачный фон, см. `badge_for`). Доказывает, что `applyRatings`
        обновляет ВСЕ вхождения, не только первое найденное querySelector'ом."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(f"{blurb} {selectors.RATE_BUTTON}")
        count = 0
        for el in els:
            bg = el.value_of_css_property("background-color")
            if bg not in ("", "transparent", "rgba(0, 0, 0, 0)"):
                count += 1
        return count

    def tag_link_highlighted(self, work_id: str, tag_text: str) -> bool:
        """`a.tag` внутри блёрба работы `work_id` с точным текстом `tag_text` —
        читает атрибут `data-ao3-tag-hl`, проставляемый `highlightWorkTags`
        (ao3_bridge.js) только реально совпавшим личным тегам (TC-056). Возвращает
        False и если тег с таким текстом вообще не найден на карточке (структурная
        ошибка локатора неотличима здесь от "не подсвечен" — вызывающий код TC-056
        сначала проверяет ПОЛОЖИТЕЛЬНЫЙ случай, что исключает эту двусмысленность
        для отрицательных проверок в том же тесте)."""
        blurb = selectors.blurb_by_work_id(work_id)
        for el in self.css_all(f"{blurb} a.tag"):
            if el.text.strip() == tag_text:
                return el.get_attribute("data-ao3-tag-hl") is not None
        return False
