"""Тесты side panel на Browse (app-under-test ui/browser/BrowseSidePanel.kt):
Contrast (тема), A-/A+ (шрифт), эквивалентность их стейта с экраном Settings и
Home-навигация активной вкладки (TC-057).

Дизайн следует test_smoke.py/test_rating.py: точечная зависимость от живого AO3
(WebView должен догрузить страницу) неизбежна для проверки textZoom/theme —
проверяется geometry заголовка и SharedPreferences, а не контент сайта.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.steps import app_steps, browser_steps, rating_steps, settings_steps, side_panel_steps


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-050")
@allure.title("Contrast-иконка side panel переключает тему мгновенно (вход через панель)")
def test_side_panel_contrast_toggles_theme_instantly(clean_app, driver):
    # Given приложение в светлой теме (дефолт — SYSTEM, зависит от эмулятора,
    # поэтому тема приводится к Light явно через Settings), Browse активна
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")

    side_panel_steps.expand(driver)
    side_panel_steps.assert_theme_is_light(driver)

    # When пользователь нажимает иконку Contrast в side panel
    side_panel_steps.toggle_theme(driver)

    # Then иконка Contrast мгновенно отражает новое состояние (Dark) — без
    # перезапуска приложения, вход именно через панель (не Settings)
    side_panel_steps.assert_theme_is_dark(driver)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-054")
@allure.title("Side panel и Settings — один общий стейт темы/шрифта (панель → Settings)")
def test_side_panel_and_settings_share_theme_and_font_state(clean_app, driver):
    # Given тема Light и дефолтный fontSizeStep (0), Browse активна, side panel развёрнут
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")
    side_panel_steps.expand(driver)
    side_panel_steps.assert_theme_is_light(driver)

    # When пользователь переключает тему на Dark через side panel и увеличивает шрифт «A+»
    side_panel_steps.toggle_theme(driver)
    side_panel_steps.increase_font(driver)
    # Свернуть панель перед переключением вкладки — иначе кнопки панели (ниже на
    # экране, чем ручка-пилюля) перехватывают эвристику BottomNav._find_pill
    side_panel_steps.collapse(driver)

    # Then экран Settings отражает изменения, сделанные из панели — оба входа
    # управляют одним SettingsViewModel/SharedPreferences (theme_mode/font_size_step)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_settings_loaded(driver)
    settings_steps.assert_theme_mode_pref("DARK")
    settings_steps.assert_font_size_step_pref(1)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-051")
@allure.title("«A+» в side panel мгновенно увеличивает шрифт в WebView и переживает рестарт")
def test_font_size_increase_instant_and_persists(clean_app, driver):
    # Given на Browse открыта страница AO3 с читаемым текстом, fontSizeStep дефолтный (0)
    app_steps.wait_app_ready(driver)
    baseline = browser_steps.measure_heading_height(driver)

    # When пользователь нажимает «A+» один раз
    side_panel_steps.expand(driver)
    side_panel_steps.increase_font(driver)

    # Then текст веб-страницы становится крупнее сразу (без перезагрузки страницы)
    enlarged = browser_steps.measure_heading_height(driver)
    assert enlarged > baseline, f"текст не увеличился сразу после «A+»: {baseline} -> {enlarged}"

    # When приложение полностью перезапущено (force-stop + relaunch, не pm clear)
    app_steps.restart_app(driver)
    app_steps.wait_app_ready(driver)

    # Then увеличенный размер шрифта сохранён (font_size_step=1 в SharedPreferences)
    settings_steps.assert_font_size_step_pref(1)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-052")
@allure.title("Кнопки шрифта side panel отключаются на границах диапазона (шаг 0 и 6)")
def test_font_buttons_disabled_at_range_boundaries(clean_app, driver):
    # Given side panel развёрнут, fontSizeStep на дефолтном (не граничном) шаге 0
    app_steps.wait_app_ready(driver)
    side_panel_steps.expand(driver)

    # When пользователь многократно нажимает «A+», пока не достигнута верхняя граница
    # (диапазон — 7 ступеней 0..6, 6 нажатий от 0 гарантированно доходят до максимума)
    for _ in range(6):
        side_panel_steps.increase_font(driver)

    # Then «A+» неактивна на максимуме, «A-» остаётся активной
    side_panel_steps.assert_increase_enabled(driver, False)
    side_panel_steps.assert_decrease_enabled(driver, True)

    # When пользователь многократно нажимает «A-», пока не достигнута нижняя граница
    for _ in range(6):
        side_panel_steps.decrease_font(driver)

    # Then «A-» неактивна на минимуме, «A+» остаётся активной
    side_panel_steps.assert_decrease_enabled(driver, False)
    side_panel_steps.assert_increase_enabled(driver, True)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-053")
@allure.title("Двухпальцевый pinch/spread на Browse меняет размер шрифта (тот же fontSizeStep)")
def test_pinch_spread_changes_font_size(clean_app, driver):
    # Given на Browse открыта страница AO3, fontSizeStep приведён к среднему
    # (не граничному) шагу через панель, затем панель свёрнута — жест выполняется
    # по области контента (BrowserScreen.kt pointerInput, не по side panel)
    app_steps.wait_app_ready(driver)
    side_panel_steps.expand(driver)
    for _ in range(3):
        side_panel_steps.increase_font(driver)
    side_panel_steps.collapse(driver)
    baseline = browser_steps.measure_heading_height(driver)

    # When пользователь выполняет двухпальцевый spread поверх страницы, превышая
    # порог распознавания жеста (span >= 30dp)
    browser_steps.pinch_spread(driver)

    # Then размер текста увеличивается — тот же эффект, что кнопка «A+» в side panel
    # (появление временного HUD-индикатора уровня шрифта — известное ограничение
    # автоматизации: LevelIndicator рендерится без contentDescription/testTag и виден
    # только ~800ms, поэтому проверяется наблюдаемый функциональный контракт — рост
    # размера текста, а не сам факт появления индикатора)
    enlarged = browser_steps.measure_heading_height(driver)
    assert enlarged > baseline, f"текст не увеличился после spread: {baseline} -> {enlarged}"

    # When пользователь выполняет обратный жест pinch (сведение пальцев)
    browser_steps.pinch_close(driver)

    # Then размер текста уменьшается обратно
    shrunk = browser_steps.measure_heading_height(driver)
    assert shrunk < enlarged, f"текст не уменьшился после pinch: {enlarged} -> {shrunk}"


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-055")
@allure.title("Двухпальцевый вертикальный драг меняет яркость; ниже минимума — чёрный overlay")
def test_two_finger_drag_changes_brightness(clean_app, driver):
    # Given на Browse открыта страница AO3, яркость на дефолтном уровне (1.0, оверлея
    # нет), side panel свёрнут — жест выполняется по области контента
    app_steps.wait_app_ready(driver)
    baseline_luma = browser_steps.measure_screen_luma(driver)

    # When пользователь выполняет двухпальцевый параллельный вертикальный драг вниз,
    # продолжая тянуть за пределы минимальной яркости окна (v < 0 → добавляется
    # чёрный overlay поверх всего экрана, MainActivity.kt overlayAlpha)
    #
    # Известное ограничение автоматизации (см. заметку в TC-055.md): реальная яркость
    # окна (Window.attributes.screenBrightness) не видна UiAutomator2 как UI-элемент,
    # а HUD-индикатор яркости — тот же непригодный для наблюдения LevelIndicator, что
    # и у шрифта (TC-053). Прокси — средняя яркость (luma) полноэкранного скриншота:
    # и снижение реальной яркости окна, и появление чёрного overlay одинаково
    # затемняют кадр, так что комбинированный эффект наблюдаем одним сигналом.
    browser_steps.drag_brightness_down(driver)

    # Then кадр заметно темнее — снижена реальная яркость окна и/или включён overlay
    darkened_luma = browser_steps.measure_screen_luma(driver)
    assert darkened_luma < baseline_luma * 0.7, (
        f"экран не потемнел после драга вниз: {baseline_luma:.1f} -> {darkened_luma:.1f}"
    )

    # When пользователь выполняет обратный драг вверх
    browser_steps.drag_brightness_up(driver)

    # Then overlay убран и яркость повышена обратно — кадр заметно светлее тёмного состояния
    restored_luma = browser_steps.measure_screen_luma(driver)
    assert restored_luma > darkened_luma * 1.3, (
        f"экран не посветлел после драга вверх: {darkened_luma:.1f} -> {restored_luma:.1f}"
    )


@pytest.mark.p3
@pytest.mark.live
@allure.id("TC-057")
@allure.title("Кнопка Home в side panel переводит активную вкладку на главную страницу AO3")
def test_side_panel_home_navigates_active_tab_to_ao3_root(clean_app, driver):
    # Given активная вкладка Browse открыта НЕ на главной AO3 — страница работы с
    # синтетическим ao3_id (реальный сайт отдаёт 404, но URL меняется, что и нужно
    # для Given). Ждём именно оседания стартовой live-загрузки Home
    # (`wait_app_ready`), а не только присутствия нативной оболочки
    # (`wait_ui_ready`) — иначе `open_work_page` навигирует WebView (`driver.get`)
    # ПОКА стартовая загрузка archiveofourown.org ещё в полёте, и chromedriver
    # теряет цель (`cannot determine loading status from no such window`,
    # см. «Ревью автотеста» TC-057.md). side panel развёрнут и показывает иконку Home
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, W.LOVED.ao3_id)
    side_panel_steps.expand(driver)
    side_panel_steps.assert_home_icon_visible(driver)

    # When пользователь нажимает иконку Home в side panel
    side_panel_steps.tap_home(driver)

    # Then WebView активной вкладки загружает главную страницу AO3 (URL становится
    # равен HOME_URL)
    browser_steps.assert_active_tab_url(driver, browser_steps.HOME_URL)
    # And side panel сворачивается автоматически (без отдельного действия пользователя)
    side_panel_steps.assert_collapsed(driver)
