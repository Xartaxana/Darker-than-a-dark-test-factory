"""Бизнес-шаги содержимого WebView, не привязанные к конкретному нативному экрану."""
from __future__ import annotations

import contextlib
import re
import time
import uuid

import allure
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.interaction import POINTER_TOUCH

from framework.config import settings
from framework.core import contexts
from framework.core.navigate import navigate
from framework.core.waits import assert_holds_for, poll_for, wait_until
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
        # AT-BUG-025: driver.get() голым вызовом может зависнуть без load-события
        # (WebView этого приложения) — bounded-хелпер ограничивает сам вызов
        # навигации тем же бюджетом, что и последующий wait_until.
        navigate(driver, STABLE_TALL_LIVE_URL, settings.WEBVIEW_LOAD_TIMEOUT)
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


@allure.step("Then компоновка WebView соответствует ориентации (landscape={landscape})")
def assert_layout_matches_orientation(driver, landscape: bool) -> None:
    """TC-111: прокси «side panel/лейаут отражает ориентацию» через ШИРИНУ/ВЫСОТУ
    нативного WebView-контейнера — не через взаимодействие с side panel (см.
    `BrowserScreen.webview_rect` докстринг за находкой разведки: side panel/
    TabStrip/BottomBar полностью пропадают из accessibility-дерева сразу после
    поворота устройства, не восстанавливаются за 10с/тап — находка для триажа,
    не блокер этого кейса)."""
    rect = BrowserScreen(driver).webview_rect()
    if landscape:
        assert rect["width"] > rect["height"], f"компоновка не landscape: WebView rect={rect}"
    else:
        assert rect["height"] > rect["width"], f"компоновка не portrait: WebView rect={rect}"


@allure.step("When устройство повёрнуто в {orientation}")
def rotate(driver, orientation: str) -> None:
    """TC-111: штатное Appium/WebDriver-capability (`driver.orientation`), не
    требует нового framework-примитива — манифест приложения несёт
    `configChanges="uiMode|orientation|screenSize|screenLayout|
    smallestScreenSize"` (сверено в `AndroidManifest.xml`), поворот НЕ
    пересоздаёт Activity."""
    driver.orientation = orientation


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


@allure.step("Then TabStrip НЕ виден (экран не переключился на Browse)")
def assert_tab_strip_not_visible(driver, timeout: int = 3):
    """TC-173/175: TabStrip рендерится ТОЛЬКО при `selectedTab == AppTab.BROWSE`
    (MainActivity.kt:408), НЕЗАВИСИМО от числа открытых вкладок — его отсутствие
    после фонового открытия из Library доказывает, что экран не переключился на
    Browse (в отличие от TC-136/TC-137, где тап по телу карточки переключает
    экран безусловно). Мгновенный снимок (не `assert_holds_for`) — действие уже
    завершилось синхронной рекомпозицией к моменту вызова, не async-эффект."""
    assert not BrowserScreen(driver).is_tab_strip_visible(timeout=timeout), (
        "TabStrip неожиданно виден — похоже, экран переключился на Browse"
    )


@allure.step("Then TabStrip остаётся скрыт весь бюджет (fullscreen активен)")
def assert_tab_strip_hidden(driver, timeout: int = 10, poll_interval: float = 0.3):
    """Доработка (батч мелочей D-0081, 2026-07-29): был одноразовый
    `is_tab_strip_visible(timeout=3)` — эффект (TabStrip неожиданно
    появляется), пришедший ПОЗЖЕ единственного 3-секундного опроса, проскакивал
    незамеченным. Теперь `assert_holds_for` держит негатив ВЕСЬ бюджет
    (симметрично `assert_tab_strip_visible`/`assert_top_chrome_not_darkened`),
    падая на ПЕРВОМ появлении полосы в любой момент окна. Каждый опрос —
    мгновенный снимок (`timeout=0`), без вложенного ожидания — ЭТО стало верно
    только с attempt 2 (2026-07-29): `framework/core/waits.py` схлопывал
    falsy `timeout=0` в `DEFAULT_TIMEOUT` (`timeout or DEFAULT_TIMEOUT`), из-за
    чего каждый снимок реально блокировался на ~20s (критик замерил: шаг
    подорожал с ~3.2s до 20.02s одним внешним опросом) — исправлено на
    `timeout if timeout is not None else DEFAULT_TIMEOUT` в самом `waits.py`,
    не здесь (корень класса — там, не в вызывающем коде)."""
    screen = BrowserScreen(driver)

    def check() -> bool:
        return not screen.is_tab_strip_visible(timeout=0)

    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg="TabStrip должен быть скрыт в режиме fullscreen (обнаружен видимым в пределах бюджета)",
    )


@allure.step("Then измерена средняя яркость верхней полосы экрана (пиксельный прокси TabStrip, TC-058)")
def measure_top_chrome_luma(driver) -> float:
    return BrowserScreen(driver).top_chrome_avg_luma()


# --- TC-108: contrast sanity (luma-прокси различимости текста от фона) ---
# Порог подобран эмпирически на живом прогоне (emulator-5554, 2026-07-22): область
# однородной заливки (без текста) даёт std однозначных единиц (шум сжатия PNG/
# сглаживание), область с реальным текстом на контрастном фоне — на порядок больше
# (десятки единиц) в обоих системных вариантах темы (см. witness теста). Щедрый
# отступ ниже минимума здорового диапазона — тот же класс калибровки, что
# `perf_steps.MEMORY_RECOVERY_FRACTION`.
CONTRAST_SANITY_MIN_STD = 15.0


@allure.step("Then текст bottom bar различим от фона по luma-прокси (std >= {min_std})")
def assert_bottom_bar_text_distinguishable(driver, min_std: float = CONTRAST_SANITY_MIN_STD):
    _, std = BrowserScreen(driver).region_luma_stats(BrowserScreen(driver).bottom_bar_box())
    assert std >= min_std, (
        f"bottom bar: luma std={std:.1f} ниже sanity-порога {min_std} — текст и фон "
        f"визуально неразличимы (luma-прокси, не точный WCAG-ratio, см. TC-108)"
    )


@allure.step("Then заголовок работы различим от фона по luma-прокси (std >= {min_std})")
def assert_work_title_distinguishable(driver, min_std: float = CONTRAST_SANITY_MIN_STD):
    _, std = BrowserScreen(driver).region_luma_stats(BrowserScreen(driver).work_title_zone_box())
    assert std >= min_std, (
        f"заголовок работы: luma std={std:.1f} ниже sanity-порога {min_std} — текст и "
        f"фон визуально неразличимы (luma-прокси, не точный WCAG-ratio, см. TC-108)"
    )


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


# --- AT-BUG-030: поведенческий контроль guard'а тап-зон (bridge-tap-zone-guard,
# TC-119/120/122). Тап дispatch'ится синтетическим `MouseEvent` через
# `dispatchEvent`, не Selenium `.click()`/физическим нативным тапом — тот же
# класс обхода, что уже используют `tap_rate_button`/`click_probe_link`
# (JS DOM API вместо геометрической интерактивности), усиленный явным
# `clientX`/`clientY`: голый `.click()` отдаёт `clientX=clientY=0` в событии,
# недостаточно guard'у (`ao3_bridge.js:1156-1160`), который вычисляет треть
# тапа именно из `e.clientY`. Координата берётся из РЕАЛЬНОГО
# `getBoundingClientRect()` узла (центр) — honesty-тест читает фактическое
# положение, заданное фикстурой (AT-BUG-030, `position:absolute; top:Nvh`),
# а не хардкодит предположение о нём; если регрессия испортит геометрию
# фикстуры, вычисленная координата уедет из требуемой трети/band вместе с ней
# (тот же диагностический эффект, что описан в bugs/AT-BUG-030.md). `bubbles:
# true` обязателен для `onclick`-атрибута самого узла (bubbling-фаза); guard
# слушает `click` на `document` с `{capture:true}` — синтетический
# `dispatchEvent` проходит capture-фазу независимо от `bubbles`, но `onclick`
# узла — только с `bubbles:true`.
@allure.step("When синтетически тапнут DOM-узел {css_selector} (координата — центр его РЕАЛЬНОГО bounding rect)")
def dispatch_synthetic_tap(driver, css_selector: str) -> dict:
    with contexts.in_webview(driver):
        el = driver.find_element(AppiumBy.CSS_SELECTOR, css_selector)
        rect = driver.execute_script(
            "var r = arguments[0].getBoundingClientRect();"
            "return {left: r.left, top: r.top, width: r.width, height: r.height, "
            "innerHeight: window.innerHeight};",
            el,
        )
        client_x = rect["left"] + rect["width"] / 2
        client_y = rect["top"] + rect["height"] / 2
        driver.execute_script(
            "var ev = new MouseEvent('click', {bubbles: true, cancelable: true, "
            "clientX: arguments[1], clientY: arguments[2], view: window});"
            "arguments[0].dispatchEvent(ev);",
            el, client_x, client_y,
        )
    # S-2 (доработка attempt 2, критик-вход B4): фракция включена В ВОЗВРАЩАЕМЫЙ
    # dict, не только в текстовое allure-вложение — позволяет вызывающим
    # steps-обёрткам (`dispatch_tap_zone_*_tap`) заассертить геометрию узла БЕЗ
    # пересчёта.
    rect["fraction_of_innerHeight"] = client_y / rect["innerHeight"]
    allure.attach(
        f"css_selector={css_selector!r} rect={rect!r} dispatched_clientY={client_y:.1f} "
        f"fraction_of_innerHeight={rect['fraction_of_innerHeight']:.3f}",
        name="tap-zone-guard-dispatch-geometry",
        attachment_type=allure.attachment_type.TEXT,
    )
    return rect


# S-2 (доработка attempt 2, критик-вход B4): geometry-ассерты в рантайме
# отсутствовали — `dispatch_synthetic_tap` возвращал `rect`/
# `fraction_of_innerHeight`, но ни один тест это не проверял. Для НЕГАТИВНЫХ
# Then (TC-119, TC-122) это дыра: если регрессия испортит геометрию фикстуры
# (узел уедет из средней трети), тест молча дал бы ложно-зелёный (см.
# `bugs/AT-BUG-030.md`, раздел «Геометрия узлов 1 и 2» — диагностическая сила
# негатива зависит от band). Band-границы совпадают с band'ами
# `recording_builder._TAP_ZONE_BUTTON_TOP_VH`/`_TAP_ZONE_DIV_TOP_VH`.
_TAP_ZONE_MIDDLE_THIRD_BAND = (1 / 3, 2 / 3)
_TAP_ZONE_DIV_BAND = (0.44, 0.56)


def _assert_tap_zone_geometry_band(rect: dict, band: tuple[float, float], node_label: str) -> None:
    fraction = rect["fraction_of_innerHeight"]
    low, high = band
    assert low <= fraction <= high, (
        f"{node_label}: fraction_of_innerHeight={fraction:.3f} вне ожидаемого band "
        f"[{low:.3f}, {high:.3f}] — геометрия фикстуры уехала от заданной AT-BUG-030, "
        f"диагностическая сила Then этого узла под угрозой (см. bugs/AT-BUG-030.md)"
    )


@allure.step("Then фикстурный узел {css_selector} несёт data-tapped=\"1\" (собственный обработчик клика сработал)")
def assert_tap_marker_tapped(driver, css_selector: str, timeout: int | None = None) -> None:
    """AT-BUG-030: опрашивает `data-tapped`, а не читает один раз — `dispatchEvent`
    синхронен, но добавляет запас на тот же класс латентности WEBVIEW-round-trip,
    что и остальные опросы этого модуля (`assert_blurb_hidden` и т.п.)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: d.execute_script(
                "var el = document.querySelector(arguments[0]); "
                "return el && el.getAttribute('data-tapped') === '1';",
                css_selector,
            ),
            timeout=timeout or 5,
            message=f"узел {css_selector} не получил data-tapped=\"1\" после синтетического тапа "
                    f"— собственный обработчик клика не сработал",
        )


def _kudo_submit_click_count(driver) -> int:
    """AT-BUG-035: читает `data-kudo-clicked` узла `#kudo_submit` как число
    (инкрементный счётчик, не константа) — `-1`, если узел структурно
    отсутствует (не должно случаться после Verified-фикса, но так негатив не
    станет вакуумно-истинным на отсутствующем узле, а честно провалится на
    сравнении с 0/1, см. класс `AT-BUG-029`/калибровка Lead 2026-07-30)."""
    return driver.execute_script(
        "var el = document.querySelector(arguments[0]); "
        "return el ? Number(el.getAttribute('data-kudo-clicked') || 0) : -1;",
        selectors.KUDO_SUBMIT,
    )


@allure.step("Then узел #kudo_submit несёт data-kudo-clicked=\"{expected}\" (счётчик клика, TC-138/144)")
def assert_kudo_submit_click_count(driver, expected: int, timeout: int | None = None) -> None:
    """Позитивная сверка (TC-138/TC-144): опрашивает, пока инкрементный счётчик
    `#kudo_submit` (AT-BUG-035, `bugs/BUG-015.md`) не достигнет `expected` —
    годится, когда клик УЖЕ должен был случиться синхронно внутри
    `applyRating`/`onRateWorkRequested` (`evalJs`), но чтение требует запаса на
    WEBVIEW round-trip (тот же класс латентности, что `assert_rating_badge_visible`).
    ДЛЯ НЕГАТИВНОГО Then («клика не было») эта функция НЕ годится — условие «уже
    `expected`» истинно с первого кадра и не докажет отсутствия эффекта,
    случившегося ПОЗЖЕ; используйте `assert_kudo_submit_click_count_holds`
    (симметрично `assert_top_chrome_not_darkened` vs `assert_top_chrome_darkened`)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: _kudo_submit_click_count(d) == expected,
            timeout=timeout or 6,
            message=f"узел #kudo_submit не показал data-kudo-clicked={expected} (счётчик клика) "
                    f"в отведённое время",
        )


@allure.step("Then узел #kudo_submit держит data-kudo-clicked=\"{expected}\" стабильно {budget_s}с (не удваивается/не появляется отложенно)")
def assert_kudo_submit_click_count_holds(
    driver, expected: int, budget_s: float = 3.0, poll_interval: float = 0.4,
) -> None:
    """Опрашивает ВЕСЬ бюджет `budget_s` (`framework.core.waits.assert_holds_for`),
    а не читает один раз — тот же приём, что `assert_top_chrome_not_darkened`
    (докстринг там же за полным обоснованием класса «негатив, у которого условие
    уже истинно с первого кадра»). Основное применение — НЕГАТИВНЫЙ Then
    (TC-139/140/141/142/143: «клика не было»), но также покрывает позитивное
    «ровно один клик, не два» (TC-138/144), если вызвать ПОСЛЕ
    `assert_kudo_submit_click_count(driver, expected)` (сначала дождаться
    `expected`, затем убедиться, что он не растёт дальше)."""
    with contexts.in_webview(driver):
        def check() -> bool:
            actual = _kudo_submit_click_count(driver)
            assert actual == expected, (
                f"data-kudo-clicked неожиданно = {actual}, ожидали стабильно {expected} "
                f"весь бюджет {budget_s}с — подозрение на (повторный/отложенный) kudos-клик"
            )
            return True
        assert_holds_for(
            check, budget_s=budget_s, interval_s=poll_interval,
            msg=f"узел #kudo_submit не удержал data-kudo-clicked={expected} весь бюджет {budget_s}с",
        )


# Именованные обёртки над узлами AT-BUG-030 (docs/08 C1: локаторы/`framework.web`
# запрещены прямым импортом в `tests/` — тесты вызывают только именованные
# steps-функции, сам селектор остаётся инкапсулирован здесь).
@allure.step("When синтетически тапнут фикстурный <button> (узел 1, AT-BUG-030)")
def dispatch_tap_zone_button_tap(driver) -> dict:
    rect = dispatch_synthetic_tap(driver, selectors.TAP_ZONE_BUTTON)
    _assert_tap_zone_geometry_band(rect, _TAP_ZONE_MIDDLE_THIRD_BAND, "button (узел 1)")
    return rect


@allure.step("When синтетически тапнут вложенный <span>-потомок фикстурного <button> (узел 1, closest-семантика TC-122)")
def dispatch_tap_zone_button_child_tap(driver) -> dict:
    rect = dispatch_synthetic_tap(driver, selectors.TAP_ZONE_BUTTON_CHILD)
    _assert_tap_zone_geometry_band(rect, _TAP_ZONE_MIDDLE_THIRD_BAND, "span (узел 1, потомок)")
    return rect


@allure.step("When синтетически тапнут фикстурный НЕ-whitelisted <div onclick> (узел 2, AT-BUG-030)")
def dispatch_tap_zone_div_tap(driver) -> dict:
    rect = dispatch_synthetic_tap(driver, selectors.TAP_ZONE_DIV)
    _assert_tap_zone_geometry_band(rect, _TAP_ZONE_DIV_BAND, "div (узел 2)")
    return rect


# TC-121: whitelisted <a> БЕЗ собственного onclick (реальная download-ссылка,
# selectors.DOWNLOAD_HTML_LINK) — четвёртая ячейка 2×2-матрицы (whitelist=true,
# обработчик=false), замыкающая её вместе с TC-119 (true,true) и TC-120
# (false,true). Позиция тапа НЕ завязана на среднюю треть (guard's closest()
# отсекает узел ДО вычисления третьей) — geometry-band ассерт здесь неуместен
# (в отличие от `dispatch_tap_zone_button_tap`/`dispatch_tap_zone_div_tap`),
# координата берётся из естественного положения ссылки в DOM.
@allure.step("When синтетически тапнута download-ссылка HTML в теле work-страницы (li.download a[title=\"HTML\"], TC-121, whitelisted тег БЕЗ собственного onclick)")
def dispatch_tap_zone_download_link_tap(driver) -> dict:
    return dispatch_synthetic_tap(driver, selectors.DOWNLOAD_HTML_LINK)


@allure.step("Then фикстурный <button> получил data-tapped=\"1\"")
def assert_tap_zone_button_tapped(driver) -> None:
    assert_tap_marker_tapped(driver, selectors.TAP_ZONE_BUTTON)


@allure.step("Then фикстурный <div> получил data-tapped=\"1\"")
def assert_tap_zone_div_tapped(driver) -> None:
    assert_tap_marker_tapped(driver, selectors.TAP_ZONE_DIV)


# TC-118 (TEST_BUG fix, test-maintainer, 2026-08-11, runs/RUN-20260811-0405.md):
# `open_live_listing` возвращает голову самой волатильной живой ленты AO3
# («Latest Works») — работа за id может быть удалена/скрыта между скрапом
# листинга и навигацией на её work-страницу, AO3 в этом случае штатно отдаёт
# 404. Лёгкая (БЕЗ подсчёта onclick-кандидатов, БЕЗ исключения при неудаче)
# проверка того же двойного якоря идентичности документа, что финальный ассерт
# ниже (`pathname` + `WORK_PAGE_CONTENT_MARKERS`) — используется
# `rating_steps.open_live_work_page` для перебора кандидатов ленты: пробует
# каждого по очереди, пока не найдёт реально живую work-страницу.
def probe_live_work_page_identity(driver) -> dict:
    """Возвращает `{"pathname", "title", "has_content_marker", "is_live"}` —
    `is_live` истинен ТОЛЬКО когда pathname матчит `^/works/\\d` (симметрично
    guard'у `ao3_bridge.js:1154`) И присутствует хотя бы один узел реального
    контента work-страницы (`selectors.WORK_PAGE_CONTENT_MARKERS`, те же узлы,
    что читает сам `ao3_bridge.js:1139-1142`). `title` — `document.title`
    страницы, диагностический сигнал, отличающий класс нештатной страницы
    (штатная AO3 404 несёт `"404 Error | Archive of Our Own"` в title;
    Cloudflare-интерстишл — `"Just a moment..."`) — не используется для
    решения `is_live` (оба класса одинаково "не живые"), только для
    последующей диагностики вызывающим кодом."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: d.execute_script("return document.readyState;") == "complete",
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="work-страница не завершила загрузку (readyState != complete)",
        )
        result = driver.execute_script(
            "return {pathname: window.location.pathname, "
            "        title: document.title, "
            "        hasContentMarker: !!document.querySelector(arguments[0])};",
            selectors.WORK_PAGE_CONTENT_MARKERS,
        )
    pathname = result["pathname"]
    has_content_marker = bool(result["hasContentMarker"])
    is_live = bool(re.match(r"^/works/\d", pathname)) and has_content_marker
    return {
        "pathname": pathname,
        "title": result["title"],
        "has_content_marker": has_content_marker,
        "is_live": is_live,
    }


def _diagnose_non_live_page(title: str) -> str:
    """TC-118 root_cause (`runs/RUN-20260811-0405.md`): прежняя диагностика
    безусловно предполагала Cloudflare-интерстишл, хотя реальной причиной чаще
    оказывается штатная страница AO3 «Error 404» (работа удалена/скрыта) —
    разные классы, требующие разного триажа. Классифицирует ПО title страницы,
    не гадает; неопознанный title называется явно, не подгоняется под один из
    известных классов."""
    if "404" in title:
        return f"штатная страница ошибки AO3 (404), title={title!r}"
    if "just a moment" in title.lower():
        return f"вероятен Cloudflare bot-check интерстишл (R-03), title={title!r}"
    return f"неопознанная нештатная страница, title={title!r}"


# TC-118: числовая проба ПРЕДПОСЫЛКИ guard'а тап-зон на живой work-странице
# (bridge-tap-zone-guard, docs/01 §9 «Дополнение области», доработка attempt 2
# B1/B2). ЕДИНЫЙ предикат, симметричный `ao3_bridge.js:1155` (не два изолированных
# подсчёта тега/role) — селектор whitelist переиспользован из
# `selectors.TAP_ZONE_GUARD_WHITELIST`, не продублирован строкой здесь.
@allure.step("Then подсчитаны узлы тела work-страницы вне whitelist guard'а тап-зон с собственным атрибутным [onclick] (симметрично ao3_bridge.js:1155)")
def assert_no_non_whitelisted_onclick_candidates(driver) -> int:
    """TC-118: `Array.from(document.body.querySelectorAll('[onclick]')).filter(n =>
    !n.closest(whitelist))` — единственная граница валидности: видит ТОЛЬКО
    атрибутные `onclick`, не `addEventListener`/jQuery-обработчики (см. TC-118
    Then/B3, решено владельцем 2026-07-28 — критерий сохранён с сужением до
    этого класса). Возвращает N; при N > 0 узлы (первые 200 символов
    `outerHTML` каждого) вложены в Allure как находка ДЛЯ test-strategist
    (пере-оценка §5) — этот кейс баг по числу не заводит (non-goal, см. Then).

    Доработка attempt 2 (критик-вход): N=0 сам по себе НЕ доказывает, что
    открытая страница — реальная work-страница с контентом (Cloudflare-
    интерстишл на том же `readyState=complete` тоже не содержит атрибутных
    onclick вне whitelist — N=0 неотличим от «измерена пустота»). В том же
    `execute_script` дополнительно снимаются два позитивных якоря
    идентичности документа ДО ассерта count == 0: `location.pathname` (обязан
    матчить `^/works/\\d`, симметрично guard'у `ao3_bridge.js:1154`) и
    наличие хотя бы одного узла реального контента work-страницы
    (`selectors.WORK_PAGE_CONTENT_MARKERS` — те же узлы, что читает сам
    `ao3_bridge.js:1139-1142` для скрапинга метаданных). Оба поля вложены в
    тот же Allure-аттач, что и count, для аудита."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: d.execute_script("return document.readyState;") == "complete",
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="work-страница не завершила загрузку (readyState != complete) — "
                    "подсчёт кандидатов вне whitelist guard'а не выполнить надёжно",
        )
        result = driver.execute_script(
            "return (function(whitelist, contentMarkers) {"
            "  var nodes = Array.from(document.body.querySelectorAll('[onclick]'))"
            "    .filter(function(n) { return !n.closest(whitelist); });"
            "  return {pathname: window.location.pathname, "
            "          title: document.title, "
            "          hasContentMarker: !!document.querySelector(contentMarkers), "
            "          count: nodes.length, "
            "          details: nodes.map(function(n) { return n.outerHTML.slice(0, 200); })};"
            "})(arguments[0], arguments[1]);",
            selectors.TAP_ZONE_GUARD_WHITELIST,
            selectors.WORK_PAGE_CONTENT_MARKERS,
        )
    pathname = result["pathname"]
    title = result["title"]
    has_content_marker = bool(result["hasContentMarker"])
    count = int(result["count"])
    allure.attach(
        f"pathname={pathname!r} title={title!r} has_content_marker={has_content_marker} "
        f"count={count} details={result['details']!r}",
        name="tc-118-non-whitelisted-onclick-candidates",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert re.match(r"^/works/\d", pathname), (
        f"pathname={pathname!r} не соответствует ^/works/\\d — открыта НЕ work-страница "
        f"(guard тап-зон тоже проверяет только этот паттерн, ao3_bridge.js:1154); "
        f"N={count} неинтерпретируем без этого якоря идентичности документа "
        f"({_diagnose_non_live_page(title)})"
    )
    assert has_content_marker, (
        f"на странице pathname={pathname!r} не найдено ни одного узла реального контента "
        f"work-страницы ({selectors.WORK_PAGE_CONTENT_MARKERS!r}) — {_diagnose_non_live_page(title)}; "
        f"N={count} НЕ является доказательством отсутствия кандидатов, т.к. измерена "
        f"пустая/нештатная страница, а не реальная work-страница. TC-118 root_cause "
        f"(runs/RUN-20260811-0405.md): вызывающий код обязан пройти через "
        f"`rating_steps.open_live_work_page` (перебор кандидатов с фолбэком) ДО этого "
        f"ассерта — если он всё же сработал, значит либо фолбэк не был применён, либо "
        f"страница деградировала МЕЖДУ проверкой фолбэка и этим вызовом (гонка, не тот "
        f"же класс, что исходный root_cause)"
    )
    assert count == 0, (
        f"найдено {count} узл(ов) вне whitelist guard'а тап-зон с собственным "
        f"атрибутным onclick на живой work-странице ({result['details']!r}) — "
        f"предпосылка риска R-02 (guard-пробой, ao3_bridge.js:1155) предъявлена; "
        f"баг по этому числу этим кейсом НЕ заводится (non-goal) — находка "
        f"передаётся test-strategist'у на пере-оценку §5 docs/01-test-strategy.md"
    )
    return count


@allure.step("Then верхняя полоса экрана НЕ потемнела относительно baseline (toggleFullscreen НЕ вызван)")
def assert_top_chrome_not_darkened(
    driver, baseline: float, ratio: float = 0.5, timeout: int = 10, poll_interval: float = 0.3,
) -> None:
    """Негативная сверка TC-119/TC-122 — доработка S-1 (attempt 2, критик-вход
    B4): бюджет ТЕПЕРЬ СИММЕТРИЧЕН позитивной `assert_top_chrome_darkened` (тот
    же `timeout=10`, не короткая settle-пауза с одним чтением). `wait_until`,
    опрашивающий условие ДО достижения порога, тут неприменим (условие «не
    потемнело» уже истинно с первого кадра, опрос завершился бы мгновенно,
    ничего не гарантируя про поведение ПОСЛЕ клика) — вместо этого опрашиваем
    ВЕСЬ бюджет через `assert_holds_for` (батч мелочей D-0081, 2026-07-29:
    ручная реализация обобщена в примитив `framework.core.waits.assert_holds_for`)
    и assert'им, что порог потемнения НЕ пересекается НИ РАЗУ за всё окно, в
    котором мог бы случиться анимированный fullscreen-reflow (прежняя редакция
    читала luma только один раз после короткой паузы 1.5с — пропускала более
    позднее пересечение порога в оставшиеся ~8.5с бюджета позитивной проверки)."""
    threshold = baseline * ratio

    def check() -> bool:
        luma = BrowserScreen(driver).top_chrome_avg_luma()
        assert luma >= threshold, (
            f"верхняя полоса потемнела (luma={luma:.1f} < baseline*{ratio}={threshold:.1f}) "
            f"после тапа — toggleFullscreen, похоже, был вызван, хотя guard должен был его подавить"
        )
        return True

    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg=f"верхняя полоса потемнела относительно baseline*{ratio}",
    )


# --- TC-126/TC-127/TC-128: reading-UX tap-зоны (`ao3_bridge.js:1149-1164`,
# browse-tap-to-scroll/browse-tap-fullscreen) — верхняя/нижняя треть скроллят,
# средняя переключает fullscreen. Узел 3 AT-BUG-030 (высота документа >=
# 3×innerHeight) уже присутствует во всех потребителях `render_work_page_html`
# (в т.ч. `work_with_download.mitm`, общем с TC-032/033/119/120/122).

@allure.step("Then текущий window.innerHeight страницы AO3 в WebView измерен")
def get_webview_inner_height(driver) -> int:
    with contexts.in_webview(driver):
        return int(driver.execute_script("return window.innerHeight;") or 0)


@allure.step("Then WebView-контекст отдаёт ненулевые размеры вьюпорта (готов к execute_script)")
def wait_webview_viewport_ready(driver, timeout: int | None = None) -> int:
    """TC-125: после `am force-stop` + relaunch `wait_ao3_loaded` (current_url
    содержит `archiveofourown.org`) может стать истинным РАНЬШЕ, чем
    свежепересозданный после смерти процесса `android.webkit.WebView` реально
    заляжет в layout — `webview_name()` (`framework/core/contexts.py`) берёт
    ПЕРВЫЙ контекст, содержащий `WEBVIEW`, из `driver.contexts`, без гарантии,
    что это именно полностью отрисованный instance; наблюдался `innerHeight ==
    innerWidth == 0` (`document.elementFromPoint(0, 0)` промахивается мимо
    любого узла) сразу после `wait_ao3_loaded`, хотя `current_url` уже был
    верным. Опрашивает (не читает один раз) `window.innerHeight`, пока не
    станет > 0 — тот же класс WEBVIEW-round-trip латентности, что остальные
    опросы этого модуля."""
    def _ready(_d):
        with contexts.in_webview(_d):
            return int(_d.execute_script("return window.innerHeight;") or 0) > 0

    wait_until(
        driver, _ready, timeout=timeout,
        message="WebView не отдал ненулевой innerHeight после relaunch — контекст ещё не готов",
    )
    return get_webview_inner_height(driver)


@allure.step(
    "When синтетически тапнута точка вьюпорта на высоте {y_fraction}×innerHeight "
    "(X — центр ширины, целевой DOM-узел — document.elementFromPoint)"
)
def dispatch_synthetic_viewport_tap(driver, y_fraction: float) -> dict:
    """Тап по ГЕОМЕТРИЧЕСКОЙ координате вьюпорта, не по конкретному CSS-селектору
    (в отличие от `dispatch_synthetic_tap` узлов 1/2 AT-BUG-030): `clientX`/
    `clientY` вычисляются из ТЕКУЩЕГО `innerWidth`/`innerHeight` НЕПОСРЕДСТВЕННО
    перед диспатчем (обязательно для TC-128 — `innerHeight` меняется между
    входом/выходом fullscreen, см. заметки кейса про пересчёт координаты перед
    КАЖДЫМ тапом), целевой узел находится через `document.elementFromPoint(clientX,
    clientY)` — та же связка hit-testing'а, что браузер использует для реального
    клика пользователя, поэтому guard (`e.target.closest(...)`, `ao3_bridge.js:1152`)
    видит РЕАЛЬНЫЙ узел под точкой, а не хардкод. Это верно только про
    hit-testing (выбор узла-цели), НЕ про источник самого события: как и
    `dispatch_synthetic_tap` (см. докстринг AT-BUG-030 выше), это синтетический
    `MouseEvent`/`dispatchEvent`, не Selenium `.click()`/физический нативный тап
    — `dispatchEvent` бьёт напрямую в JS-обработчик `ao3_bridge.js`, минуя
    нативный Android touch-стек.

    Узлы 1/2 AT-BUG-030 (`<button>`/`<div onclick>`) стоят в узкой колонке
    `left:24px; width:200px` — центр вьюпорта по X (`innerWidth/2 ≈ 490px` на
    эталонном AVD, CH-005:603) далеко за их правой границей (224px), поэтому
    тап по центральной колонке X всегда промахивается мимо этих узлов
    независимо от Y и от текущей scroll-позиции — целевым узлом в точке
    оказывается неинтерактивный узел филлера (узел 3,
    `render_reading_ux_filler_html`: `<div>`-обёртка или вложенный `<p>`,
    эмпирически замечены оба тега в разных точках), вне whitelist guard'а."""
    with contexts.in_webview(driver):
        result = driver.execute_script(
            "var innerHeight = window.innerHeight;"
            "var innerWidth = window.innerWidth;"
            "var clientX = innerWidth / 2;"
            "var clientY = innerHeight * arguments[0];"
            "var target = document.elementFromPoint(clientX, clientY);"
            "if (!target) {"
            "  return {found: false, innerHeight: innerHeight, innerWidth: innerWidth, "
            "clientX: clientX, clientY: clientY};"
            "}"
            "var ev = new MouseEvent('click', {bubbles: true, cancelable: true, "
            "clientX: clientX, clientY: clientY, view: window});"
            "var interactive = !!target.closest('a, button, input, select, textarea, "
            "label, summary, [role=\"button\"]');"
            "target.dispatchEvent(ev);"
            "return {found: true, innerHeight: innerHeight, innerWidth: innerWidth, "
            "clientX: clientX, clientY: clientY, tagName: target.tagName, "
            "interactive: interactive};",
            y_fraction,
        )
    assert result.get("found"), (
        f"document.elementFromPoint не нашёл узел на координате "
        f"({result['clientX']:.1f}, {result['clientY']:.1f}) — тап не может быть диспатчен"
    )
    allure.attach(
        f"y_fraction={y_fraction:.3f} innerHeight={result['innerHeight']} "
        f"innerWidth={result['innerWidth']} clientX={result['clientX']:.1f} "
        f"clientY={result['clientY']:.1f} target_tag={result['tagName']!r} "
        f"interactive={result.get('interactive')!r}",
        name="viewport-tap-dispatch-geometry",
        attachment_type=allure.attachment_type.TEXT,
    )
    return result


# Середина каждой трети — запас от границ (1/3, 2/3), не пограничное значение.
_TAP_ZONE_TOP_THIRD_FRACTION = 1 / 6
_TAP_ZONE_BOTTOM_THIRD_FRACTION = 5 / 6
_TAP_ZONE_MIDDLE_FRACTION = 0.5


@allure.step("When пользователь тапает по верхней трети экрана work-страницы (tap-to-scroll)")
def dispatch_tap_to_scroll_up_tap(driver) -> dict:
    return dispatch_synthetic_viewport_tap(driver, _TAP_ZONE_TOP_THIRD_FRACTION)


@allure.step("When пользователь тапает по нижней трети экрана work-страницы (tap-to-scroll)")
def dispatch_tap_to_scroll_down_tap(driver) -> dict:
    return dispatch_synthetic_viewport_tap(driver, _TAP_ZONE_BOTTOM_THIRD_FRACTION)


@allure.step("When пользователь тапает по средней трети (центру вьюпорта) work-страницы (toggle fullscreen)")
def dispatch_tap_zone_fullscreen_toggle_tap(driver) -> dict:
    return dispatch_synthetic_viewport_tap(driver, _TAP_ZONE_MIDDLE_FRACTION)


@allure.step(
    "Given work-страница предварительно проскроллена вниз (execute_script), "
    "чтобы scrollY > 0.95×innerHeight (предпосылка TC-126)"
)
def prescroll_past_tap_to_scroll_threshold(driver, margin_ratio: float = 1.5) -> tuple[int, int]:
    """TC-126, «Заметки для автоматизации»: `execute_script("window.scrollTo(...)")`
    — дешевле и не создаёт зависимости TC-126 от TC-127 (тап по нижней трети как
    альтернативный способ предскролла). `innerHeight` читается заново
    непосредственно перед `scrollTo` (дешёвый детерминированный расчёт, не
    хардкод под конкретный AVD); `margin_ratio=1.5` даёт `scrollY` существенно
    выше порога `0.95×innerHeight`, но безопасно ниже максимума скролла
    документа (узел 3 AT-BUG-030 — высота >= 3×innerHeight — даёт запас).
    Возвращает (scrollY после предскролла, innerHeight)."""
    inner_height = get_webview_inner_height(driver)
    target_px = int(inner_height * margin_ratio)
    scroll_webview_to(driver, target_px)
    scroll_after = get_webview_scroll_y(driver)
    threshold = 0.95 * inner_height
    assert scroll_after > threshold, (
        f"предскролл не превысил порог 0.95×innerHeight={threshold:.1f}: "
        f"scrollY={scroll_after} после scrollTo({target_px}px) — Given TC-126 не выполнен"
    )
    return scroll_after, inner_height


_TAP_TO_SCROLL_DELTA_RATIO = 0.95
# Допуск на округление/анимацию — сама дельта детерминирована (`behavior:
# 'instant'`), но клампинг у границ документа/округление float в JS дают
# небольшой люфт; 15% от ожидаемой дельты — щедрый запас без риска пропустить
# реальную регрессию величины скролла.
_TAP_TO_SCROLL_DELTA_TOLERANCE_RATIO = 0.15


@allure.step(
    "Then window.scrollY изменился примерно на {direction}×0.95×innerHeight "
    "относительно scrollY до тапа ({scroll_before})"
)
def assert_tap_to_scroll_delta(
    driver, scroll_before: int, inner_height: int, direction: int, timeout: int = 5,
) -> int:
    """TC-126 (direction=-1, тап по верхней трети)/TC-127 (direction=+1, тап по
    нижней трети) — измерение CH-005 (`dy ≈ ±1710` при `innerHeight=1800`,
    `0.95×1800=1710`). Опрашивает (не читает один раз) — тот же класс
    WEBVIEW-round-trip латентности, что остальные опросы этого модуля.

    AT-BUG-039 (тот же класс, что `AT-BUG-036` attempt 2 —
    `app_steps.wait_persisted_tab_count`): диагностика при таймауте обязана
    нести последнее РЕАЛЬНО НАБЛЮДЁННОЕ внутри опроса значение `scrollY`, не
    свежий вызов ДО/ПОСЛЕ ожидания — `message=` вычислялся бы до входа в
    `wait_until`, замораживая устаревшее значение под подписью «текущий».
    `holder` заполняется ВНУТРИ предиката на каждом опросе; при таймауте
    `TimeoutException` от `wait_until` перехватывается и переброшен заново с
    сообщением, дополненным `holder["scroll_y"]` — последним, что видел сам
    опрос."""
    expected_delta = direction * _TAP_TO_SCROLL_DELTA_RATIO * inner_height
    tolerance_px = abs(expected_delta) * _TAP_TO_SCROLL_DELTA_TOLERANCE_RATIO

    holder: dict[str, int] = {}

    def _matches(d):
        holder["scroll_y"] = get_webview_scroll_y(d)
        actual_delta = holder["scroll_y"] - scroll_before
        return abs(actual_delta - expected_delta) <= tolerance_px

    try:
        wait_until(
            driver, _matches, timeout=timeout,
            message=(
                f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
                f"(±{tolerance_px:.1f}px) относительно scrollY до тапа={scroll_before} "
                f"за {timeout}с"
            ),
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
            f"(±{tolerance_px:.1f}px) относительно scrollY до тапа={scroll_before} "
            f"за {timeout}с (последнее наблюдённое внутри опроса scrollY="
            f"{holder.get('scroll_y')})"
        ) from exc
    return get_webview_scroll_y(driver)


_VOLUME_PAGE_SCROLL_RATIO = 0.9
# AT-BUG-072/TC-252: `BrowserViewModel.scrollActivePageBy` — `window.scrollBy(0,
# Math.round(window.innerHeight*0.9)*direction)` — множитель 0.9, НЕ 0.95 как у
# `_TAP_TO_SCROLL_DELTA_RATIO` выше: разные механизмы (volume-button paging vs
# tap-to-scroll), совпадение множителя не гарантировано и не проверено.
_VOLUME_PAGE_SCROLL_TOLERANCE_RATIO = 0.15


@allure.step(
    "Then window.scrollY изменился примерно на {direction}×0.9×innerHeight "
    "относительно scrollY до нажатия клавиши громкости ({scroll_before})"
)
def assert_volume_page_scroll_delta(
    driver, scroll_before: int, inner_height: int, direction: int, timeout: int = 5,
) -> int:
    """TC-252 (AT-BUG-072) — параллельная структура `assert_tap_to_scroll_delta`
    выше (TC-126/127): тот же приём опроса (не одноразовое чтение) и той же
    диагностики при таймауте (последнее РЕАЛЬНО НАБЛЮДЁННОЕ внутри опроса
    значение `scrollY`, AT-BUG-039-класс), но множитель `_VOLUME_PAGE_
    SCROLL_RATIO=0.9` (`BrowserViewModel.scrollActivePageBy`), не 0.95 —
    разные JS-вызовы (`MainActivity.volumePageHandler` -> `evalJs`, не
    `ao3_bridge.js` tap-хэндлер), значения множителей независимы."""
    expected_delta = direction * _VOLUME_PAGE_SCROLL_RATIO * inner_height
    tolerance_px = abs(expected_delta) * _VOLUME_PAGE_SCROLL_TOLERANCE_RATIO

    holder: dict[str, int] = {}

    def _matches(d):
        holder["scroll_y"] = get_webview_scroll_y(d)
        actual_delta = holder["scroll_y"] - scroll_before
        return abs(actual_delta - expected_delta) <= tolerance_px

    try:
        wait_until(
            driver, _matches, timeout=timeout,
            message=(
                f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
                f"(±{tolerance_px:.1f}px) относительно scrollY до нажатия={scroll_before} "
                f"за {timeout}с"
            ),
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"scrollY не изменился на ожидаемую дельту {expected_delta:.1f}px "
            f"(±{tolerance_px:.1f}px) относительно scrollY до нажатия={scroll_before} "
            f"за {timeout}с (последнее наблюдённое внутри опроса scrollY="
            f"{holder.get('scroll_y')})"
        ) from exc
    return get_webview_scroll_y(driver)


# --- TC-123: tap_to_scroll=OFF — негативный инвариант (ни одна треть work-страницы
# не производит эффекта). Единственный гейт `ao3_bridge.js:1153`
# (`if (!window.__ao3TapToScroll) return;`) применяется ДО вычисления координаты
# тапа, поэтому предскролл/negative-Then общие для всех трёх третей.

@allure.step(
    "Given work-страница предварительно проскроллена к позиции scrollY ≈ innerHeight "
    "(строго не у края — предпосылка негативного инварианта TC-123)"
)
def prescroll_to_tap_zone_invariant_position(driver) -> int:
    """TC-123: `S ≈ innerHeight`, строго внутри окна `(0.95×innerHeight, maxScroll −
    0.95×innerHeight)` (`maxScroll = document.documentElement.scrollHeight - innerHeight`) —
    иначе негативный Then («scrollY не меняется») был бы истинен и при
    КОРРЕКТНО работающем гейте, и при СЛОМАННОМ: `scrollBy` от сломанного
    (пропускающего) гейта клампился бы браузером обратно к границе (0 или
    maxScroll), неотличимо от «гейт сработал» (см. TC-123 предусловия). Узел 3
    AT-BUG-030 (высота документа >= 3×innerHeight) гарантирует
    `maxScroll >= 2×innerHeight`, поэтому `innerHeight` всегда лежит в
    допустимом окне с запасом. Возвращает фактический `scrollY` после
    предскролла — окно сверяется собственным assert'ом, а не предполагается."""
    with contexts.in_webview(driver):
        metrics = driver.execute_script(
            "return {innerHeight: window.innerHeight, "
            "scrollHeight: document.documentElement.scrollHeight};"
        )
    inner_height = int(metrics["innerHeight"])
    max_scroll = int(metrics["scrollHeight"]) - inner_height
    target_px = round(inner_height)
    scroll_webview_to(driver, target_px)
    scroll_after = get_webview_scroll_y(driver)
    low = 0.95 * inner_height
    high = max_scroll - 0.95 * inner_height
    allure.attach(
        f"S={scroll_after} innerHeight={inner_height} maxScroll={max_scroll} "
        f"window=({low:.1f}, {high:.1f})",
        name="tap-zone-prescroll-geometry",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert low < scroll_after < high, (
        f"предскролл scrollY={scroll_after} (target={target_px}) не попал строго "
        f"внутрь окна ({low:.1f}, {high:.1f}) при innerHeight={inner_height}, "
        f"maxScroll={max_scroll} — негативный Then TC-123 был бы неотличим от "
        f"клампа к границе скролла"
    )
    return scroll_after


@allure.step("Then window.scrollY остаётся равным {expected} (тап не произвёл эффекта, tap_to_scroll=OFF)")
def assert_scroll_unchanged(driver, expected: int, timeout: int = 5, poll_interval: float = 0.3) -> None:
    """TC-123: негативная сверка, симметричная `assert_top_chrome_not_darkened` —
    опрашивает ВЕСЬ бюджет через `assert_holds_for`, а не читает `scrollY` один
    раз сразу после тапа (тот же класс: условие «не изменился» уже истинно с
    первого кадра, одноразовое чтение не отличило бы «гейт корректно подавил
    эффект» от «эффект ещё не докатился» — держим негатив на всём бюджете)."""
    def check() -> bool:
        actual = get_webview_scroll_y(driver)
        assert actual == expected, (
            f"scrollY изменился: было {expected}, стало {actual} — тап произвёл эффект, "
            f"хотя tap_to_scroll=OFF должен был подавить весь обработчик "
            f"(ao3_bridge.js:1153, единый ранний return ДО вычисления третьей тапа)"
        )
        return True
    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg=f"scrollY отклонился от ожидаемого {expected} (tap_to_scroll=OFF)",
    )


# --- TC-124: позитивный якорь пересоздания документа (rework attempt 2,
# критик-вход B2'). `tap_to_scroll` синхронизируется с живым WebView ДВУМЯ
# путями — реактивным push на уже открытую вкладку (`LaunchedEffect(tapToScroll)`,
# BrowserScreen.kt:187-192, `evaluateJavascript`, БЕЗ reload/навигации) и
# реинъекцией при (пере)загрузке (`onPageFinished`, BrowserScreen.kt:603). Без
# независимого от самого тумблера сигнала эти два пути неотличимы: наблюдаемый
# эффект тапа («страница скроллится») одинаков в обоих случаях. Маркер —
# JS-поле на `window` ТЕКУЩЕГО документа: `reload()`/навигация пересоздают
# `window` с нуля (маркер исчезает), `evaluateJavascript` на уже загруженный
# документ его не трогает (маркер переживает) — то же различение, что
# `assert_active_tab_url`/`assert_scroll_restored` делают для других гонок
# этого модуля, только для факта «документ пересоздан», а не значения стейта.

@allure.step("Given документ WebView помечен уникальным маркером идентичности")
def mark_document_identity(driver) -> str:
    """Возвращает маркер — вызывающий код сверяет его тем же значением через
    `assert_document_identity_preserved`/`wait_document_identity_changed`."""
    marker = str(uuid.uuid4())
    with contexts.in_webview(driver):
        driver.execute_script("window.__ao3TestDocMarker = arguments[0];", marker)
    allure.attach(
        marker, name="document-identity-marker-set", attachment_type=allure.attachment_type.TEXT,
    )
    return marker


def _read_document_identity_marker(driver):
    with contexts.in_webview(driver):
        return driver.execute_script("return window.__ao3TestDocMarker;")


@allure.step(
    "Then документ WebView НЕ пересоздавался — маркер идентичности сохранился "
    "({prev_marker})"
)
def assert_document_identity_preserved(
    driver, prev_marker: str, timeout: int = 5, poll_interval: float = 0.3,
) -> None:
    """TC-124 (сценарий live-push): позитивно доказывает, что наблюдаемый
    эффект тапа применился именно реактивным push (`LaunchedEffect(tapToScroll)`)
    к уже открытому документу, а не переинъекцией при загрузке — без этого
    ассерта сценарий «без reload» структурно неотличим от «reload произошёл
    незаметно» (симметрично `assert_scroll_unchanged` — опрашивает весь
    бюджет, а не читает один раз сразу после действия)."""
    def check() -> bool:
        actual = _read_document_identity_marker(driver)
        assert actual == prev_marker, (
            f"маркер идентичности документа изменился: было {prev_marker!r}, стало "
            f"{actual!r} — документ WebView был пересоздан (неожиданный reload/"
            f"навигация), хотя сценарий этого не предполагает"
        )
        return True
    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg=f"маркер идентичности документа отклонился от {prev_marker!r}",
    )


@allure.step(
    "Then документ WebView пересоздан — маркер идентичности исчез (reload "
    "завершён)"
)
def wait_document_identity_changed(driver, prev_marker: str, timeout: int | None = None) -> None:
    """TC-124 (сценарий theme-reload): точка синхронизации ПЕРЕД любым
    дальнейшим взаимодействием со страницей (предскролл/тап) — опрашивает
    маркер, пока `reload()` (BrowserScreen.kt `LaunchedEffect(darkTheme)`) не
    пересоздаст документ и не сотрёт его. Служит одновременно (а) позитивным
    доказательством, что reload реально произошёл (не только «тумблер всё ещё
    ON», что могло бы быть истинно и без reload), и (б) гарантией, что
    последующие `execute_script`-чтения видят уже финальный, полностью
    пересозданный документ, а не устаревшее состояние старого (класс B2':
    без этой точки синхронизации предскролл мог начаться ДО завершения
    reload и оперировать над уже неактуальным scrollY)."""
    wait_until(
        driver,
        lambda d: _read_document_identity_marker(d) != prev_marker,
        timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
        message=(
            f"документ WebView не пересоздался за отведённый бюджет — маркер "
            f"идентичности остаётся {prev_marker!r}, reload от смены темы, похоже, "
            f"не произошёл"
        ),
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


@allure.step("Then текущий URL активной вкладки Browse прочитан")
def get_active_tab_url(driver) -> str:
    with contexts.in_webview(driver):
        return driver.current_url or ""


# --- TC-103 (security/file-access): встроенная в скачанный файл ссылка на
# internal-путь вне директории загрузок — негативный/граничный случай, ∩ TC-034 ---

@allure.step("When внутри открытого локального файла нажата тестовая ссылка probe-link")
def click_probe_link(driver) -> None:
    """Клик через JS DOM API (не Selenium `.click()`) — тот же приём, что
    `tap_rate_button` (TC-072/074/076): не требует геометрической интерактивности,
    достаточно скроллнуть элемент в область видимости перед кликом."""
    with contexts.in_webview(driver):
        link = DownloadedWorkPage(driver).probe_link()
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", link,
        )


@allure.step("Then WebView не отображает содержимое целевого файла как успешно загруженную страницу")
def assert_file_link_navigation_blocked_or_empty(
    driver, original_url: str, timeout: int = 10,
) -> None:
    """TC-103: после клика по `probe-link` (файл вне `_DOWNLOAD_FIXTURE_REL_DIR`)
    Then кейса допускает ЛЮБОЙ из трёх исходов — навигация не состоялась (URL не
    изменился), показана ошибка загрузки (включая кастомную error page приложения,
    TC-046 — `about:blank` base URL + заголовок «Couldn't load this page»), либо
    пустой результат (WebView НЕ отрисовал непустое содержимое целевого файла).
    НЕ проверяет единственный конкретный исход — какой из трёх сработает,
    зависит от реального поведения WebView/ОС для конкретного целевого файла
    (не задокументировано заранее, testability gap TC-103.md)."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: d.execute_script("return document.readyState;") == "complete",
            timeout=timeout,
            message="WebView не стабилизировался (readyState != complete) после клика "
                    "по probe-link",
        )
        current_url = driver.current_url or ""
        body_text = driver.execute_script(
            "return (document.body && document.body.innerText) || '';"
        ) or ""
    same_url = current_url.rstrip("/") == original_url.rstrip("/")
    is_custom_error_page = current_url == "about:blank" and "Couldn't load this page" in body_text
    is_empty = body_text.strip() == ""
    allure.attach(
        f"original_url={original_url!r} current_url={current_url!r} "
        f"body_text_len={len(body_text)} same_url={same_url} "
        f"is_custom_error_page={is_custom_error_page} is_empty={is_empty}",
        name="tc103-file-link-navigation-observation",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert same_url or is_custom_error_page or is_empty, (
        f"клик по probe-link привёл к успешно отображённой странице целевого файла: "
        f"current_url={current_url!r}, {len(body_text)} символов непустого текста в "
        f"body — открытие скачанного контента дало доступ к произвольному internal-"
        f"файлу приложения по клику на встроенную ссылку"
    )


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


@allure.step("Then URL активной вкладки держит {url} стабильно {budget_s}с (не удваивается/не меняется отложенно)")
def assert_active_tab_url_holds(driver, url: str, budget_s: float = 5.0, poll_interval: float = 0.4) -> None:
    """TC-183 (rework attempt 2, критик-вход B2, доработка (б)): негативный
    Then «queryString НЕ дописан второй раз» читался ОДНИМ снимком через
    `assert_active_tab_url` — условие «URL == LISTING_FILTERED_URL» уже истинно
    С ПЕРВОГО КАДРА (вкладка была на этом URL ещё ДО When), `wait_until`
    вернулся бы мгновенно, ничего не гарантируя про отложенный второй
    `loadUrl()` внутри `view.post {}` (`BrowserScreen.kt:626` — колбэк САМ
    откладывает повторную загрузку на следующий цикл message loop). Опрашивает
    ВЕСЬ бюджет через `assert_holds_for` — тот же приём, что
    `assert_top_chrome_not_darkened`/`assert_kudo_submit_click_count_holds`."""
    with contexts.in_webview(driver):
        target = url.rstrip("/")

        def check() -> bool:
            actual = (driver.current_url or "").rstrip("/")
            assert actual == target, (
                f"URL активной вкладки изменился на {actual!r}, ожидали стабильно {url!r} "
                f"весь бюджет {budget_s}с — похоже на повторное срабатывание перехвата"
            )
            return True

        assert_holds_for(
            check, budget_s=budget_s, interval_s=poll_interval,
            msg=f"URL активной вкладки не удержал {url} весь бюджет {budget_s}с",
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


@contextlib.contextmanager
def in_webview_at_tab_position(driver, position: int, timeout: int | None = None):
    """AT-BUG-070 (test_debt, Fixed) — адресует WEBVIEW-контекст к вкладке на
    НАТИВНОЙ (0-based) позиции `position`, ЛЮБОЙ — включая `!= 0`, пока
    другие вкладки (в т.ч. вкладка-0) тоже живы, БЕЗ свёртки числа вкладок к
    одной (в отличие от established-приёма reduce-to-one, см. докстринг
    `browser_screen.py::tab_chip_locator`).

    Признак адресации — нативный заголовок чипа вкладки
    (`BrowserScreen.tab_chip_title_at`, источник — `WebChromeClient.
    onReceivedTitle`, ТОТ ЖЕ источник, что `document.title` внутри самой
    страницы) читается ДО входа в WEBVIEW (нативное дерево, sticky-класс
    здесь не участвует), затем матчится против `driver.title` каждого
    `driver.window_handles` (`contexts.in_webview_matching` — общий
    механизм и полная эмпирика в `framework/core/contexts.py`). Это НЕ
    `current_url`-угадывание (критерий готовности AT-BUG-070 явно требует
    другого способа) — заголовок известен ЗАРАНЕЕ из независимого,
    небраузерного источника.

    ВНИМАНИЕ: если несколько вкладок несут одинаковый заголовок (напр. две
    ещё не догрузившиеся вкладки с одинаковым плейсхолдером), матчинг
    бросит `AssertionError` (неоднозначность) — вызывающему коду нужен
    более узкий признак (см. `contexts.in_webview_matching` напрямую с
    собственным предикатом, напр. по известному URL из `open_tabs_urls`)."""
    expected_title = BrowserScreen(driver).tab_chip_title_at(position, timeout=timeout)
    with contexts.in_webview_matching(
        driver,
        lambda url, title: title == expected_title,
        timeout=timeout,
        description=f"tab position {position}, native title={expected_title!r}",
    ) as handle:
        yield handle


@allure.step("Then прочитан URL вкладки на позиции {position} через WEBVIEW-контекст (AT-BUG-070)")
def webview_url_at_tab_position(driver, position: int, timeout: int | None = None) -> str:
    with in_webview_at_tab_position(driver, position, timeout=timeout):
        return driver.current_url


@allure.step("Then выполнен JS `{script}` на вкладке на позиции {position} через WEBVIEW-контекст (AT-BUG-070)")
def execute_script_at_tab_position(driver, position: int, script: str, timeout: int | None = None):
    with in_webview_at_tab_position(driver, position, timeout=timeout):
        return driver.execute_script(script)


@allure.step("Then получен стабильный WEBVIEW-handle вкладки, чей текущий URL — {url} (AT-BUG-070)")
def webview_handle_for_url(driver, url: str, timeout: int | None = None) -> str:
    """AT-BUG-070 — альтернатива `in_webview_at_tab_position` для сценариев, где
    у нескольких вкладок совпадает `document.title` (эмпирически найдено на
    `listing_basic.mitm`: обе фикстурные страницы, отфильтрованная и
    неотфильтрованная, несут ОДИН И ТОТ ЖЕ `<title>` "Test Fixture Listing |
    Archive of Our Own" — title-матчинг там неоднозначен), но известен
    ТЕКУЩИЙ URL цели из НЕ-WebView-оракула (`app_steps.
    assert_persisted_tab_url_at`/`open_tabs_urls` — не `current_url`-
    угадывание). Возвращает handle для повторного адресного использования
    через `contexts.in_webview_handle` — сам URL цели может ИЗМЕНИТЬСЯ
    следующим действием (напр. `navigate_tab_via_page_js_to`), а handle
    остаётся валиден (эмпирически подтверждено, см. `contexts.
    in_webview_handle` докстринг)."""
    with contexts.in_webview_matching(
        driver,
        lambda u, t: u.rstrip("/") == url.rstrip("/"),
        timeout=timeout,
        description=f"tab currently at known url={url!r}",
    ) as handle:
        return handle


@allure.step("When вкладка (handle {handle}) сама переходит на {url} (renderer-initiated, AT-BUG-070)")
def navigate_tab_via_page_js_to(driver, handle: str, url: str, timeout: int | None = None) -> None:
    """AT-BUG-070 — тот же приём, что `navigate_listing_via_page_js`
    (renderer-initiated `window.location.href`, проходит `shouldOverride
    UrlLoading` в отличие от host-initiated `driver.get()`), но явно
    адресован к КОНКРЕТНОЙ вкладке через её ранее захваченный `window_handles`
    handle (`webview_handle_for_url`/`in_webview_at_tab_position`) — не
    активной/sticky вкладке. Нужен для утверждений про НЕ-активные/
    НЕ-нулевые вкладки (напр. TC-207, контраст-дверь Г2 CH-010/BUG-070)."""
    with contexts.in_webview_handle(driver, handle, timeout=timeout):
        driver.execute_script(f"window.location.href = {url!r};")


@allure.step("Then URL вкладки (handle {handle}) стал {url}")
def assert_webview_handle_url(driver, handle: str, url: str, timeout: int | None = None) -> str:
    """AT-BUG-070 — опрашивает URL КОНКРЕТНОЙ вкладки (по стабильному
    handle, не по позиции/заголовку — оба могли смениться отложенной
    навигацией) до совпадения с `url`, тот же класс поллинга, что
    `assert_active_tab_url`, но адресован не к sticky-контексту."""
    def _current(_d):
        with contexts.in_webview_handle(driver, handle, timeout=timeout):
            return driver.current_url

    return wait_until(
        driver,
        lambda d: (u := _current(d)) and u.rstrip("/") == url.rstrip("/") and u,
        timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
        message=f"URL вкладки (handle {handle}) не стал {url!r}",
    )


@allure.step("When открыта листинговая страница (replay-фикстура) {url}")
def open_listing(driver, url: str):
    """Навигация WebView на URL листинга AO3 (replay-запись — см. `conftest.replay`,
    `framework/data/recording_builder.py`). Ждёт появления хотя бы одного блёрба
    работы — сигнал, что bridge (`ao3_bridge.js`) уже прошёлся по DOM и вставил
    Rate-кнопки (`onWorksFound` → `applyRatings`), а не просто что страница ответила
    200."""
    with contexts.in_webview(driver):
        # AT-BUG-025: см. `open_stable_tall_page` — bounded-навигация вместо
        # голого driver.get().
        navigate(driver, url, settings.WEBVIEW_LOAD_TIMEOUT)
        wait_until(
            driver,
            lambda d: len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)) > 0,
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message="листинговая replay-страница не загрузилась (нет блёрбов работ)",
        )


@allure.step("When страница в WebView сама переходит на {url} (window.location.href — renderer-initiated навигация)")
def navigate_listing_via_page_js(driver, url: str) -> None:
    """TC-182/TC-183: `shouldOverrideUrlLoading` (`BrowserScreen.kt:616-631`)
    перехватывает только НАВИГАЦИЮ, ИНИЦИИРОВАННУЮ САМОЙ СТРАНИЦЕЙ (клик по
    ссылке, JS-редирект) — официальная документация Android явно исключает
    навигации, вызванные ХОСТ-приложением напрямую через `loadUrl(String)`
    («This method is not called for internal page navigations, such as calling
    loadUrl(String)»). Красная проба TC-182 (2026-08-14, живой прогон) эмпирически
    подтвердила: `open_listing`/`navigate()` (Selenium `driver.get()`, под капотом —
    chromedriver `Page.navigate`, host-initiated по тому же классу, что и прямой
    `loadUrl()`) НЕ триггерит guard — URL остаётся тем, что был запрошен, дописывания
    queryString не происходит НЕЗАВИСИМО от активного профиля (реальный дефект
    охвата теста, не приложения — `assert_active_tab_url` таймаутил, ожидая
    `LISTING_FILTERED_URL`, реально получая `LISTING_BASIC_URL` без изменений).
    `window.location.href = url`, выполненный ВНУТРИ страницы через
    `execute_script`, — renderer-initiated навигация того же класса, что реальный
    клик по ссылке/JS-редирект, поэтому проходит через `shouldOverrideUrlLoading`
    штатно (в отличие от `settings_steps.reload_active_webview_page`, которая
    нарочно использует `window.location.reload()` — специальный "reload"-тип
    навигации, для которого тот же официальный докстринг Android отдельно
    исключает вызов колбэка: «This method is not called for reload()» — здесь
    нужна ИМЕННО обычная навигация, не reload, поэтому `href`-присваивание, не
    `.reload()`). Годится и для повтора ТОГО ЖЕ URL (TC-183: присваивание
    `location.href` идентичной строке — это НЕ no-op, браузер выполняет полноценную
    повторную навигацию, в отличие от `driver.get()` на тот же URL, см. докстринг
    `reload_active_webview_page` за прецедентом TC-020) — ЭМПИРИЧЕСКИ ПОДТВЕРЖДЕНО
    и, начиная с critic-раунда 4 (блокер B1), ОХРАНЯЕТСЯ ПОСТОЯННЫМ ТЕСТОВЫМ УЗЛОМ
    `test_filter_profiles.py::test_same_url_renderer_navigation_reaches_interceptor`:
    состояние ON, активный профиль, вкладка на `LISTING_BASIC_URL` (без
    `work_search`) -> `navigate_listing_via_page_js(driver, LISTING_BASIC_URL)` (ТОТ
    ЖЕ URL, что уже открыт) -> итоговый URL обязан стать `LISTING_FILTERED_URL`.
    НЕ ссылайся на этот абзац как на источник факта: источник — тот узел, он падает
    при смерти предпосылки (красная проба критика 2026-08-14: подмена When на
    host-initiated `open_listing` роняет узел). Прежде эта строка несла факт ТОЛЬКО
    прозой — одноразовый живой прогон без падающего носителя, что и было блокером
    B1 раунда 3 (см. routing-log, task_id TC-181-185): доставка на ДРУГОЙ URL
    (доказана зелёным TC-182) не доказывает доставку на ТОТ ЖЕ URL, класс «same-URL
    — особый случай» уже ловил этот репозиторий на `driver.get()` (TC-020)."""
    with contexts.in_webview(driver):
        driver.execute_script("window.location.href = arguments[0];", url)
        wait_until(
            driver,
            lambda d: len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)) > 0,
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"страница {url} не загрузилась после JS-навигации window.location.href (нет блёрбов работ)",
        )


@allure.step(
    "When страница в WebView сама повторно переходит на {url} (window.location.href, "
    "с доказательством реальной навигации через staleness старого DOM-узла)"
)
def navigate_listing_via_page_js_proving_reload(driver, url: str) -> None:
    """TC-183 (rework attempt 2, критик-вход B2, доработка (а)): базовая
    `navigate_listing_via_page_js` ждёт `WORK_BLURB>0` ПОСЛЕ JS-навигации — при
    SAME-URL навигации это условие удовлетворяется СТАРЫМ, ещё не заменённым
    DOM (если бы документ по какой-то причине НЕ перезагрузился, старые блёрбы
    остались бы в DOM и `find_elements` нашёл бы именно их) — само по себе не
    доказывает, что документ РЕАЛЬНО перезагрузился, только что блёрбы
    присутствуют (могли быть старыми). Держит ссылку на существующий
    `WORK_BLURB`-узел ДО вызова `window.location.href = url`, затем ждёт, пока
    обращение к НЕЙ не станет `StaleElementReferenceException` — тот же приём,
    что `click_retry` (доказательство ЗАМЕНЫ DOM, не визуального сходства
    нового с прежним) — прежде чем считать блёрбы новой страницы."""
    with contexts.in_webview(driver):
        old_blurb = driver.find_element(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)
        driver.execute_script("window.location.href = arguments[0];", url)
        wait_until(
            driver, lambda d: _is_stale(old_blurb), timeout=10,
            message=f"страница {url} не перезагрузилась после JS-навигации window.location.href "
                    f"(старый DOM-узел work-блёрба остаётся валидным — same-URL навигация могла "
                    f"оказаться no-op)",
        )
        wait_until(
            driver,
            lambda d: len(d.find_elements(AppiumBy.CSS_SELECTOR, selectors.WORK_BLURB)) > 0,
            timeout=settings.WEBVIEW_LOAD_TIMEOUT,
            message=f"страница {url} не загрузилась после JS-навигации window.location.href (нет блёрбов работ)",
        )


@allure.step("When в WebView открыт URL {url} (ждёт полной загрузки документа)")
def open_url_and_wait_ready(driver, url: str, timeout: int | None = None) -> None:
    """Навигация на произвольный URL без ожидания специфичного контента (блёрбов
    и т.п.) — годится и для живой домашней/произвольной страницы AO3 (TC-066), и
    для replay-фикстур без work-блёрбов (TC-067, `ao3_home_smoke.mitm`)."""
    with contexts.in_webview(driver):
        # AT-BUG-025: bounded-навигация — раньше таймаут был навешен только на
        # ПОСЛЕДУЮЩИЙ wait_until (readyState-поллинг), а не на сам driver.get(),
        # который мог зависнуть без load-события и без исключения вовсе.
        navigate(driver, url, timeout or settings.WEBVIEW_LOAD_TIMEOUT)
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
    риску не подвержен — там нет реальной Cloudflare, повторные попытки не нужны.

    AT-BUG-025: раньше `driver.get(url)` на каждой попытке был ничем не ограничен
    (таймаут был только у ПОСЛЕДУЮЩЕГО `wait_until`) — зависание самого вызова
    навигации без load-события съедало весь `total_timeout` (или весь
    `settings.APPIUM_HTTP_TIMEOUT`) уже на первой попытке, не давая ретрай-циклу
    вообще сработать. Теперь `driver.get()` тоже ограничен per-попыточным
    бюджетом (`min(attempt_timeout, remaining)`) через bounded-хелпер `navigate`;
    его таймаут (`navigate()` перехватывает `urllib3.exceptions.ReadTimeoutError`/
    `MaxRetryError` и перебрасывает встроенным `TimeoutError` — см.
    `framework/core/navigate.py`; НИ ОДИН из urllib3-классов сам по себе не
    наследует builtin `TimeoutError`, вопреки более ранней ошибочной записи в
    `bugs/AT-BUG-025.md`) трактуется как неудавшаяся попытка наравне с
    `TimeoutException` от `wait_until`."""
    total_timeout = timeout or settings.WEBVIEW_LOAD_TIMEOUT
    attempt_timeout = 8
    deadline = time.time() + total_timeout
    with contexts.in_webview(driver):
        last_exc: Exception | None = None
        while time.time() < deadline:
            remaining = max(1, int(deadline - time.time()))
            try:
                navigate(driver, url, min(attempt_timeout, remaining))
            except TimeoutError as exc:
                last_exc = exc
                continue
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


# TC-197: баннер над листингом (`selectors.HIDDEN_NOTICE_ID`) — чистая функция
# пары флагов `(ratedHidden, filterActive)`, инжектируется/обновляется
# `ao3_bridge.js::updateHiddenBanner`, вызываемым один раз синхронно в конце
# `ao3BridgeInit` на КАЖДОЙ загрузке страницы. Заметка о нужном методе уже
# была в TC-197.md («Заметки для автоматизации», page-object-доработка по
# образцу TC-092/093/094) — `ListingPage.hidden_banner_text`.
@allure.step("Then над листингом узел баннера скрытых работ показывает ДОСЛОВНО «{expected_text}»")
def assert_hidden_banner_text(driver, expected_text: str, timeout: int | None = None):
    """Опрашивает текст `#ao3-companion-hidden-notice`, не читает один раз — тот же
    класс латентности WEBVIEW round-trip, что `assert_blurb_hidden`, даже несмотря
    на то, что `updateHiddenBanner` сам синхронен относительно остального прохода
    bridge-скрипта."""
    with contexts.in_webview(driver):
        wait_until(
            driver,
            lambda d: ListingPage(d).hidden_banner_text() == expected_text,
            timeout=timeout,
            message=f"узел баннера скрытых работ не показал ожидаемый дословный текст {expected_text!r}",
        )


@allure.step("Then узел баннера скрытых работ #ao3-companion-hidden-notice ОТСУТСТВУЕТ в DOM весь бюджет")
def assert_hidden_banner_absent(driver, timeout: int = 10, poll_interval: float = 0.3):
    """TC-197 вариант D: гейт создания узла (`ratedHidden || filterActive`,
    `ao3_bridge.js:511`) ложен при обоих флагах false. Критик-гейт приёмки
    (2026-08-20): первая редакция опрашивала `wait_until(... is None)` —
    возврат на ПЕРВОМ чтении «отсутствует», тот же класс латентности,
    что AT-BUG-082/083/085 (негативный Then без settle+hold), обоснование
    невакуумности при этом ссылалось на ДРУГИЕ инстансы параметризации
    (варианты A/B/C — другие сессии Appium/навигация), что тайминговой
    гарантии ВНУТРИ инстанса D не давало. Теперь `assert_holds_for` держит
    негатив ВЕСЬ бюджет (симметрично `assert_tab_strip_hidden`), падая на
    ПЕРВОМ появлении узла в любой момент окна — та же форма, что уже
    принята для класса «негатив без settle+hold» в этом файле."""

    def check() -> bool:
        with contexts.in_webview(driver):
            return ListingPage(driver).hidden_banner_text() is None

    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg="узел баннера скрытых работ #ao3-companion-hidden-notice неожиданно "
            "присутствует в DOM (оба флага ratedHidden/filterActive должны быть false)",
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


@allure.step("Then панель фильтра держит «{name}» как активно применённый весь бюджет {budget_s}с (не снимается отложенно)")
def assert_active_filter_shown_holds(driver, name: str, budget_s: float = 5.0, poll_interval: float = 0.4) -> None:
    """TC-185 (rework attempt 2, критик-вход B3): `setActiveFilter(id)`
    (`BrowserViewModel.kt:applyFilter`) ставится ДО навигации, а возможное
    снятие профиля произошло бы ПОЗЖЕ, внутри `onPageLoaded` (после коммита
    URL, см. `BrowserViewModel.kt:501-504`) — одноразовое чтение
    `assert_active_filter_shown` СРАЗУ после действия ловит только состояние
    ДО этого более позднего момента, где мог бы проявиться гипотетический
    дефект (`pendingFilterApplication` не потребился/потребился неверно).
    Опрашивает `filter_dropdown_has_option` ВЕСЬ бюджет через
    `assert_holds_for` (снимок `timeout=0` — мгновенная проверка на каждом
    опросе, тот же приём, что `assert_tab_strip_hidden`/
    `assert_top_chrome_not_darkened`), а не полагается на факт, что условие
    уже истинно в момент вызова."""
    BottomNav(driver).ensure_visible()
    screen = BrowserScreen(driver)

    def check() -> bool:
        assert screen.filter_dropdown_has_option(name, timeout=0), (
            f"панель фильтра перестала показывать «{name}» как активно применённый профиль "
            f"(проверено в пределах бюджета {budget_s}с)"
        )
        return True

    assert_holds_for(
        check, budget_s=budget_s, interval_s=poll_interval,
        msg=f"панель фильтра не удержала «{name}» как активно применённый профиль весь бюджет {budget_s}с",
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
def open_unreachable_url(driver, url: str = UNREACHABLE_URL, timeout: int | None = None) -> None:
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
    error page делает отдельный шаг `assert_error_page_shown`.

    AT-BUG-025: раньше `try/except WebDriverException` гасил только СИНХРОННУЮ
    сетевую ошибку — зависание `driver.get()` БЕЗ исключения (WebView не отдал
    ни `net::ERR`, ни успешную загрузку) не было ничем ограничено. Навигация
    теперь идёт через bounded-хелпер `navigate`; истечение его таймаута —
    встроенный `TimeoutError` (`navigate()` сам перехватывает
    `urllib3.exceptions.ReadTimeoutError`/`MaxRetryError` — НИ ОДИН из них не
    наследует builtin `TimeoutError` сам по себе, см. `framework/core/navigate.py`
    за исправлением более ранней ошибочной записи — и перебрасывает встроенным
    классом) — гасится тем же способом, что и ожидаемая сетевая ошибка:
    реальную проверку итога всё равно делает `assert_error_page_shown`
    следующим шагом."""
    with contexts.in_webview(driver):
        try:
            navigate(driver, url, timeout or settings.WEBVIEW_LOAD_TIMEOUT)
        except WebDriverException as exc:
            if "net::ERR" not in str(exc):
                raise
        except TimeoutError:
            pass


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
def assert_tab_limit_dialog_shown(
    driver, expected_max: int = 10, timeout: int | None = None,
    expected_message: str | None = None,
) -> None:
    """`expected_message`, если задан (TC-131), сравнивается с текстом диалога
    ПОБУКВЕННО (`==`), а не подстрокой — доказывает дословный текст целиком, не
    только число вкладок. По умолчанию (TC-022 и любой другой существующий
    вызывающий код) `expected_message=None` сохраняет прежнее поведение —
    подстрочную проверку `"{expected_max} tabs open" in message`."""
    screen = BrowserScreen(driver)
    assert screen.tab_limit_dialog_visible(timeout=timeout), (
        "диалог «Tab limit reached» не появился при достижении MAX_TABS"
    )
    message = screen.tab_limit_dialog_message(timeout=timeout)
    if expected_message is not None:
        assert message == expected_message, (
            f"текст диалога лимита не совпадает дословно с ожидаемым: "
            f"{message!r} != {expected_message!r}"
        )
    else:
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


# --- Snackbar «Opened in background» (TC-173/175/176) ---

@allure.step("Then snackbar «Opened in background» НЕ появился")
def assert_opened_in_background_snackbar_not_shown(driver, timeout: int = 3) -> None:
    """TC-175: на потолке MAX_TABS `openTab` возвращает `false` ДО записи сигнала
    `backgroundTabOpen` — snackbar не должен появляться вовсе."""
    assert not BrowserScreen(driver).opened_in_background_snackbar_visible(timeout=timeout), (
        "snackbar «Opened in background» неожиданно появился при отказе на потолке MAX_TABS"
    )


@allure.step("When снекбар «Opened in background» показан, затем дожидаемся его полного исчезновения")
def wait_opened_in_background_snackbar_shown_then_gone(driver, timeout: int | None = None) -> None:
    """TC-176: сначала доказывает, что snackbar реально появился (иначе
    последующее ожидание «отсутствия» тривиально истинно, даже если снекбар
    вовсе не показался), затем опрашивает его ПОЛНОЕ исчезновение — не таймер,
    см. докстринг `BrowserScreen.wait_opened_in_background_snackbar_gone`."""
    screen = BrowserScreen(driver)
    assert screen.opened_in_background_snackbar_visible(timeout=timeout if timeout is not None else 5), (
        "snackbar «Opened in background» не появился после фонового открытия"
    )
    screen.wait_opened_in_background_snackbar_gone(timeout=timeout if timeout is not None else 10)


@allure.step("Then снекбар «Opened in background» показывает дословно «{expected_text}»")
def assert_opened_in_background_snackbar_text(driver, expected_text: str, timeout: int | None = None) -> None:
    screen = BrowserScreen(driver)
    assert screen.opened_in_background_snackbar_visible(timeout=timeout if timeout is not None else 8), (
        "snackbar «Opened in background» не появился"
    )
    actual = screen.opened_in_background_snackbar_text(timeout=timeout)
    assert actual == expected_text, (
        f"текст snackbar не совпадает дословно: {actual!r} != {expected_text!r}"
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


# --- TC-129/TC-130: infinite scroll (`ao3_bridge.js:520-615`, browse-infinite-scroll) —
# скролл к концу листинга подгружает следующую страницу ФОНОВЫМ запросом (fetch), не
# навигацией. `SCROLL_MARGIN` сверен с `ao3_bridge.js:514` (`var SCROLL_MARGIN = 400;`)
# на момент автоматизации TC-130 (2026-07-29) — сверить заново при правке этого модуля,
# если константа в исходнике изменится.

_INFINITE_SCROLL_MARGIN_PX = 400


@allure.step("Then снят снимок id work-блёрбов листинга (для diff до/после подгрузки)")
def snapshot_work_blurb_ids(driver) -> list[str]:
    with contexts.in_webview(driver):
        return ListingPage(driver).blurb_work_ids()


@allure.step("Then window.location.pathname/query WebView сняты (снимок)")
def get_webview_location(driver) -> tuple[str, str]:
    with contexts.in_webview(driver):
        result = driver.execute_script(
            "return {pathname: window.location.pathname, search: window.location.search};"
        )
    return result["pathname"], result["search"]


@allure.step("Then window.location.pathname/query WebView не изменились (фоновая подгрузка — не навигация)")
def assert_webview_location_unchanged(driver, before: tuple[str, str]) -> None:
    after = get_webview_location(driver)
    assert after == before, (
        f"window.location.pathname/query WebView изменились: было {before}, стало {after} "
        f"— похоже на навигацию, а не фоновый fetch (TC-130 Then)"
    )


@allure.step(
    "When листинг проскроллен вниз ПРИЦЕЛЬНЫМ минимальным скроллом "
    "(триггер scroll-события infinite-scroll, ao3_bridge.js:548-554)"
)
def trigger_infinite_scroll_load(driver, min_blurb_count: int, timeout: int | None = None) -> None:
    """TC-130 «Заметки для автоматизации», доработка attempt 4 (критик-вход измерение
    headless Chromium): прицельный, ОДНОКРАТНЫЙ скролл с нижним ограничением —
        delta = Math.max(1, ol.getBoundingClientRect().bottom
                             - (innerHeight + SCROLL_MARGIN) + 1)
        window.scrollTo(0, window.scrollY + delta)
    На фикстуре `listing_paginated.mitm` сырая дельта (без `Math.max`) отрицательна
    (предикат подгрузки уже истинен ПРИ ЗАГРУЗКЕ страницы, `ol.bottom ≈ 627 CSS px`
    независимо от ширины вьюпорта) — `scrollTo` от `scrollY=0` клампился бы к 0, и
    scroll-событие не породилось бы вовсе (`ev=0, fetches=0`, тест недостижимо
    красный). `Math.max(1, …)` гарантирует минимальный ненулевой скролл — эквивалент
    `scrollBy(0, 1)`, порождает РОВНО ОДНО scroll-событие и РОВНО ОДНУ подгрузку.

    НЕ используется `scrollTo(0, document.body.scrollHeight)`: филлер-блок фикстуры
    стоит СНАРУЖИ `<ol>` (`recording_builder.py`, `filler_block`), из-за чего условие
    триггера (`ol.bottom > innerHeight + SCROLL_MARGIN`) остаётся ложным (то есть
    подгрузка продолжает срабатывать) после КАЖДОГО аппенда, пока viewport стоит у
    самого низа документа — риск зацепить эвикцию окна (`PAGE_WINDOW=3`) уже в рамках
    этого кейса (явный non-goal TC-130).

    Ждёт, пока число `li[id^="work_"]` не превысит `min_blurb_count` — сигнал, что
    `fetchAndAppend` (`ao3_bridge.js:557-615`) успел завершиться и добавить хотя бы
    один блёрб."""
    with contexts.in_webview(driver):
        driver.execute_script(
            "var ol = document.querySelector('ol.work.index.group');"
            "var SCROLL_MARGIN = arguments[0];"
            "var delta = Math.max(1, ol.getBoundingClientRect().bottom - "
            "(window.innerHeight + SCROLL_MARGIN) + 1);"
            "window.scrollTo(0, window.scrollY + delta);",
            _INFINITE_SCROLL_MARGIN_PX,
        )
        wait_until(
            driver,
            lambda d: len(ListingPage(d).blurb_work_ids()) > min_blurb_count,
            timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
            message=(
                f"после скролла число work-блёрбов не превысило {min_blurb_count} — "
                f"фоновая подгрузка (fetchAndAppend, ao3_bridge.js:557-615) не сработала"
            ),
        )


@allure.step(
    "Then после подгрузки на листинге >= 2 work-блёрбов, все id уникальны, и среди "
    "них есть хотя бы один id, отсутствовавший в снимке ДО скролла"
)
def assert_infinite_scroll_appended_new_unique_blurbs(driver, ids_before: list[str]) -> list[str]:
    """TC-130 Then (доработка attempt 2 критик-вход N2 — count `>= 2`, НЕ ровно 2:
    после аппенда возможна каскадная третья подгрузка от scroll anchoring; доработка
    attempt 3 критик-вход B3 — снимок-diff устойчив к глубине каскада, не привязан к
    id конкретной СТРАНИЦЫ 2). Возвращает НОВЫЕ id (diff) — вызывающий тест сверяет
    Rate-кнопку именно на них, не на позиционно предполагаемом «втором» блёрбе."""
    with contexts.in_webview(driver):
        ids_after = ListingPage(driver).blurb_work_ids()
    assert len(ids_after) >= 2, (
        f"после скролла на листинге {len(ids_after)} work-блёрбов (было {len(ids_before)} "
        f"до скролла), ожидали >= 2: {ids_after}"
    )
    new_ids = [wid for wid in ids_after if wid not in ids_before]
    assert new_ids, (
        f"множество id work-блёрбов ПОСЛЕ скролла не содержит ни одного id, "
        f"отсутствовавшего ДО скролла — фоновая подгрузка не добавила новых блёрбов "
        f"(до={ids_before}, после={ids_after})"
    )
    assert len(ids_after) == len(set(ids_after)), (
        f"id work-блёрбов ПОСЛЕ скролла содержат дубликаты: {ids_after}"
    )
    return new_ids


@allure.step("Then у каждого вновь появившегося work-блёрба ({work_ids}) инжектирована собственная Rate-кнопка")
def assert_rate_buttons_present_for(driver, work_ids: list[str]) -> None:
    """TC-130 Then (доработка attempt 3 критик-вход B3): проверка «любой/каждый из
    diff-множества», не «последний в списке» и не «специфично страница 2» — bridge
    инжектирует Rate-кнопку в цикле на КАЖДЫЙ аппендящийся `li` (`ao3_bridge.js:
    570-581`), проверка обязана покрывать ВСЕ новые id, не один."""
    assert work_ids, "нечего проверять — пустой список вновь появившихся work id"
    with contexts.in_webview(driver):
        page = ListingPage(driver)
        for work_id in work_ids:
            state = page.rate_button_state(work_id)
            assert state["button_count"] >= 1, (
                f"вновь подгруженный блёрб work_id={work_id}: Rate-кнопка не найдена "
                f"(button_count={state['button_count']})"
            )


# --- TC-129: infinite scroll OFF — скролл к концу листинга НЕ подгружает
# следующую страницу, нумерованная пагинация остаётся штатной ---

@allure.step("When листинг проскроллен до самого конца документа")
def scroll_listing_to_bottom(driver) -> None:
    """TC-129 (OFF-сторона): в отличие от `trigger_infinite_scroll_load`
    (ON-сторона, прицельный минимальный скролл — риск зацепить каскад/эвикцию
    окна на 5-страничной фикстуре), здесь скролл к самому низу документа
    безопасен: при `infinite_scroll=OFF` гейт `ao3_bridge.js:530` не
    подписывает `scroll`-листенер вовсе на этой загрузке страницы — скроллить
    прицельно попросту не к чему.

    Доработка attempt 2 (критик-вход Б1): `scrollTo` читается ОБРАТНО сразу
    после вызова — фикстура листинга (`recording_builder.py::render_listing_
    filler_html`) гарантирует высоту ТОЛЬКО количеством филлер-абзацев, БЕЗ
    `min-height` (в отличие от work-страниц, где AT-BUG-030 добавил
    `min-height: 6000px`); если на конкретном устройстве/вьюпорте документ
    не выше вьюпорта, `scrollTo` клампится к 0, скролл не происходит вовсе, и
    негативный Then (`assert_work_blurb_count_holds`) прошёл бы вакуумно
    зелёным независимо от того, сломан ли гейт тумблера — тот же класс
    ложно-зелёных #1 (CLAUDE.md), что уже разобран для `assert_work_blurb_
    count_holds`, но на уровне достижимости самого скролла, а не эффекта.
    Замер прикладывается в Allure — это первый device-прогон фикстуры,
    подтверждающий (или опровергающий) прокручиваемость на живом WebView."""
    with contexts.in_webview(driver):
        result = driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
            "return {y: window.scrollY, ih: window.innerHeight, "
            "sh: document.body.scrollHeight};"
        )
    allure.attach(
        f"scrollY={result['y']} innerHeight={result['ih']} "
        f"scrollHeight={result['sh']}",
        name="listing-scroll-to-bottom-geometry",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert result["y"] > 0, (
        f"страница не прокрутилась (scrollY=0, innerHeight={result['ih']}, "
        f"scrollHeight={result['sh']}) — негативный Then вакуумен: документ не "
        f"выше вьюпорта, скролл к концу не мог произойти"
    )


# --- TC-256 (AT-BUG-074): скролл work-страницы до самого конца документа —
# триггер auto-mark-as-read (`ao3_bridge.js:1164-1197`, `onScroll`). Тот же
# приём геометрии, что `scroll_listing_to_bottom` (browser-clamped `scrollTo`
# гарантирует, что последний узел документа — `#chapters`/`.userstuff.module`,
# AT-BUG-074 — оказывается в вьюпорте по построению, см. докстринг
# `recording_builder._chapters_html`), но отдельная функция (не переиспользование
# `scroll_listing_to_bottom`): разный домен (work-страница, не листинг),
# разное диагностическое имя в Allure-шаге/аттаче.
@allure.step("When work-страница проскроллена до самого конца документа")
def scroll_work_page_to_bottom(driver) -> dict:
    """Возвращает геометрию (`{y, ih, sh}`) — вызывающий код (TC-256) сам решает,
    ждать ли эффект (`wait_for` на `seed_db.read_work_ratings_full()`), эта
    функция только гарантирует, что скролл РЕАЛЬНО произошёл (тот же негативный
    якорь, что `scroll_listing_to_bottom` — без него `assert`, ожидающий эффекта
    `onWorkFinished`, был бы неинтерпретируем при недостаточно высокой странице)."""
    with contexts.in_webview(driver):
        result = driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
            "return {y: window.scrollY, ih: window.innerHeight, "
            "sh: document.body.scrollHeight};"
        )
    allure.attach(
        f"scrollY={result['y']} innerHeight={result['ih']} "
        f"scrollHeight={result['sh']}",
        name="work-page-scroll-to-bottom-geometry",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert result["y"] > 0, (
        f"work-страница не прокрутилась (scrollY=0, innerHeight={result['ih']}, "
        f"scrollHeight={result['sh']}) — auto-mark-as-read Then ниже неинтерпретируем: "
        f"документ не выше вьюпорта, скролл к концу не мог произойти"
    )
    return result


@allure.step("Then на листинге весь бюджет остаётся ровно {expected} work-блёрб(ов) (li[id^='work_'])")
def assert_work_blurb_count_holds(driver, expected: int, timeout: int = 8, poll_interval: float = 0.3) -> None:
    """TC-129: негативный Then («подгрузки не произошло») — тот же класс, что
    `assert_scroll_unchanged`/`assert_top_chrome_not_darkened`: одноразовое
    чтение сразу после скролла не отличило бы «infinite_scroll корректно
    выключен» от «фоновый fetch ещё не успел дописать DOM» (класс
    ложно-зелёных #1, CLAUDE.md — негатив об отсутствии сетевого эффекта
    держится ВЕСЬ бюджет, эффект достижим на этой replay-фикстуре, не уходит
    на живой AO3/404)."""
    def check() -> bool:
        with contexts.in_webview(driver):
            ids = ListingPage(driver).blurb_work_ids()
        assert len(ids) == expected, (
            f"на листинге {len(ids)} work-блёрбов, ожидали ровно {expected} — "
            f"фоновая подгрузка (fetchAndAppend, ao3_bridge.js:557-615) сработала, "
            f"хотя infinite_scroll=OFF должен был не подписать scroll-листенер вовсе: {ids}"
        )
        return True

    assert_holds_for(
        check, budget_s=timeout, interval_s=poll_interval,
        msg=f"число work-блёрбов отклонилось от ожидаемых {expected}",
    )


@allure.step("Then нумерованная пагинация («1»/«2») остаётся видимой (infinite_scroll=OFF не прячет её)")
def assert_pagination_numbered_items_visible(driver) -> None:
    """TC-129: `ao3_bridge.js:541-545` прячет (`display:none`) КАЖДЫЙ `li`
    пагинации, КРОМЕ `.next`/`.previous`, но ТОЛЬКО внутри гейта `:530`
    (`infinite_scroll !== false`) — при OFF блок не выполняется вовсе,
    нумерованные пункты обязаны остаться видимыми. «Next →» НАМЕРЕННО не
    входит в эту проверку (критик-вход N5 TC-129): `:542` не прячет `li.next`
    ни в одном состоянии тумблера — включение его сюда утверждало бы факт,
    которого код не производит."""
    with contexts.in_webview(driver):
        items = ListingPage(driver).pagination_numbered_items_state()
    assert items, "нумерованные пункты пагинации (не .next/.previous) не найдены в DOM"
    hidden = [item for item in items if item["display"] == "none"]
    assert not hidden, (
        f"часть нумерованных пунктов пагинации скрыта (display:none), хотя infinite_scroll=OFF "
        f"не должен прятать их (гейт ao3_bridge.js:530/541-545 выполняется только при ON): "
        f"{hidden} (все пункты: {items})"
    )


@allure.step("When нажата ссылка «Next →» нумерованной пагинации")
def tap_next_page_link(driver, before: tuple[str, str] | None = None, timeout: int | None = None) -> None:
    """TC-129: клик по «Next →» — обычная разметка AO3 (`li.next a`, НЕ
    инжектируется bridge, `ao3_bridge.js:539-540` намеренно оставляет
    Prev/Next нативными ссылками) — тап через JS DOM API, тот же приём, что
    `click_probe_link`/`tap_rate_button`.

    Доработка attempt 2 (критик-вход Н2): ждём не `document.readyState`
    (СТАРЫЙ документ уже `complete` ДО коммита навигации — фактический
    no-op, гонка с самой навигацией), а РЕАЛЬНУЮ смену
    `pathname`/`search` через `get_webview_location`. `before` опционален —
    если не передан, снимается тем же вызовом (обратная совместимость для
    вызывающих без снимка ДО клика)."""
    if before is None:
        before = get_webview_location(driver)
    with contexts.in_webview(driver):
        link = ListingPage(driver).next_page_link()
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", link,
        )
    wait_until(
        driver,
        lambda d: get_webview_location(d) != before,
        timeout=timeout or settings.WEBVIEW_LOAD_TIMEOUT,
        message="страница 2 не завершила навигацию (pathname/search не изменились) после клика «Next →»",
    )


@allure.step("Then window.location.pathname/query WebView изменились (клик «Next →» — полная навигация)")
def assert_webview_location_changed(driver, before: tuple[str, str]) -> None:
    """TC-129: тап по «Next →» — штатная навигация AO3 без вмешательства
    bridge, симметрично `assert_webview_location_unchanged` (TC-130, фоновый
    fetch НЕ меняет location).

    Доработка attempt 2 (критик-вход Н3): кейс требует навигации КОНКРЕТНО НА
    СТРАНИЦУ 2, не любой смены location — href фикстуры детерминирован
    (`recording_builder.py::build_listing_paginated`), поэтому `search`
    обязан нести `page=2`."""
    after = get_webview_location(driver)
    assert after != before, (
        f"window.location.pathname/query WebView не изменились после клика «Next →»: "
        f"было {before}, стало {after} — ожидали полную навигацию на страницу 2"
    )
    _, search_after = after
    assert "page=2" in search_after, (
        f"после клика «Next →» query не несёт page=2 (стало {after}) — навигация "
        f"произошла не на страницу 2 конкретно"
    )


# --- TC-188: DEBUG-кнопка «Copy URL» (ao3_bridge.js:1067-1087) — видимость
# переключается РЕАКТИВНО (`window.setDebugCopyUrl`, BrowserScreen.kt:182,
# `evaluateJavascript` БЕЗ reload), клик копирует `location.href` и меняет
# подпись на "Copied!" на 1500мс. `selectors.DEBUG_COPY_URL_BUTTON` ("body >
# button") однозначен даже когда на странице одновременно присутствует
# фикстурный tap-zone-guard `<button data-tap-marker="button">` (не прямой
# потомок body, см. докстринг константы).

def _copy_url_button_display(driver) -> str:
    """`'absent'`, если узла нет вовсе (bridge не инжектировался/иная
    страница) — отличимо от `'none'` (узел есть, скрыт тумблером OFF)."""
    with contexts.in_webview(driver):
        return driver.execute_script(
            f"var b = document.querySelector({selectors.DEBUG_COPY_URL_BUTTON!r}); "
            "return b ? getComputedStyle(b).display : 'absent';"
        )


@allure.step("Then плавающая кнопка «Copy URL» не видна пользователю")
def assert_copy_url_button_hidden(driver, timeout: int = 5) -> None:
    wait_until(
        driver,
        lambda d: _copy_url_button_display(d) == "none",
        timeout=timeout,
        message="кнопка «Copy URL» видима (display != none), хотя тумблер «Show "
                "copy-URL button» выключен",
    )


@allure.step("Then плавающая кнопка «Copy URL» видна пользователю")
def assert_copy_url_button_visible(driver, timeout: int = 5) -> None:
    wait_until(
        driver,
        lambda d: _copy_url_button_display(d) not in ("none", "absent"),
        timeout=timeout,
        message="кнопка «Copy URL» не появилась (display == none/узел отсутствует), "
                "хотя тумблер «Show copy-URL button» включён",
    )


@allure.step("When пользователь тапает по кнопке «Copy URL»")
def tap_copy_url_button(driver) -> None:
    """НАСТОЯЩИЙ Android-тач через `ActionBuilder`/`POINTER_TOUCH` в НАТИВНОМ
    контексте (координата — центр РЕАЛЬНОГО `getBoundingClientRect()` узла,
    переведённая из CSS px WebView в экранные px устройства) — ни синтетический
    `dispatchEvent` (`dispatch_synthetic_tap`), ни Selenium `.click()` в
    WEBVIEW-контексте (через chromedriver-прокси) здесь НЕ годятся: живой
    прогон 2026-08-14 (3 попытки подряд, все три — идентичный симптом) показал,
    что `navigator.clipboard.writeText` НЕ резолвится (подпись кнопки НИКОГДА
    не переходит в «Copied!») ни под одним из этих двух способов —
    Chromedriver-инициированный клик остаётся ВНУТРИ рендер-процесса WebView и,
    судя по всему, не устанавливает нужный Android-уровня "user activation"/
    фокус документа, которого требует Clipboard API (WebView Chromium требует
    транзиентную активацию ОТ РЕАЛЬНОГО touch-события, поступающего через
    Android input-стек, не через CDP/чистый JS `dispatchEvent`). Реальный
    физический тап через UiAutomator2 — тот же класс события, что обычный
    пользовательский палец, гарантированно даёт документу и фокус, и
    активацию. Guard тап-зон (`ao3_bridge.js:1155`) от способа тапа не зависит
    — whitelist проверяется по тегу `e.target`, один и тот же для любого клика."""
    with contexts.in_webview(driver):
        el = driver.find_element(AppiumBy.CSS_SELECTOR, selectors.DEBUG_COPY_URL_BUTTON)
        rect = driver.execute_script(
            "var r = arguments[0].getBoundingClientRect();"
            "return {left: r.left, top: r.top, width: r.width, height: r.height, "
            "innerWidth: window.innerWidth};",
            el,
        )
        # Диагностический пробник (2026-08-14, независимая от clipboard проверка
        # «клик вообще дошёл до узла») — СВОЙ слушатель, НЕЗАВИСИМЫЙ от
        # `ao3_bridge.js`, идемпотентная установка (флаг на самом узле): считает
        # клики в `window.__ao3TestClickCount`, читается `assert_copy_url_button_
        # label` при таймауте, чтобы отличить «клик не дошёл до кнопки» от «клик
        # дошёл, но `navigator.clipboard.writeText` не зарезолвился».
        driver.execute_script(
            "var b = arguments[0]; if (!b.__ao3TestClickProbeInstalled) { "
            "b.__ao3TestClickProbeInstalled = true; window.__ao3TestClickCount = 0; "
            "b.addEventListener('click', function () { "
            "window.__ao3TestClickCount = (window.__ao3TestClickCount || 0) + 1; }); }",
            el,
        )
    css_x = rect["left"] + rect["width"] / 2
    css_y = rect["top"] + rect["height"] / 2

    webview_screen_rect = BrowserScreen(driver).webview_rect()
    scale = webview_screen_rect["width"] / rect["innerWidth"] if rect["innerWidth"] else 1.0
    screen_x = int(webview_screen_rect["x"] + css_x * scale)
    screen_y = int(webview_screen_rect["y"] + css_y * scale)
    allure.attach(
        f"css rect={rect!r} webview_screen_rect={webview_screen_rect!r} scale={scale:.3f} "
        f"-> screen tap=({screen_x}, {screen_y})",
        name="tap_copy_url_button: coordinate translation",
        attachment_type=allure.attachment_type.TEXT,
    )

    contexts.to_native(driver)
    builder = ActionBuilder(driver)
    finger = builder.add_pointer_input(POINTER_TOUCH, "finger1")
    finger.create_pointer_move(duration=0, x=screen_x, y=screen_y)
    finger.create_pointer_down()
    finger.create_pointer_move(duration=50, x=screen_x, y=screen_y)
    finger.create_pointer_up(0)
    builder.perform()


@allure.step("Then подпись кнопки «Copy URL» показывает «{expected}»")
def assert_copy_url_button_label(driver, expected: str, timeout: int = 5) -> None:
    """AT-BUG-039-класс диагностики (тот же приём, что `assert_tap_to_scroll_delta`):
    `holder` заполняется ВНУТРИ предиката на каждом опросе; при таймауте
    `TimeoutException` перехватывается и переброшен заново с сообщением,
    дополненным `holder["value"]` — РЕАЛЬНО ПОСЛЕДНИМ наблюдённым значением, а
    не свежим вызовом ДО/ПОСЛЕ ожидания (`message=` строкой вычислился бы до
    входа в `wait_until`, замораживая устаревшее/начальное значение под
    подписью «последнее»)."""
    holder: dict[str, str | None] = {"value": None}

    def _label(d) -> str | None:
        with contexts.in_webview(d):
            value = d.execute_script(
                f"var b = document.querySelector({selectors.DEBUG_COPY_URL_BUTTON!r}); "
                "return b ? b.textContent : null;"
            )
        holder["value"] = value
        return value

    try:
        wait_until(
            driver, lambda d: _label(d) == expected, timeout=timeout,
            message=f"подпись кнопки «Copy URL» не стала «{expected}» за {timeout}с",
        )
    except TimeoutException as exc:
        # Диагностика (2026-08-14): различает «клик не дошёл до узла» (см.
        # __ao3TestClickCount, tap_copy_url_button) от «клик дошёл, но
        # navigator.clipboard.writeText не зарезолвился» (hasFocus/isSecureContext/
        # тип API) — без этого таймаут неотличим по причине.
        try:
            with contexts.in_webview(driver):
                diag = driver.execute_script(
                    f"var b = document.querySelector({selectors.DEBUG_COPY_URL_BUTTON!r}); "
                    "return {hasFocus: document.hasFocus(), "
                    "isSecureContext: window.isSecureContext, "
                    "clipboardType: typeof navigator.clipboard, "
                    "writeTextType: (navigator.clipboard && typeof navigator.clipboard.writeText) || 'n/a', "
                    "clickCount: window.__ao3TestClickCount || 0, "
                    "buttonText: b ? b.textContent : null};"
                )
                try:
                    browser_log = driver.get_log("browser")
                except Exception as log_exc:  # noqa: BLE001
                    browser_log = f"<browser log недоступен: {log_exc.__class__.__name__}: {log_exc}>"
        except Exception as diag_exc:  # noqa: BLE001
            diag = f"<диагностика недоступна: {diag_exc.__class__.__name__}>"
            browser_log = "<n/a>"
        raise TimeoutException(
            f"подпись кнопки «Copy URL» не стала «{expected}» за {timeout}с "
            f"(последнее наблюдение: {holder['value']!r}; диагностика: {diag!r}; "
            f"browser log: {browser_log!r})"
        ) from exc


@allure.step("Then клик по «Copy URL» реально вызывает navigator.clipboard.writeText "
              "(browser log/подпись — ESC-032 путь б.1)")
def assert_copy_url_write_text_invoked(driver, timeout: int = 5, poll_interval: float = 0.3) -> None:
    """TC-188 (переформулировка Then, ESC-032 путь б.1, `bugs/AT-BUG-068.md`):
    продуктовый контракт «Copied!»/1500мс-таймер/содержимое буфера НЕ
    ассертится здесь — заблокирован окружением (`DOMException` бросается
    permission-слоем Blink ДО Android `ClipboardManager`, путь (а)
    АРХИТЕКТУРНО недостижим на этом AVD, не «пока не нашли обход» — критик-вход
    раунда 2 AT-BUG-068). Ядро кейса, автоматизируемое сейчас: клик доходит до
    DOM-узла кнопки, и `navigator.clipboard.writeText(location.href)` РЕАЛЬНО
    ВЫЗЫВАЕТСЯ.

    Позитивный артефакт-якорь, не вакуумный негатив (класс ложно-зелёных #1,
    CLAUDE.md): в ТЕКУЩЕЙ тестовой среде (`ao3_test_api34`, System WebView
    Chromium 113.0.5672.136) вызов `writeText` детерминированно ДОКАЗУЕМ через
    `driver.get_log('browser')` — запись `DOMException: Write permission
    denied` СУЩЕСТВУЕТ там, только если исполнение реально дошло до Clipboard
    API (см. живую диагностику `AT-BUG-068.md`: `clickCount=1`,
    `hasFocus=true`, `isSecureContext=true`, промис РЕАЛЬНО реджектится этим
    исключением). Отсутствие сигнала НЕ засчитывается автоматически —
    альтернативный позитивный путь (среда, где запись в буфер РАЗРЕШЕНА:
    промис резолвится, `.then()` меняет подпись на «Copied!») тоже
    принимается тем же ассертом, поэтому формулировка не ломается при смене
    WebView/AVD-образа. Один ИЗ ДВУХ сигналов ОБЯЗАН появиться — иначе клик,
    похоже, вообще не дошёл до обработчика (или тестовая среда деградировала
    иначе), и это честный провал, а не «продукт не готов»."""
    accumulated: list[str] = []

    def _observed() -> bool:
        with contexts.in_webview(driver):
            try:
                entries = driver.get_log("browser")
            except Exception:  # noqa: BLE001
                entries = []
            label = driver.execute_script(
                f"var b = document.querySelector({selectors.DEBUG_COPY_URL_BUTTON!r}); "
                "return b ? b.textContent : null;"
            )
        for entry in entries:
            msg = entry.get("message", "") if isinstance(entry, dict) else str(entry)
            accumulated.append(msg)
        if any("DOMException" in m and "Write permission denied" in m for m in accumulated):
            return True
        return label == "Copied!"

    ok = poll_for(_observed, timeout=timeout, interval=poll_interval)
    assert ok, (
        "ни DOMException «Write permission denied» в browser log (AT-BUG-068, "
        "признак этой среды), ни подпись «Copied!» (признак среды без этого "
        f"ограничения) не наблюдались за {timeout}с после тапа по «Copy URL» — "
        f"navigator.clipboard.writeText, похоже, не был вызван вовсе (клик не "
        f"дошёл до обработчика узла); накопленный browser log: {accumulated!r}"
    )
