"""Тесты области library — состояние скролла/сортировки вкладок при переключении
(story #28, батч 2: TC-177/TC-178/TC-179/TC-180). Полностью на сидинге Room, без
обращения к живому AO3 (тот же дизайн, что `test_library_filters.py`/`test_library.py`
— наблюдаемость позиции читается напрямую по видимой карточке, класс негативных
сетевых Then AT-BUG-029 здесь неприменим).

Механизм под наблюдением — `LibraryScreen.kt:905-912` (`WorkList`): скролл каждой
страницы пейджера сохраняется через `rememberLazyListState()`/`rememberSaveable`, а
сброс к началу (`scrollToItem(0)`) срабатывает ТОЛЬКО когда `lastSort` СТРАНИЦЫ
расходится с полученным `effectiveSort` — сравнение происходит в момент, когда
страница снова входит в композицию (не когда сортировка меняется физически).
`effectiveSort` (`:226-229`) вычисляется от активной страницы пейджера и подменяет
недопустимый для текущей вкладки выбор (`sortBy`, например Rating вне Files) на
Last read — ТОЛЬКО в отображении, хранимое значение не теряется.

TC-177/TC-178 — позитивный инвариант «переключение вкладок само по себе не сбрасывает
скролл» (обычный визит и визит с активной Files-only сортировкой Rating).
TC-179 — негативный твин: сортировка, изменённая, пока вкладка ВНЕ экрана, сбрасывает
её скролл ИМЕННО при возврате (не раньше) — тест явно анкерует это отличие: пока
пользователь остаётся на Files (активная страница), смена сортировки применяется
НЕМЕДЛЕННО к самой Files (её собственный `lastSort` расходится сразу и её список
переупорядочивается/сбрасывается на месте) — эта немедленная реакция проверяется ДО
возврата на Favorite и служит контрольным анкером «T0: смена уже случилась», отдельным
от «T1: сброс Favorite обнаружен по возврату» — иначе тест не отличил бы «сброс
случился в момент смены» от «сброс случился при возврате» (оба привели бы к одному и
тому же видимому состоянию при возврате).
TC-180 — судьба недопустимого выбора: Rating, выбранная на Files, не удаляется из
хранимого состояния при уходе на другую вкладку (видна как Last read временно), и
снова действует по возврату на Files — тест проверяет ОБЕ стороны инварианта.

`library_steps.assert_sort_trigger_label` уже читает content-desc топ-бара
(`by_desc(...)`, `MainActivity.kt` `contentDescription = "Sort library: ${label}"`,
`LibraryScreen.kt:269-275`) — единственное место в приложении, где эта подпись
рендерится (сверено по коду, `Grep "Sort library"` — одно совпадение). Заметки
TC-180 предполагали ОТДЕЛЬНЫЙ примитив для content-desc топ-бара (в отличие от
«видимого Text» триггера сортировки) — расхождение со стилем «код важнее прозы кейса»
(project memory): существующий примитив уже читает именно content-desc, отдельного
Text-триггера в дереве нет, второй примитив избыточен."""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.steps import app_steps, library_steps

# TC-179: топ-3 по word_count среди `W.FILES_SCROLL_FILLERS` (21..30) — гарантированно
# помещаются в первый экран без скролла, используются для доказательства немедленного
# реордера АКТИВНОЙ страницы Files (в отличие от отложенного эффекта Favorite).
_FILES_TOP3_DESC = [
    w.title for w in sorted(W.FILES_SCROLL_FILLERS, key=lambda w: w.word_count, reverse=True)[:3]
]


@pytest.mark.p1
@allure.id("TC-177")
@allure.title(
    "Скролл-позиция вкладки Library сохраняется при переключении на другую вкладку и возврате"
)
def test_library_favorite_scroll_retained_across_tab_switch(
    library_favorite_scroll_and_disliked_neighbor_seeded, driver,
):
    fixture = library_favorite_scroll_and_disliked_neighbor_seeded
    disliked_neighbor = fixture["disliked_neighbor"]
    marker = W.SCROLL_FILLERS[-1]

    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")

    # Given вкладка Favorite активна, сортировка Last read (дефолт), список
    # прокручен вниз (не на самом верху) — позиция маркерной карточки снята ПОСЛЕ
    # скролла (заметки TC-177: сравнение с произвольным baseline_y, снятым после
    # скролла вниз, — НЕ канон TC-030, где база снимается до скролла у верха списка)
    library_steps.open_library_tab_for(driver, "SAVE")
    library_steps.assert_sort_trigger_label(driver, "Last read")
    library_steps.scroll_library_down_to(driver, marker.title)
    baseline_y = library_steps.capture_topmost_card_y(driver, [marker.title])

    # When пользователь переключается на вкладку Disliked (достаточно далеко, чтобы
    # страница Favorite была утилизирована пейджером) и обратно на Favorite
    library_steps.open_library_tab_for(driver, "DISLIKE")
    library_steps.assert_work_in_tab(driver, "DISLIKE", disliked_neighbor.title)
    library_steps.open_library_tab_for(driver, "SAVE")

    # Then список Favorite стоит НА ТОЙ ЖЕ позиции — та же маркерная карточка на том
    # же Y (в пределах допуска)
    library_steps.assert_scroll_retained(driver, marker.title, baseline_y)
    # And сортировка осталась Last read — эффект сброса вообще не должен был сработать
    library_steps.assert_sort_trigger_label(driver, "Last read")


@pytest.mark.p1
@allure.id("TC-178")
@allure.title(
    "Скролл сохраняется у ОБЕИХ вкладок при переключении, даже когда активна "
    "Files-only сортировка Rating"
)
def test_library_files_rating_and_neighbor_scroll_retained(
    library_favorite_and_files_scroll_seeded, driver,
):
    fixture = library_favorite_and_files_scroll_seeded
    files_marker = W.FILES_SCROLL_FILLERS[-1]
    favorite_marker = W.SCROLL_FILLERS[-1]

    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")

    # Given вкладка Favorite прокручена вниз (сортировка Last read, дефолт, вообще
    # не менялась), база снята ПОСЛЕ скролла (тот же приём, что TC-177)
    library_steps.open_library_tab_for(driver, "SAVE")
    library_steps.assert_sort_trigger_label(driver, "Last read")
    library_steps.scroll_library_down_to(driver, favorite_marker.title)
    favorite_baseline_y = library_steps.capture_topmost_card_y(driver, [favorite_marker.title])

    # And на Files выбрана сортировка Rating (единственная Files-only сортировка,
    # отличная от Last read соседей — `effectiveSort` Files теоретически мог бы
    # потечь в соседей, см. requirements кейса), список прокручен вниз, база снята
    library_steps.open_files_tab(driver)
    library_steps.select_library_sort(driver, "Rating")
    library_steps.scroll_library_down_to(driver, files_marker.title)
    files_baseline_y = library_steps.capture_topmost_card_y(driver, [files_marker.title])

    # When пользователь переключается Files -> Disliked (ближайший сосед в пейджере) -> Files
    library_steps.open_library_tab_for(driver, "DISLIKE")
    library_steps.open_files_tab(driver)

    # Then Files стоит на прежней прокрученной позиции, сортировка Rating не сброшена
    library_steps.assert_scroll_retained(driver, files_marker.title, files_baseline_y)
    library_steps.assert_sort_trigger_label(driver, "Rating")

    # When отдельно (тот же сид) пользователь переключается Files -> Favorite
    # (вкладка ДАЛЕКО от Files в пейджере) -> Files
    library_steps.open_library_tab_for(driver, "SAVE")

    # Then скролл Favorite (не участвовавшей в смене сортировки) ТОЖЕ не сброшен
    # после промежуточного визита на Files с активной Files-only Rating — несмотря
    # на то, что при активной странице Files всем страницам пейджера технически
    # передаётся effectiveSort=Rating, lastSort Favorite сравнивается только в
    # момент, когда САМА Favorite активна (получает effectiveSort от своего
    # контекста, где Rating недопустима и не передаётся)
    library_steps.assert_scroll_retained(driver, favorite_marker.title, favorite_baseline_y)
    library_steps.assert_sort_trigger_label(driver, "Last read")

    library_steps.open_files_tab(driver)
    # And после возврата Files снова на прежней позиции, сортировка снова Rating
    library_steps.assert_scroll_retained(driver, files_marker.title, files_baseline_y)
    library_steps.assert_sort_trigger_label(driver, "Rating")


@pytest.mark.p1
@allure.id("TC-179")
@allure.title(
    "Смена сортировки, пока вкладка Library вне экрана, сбрасывает её скролл на "
    "верх при возврате"
)
def test_library_offscreen_sort_change_resets_scroll_on_return(
    library_favorite_and_files_scroll_seeded, driver,
):
    fixture = library_favorite_and_files_scroll_seeded
    known_titles = [w.title for w in fixture["favorite"]]

    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")

    # Given активна вкладка Favorite, сортировка Last read (текущая для Favorite),
    # база снята ДО скролла (канон TC-030/TC-063 — база у верха списка, не после
    # скролла, в отличие от TC-177/178: здесь сравнение будет с ВЕРХОМ списка,
    # `assert_scroll_reset_to_top`, не с произвольной позицией), список прокручен вниз
    library_steps.open_library_tab_for(driver, "SAVE")
    library_steps.assert_sort_trigger_label(driver, "Last read")
    baseline_y = library_steps.capture_topmost_card_y(driver, known_titles)
    library_steps.scroll_library_down_to(driver, W.SCROLL_FILLERS[-1].title)

    # When пользователь переключается на вкладку Files (Favorite уходит вне экрана и
    # утилизируется пейджером)
    library_steps.open_files_tab(driver)

    # And НЕ находясь на Favorite, сортировка Favorite меняется на другую допустимую
    # (Word count, доступна везде) — librarySortBy общий для MainActivity
    # (не per-tab состояние), смену производим физически на Files
    library_steps.select_library_sort(driver, "Word count (high to low)")

    # And T0 — контрольный анкер «смена уже случилась, пока мы физически на Files»,
    # СТРОГО ДО следующего возврата на Favorite: Files, будучи активной страницей,
    # получает НЕМЕДЛЕННЫЙ реордер/сброс собственного LazyListState (тот же
    # механизм LaunchedEffect(sort), сработавший здесь на месте, а не отложенно) —
    # без этого анкера тест не отличил бы «сброс уже случился в момент смены» от
    # «сброс случился именно при возврате» (оба дали бы одинаковую картину на
    # Favorite при возврате)
    library_steps.assert_sort_trigger_label(driver, "Word count (high to low)")
    library_steps.assert_sorted_by_wordcount_desc(driver, _FILES_TOP3_DESC)

    # And пользователь возвращается на вкладку Favorite
    library_steps.open_library_tab_for(driver, "SAVE")

    # Then T1 — список Favorite открывается СВЕРХУ (не на прежней прокрученной
    # позиции) — lastSort Favorite (Last read) разошёлся с полученным effectiveSort
    # (Word count) именно в момент, когда страница СНОВА вошла в композицию
    library_steps.assert_sort_trigger_label(driver, "Word count (high to low)")
    library_steps.assert_scroll_reset_to_top(driver, W.PENDING.title, baseline_y)
    # And список действительно переупорядочен по новой сортировке (Word count), не
    # по старой (Last read)
    favorite_desc_order = [
        W.PENDING.title, W.LOVED.title, W.KUDOSED.title, W.READ.title, W.DISLIKED.title,
    ]
    library_steps.assert_sorted_by_wordcount_desc(driver, favorite_desc_order)


@pytest.mark.p1
@allure.id("TC-180")
@allure.title(
    "Выбор сортировки Rating, недопустимый вне Files, замещается Last read в "
    "отображении, но сохраняется и снова действует на Files"
)
def test_library_files_rating_pick_survives_visit_to_other_tab(
    library_files_rating_seeded, driver,
):
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_files_tab(driver)

    # Given на Files видно 5 скачанных работ, выбрана сортировка Rating, список
    # упорядочен по рангу рейтинга (тот же канон, что TC-065)
    for w in library_files_rating_seeded:
        library_steps.assert_work_in_files_tab(driver, w.title)
    library_steps.select_library_sort(driver, "Rating")
    rating_order = [
        W.LOVED.title, W.KUDOSED.title, W.READ.title, W.PENDING.title, W.DISLIKED.title,
    ]
    library_steps.assert_cards_in_order(driver, rating_order)
    library_steps.assert_sort_trigger_label(driver, "Rating")

    # When пользователь переключается на вкладку Favorite (Rating недопустима вне Files)
    library_steps.open_library_tab_for(driver, "SAVE")

    # Then список Favorite отображается в порядке Last read (fallback — позитивный
    # якорь: W.LOVED реально виден на Favorite, рейтинг SAVE засеян
    # `library_files_rating_seeded`), И content-desc иконки-триггера топ-бара
    # показывает «Sort library: Last read» — оба индикатора согласованно откатились
    library_steps.assert_work_in_tab(driver, "SAVE", W.LOVED.title)
    library_steps.assert_sort_trigger_label(driver, "Last read")

    # When пользователь возвращается на вкладку Files
    library_steps.open_files_tab(driver)

    # Then список Files снова упорядочен по Rating — выбор НЕ был потерян уходом на
    # другую вкладку, он был только визуально замещён на время, пока Rating была
    # недопустима (обе стороны инварианта: замещение на Favorite выше + оживание
    # здесь)
    library_steps.assert_cards_in_order(driver, rating_order)
    library_steps.assert_sort_trigger_label(driver, "Rating")
