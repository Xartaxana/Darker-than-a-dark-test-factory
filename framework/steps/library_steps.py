"""Бизнес-шаги экрана Library (GWT)."""
from __future__ import annotations

import allure

from framework.screens.library_screen import TAB_BY_RATING, LibraryScreen


@allure.step("When открыта вкладка Library для рейтинга {rating}")
def open_library_tab_for(driver, rating: str):
    LibraryScreen(driver).open_tab_for_rating(rating)


@allure.step("Then во вкладке {rating} присутствует работа «{title}»")
def assert_work_in_tab(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )


@allure.step("Then во вкладке {rating} НЕТ работы «{title}»")
def assert_work_not_in_tab(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert not lib.has_work(title, timeout=4), (
        f"работа «{title}» неожиданно присутствует во вкладке {TAB_BY_RATING[rating]}"
    )
