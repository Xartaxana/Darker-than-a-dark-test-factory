"""Базовый Screen Object. Локаторная дисциплина: элементы ищутся хелперами отсюда,
в наследниках объявляются локаторы (один локатор — одно место). Без assert'ов и без
знания о сценариях — это делают слои steps/tests.
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC

from framework.core import contexts
from framework.core.waits import wait_until


class BaseScreen:
    def __init__(self, driver):
        self.driver = driver
        contexts.to_native(driver)

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

    def swipe_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами, пока не покажется текст. Устойчиво к Compose,
        где UiScrollable не всегда распознаёт скроллируемый контейнер."""
        loc = self.by_text(text)
        if self.is_present(loc, timeout=2):
            return True
        size = self.driver.get_window_size()
        x = size["width"] // 2
        y1, y2 = int(size["height"] * 0.8), int(size["height"] * 0.25)
        for _ in range(max_swipes):
            self.driver.swipe(x, y1, x, y2, 400)
            if self.is_present(loc, timeout=1):
                return True
        return False

    def swipe_up_to_text(self, text: str, max_swipes: int = 8) -> bool:
        """Прокручивает экран свайпами в ОБРАТНОМ направлении к `swipe_to_text` —
        нужно, когда искомый текст находится ВЫШЕ текущей позиции скролла (например,
        после подтверждения диалога, который сам не сбрасывает скролл, нужно
        вернуться к разделу, расположенному выше того, где сейчас находимся —
        см. TC-021, `framework/steps/saf_steps.py::open_settings_scrolled_to`)."""
        loc = self.by_text(text)
        if self.is_present(loc, timeout=2):
            return True
        size = self.driver.get_window_size()
        x = size["width"] // 2
        y1, y2 = int(size["height"] * 0.25), int(size["height"] * 0.8)
        for _ in range(max_swipes):
            self.driver.swipe(x, y1, x, y2, 400)
            if self.is_present(loc, timeout=1):
                return True
        return False
