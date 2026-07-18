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
