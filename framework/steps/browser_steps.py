"""Бизнес-шаги содержимого WebView, не привязанные к конкретному нативному экрану."""
from __future__ import annotations

import allure

from framework.core import contexts
from framework.core.waits import wait_until
from framework.screens.browser_screen import BrowserScreen
from framework.web.downloaded_work_page import DownloadedWorkPage
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
