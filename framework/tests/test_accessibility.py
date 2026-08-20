"""Область accessibility (test-cases/accessibility/, docs/01-test-strategy.md §9
area E1): TC-106 (content-desc/text на ключевых контролах), TC-107 (font scaling
1.3x), TC-108 (contrast sanity dark/light), TC-148 (touch-target >= 48dp свип),
TC-150 (свип попарных пересечений bounds интерактивных узлов), TC-149 (свип
вычисленного WCAG-контраста DOM-контента WebView).
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import (
    a11y_steps,
    app_steps,
    browser_steps,
    library_steps,
    rating_steps,
    settings_steps,
    side_panel_steps,
)

FONT_SCALE = 1.3
DEFAULT_FONT_SCALE = 1.0


@pytest.fixture()
def font_scale_1_3():
    """TC-107: системный `font_scale=1.3` применяется ДО старта приложения (см.
    `adb.set_font_scale` — детерминированный способ, не зависящий от live-конфига
    активности). Восстанавливает дефолт (1.0) в teardown НЕЗАВИСИМО от исхода
    теста — иначе следующий тест унаследует изменённый масштаб (тот же класс
    проблемы, что logcat в TC-098/TC-105)."""
    app_steps.set_font_scale(FONT_SCALE)
    try:
        yield
    finally:
        app_steps.set_font_scale(DEFAULT_FONT_SCALE)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-106")
@allure.title("Ключевые контролы (Rate/Note/тема/шрифт/таб) несут content-description или видимый текст")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_key_controls_have_accessible_label_or_text(placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given RatingMenu раскрыта на странице работы W, TabStrip виден с >=2
    # вкладками, активна именно вкладка работы W.
    # `isWorkPage` вкладки проставляется ТОЛЬКО в `onPageLoaded` (реальное
    # завершение загрузки, BrowserViewModel.kt:463-476) — открываем работу W ТЕМ ЖЕ
    # проверенным приёмом, что TC-007/098 (`rating_steps.open_work_page`,
    # chromedriver `.get()` на вкладке-0), а не через deep-link напрямую на URL
    # работы (deep-link создаёт вкладку раньше, чем страница реально догрузится,
    # без наблюдаемого сигнала готовности для новой вкладки — гонка). Вторая
    # вкладка добавляется ОТДЕЛЬНЫМ deep-link'ом на Home (тот же приём, что
    # TC-022/023) — она становится активной автоматически, поэтому переключаемся
    # обратно на вкладку 0 (работа W), сохраняя TabStrip видимым (2 вкладки).
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    browser_steps.switch_to_tab(driver, 0)
    a11y_steps.expand_rating_panel(driver)

    # When accessibility-дерево читается напрямую (find_elements/get_attribute),
    # без взаимодействия с самими контролами — только инспекция уже отрисованного
    # состояния (RatingOverlay.kt/TabStrip.kt/BottomBar.kt — все code-anchors
    # сверены с исходником при написании теста).
    # Then RatingMenu/TabStrip несут непустой content-desc ИЛИ видимый text
    a11y_steps.assert_rating_buttons_labeled(driver)
    a11y_steps.assert_note_button_labeled(driver)
    a11y_steps.assert_tab_strip_controls_labeled(driver)

    # Side panel раскрыта ОТДЕЛЬНЫМ шагом (не одновременно с проверкой выше):
    # разведка (live-дерево, emulator-5554) показала, что развёрнутая side panel
    # рисует собственный полноэкранный scrim-`Box` (MainActivity.kt ~561-579,
    # `clickable { panelExpanded = false }`), который перекрывает WebView/
    # TabStrip/BottomBar/RatingMenu НЕ только визуально, но и в accessibility-
    # дереве — при развёрнутой панели узлы этих зон полностью ОТСУТСТВУЮТ в XML
    # (не просто скрыты/неважны, см. witness прогона). Дизайнерское поведение
    # модального оверлея, не баг: Given кейса («всё раскрыто одновременно»)
    # физически ненаблюдаемо ОДНИМ снимком дерева — Then проверяется тем же
    # набором фактов ПОСЛЕДОВАТЕЛЬНО (сначала RatingMenu/TabStrip выше, теперь
    # тема/шрифт панели), что не меняет проверяемое свойство (каждый named-контрол
    # несёт лейбл), только порядок инспекции.
    side_panel_steps.expand(driver)
    a11y_steps.assert_theme_toggle_labeled(driver)
    a11y_steps.assert_font_size_controls_labeled(driver)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-107")
@allure.title("Font scaling 1.3x на основных экранах: нет краша, контролы остаются в дереве")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_font_scale_1_3_no_crash_key_controls_present(font_scale_1_3, placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given font_scale системы = 1.3 (фикстура, применена ДО старта приложения),
    # приложение запущено с чистыми данными и открытой работой W (переиспользован
    # seed TC-009 через placeholder_seeded_work, см. test_rating.py докстринг)
    # When представительный smoke-путь: Library -> Browse (работа W, панель
    # рейтинга раскрыта) -> Settings — тот же приём, что TC-098/TC-105 (не
    # изобретаем новый маршрут)
    app_steps.wait_app_ready(driver)
    app_steps.assert_process_alive()

    app_steps.open_tab(driver, "Library")
    library_steps.assert_library_loaded(driver)
    app_steps.assert_process_alive()

    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.assert_rating_panel_present_and_clickable(driver)
    app_steps.assert_process_alive()

    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_settings_loaded(driver)
    app_steps.assert_process_alive()

    # Then приложение не крашится ни на одном из трёх экранов (process alive на
    # каждом шаге выше) и ключевые контролы каждого экрана присутствуют в
    # accessibility tree и кликабельны: bottom nav (успешная навигация через
    # `open_tab` выше уже доказывает это — `tap()` ждёт `element_to_be_clickable`),
    # Rate-кнопка/панель рейтинга (проверено выше), контролы темы/шрифта/яркости
    # в Settings (testability gap — см. TC-107.md: НЕ доказывает отсутствие
    # визуальной обрезки текста, только отсутствие функционального регресса)
    settings_steps.assert_reader_controls_present_and_clickable(driver)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-108")
@allure.title("Contrast sanity dark/light: текст и фон различимы в обоих системных вариантах темы")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_contrast_sanity_dark_and_light(placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given приложение открыто на странице работы W
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)

    # When тема приложения переключается в Dark (side panel toggle), делается
    # скриншот; затем переключается в Light, делается второй скриншот
    side_panel_steps.expand(driver)
    side_panel_steps.toggle_theme(driver)
    side_panel_steps.assert_theme_is_dark(driver)
    side_panel_steps.collapse(driver)

    # Then в Dark текстовые зоны (bottom bar, заголовок работы) различимы от фона
    # по luma-прокси (std сверх sanity-порога — не точный WCAG-ratio, см. TC-108.md)
    browser_steps.assert_bottom_bar_text_distinguishable(driver)
    browser_steps.assert_work_title_distinguishable(driver)

    # When тема переключается обратно в Light — инвариант проверяется для КАЖДОГО
    # варианта темы независимо (не только для одного примера, см. Инвариант кейса)
    side_panel_steps.expand(driver)
    side_panel_steps.toggle_theme(driver)
    side_panel_steps.assert_theme_is_light(driver)
    side_panel_steps.collapse(driver)

    # Then то же свойство различимости верно и в Light
    browser_steps.assert_bottom_bar_text_distinguishable(driver)
    browser_steps.assert_work_title_distinguishable(driver)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-148")
@allure.title("Свип touch-target: нативные интерактивные цели не меньше 48dp")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_native_chrome_touch_targets_at_least_48dp(placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given плотность экрана измерена ДО свипа (РЕАЛЬНАЯ плотность текущего
    # прогона, не хардкод из документации), маршрут Library -> Browse (work
    # page, side panel свёрнут) -> Browse (side panel раскрыт) -> Settings
    # пройден один раз, TabStrip виден с >=2 вкладками (тот же приём открытия
    # второй вкладки, что TC-106/TC-107: rating_steps.open_work_page + deep-link
    # на Home + переключение обратно на вкладку-0).
    app_steps.wait_app_ready(driver)
    density = app_steps.measure_screen_density()
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    browser_steps.switch_to_tab(driver, 0)

    measurements: list[tuple[str, dict]] = []

    # When accessibility-дерево читается напрямую (без взаимодействия с самими
    # контролами — раскрытие панелей ниже готовит состояние Given, не часть
    # измерения) на КАЖДОЙ точке маршрута, для поимённого списка целей.
    app_steps.open_tab(driver, "Library")
    library_steps.assert_library_loaded(driver)
    measurements += a11y_steps.measure_library_tab_chips(driver)

    # `open_tab` сбрасывает `navExpanded=false` (MainActivity.kt onSelect) при
    # ЛЮБОМ переключении нижней навигации — возврат на Browse гарантированно
    # заново свёрнут, а активная вкладка-0 (страница работы) и TabStrip (2
    # вкладки) не зависят от переключений BottomNav (отдельный слой состояния
    # browserViewModel), поэтому здесь по-прежнему видна работа W с TabStrip.
    app_steps.open_tab(driver, "Browse")
    measurements += a11y_steps.measure_bottom_bar_handle(driver)
    measurements += a11y_steps.measure_side_panel_collapsed_handle(driver)
    measurements += a11y_steps.measure_tab_strip_targets(driver)

    side_panel_steps.expand(driver)
    measurements += a11y_steps.measure_side_panel_expanded_controls(driver)

    # Раскрытая side panel рисует полноэкранный scrim (MainActivity.kt:686-701,
    # `AnimatedVisibility(visible = selectedTab == AppTab.BROWSE && panelExpanded)`),
    # который перекрывает BottomNav в accessibility-дереве — тот же эффект, что
    # TC-106 задокументировал для RatingMenu/TabStrip/BottomBar. Измерение уже
    # снято выше; сворачиваем панель ПЕРЕД переходом на Settings — тот же приём,
    # что TC-108 использует после каждого действия на раскрытой панели
    # (`side_panel_steps.collapse`), иначе `open_tab("Settings")` не находит
    # кнопку (перекрыта скримом).
    side_panel_steps.collapse(driver)

    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_settings_loaded(driver)
    measurements += a11y_steps.measure_settings_controls(driver)

    # Then для КАЖДОЙ именованной цели маршрута bounds.width >= 48dp И
    # bounds.height >= 48dp по РЕАЛЬНО измеренной плотности — проверяется КАК
    # СВОЙСТВО одновременно для всего списка (см. «Инвариант» TC-148.md), не
    # как отдельные примеры по одной цели.
    a11y_steps.assert_touch_targets_at_least_48dp(measurements, density)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-150")
@allure.title("Свип перекрытий: bounding-rect'ы нативных интерактивных элементов не пересекаются")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_no_interactive_bounds_overlap(placeholder_seeded_work, driver):
    work = placeholder_seeded_work
    # Given маршрут Library -> Browse (work page, side panel свёрнут) ->
    # Browse (side panel раскрыт) -> Settings пройден один раз, TabStrip
    # виден с >=2 вкладками — тот же поимённый маршрут и тот же приём
    # открытия второй вкладки, что TC-148 (rating_steps.open_work_page +
    # deep-link на Home + переключение обратно на вкладку-0).
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    browser_steps.switch_to_tab(driver, 0)

    findings: list[tuple[str, object]] = []

    # When на КАЖДОЙ точке маршрута accessibility-дерево читается напрямую
    # через UiAutomator2 (без взаимодействия с элементами — переключение
    # вкладок/раскрытие панелей готовит состояние Given, не часть этого
    # When), из него извлекаются bounds ВСЕХ интерактивных узлов и
    # вычисляется попарное пересечение прямоугольников `bounds` (кроме
    # parent-child, см. `framework.core.a11y_tree`).
    app_steps.open_tab(driver, "Library")
    library_steps.assert_library_loaded(driver)
    findings += a11y_steps.collect_interactive_overlaps(driver, "Library")

    # `open_tab` сбрасывает `navExpanded=false` при ЛЮБОМ переключении нижней
    # навигации (см. докстринг TC-148 в этом же файле) — возврат на Browse
    # гарантированно заново свёрнут (side panel свёрнута).
    app_steps.open_tab(driver, "Browse")
    findings += a11y_steps.collect_interactive_overlaps(driver, "Browse (side panel свёрнут, TabStrip)")

    side_panel_steps.expand(driver)
    findings += a11y_steps.collect_interactive_overlaps(driver, "Browse (side panel раскрыт)")
    # Сворачиваем панель ПЕРЕД переходом на Settings — тот же приём, что
    # TC-148 (раскрытая панель рисует scrim, перекрывающий BottomNav).
    side_panel_steps.collapse(driver)

    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_settings_loaded(driver)
    findings += a11y_steps.collect_interactive_overlaps(driver, "Settings")

    # Then ни для одной пары РАЗНЫХ (не parent-child) интерактивных узлов ни
    # на одной точке маршрута пересечение bounds не найдено — проверяется КАК
    # СВОЙСТВО одновременно для ВСЕХ точек (см. «Инвариант» TC-150.md).
    a11y_steps.assert_no_overlapping_interactive_targets(findings)


@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-149")
@allure.title(
    "Вычисленный контраст DOM-контента WebView (инжектированные Rate/Note-кнопки + "
    "фикстурные узлы work-страницы) держит WCAG-порог 4.5:1/3:1 в light и dark"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_computed_contrast_holds_wcag_threshold_light_and_dark(
    loved_work_rated_and_commented_seeded, replay, driver
):
    work = loved_work_rated_and_commented_seeded
    measurements: list[a11y_steps.Contrast] = []

    # Given приложение открыто в replay-режиме на листинговой странице
    # (`listing_basic.mitm`, Light-тема); на блёрбе засеянной работы LOVED видны
    # закрашенный Rate-бейдж (`data-ao3-rate-btn`, BADGE.SAVE) и Note-кнопка
    # (`data-ao3-note-btn`) — см. `loved_work_rated_and_commented_seeded`.
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    browser_steps.assert_note_button_present(driver, work.ao3_id, "TC-149 seeded comment")

    # When 1: для Rate-бейджа и Note-кнопки на листинге вычисляется WCAG-контраст
    # против эффективного фона (точка маршрута «листинг», Light).
    measurements += a11y_steps.measure_listing_badge_contrast(driver, work.ao3_id, "листинг×Light")

    # When 2: WebView навигируется на work-страницу LOVED (`BrowserScreen.open_work`,
    # ТОТ ЖЕ replay-сеанс — flow для этой work-страницы уже записан в
    # `listing_basic.mitm`, `build_listing_basic`); вычисляется контраст заголовка
    # (`h2.title.heading`) и первого абзаца тела фикстуры (`.wrapper > p`) —
    # точка маршрута «work-страница», Light.
    rating_steps.open_work_page(driver, work.ao3_id)
    measurements += a11y_steps.measure_work_page_contrast(driver, "work-страница×Light")

    # When 3: тема переключается на Dark (side panel toggle); контраст title/body
    # пересчитывается на ТЕКУЩЕЙ (work) странице — точка «work-страница», Dark.
    side_panel_steps.expand(driver)
    side_panel_steps.toggle_theme(driver)
    side_panel_steps.assert_theme_is_dark(driver)
    side_panel_steps.collapse(driver)
    measurements += a11y_steps.measure_work_page_contrast(driver, "work-страница×Dark")

    # When 4: WebView навигируется обратно на `LISTING_BASIC_URL` (тот же
    # replay-сеанс, та же фикстура отдаёт тот же HTML); контраст Rate-бейджа/
    # Note-кнопки пересчитывается — точка маршрута «листинг», Dark.
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    measurements += a11y_steps.measure_listing_badge_contrast(driver, work.ao3_id, "листинг×Dark")

    # Then для каждой из четырёх комбинаций «точка маршрута × тема» (листинг×Light,
    # work-страница×Light, work-страница×Dark, листинг×Dark) вычисленный ratio
    # КАЖДОГО узла этой точки >= 4.5:1 (обычный текст) либо >= 3:1 (крупный текст) —
    # проверяется КАК СВОЙСТВО одновременно для ВСЕХ узлов ОБЕИХ точек И ОБЕИХ тем
    # (см. «Инвариант» TC-149.md).
    a11y_steps.assert_all_nodes_meet_contrast_threshold(measurements)
