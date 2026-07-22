"""TC-102 (security): JS-bridge (`window.Android`) exposure — baseline на
доверенном AO3-origin vs проба на локальной error-странице (не-AO3-контент).

Переиспользует `browser_steps.open_unreachable_url`/`assert_error_page_shown`
(тот же механизм не-AO3-состояния, что TC-046) — не изобретает новый способ
попасть на не-AO3-контент. `window.Android` — нативный `@JavascriptInterface`
(`addJavascriptInterface(bridge, "Android")`, BrowserScreen.kt) — НЕ то же
самое, что `ao3_bridge.js` (JS-файл, инжектируемый только на AO3-страницах);
testability gap и обоснование см. TC-102.md «Заметки для автоматизации»."""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps, browser_steps, security_steps


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-102")
@allure.title("JS-bridge (window.Android) доступность: baseline на AO3-origin vs проба на локальной error-странице")
def test_js_bridge_exposure_baseline_vs_non_ao3_error_page(clean_app, driver):
    # Given активная вкладка отображает доверенный AO3-origin контент (HOME_URL)
    app_steps.wait_app_ready(driver)

    # When в контексте WebView этой вкладки выполняется JS-проба `typeof
    # window.Android` — снимается baseline на доверенном origin
    # Then window.Android доступен (штатная функциональная интеграция, не сам
    # предмет риска — это baseline)
    security_steps.assert_js_bridge_available(driver)

    # And та же вкладка переводится на заведомо недоступный URL (тот же приём,
    # что TC-046) — показывается кастомная error-страница приложения (не-AO3-
    # контент, about:blank base URL)
    browser_steps.open_unreachable_url(driver)
    browser_steps.assert_error_page_shown(driver)

    # Then фактическая доступность window.Android на локальной error-странице
    # зафиксирована как наблюдаемый факт — нативный @JavascriptInterface по
    # семантике Android не скоупится по origin сам по себе; кейс документирует
    # факт, не выносит вердикт «уязвимость»/«не уязвимость» (E4-min, §8)
    security_steps.record_js_bridge_observation(driver, "локальная error-страница (не-AO3-контент)")
