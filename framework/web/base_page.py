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

    # TC-149: вычисленный WCAG-контраст ОДНОГО DOM-узла — относительная
    # яркость по формуле W3C (sRGB -> linear -> luminance), эффективный фон
    # ищется подъёмом по `parentElement` до первого предка с непрозрачным
    # (`alpha > 0`) вычисленным `background-color` (WebView не композитит
    # частичную альфу за нас — этого достаточно для реальных страниц/фикстур
    # этого кейса, где фон в итоге упирается в непрозрачную заливку body/li).
    # «Крупный текст» классифицируется по ТЕКУЩЕМУ отрендеренному
    # `font-size`/`font-weight` (не номинальному CSS-размеру фикстуры) — см.
    # TC-149.md «Заметки для автоматизации» про `fontSizeStep`.
    _CONTRAST_OF_ELEMENT_JS = """
        function parseColor(str) {
            if (!str) return null;
            var m = str.match(/rgba?\\(([^)]+)\\)/);
            if (!m) return null;
            var parts = m[1].split(',').map(function (s) { return parseFloat(s); });
            return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
        }
        function channelLum(c) {
            var s = c / 255;
            return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        }
        function relLuminance(rgb) {
            return 0.2126 * channelLum(rgb.r) + 0.7152 * channelLum(rgb.g) + 0.0722 * channelLum(rgb.b);
        }
        function effectiveBackground(node) {
            while (node) {
                var bg = parseColor(window.getComputedStyle(node).backgroundColor);
                if (bg && bg.a > 0) return bg;
                node = node.parentElement;
            }
            return {r: 255, g: 255, b: 255, a: 1};
        }
        var el = document.querySelector(arguments[0]);
        if (!el) {
            throw new Error('contrast_of: querySelector не нашёл узел для селектора: ' + arguments[0]);
        }
        var cs = window.getComputedStyle(el);
        var fg = parseColor(cs.color);
        var bg = effectiveBackground(el);
        var l1 = relLuminance(fg);
        var l2 = relLuminance(bg);
        var lighter = Math.max(l1, l2), darker = Math.min(l1, l2);
        var ratio = (lighter + 0.05) / (darker + 0.05);
        var fontSizePx = parseFloat(cs.fontSize);
        var weightNum = parseInt(cs.fontWeight, 10);
        var bold = cs.fontWeight === 'bold' || (!isNaN(weightNum) && weightNum >= 700);
        var isLarge = fontSizePx >= 24 || (bold && fontSizePx >= 18.66);
        return {
            color: cs.color,
            background: cs.backgroundColor,
            effectiveBackground: 'rgba(' + bg.r + ', ' + bg.g + ', ' + bg.b + ', ' + bg.a + ')',
            ratio: ratio,
            fontSizePx: fontSizePx,
            fontWeight: cs.fontWeight,
            bold: bold,
            isLarge: isLarge,
            threshold: isLarge ? 3.0 : 4.5,
        };
    """

    def contrast_of(self, selector: str) -> dict:
        """Вычисленный WCAG-контраст-ratio узла, адресуемого CSS-селектором
        `selector`, против эффективного фона (см. докстринг выше) +
        классификация «крупный текст»/порог. Узел резолвится ВНУТРИ
        инжектированного скрипта через `document.querySelector(selector)` —
        `selector` (строка-локатор, живёт у вызывающего page object) уходит
        через границу Appium/chromedriver как примитив, а не как сериализованная
        W3C-ссылка на `WebElement` (`arguments[0]` = WebElement): на
        chromedriver=74.0.3729.6 (стек 2, api29) такая ссылка резолвилась
        некорректно внутри инжектированного скрипта — `getComputedStyle`
        получал НЕ `Element` (`TypeError: parameter 1 is not of type
        'Element'`, `bugs/AT-BUG-096.md`). Передача строки работает
        одинаково на chromedriver 74 И на текущем chromedriver стека 1
        (api34) — не версионная развилка."""
        return self.driver.execute_script(self._CONTRAST_OF_ELEMENT_JS, selector)
