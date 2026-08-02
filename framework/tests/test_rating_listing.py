"""Тесты области rating: точка входа — листинговая страница (Rate/Note-кнопка,
bottom-sheet `RatingOverlay`), в отличие от `test_rating.py` (встроенная панель
work-page, `RatingMenu`). Требует replay-инфраструктуру (AT-BUG-004, Verified) —
`framework/data/recordings/listing_basic.mitm`/`listing_duplicate_work.mitm`,
сгенерированные `framework/data/recording_builder.py` (см. `test_visibility.py`
за тем же обоснованием конструирования фикстур программно, а не живой записью).

Данные работы (title/author/fandom/wordCount), которые `applyRating` пишет в Room
для НОВОЙ строки, приходят из самого блёрба листинга (`ao3_bridge.js::getWorkData`,
`signalRate`/`signalRateWithNote` передают их в `Android.rateWork`) — в отличие от
встроенной панели work-page (`savePanelRating`, см. докстринг `test_rating.py`), для
листинговых сценариев НЕ нужен placeholder-сидинг под скрейп: `onRateWorkRequested`
(BrowserViewModel.kt) кладёт `PendingWorkInfo`/новую `WorkRating` строку из
параметров JS-вызова напрямую, без похода в DOM work-страницы.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps, rating_steps


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-009")
@allure.title("Простановка рейтинга {rating} из листинга (Rate-кнопка -> bottom-sheet)")
@pytest.mark.parametrize(
    "replay,rating,work",
    [
        (rb.LISTING_BASIC_FILENAME, "SAVE", W.LOVED),
        (rb.LISTING_BASIC_FILENAME, "LIKE", W.KUDOSED),
        (rb.LISTING_BASIC_FILENAME, "READ", W.READ),
        (rb.LISTING_BASIC_FILENAME, "PENDING", W.PENDING),
        (rb.LISTING_BASIC_FILENAME, "DISLIKE", W.DISLIKED),
    ],
    indirect=["replay"],
)
def test_rate_work_from_listing_overlay(clean_app, replay, driver, rating, work):
    # Given приложение с чистыми данными, открыта replay-листинговая страница с
    # работой W (Rate-кнопка видна и не активирована — все эталонные работы в
    # listing_basic.mitm стартуют без рейтинга)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    baseline_luma = rating_steps.capture_listing_overlay_baseline(driver, rating)

    # When в открывшемся нативном bottom-sheet (RatingOverlay) пользователь
    # выбирает рейтинг R
    rating_steps.rate_via_listing_overlay(driver, rating)

    # Then bottom-sheet подтверждает сохранение (выбранная кнопка визуально
    # темнеет — sheet НЕ закрывается сам после выбора, см. RatingOverlay.kt), бейдж
    # Rate-кнопки на карточке блёрба обновляется без перезагрузки листинга, работа
    # W появляется в соответствующей вкладке Library
    rating_steps.assert_rating_button_selected(driver, rating, baseline_luma)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    rating_steps.dismiss_rating_overlay(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, rating, work.title)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-010")
@allure.title("Бейдж на странице работы обновляется мгновенно после рейтинга из панели (без reload)")
@pytest.mark.parametrize(
    "rating,placeholder_seeded_work", [("SAVE", W.LOVED)], indirect=["placeholder_seeded_work"],
)
def test_panel_rating_updates_without_reload(placeholder_seeded_work, driver, rating):
    # Given приложение и открыта страница работы W без рейтинга, панель RatingMenu
    # раскрыта; зафиксирован baseline (window-маркер WebView + исходный цвет кнопки
    # рейтинга) до простановки
    work = placeholder_seeded_work
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    marker = browser_steps.mark_no_reload_baseline(driver)
    baseline_luma = rating_steps.capture_panel_rating_baseline(driver, rating)

    # When пользователь ставит рейтинг «Loved» через панель RatingMenu
    rating_steps.rate_current_work(driver, rating)

    # Then бейдж (цвет выбранной кнопки в панели) отражает «Loved» немедленно,
    # а WebView не выполнил повторную навигацию/reload (window-маркер сохранился)
    rating_steps.assert_rating_button_selected(driver, rating, baseline_luma)
    browser_steps.assert_no_reload_since(driver, marker)


@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-011")
@allure.title("Бейдж Rate-кнопки на листинге обновляется мгновенно из bottom-sheet (без reload)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_listing_rate_button_updates_without_reload(clean_app, replay, driver):
    # Given приложение с чистыми данными, открыта replay-листинговая страница с
    # работой W без рейтинга; зафиксирован baseline (window-маркер WebView) до
    # простановки
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    work = W.KUDOSED
    marker = browser_steps.mark_no_reload_baseline(driver)

    # When пользователь через Rate-кнопку работы W и bottom-sheet ставит рейтинг «Liked»
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")

    # Then стиль/цвет Rate-кнопки работы W на карточке блёрба меняется на
    # отражающий «Liked» немедленно, а WebView не выполнил повторную навигацию/reload
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    browser_steps.assert_no_reload_since(driver, marker)


@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-012")
@allure.title("applyRatings синхронизирует бейдж во всех вхождениях одной работы на странице")
@pytest.mark.parametrize("replay", [rb.LISTING_DUPLICATE_FILENAME], indirect=True)
def test_apply_ratings_syncs_duplicate_blurbs(clean_app, replay, driver):
    # Given приложение с чистыми данными, открыта replay-листинговая страница, где
    # работа W (LOVED) отображена в ДВУХ разных блёрбах на одной странице
    # (listing_duplicate_work.mitm), оба без рейтинга
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_DUPLICATE_URL)
    work = W.LOVED

    # When пользователь ставит рейтинг «Read» через Rate-кнопку одного из двух
    # вхождений работы W (клик по первому найденному querySelector'ом узлу
    # duplicate-id — `signalRate` берёт `document.getElementById`, тоже первый)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "READ")

    # Then бейдж/стиль Rate-кнопки обновляется на «Read» у ОБОИХ вхождений работы W
    # на странице без перезагрузки
    browser_steps.assert_rating_badge_visible_all(driver, work.ao3_id, expected_count=2)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-043")
@allure.title("Comment-only работа видна на листинге и отсутствует ни на одной рейтинговой вкладке Library")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_comment_only_visible_on_listing_and_absent_from_rating_tabs(replay, comment_only_work, driver):
    # Given работа W (KUDOSED) имеет только комментарий, без рейтинга (rating=null,
    # comment≠null, см. фикстуру comment_only_work) и фильтрация по рейтингу включена
    # (Disliked в hidden-set — дефолт)
    work = comment_only_work
    app_steps.wait_ui_ready(driver)

    # When пользователь просматривает листинговую страницу с работой W и переходит
    # на экран Library
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then работа W видна на листинге (не скрыта фильтрацией — работы с rating=null
    # никогда не скрываются), и не отображается ни на одной из пяти рейтинговых
    # вкладок Library
    browser_steps.assert_blurb_visible(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    for rating in ("SAVE", "LIKE", "READ", "PENDING", "DISLIKE"):
        library_steps.assert_work_not_in_tab(driver, rating, work.title)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-044")
@allure.title("Note-кнопка на листинге открывает overlay с развёрнутым и предзаполненным комментарием")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_note_button_opens_overlay_with_expanded_comment(replay, note_work_seeded, driver):
    # Given работа W (READ) имеет существующий комментарий "Existing note text" и
    # видимую Note-кнопку (карандаш, слева от Rate-кнопки — comment непустой)
    work = note_work_seeded
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # When пользователь нажимает Note-кнопку работы W (первый тап раскрывает
    # всплывающую подсказку с текстом заметки, тап по НЕЙ вызывает
    # signalRateWithNote — см. browser_steps.tap_note_button/tap_note_tooltip)
    browser_steps.tap_note_button(driver, work.ao3_id)
    browser_steps.tap_note_tooltip(driver)

    # Then открывается overlay рейтинга для работы W с полем комментария, уже
    # развёрнутым (не свёрнутым за "Add a note"), предзаполненным существующим текстом
    rating_steps.assert_note_overlay_expanded_with_text(driver, "Existing note text")


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-045")
@allure.title("Личные теги не влияют на видимость работы независимо от фильтрации")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_personal_tags_do_not_affect_visibility(replay, disliked_work_with_tags_seeded, driver):
    # Given ДВЕ работы с ОДИНАКОВЫМИ личными тегами, различающиеся только
    # рейтингом: W_disliked (DISLIKED, скрывается фильтрацией по умолчанию) и
    # W_visible (LOVED, rating=SAVE — не в hidden-set)
    work_disliked, work_visible = disliked_work_with_tags_seeded
    app_steps.wait_ui_ready(driver)

    # When пользователь просматривает листинговую страницу с включённой фильтрацией
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then W_disliked скрыта на листинге (как и любая другая Disliked-работа), а
    # W_visible — с ТЕМИ ЖЕ тегами — видна: одинаковые теги дают ПРОТИВОПОЛОЖНЫЙ
    # исход, что и доказывает независимость видимости от tags как свойство (не
    # единичный пример), а не только то, что теги не "спасают" от скрытия
    browser_steps.assert_blurb_hidden(driver, work_disliked.ao3_id)
    browser_steps.assert_blurb_visible(driver, work_visible.ao3_id)

    # And переход на экран Library: вкладка DISLIKED показывает W_disliked с
    # сохранёнными личными тегами, вкладка FAVORITE — W_visible с ТЕМИ ЖЕ тегами
    # (теги сохраняются и отображаются одинаково независимо от рейтинга/видимости)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_tags_visible(
        driver, "DISLIKE", work_disliked.title, "spoiler · reread-candidate",
    )
    library_steps.assert_work_tags_visible(
        driver, "SAVE", work_visible.title, "spoiler · reread-candidate",
    )


@pytest.mark.p3
@pytest.mark.replay
@allure.id("TC-056")
@allure.title("Личный тег, совпадающий с AO3-тегом карточки, подсвечивается на листинге")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_matching_personal_tag_highlighted_on_listing(replay, tagged_work_seeded, driver):
    # Given работа W (LOVED) на листинге имеет личные теги ["Fluff", "Angst"], из
    # которых «Fluff» совпадает с одним из AO3-тегов её карточки (freeform «Fluff»,
    # зашит в каждый блёрб listing_basic.mitm), а «Angst» не совпадает ни с одним
    work = tagged_work_seeded
    app_steps.wait_ui_ready(driver)

    # When пользователь просматривает листинговую страницу с блёрбом работы W
    # (bridge применил applyRatings/highlightWorkTags)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then ссылка AO3-тега «Fluff» на карточке W подсвечена (data-ao3-tag-hl), а
    # остальные AO3-теги карточки — НЕ подсвечены (подсвечивается только реально
    # совпавший тег; «Angst» ни на что не влияет — не совпал ни с чем)
    browser_steps.assert_tag_highlighted(driver, work.ao3_id, "Fluff")
    browser_steps.assert_tag_not_highlighted(
        driver, work.ao3_id, "Creator Chose Not To Use Archive Warnings",
    )
    browser_steps.assert_tag_not_highlighted(driver, work.ao3_id, "Test Ship/Other Ship")


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-087")
@allure.title("Save note сохраняет введённый комментарий работы (bottom-sheet листинга)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_save_note_persists_comment(clean_app, replay, driver):
    # Given приложение с чистыми данными, открыта replay-листинговая страница с
    # работой W (KUDOSED) без рейтинга и комментария; Rate-кнопкой открыт нативный
    # bottom-sheet
    work = W.KUDOSED
    comment = "New saved note"
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)

    # When пользователь раскрывает поле комментария, вводит «New saved note» и
    # нажимает «Save note»
    rating_steps.add_note_via_listing_overlay(driver, comment)

    # Then bottom-sheet не закрывается сам, поле комментария сворачивается в
    # компактный превью-режим с введённым текстом
    rating_steps.assert_overlay_still_open(driver)
    rating_steps.assert_comment_collapsed_with_text(driver, comment)

    # And после закрытия bottom-sheet тапом по scrim и повторного открытия
    # Rate-кнопкой той же работы комментарий по-прежнему предзаполнен —
    # доказательство персистентности в Room
    rating_steps.reopen_listing_overlay(driver, work.ao3_id)
    rating_steps.assert_comment_persisted(driver, comment)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-088")
@allure.title("Clear note очищает сохранённый комментарий работы (bottom-sheet листинга)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_clear_note_removes_comment(replay, note_work_seeded, driver):
    # Given работа W (READ) имеет рейтинг Kudosed и сохранённый комментарий
    # «Existing note text»; Rate-кнопкой открыт bottom-sheet — комментарий показан
    # в свёрнутом превью-режиме
    work = note_work_seeded
    existing_text = "Existing note text"
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.assert_comment_collapsed_with_text(driver, existing_text)

    # When пользователь тапает по свёрнутому превью (раскрывает поле комментария)
    # и нажимает «Clear note»
    rating_steps.tap_comment_preview(driver, existing_text)
    rating_steps.clear_note(driver)

    # Then поле комментария немедленно пустеет, область комментария возвращается
    # к тогглу «Add a note»
    rating_steps.assert_comment_cleared(driver)

    # And после закрытия bottom-sheet тапом по scrim и повторного открытия
    # Rate-кнопкой работы W комментарий остаётся пустым — доказательство
    # персистентности очистки в Room
    rating_steps.reopen_listing_overlay(driver, work.ao3_id)
    rating_steps.assert_comment_cleared(driver, timeout=8)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-090")
@allure.title("Добавление личного тега через текстовое поле и кнопку Add сохраняет его среди выбранных")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_add_freeform_tag_persists(clean_app, replay, driver):
    # Given приложение с чистыми данными, открыта replay-листинговая страница с
    # работой W (KUDOSED), у которой нет ни рейтинга, ни личных тегов; Rate-кнопкой
    # открыт нативный bottom-sheet; тег «spoiler-test» ещё не встречается на экране
    work = W.KUDOSED
    tag = "spoiler-test"
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.assert_chip_absent(driver, tag)

    # When пользователь выбирает рейтинг «Kudosed» (разблокирует раздел тегов),
    # раскрывает раздел тегов, вводит свободный тег «spoiler-test» и нажимает «Add»
    rating_steps.rate_via_listing_overlay(driver, "LIKE")
    rating_steps.add_tag_via_listing_overlay(driver, tag)

    # Then тег «spoiler-test» появляется как выбранный чип; после сворачивания
    # раздела лейбл показывает счётчик «Saved tags (1)»
    rating_steps.assert_chip_visible(driver, tag)
    rating_steps.collapse_tags_section(driver)
    rating_steps.assert_tags_count_label_visible(driver, 1)

    # And после закрытия bottom-sheet тапом по scrim, повторного открытия
    # Rate-кнопкой работы W и раскрытия раздела тегов чип «spoiler-test»
    # по-прежнему присутствует — доказательство персистентности в Room
    rating_steps.reopen_listing_overlay(driver, work.ao3_id)
    rating_steps.open_tags_section(driver)
    rating_steps.assert_chip_visible(driver, tag)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-091")
@allure.title("Тап по выбранному чипу удаляет личный тег работы (bottom-sheet листинга)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_tap_selected_chip_removes_tag(replay, tagged_work_seeded, driver):
    # Given работа W (LOVED) засеяна с рейтингом Kudosed и личными тегами
    # ["Fluff", "Angst"]; Rate-кнопкой открыт bottom-sheet, раздел тегов раскрыт —
    # «Fluff» и «Angst» видны как выбранные чипы
    work = tagged_work_seeded
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.open_tags_section(driver)
    rating_steps.assert_chip_visible(driver, "Fluff")
    rating_steps.assert_chip_visible(driver, "Angst")

    # When пользователь тапает по чипу «Angst»
    rating_steps.tap_selected_chip(driver, "Angst")

    # Then чип «Angst» немедленно исчезает целиком, чип «Fluff» остаётся видимым
    rating_steps.assert_chip_absent(driver, "Angst")
    rating_steps.assert_chip_visible(driver, "Fluff")

    # And после сворачивания раздела лейбл показывает «Saved tags (1)»
    rating_steps.collapse_tags_section(driver)
    rating_steps.assert_tags_count_label_visible(driver, 1)

    # And после закрытия bottom-sheet тапом по scrim, повторного открытия
    # Rate-кнопкой работы W и раскрытия раздела тегов «Angst» по-прежнему
    # отсутствует, «Fluff» по-прежнему присутствует — доказательство
    # персистентности удаления в Room
    rating_steps.reopen_listing_overlay(driver, work.ao3_id)
    rating_steps.open_tags_section(driver)
    rating_steps.assert_chip_absent(driver, "Angst")
    rating_steps.assert_chip_visible(driver, "Fluff")


# --- TC-138..143: rating/bridge — авто-клик kudos через листинговый вход
# (`BrowserViewModel.kt::applyRating`, `:856-861`, bugs/BUG-015.md,
# bugs/AT-BUG-035.md Verified — узел `#kudo_submit` инструментирован
# инкрементным счётчиком клика, `framework/data/recording_builder.py`). Given
# TC-138/139/142/143 повторяет схему TC-026 (`test_tabs.py`): Tab A (листинг,
# вкладка-0) + Tab B (work-страница W, открытая в фон `long_press_work_link`) —
# chromedriver прилипает к вкладке-0 (`browser_screen.py:319-329`), поэтому
# читать `#kudo_submit` Tab B можно только идиомой reduce-to-one: сначала
# наблюдения на Tab A (sticky-context, дефолт), ЗАТЕМ `swipe_close_tab(driver,
# position=0)` закрывает Tab A — Tab B остаётся единственной живой WebView,
# chromedriver переподключается к ней (см. `browser_steps.assert_kudo_submit_
# click_count`/`_holds`, докстринги).


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-138")
@allure.title("Первый переход рейтинга в Kudosed через листинг при открытой вкладке работы шлёт kudos ровно один раз")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_first_kudosed_via_listing_with_open_work_tab_clicks_kudos_once(clean_app, replay, driver):
    # Given приложение с чистыми данными; открыты Tab A (листинг с блёрбом W без
    # рейтинга — вкладка-0) и Tab B (work-страница W, открытая в фон long-press-ом
    # по ссылке блёрба, тот же приём, что TC-026); на Tab B узел #kudo_submit ещё
    # без data-kudo-clicked (baseline инструментированного узла фикстуры)
    work = W.LOVED
    app_steps.wait_home_ready_for_deep_link(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.long_press_work_link(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)

    # When на Tab A (по-прежнему активной — long-press не переключает активную
    # вкладку, см. TC-026) пользователь Rate-кнопкой W открывает нативный
    # bottom-sheet и выбирает рейтинг «Kudosed» (LIKE)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")

    # Then рейтинг сохранён: бейдж «Kudosed» появляется у блёрба W на Tab A без
    # перезагрузки (штатный sticky-контекст — Tab A это вкладка-0), работа
    # отображается на вкладке Kudosed экрана Library
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    rating_steps.dismiss_rating_overlay(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "LIKE", work.title)

    # And ПОСЛЕ проверки бейджа Tab A закрывается — идиома reduce-to-one
    # (`browser_steps.swipe_close_tab(driver, position=0)`, обоснование
    # `browser_screen.py:319-329`): Tab B остаётся единственной живой WebView,
    # уничтожение прилипшей цели форсирует chromedriver переподключиться к ней.
    # На Tab B узел #kudo_submit получает data-kudo-clicked="1" — ровно один
    # клик; повторное чтение после паузы даёт то же «1», не «2» (инкрементный
    # счётчик, не константа, AT-BUG-035)
    app_steps.open_tab(driver, "Browse")
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_kudo_submit_click_count(driver, 1)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-139")
@allure.title("Правка личного тега уже-Kudosed работы через листинг НЕ отправляет kudos повторно (ожидаемо-красный BUG-015)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos(replay, kudosed_work_seeded, driver):
    # Given работа W уже имеет рейтинг Kudosed (LIKE), личных тегов нет; открыты
    # Tab A (листинг, блёрб W с бейджем Kudosed) и Tab B (work-страница W, в
    # фоне, тот же приём, что TC-138) — нужна, чтобы условие `:857-858` могло
    # сработать, если бы гипотетический баг ошибочно кликал; на Tab B
    # #kudo_submit без data-kudo-clicked (baseline)
    work = kudosed_work_seeded
    app_steps.wait_home_ready_for_deep_link(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    browser_steps.long_press_work_link(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)

    # When на Tab A пользователь Rate-кнопкой открывает bottom-sheet, раскрывает
    # раздел тегов и добавляет личный тег «re-save-kudos-probe» (правка
    # метаданных; рейтинг НЕ меняется, остаётся Kudosed) — тот же приём, что
    # TC-090/TC-114
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.add_tag_via_listing_overlay(driver, "re-save-kudos-probe")

    # Then тег «re-save-kudos-probe» сохраняется среди выбранных
    rating_steps.assert_chip_visible(driver, "re-save-kudos-probe")
    rating_steps.dismiss_rating_overlay(driver)

    # And ПОСЛЕ этого Tab A закрывается (reduce-to-one, тот же приём, что
    # TC-138) — повторного клика по kudos НЕ должно быть, на Tab B
    # #kudo_submit должен ОСТАТЬСЯ без data-kudo-clicked. ОЖИДАЕМОЕ ПАДЕНИЕ на
    # текущей сборке (прецедент TC-048: кейс пишется по спеке, не по факту
    # сборки) — по коду (`:856-861`) applyRating кликает kudos при ЛЮБОМ
    # сохранении через листинг уже-Kudosed/Favorite работы независимо от того,
    # менялся ли рейтинг; реально data-kudo-clicked="1" появится. Красный
    # результат триажится как APP_BUG/BUG-015, не как расхождение теста со
    # спекой (см. test-cases/rating/TC-139.md)
    app_steps.open_tab(driver, "Browse")
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 0)


@pytest.mark.p3
@pytest.mark.replay
@allure.id("TC-140")
@allure.title("Простановка Kudosed через листинг без открытой вкладки работы не отправляет kudos")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_rate_kudosed_via_listing_without_open_work_tab_does_not_click_kudos(clean_app, replay, driver):
    # Given приложение с чистыми данными; открыта ТОЛЬКО листинговая вкладка с
    # блёрбом W без рейтинга — никакой work-вкладки W не открыто (единственная
    # вкладка на протяжении всего сценария)
    work = W.LOVED
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # When пользователь Rate-кнопкой W открывает bottom-sheet и выбирает рейтинг
    # «Kudosed» (LIKE)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")

    # Then рейтинг сохраняется — бейдж «Kudosed» появляется у блёрба W, работа
    # отображается на вкладке Kudosed Library (запись в Room и обновление бейджа
    # не зависят от наличия открытой work-вкладки — это отдельный, безусловный путь)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    rating_steps.dismiss_rating_overlay(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "LIKE", work.title)

    # And наблюдаемое доказательство отсутствия клика (единственно возможное в
    # момент, когда для клика физически не было вкладки): пользователь ПОСЛЕ
    # этого открывает work-страницу W IN-PLACE (`rating_steps.open_work_page` —
    # НЕ `long_press_work_link`, которая создала бы вторую вкладку и без нужды
    # втянула бы кейс в sticky-context блокер B1, см. заметки TC-140.md) — на
    # СВЕЖЕЗАГРУЖЕННОЙ странице #kudo_submit НЕ несёт data-kudo-clicked: открытие
    # вкладки уже ПОСЛЕ факта не могло получить клик, который случился бы в
    # момент простановки рейтинга (если бы случился)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 0)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-142")
@allure.title("Смена рейтинга через листинг с Kudosed на Read не отправляет kudos")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_change_rating_kudosed_to_read_via_listing_does_not_click_kudos(replay, kudosed_work_seeded, driver):
    # Given работа W имеет рейтинг Kudosed (LIKE); открыты Tab A (листинг, бейдж
    # Kudosed) и Tab B (work-страница W, в фоне, тот же приём, что TC-138/139)
    work = kudosed_work_seeded
    app_steps.wait_home_ready_for_deep_link(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    browser_steps.long_press_work_link(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)

    # When на Tab A пользователь Rate-кнопкой открывает bottom-sheet и выбирает
    # рейтинг «Read» (смена рейтинга, НЕ правка метаданных — реальный переход на
    # значение вне множества {LIKE, SAVE}). Тап ОДИН, по кнопке «Read», не по
    # уже выбранной «Kudosed» (тап по уже выбранной кнопке деселектит её —
    # предмет TC-143, не этот кейс)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "READ")

    # Then рейтинг меняется на Read — работа W перемещается из вкладки Kudosed
    # во вкладку Read экрана Library
    rating_steps.dismiss_rating_overlay(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "READ", work.title)

    # And ПОСЛЕ этого Tab A закрывается (reduce-to-one, тот же приём, что
    # TC-138/139) — на Tab B #kudo_submit НЕ получает data-kudo-clicked: новое
    # сохраняемое значение (READ) не входит в предикат `:856`, evalJs с
    # kudos-кликом структурно не строится для этого вызова
    app_steps.open_tab(driver, "Browse")
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 0)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-143")
@allure.title("Снятие рейтинга Kudosed (deselect) через листинг не отправляет kudos")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_deselect_kudosed_via_listing_does_not_click_kudos(replay, kudosed_work_seeded, driver):
    # Given работа W имеет рейтинг Kudosed (LIKE); открыты Tab A (листинг, бейдж
    # Kudosed) и Tab B (work-страница W, в фоне, тот же приём, что TC-138/139/142)
    work = kudosed_work_seeded
    app_steps.wait_home_ready_for_deep_link(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
    browser_steps.long_press_work_link(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)

    # When на Tab A пользователь Rate-кнопкой открывает bottom-sheet и повторно
    # нажимает уже выбранную кнопку «Kudosed» (deselect — общий toggle-механизм
    # RatingOverlay.kt, тот же приём, что TC-117 для панели, но здесь через
    # листинговый путь applyRating)
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")

    # Then рейтинг снят — работа W исчезает из вкладки Kudosed экрана Library
    rating_steps.dismiss_rating_overlay(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "LIKE", work.title)

    # And ПОСЛЕ этого Tab A закрывается (reduce-to-one, тот же приём, что
    # TC-138/139/142) — на Tab B #kudo_submit НЕ получает data-kudo-clicked:
    # ветка rating == null (`:803-838`) завершается return@launch (:837) ДО
    # того, как код доходит до строки :856 — evalJs с kudos структурно
    # недостижим для этого сохранения
    app_steps.open_tab(driver, "Browse")
    browser_steps.swipe_close_tab(driver, 0)
    browser_steps.assert_kudo_submit_click_count_holds(driver, 0)
