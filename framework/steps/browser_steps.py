"""Бизнес-шаги содержимого WebView, не привязанные к конкретному нативному экрану."""
from __future__ import annotations

import allure
from appium.webdriver.common.appiumby import AppiumBy

from framework.config import settings
from framework.core import contexts
from framework.core.waits import wait_until
from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav
from framework.web import selectors
from framework.web.downloaded_work_page import DownloadedWorkPage
from framework.web.listing_page import ListingPage
from framework.web.reader_page import ReaderPage

HOME_URL = "https://archiveofourown.org"


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


@allure.step("Then измерена средняя яркость (luma) области WebView")
def measure_webview_luma(driver) -> float:
    return BrowserScreen(driver).webview_avg_luma()


@allure.step("Then содержимое WebView заметно потемнело относительно baseline")
def assert_webview_darkened(driver, baseline: float, ratio: float = 0.7, timeout: int = 20):
    """Опрашивает luma области WebView, пока страница не перерисуется тёмной — смена
    темы триггерит программный `reload()` (BrowserScreen.kt LaunchedEffect(darkTheme)),
    поэтому одноразовое чтение сразу после переключения было бы гонкой с перерисовкой
    (см. TC-048 заметки)."""
    def _darker(d):
        luma = BrowserScreen(d).webview_avg_luma()
        return luma < baseline * ratio
    wait_until(
        driver, _darker, timeout=timeout,
        message=f"WebView не потемнел относительно baseline={baseline:.1f} за {timeout}с",
    )


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


@allure.step("Then активная вкладка загрузила {url}")
def assert_active_tab_url(driver, url: str = HOME_URL, timeout: int | None = None):
    """Опрашивает `current_url`, а не читает его один раз: `onNavigateHome`
    (MainActivity.kt) пишет `pendingNavigationUrl` в `BrowserViewModel.uiState`
    асинхронно, применяется отдельным `LaunchedEffect` в `BrowserScreen.kt`
    (~212-218) через `webViews[activeId]?.loadUrl(url)` — одноразовое чтение сразу
    после действия было бы гонкой (тот же класс, что устранён в
    `assert_blurb_hidden`, см. AT-BUG-004). Сравнение без хвостового «/» — WebView
    может нормализовать корневой URL добавлением слэша."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: (d.current_url or "").rstrip("/") == url.rstrip("/"),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"URL активной вкладки не стал {url}",
        )


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


@allure.step("When нажата Rate-кнопка работы {work_id} на листинге")
def tap_rate_button(driver, work_id: str):
    """Клик по инжектированной bridge Rate-кнопке (`ao3_bridge.js::makeRateButton`) —
    обработчик клика добавлен синхронно при её создании (в момент первого прохода
    bridge по `li[id^="work_"]`, уже пройденного к моменту, когда `open_listing`
    дождался блёрбов), доп. ожидание готовности хендлера не нужно. Клик открывает
    нативный `RatingOverlay` (bottom-sheet) поверх WebView — ожидание его появления
    делает вызывающий шаг (`rating_steps.rate_via_listing_overlay`), не этот."""
    with contexts.in_webview(driver):
        ListingPage(driver).rate_button(work_id).click()


@allure.step("Then на карточке работы {work_id} на листинге появился бейдж рейтинга")
def assert_rating_badge_visible(driver, work_id: str):
    """Опрашивает появление `[data-ao3-badge]` в блёрбе, а не читает один раз: бейдж —
    следствие нативного round-trip (`applyRating` -> `broadcastRatingChange` ->
    `window.applyRatings` в `BrowserViewModel.kt`), выполняемого через фоновый
    `evalJs` на WebView-вкладке — одноразовая проверка сразу после выбора рейтинга
    была бы гонкой (тот же класс, что и `assert_blurb_hidden`, см. AT-BUG-004)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).badge_for(work_id),
            message=f"бейдж рейтинга работы {work_id} не появился на листинге после простановки",
        )


# --- Filter panel (BottomBar.kt FilterPanel, TC-041/TC-042) ---

@allure.step("When раскрыта выпадашка «AO3 filter:» на листинге")
def open_filter_dropdown(driver):
    """Панель — часть секции, скрытой за нижней pill-ручкой на вкладке BROWSE
    (см. `framework/screens/navigation.py`) — раскрытие ручки нужно ПЕРЕД тапом
    по триггеру, отдельно от `BrowserScreen.open_filter_dropdown` (та знает
    только про сам триггер, композиция с BottomNav — здесь, в steps)."""
    BottomNav(driver).ensure_visible()
    BrowserScreen(driver).open_filter_dropdown()


@allure.step("Then в выпадашке фильтра предложен профиль «{name}»")
def assert_filter_offered(driver, name: str):
    assert BrowserScreen(driver).filter_dropdown_has_option(name), (
        f"профиль «{name}» не предложен в выпадашке фильтра на листинге"
    )


@allure.step("Then в выпадашке фильтра профиль «{name}» НЕ предложен")
def assert_filter_not_offered(driver, name: str, timeout: int = 3):
    assert not BrowserScreen(driver).filter_dropdown_has_option(name, timeout=timeout), (
        f"профиль «{name}» всё ещё предложен в выпадашке фильтра — ожидали удалённым"
    )
