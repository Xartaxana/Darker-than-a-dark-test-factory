"""Тесты фильтр-панели и сортировки экрана Library (TC-027/TC-028/TC-029/TC-030,
TC-031, TC-060/TC-061/TC-062/TC-063/TC-064/TC-065). Полностью на сидинге Room,
без обращения к живому AO3 (см. test_library.py — тот же дизайн, минимизация
сети)."""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.steps import app_steps, library_steps


@pytest.mark.p1
@allure.id("TC-027")
@allure.title("Фильтр word count min/max сужает список работ на вкладке Library")
def test_library_filter_word_count_range(library_word_count_boundary_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")
    # Given на вкладке видно все 7 работ (300/800/1000/1500/4200/5000/12000 слов —
    # 5 исходных + 2 граничных, C4-ретрофит 2026-07-18)
    for w in library_word_count_boundary_seeded:
        library_steps.assert_work_in_tab(driver, "PENDING", w.title)

    # When пользователь задаёт диапазон word count 1000-5000 и применяет фильтр
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_word_count_filter(driver, min_words="1000", max_words="5000")

    # Then остаются только работы с word_count в [1000, 5000] — KUDOSED (1500), LOVED (4200)
    library_steps.assert_work_in_tab(driver, "PENDING", W.KUDOSED.title)
    library_steps.assert_work_in_tab(driver, "PENDING", W.LOVED.title)
    # And включительность границ: work'ы с word_count РОВНО 1000 и РОВНО 5000 тоже
    # видны — фильтр в LibraryScreen.kt:164-169 сравнивает `>= min`/`<= max`, не строго
    # (C4-ретрофит: до этого assert'а граница не была доказана ни одним значением ALL)
    library_steps.assert_work_in_tab(driver, "PENDING", W.WORD_COUNT_MIN_BOUNDARY.title)
    library_steps.assert_work_in_tab(driver, "PENDING", W.WORD_COUNT_MAX_BOUNDARY.title)
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


@pytest.mark.p3
@allure.id("TC-031")
@allure.title("Работы без word_count уходят в конец списка при сортировке Word count")
def test_library_sort_wordcount_null_last(library_null_wordcount_seeded, driver):
    with_wc = library_null_wordcount_seeded["with_wordcount"]  # [READ(800), LOVED(4200)]
    null_wc = library_null_wordcount_seeded["null_wordcount"]
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")

    # Given на вкладке видно 3 работы: две с word_count (800, 4200), одна без (null)
    for w in (*with_wc, null_wc):
        library_steps.assert_work_in_tab(driver, "PENDING", w.title)

    # When пользователь выбирает сортировку "Word count" (low to high — любое
    # направление достаточно, см. заметки кейса: оба направления используют один и
    # тот же первичный ключ "wordCount != null")
    library_steps.select_library_sort(driver, "Word count (low to high)")

    # Then работа без word_count — последняя, а между собой две остальные упорядочены
    # по возрастанию (READ=800 раньше LOVED=4200)
    library_steps.assert_cards_in_order(driver, [w.title for w in with_wc] + [null_wc.title])


@pytest.mark.p1
@allure.id("TC-060")
@allure.title("Фильтр по личным тегам сужает список по AND-семантике")
def test_library_filter_tags_and_semantics(library_tags_and_seeded, driver):
    w1, w2, w3 = library_tags_and_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "SAVE")

    # Given на вкладке видно 3 работы: W1 (fluff+hurt-comfort), W2 (fluff), W3 (canon-divergent)
    for w in (w1, w2, w3):
        library_steps.assert_work_in_tab(driver, "SAVE", w.title)

    # When пользователь выбирает ОБА тега "fluff" и "hurt-comfort" и применяет фильтр
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_tags_filter(driver, ["fluff", "hurt-comfort"])

    # Then список показывает только W1 — единственную работу с ОБОИМИ тегами
    library_steps.assert_work_in_tab(driver, "SAVE", w1.title)
    # And W2 скрыта, несмотря на частичное пересечение (только "fluff")
    library_steps.assert_work_not_in_tab(driver, "SAVE", w2.title)
    # And W3 скрыта полностью (ни одного совпадения)
    library_steps.assert_work_not_in_tab(driver, "SAVE", w3.title)


@pytest.mark.p1
@allure.id("TC-061")
@allure.title("Свободный текстовый поиск по Library сужает список до совпадений в любом поле")
def test_library_filter_freetext_search(library_freetext_search_seeded, driver):
    w1, w2, w3 = library_freetext_search_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "SAVE")

    # Given на вкладке видно 3 работы, только у W1 в comment есть подстрока "wintersong"
    for w in (w1, w2, w3):
        library_steps.assert_work_in_tab(driver, "SAVE", w.title)

    # When пользователь вводит "WinterSong" (смешанный регистр) в поле "Search any
    # field" и применяет фильтр
    library_steps.open_library_filter_sheet(driver)
    library_steps.apply_search_filter(driver, "WinterSong")

    # Then список показывает только W1 (совпадение в comment, регистронезависимо)
    library_steps.assert_work_in_tab(driver, "SAVE", w1.title)
    # And W2 и W3 скрыты (подстрока не встречается ни в одном поле)
    library_steps.assert_work_not_in_tab(driver, "SAVE", w2.title)
    library_steps.assert_work_not_in_tab(driver, "SAVE", w3.title)

    # And очистка поля поиска и повторное применение возвращают список ко всем 3 работам
    library_steps.open_library_filter_sheet(driver)
    library_steps.clear_search_filter(driver)
    for w in (w1, w2, w3):
        library_steps.assert_work_in_tab(driver, "SAVE", w.title)


@pytest.mark.p1
@allure.id("TC-062")
@allure.title("Сортировка Last read (по умолчанию) упорядочивает по недавности обновления рейтинга")
def test_library_sort_last_read_default(library_last_read_order_seeded, driver):
    mango, apple, zebra = library_last_read_order_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "SAVE")

    # Given 3 работы засеяны в хронологическом порядке Mango -> Apple -> Zebra;
    # сортировка не менялась вручную (дефолт LibrarySort.LAST_READ)
    # When пользователь открывает вкладку Library (без действий с dropdown сортировки)
    # Then список показан в порядке Zebra, Apple, Mango — от самой недавно
    # обновлённой к самой старой (не совпадает ни с порядком вставки, ни с алфавитом)
    library_steps.assert_cards_in_order(driver, [zebra.title, apple.title, mango.title])


@pytest.mark.p1
@allure.id("TC-063")
@allure.title("Сортировка Word count (low to high) упорядочивает по возрастанию и сбрасывает скролл")
def test_library_sort_wordcount_asc_resets_scroll(library_wordcount_scroll_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")

    # Given список содержит работы с разным word_count, запоминаем исходную Y-позицию
    # верхней карточки
    known_titles = [w.title for w in library_wordcount_scroll_seeded]
    baseline_y = library_steps.capture_topmost_card_y(driver, known_titles)

    # ...и скроллим список вниз (не на самом верху)
    last_filler = W.SCROLL_FILLERS[-1]
    library_steps.scroll_library_down_to(driver, last_filler.title)

    # When пользователь выбирает сортировку "Word count" (low to high)
    library_steps.select_library_sort(driver, "Word count (low to high)")

    # Then иконка-триггер в top bar сменилась на иконку выбранной сортировки
    library_steps.assert_sort_trigger_label(driver, "Word count (low to high)")
    # And список визуально сброшен к началу — верхняя карточка теперь самый маленький
    # филлер (word_count=11, меньше 300 у DISLIKED — минимум среди ВСЕХ засеянных),
    # проверяем ДО повторного скролла вниз ниже
    library_steps.assert_scroll_reset_to_top(driver, W.SCROLL_FILLERS[0].title, baseline_y)

    # And пять эталонных работ ALL упорядочены между собой по возрастанию word_count
    # (300, 800, 1500, 4200, 12000), независимо от того, где среди них оказались
    # филлеры (word_count 11-20 — меньше самого маленького из ALL, поэтому все 10
    # филлеров идут ПЕРЕД пятёркой ALL — нужно проскроллить вниз, чтобы её увидеть)
    library_steps.scroll_library_down_to(driver, W.PENDING.title)
    asc_order = [W.DISLIKED.title, W.READ.title, W.KUDOSED.title, W.LOVED.title, W.PENDING.title]
    library_steps.assert_cards_in_order(driver, asc_order)


@pytest.mark.p1
@allure.id("TC-064")
@allure.title("Сортировка Author (A–Z), работы с пустым author уходят в конец")
def test_library_sort_author_asc_blank_last(library_author_sort_seeded, driver):
    w1, w2, w3 = library_author_sort_seeded  # Zoe Martinez, Amy Chen, "" (пустой)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_library_tab_for(driver, "PENDING")

    # Given запоминаем исходную Y-позицию верхней видимой карточки, затем скроллим вниз
    known_titles = [w1.title, w2.title, w3.title]
    baseline_y = library_steps.capture_topmost_card_y(driver, known_titles)
    last_filler = W.SCROLL_FILLERS[-1]
    library_steps.scroll_library_down_to(driver, last_filler.title)

    # When пользователь выбирает сортировку "Author (A–Z)"
    library_steps.select_library_sort(driver, "Author (A–Z)")

    # Then иконка-триггер сменилась, и список визуально сброшен к началу — верхняя
    # карточка теперь Amy Chen (W2, лексикографически первая среди непустых author),
    # проверяем ДО повторного скролла вниз ниже (Amy Chen раньше Zoe Martinez
    # доказывается транзитивно: W2 — самая первая карточка целиком, а W1 — см. ниже —
    # идёт ПОСЛЕ всех филлеров, которые в свою очередь идут ПОСЛЕ W2)
    library_steps.assert_sort_trigger_label(driver, "Author (A–Z)")
    library_steps.assert_scroll_reset_to_top(driver, w2.title, baseline_y)

    # And W1 (Zoe Martinez) идёт после всех непустых-author филлеров, а W3 (пустой
    # author) — ПОСЛЕДНЯЯ в списке, после W1 (непустые авторы, включая филлеры,
    # всегда идут раньше пустого) — весь хвост списка не помещается на экран целиком
    # без верхних карточек, скроллим вниз, чтобы увидеть W1/W3
    library_steps.scroll_library_down_to(driver, w3.title)
    library_steps.assert_cards_in_order(driver, [last_filler.title, w1.title, w3.title])


@pytest.mark.p1
@allure.id("TC-065")
@allure.title("Сортировка Rating (только вкладка Files/Downloads) группирует по рангу рейтинга")
def test_library_sort_rating_files_tab_only(library_files_rating_seeded, driver):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_files_tab(driver)

    # Given на вкладке Files видно 5 скачанных работ с разными рейтингами, засеянных
    # в порядке DISLIKED -> PENDING -> READ -> KUDOSED -> LOVED (обратном ожидаемому)
    for w in library_files_rating_seeded:
        library_steps.assert_work_in_files_tab(driver, w.title)

    # When пользователь открывает dropdown сортировки (доступен на Files) и выбирает "Rating"
    library_steps.select_library_sort(driver, "Rating")

    # Then список переупорядочен по рангу рейтинга: LOVED, KUDOSED, READ, PENDING, DISLIKED
    library_steps.assert_cards_in_order(driver, [
        W.LOVED.title, W.KUDOSED.title, W.READ.title, W.PENDING.title, W.DISLIKED.title,
    ])

    # And переключение на другую вкладку (Favorite) и открытие dropdown сортировки
    # НЕ показывает "Rating" среди опций — опция специфична для вкладки Files
    library_steps.open_library_tab_for(driver, "SAVE")
    library_steps.assert_sort_option_unavailable(driver, "Rating")
