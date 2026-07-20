"""Страница-листинг AO3 (блёрбы работ) внутри WebView + элементы, инжектированные bridge."""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class ListingPage(BasePage):
    def blurb_count(self) -> int:
        return len(self.css_all(selectors.WORK_BLURB))

    def blurb_work_ids(self) -> list[str]:
        """Work id для каждого найденного `li[id^="work_"].work.blurb`, извлечённый
        ТЕМ ЖЕ способом, что `ao3_bridge.js` (`li.id.replace('work_', '')`,
        `applyAllFilters`/`applyRatings`) — прямое зеркало DOM-контракта листинга
        (TC-068/069), не побочный продукт другого локатора."""
        return [el.get_attribute("id").replace("work_", "", 1) for el in self.css_all(selectors.WORK_BLURB)]

    def heading_count(self) -> int:
        """Количество видимых заголовков работ (`h4.heading`) на странице —
        независимая от `WORK_BLURB` проба, что селектор блёрба не занижает/
        завышает набор (TC-068: рекламные/promoted блоки листинга AO3 визуально
        похожи на карточку работы, но не `li.work.blurb`)."""
        return len(self.css_all(selectors.WORK_HEADING))

    def rate_button_state(self, work_id: str) -> dict:
        """Структурная+визуальная проба Rate-кнопки ОДНОГО блёрба (TC-070/071):
        сколько `[data-ao3-btn-wrap]`/`[data-ao3-rate-btn]` внутри него, к какому
        work id привязана кнопка (`data-ao3-rate-btn`) и её текущий фон (для
        различения оценено/не оценено — тот же признак, что `badge_for`)."""
        blurb = selectors.blurb_by_work_id(work_id)
        wraps = self.css_all(f"{blurb} {selectors.BTN_WRAP}")
        buttons = self.css_all(f"{blurb} {selectors.RATE_BUTTON}")
        return {
            "wrap_count": len(wraps),
            "button_count": len(buttons),
            "attr": buttons[0].get_attribute("data-ao3-rate-btn") if buttons else None,
            "bg": buttons[0].value_of_css_property("background-color") if buttons else None,
        }

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

    def opacity_of(self, work_id: str) -> str:
        """CSS `opacity` вычисленный для блёрба `work_id` (TC-092/093) — dim-режим
        (`ao3_bridge.js::applyAllFilters`, стр.110-113) выставляет `li.style.opacity
        = '0.3'` для работ, исключённых фильтром, вместо `display:none` у hide-режима.
        Пустая строка, если блёрб вообще не найден в DOM."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(blurb)
        if not els:
            return ""
        return els[0].value_of_css_property("opacity")

    def is_dimmed(self, work_id: str) -> bool:
        """Работа исключена фильтром в dim-режиме: блёрб ОСТАЁТСЯ отрендеренным
        (`display != 'none'`), но затемнён (`opacity == '0.3'`) — визуальный аналог
        `is_hidden` для `filterDisplayMode == 'dim'` (см. `opacity_of` за источником)."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(blurb)
        if not els:
            return False
        display = els[0].value_of_css_property("display")
        opacity = els[0].value_of_css_property("opacity")
        return display != "none" and opacity == "0.3"

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

    def has_note_button(self, work_id: str) -> bool:
        """Работа `work_id` имеет инжектированную Note-кнопку в своём
        `[data-ao3-btn-wrap]` (TC-074/075: биусловное присутствие по факту
        непустого `comment`, `applyRatings` стр.399-415)."""
        blurb = selectors.blurb_by_work_id(work_id)
        return self.exists(f"{blurb} {selectors.NOTE_BUTTON}")

    def note_button_title(self, work_id: str) -> str | None:
        """Атрибут `title` инжектированной Note-кнопки — `applyRatings` кладёт туда
        засеянный/сохранённый `comment` дословно (см. `makeNoteButton`). `None`, если
        кнопки нет вовсе (вызывающий код TC-074/075 сначала проверяет присутствие)."""
        blurb = selectors.blurb_by_work_id(work_id)
        els = self.css_all(f"{blurb} {selectors.NOTE_BUTTON}")
        return els[0].get_attribute("title") if els else None

    def has_tag_button(self, work_id: str) -> bool:
        """Работа `work_id` имеет инжектированную Tag-кнопку в своём
        `[data-ao3-btn-wrap]` (TC-076/077: биусловное присутствие по факту непустой
        РАЗНОСТИ (личные теги \\ AO3-теги карточки), `getCustomTags`/`applyRatings`
        стр.417-433)."""
        blurb = selectors.blurb_by_work_id(work_id)
        return self.exists(f"{blurb} {selectors.TAG_BUTTON}")

    def own_tags(self, work_id: str) -> list[str]:
        """Текст СОБСТВЕННЫХ AO3-тегов карточки `work_id` (`ul.tags.commas li a.tag`) —
        тот же селектор, что `ao3_bridge.js::getCustomTags` использует для построения
        `ao3Set` (TC-076/077: нужен, чтобы подобрать личный тег, заведомо
        отсутствующий/заведомо совпадающий с набором конкретной карточки на живом
        листинге, где состав тегов не детерминирован заранее)."""
        blurb = selectors.blurb_by_work_id(work_id)
        return [el.text.strip() for el in self.css_all(f"{blurb} {selectors.TAGS_CONTAINER} a.tag")]

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
