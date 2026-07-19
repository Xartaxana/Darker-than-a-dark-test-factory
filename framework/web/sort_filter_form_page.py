"""Форма AO3 Sort & Filter (`#work-filters`) внутри WebView — TC-040 (инжектированная
кнопка "Save filter", `ao3_bridge.js::injectSaveFilterButton`), TC-078/079/080/081
(инжектированные main-pairing include/exclude чекбоксы,
`injectMainPairingCheckbox`/`injectExcludeMainPairingCheckbox`), TC-082/083
(идемпотентность инъекции "Save filter" при повторных мутациях формы).

Реальная разметка (`sort_filter_form.mitm`) держит форму в DOM с загрузки страницы,
но прячет её CSS-классом `narrow-hidden` на узких вьюпортах — реальный toggle этой
секции живёт во внешнем site-JS AO3, не воспроизведённом в записи (см.
`bugs/AT-BUG-006.md`). Взаимодействие ниже НЕ раскрывает форму визуально: значение
поля выставляется и кнопка "кликается" через JS DOM API, которые не требуют
`displayed=True` (в отличие от Selenium `.clear()+.send_keys()`/`.click()`,
упавших бы `ElementNotInteractable` на скрытом узле) — обработчики
`ao3_bridge.js` читают `form.elements`/слушают `click` независимо от CSS-видимости,
эффект идентичен реальному раскрытию + вводу. Relationship-чекбоксы ниже —
тот же приём: `element.click()` через JS вызывает НАСТОЯЩИЙ клик (не просто меняет
`.checked`), т.е. штатно всплывает событие `change`, на которое подписан
`updateAvailability` внутри `ao3_bridge.js` (стр.719-735/816-820)."""
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

    def toggle_relationship_checkbox(self, container_selector: str, index: int) -> None:
        """Кликает по `index`-му РЕАЛЬНОМУ (не инжектированному) relationship-
        чекбоксу внутри контейнера (`#include_relationship_tags`/
        `#exclude_relationship_tags`) — сама реальная разметка AO3 держит их как
        `<dd id="...">` (не `<ul>`, несмотря на имя переменной `ul` в
        `ao3_bridge.js`), инжектированный чекбокс исключён обоими `:not(...)`
        независимо от того, в каком из двух контейнеров он сидит."""
        self.driver.execute_script(
            """
            var container = document.querySelector(arguments[0]);
            var cbs = container.querySelectorAll(
                'input[type="checkbox"]:not([data-ao3-main-pairing-cb]):not([data-ao3-excl-main-pairing-cb])'
            );
            cbs[arguments[1]].click();
            """,
            container_selector, index,
        )

    def checkbox_availability_state(self, checkbox_selector: str) -> dict | None:
        """`disabled`/`label.style.opacity` инжектированного чекбокса (main-pairing
        include/exclude) — `None`, если чекбокс ещё не инжектирован."""
        return self.driver.execute_script(
            """
            var cb = document.querySelector(arguments[0]);
            if (!cb) return null;
            var label = cb.closest('label');
            return {disabled: cb.disabled, opacity: label ? label.style.opacity : ''};
            """,
            checkbox_selector,
        )

    def save_profile_button_count(self) -> int:
        return len(self.css_all(selectors.SAVE_PROFILE_BTN))

    def save_profile_button_immediately_after_submit(self) -> bool:
        """True, если инжектированная кнопка Save filter — `nextElementSibling`
        submit-кнопки формы (`ao3_bridge.js::injectSaveFilterButton`,
        `submitBtn.parentNode.insertBefore(btn, submitBtn.nextSibling)`)."""
        return bool(self.driver.execute_script(
            """
            var submitBtn = document.querySelector(
                '#work-filters input[name="commit"][type="submit"]'
            );
            if (!submitBtn) return false;
            var next = submitBtn.nextElementSibling;
            return !!next && next.hasAttribute('data-ao3-save-profile');
            """
        ))

    def toggle_form_class(self) -> None:
        """Мутирует `class` `#work-filters` — тот же наблюдаемый триггер
        `MutationObserver({attributeFilter: ['style', 'class']})`
        (`ao3_bridge.js` стр.1076-1084), что реальный AO3 toggle-JS (не
        воспроизведённый в replay-записи, см. модульный докстринг): раскрытие/
        скрытие секции формы AO3 переключает именно class/style `#work-filters`."""
        self.driver.execute_script(
            """
            var form = document.getElementById('work-filters');
            if (form) { form.classList.toggle('ao3-test-form-toggle'); }
            """
        )
