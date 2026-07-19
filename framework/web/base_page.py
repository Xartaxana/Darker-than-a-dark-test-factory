"""Базовый Page Object для DOM внутри WebView. Работает только когда драйвер уже
в WEBVIEW-контексте (об этом заботится вызывающий шаг через core.contexts).
"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from framework.core.waits import wait_until


class BasePage:
    def __init__(self, driver):
        self.driver = driver

    def css(self, selector: str):
        return self.driver.find_element(AppiumBy.CSS_SELECTOR, selector)

    def css_all(self, selector: str):
        return self.driver.find_elements(AppiumBy.CSS_SELECTOR, selector)

    def exists(self, selector: str) -> bool:
        return len(self.css_all(selector)) > 0

    def wait_css(self, selector: str, timeout: int | None = None):
        return wait_until(
            self.driver,
            lambda d: (els := d.find_elements(AppiumBy.CSS_SELECTOR, selector)) and els[0],
            timeout=timeout, message=f"не найден DOM-элемент: {selector}",
        )

    def bridge_marker_present(self) -> bool:
        """Наблюдаемый факт того, что `ao3_bridge.js` выполнился на текущей
        странице (`window.__ao3Bridge === true`, guard стр.5-6 ao3_bridge.js) —
        JS-глобал, не элемент DOM-дерева, поэтому читается через execute_script,
        не через css-локатор (TC-066/067)."""
        return bool(self.driver.execute_script("return window.__ao3Bridge === true;"))
