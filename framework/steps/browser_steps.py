"""Бизнес-шаги содержимого WebView, не привязанные к конкретному нативному экрану."""
from __future__ import annotations

import allure
from appium.webdriver.common.appiumby import AppiumBy

from framework.config import settings
from framework.core import contexts
from framework.core.waits import wait_until
from framework.screens.browser_screen import BrowserScreen
from framework.web import selectors
from framework.web.downloaded_work_page import DownloadedWorkPage
from framework.web.listing_page import ListingPage
from framework.web.reader_page import ReaderPage


@allure.step("Then измерена высота заголовка страницы AO3 в WebView")
def measure_heading_height(driver) -> float:
    with contexts.in_webview(driver):
        return ReaderPage(driver).heading_height()


@allure.step("When выполнен двухпальцевый spread над страницей (увеличение шрифта жестом)")
def pinch_spread(driver):
    BrowserScreen(driver).pinch_spread()


@allure.step("When выполнен двухпальцевый pinch над страницей (уменьшение шрифта жестом)")
def pinch_close(driver):
    BrowserScreen(driver).pinch_close()


@allure.step("When выполнен двухпальцевый параллельный драг вниз над страницей (снижение яркости)")
def drag_brightness_down(driver, dy_total_px: int = 2000):
    BrowserScreen(driver).drag_brightness_down(dy_total_px)


@allure.step("When выполнен двухпальцевый параллельный драг вверх над страницей (повышение яркости)")
def drag_brightness_up(driver, dy_total_px: int = 2000):
    BrowserScreen(driver).drag_brightness_up(dy_total_px)


@allure.step("Then измерена средняя яркость (luma) полноэкранного скриншота")
def measure_screen_luma(driver) -> float:
    return BrowserScreen(driver).screenshot_avg_luma()


@allure.step("When лишние вкладки WebView закрыты (оставлена только активная)")
def close_other_tabs(driver):
    BrowserScreen(driver).close_leftmost_tab()


@allure.step("Then файл открыт локально (file:// или content://) на активной вкладке Browse")
def assert_local_file_opened(driver):
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: (d.current_url or "").startswith(("file://", "content://")),
            message="файл не открылся через file:///content:// URL",
        )


@allure.step("Then в загруженном DOM инжектированы мобильный viewport и reader.css")
def assert_downloaded_page_styled(driver):
    with contexts.in_webview(driver):
        page = DownloadedWorkPage(driver)
        page.wait_viewport_meta()
        page.wait_reader_css()


@allure.step("When открыта листинговая страница (replay-фикстура) {url}")
def open_listing(driver, url: str):
    """Навигация WebView на URL листинга AO3 (replay-запись — см. `conftest.replay`,
    `framework/data/recording_builder.py`). Ждёт появления хотя бы одного блёрба
    работы — сигнал, что bridge (`ao3_bridge.js`) уже прошёлся по DOM и вставил
    Rate-кнопки (`onWorksFound` → `applyRatings`), а не просто что страница ответила
    200."""
    with contexts.in_webview(driver):
        driver.get(url)
        wait_until(
            driver,
            lambda d: len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)) > 0,
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="листинговая replay-страница не загрузилась (нет блёрбов работ)",
        )


@allure.step("Then блёрб работы {work_id} скрыт фильтрацией на листинге")
def assert_blurb_hidden(driver, work_id: str):
    """Опрашивает `display:none` блёрба, а не читает его один раз: скрытие — следствие
    нативного round-trip (`applyRatings` -> `applyAllFilters` в `ao3_bridge.js`),
    который может ещё не завершиться к моменту первого чтения DOM — одноразовая
    проверка была бы гонкой, проходящей на латентности переключения в WEBVIEW, а не
    на факте синхронизации (см. AT-BUG-004, приёмка critic)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).is_hidden(work_id),
            message=f"работа {work_id} должна быть скрыта фильтрацией (applyAllFilters), но видна",
        )


@allure.step("Then блёрб работы {work_id} виден на листинге")
def assert_blurb_visible(driver, work_id: str):
    """См. `assert_blurb_hidden` — тот же опрос вместо одноразового чтения."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: not ListingPage(d).is_hidden(work_id),
            message=f"работа {work_id} должна быть видна, но скрыта фильтрацией",
        )
