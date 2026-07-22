"""Бизнес-шаги accessibility-инспекции (TC-106): чтение content-desc/text уже
отрисованных контролов accessibility-дерева, БЕЗ взаимодействия с самими
контролами (раскрытие панелей — подготовка состояния Given, не часть Then).
Локаторы переиспользуются из уже существующих screen-модулей (`RatingOverlay`/
`SidePanel`/`BrowserScreen`) — здесь не заводится ни одного нового локатора,
только композиция + чтение атрибутов через `BaseScreen.label_of`.
"""
from __future__ import annotations

import allure

from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav
from framework.screens.rating_overlay import RATING_BUTTON_LABEL, RatingOverlay
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
