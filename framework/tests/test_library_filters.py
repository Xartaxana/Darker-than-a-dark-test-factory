"""Тесты фильтр-панели и сортировки экрана Library (TC-027/TC-028/TC-029/TC-030).
Полностью на сидинге Room, без обращения к живому AO3 (см. test_library.py —
тот же дизайн, минимизация сети)."""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.steps import app_steps, library_steps


@pytest.mark.p1
@allure.id("TC-027")
@allure.title("Фильтр word count min/max сужает список работ на вкладке Library")
def test_library_filter_word_count_range(library_all_one_rating_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")
    # Given на вкладке видно все 5 работ (300/800/1500/4200/12000 слов)
    for w in library_all_one_rating_seeded:
        library_steps.assert_work_in_tab(driver, "PENDING", w.title)

    # When пользователь задаёт диапазон word count 1000-5000 и применяет фильтр
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_word_count_filter(driver, min_words="1000", max_words="5000")

    # Then остаются только работы с word_count в [1000, 5000] — KUDOSED (1500), LOVED (4200)
    library_steps.assert_work_in_tab(driver, "PENDING", W.KUDOSED.title)
    library_steps.assert_work_in_tab(driver, "PENDING", W.LOVED.title)
    # And работы с 300, 800 и 12000 не отображаются
    library_steps.assert_work_not_in_tab(driver, "PENDING", W.DISLIKED.title)
    library_steps.assert_work_not_in_tab(driver, "PENDING", W.READ.title)
    library_steps.assert_work_not_in_tab(driver, "PENDING", W.PENDING.title)


@pytest.mark.p1
@allure.id("TC-028")
@allure.title("Чекбокс downloaded-only фильтрует по наличию файла")
def test_library_filter_downloaded_only(library_downloaded_only_seeded, driver):
    downloaded = library_downloaded_only_seeded["downloaded"]
    no_file = library_downloaded_only_seeded["no_file"]
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "SAVE")
    # Given на вкладке видно 3 работы, из которых только 1 имеет скачанный файл
    for w in (downloaded, *no_file):
        library_steps.assert_work_in_tab(driver, "SAVE", w.title)

    # When пользователь включает чекбокс "downloaded-only"
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_downloaded_only_filter(driver, True)

    # Then список показывает только работу со скачанным файлом
    library_steps.assert_work_in_tab(driver, "SAVE", downloaded.title)
    # And остальные 2 работы (без файла) скрыты
    for w in no_file:
        library_steps.assert_work_not_in_tab(driver, "SAVE", w.title)

    # And выключение чекбокса возвращает список ко всем 3 работам
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_downloaded_only_filter(driver, False)
    for w in (downloaded, *no_file):
        library_steps.assert_work_in_tab(driver, "SAVE", w.title)


@pytest.mark.p1
@allure.id("TC-029")
@allure.title("Фильтр по фандому сужает список до совпадающих работ")
def test_library_filter_by_fandom(library_all_one_rating_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")
    # Given на вкладке видно 5 работ с разными значениями фандома
    for w in library_all_one_rating_seeded:
        library_steps.assert_work_in_tab(driver, "PENDING", w.title)

    # When пользователь выбирает фандом "Fandom Alpha" (LOVED.fandom) и применяет фильтр
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_fandom_filter(driver, W.LOVED.fandom)

    # Then список показывает только работу с этим фандомом
    library_steps.assert_work_in_tab(driver, "PENDING", W.LOVED.title)
    # And остальные 4 работы с другими фандомами скрыты
    for w in library_all_one_rating_seeded:
        if w is not W.LOVED:
            library_steps.assert_work_not_in_tab(driver, "PENDING", w.title)


@pytest.mark.p1
@allure.id("TC-030")
@allure.title("Сортировка Word count (high to low) упорядочивает список и сбрасывает скролл")
def test_library_sort_wordcount_desc_resets_scroll(library_wordcount_scroll_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")

    # Given список содержит работы с разным word_count, запоминаем исходную Y-позицию
    # верхней карточки (маркер "верха списка" для проверки сброса скролла позже)
    known_titles = [w.title for w in library_wordcount_scroll_seeded]
    baseline_y = library_steps.capture_topmost_card_y(driver, known_titles)

    # ...и скроллим список вниз (не на самом верху)
    last_filler = W.SCROLL_FILLERS[-1]
    library_steps.scroll_library_down_to(driver, last_filler.title)

    # When пользователь выбирает сортировку "Word count" (high to low)
    library_steps.select_library_sort(driver, "Word count (high to low)")

    # Then список переупорядочен по убыванию word_count (12000, 4200, 1500, 800, 300)
    desc_order = [W.PENDING.title, W.LOVED.title, W.KUDOSED.title, W.READ.title, W.DISLIKED.title]
    library_steps.assert_sorted_by_wordcount_desc(driver, desc_order)
    # And иконка-триггер в top bar сменилась на иконку выбранной сортировки
    library_steps.assert_sort_trigger_label(driver, "Word count (high to low)")
    # And список визуально сброшен к началу (карточка с макс. word_count — на исходной Y-позиции)
    library_steps.assert_scroll_reset_to_top(driver, W.PENDING.title, baseline_y)
