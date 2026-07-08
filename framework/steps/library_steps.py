"""Бизнес-шаги экрана Library (GWT)."""
from __future__ import annotations

import allure

from framework.screens.library_screen import FILES_TAB, TAB_BY_RATING, LibraryScreen


@allure.step("When открыта вкладка Library для рейтинга {rating}")
def open_library_tab_for(driver, rating: str):
    LibraryScreen(driver).open_tab_for_rating(rating)


@allure.step("When открыта вкладка Library FILES")
def open_files_tab(driver):
    LibraryScreen(driver).open_tab(FILES_TAB)


@allure.step("Then виден таб Favorite (Library загрузился)")
def assert_library_loaded(driver):
    assert LibraryScreen(driver).has_work("FAVORITE", timeout=8), (
        "экран Library не отрисовался (не видна вкладка FAVORITE)"
    )


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


@allure.step("Then во вкладке FILES присутствует работа «{title}»")
def assert_work_in_files_tab(driver, title: str):
    lib = LibraryScreen(driver).open_tab(FILES_TAB)
    assert lib.has_work(title), f"работа «{title}» не найдена во вкладке FILES"


@allure.step("Then во вкладке FILES НЕТ работы «{title}»")
def assert_work_not_in_files_tab(driver, title: str):
    lib = LibraryScreen(driver).open_tab(FILES_TAB)
    assert not lib.has_work(title, timeout=4), (
        f"работа «{title}» неожиданно присутствует во вкладке FILES"
    )


@allure.step("When пользователь тапает open-иконку работы «{title}» (открыть скачанный файл)")
def open_downloaded_file(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.tap_open_icon()


@allure.step("When long-press по карточке «{title}», в overlay выбрано «{action}»")
def delete_via_overlay(driver, title: str, action: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.long_press_work(title)
    assert lib.delete_overlay_visible(), "overlay удаления не появился после long-press"
    if action == "Delete work":
        lib.tap_delete_work()
    elif action == "Delete downloaded file":
        lib.tap_delete_downloaded_file()
    else:
        raise ValueError(f"неизвестное действие overlay: {action}")


@allure.step("Then карточка «{title}» показывает download-иконку (файл не скачан)")
def assert_download_icon_shown(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    assert lib.has_download_icon(), f"download-иконка не появилась у «{title}»"


@allure.step("Then карточка «{title}» показывает open-иконку (файл скачан)")
def assert_open_icon_shown(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    assert lib.has_open_icon(), f"open-иконка не появилась у «{title}»"
