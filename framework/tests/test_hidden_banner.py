"""Тесты области «баннер над листингом скрытых работ» (feature
`bridge-hidden-works-banner`, R-06, `ao3_bridge.js::updateHiddenBanner`).

TC-197 (test-automator, П1 spec-p1-dedup v7, docs/tasks/p1-dedup-lead-pass.md Р2):
поглощает TC-199/TC-200/TC-201 — четыре P1-кейса были представителями одной
таблицы истинности по паре булевых флагов `(ratedHidden, filterActive)`
(`ao3_bridge.js:509-519`), сведены в ОДИН параметризованный тест по решению
test-designer (см. TC-197.md «Заметки для автоматизации»: «параметризация
ОДНОГО теста по паре флагов... варианты НЕ образуют journey/чекпойнты»).

Given каждого варианта — одна и та же дорогая инфраструктура
(`library_and_filter_profile_seeded`: `seeded_library` + профиль "My saved
search", тот же `queryString`, что TC-041/TC-181..185), варьируется только
состояние тумблера «Hide Disliked works» ДО навигации и то, применяет ли
When сохранённый фильтр-профиль (варианты B/C) или нет (A/D) — общая
инфраструктура НЕ требует отдельной фикстуры на вариант (см. докстринг
фикстуры в conftest.py).

Негативный Then варианта D («узла нет») — НЕ вакуумный (класс 3 ложно-зелёных
негативов, CLAUDE.md): `updateHiddenBanner()` вызывается синхронно на КАЖДОЙ
загрузке страницы (`ao3_bridge.js:1075`), независимо от значений флагов — путь
к этому коду гарантированно достижим; варианты A/B/C того же параметризованного
кейса — ПОЗИТИВНЫЙ КОНТРОЛЬ, доказывающий, что та же самая инфраструктура
(та же навигация, та же bridge-инъекция) реально производит узел с непустым
текстом при true-флагах — отсутствие узла в D объясняется именно гейтом
`ratedHidden || filterActive` (`ao3_bridge.js:511`), а не тем, что код вообще
не выполнился.

Class 2 (идемпотентный условный сеттер, CLAUDE.md): `settings_steps.
set_hide_rating` тапает только при несовпадении текущего состояния с желаемым —
явный `assert_rating_hidden` СРАЗУ после вызова во ВСЕХ четырёх вариантах
(не только там, где тумблер реально переключается), чтобы молча несработавший
тап не оставил Given неверифицированным ни в одном варианте."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, settings_steps

_BANNER_VISIBILITY_ONLY = "Some works may be hidden by your visibility settings"
_BANNER_FILTER_ONLY = "Some works may be hidden by the active AO3 filter"
_BANNER_BOTH = "Some works may be hidden by visibility settings and active AO3 filter"


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-197")
@allure.title(
    "Баннер над листингом отражает РОВНО причину скрытия по паре флагов "
    "(ratedHidden × filterActive): дословный текст на каждую комбинацию, узла нет при обеих false"
)
@pytest.mark.parametrize(
    "disliked_hidden, use_filter, expected_banner",
    [
        pytest.param(True, False, _BANNER_VISIBILITY_ONLY, id="A-rated-hidden-only"),
        pytest.param(False, True, _BANNER_FILTER_ONLY, id="B-filter-active-only"),
        pytest.param(True, True, _BANNER_BOTH, id="C-both-causes"),
        pytest.param(False, False, None, id="D-neither-cause"),
    ],
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_hidden_banner_matches_flag_combination(
    replay, library_and_filter_profile_seeded, driver,
    disliked_hidden, use_filter, expected_banner,
):
    name = library_and_filter_profile_seeded

    # Given тумблер «Hide Disliked works» приведён к нужному для варианта
    # состоянию ДО навигации листинга (set_hide_rating идемпотентен — тап
    # только при несовпадении, поэтому состояние подтверждается ЯВНЫМ assert'ом
    # сразу после, независимо от того, потребовался ли реальный тап)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.set_hide_rating(driver, "Disliked", disliked_hidden)
    settings_steps.assert_rating_hidden(driver, "Disliked", disliked_hidden)
    app_steps.open_tab(driver, "Browse")

    # When пользователь открывает базовый листинг; варианты B/C дополнительно
    # раскрывают фильтр-панель и выбирают сохранённый профиль "My saved search"
    # (тот же путь, что TC-041 test_apply_filter_profile) — эта навигация И
    # есть переход на итоговую (отфильтрованную) страницу, чей баннер проверяет Then
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    if use_filter:
        browser_steps.open_filter_dropdown(driver)
        browser_steps.select_filter_option(driver, name)
        browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)

    # Then над `ol.work.index.group` присутствует узел с ДОСЛОВНЫМ текстом,
    # предписанным парой флагов этого варианта — либо узел отсутствует (D)
    if expected_banner is None:
        browser_steps.assert_hidden_banner_absent(driver)
    else:
        browser_steps.assert_hidden_banner_text(driver, expected_banner)

    # And сообщение и факт скрытия согласованы, баннер не «сирота»: блёрб
    # работы DISLIKED скрыт РОВНО когда ratedHidden=true этого варианта, видим —
    # когда false (инвариант, общий для всех четырёх вариантов кейса)
    if disliked_hidden:
        browser_steps.assert_blurb_hidden(driver, W.DISLIKED.ao3_id)
    else:
        browser_steps.assert_blurb_visible(driver, W.DISLIKED.ao3_id)
