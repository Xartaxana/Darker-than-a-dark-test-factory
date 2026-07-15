"""Бизнес-шаги Side panel на Browse (GWT) — тема и размер шрифта из панели.
Единственный слой (наравне с другими steps/*), где допустим allure.step."""
from __future__ import annotations

import allure

from framework.screens.side_panel import SidePanel, TO_DARK, TO_LIGHT


@allure.step("When side panel развёрнут")
def expand(driver):
    SidePanel(driver).expand()


@allure.step("When side panel свёрнут")
def collapse(driver):
    SidePanel(driver).collapse()


@allure.step("Then side panel показывает тему Light (иконка «Switch to dark mode»)")
def assert_theme_is_light(driver):
    assert SidePanel(driver).theme_desc_visible(TO_DARK), \
        "ожидали иконку Contrast «Switch to dark mode» (тема Light)"


@allure.step("Then side panel показывает тему Dark (иконка «Switch to light mode»)")
def assert_theme_is_dark(driver):
    assert SidePanel(driver).theme_desc_visible(TO_LIGHT), \
        "ожидали иконку Contrast «Switch to light mode» (тема Dark)"


@allure.step("When нажата иконка Contrast (side panel)")
def toggle_theme(driver):
    SidePanel(driver).tap_contrast()


@allure.step("When нажата «A+» (side panel)")
def increase_font(driver):
    SidePanel(driver).increase_font()


@allure.step("When нажата «A-» (side panel)")
def decrease_font(driver):
    SidePanel(driver).decrease_font()


@allure.step("Then кнопка «A+» enabled={expected}")
def assert_increase_enabled(driver, expected: bool):
    actual = SidePanel(driver).is_increase_enabled()
    assert actual == expected, f"«A+» enabled={actual}, ожидали {expected}"


@allure.step("Then кнопка «A-» enabled={expected}")
def assert_decrease_enabled(driver, expected: bool):
    actual = SidePanel(driver).is_decrease_enabled()
    assert actual == expected, f"«A-» enabled={actual}, ожидали {expected}"


@allure.step("Then side panel показывает иконку Home («AO3 home»)")
def assert_home_icon_visible(driver):
    assert SidePanel(driver).home_icon_visible(), \
        "иконка Home («AO3 home») не видна в развёрнутой side panel"


@allure.step("When нажата иконка Home (side panel)")
def tap_home(driver):
    SidePanel(driver).tap_home()


@allure.step("Then side panel свёрнута автоматически (без отдельного действия)")
def assert_collapsed(driver):
    assert SidePanel(driver).is_collapsed(), \
        "side panel должна была свернуться автоматически после нажатия Home"
