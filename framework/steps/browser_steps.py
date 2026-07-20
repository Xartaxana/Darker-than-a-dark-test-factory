"""Бизнес-шаги содержимого WebView, не привязанные к конкретному нативному экрану."""
from __future__ import annotations

import time
import uuid

import allure
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)

from framework.config import settings
from framework.core import contexts
from framework.core.waits import wait_until
from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav
from framework.web import selectors
from framework.web.downloaded_work_page import DownloadedWorkPage
from framework.web.error_page import ErrorPage
from framework.web.listing_page import ListingPage
from framework.web.reader_page import ReaderPage
from framework.web.sort_filter_form_page import SortFilterFormPage

HOME_URL = "https://archiveofourown.org"
# Статическая информационная страница AO3 — см. `open_stable_tall_page` docstring
# (AT-BUG-015) за обоснованием выбора именно этого URL.
STABLE_TALL_LIVE_URL = f"{HOME_URL}/tos"
# Реальный листинг «последних обновлённых» работ AO3 (дефолтная сортировка
# revised_at) — используется canary-кейсами контракта селекторов (TC-068/070),
# которым нужна ЖИВАЯ листинговая страница с ≥1 work-блёрбом, но не важен
# конкретный состав/количество работ (в отличие от `open_stable_tall_page`,
# см. AT-BUG-015 п.2 про time-sensitive контент этого же URL).
LIVE_LISTING_URL = f"{HOME_URL}/works"
# `.test` — зарезервированный RFC 2606 TLD, никогда не резолвится DNS'ом — гарантирует
# `ERR_NAME_NOT_RESOLVED` детерминированно, независимо от состояния живого AO3 (R-03) и
# без mitmproxy/офлайн-режима сети (TC-046, значение из «Проверяемые данные» кейса).
UNREACHABLE_URL = "https://nonexistent.invalid.test/"


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


@allure.step("Then содержимое WebView заметно посветлело относительно тёмного baseline")
def assert_webview_lightened(driver, dark_baseline: float, ratio: float = 0.7, timeout: int = 20):
    """Симметрично `assert_webview_darkened` — обратное направление Dark→Light
    (C4-ретрофит TC-048, 2026-07-18: инвариант кейса требует СИММЕТРИИ обоих
    направлений, до этого assert'а Dark→Light нигде не проверялся).
    `dark_baseline` — luma, измеренная В тёмной теме (низкое значение); ждём, пока
    после программного `reload()` в Light luma не поднимется заметно выше — то же
    отношение `ratio`, что и `assert_webview_darkened`, только в обратную сторону
    (порог — деление, а не умножение, симметрично «потемнению на 30%»)."""
    def _lighter(d):
        luma = BrowserScreen(d).webview_avg_luma()
        return luma > dark_baseline / ratio
    wait_until(
        driver, _lighter, timeout=timeout,
        message=f"WebView не посветлел относительно тёмного baseline={dark_baseline:.1f} за {timeout}с",
    )


@allure.step("When в WebView открыта статическая информационная страница AO3 (ToS)")
def open_stable_tall_page(driver) -> str:
    """Навигация WebView на `STABLE_TALL_LIVE_URL` (`{HOME_URL}/tos`) — используется
    сценариями, которым нужна ЖИВАЯ (без replay) страница AO3 с гарантированно
    большим И СТАБИЛЬНЫМ между загрузками контентом (высота выше `innerHeight`,
    содержимое не меняется между двумя загрузками в пределах одного прогона).

    Почему именно эта страница, а не листинг работ и не Browse root (AT-BUG-015,
    диагностика измерением на устройстве, 2026-07-18, три раунда):
    1. Browse root (`HOME_URL` без пути) короче экрана на использованном эмуляторе
       (`document.body.scrollHeight=427` < `window.innerHeight=798`) — `scrollTo`
       там легитимно клампится к 0, скроллить физически нечего (не флейк и не
       тайминг — повторный замер после 2с ожидания дал те же числа).
    2. `{HOME_URL}/works` (листинг «последних обновлённых» работ, дефолтная
       сортировка AO3 по `revised_at`) достаточно высок (`scrollHeight=11030`), НО
       переключение темы триггерит программный `reload()` WebView (см. `TC-048` —
       `BrowserScreen.kt LaunchedEffect(darkTheme)`), а сам листинг —
       time-sensitive: между двумя загрузками (~10с, время Settings round-trip)
       контент на реальном archiveofourown.org успевает измениться —
       `document.body.scrollHeight` реально вырос (11030 -> 12731), из-за чего
       пиксельный `scrollY` после `reload()` закономерно не совпал (899 -> 930).
       Честный артефакт волатильности ВЫБРАННОЙ страницы (живой листинг), не баг
       приложения и не флейк тестовой инфраструктуры.
    3. `{HOME_URL}/tos` — статическая информационная страница (условия
       использования), контент НЕ time-sensitive: `reload()` всё равно происходит
       (`document.body.scrollHeight` еле заметно вырос: 9768 -> 9769, разница
       <1px — сеть/шрифты, не смена контента), а `scrollY` после переключения
       темы совпал с точностью до <1px (899.8 -> 900.6, было бы 899.8 -> 899.8
       на идеально статичной странице). Подходящий Given для assert'а сохранности
       scroll-позиции."""
    with contexts.in_webview(driver):
        driver.get(STABLE_TALL_LIVE_URL)
        wait_until(
            driver,
            lambda d: (
                d.execute_script("return document.readyState;") == "complete"
                and d.execute_script("return document.body.scrollHeight;") > 2000
            ),
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="статическая страница AO3 (/tos) не загрузилась (readyState "
                    "не complete или контент короче ожидаемого)",
        )
        return driver.current_url


@allure.step("Then измерена текущая позиция прокрутки (window.scrollY) страницы AO3 в WebView")
def get_webview_scroll_y(driver) -> int:
    with contexts.in_webview(driver):
        return int(driver.execute_script("return window.scrollY;") or 0)


@allure.step("Then позиция скролла активной вкладки восстановлена (не с нуля)")
def assert_scroll_restored(driver, timeout: int = 15) -> int:
    """Опрашивает `window.scrollY`, не читает один раз: после Undo/рестарта вкладка
    получает СВЕЖИЙ WebView (`BrowserScreen.kt` LaunchedEffect создаёт новый объект
    для отсутствующего в `webViews` id), которому ещё нужно догрузиться и применить
    peek-based scroll-restore (`Ao3JsBridge.peekScrollRestore`) — одноразовое чтение
    сразу после переключения было бы гонкой (тот же класс, что и другие опросы в
    этом модуле, см. `assert_active_tab_url`)."""
    with contexts.in_webview(driver):
        return wait_until(
            driver,
            lambda d: (v := int(d.execute_script("return window.scrollY;") or 0)) > 0 and v,
            timeout=timeout,
            message="scrollY восстановленной вкладки остаётся 0 — позиция скролла не восстановилась",
        )


@allure.step("When страница AO3 в WebView прокручена на {pixels}px вниз")
def scroll_webview_to(driver, pixels: int) -> None:
    """`behavior: 'instant'` обязателен — многие страницы AO3 задают CSS
    `scroll-behavior: smooth`, из-за чего голый `window.scrollTo(x, y)` не
    прыгает мгновенно, а анимирует переход; немедленное чтение `scrollY` сразу
    после вызова тогда ловит 0/промежуточное значение. Тот же обход уже
    применяется в собственном bridge приложения
    (`app-under-test/.../assets/ao3_bridge.js`: `window.scrollBy({...,
    behavior: 'instant'})`), здесь — то же самое для `scrollTo`. После скролла
    опрашиваем позицию (страница может ещё довёрстываться/лениво грузить
    контент, сразу после `scrollTo` высота могла быть не финальной) — не
    одноразовое чтение сразу за скроллом."""
    with contexts.in_webview(driver):
        driver.execute_script(
            f"window.scrollTo({{top: {pixels}, left: 0, behavior: 'instant'}});"
        )
    wait_until(
        driver,
        lambda d: get_webview_scroll_y(d) > 0,
        timeout=5,
        message=f"страница AO3 не проскроллилась к {pixels}px (scrollY остаётся 0)",
    )


@allure.step("Then TabStrip виден вверху экрана (открыто >1 вкладки, не fullscreen)")
def assert_tab_strip_visible(driver, timeout: int | None = None):
    assert BrowserScreen(driver).is_tab_strip_visible(timeout=timeout), \
        "TabStrip должен быть виден (tabs>1, не в fullscreen)"


@allure.step("Then TabStrip скрыт (fullscreen активен)")
def assert_tab_strip_hidden(driver, timeout: int = 3):
    assert not BrowserScreen(driver).is_tab_strip_visible(timeout=timeout), \
        "TabStrip должен быть скрыт в режиме fullscreen"


@allure.step("Then измерена средняя яркость верхней полосы экрана (пиксельный прокси TabStrip, TC-058)")
def measure_top_chrome_luma(driver) -> float:
    return BrowserScreen(driver).top_chrome_avg_luma()


@allure.step("Then верхняя полоса экрана заметно темнее baseline (TabStrip/статус-бар скрыты — fullscreen)")
def assert_top_chrome_darkened(driver, baseline: float, ratio: float = 0.5, timeout: int = 10):
    """Опрашивает luma верхней полосы, пока она не пересечёт порог потемнения — вход
    в fullscreen (`WindowInsetsControllerCompat.hide(systemBars())`) триггерит
    анимированный reflow (hide systemBars + resize WebView), продолжающийся некоторое
    время после самого тапа (тот же класс гонки, что `assert_webview_darkened`).
    Раньше settle-буфер под этот reflow обеспечивался лишь ПОБОЧНО таймаутом
    `is_present("GOT IT", timeout=3)` в `_dismiss_fullscreen_system_hint` — при
    выходе из fullscreen подсказка не появляется, и наблюдаемая задержка была
    случайным следствием чужого хелпера, а не свойством этой проверки (ревью
    test-reviewer TC-058, 2026-07-18)."""
    def _darker(d):
        luma = BrowserScreen(d).top_chrome_avg_luma()
        return luma < baseline * ratio
    wait_until(
        driver, _darker, timeout=timeout,
        message=f"верхняя полоса не потемнела после входа в fullscreen относительно baseline={baseline:.1f} за {timeout}с",
    )


@allure.step("Then верхняя полоса экрана снова светлая, как до fullscreen (TabStrip восстановлен)")
def assert_top_chrome_restored(driver, baseline: float, ratio: float = 0.5, timeout: int = 10):
    """Симметрично `assert_top_chrome_darkened` — обратное направление (выход из
    fullscreen), тот же settle-поллинг вместо одноразового чтения (см. докстринг
    выше)."""
    def _restored(d):
        luma = BrowserScreen(d).top_chrome_avg_luma()
        return luma > baseline * ratio
    wait_until(
        driver, _restored, timeout=timeout,
        message=f"верхняя полоса не восстановилась после выхода из fullscreen относительно baseline={baseline:.1f} за {timeout}с",
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


@allure.step("Then вкладка {target_position} стала физически активной (scrollY-асимметрия нативного скролла, AT-BUG-022)")
def assert_tab_became_active_via_scroll(
    driver,
    target_position: int,
    scroll_baseline: int | None = None,
    distance_px: int = 1400,
    timeout: int | None = None,
) -> int:
    """Различает «switchTab(target_position) реально сделал вкладку активной»
    от «switchTab — no-op» БЕЗ сведения числа вкладок к одной (`swipe_close_tab`
    reduce-to-one) — тот приём структурно не может различить эти два состояния,
    когда цель — вкладка 0 (см. полный разбор конфаунда в `bugs/AT-BUG-022.md`).

    Механизм (эмпирически подтверждён на эмуляторе, живой прогон 2026-07-20,
    сценарий буквально TC-084: 3 вкладки, активна 2, тап по чипу 0):
    НАТИВНЫЕ жесты (тап/свайп) бьют по физически видимому View
    (`activeContainer`, см. докстринг `browser_screen.py:255-270`), НЕ подвержены
    sticky-прилипанию chromedriver к вкладке-0, тогда как WEBVIEW-контекст
    (`execute_script`/`get_webview_scroll_y`) ВСЕГДА читает именно вкладку-0.
    Поэтому нативный скролл ПОСЛЕ тапа детерминированно меняет `scrollY`
    вкладки 0, только если тап РЕАЛЬНО сделал её физически отображаемой:

    - контрольный прогон (активна вкладка 2, тап на 0 ЕЩЁ не сделан): свайп не
      меняет scrollY вкладки 0 (0 -> 0 — свайп бьёт по вкладке 2, не по 0);
    - после тапа на чип 0 + тот же свайп: scrollY вкладки 0 меняется (0 -> 720
      на контрольном прогоне) — свайп теперь бьёт именно по вкладке 0.

    ТОЛЬКО `target_position == 0` покрыт этой эмпирической проверкой — сама
    вкладка 0 является единственной, чей `scrollY` вообще читаем через
    WEBVIEW-контекст при >1 живых вкладках. Симметричный приём для
    `target_position != 0` (проверка, что scrollY вкладки 0 ПЕРЕСТАЁТ меняться
    после переключения на другую цель) технически аналогичен, но НЕ проверен
    отдельным живым прогоном в этой сессии — вызывающий код обязан подтвердить
    его эмпирически на своём сценарии, прежде чем полагаться на него.

    Возвращает измеренный scrollY вкладки 0 после свайпа."""
    if scroll_baseline is None:
        scroll_baseline = get_webview_scroll_y(driver)
    BrowserScreen(driver).swipe_scroll_active_tab_down(distance_px)
    if target_position == 0:
        return wait_until(
            driver,
            lambda d: (v := get_webview_scroll_y(d)) > scroll_baseline and v,
            timeout=timeout or 5,
            message=(
                f"после переключения на вкладку 0 нативный свайп не изменил её scrollY "
                f"(осталось {scroll_baseline}) — switchTab(0), похоже, НЕ сделал вкладку 0 "
                f"физически активной (no-op), см. bugs/AT-BUG-022.md"
            ),
        )
    raise NotImplementedError(
        f"assert_tab_became_active_via_scroll для target_position={target_position} "
        "(!= 0) не покрыт эмпирической проверкой AT-BUG-022 в этой сессии — не "
        "использовать без отдельного живого прогона, подтверждающего симметрию "
        "приёма для не-нулевой цели"
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


@allure.step("When в WebView открыт URL {url} (ждёт полной загрузки документа)")
def open_url_and_wait_ready(driver, url: str, timeout: int | None = None) -> None:
    """Навигация на произвольный URL без ожидания специфичного контента (блёрбов
    и т.п.) — годится и для живой домашней/произвольной страницы AO3 (TC-066), и
    для replay-фикстур без work-блёрбов (TC-067, `ao3_home_smoke.mitm`)."""
    with contexts.in_webview(driver):
        driver.get(url)
        wait_until(
            driver,
            lambda d: d.execute_script("return document.readyState;") == "complete",
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"страница {url} не завершила загрузку (readyState != complete)",
        )


@allure.step("Then в JS-контексте страницы присутствует маркер инъекции bridge (window.__ao3Bridge)")
def assert_bridge_marker_present(driver, timeout: int | None = None) -> None:
    """Опрашивает `window.__ao3Bridge`, не читает один раз: bridgeScript —
    отдельный `evaluateJavascript`-вызов, идущий ПОСЛЕДНИМ в цепочке нескольких
    таких вызовов внутри `onPageFinished` (BrowserScreen.kt ~594-613) — тот же
    класс гонки, что и другие JS-маркеры этого модуля (см. `assert_active_tab_url`);
    одноразовое чтение сразу после навигации могло бы поймать окно ДО выполнения
    bridgeScript (TC-066/067)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).bridge_marker_present(),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message="маркер window.__ao3Bridge не появился — bridge не инжектирован",
        )


@allure.step("Then каждый work-блёрб листинга имеет извлекаемый непустой числовой work id, их количество совпадает с количеством h4.heading")
def assert_blurb_selector_matches_headings(driver, min_count: int = 1) -> list[str]:
    """TC-068/069: доказывает, что `selectors.WORK_BLURB` не промахивается мимо
    части работ и не ловит посторонние `<li>` — сверка count(WORK_BLURB) ==
    count(h4.heading), плюс каждый извлечённый work id непустой и числовой (тот
    же способ извлечения, что `ao3_bridge.js::applyAllFilters`). Возвращает список
    work id — вызывающий тест (TC-069) сверяет его ТОЧНОЕ множество с эталонными
    данными фикстуры."""
    with contexts.in_webview(driver):
        page = ListingPage(driver)
        work_ids = page.blurb_work_ids()
        heading_count = page.heading_count()
    assert len(work_ids) >= min_count, (
        f"на листинге найдено {len(work_ids)} work-блёрбов, ожидали >= {min_count}"
    )
    for wid in work_ids:
        assert wid and wid.isdigit(), (
            f"work id {wid!r}, извлечённый из id блёрба, не непустой числовой"
        )
    assert len(work_ids) == heading_count, (
        f"количество work-блёрбов ({len(work_ids)}) не совпадает с количеством "
        f"h4.heading ({heading_count}) — селектор промахивается мимо части работ "
        f"или ловит посторонние <li>"
    )
    return work_ids


@allure.step("Then у каждого work-блёрба листинга ровно одна Rate-кнопка внутри одного btn-wrap, привязанная к своему work id, в состоянии «неоценено»")
def assert_every_blurb_has_unrated_rate_button(driver, timeout: int | None = None) -> list[str]:
    """TC-070/071: инвариант «у каждого work-блёрба есть ровно одна СОБСТВЕННАЯ
    Rate-кнопка, привязанная к ЕГО work id» — не пример на одной работе. Ждёт
    (не читает один раз), пока количество `[data-ao3-rate-btn]` не догонит
    количество блёрбов: initial-injection проход bridge (`ao3_bridge.js`
    стр.851-869) синхронный внутри своего IIFE, но независимая от него навигация
    WebView могла успеть отрисовать `li`-блёрбы (статический HTML AO3) чуть
    раньше, чем bridge вообще начал выполняться (тот же класс гонки, что и
    остальные опросы этого модуля)."""
    with contexts.in_webview(driver):
        page = ListingPage(driver)
        work_ids = page.blurb_work_ids()
        assert work_ids, "на листинге не найдено ни одного work-блёрба — нечего проверять"
        wait_until(
            driver,
            lambda d: len(ListingPage(d).css_all(selectors.RATE_BUTTON)) >= len(work_ids),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message="Rate-кнопки не инжектированы для всех work-блёрбов листинга",
        )
        for work_id in work_ids:
            state = page.rate_button_state(work_id)
            assert state["wrap_count"] == 1, (
                f"work {work_id}: ожидали ровно один [data-ao3-btn-wrap], нашли {state['wrap_count']}"
            )
            assert state["button_count"] == 1, (
                f"work {work_id}: ожидали ровно одну [data-ao3-rate-btn], нашли {state['button_count']}"
            )
            assert state["attr"] == work_id, (
                f"work {work_id}: атрибут data-ao3-rate-btn={state['attr']!r} не совпадает с work id блёрба"
            )
            assert state["bg"] in ("", "transparent", "rgba(0, 0, 0, 0)"), (
                f"work {work_id}: Rate-кнопка не в состоянии «неоценено» (bg={state['bg']!r})"
            )
    return work_ids


@allure.step("When открыта живая листинговая страница {url} (устойчиво к Cloudflare bot-check, R-03)")
def open_live_listing(driver, url: str, timeout: int | None = None) -> None:
    """Как `open_listing`, но для ЖИВОГО archiveofourown.org, подверженного
    Cloudflare bot-check (R-03): интерстишл-страница технически «загружается»
    (readyState complete, тот же hostname archiveofourown.org, см. заметки
    TC-066 про guard `ao3_bridge.js`), не содержит work-блёрбов и сама НЕ
    перенаправляет себя внутри WebView — заголовок остаётся «Just a moment...»
    произвольно долго (эмпирически проверено диагностикой при автоматизации
    TC-068/070: 15с ожидания на месте не дали self-redirect). Клиентский JS-
    челлендж всё же выполняется в фоне и оставляет clearance-cookie — ПОВТОРНАЯ
    навигация на ТОТ ЖЕ URL после короткой паузы типично проходит уже с реальным
    контентом (эмпирически: 1 повтор после ~4с хватило). Общий бюджет —
    `settings.WEBVIEW_LOAD_TIMEOUT`, разбитый на короткие попытки, а не одно
    длинное ожидание — иначе первая интерстишл-попытка съедает весь таймаут, не
    оставляя шанса на повторную навигацию. `open_listing` (replay-фикстуры) этому
    риску не подвержен — там нет реальной Cloudflare, повторные попытки не нужны."""
    total_timeout = timeout or settings.WEBVIEW_LOAD_TIMEOUT
    attempt_timeout = 8
    deadline = time.time() + total_timeout
    with contexts.in_webview(driver):
        last_exc: Exception | None = None
        while time.time() < deadline:
            driver.get(url)
            remaining = max(1, int(deadline - time.time()))
            try:
                wait_until(
                    driver,
                    lambda d: len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)) > 0,
                    timeout=min(attempt_timeout, remaining),
                    message="живая листинговая страница не отдала work-блёрбы за эту попытку",
                )
                return
            except TimeoutException as exc:
                last_exc = exc
        raise TimeoutException(
            f"живая листинговая страница {url} не отдала work-блёрбы за "
            f"{total_timeout}s несколькими попытками (устойчивый Cloudflare "
            f"bot-check, R-03)"
        ) from last_exc


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


@allure.step("Then блёрб работы {work_id} затемнён фильтрацией (dim-режим, opacity 0.3), но остаётся в разметке")
def assert_blurb_dimmed(driver, work_id: str):
    """TC-092/093: опрашивает `display`+`opacity` блёрба, а не читает один раз — тот же
    класс гонки нативного round-trip (`applyAllFilters`), что `assert_blurb_hidden`."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).is_dimmed(work_id),
            message=f"работа {work_id} должна быть затемнена фильтрацией (dim, opacity 0.3), но не затемнена",
        )


@allure.step("Then блёрб работы {work_id} НЕ затемнён (рейтинг вне hidden-set)")
def assert_blurb_not_dimmed(driver, work_id: str):
    """TC-092: негативная сверка для работ вне hidden-set — вызывается ПОСЛЕ
    `assert_blurb_dimmed`/`assert_blurb_visible` целевой работы того же листинга
    (applyAllFilters красит opacity ВСЕХ блёрбов за один синхронный проход, тот же
    приём, что `assert_rate_button_unrated`), поэтому мгновенное чтение здесь не гонка."""
    with contexts.in_webview(driver):
        opacity = ListingPage(driver).opacity_of(work_id)
    assert opacity != "0.3", (
        f"работа {work_id} неожиданно затемнена (opacity=0.3), хотя её рейтинг вне hidden-set"
    )


@allure.step("When нажата Rate-кнопка работы {work_id} на листинге")
def tap_rate_button(driver, work_id: str):
    """Клик по инжектированной bridge Rate-кнопке (`ao3_bridge.js::makeRateButton`) —
    обработчик клика добавлен синхронно при её создании (в момент первого прохода
    bridge по `li[id^="work_"]`, уже пройденного к моменту, когда `open_listing`
    дождался блёрбов), доп. ожидание готовности хендлера не нужно. Клик открывает
    нативный `RatingOverlay` (bottom-sheet) поверх WebView — ожидание его появления
    делает вызывающий шаг (`rating_steps.rate_via_listing_overlay`), не этот.

    Клик через JS DOM API, не Selenium `.click()` (TC-072/074/076, диагностика на
    живом archiveofourown.org): реальная страница держит в DOM `div#tos_prompt`
    (CSS-класс `hidden`, полноэкранный оверлей) — Chromedriver's native click
    геометрически считает его перекрывающим точку клика (`elementFromPoint`
    возвращает именно его, а не саму Rate-кнопку) и падает
    `ElementNotInteractableException`, хотя визуально/логически элемент скрыт.
    Тот же класс проблемы, что уже решён для `SortFilterFormPage.click_save_filter`
    (см. модульный докстринг `sort_filter_form_page.py`) — JS `element.click()`
    не требует геометрической интерактивности и всё равно вызывает обработчик,
    добавленный `addEventListener('click', ...)` в `makeRateButton`, с тем же
    наблюдаемым эффектом, что реальный тап пользователя."""
    with contexts.in_webview(driver):
        btn = ListingPage(driver).rate_button(work_id)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", btn)


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


@allure.step("Then на ВСЕХ вхождениях работы {work_id} на листинге появился бейдж рейтинга")
def assert_rating_badge_visible_all(driver, work_id: str, expected_count: int = 2):
    """Как `assert_rating_badge_visible`, но требует, чтобы бейдж проставился у
    НЕСКОЛЬКИХ вхождений блёрба на одной странице (TC-012, `listing_duplicate_work.mitm`) —
    доказывает, что `applyRatings` обходит ВСЕ `li[id^="work_"]`, а не только первое
    совпадение `querySelector`."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).rated_button_count(work_id) >= expected_count,
            message=f"бейдж рейтинга работы {work_id} не появился у всех {expected_count} "
                    f"вхождений на листинге",
        )


@allure.step("Then Rate-кнопка работы {work_id} в состоянии «неоценено» (прозрачный фон)")
def assert_rate_button_unrated(driver, work_id: str):
    """TC-073: сверка НЕГАТИВНОЙ ветки бейджа per-work — вызывается СРАЗУ после
    `assert_rating_badge_visible` другой работы того же листинга (не опрос):
    `applyRatings` красит Rate-кнопки ВСЕХ `li[id^="work_"]` за ОДИН синхронный
    проход `forEach`, поэтому если бейдж целевой работы уже подтверждён опросом,
    состояние остальных в ЭТОМ ЖЕ вызове уже тоже финализировано (тот же приём,
    что `assert_tag_not_highlighted`)."""
    with contexts.in_webview(driver):
        state = ListingPage(driver).rate_button_state(work_id)
    assert state["bg"] in ("", "transparent", "rgba(0, 0, 0, 0)"), (
        f"work {work_id}: Rate-кнопка не в состоянии «неоценено» (bg={state['bg']!r})"
    )


@allure.step("Then Note-кнопка работы {work_id} присутствует, title равен засеянному/сохранённому комментарию «{expected_title}»")
def assert_note_button_present(driver, work_id: str, expected_title: str, timeout: int | None = None):
    """TC-074/075: опрашивает появление `[data-ao3-note-btn]` — следствие нативного
    round-trip (сохранение через UI live-кейса ИЛИ применение засеянных данных при
    первой загрузке replay-листинга), тот же класс гонки, что `assert_rating_badge_visible`."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).has_note_button(work_id),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"Note-кнопка работы {work_id} не появилась (comment не пуст, но кнопка не инжектирована)",
        )
        actual_title = ListingPage(driver).note_button_title(work_id)
    assert actual_title == expected_title, (
        f"title Note-кнопки работы {work_id} не совпадает с ожидаемым комментарием: "
        f"{actual_title!r} != {expected_title!r}"
    )


@allure.step("Then Note-кнопка работы {work_id} отсутствует (нет comment)")
def assert_note_button_absent(driver, work_id: str):
    """Мгновенная проверка (не опрос) — вызывается ПОСЛЕ `assert_note_button_present`
    другой работы того же листинга (см. докстринг `assert_rate_button_unrated` за тем
    же обоснованием синхронного единого прохода `applyRatings`), либо как
    предусловие Given до какого-либо действия (работа без comment остаётся такой,
    гонки со временем нет)."""
    with contexts.in_webview(driver):
        assert not ListingPage(driver).has_note_button(work_id), (
            f"Note-кнопка работы {work_id} неожиданно присутствует (comment не засеян/не сохранялся)"
        )


@allure.step("Then Tag-кнопка работы {work_id} присутствует")
def assert_tag_button_present(driver, work_id: str, timeout: int | None = None):
    """TC-076/077: опрашивает появление `[data-ao3-tag-btn]` — тот же класс гонки,
    что `assert_note_button_present`."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).has_tag_button(work_id),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"Tag-кнопка работы {work_id} не появилась (личный тег вне AO3-набора карточки, но кнопка не инжектирована)",
        )


@allure.step("Then Tag-кнопка работы {work_id} отсутствует")
def assert_tag_button_absent(driver, work_id: str):
    """Мгновенная проверка (не опрос) — см. докстринг `assert_note_button_absent`:
    вызывается ПОСЛЕ подтверждённого барьера (`assert_rating_badge_visible`/
    `assert_tag_button_present` другой работы того же листинга) либо как
    предусловие без гонки со временем."""
    with contexts.in_webview(driver):
        assert not ListingPage(driver).has_tag_button(work_id), (
            f"Tag-кнопка работы {work_id} неожиданно присутствует (личный тег отсутствует "
            f"или полностью пересекается с AO3-тегами карточки)"
        )


@allure.step("Then прочитаны собственные AO3-теги карточки работы {work_id} на листинге")
def own_ao3_tags(driver, work_id: str) -> list[str]:
    """TC-076/077: читает `ul.tags.commas li a.tag` работы `work_id` — тот же набор,
    что `ao3_bridge.js::getCustomTags` строит в `ao3Set`. Нужно на живом листинге,
    где состав AO3-тегов конкретной карточки не детерминирован заранее (в отличие
    от replay-фикстуры `listing_basic.mitm`)."""
    with contexts.in_webview(driver):
        return ListingPage(driver).own_tags(work_id)


@allure.step("Then среди work id листинга (кроме {exclude_work_id}) найдена работа с хотя бы одним собственным AO3-тегом")
def find_blurb_with_ao3_tags(driver, work_ids: list[str], exclude_work_id: str) -> tuple[str, str]:
    """TC-076: проверка ветки биусловности «личный тег СОВПАДАЕТ с AO3-тегом
    карточки» требует карточку, реально имеющую хотя бы один AO3-тег — на живом
    листинге это не гарантировано для ЛЮБОЙ работы, поэтому перебираем `work_ids`
    (кроме уже занятой `exclude_work_id`), пока не найдём подходящую. Возвращает
    `(work_id, первый_текст_её_AO3-тега)`."""
    with contexts.in_webview(driver):
        page = ListingPage(driver)
        for work_id in work_ids:
            if work_id == exclude_work_id:
                continue
            tags = page.own_tags(work_id)
            if tags:
                return work_id, tags[0]
    raise AssertionError(
        f"не найдено ни одной работы листинга (кроме {exclude_work_id!r}) с собственным "
        f"AO3-тегом — не на чем проверить ветку биусловности Tag-кнопки (TC-076)"
    )


@allure.step("When нажата Note-кнопка работы {work_id} на листинге")
def tap_note_button(driver, work_id: str):
    """Клик по инжектированной Note-кнопке (карандаш) — открывает лишь всплывающую
    подсказку с текстом заметки (`ao3_bridge.js::showTooltip`), не overlay напрямую
    (см. `tap_note_tooltip`, TC-044)."""
    with contexts.in_webview(driver):
        ListingPage(driver).note_button(work_id).click()


@allure.step("When нажата всплывающая подсказка Note-кнопки")
def tap_note_tooltip(driver):
    """Клик по САМОЙ подсказке (не по Note-кнопке) — вызывает `signalRateWithNote`,
    открывающий нативный `RatingOverlay` с уже развёрнутым полем комментария
    (см. `tap_note_button`, TC-044)."""
    with contexts.in_webview(driver):
        ListingPage(driver).note_tooltip().click()


@allure.step("Then AO3-тег «{tag_text}» на карточке работы {work_id} подсвечен (совпадение с личным тегом)")
def assert_tag_highlighted(driver, work_id: str, tag_text: str):
    """Опрашивает атрибут `data-ao3-tag-hl`, а не читает один раз: подсветка —
    следствие нативного round-trip (`highlightWorkTags`, вызываемого из
    `window.applyRatings`), тот же класс гонки, что `assert_blurb_hidden` (TC-056)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).tag_link_highlighted(work_id, tag_text),
            message=f"AO3-тег «{tag_text}» работы {work_id} не подсвечен (data-ao3-tag-hl отсутствует)",
        )


@allure.step("Then AO3-тег «{tag_text}» на карточке работы {work_id} НЕ подсвечен")
def assert_tag_not_highlighted(driver, work_id: str, tag_text: str):
    """Проверка мгновенная (не опрос): вызывается ПОСЛЕ `assert_tag_highlighted` в
    том же тесте — `highlightWorkTags` обрабатывает ВСЕ теги блёрба за один
    синхронный проход, так что если один тег уже подсвечен, остальные в этом же
    вызове уже тоже обработаны (TC-056)."""
    with contexts.in_webview(driver):
        assert not ListingPage(driver).tag_link_highlighted(work_id, tag_text), (
            f"AO3-тег «{tag_text}» работы {work_id} неожиданно подсвечен"
        )


_NO_RELOAD_MARKER_ATTR = "__ao3TestNoReloadMarker"


@allure.step("Given зафиксирован baseline: WebView не совершал навигацию с момента открытия страницы")
def mark_no_reload_baseline(driver) -> str:
    """Кладёт уникальный маркер в `window` активной WebView-страницы. JS-вызовы,
    которыми `applyRating`/`broadcastRatingChange` (BrowserViewModel.kt) обновляют
    бейджи — `evaluateJavascript` на уже загруженном документе, НЕ навигация —
    маркер их переживает. Любая РЕАЛЬНАЯ навигация/reload заменяет документ и стирает
    все `window`-глобалы, включая маркер — более надёжный сигнал, чем счётчик
    `onPageFinished`/history index (недоступны из WebDriver JS напрямую) или
    визуальный flash/loading indicator (у этого приложения таких нет), см. TC-010/011."""
    marker = f"no-reload-{uuid.uuid4().hex}"
    with contexts.in_webview(driver):
        driver.execute_script(f"window.{_NO_RELOAD_MARKER_ATTR} = {marker!r};")
    return marker


@allure.step("Then WebView не выполнил навигацию/reload с момента baseline")
def assert_no_reload_since(driver, marker: str) -> None:
    with contexts.in_webview(driver):
        current = driver.execute_script(f"return window.{_NO_RELOAD_MARKER_ATTR};")
    assert current == marker, (
        f"WebView перезагрузился/навигировал: window-маркер потерян "
        f"(было {marker!r}, стало {current!r})"
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


@allure.step("When в выпадашке фильтра выбран профиль «{name}»")
def select_filter_option(driver, name: str):
    BrowserScreen(driver).select_filter_option(name)


@allure.step("Then панель фильтра показывает «{name}» как активно применённый")
def assert_active_filter_shown(driver, name: str, timeout: int | None = None):
    """Триггер FilterPanel (BottomBar.kt `Text(activeFilter?.name ?: "None")`)
    перерисовывается сразу при смене `activeFilterId` — но сам выбор опции ТАКЖЕ
    сворачивает нижнюю ручку-пилюлю (`MainActivity.kt onFilterSelected = { ...;
    navExpanded = false }`), а панель целиком скрыта, пока пилюля свёрнута
    (`BottomBar.kt AnimatedVisibility(visible = selectedTab != BROWSE ||
    navExpanded)`, см. `framework/screens/navigation.py`) — без повторного
    раскрытия ручки триггер не найти вообще, не только его новый текст."""
    BottomNav(driver).ensure_visible()
    assert BrowserScreen(driver).filter_dropdown_has_option(name, timeout=timeout), (
        f"панель фильтра не показывает «{name}» как активно применённый профиль"
    )


# --- Форма AO3 Sort & Filter (#work-filters) + инжектированная "Save filter" —
# TC-040, см. `framework/web/sort_filter_form_page.py` за обоснованием JS-приёмов. ---

@allure.step("Given форма Sort & Filter AO3 открыта на {url}, поле word count min заполнено «{value}»")
def open_sort_filter_form(driver, url: str, value: str) -> None:
    open_listing(driver, url)
    with contexts.in_webview(driver):
        SortFilterFormPage(driver).set_word_count_min(value)


@allure.step("When нажата инжектированная кнопка «Save filter»")
def tap_save_filter_button(driver) -> None:
    with contexts.in_webview(driver):
        SortFilterFormPage(driver).click_save_filter()


@allure.step("Then появляется диалог «Save filter»")
def assert_save_filter_dialog_visible(driver, timeout: int | None = None) -> None:
    assert BrowserScreen(driver).save_filter_dialog_visible(timeout=timeout), (
        "диалог «Save filter» не появился после нажатия инжектированной кнопки"
    )


def _wait_relationship_controls_ready(driver, timeout: int | None = None) -> None:
    """Ждёт, пока ОБА инжектированных main-pairing чекбокса (include/exclude)
    появятся в DOM — `injectMainPairingCheckbox`/`injectExcludeMainPairingCheckbox`
    вызываются синхронно внутри общего IIFE вместе с инъекцией Rate-кнопок, но
    независимая от bridge навигация WebView могла обогнать его выполнение (тот
    же класс гонки, что `assert_every_blurb_has_unrated_rate_button`)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: (
                len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.MAIN_PAIRING_CHECKBOX)) > 0
                and len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.EXCL_MAIN_PAIRING_CHECKBOX)) > 0
            ),
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message="инжектированные relationship-чекбоксы (main-pairing include/exclude) не появились",
        )


@allure.step("Given открыта форма Sort & Filter (replay) на {url}, инжектированные relationship-контролы готовы")
def open_sort_filter_form_relationship_ready(driver, url: str) -> None:
    open_listing(driver, url)
    _wait_relationship_controls_ready(driver)


@allure.step("Given открыта живая форма Sort & Filter на {url}, инжектированные relationship-контролы готовы")
def open_live_sort_filter_form_relationship_ready(driver, url: str) -> None:
    open_live_listing(driver, url)
    _wait_relationship_controls_ready(driver)


# scope: "include" (#include_relationship_tags / [data-ao3-main-pairing-cb], TC-078/079)
# или "exclude" (#exclude_relationship_tags / [data-ao3-excl-main-pairing-cb], TC-080/081) —
# два независимых DOM-узла с одинаковым контрактом доступности (симметрия §9).
_RELATIONSHIP_SCOPES = {
    "include": (selectors.INCLUDE_RELATIONSHIP_TAGS, selectors.MAIN_PAIRING_CHECKBOX),
    "exclude": (selectors.EXCLUDE_RELATIONSHIP_TAGS, selectors.EXCL_MAIN_PAIRING_CHECKBOX),
}


@allure.step("When в {scope}-списке relationship-тегов переключён (клик) чекбокс на позиции {index}")
def toggle_relationship_checkbox(driver, scope: str, index: int) -> None:
    container_selector, _ = _RELATIONSHIP_SCOPES[scope]
    with contexts.in_webview(driver):
        SortFilterFormPage(driver).toggle_relationship_checkbox(container_selector, index)


@allure.step("Then инжектированный main-pairing чекбокс {scope}-списка доступен (disabled=false, label непрозрачный)")
def assert_relationship_checkbox_enabled(driver, scope: str, timeout: int | None = None) -> None:
    _, checkbox_selector = _RELATIONSHIP_SCOPES[scope]
    with contexts.in_webview(driver):
        page = SortFilterFormPage(driver)
        wait_until(
            driver,
            lambda d: bool(state := page.checkbox_availability_state(checkbox_selector)) and not state["disabled"],
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"чекбокс {scope}-списка не стал доступен (disabled остаётся true)",
        )
        state = page.checkbox_availability_state(checkbox_selector)
    assert state is not None and state["opacity"] == "1", (
        f"чекбокс {scope}-списка доступен (disabled=false), но label.style.opacity "
        f"!= '1' (opacity={state and state['opacity']!r})"
    )


@allure.step("Then инжектированный main-pairing чекбокс {scope}-списка НЕ доступен (disabled=true, opacity 0.4)")
def assert_relationship_checkbox_disabled(driver, scope: str, timeout: int | None = None) -> None:
    _, checkbox_selector = _RELATIONSHIP_SCOPES[scope]
    with contexts.in_webview(driver):
        page = SortFilterFormPage(driver)
        wait_until(
            driver,
            lambda d: bool(state := page.checkbox_availability_state(checkbox_selector)) and state["disabled"],
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"чекбокс {scope}-списка не стал недоступен (disabled остаётся false)",
        )
        state = page.checkbox_availability_state(checkbox_selector)
    assert state is not None and state["opacity"] == "0.4", (
        f"чекбокс {scope}-списка недоступен (disabled=true), но label.style.opacity "
        f"!= '0.4' (opacity={state and state['opacity']!r})"
    )


@allure.step("Then инжектированная кнопка Save filter — ровно одна, сразу после submit-кнопки формы")
def assert_save_filter_button_present_once(driver, timeout: int | None = None) -> None:
    with contexts.in_webview(driver):
        page = SortFilterFormPage(driver)
        wait_until(
            driver,
            lambda d: page.save_profile_button_count() >= 1,
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message="инжектированная кнопка Save filter не появилась рядом с submit формы",
        )
        count = page.save_profile_button_count()
        adjacent = page.save_profile_button_immediately_after_submit()
    assert count == 1, f"ожидали ровно одну кнопку Save filter, нашли {count}"
    assert adjacent, (
        "кнопка Save filter не является nextElementSibling submit-кнопки формы "
        "(#work-filters input[name=\"commit\"][type=\"submit\"])"
    )


@allure.step("When форма Sort & Filter мутирует (class #work-filters) {times} раз(а) — имитация повторного раскрытия/скрытия")
def mutate_sort_filter_form(driver, times: int = 2) -> None:
    """Каждый вызов — ОТДЕЛЬНЫЙ `execute_script` (полноценный round-trip через
    chromedriver), а не несколько мутаций в одном синхронном скрипте — иначе
    `MutationObserver` батчит их в ОДИН вызов callback'а вместо `times` отдельных
    срабатываний (микротаск-очередь флашится между раздельными вызовами
    `execute_script`, но не внутри одного). Проверяет реальную идемпотентность
    ЧЕРЕЗ ГРАНИЦЫ обработчика, а не однократный вызов инжектора (TC-082/083)."""
    with contexts.in_webview(driver):
        page = SortFilterFormPage(driver)
        for _ in range(times):
            page.toggle_form_class()


@allure.step("When в диалоге введено имя «{name}» и нажат Save; дожидается фоновой пост-save навигации")
def save_filter_profile_as(driver, name: str) -> None:
    """AT-BUG-016: `confirmSaveFilter` (`BrowserViewModel.kt`) уходит в ФОНОВУЮ
    навигацию активной вкладки (`navigateActiveTabTo`) сразу после подтверждения
    диалога — эта навигация форвардит на live-URL (суб-ресурсы `sort_filter_form.mitm`
    не самодостаточны) и раньше НЕ дожидалась перед `open_tab("Settings")`, из-за чего
    UiAutomator2 tree-dump (`_find_pill`) конкурировал с GPU-компоновкой ещё
    рендерящейся живой страницы и детерминированно крашил qemu (0xc0000005).
    Дожидаемся `document.readyState == 'complete'` НОВОЙ страницы (URL сменился
    относительно того, что было открыто до Save) прежде чем возвращать управление —
    к моменту `open_tab("Settings")` фоновый рендер уже осел."""
    with contexts.in_webview(driver):
        pre_save_url = driver.current_url

    screen = BrowserScreen(driver)
    screen.enter_filter_profile_name(name)
    screen.confirm_save_filter()

    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: (
                (d.current_url or "") != pre_save_url
                and d.execute_script("return document.readyState;") == "complete"
            ),
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="фоновая пост-save навигация (BrowserViewModel.confirmSaveFilter) "
                    "не завершилась (URL не сменился или readyState не complete)",
        )


# --- Кастомная error page при ошибке загрузки главного фрейма (TC-046,
# BrowserScreen.kt WebViewClient.onReceivedError/onPageFinished, buildErrorHtml) ---

def _is_stale(element) -> bool:
    """True, если `element` больше не привязан к текущему DOM (страница
    перезагрузилась/заменилась) — используется как доказательство РЕАЛЬНОЙ
    навигации после клика Retry, не одноразовое чтение состояния."""
    try:
        element.is_enabled()
        return False
    except StaleElementReferenceException:
        return True


@allure.step("When в WebView открыт заведомо недоступный по сети URL {url}")
def open_unreachable_url(driver, url: str = UNREACHABLE_URL) -> None:
    """Навигация активной вкладки на несуществующий домен — main-frame запрос
    гарантированно завершается `ERR_NAME_NOT_RESOLVED` (см. `UNREACHABLE_URL`).

    chromedriver's `Page.navigate` (за которым стоит `driver.get`) ждёт
    завершения загрузки фрейма и surfaced-ит сетевую ошибку СИНХРОННО как
    `WebDriverException("net::ERR_...")` из самого вызова `get()` — это
    отдельный канал от нативного `WebViewClient.onReceivedError` приложения
    (который и рисует кастомную error page, проверяемую следующим шагом).
    Эта ошибка chromedriver — ОЖИДАЕМЫЙ сигнал (сама фиксация сетевого сбоя,
    без него не было бы что проверять), не флейк: гасим только `net::ERR*`,
    любая другая причина падения `get()` (не про сеть) уходит дальше.
    Не ждём успешной загрузки (её не будет по построению) — ожидание кастомной
    error page делает отдельный шаг `assert_error_page_shown`."""
    with contexts.in_webview(driver):
        try:
            driver.get(url)
        except WebDriverException as exc:
            if "net::ERR" not in str(exc):
                raise


@allure.step("Then показана кастомная themed error page с Retry-ссылкой на {expected_url}")
def assert_error_page_shown(driver, expected_url: str = UNREACHABLE_URL, timeout: int | None = None):
    """Ждёт кастомную error page приложения (`BrowserScreen.kt buildErrorHtml`),
    загруженную через `loadDataWithBaseURL("about:blank", ...)` — НЕ дефолтную
    страницу ошибки Chrome/WebView (у неё другие разметка/URL). Проверяет три
    факта из Then кейса разом: (1) `current_url` == `about:blank` (страница не
    попадает в историю навигации — заметка кейса), (2) текст кастомного заголовка
    виден, (3) Retry-ссылка ведёт на исходный (упавший) URL, не на другой адрес."""
    timeout = timeout or settings.WEBVIEW_LOAD_TIMEOUT
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: (d.current_url or "") == "about:blank",
            timeout=timeout,
            message="WebView не перешёл на about:blank — кастомная error page грузится "
                    "через loadDataWithBaseURL с base URL about:blank",
        )
        page = ErrorPage(driver)
        heading = page.wait_heading(timeout=timeout)
        assert heading.text.strip() == "Couldn't load this page", (
            f"неожиданный текст заголовка кастомной error page: {heading.text!r} "
            f"(похоже на дефолтную страницу ошибки WebView/Chrome, не кастомную)"
        )
        link = page.retry_link(timeout=timeout)
        href = link.get_attribute("href")
        assert href == expected_url, (
            f"Retry-ссылка ведёт не на исходный упавший URL: {href!r} != {expected_url!r}"
        )


# --- TabStrip: создание/лимит/закрытие/undo/переключение вкладок (TC-022..026) ---

@allure.step("When нажата кнопка «New tab» в TabStrip")
def open_new_tab(driver) -> None:
    BrowserScreen(driver).tap_new_tab()


@allure.step("Then показан диалог «Tab limit reached» с упоминанием {expected_max} вкладок")
def assert_tab_limit_dialog_shown(driver, expected_max: int = 10, timeout: int | None = None) -> None:
    screen = BrowserScreen(driver)
    assert screen.tab_limit_dialog_visible(timeout=timeout), (
        "диалог «Tab limit reached» не появился при достижении MAX_TABS"
    )
    message = screen.tab_limit_dialog_message(timeout=timeout)
    assert f"{expected_max} tabs open" in message, (
        f"текст диалога лимита не упоминает «{expected_max} tabs open»: {message!r}"
    )


@allure.step("Then диалог «Tab limit reached» НЕ появился")
def assert_tab_limit_dialog_not_shown(driver, timeout: int = 2) -> None:
    assert not BrowserScreen(driver).tab_limit_dialog_visible(timeout=timeout), (
        "диалог «Tab limit reached» появился преждевременно (до достижения MAX_TABS)"
    )


@allure.step("When диалог «Tab limit reached» закрыт нажатием OK")
def dismiss_tab_limit_dialog(driver) -> None:
    BrowserScreen(driver).dismiss_tab_limit_dialog()


@allure.step("When свайпом вверх закрыта вкладка на позиции {position}")
def swipe_close_tab(driver, position: int) -> None:
    BrowserScreen(driver).swipe_close_tab(position)


@allure.step("When пользователь переключается на вкладку на позиции {position}")
def switch_to_tab(driver, position: int) -> None:
    BrowserScreen(driver).tap_tab_chip(position)


@allure.step("Then в snackbar показан Undo для закрытой вкладки")
def assert_undo_snackbar_visible(driver, timeout: int = 5) -> None:
    assert BrowserScreen(driver).undo_snackbar_visible(timeout=timeout), (
        "snackbar с действием Undo не появился после закрытия вкладки"
    )


@allure.step("Then прочитан заголовок чипа на позиции {position}")
def tab_chip_title_at(driver, position: int, timeout: int | None = None) -> str:
    return BrowserScreen(driver).tab_chip_title_at(position, timeout=timeout)


@allure.step("Then из списка кандидатов отобраны заголовки, реально видимые в TabStrip")
def visible_titles(driver, titles: list[str], timeout: int = 3) -> list[str]:
    return [t for t in titles if BrowserScreen(driver).tab_title_visible(t, timeout=timeout)]


@allure.step("Then исчерпывающе перебраны доступные snackbar Undo (до {max_attempts} попыток), посчитаны успешные восстановления и подтверждённые маркеры")
def exhaust_undo_snackbars(driver, max_attempts: int = 8, candidate_titles: list[str] | None = None) -> tuple[int, list[str]]:
    """TC-024: сколько бы snackbar'ов Undo ни оказалось реально доступно (см. заметки
    TC-024.md про эмпирически ограниченную интерактивность очереди
    `SnackbarHostState.showSnackbar` под программной нагрузкой) — нажимает Undo на
    КАЖДОМ появившемся, считая по росту числа видимых чипов «Close tab», является ли
    попытка успешным восстановлением или молчаливым no-op (эвикнутый снапшот).

    Возвращает `(restored_count, confirmed_titles)` — `confirmed_titles` из
    `candidate_titles` считываются СРАЗУ после КАЖДОГО успешного восстановления
    (не единым отложенным снимком в самом конце вызывающим кодом). Найдено
    2026-07-18 (доработка по ревью, попутный прогон): единый снимок «в самом
    конце» после того, как цикл уже потратил ДОПОЛНИТЕЛЬНЫЕ `undo_snackbar_visible(
    timeout=10)`-ожидания на ещё один(-е) НЕсуществующий(-е) снекбар(ы) перед тем,
    как окончательно оборвать цикл, — воспроизводимо (1 из 5 прогонов) давал
    `restored_count > len(найденных title)`: не потому что восстановилась Home
    (снапшот Home эвиктится синхронно ДО первого показа snackbar'а, см. докстринг
    теста в `test_tabs.py`), а потому что снимок заголовков откладывался на
    десятки секунд позже самого восстановления. Чтение заголовка сразу устраняет
    временной зазор между «событием» и «измерением».

    Найдено 2026-07-18 (доработка по ревью, попутный прогон TC-024, отдельный
    класс): между проверкой `undo_snackbar_visible` и `tap_undo_snackbar` есть
    зазор, в который снекбар может успеть авто-скрыться (`SnackbarDuration.Short`
    ~4с) — особенно для ПЕРВОГО (Home) снекбара, который к моменту начала опроса
    тестом уже мог провисеть заметную долю своего окна (6 swipe-закрытий занимают
    реальное время устройства). Непойманный `TimeoutException` из-под
    `tap_undo_snackbar` раньше падал наружу и валил тест. Тап обёрнут коротким
    таймаутом + try/except — гонка с авто-скрытием трактуется как истёкшая
    попытка (цикл идёт дальше проверять следующий снекбар), а не как крах
    теста."""
    restored_count = 0
    confirmed_titles: list[str] = []
    for _ in range(max_attempts):
        if not BrowserScreen(driver).undo_snackbar_visible(timeout=10):
            break
        before = BrowserScreen(driver).close_tab_icon_count()
        try:
            BrowserScreen(driver).tap_undo_snackbar(timeout=3)
        except Exception:  # noqa: BLE001 — снекбар авто-скрылся между проверкой и тапом
            continue
        try:
            wait_until(driver, lambda d: BrowserScreen(d).close_tab_icon_count() != before,
                       timeout=3, message="tab count unchanged after Undo tap")
            restored_count += 1
            if candidate_titles:
                confirmed_titles = visible_titles(driver, candidate_titles)
        except Exception:  # noqa: BLE001 — ожидаемый исход для вытесненного снапшота
            pass
    return restored_count, confirmed_titles


@allure.step("When нажат Undo в snackbar")
def tap_undo(driver, timeout: int | None = None) -> None:
    BrowserScreen(driver).tap_undo_snackbar(timeout=timeout)


@allure.step("When snackbar «Tab closed» смахнут в сторону (без нажатия Undo)")
def dismiss_snackbar_by_swipe(driver, timeout: int | None = None) -> None:
    BrowserScreen(driver).swipe_dismiss_snackbar(timeout=timeout)


@allure.step("Then заголовок вкладки, содержащий «{title_substring}», виден в TabStrip")
def assert_tab_title_visible(driver, title_substring: str, timeout: int | None = None) -> None:
    assert BrowserScreen(driver).tab_title_visible(title_substring, timeout=timeout), (
        f"заголовок вкладки, содержащий «{title_substring}», не найден в TabStrip"
    )


@allure.step("Then заголовок вкладки, содержащий «{title_substring}», НЕ виден в TabStrip")
def assert_tab_title_not_visible(driver, title_substring: str, timeout: int = 3) -> None:
    assert not BrowserScreen(driver).tab_title_visible(title_substring, timeout=timeout), (
        f"заголовок вкладки, содержащий «{title_substring}», неожиданно виден в TabStrip"
    )


@allure.step("When активная вкладка проскроллена вниз нативным свайпом")
def swipe_scroll_active_tab(driver, distance_px: int = 1400) -> None:
    BrowserScreen(driver).swipe_scroll_active_tab_down(distance_px)


@allure.step("Then заголовок чипа на позиции {position} равен «{expected_title}»")
def assert_tab_title_at_position(driver, position: int, expected_title: str, timeout: int | None = None) -> None:
    """Опрашивает заголовок чипа, не читает один раз: сразу после создания/
    восстановления вкладки чип несёт плейсхолдер `TabInfo.title = "Loading…"`
    (TabInfo.kt) до срабатывания `WebChromeClient.onReceivedTitle` — одноразовое
    чтение сразу после появления элемента ловило бы гонку (та же гонка, что уже
    закрыта в других опросах этого модуля, см. `assert_active_tab_url`)."""
    actual = wait_until(
        driver,
        lambda d: (t := BrowserScreen(d).tab_chip_title_at(position, timeout=2)) == expected_title and t,
        timeout=timeout or 5,
        message=f"чип на позиции {position} не получил заголовок {expected_title!r}",
    )
    assert actual == expected_title


@allure.step("When пользователь делает long-press по ссылке работы «{title}» на листинге")
def long_press_work_link(driver, title: str, timeout: int | None = None) -> None:
    """Настоящий native long-press поверх WebView-ссылки (TC-026) — см.
    `BrowserScreen.long_press_link_by_text` и `bugs/AT-BUG-018.md` за полным
    обоснованием механизма (native a11y-узел ссылки, не координаты/офсет
    контейнера WebView)."""
    BrowserScreen(driver).long_press_link_by_text(title, timeout)


@allure.step("When нажата Retry-ссылка на error page")
def click_retry(driver) -> None:
    """Клик по Retry-ссылке инициирует повторную загрузку исходного (упавшего) URL —
    WebView без `shouldOverrideUrlLoading`-перехвата обрабатывает переход по `<a href>`
    сама (см. BrowserScreen.kt), это полноценная новая навигация, не no-op: держим
    ссылку на СТАРЫЙ DOM-элемент и ждём, пока обращение к нему не станет
    `StaleElementReferenceException` — доказательство того, что документ реально
    перезагрузился (а не просто визуально не изменился), прежде чем вызывающий шаг
    станет проверять НОВУЮ error page."""
    with contexts.in_webview(driver):
        link = ErrorPage(driver).retry_link()
        link.click()
        wait_until(
            driver, lambda d: _is_stale(link), timeout=10,
            message="страница не перезагрузилась после клика Retry (старый DOM-узел "
                    "Retry-ссылки остаётся валидным)",
        )
