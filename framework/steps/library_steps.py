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


@allure.step("Then вкладки Library идут слева направо: {labels}")
def assert_library_tabs_order(driver, labels: list[str]):
    lib = LibraryScreen(driver)
    positions = [(label, lib.tab_label_x(label)) for label in labels]
    missing = [label for label, x in positions if x is None]
    assert not missing, f"вкладки не найдены: {missing}"
    xs = [x for _, x in positions]
    assert xs == sorted(xs), (
        f"порядок вкладок слева направо не соответствует ожидаемому: {positions}"
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


@allure.step("Then во вкладке {rating} работа «{title}» показывает личные теги «{tags_text}»")
def assert_work_tags_visible(driver, rating: str, title: str, tags_text: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )
    assert lib.has_tags_text(tags_text), (
        f"личные теги «{tags_text}» не отображены на карточке «{title}»"
    )


@allure.step("Then во вкладке {rating} работа «{title}» показывает note-иконку (сохранённый комментарий)")
def assert_work_note_icon_visible(driver, rating: str, title: str):
    lib = LibraryScreen(driver).open_tab_for_rating(rating)
    assert lib.has_work(title), (
        f"работа «{title}» не найдена во вкладке {TAB_BY_RATING[rating]}"
    )
    assert lib.has_note_icon(), (
        f"note-иконка не отображена на карточке «{title}»"
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


@allure.step("When работа «{title}» открыта из Library в Browse (добавляется вкладка)")
def open_work_in_browser(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена в Library"
    lib.open_work(title)


@allure.step("When пользователь тапает open-иконку работы «{title}» (открыть скачанный файл)")
def open_downloaded_file(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.tap_open_icon()


@allure.step("When пользователь тапает download-иконку работы «{title}» (ручное скачивание)")
def download_via_card(driver, title: str):
    lib = LibraryScreen(driver)
    assert lib.has_work(title), f"работа «{title}» не найдена"
    lib.tap_download_icon()


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
def assert_open_icon_shown(driver, title: str, timeout: int | None = None):
    """`timeout` — явный override дефолта (8с): скачивание через сеть (TC-032/033,
    DownloadRepository.downloadWork через replay-прокси) асинхронное и медленнее,
    чем локальная фикстура (downloaded_work_seeded), где дефолта достаточно."""
    lib = LibraryScreen(driver)
    assert lib.has_work(title, timeout=timeout), f"работа «{title}» не найдена"
    assert lib.has_open_icon(timeout=timeout), f"open-иконка не появилась у «{title}»"


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


# --- Личные теги / свободный текст (TC-060/TC-061) ---

@allure.step("When пользователь выбирает теги {tags} в фильтр-панели и применяет фильтр")
def apply_tags_filter(driver, tags: list[str]):
    lib = LibraryScreen(driver)
    for tag in tags:
        lib.select_tag(tag)
    lib.tap_apply_filters()


@allure.step("When пользователь вводит запрос «{query}» в поле «Search any field» и применяет фильтр")
def apply_search_filter(driver, query: str):
    lib = LibraryScreen(driver)
    lib.set_search_query(query)
    lib.tap_apply_filters()


@allure.step("When пользователь очищает поле поиска (крестик) и применяет фильтр")
def clear_search_filter(driver):
    lib = LibraryScreen(driver)
    lib.clear_search_query()
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


@allure.step("Then опция сортировки «{label}» недоступна на текущей вкладке")
def assert_sort_option_unavailable(driver, label: str, current_label: str = "Last read"):
    """Открывает dropdown сортировки, проверяет отсутствие опции `label` среди
    видимых пунктов, закрывает dropdown БЕЗ выбора (TC-065: "Rating" существует
    только на вкладке Files/Downloads, `librarySortOptionsFor(isFilesTab)`)."""
    lib = LibraryScreen(driver)
    lib.open_sort_menu(current_label=current_label)
    assert not lib.is_present(lib.by_text(label), timeout=3), (
        f"опция сортировки «{label}» неожиданно доступна вне вкладки Files"
    )
    lib.close_sort_menu()


@allure.step("Then карточки видны в порядке: {titles_in_order}")
def assert_cards_in_order(driver, titles_in_order: list[str]):
    """Обобщение `assert_sorted_by_wordcount_desc` на произвольный порядок/поле
    сортировки (TC-031/TC-062/TC-063/TC-064/TC-065) — сравнивает видимые
    Y-координаты перечисленных карточек, не зависит от того, где среди них
    оказались посторонние (не перечисленные) карточки/филлеры."""
    lib = LibraryScreen(driver)
    positions = [(t, lib.visible_card_y(t)) for t in titles_in_order]
    missing = [t for t, y in positions if y is None]
    assert not missing, f"не видны карточки: {missing}"
    ys = [y for _, y in positions]
    assert ys == sorted(ys), (
        f"порядок карточек не соответствует ожидаемому: {positions}"
    )


@allure.step("Then список визуально сброшен к началу (карточка «{title}» на исходной Y-позиции)")
def assert_scroll_reset_to_top(driver, title: str, baseline_y: int, tolerance: int = 60):
    lib = LibraryScreen(driver)
    y = lib.visible_card_y(title)
    assert y is not None, f"карточка «{title}» не видна после сортировки"
    assert abs(y - baseline_y) <= tolerance, (
        f"скролл не сброшен к началу: карточка «{title}» на Y={y}, ожидалось около {baseline_y}"
    )


# --- Пустая вкладка (TC-037: Library остаётся пустой после диалога Scan "0 файлов") ---

@allure.step("Then текущая вкладка Library пуста («Nothing here yet»)")
def assert_library_empty(driver, timeout: int | None = None):
    assert LibraryScreen(driver).is_empty(timeout=timeout), (
        "Library не пуста — ожидали пустое состояние «Nothing here yet»"
    )
