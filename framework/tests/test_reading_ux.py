"""Reading-UX тап-зоны work-страницы (`ao3_bridge.js:1149-1166`,
docs/01-test-strategy.md §9 «reading-UX жесты и их тумблеры» —
browse-tap-to-scroll/browse-tap-fullscreen). Три равные трети viewport:
верхняя скроллит вверх, нижняя — вниз, средняя переключает fullscreen; guard
whitelist-узлов (`closest('a, button, input, select, textarea, label, summary,
[role="button"]')`) выполняется РАНЬШЕ вычисления трети и гейтит ВЕСЬ
обработчик флагом `window.__ao3TapToScroll` — TC-126/TC-127/TC-128 несут
`tap_to_scroll = ON` как общее предусловие.

Узел 3 AT-BUG-030 (высота документа >= 3×innerHeight) уже присутствует во всех
четырёх потребителях `render_work_page_html`, включая `work_with_download.mitm`
(общий с TC-032/033/119/120/122) — TC-126/TC-127 используют его для
диагностической силы Then (страница не должна упираться в границу скролла ДО
тапа), TC-128 не зависит от высоты/скролла вовсе, но переиспользует ту же
короткую-по-сути (структурно) фикстуру без изменений.

Тап дispatch'ится синтетическим `MouseEvent` через `document.elementFromPoint`
(`browser_steps.dispatch_synthetic_viewport_tap`) — целевой узел определяется
РЕАЛЬНОЙ геометрией страницы в момент тапа, не хардкодом CSS-селектора;
центральная колонка X (`innerWidth/2`) промахивается мимо узлов 1/2 AT-BUG-030
(`left:24px; width:200px`) независимо от Y/scroll-позиции, поэтому целью тапа
всегда оказывается обычный `<p>`-филлер (неинтерактивный, вне whitelist).

Порядок навигации в Given TC-128 (work-страница — вкладка-0, вторая вкладка
открыта ПОСЛЕ через Library) — тот же паттерн, что `test_tap_zone_guard.py`
(AT-BUG-018/019/022: единственный Appium `WEBVIEW_<pkg>` context прилипает к
вкладке-0 независимо от визуально активной вкладки)."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, library_steps, rating_steps, settings_steps

# Калибровка TC-119/120/122 (AT-BUG-030, живой прогон) — светлая статичная
# фикстура даёт скромный luma-контраст, не дефолтные 0.5 (TC-058).
_TOP_CHROME_RATIO = 0.7


def _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work):
    """Общий Given TC-126/127/128: tap_to_scroll включён, work-страница —
    вкладка-0 (WEBVIEW-context-цель), вторая вкладка открыта, чтобы TabStrip
    отрендерился (`tabs.size>1`), не fullscreen."""
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_tap_to_scroll(driver)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    library_steps.open_work_in_browser(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-126")
@allure.title("Тап по верхней трети work-страницы скроллит страницу вверх (tap-to-scroll ON)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_top_third_scrolls_up(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница (высота >= 3×innerHeight, узел 3
    # AT-BUG-030) — вкладка-0, TabStrip виден (>=2 вкладки), не fullscreen;
    # страница предварительно проскроллена вниз так, что scrollY > 0.95×innerHeight
    # (execute_script — дешевле и не создаёт зависимости от TC-127)
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    scroll_before, inner_height = browser_steps.prescroll_past_tap_to_scroll_threshold(driver)

    # When пользователь тапает по верхней трети экрана (clientY < innerHeight/3,
    # цель — неинтерактивный узел)
    browser_steps.dispatch_tap_to_scroll_up_tap(driver)

    # Then window.scrollY уменьшается примерно на 0.95×innerHeight (измерение
    # CH-005: dy ≈ -1710 при innerHeight=1800)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=-1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-127")
@allure.title("Тап по нижней трети work-страницы скроллит страницу вниз (tap-to-scroll ON)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_bottom_third_scrolls_down(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница (высота >= 3×innerHeight, узел 3
    # AT-BUG-030) — вкладка-0, TabStrip виден (>=2 вкладки), не fullscreen;
    # страница в начальной позиции (scrollY = 0, штатное состояние после
    # свежей загрузки — не требует предскролла, в отличие от TC-126)
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    scroll_before = browser_steps.get_webview_scroll_y(driver)
    assert scroll_before == 0, (
        f"Given TC-127 требует scrollY=0 (свежая загрузка), фактически {scroll_before}"
    )
    inner_height = browser_steps.get_webview_inner_height(driver)

    # When пользователь тапает по нижней трети экрана (clientY >= 2×innerHeight/3,
    # цель — неинтерактивный узел)
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)

    # Then window.scrollY увеличивается примерно на 0.95×innerHeight (измерение
    # CH-005: dy ≈ +1710 при innerHeight=1800), не превышая максимально
    # возможный скролл документа (узел 3 AT-BUG-030 даёт достаточный запас)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-128")
@allure.title("Тап по средней трети work-страницы переключает fullscreen (вход и выход)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_middle_third_toggles_fullscreen(loved_work_seeded, replay, driver):
    # Given открыты 2 вкладки Browse, активная — replay work-страница; TabStrip
    # виден вверху экрана; tap_to_scroll включён (routine, вне скоупа этого
    # кейса); режим fullscreen выключен
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    baseline_luma = browser_steps.measure_top_chrome_luma(driver)

    # When пользователь тапает по средней трети экрана (координата — центр
    # вьюпорта, ПЕРЕСЧИТЫВАЕМЫЙ перед каждым тапом — innerHeight меняется между
    # входом/выходом из fullscreen, см. заметки кейса)
    browser_steps.dispatch_tap_zone_fullscreen_toggle_tap(driver)

    # Then режим fullscreen включается: TabStrip скрывается (тот же пиксельный
    # прокси, что TC-058, top_chrome_avg_luma)
    browser_steps.assert_top_chrome_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)

    # When пользователь тапает по средней трети экрана ещё раз (координата
    # пересчитана заново как защитная мера — на этом стенде innerHeight
    # эмпирически не меняется между тапами, см. заметки кейса TC-128)
    browser_steps.dispatch_tap_zone_fullscreen_toggle_tap(driver)

    # Then режим fullscreen выключается: TabStrip снова отображается — toggle
    # симметричен, второй тап возвращает исходное наблюдаемое состояние
    browser_steps.assert_top_chrome_restored(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)
