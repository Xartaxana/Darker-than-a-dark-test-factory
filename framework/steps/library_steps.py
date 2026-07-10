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


# --- Фильтр-панель (TC-027/TC-028/TC-029) ---

@allure.step("When пользователь открывает фильтр-панель Library")
def open_library_filter_sheet(driver):
    lib = LibraryScreen(driver)
    lib.open_filter_sheet()
    assert lib.is_filter_sheet_open(), "фильтр-панель Library не открылась"


@allure.step("When пользователь задаёт диапазон word count min={min_words} max={max_words} и применяет фильтр")
def apply_word_count_filter(driver, min_words: str = "", max_words: str = ""):
    lib = LibraryScreen(driver)
    if min_words:
        lib.set_min_words(min_words)
    if max_words:
        lib.set_max_words(max_words)
    lib.tap_apply_filters()


@allure.step("When пользователь выбирает фандом «{fandom}» в фильтр-панели и применяет фильтр")
def apply_fandom_filter(driver, fandom: str):
    lib = LibraryScreen(driver)
    lib.open_fandom_picker()
    lib.select_fandom_option(fandom)
    lib.tap_apply_filters()


@allure.step("When пользователь устанавливает чекбокс downloaded-only={checked} и применяет фильтр")
def apply_downloaded_only_filter(driver, checked: bool):
    lib = LibraryScreen(driver)
    lib.set_downloaded_only(checked)
    lib.tap_apply_filters()


# --- Сортировка (TC-030) ---

@allure.step("When запомнена исходная Y-позиция верхней видимой карточки")
def capture_topmost_card_y(driver, known_titles: list[str]) -> int:
    lib = LibraryScreen(driver)
    top = lib.topmost_visible_title(known_titles)
    assert top is not None, "не удалось определить верхнюю видимую карточку из известных"
    return lib.visible_card_y(top)


@allure.step("When список Library проскроллен вниз (виден маркер «{marker_title}»)")
def scroll_library_down_to(driver, marker_title: str):
    lib = LibraryScreen(driver)
    assert lib.swipe_to_text(marker_title), (
        f"не удалось проскроллить список Library до «{marker_title}»"
    )


@allure.step("When пользователь открывает dropdown сортировки в top bar и выбирает «{label}»")
def select_library_sort(driver, label: str, current_label: str = "Last read"):
    lib = LibraryScreen(driver)
    lib.open_sort_menu(current_label=current_label)
    lib.select_sort_option(label)


@allure.step("Then список упорядочен по убыванию word_count: {titles_desc}")
def assert_sorted_by_wordcount_desc(driver, titles_desc: list[str]):
    lib = LibraryScreen(driver)
    positions = [(t, lib.visible_card_y(t)) for t in titles_desc]
    missing = [t for t, y in positions if y is None]
    assert not missing, f"после сортировки не видны карточки: {missing}"
    ys = [y for _, y in positions]
    assert ys == sorted(ys), (
        f"порядок карточек не соответствует убыванию word_count: {positions}"
    )


@allure.step("Then триггер сортировки в top bar показывает «{label}»")
def assert_sort_trigger_label(driver, label: str):
    lib = LibraryScreen(driver)
    actual = lib.sort_trigger_label()
    assert actual == label, f"иконка-триггер сортировки не сменилась на «{label}» (сейчас: «{actual}»)"


@allure.step("Then список визуально сброшен к началу (карточка «{title}» на исходной Y-позиции)")
def assert_scroll_reset_to_top(driver, title: str, baseline_y: int, tolerance: int = 60):
    lib = LibraryScreen(driver)
    y = lib.visible_card_y(title)
    assert y is not None, f"карточка «{title}» не видна после сортировки"
    assert abs(y - baseline_y) <= tolerance, (
        f"скролл не сброшен к началу: карточка «{title}» на Y={y}, ожидалось около {baseline_y}"
    )
