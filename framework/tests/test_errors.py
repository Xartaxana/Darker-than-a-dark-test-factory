"""Тесты области errors (test-cases/errors/): кастомная themed error page,
показываемая приложением вместо дефолтной страницы ошибки WebView/Chrome при
`onReceivedError` главного фрейма (app-under-test `BrowserScreen.kt`
`WebViewClient.onReceivedError`/`onPageFinished`/`buildErrorHtml`, TC-046).
"""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps, browser_steps


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-046")
@allure.title("Ошибка загрузки главного фрейма показывает кастомную error page с Retry")
def test_main_frame_load_error_shows_custom_error_page_with_retry(clean_app, driver):
    # Given активная вкладка догрузила живой AO3 (без «зависшей» навигации в фоне —
    # иначе последующий driver.get() ниже прервал бы ЕЁ, и onReceivedError сработал бы
    # для случайно прерванного старого URL, а не для целевого недоступного)
    app_steps.wait_app_ready(driver)

    # When активная вкладка пытается загрузить URL, недоступный по сети (main-frame
    # запрос завершается ERR_NAME_NOT_RESOLVED — `.test` TLD никогда не резолвится,
    # см. UNREACHABLE_URL) — WebView получает onReceivedError для главного фрейма
    browser_steps.open_unreachable_url(driver)

    # Then отображается кастомная themed error page приложения (не дефолтная страница
    # ошибки Chrome/WebView) с текстом об ошибке, и на ней есть Retry-ссылка на
    # исходный (упавший) URL
    browser_steps.assert_error_page_shown(driver)

    # When нажат Retry
    browser_steps.click_retry(driver)

    # Then нажатие Retry инициирует повторную загрузку ТОГО ЖЕ URL (снова падает тем
    # же образом — снова показана кастомная error page с Retry-ссылкой на тот же
    # исходный URL, а не переход на другой адрес)
    browser_steps.assert_error_page_shown(driver)
