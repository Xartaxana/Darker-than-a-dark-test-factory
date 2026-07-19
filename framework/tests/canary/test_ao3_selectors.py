"""Canary-suite (R-02) — контракт DOM-селекторов bridge (`ao3_bridge.js`) с живым и
replay-DOM archiveofourown.org. Тестирует НАШ контракт (`framework/web/selectors.py`),
не сам сайт AO3 (граница §8, docs/01) — см. docs/01 §9 «Canary — контракт селекторов
bridge» за происхождением и DoD области.

Каждый живой (`live`) кейс — парный replay-кейсу (`replay`) на той же наблюдаемой
DOM-грани: live доказывает контракт против реального archiveofourown.org (ежедневный
canary, §4), replay даёт детерминированную регрессию без сетевой переменной
(Cloudflare bot-check, R-03).
"""
from __future__ import annotations

import uuid

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, rating_steps

# Реально записанная (не синтетически собранная `recording_builder`) фикстура
# спайка B — единственная страница archiveofourown.org (`GET
# https://archiveofourown.org/`) в этом .mitm, снятая живым mitmdump-прогоном
# (docs/environment-setup.md «Спайк B»/«Результаты спайков Фазы 0»). Годится для
# TC-067: контракту маркера инъекции не нужны work-блёрбы, только сама страница
# archiveofourown.org.
AO3_HOME_SMOKE_FILENAME = "ao3_home_smoke.mitm"


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-066")
@allure.title("ao3_bridge.js инжектируется в живую AO3-страницу (window.__ao3Bridge marker)")
def test_bridge_marker_present_live(driver):
    # Given приложение запущено live
    app_steps.wait_ui_ready(driver)

    # When вкладка Browse загружает домашнюю страницу archiveofourown.org
    browser_steps.open_url_and_wait_ready(driver, browser_steps.HOME_URL)

    # Then в JS-контексте страницы присутствует маркер инъекции window.__ao3Bridge
    # (наблюдаемый факт того, что bridge выполнился, а не косвенное следствие вроде
    # наличия кнопок, зависящее от типа страницы)
    browser_steps.assert_bridge_marker_present(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-067")
@allure.title("ao3_bridge.js инжектируется на replay-странице (window.__ao3Bridge marker, детерминированная регрессия)")
@pytest.mark.parametrize("replay", [AO3_HOME_SMOKE_FILENAME], indirect=True)
def test_bridge_marker_present_replay(clean_app, replay, driver):
    # Given приложение запущено в replay-режиме, вкладка Browse загружает
    # записанную домашнюю страницу ao3_home_smoke.mitm
    app_steps.wait_ui_ready(driver)
    browser_steps.open_url_and_wait_ready(driver, browser_steps.HOME_URL)

    # Then в JS-контексте страницы присутствует маркер инъекции window.__ao3Bridge
    browser_steps.assert_bridge_marker_present(driver)


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-068")
@allure.title("Селектор work-блёрба и извлечение work id совпадают с живым DOM листинга AO3 (live)")
def test_work_blurb_selector_matches_live_listing(driver):
    # Given приложение запущено live, открыта реальная листинговая страница AO3
    # с ≥1 работой
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, browser_steps.LIVE_LISTING_URL)

    # Then каждый элемент, найденный li[id^="work_"].work.blurb, имеет непустой
    # числовой work id, и их количество совпадает с количеством видимых
    # h4.heading — инвариант, верный для ЛЮБОГО состава работ на странице
    browser_steps.assert_blurb_selector_matches_headings(driver, min_count=1)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-069")
@allure.title("Селектор work-блёрба и извлечение work id совпадают с replay-DOM листинга (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_work_blurb_selector_matches_replay_listing(clean_app, replay, driver):
    # Given приложение запущено в replay-режиме, открыта записанная листинговая
    # страница listing_basic.mitm (5 эталонных работ works.ALL)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then найдены ровно 5 элементов li[id^="work_"].work.blurb, с id
    # work_900000001..work_900000005, чьи извлечённые work id совпадают с ao3_id
    # эталонных работ — тот же контракт, что TC-068, на детерминированном наборе
    work_ids = browser_steps.assert_blurb_selector_matches_headings(driver, min_count=5)
    expected = sorted(w.ao3_id for w in W.ALL)
    assert sorted(work_ids) == expected, (
        f"извлечённые work id листинга {sorted(work_ids)} не совпадают с "
        f"эталонным набором works.ALL {expected}"
    )


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-070")
@allure.title("Rate-кнопка инжектируется в каждый неоценённый work-блёрб живого листинга (live)")
def test_rate_button_injected_on_live_listing(clean_app, driver):
    # Given приложение с чистыми данными (ни одна работа не оценена), режим live,
    # открыта реальная листинговая страница AO3 с ≥1 работой
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, browser_steps.LIVE_LISTING_URL)

    # Then КАЖДЫЙ work-блёрб содержит ровно один [data-ao3-btn-wrap], а внутри
    # него — ровно один [data-ao3-rate-btn] с data-ao3-rate-btn == work id
    # родительского блёрба, в состоянии «неоценено» (прозрачный фон) — DOM-
    # контракт, верный для ЛЮБОГО количества работ на листинге
    browser_steps.assert_every_blurb_has_unrated_rate_button(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-071")
@allure.title("Rate-кнопка инжектируется в каждый неоценённый work-блёрб replay-листинга (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_rate_button_injected_on_replay_listing(clean_app, replay, driver):
    # Given приложение с чистыми данными, режим replay, открыта listing_basic.mitm
    # (5 эталонных работ works.ALL, ни одна не оценена)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then каждая из 5 работ имеет собственную Rate-кнопку с атрибутом, равным её
    # ao3_id, в состоянии «неоценено» — тот же контракт, что TC-070, на
    # детерминированном фиксированном наборе (регрессионный якорь)
    work_ids = browser_steps.assert_every_blurb_has_unrated_rate_button(driver)
    expected = sorted(w.ao3_id for w in W.ALL)
    assert sorted(work_ids) == expected, (
        f"work id с Rate-кнопками {sorted(work_ids)} не совпадают с эталонным "
        f"набором works.ALL {expected}"
    )


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-072")
@allure.title("Rate-кнопка отражает бейдж рейтинга непрозрачным цветом BADGE-палитры на живом листинге (live)")
def test_rate_button_badge_opaque_color_live(clean_app, driver):
    # Given приложение с чистыми данными, режим live, открыта реальная листинговая
    # страница AO3 с работой W (Rate-кнопка видна, не оценена)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, browser_steps.LIVE_LISTING_URL)
    work_id = browser_steps.assert_blurb_selector_matches_headings(driver, min_count=1)[0]

    # When пользователь нажимает Rate-кнопку работы W и выбирает рейтинг R (SAVE)
    # в открывшемся RatingOverlay
    browser_steps.tap_rate_button(driver, work_id)
    rating_steps.rate_via_listing_overlay(driver, "SAVE")

    # Then та же [data-ao3-rate-btn] работы W получает непрозрачный background-color
    # BADGE-палитры (см. заметки TC-072: "непрозрачный" — bg != rgba(0,0,0,0) —
    # достаточная и устойчивая к живой теме/AO3 сверка контракта бейджа)
    browser_steps.assert_rating_badge_visible(driver, work_id)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-073")
@allure.title("Rate-кнопка отражает бейдж рейтинга непрозрачным цветом BADGE-палитры на replay-листинге (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_rate_button_badge_opaque_color_replay(loved_work_seeded, replay, driver):
    # Given приложение запущено в replay-режиме, работа LOVED засеяна с рейтингом
    # SAVE ДО первого рендера листинга, открыта listing_basic.mitm
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then [data-ao3-rate-btn] работы LOVED непрозрачна (бейдж BADGE.SAVE применён)
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)

    # And [data-ao3-rate-btn] остальных 4 работ (не засеяны) остаются в состоянии
    # «неоценено» (прозрачный фон) — закраска per-work, не глобальная
    for other in W.ALL:
        if other.ao3_id != work.ao3_id:
            browser_steps.assert_rate_button_unrated(driver, other.ao3_id)


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-074")
@allure.title("Note-кнопка инжектируется в work-блёрб живого листинга тогда и только тогда, когда есть comment (live)")
def test_note_button_present_iff_comment_live(clean_app, driver):
    # Given приложение с чистыми данными, режим live, открыта реальная листинговая
    # страница AO3 с работой W (не оценена, без комментария) и хотя бы ещё одной
    # другой работой на той же странице
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, browser_steps.LIVE_LISTING_URL)
    work_ids = browser_steps.assert_blurb_selector_matches_headings(driver, min_count=2)
    work_id, other_ids = work_ids[0], work_ids[1:]

    # When пользователь нажимает Rate-кнопку работы W, выбирает рейтинг, раскрывает
    # поле комментария, вводит непустой текст и сохраняет ("Save note")
    comment_text = f"tc074-note-{uuid.uuid4().hex[:8]}"
    browser_steps.tap_rate_button(driver, work_id)
    rating_steps.rate_via_listing_overlay(driver, "SAVE")
    rating_steps.add_note_via_listing_overlay(driver, comment_text)
    rating_steps.dismiss_rating_overlay(driver)

    # Then та же [data-ao3-btn-wrap] работы W получает [data-ao3-note-btn] с title,
    # равным введённому тексту
    browser_steps.assert_note_button_present(driver, work_id, comment_text)

    # And для ЛЮБОЙ другой работы того же листинга (без комментария) Note-кнопка
    # отсутствует — биусловное присутствие, не пример на одной работе (Инвариант
    # TC-074)
    for other_id in other_ids:
        browser_steps.assert_note_button_absent(driver, other_id)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-075")
@allure.title("Note-кнопка инжектируется в work-блёрб replay-листинга тогда и только тогда, когда есть comment (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_note_button_present_iff_comment_replay(disliked_work_with_comment_seeded, replay, driver):
    # Given приложение запущено в replay-режиме, DISLIKED засеяна с непустым
    # комментарием, остальные 4 работы — без комментария, открыта listing_basic.mitm
    work = disliked_work_with_comment_seeded
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then [data-ao3-btn-wrap] работы DISLIKED содержит [data-ao3-note-btn] с title,
    # равным засеянному comment
    browser_steps.assert_note_button_present(driver, work.ao3_id, "TC-075 seeded comment")

    # And остальные 4 работы (без comment) НЕ имеют [data-ao3-note-btn] —
    # детерминированное подтверждение того же биусловного контракта, что TC-074
    # (Инвариант TC-075), на смешанном наборе
    for other in W.ALL:
        if other.ao3_id != work.ao3_id:
            browser_steps.assert_note_button_absent(driver, other.ao3_id)


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-076")
@allure.title("Tag-кнопка инжектируется в work-блёрб живого листинга тогда и только тогда, когда есть личные теги вне AO3-тегов карточки (live)")
def test_tag_button_present_iff_custom_tag_live(clean_app, driver):
    # Given приложение с чистыми данными, режим live, открыта реальная листинговая
    # страница AO3 с работой W (не оценена, без личных тегов)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, browser_steps.LIVE_LISTING_URL)
    work_ids = browser_steps.assert_blurb_selector_matches_headings(driver, min_count=2)
    work_id = work_ids[0]

    # When пользователь нажимает Rate-кнопку работы W, выбирает рейтинг, добавляет
    # личный тег, заведомо отсутствующий среди AO3-тегов карточки W (UUID-текст
    # структурно не может совпасть ни с одним реальным AO3-тегом)
    custom_tag = f"tc076-custom-{uuid.uuid4().hex[:8]}"
    browser_steps.tap_rate_button(driver, work_id)
    rating_steps.rate_via_listing_overlay(driver, "SAVE")
    rating_steps.add_tag_via_listing_overlay(driver, custom_tag)
    rating_steps.dismiss_rating_overlay(driver)

    # Then та же [data-ao3-btn-wrap] работы W получает [data-ao3-tag-btn]
    browser_steps.assert_tag_button_present(driver, work_id)

    # And для ДРУГОЙ работы того же листинга, чей добавленный личный тег СОВПАДАЕТ
    # (без учёта регистра) с одним из её собственных AO3-тегов, [data-ao3-tag-btn]
    # НЕ появляется (getCustomTags фильтрует пересечение с ao3Set) — Инвариант
    # TC-076 проверен на РАЗНОСТИ множеств, не на факте «есть ли вообще личные теги»
    match_work_id, matching_tag = browser_steps.find_blurb_with_ao3_tags(driver, work_ids, work_id)
    browser_steps.tap_rate_button(driver, match_work_id)
    rating_steps.rate_via_listing_overlay(driver, "LIKE")
    rating_steps.add_tag_via_listing_overlay(driver, matching_tag)
    rating_steps.dismiss_rating_overlay(driver)
    # Барьер синхронизации: applyRatings красит Rate- и Tag-кнопки ОДНИМ проходом —
    # дождавшись бейджа рейтинга (наблюдаемый факт того, что round-trip завершился),
    # можно мгновенно (не опросом) проверить отсутствие Tag-кнопки без гонки со
    # временем (см. докстринг browser_steps.assert_tag_button_absent).
    browser_steps.assert_rating_badge_visible(driver, match_work_id)
    browser_steps.assert_tag_button_absent(driver, match_work_id)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-077")
@allure.title("Tag-кнопка инжектируется в work-блёрб replay-листинга тогда и только тогда, когда есть личные теги вне AO3-тегов карточки (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_tag_button_present_iff_custom_tag_replay(disliked_work_with_custom_tag_seeded, replay, driver):
    # Given приложение запущено в replay-режиме, DISLIKED засеяна с личным тегом
    # вне её AO3-тегов, остальные 4 работы — без личных тегов, открыта
    # listing_basic.mitm
    work = disliked_work_with_custom_tag_seeded
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then [data-ao3-btn-wrap] работы DISLIKED содержит [data-ao3-tag-btn]
    browser_steps.assert_tag_button_present(driver, work.ao3_id)

    # And остальные 4 работы (без личных тегов) НЕ имеют [data-ao3-tag-btn] —
    # тот же биусловный контракт, что TC-076 (Инвариант TC-077), на детерминированном
    # смешанном наборе
    for other in W.ALL:
        if other.ao3_id != work.ao3_id:
            browser_steps.assert_tag_button_absent(driver, other.ao3_id)


# --- Batch C (правило 14): форма AO3 Sort & Filter (`#work-filters`) — main-pairing
# include/exclude чекбоксы (TC-078..081) и идемпотентность инъекции Save filter
# (TC-082/083). Переиспользует `rb.SORT_FILTER_FORM_FILENAME`/`SORT_FILTER_FORM_URL`
# (реальная запись `archiveofourown.org/tags/Fluff/works`, Verified в AT-BUG-006/016,
# см. `test_filter_profiles.py` за TC-040). ---

@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-078")
@allure.title("Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (live)")
def test_main_pairing_checkbox_availability_live(clean_app, driver):
    # Given приложение live с чистыми данными, открыта форма Sort & Filter AO3 с
    # раскрытым списком include-relationship-тегов, ни один пункт не отмечен
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_sort_filter_form_relationship_ready(driver, rb.SORT_FILTER_FORM_URL)

    # When пользователь отмечает РОВНО ОДИН чекбокс из #include_relationship_tags
    browser_steps.toggle_relationship_checkbox(driver, "include", 0)

    # Then первым пунктом списка присутствует инжектированный [data-ao3-main-pairing-cb],
    # включён (disabled=false, label непрозрачный)
    browser_steps.assert_relationship_checkbox_enabled(driver, "include")

    # And отметка ВТОРОГО чекбокса (итого 2 отмечено) отключает его — Инвариант TC-078:
    # доступность зависит только от количества отмеченных, не от того, КАКОЙ тег
    browser_steps.toggle_relationship_checkbox(driver, "include", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "include")

    # And снятие ОБЕИХ отметок (0 отмечено) — тоже отключённое состояние
    browser_steps.toggle_relationship_checkbox(driver, "include", 0)
    browser_steps.toggle_relationship_checkbox(driver, "include", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "include")


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-079")
@allure.title("Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)")
@pytest.mark.parametrize("replay", [rb.SORT_FILTER_FORM_FILENAME], indirect=True)
def test_main_pairing_checkbox_availability_replay(clean_app, replay, driver):
    # Given приложение в replay-режиме, открыта sort_filter_form.mitm с раскрытым
    # списком include-relationship-тегов, ни один пункт не отмечен
    app_steps.wait_ui_ready(driver)
    browser_steps.open_sort_filter_form_relationship_ready(driver, rb.SORT_FILTER_FORM_URL)

    # When пользователь отмечает РОВНО ОДИН чекбокс из #include_relationship_tags
    browser_steps.toggle_relationship_checkbox(driver, "include", 0)

    # Then [data-ao3-main-pairing-cb] включён
    browser_steps.assert_relationship_checkbox_enabled(driver, "include")

    # And снятие единственной отметки (0 отмечено) возвращает его в отключённое
    # состояние — тот же контракт, что TC-078, детерминированно на записанной разметке
    browser_steps.toggle_relationship_checkbox(driver, "include", 0)
    browser_steps.assert_relationship_checkbox_disabled(driver, "include")

    # And повторная отметка ДВУХ чекбоксов (итого 2 отмечено) тоже отключает
    browser_steps.toggle_relationship_checkbox(driver, "include", 0)
    browser_steps.toggle_relationship_checkbox(driver, "include", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "include")


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-080")
@allure.title("Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (live)")
def test_exclude_main_pairing_checkbox_availability_live(clean_app, driver):
    # Given приложение live с чистыми данными, открыта форма Sort & Filter AO3 с
    # раскрытым списком exclude-relationship-тегов, ни один пункт не отмечен
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_sort_filter_form_relationship_ready(driver, rb.SORT_FILTER_FORM_URL)

    # When пользователь отмечает РОВНО ОДИН чекбокс из #exclude_relationship_tags
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 0)

    # Then первым пунктом списка присутствует инжектированный
    # [data-ao3-excl-main-pairing-cb], включён
    browser_steps.assert_relationship_checkbox_enabled(driver, "exclude")

    # And отметка ВТОРОГО чекбокса (итого 2 отмечено) отключает его — независимый
    # DOM-узел от TC-078 (include), тот же контракт (Инвариант TC-080)
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "exclude")

    # And снятие ОБЕИХ отметок (0 отмечено) — тоже отключённое состояние
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 0)
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "exclude")

    # And include-чекбокс (независимый DOM-узел) остаётся отключён — ни одна
    # отметка exclude-списка на него не влияет
    browser_steps.assert_relationship_checkbox_disabled(driver, "include")


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-081")
@allure.title("Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)")
@pytest.mark.parametrize("replay", [rb.SORT_FILTER_FORM_FILENAME], indirect=True)
def test_exclude_main_pairing_checkbox_availability_replay(clean_app, replay, driver):
    # Given приложение в replay-режиме, открыта sort_filter_form.mitm с раскрытым
    # списком exclude-relationship-тегов, ни один пункт не отмечен
    app_steps.wait_ui_ready(driver)
    browser_steps.open_sort_filter_form_relationship_ready(driver, rb.SORT_FILTER_FORM_URL)

    # When пользователь отмечает РОВНО ОДИН чекбокс из #exclude_relationship_tags
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 0)

    # Then [data-ao3-excl-main-pairing-cb] включён
    browser_steps.assert_relationship_checkbox_enabled(driver, "exclude")

    # And снятие отметки возвращает чекбокс в отключённое состояние — тот же
    # контракт, что TC-080, детерминированно на записанной разметке
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 0)
    browser_steps.assert_relationship_checkbox_disabled(driver, "exclude")

    # And отметка ДВУХ чекбоксов (итого 2 отмечено) тоже отключает
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 0)
    browser_steps.toggle_relationship_checkbox(driver, "exclude", 1)
    browser_steps.assert_relationship_checkbox_disabled(driver, "exclude")


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-082")
@allure.title("Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (live)")
def test_save_filter_button_idempotent_live(clean_app, driver):
    # Given приложение live с чистыми данными, страница с формой Sort & Filter
    # загружена (форма изначально скрыта CSS narrow-hidden — не мешает проверке,
    # см. sort_filter_form_page.py)
    app_steps.wait_ui_ready(driver)
    browser_steps.open_live_listing(driver, rb.SORT_FILTER_FORM_URL)

    # Then сразу после submit-кнопки формы присутствует РОВНО ОДНА инжектированная
    # кнопка [data-ao3-save-profile]
    browser_steps.assert_save_filter_button_present_once(driver)

    # When форма несколько раз мутирует (class/style #work-filters) — имитация
    # повторного раскрытия/скрытия, каждый раз срабатывает MutationObserver и
    # повторно вызывает injectSaveFilterButton
    browser_steps.mutate_sort_filter_form(driver, times=3)

    # Then кнопка Save filter остаётся ровно одна — идемпотентный гвард держится
    # для ЛЮБОГО числа срабатываний MutationObserver (Инвариант TC-082), не только
    # для одного конкретного клика
    browser_steps.assert_save_filter_button_present_once(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-083")
@allure.title("Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (replay)")
@pytest.mark.parametrize("replay", [rb.SORT_FILTER_FORM_FILENAME], indirect=True)
def test_save_filter_button_idempotent_replay(clean_app, replay, driver):
    # Given приложение в replay-режиме, открыта sort_filter_form.mitm с формой
    # Sort & Filter, изначально скрытой
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.SORT_FILTER_FORM_URL)

    # Then после submit-кнопки формы присутствует РОВНО ОДНА кнопка Save filter
    browser_steps.assert_save_filter_button_present_once(driver)

    # When пользователь дважды переключает видимость формы (раскрыть → скрыть →
    # раскрыть — 3 срабатывания MutationObserver #work-filters)
    browser_steps.mutate_sort_filter_form(driver, times=3)

    # Then кнопка остаётся ровно одна, независимо от количества переключений —
    # тот же контракт идемпотентности, что TC-082, детерминированно на записанной
    # разметке (уже подтверждён вручную в AT-BUG-006, этот кейс формализует находку)
    browser_steps.assert_save_filter_button_present_once(driver)
