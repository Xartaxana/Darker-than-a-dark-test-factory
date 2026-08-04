"""Бизнес-шаги accessibility-инспекции (TC-106, TC-148): чтение content-desc/
text/bounds уже отрисованных контролов accessibility-дерева, БЕЗ
взаимодействия с самими контролами (раскрытие панелей — подготовка состояния
Given, не часть Then). Локаторы переиспользуются из уже существующих
screen-модулей (`RatingOverlay`/`SidePanel`/`BrowserScreen`/`LibraryScreen`/
`SettingsScreen`) — здесь не заводится ни одного нового локатора, только
композиция + чтение атрибутов через `BaseScreen.label_of`/`.rect`.

TC-148 (свип touch-target >= 48dp): функции `measure_*` — это When-шаги,
накапливающие `(имя_цели, rect)` по именованному списку целей маршрута
(bounds = ВНЕШНИЙ кликабельный узел, не текстовый потомок — см. докстринги
`side_panel.py::_button_container`/`settings_screen.py::*_button_locator`);
`assert_touch_targets_at_least_48dp` — единственный Then, проверяющий
инвариант «>= 48dp» ОДНОВРЕМЕННО для всего накопленного списка (не по одной
цели за раз — см. «Инвариант» TC-148.md)."""
from __future__ import annotations

import allure

from framework.screens.browser_screen import BrowserScreen
from framework.screens.library_screen import FILES_TAB, TAB_BY_RATING, LibraryScreen
from framework.screens.navigation import BottomNav
from framework.screens.rating_overlay import RATING_BUTTON_LABEL, RatingOverlay
from framework.screens.settings_screen import THEME_LABELS, SettingsScreen
from framework.screens.side_panel import TO_DARK, TO_LIGHT, SidePanel


@allure.step("Given раскрыта встроенная панель рейтинга (RatingMenu) на текущей странице работы")
def expand_rating_panel(driver):
    """Раскрывает нижнюю навигацию (пилюлю) — на вкладке Browse с открытой
    страницей работы это делает видимой встроенную панель `WorkRatingPanel`
    (`RatingMenu`, тот же composable, что и bottom-sheet листинга, см.
    `rating_steps.rate_current_work`)."""
    BottomNav(driver).ensure_visible()


def _assert_label(node_description: str, desc: str, text: str) -> None:
    assert desc.strip() or text.strip(), (
        f"{node_description}: и content-desc, и text пусты — узел не несёт "
        f"accessibility-лейбла (ни один канал не читаем screen reader'ом)"
    )


@allure.step("Then каждая кнопка рейтинга в RatingMenu несёт непустой content-desc или видимый text")
def assert_rating_buttons_labeled(driver) -> None:
    overlay = RatingOverlay(driver)
    for rating, label in RATING_BUTTON_LABEL.items():
        desc, text = overlay.label_of(overlay.by_text(label))
        _assert_label(f"кнопка рейтинга {rating} ({label!r})", desc, text)


@allure.step("Then кнопка заметки (Note) в RatingMenu несёт непустой content-desc или видимый text")
def assert_note_button_labeled(driver) -> None:
    overlay = RatingOverlay(driver)
    locator = (
        overlay.by_text("Hide note")
        if overlay.is_present(overlay.by_text("Hide note"), timeout=2)
        else overlay.by_text("Add a note")
    )
    desc, text = overlay.label_of(locator)
    _assert_label("кнопка заметки (Note)", desc, text)


@allure.step("Then переключатель темы в side panel несёт непустой content-desc")
def assert_theme_toggle_labeled(driver) -> None:
    panel = SidePanel(driver)
    desc_value = TO_DARK if panel.is_present(panel.by_desc(TO_DARK), timeout=2) else TO_LIGHT
    desc, text = panel.label_of(panel.by_desc(desc_value))
    _assert_label(f"переключатель темы ({desc_value!r})", desc, text)


@allure.step("Then контролы размера шрифта (A-/A+) в side panel несут непустой content-desc или видимый text")
def assert_font_size_controls_labeled(driver) -> None:
    panel = SidePanel(driver)
    for label in ("A-", "A+"):
        desc, text = panel.label_of(panel.by_text(label))
        _assert_label(f"кнопка размера шрифта {label!r}", desc, text)


@allure.step("Then контролы TabStrip (New tab/Close tab/сам таб) несут непустой content-desc или видимый text")
def assert_tab_strip_controls_labeled(driver) -> None:
    screen = BrowserScreen(driver)
    for desc_value in (screen.NEW_TAB_DESC, screen.CLOSE_TAB_DESC):
        desc, text = screen.label_of(screen.by_desc(desc_value))
        _assert_label(f"кнопка TabStrip {desc_value!r}", desc, text)
    title = screen.tab_chip_title_at(0)
    assert title.strip(), "заголовок первого таба в TabStrip пуст (ни один канал не читаем)"


# --- TC-148: свип touch-target >= 48dp по именованному списку целей маршрута ---
# `Measurement = (имя_цели, rect)`, rect — словарь Selenium/Appium `.rect`
# (`{"x":..,"y":..,"width":..,"height":..}`) в device px.

LIBRARY_TAB_LABELS: tuple[str, ...] = (
    TAB_BY_RATING["SAVE"], TAB_BY_RATING["LIKE"], TAB_BY_RATING["READ"],
    TAB_BY_RATING["DISLIKE"], FILES_TAB,
)  # Loved/Liked/Read/Disliked/Downloads (PROJECT.md-имена) -> UI-подписи (library_screen.py)

SETTINGS_THEME_MODES: tuple[str, ...] = ("LIGHT", "DARK", "SYSTEM")
SETTINGS_FONT_STEPS: range = range(7)
SETTINGS_PANEL_SIDES: tuple[str, ...] = ("Left", "Right")


@allure.step("When накопление bounds: нижняя 20dp полоса-хэндл нижней панели (Browse, навигация свёрнута)")
def measure_bottom_bar_handle(driver) -> list[tuple[str, dict]]:
    """BottomBar.kt:56 — Box без text/content-desc, самый нижний кликабельный
    не-WebView элемент, ПОКА нижняя навигация свёрнута за ручкой-пилюлей
    (`BottomNav.pill_element`, тот же приём, что `BottomNav._expand_pill`
    использует для клика). Явный guard `is_visible()`, а не молчаливое
    предположение о состоянии: при развёрнутой навигации самым нижним
    кликабельным окажется ДРУГОЙ элемент (последний пункт NavigationBar),
    измерение молча съехало бы на чужую цель."""
    nav = BottomNav(driver)
    assert not nav.is_visible(timeout=2), (
        "нижняя навигация (BottomNav) неожиданно уже развёрнута — полоса-хэндл "
        "измеряется в СВЁРНУТОМ состоянии навигации (Given TC-148); в развёрнутом "
        "состоянии «самый нижний кликабельный элемент» — уже не эта цель"
    )
    handle = nav.pill_element()
    assert handle is not None, "полоса-хэндл нижней панели не найдена (BottomBar.kt:56)"
    return [("BottomBar: 20dp полоса-хэндл нижней панели", handle.rect)]


@allure.step("When накопление bounds: handle «Expand panel» (Browse, side panel свёрнута)")
def measure_side_panel_collapsed_handle(driver) -> list[tuple[str, dict]]:
    """BrowseSidePanel.kt:154 — известный кандидат ниже порога (docs/01 §9,
    CH-005: 32×32 px на эталонном AVD). Явный guard состояния — тот же приём,
    что `measure_bottom_bar_handle`."""
    panel = SidePanel(driver)
    assert not panel.is_expanded(), (
        "side panel неожиданно уже развёрнута — handle «Expand panel» "
        "измеряется в СВЁРНУТОМ состоянии панели (Given TC-148)"
    )
    el = panel.find(panel.by_desc("Expand panel"))
    return [('side panel: handle «Expand panel»', el.rect)]


@allure.step("When накопление bounds: контролы раскрытой side panel (тема, A-/A+)")
def measure_side_panel_expanded_controls(driver) -> list[tuple[str, dict]]:
    panel = SidePanel(driver)
    assert panel.is_expanded(), (
        "side panel не раскрылась — ожидали персистентный toggle-стейт после "
        "`side_panel_steps.expand` (Given TC-148: раскрытие ОТДЕЛЬНЫМ шагом)"
    )
    theme_desc = TO_DARK if panel.is_present(panel.by_desc(TO_DARK), timeout=2) else TO_LIGHT
    theme_el = panel.find(panel.by_desc(theme_desc))
    minus_el = panel.find(panel.font_button_container("A-"))
    plus_el = panel.find(panel.font_button_container("A+"))
    return [
        (f'side panel: переключатель темы (Contrast, «{theme_desc}»)', theme_el.rect),
        ('side panel: кнопка размера шрифта «A-»', minus_el.rect),
        ('side panel: кнопка размера шрифта «A+»', plus_el.rect),
    ]


@allure.step("When накопление bounds: TabStrip (New tab, Close tab, таб-чип #0)")
def measure_tab_strip_targets(driver) -> list[tuple[str, dict]]:
    """TabStrip.kt: `New tab` — IconButton(36dp)-обёрнутая Icon(20dp,
    desc="New tab"); `Close tab` — Icon(14dp) с `.clickable` НА САМОЙ
    иконке (contentDescription="Close tab") и clickable в ОДНОМ узле, без
    обёртки; сам таб-чип — родительский Row чипа через уже существующий
    `tab_chip_locator` (клик по чипу целится в него же, не в 14dp иконку
    закрытия — см. докстринг `tab_chip_locator`)."""
    screen = BrowserScreen(driver)
    new_tab_el = screen.find(screen.by_desc(screen.NEW_TAB_DESC))
    close_tab_els = screen.driver.find_elements(*screen.by_desc(screen.CLOSE_TAB_DESC))
    assert close_tab_els, (
        "ни одной кнопки «Close tab» не найдено в дереве — ожидали >=2 вкладки "
        "(TabStrip виден, Given TC-148)"
    )
    chip_el = screen.find(screen.tab_chip_locator(0))
    out = [('TabStrip: кнопка «New tab»', new_tab_el.rect)]
    for i, el in enumerate(close_tab_els):
        out.append((f'TabStrip: кнопка «Close tab» #{i}', el.rect))
    out.append(("TabStrip: таб-чип #0", chip_el.rect))
    return out


@allure.step("When накопление bounds: чипы табов Library ({labels})")
def measure_library_tab_chips(driver, labels: tuple[str, ...] = LIBRARY_TAB_LABELS) -> list[tuple[str, dict]]:
    """LibraryScreen.kt: `Tab(modifier=Modifier.height(48.dp))` с
    content-lambda `Text(tab.label.uppercase())` — тот же composable, что
    уже кликается по `by_text(label)` в `LibraryScreen.open_tab` (не новый
    локатор, переиспользование)."""
    screen = LibraryScreen(driver)
    out = []
    for label in labels:
        el = screen.find(screen.by_text(label))
        out.append((f'Library: таб «{label}»', el.rect))
    return out


@allure.step("When накопление bounds: контролы Settings (ThemeModeRow, PanelSideRow, FontSizeRow)")
def measure_settings_controls(driver) -> list[tuple[str, dict]]:
    screen = SettingsScreen(driver)
    out = []
    for mode in SETTINGS_THEME_MODES:
        el = screen.find(screen.theme_button_locator(mode))
        out.append((f'Settings ThemeModeRow: «{THEME_LABELS[mode]}»', el.rect))
    for side in SETTINGS_PANEL_SIDES:
        el = screen.find(screen.panel_side_button_locator(side))
        out.append((f'Settings PanelSideRow: «{side}»', el.rect))
    for step in SETTINGS_FONT_STEPS:
        el = screen.find(screen.font_size_button_locator(step))
        out.append((f"Settings FontSizeRow: шаг {step}", el.rect))
    return out


@allure.step("Then все именованные цели маршрута >= 48dp по bounds accessibility-дерева (density={density})")
def assert_touch_targets_at_least_48dp(measurements: list[tuple[str, dict]], density: int) -> None:
    """Инвариант TC-148: свойство «bounds >= 48dp» проверяется КАК СВОЙСТВО,
    верное ОДНОВРЕМЕННО для ВСЕГО поимённого списка целей маршрута — находка
    ниже порога по ЛЮБОЙ цели красит ВЕСЬ прогон этого Then, список не
    сужается выборочно (см. «Инвариант» TC-148.md). `48 * density / 160` —
    РЕАЛЬНАЯ плотность ТЕКУЩЕГО прогона (`app_steps.measure_screen_density`),
    НЕ хардкод константы из документации."""
    threshold_px = 48 * density / 160
    rows = []
    failures = []
    for name, rect in measurements:
        w, h = rect["width"], rect["height"]
        w_dp, h_dp = w * 160 / density, h * 160 / density
        rows.append(f"{name}: bounds={w}x{h}px ({w_dp:.1f}x{h_dp:.1f}dp)")
        if w < threshold_px or h < threshold_px:
            failures.append(
                f"{name}: bounds={w}x{h}px ({w_dp:.1f}x{h_dp:.1f}dp @density={density}) "
                f"< порог {threshold_px:.1f}px (48dp)"
            )
    allure.attach(
        "\n".join(rows),
        name=f"TC-148 замеры (density={density}, порог={threshold_px:.1f}px)",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert not failures, (
        f"{len(failures)} из {len(measurements)} именованных целей маршрута ниже порога "
        f"48dp (density={density}, порог={threshold_px:.1f}px):\n" + "\n".join(failures)
    )
