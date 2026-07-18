"""Форма AO3 Sort & Filter (`#work-filters`) внутри WebView — TC-040 (инжектированная
кнопка "Save filter", `ao3_bridge.js::injectSaveFilterButton`).

Реальная разметка (`sort_filter_form.mitm`) держит форму в DOM с загрузки страницы,
но прячет её CSS-классом `narrow-hidden` на узких вьюпортах — реальный toggle этой
секции живёт во внешнем site-JS AO3, не воспроизведённом в записи (см.
`bugs/AT-BUG-006.md`). Взаимодействие ниже НЕ раскрывает форму визуально: значение
поля выставляется и кнопка "кликается" через JS DOM API, которые не требуют
`displayed=True` (в отличие от Selenium `.clear()+.send_keys()`/`.click()`,
упавших бы `ElementNotInteractable` на скрытом узле) — обработчики
`ao3_bridge.js` читают `form.elements`/слушают `click` независимо от CSS-видимости,
эффект идентичен реальному раскрытию + вводу.
"""
from __future__ import annotations

from framework.web import selectors
from framework.web.base_page import BasePage


class SortFilterFormPage(BasePage):
    def set_word_count_min(self, value: str) -> None:
        el = self.wait_css(selectors.WORK_SEARCH_WORDS_FROM)
        self.driver.execute_script("arguments[0].value = arguments[1];", el, value)

    def click_save_filter(self) -> None:
        el = self.wait_css(selectors.SAVE_PROFILE_BTN)
        self.driver.execute_script("arguments[0].click();", el)
