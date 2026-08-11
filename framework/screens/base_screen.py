"""Базовый Screen Object. Локаторная дисциплина: элементы ищутся хелперами отсюда,
в наследниках объявляются локаторы (один локатор — одно место). Без assert'ов и без
знания о сценариях — это делают слои steps/tests.
"""
from __future__ import annotations

import allure
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC

from framework.core import contexts
from framework.core.waits import poll_for, wait_until

# --- Тюнинг свайп-поиска (AT-BUG-048) ---
# Один длинный быстрый свайп (55% высоты за 400мс) — это fling: Android/Compose
# продолжает ехать по инерции ПОСЛЕ возврата вызова driver.swipe. Вместо него
# та же ПОЛНАЯ дистанция раунда разбита на несколько КОРОТКИХ подряд идущих
# свайпов меньшей скорости (ниже порога fling — список останавливается сразу по
# отпускании, без инерции, а итоговая landing-позиция раунда не меняется). После
# ЗАВЕРШЕНИЯ полного раунда опрашивается всё settle-окно (`poll_for`), а не один
# снимок сразу после возврата — это и есть исправление самой сути дефекта
# (редкий одиночный опрос под нагрузкой мог не застать искомый текст).
SWIPE_MICRO_STEPS = 3
SWIPE_MICRO_DURATION_MS = 300
SWIPE_SETTLE_TIMEOUT_S = 1.2
SWIPE_SETTLE_POLL_INTERVAL_S = 0.3


class BaseScreen:
    def __init__(self, driver):
        self.driver = driver
        contexts.to_native(driver)
        # Диагностика последнего неуспешного swipe_to_text/swipe_up_to_text
        # (AT-BUG-048) — различает «строки нет в списке» от «прокрутка
        # дошла до конца, строка не поймана»; пусто, пока не было неуспеха.
        self.last_swipe_diagnostic = ""

    # --- Локаторы: предпочтение content-desc > text > доступный XPath ---
    def by_desc(self, desc: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().description("{desc}")')

    def by_text(self, text: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().text("{text}")')

    def by_text_contains(self, text: str):
        return (AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{text}")')

    # --- Общие операции ---
    def find(self, locator, timeout: int | None = None):
        return wait_until(self.driver, EC.presence_of_element_located(locator),
                          timeout=timeout, message=f"не найден элемент: {locator}")

    def tap(self, locator, timeout: int | None = None):
        el = wait_until(self.driver, EC.element_to_be_clickable(locator),
                        timeout=timeout, message=f"не кликабелен: {locator}")
        el.click()
        return el

    def is_present(self, locator, timeout: int = 5) -> bool:
        try:
            wait_until(self.driver, EC.presence_of_element_located(locator), timeout=timeout)
            return True
        except Exception:  # noqa: BLE001
            return False

    def wait_absent(self, locator, timeout: int | None = None) -> None:
        """Опрашивает ОТСУТСТВИЕ локатора — дожидается, пока ни один узел ему не
        соответствует (например, полное исчезновение snackbar с экрана). Симметрично
        `is_present`, но поднимает при неуспехе, а не возвращает bool: вызывающему
        коду (TC-176) нужно именно дождаться, не просто узнать текущее состояние."""
        wait_until(
            self.driver,
            lambda d: len(d.find_elements(*locator)) == 0,
            timeout=timeout,
            message=f"элемент не исчез с экрана: {locator}",
        )

    def is_enabled(self, locator, timeout: int = 5) -> bool:
        """Читает accessibility-атрибут `enabled` найденного элемента (не требует
        видимости/кликабельности — сам факт enabled=false и есть проверяемое состояние)."""
        return self.find(locator, timeout).get_attribute("enabled") == "true"

    def is_clickable_attr(self, locator, timeout: int = 5) -> bool:
        """Читает accessibility-атрибут `clickable` найденного узла БЕЗ клика (в
        отличие от `tap()`/`element_to_be_clickable`, который клика дожидается И
        выполняет) — TC-107: доказать «контрол кликабелен» без побочного эффекта
        реального нажатия (например, изменения выбранной темы/размера шрифта)."""
        return self.find(locator, timeout).get_attribute("clickable") == "true"

    def text_of(self, locator, timeout: int | None = None) -> str:
        return self.find(locator, timeout).text

    def label_of(self, locator, timeout: int | None = None) -> tuple[str, str]:
        """Возвращает `(content-desc, text)` найденного узла — чтение атрибутов
        accessibility-дерева без взаимодействия (TC-106: инспекция «непустой
        content-desc ИЛИ видимый text» на уже отрисованных контролах)."""
        el = self.find(locator, timeout)
        desc = el.get_attribute("contentDescription") or ""
        text = el.get_attribute("text") or el.text or ""
        return desc, text

    def _probe_present(self, locator) -> bool:
        """Немедленная проверка присутствия БЕЗ ожидания — прямой
        `find_elements`, а не `is_present`/`wait_until` (поллинг поверх
        поллинга исказил бы бюджет settle-окна `_swipe_search`)."""
        return len(self.driver.find_elements(*locator)) > 0

    def _scroll_fingerprint(self) -> tuple:
        """Дешёвый отпечаток текущей прокрученной позиции — набор видимых
        непустых текстов. Не изменился после свайпа => список уткнулся в
        конец (AT-BUG-048: различает «строки нет в списке» от «прокрутка
        дошла до конца, строка не поймана»)."""
        els = self.driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches(".+")')
        return tuple(sorted((e.get_attribute("text") or "") for e in els))

    def _swipe_search(self, text: str, max_swipes: int, y1_frac: float, y2_frac: float) -> tuple[bool, str]:
        """Общая реализация `swipe_to_text`/`swipe_up_to_text` (AT-BUG-048).
        Возвращает `(found, diagnostic)` — `diagnostic` пуст при `found=True`."""
        loc = self.by_text(text)
        if self.is_present(loc, timeout=2):
            return True, ""
        size = self.driver.get_window_size()
        x = size["width"] // 2
        y1 = int(size["height"] * y1_frac)
        y2 = int(size["height"] * y2_frac)
        step_ys = [y1 + (y2 - y1) * i // SWIPE_MICRO_STEPS for i in range(SWIPE_MICRO_STEPS + 1)]
        fingerprint = self._scroll_fingerprint()
        for _ in range(max_swipes):
            # Полная дистанция раунда (y1->y2, как в исходном одиночном свайпе)
            # ВСЕГДА проходится целиком, короткими не-fling шагами — landing-
            # позиция после раунда остаётся той же, что и раньше (соседние
            # элементы вроде кнопки «Clear…» рядом с «Clear all ratings»
            # оказываются в кадре так же, как при одном большом свайпе); проверка
            # присутствия — ПОСЛЕ раунда, но settle-окном из нескольких опросов
            # (не один снимок сразу после возврата, AT-BUG-048).
            for i in range(SWIPE_MICRO_STEPS):
                self.driver.swipe(x, step_ys[i], x, step_ys[i + 1], SWIPE_MICRO_DURATION_MS)
            if poll_for(lambda: self._probe_present(loc),
                       timeout=SWIPE_SETTLE_TIMEOUT_S, interval=SWIPE_SETTLE_POLL_INTERVAL_S):
                return True, ""
            new_fingerprint = self._scroll_fingerprint()
            if new_fingerprint == fingerprint:
                return False, (
                    f"«{text}»: КОНЕЦ СПИСКА (позиция не изменилась после "
                    f"свайпа) — строка не поймана, список исчерпан"
                )
            fingerprint = new_fingerprint
        return False, f"«{text}»: НЕ НАЙДЕНА в списке за {max_swipes} свайпов (список ещё двигался, конец не достигнут)"

    def swipe_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами, пока не покажется текст. Устойчиво к Compose,
        где UiScrollable не всегда распознаёт скроллируемый контейнер.

        AT-BUG-048: короткие контролируемые свайпы (не fling) + поллинг всего
        settle-окна после каждого — искомый текст больше не проскакивает
        вьюпорт незамеченным между редкими опросами. Неуспех логируется
        диагностикой, различающей «список исчерпан» от «список ещё двигался»
        (`self.last_swipe_diagnostic`) — сигнатура метода (bool) не меняется,
        чтобы все 10 существующих call site получили фикс бесплатно."""
        found, diagnostic = self._swipe_search(text, max_swipes, y1_frac=0.8, y2_frac=0.25)
        self.last_swipe_diagnostic = diagnostic
        if not found:
            self._attach_swipe_diagnostic(diagnostic)
        return found

    def swipe_up_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами в ОБРАТНОМ направлении к `swipe_to_text` —
        нужно, когда искомый текст находится ВЫШЕ текущей позиции скролла (например,
        после подтверждения диалога, который сам не сбрасывает скролл, нужно
        вернуться к разделу, расположенному выше того, где сейчас находимся —
        см. TC-021, `framework/steps/saf_steps.py::open_settings_scrolled_to`).

        AT-BUG-048: та же fling-устойчивая реализация, что `swipe_to_text`
        (симметрично, `_swipe_search`)."""
        found, diagnostic = self._swipe_search(text, max_swipes, y1_frac=0.25, y2_frac=0.8)
        self.last_swipe_diagnostic = diagnostic
        if not found:
            self._attach_swipe_diagnostic(diagnostic)
        return found

    def _attach_swipe_diagnostic(self, diagnostic: str) -> None:
        """Прикладывает диагностику неуспешного swipe-поиска к Allure — иначе
        вызывающий `assert self.swipe_to_text(...), "статичное сообщение"`
        схлопывает «конец списка» и «строки нет» в одинаковый на вид провал
        (AT-BUG-048). Best-effort: недоступность Allure-раннера не должна
        рушить сам тест."""
        try:
            allure.attach(diagnostic, name="swipe_to_text diagnostic",
                          attachment_type=allure.attachment_type.TEXT)
        except Exception:  # noqa: BLE001
            pass

    def _attach_pre_fallback_snapshot(self, text: str) -> None:
        """AT-BUG-062, класс (не экземпляр): любой вызывающий, использующий приём
        `swipe_to_text(...) or swipe_up_to_text(...)`, теряет ПОЗИЦИЮ ОТКАЗА —
        фолбэк `swipe_up_to_text` всегда возвращает список НАВЕРХ, поэтому
        `page_source`, снятый пайплайном при итоговом провале теста
        (`framework/core/reporting.py::attach_failure_artifacts`, teardown),
        фиксирует экран УЖЕ ПОСЛЕ этого возврата, а не позицию, где прямой
        проход не поймал `text`. Снимок ЗДЕСЬ, ДО фолбэка — единственный
        источник, различающий «текста там нет» от «прокрутка проскочила
        строку» (AT-BUG-048). Best-effort, симметрично `_attach_swipe_diagnostic`.
        Изначально жил только в `SettingsScreen` (`_swipe_to_profile`) — поднят
        в `BaseScreen`, т.к. тот же паттерн `swipe_to_text(...) or
        swipe_up_to_text(...)` есть и в `framework/steps/saf_steps.py::
        _scroll_settings_to` (сиблинг, доклад AT-BUG-062 test-maintainer)."""
        try:
            allure.attach(
                self.driver.page_source,
                name=f"page_source pre-fallback (после неуспешного swipe_to_text «{text}»)",
                attachment_type=allure.attachment_type.XML,
            )
        except Exception:  # noqa: BLE001
            pass
