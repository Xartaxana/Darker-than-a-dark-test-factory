"""Infinite scroll на листинговой странице (`ao3_bridge.js:520-615`,
docs/01-test-strategy.md §9 «reading-UX жесты и их тумблеры» —
browse-infinite-scroll + settings-infinite-scroll-toggle). Тумблер
`infiniteScroll: Boolean = true` (`SettingsScreen.kt:77`) устанавливается ДО
перехода на листинговую страницу — гейт `ao3_bridge.js:530` (`window.
__ao3InfiniteScroll !== false && document.querySelector('li[id^="work_"].work.
blurb')`) вычисляется ОДИН РАЗ при инъекции (`onPageFinished`, BrowserScreen.kt
~604/~613): тумблер, включённый ПОСЛЕ загрузки страницы, не подключит подписку
scroll-листенера ретроактивно (см. TC-129, OFF-сторона — не автоматизирована в
этом модуле).

`listing_paginated.mitm` (5 листинговых страниц, `page=1..5`, 1 work-блёрб на
страницу, реальная разметка пагинации AO3) — единственная replay-фикстура,
покрывающая пагинацию/infinite-scroll (см. `recording_builder.py`
`LISTING_PAGINATED_FILENAME` докстринг за полным обоснованием B1/B2/F2/F3/F4).

TC-130 (ON-сторона) единственный автоматизирован здесь — TC-129 (OFF, «скролл
НЕ подгружает следующую страницу») остаётся Approved, следующий диспатч."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, settings_steps


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-130")
@allure.title("Infinite scroll ON: скролл к концу листинга подгружает следующую страницу без навигации")
@pytest.mark.parametrize("replay", [rb.LISTING_PAGINATED_FILENAME], indirect=True)
def test_infinite_scroll_on_loads_next_page_in_background(replay, clean_app, driver):
    # Given infinite_scroll = ON (дефолт, установлен явно ДО перехода на листинг —
    # гейт вычисляется один раз при инъекции), открыта страница 1 из 5
    # `listing_paginated.mitm` (ровно 1 li[id^="work_"], нумерованная пагинация
    # скрыта, Next остаётся)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_infinite_scroll(driver)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_PAGINATED_URL)
    ids_before = browser_steps.snapshot_work_blurb_ids(driver)
    assert len(ids_before) == 1, (
        f"Given TC-130 требует ровно 1 work-блёрб на странице 1 `listing_paginated.mitm`, "
        f"фактически {len(ids_before)}: {ids_before}"
    )
    location_before = browser_steps.get_webview_location(driver)

    # When пользователь скроллит листинг вниз (прицельный минимальный скролл — на
    # этой фикстуре предикат подгрузки уже истинен ПРИ ЗАГРУЗКЕ страницы, скролл
    # нужен как триггерящее scroll-событие, не как способ довести ol до порога)
    browser_steps.trigger_infinite_scroll_load(driver, min_blurb_count=len(ids_before))

    # Then страница 2 подгружается ФОНОВЫМ запросом (fetch, не навигацией):
    # >= 2 work-блёрба (не РОВНО 2 — возможен каскад от scroll anchoring), среди
    # них есть хотя бы один id, отсутствовавший в снимке ДО скролла, все id
    # ПОСЛЕ уникальны, pathname/query вкладки не изменились
    new_ids = browser_steps.assert_infinite_scroll_appended_new_unique_blurbs(driver, ids_before)
    browser_steps.assert_webview_location_unchanged(driver, location_before)

    # And у КАЖДОГО вновь появившегося work-блёрба (diff-множество new_ids)
    # инжектирована собственная Rate-кнопка — bridge остаётся живым для
    # подгруженного контента, не только для исходной страницы
    browser_steps.assert_rate_buttons_present_for(driver, new_ids)
