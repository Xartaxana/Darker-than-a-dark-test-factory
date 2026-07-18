"""Тесты области visibility (test-cases/visibility/): скрытие блёрбов работ на
листинговой странице AO3 фильтрацией по рейтингу (`applyAllFilters`, ao3_bridge.js).

Требует replay-фикстуру листинга (AT-BUG-004, инкремент 1): синтетические `ao3_id`
из `framework/data/works.py` не существуют на archiveofourown.org, поэтому листинг
с их блёрбами не может быть записан живым mitmdump-прогоном — только сконструирован
1:1 по проверенной разметке AO3 (`framework/data/recording_builder.py`,
`framework/data/recordings/listing_basic.mitm`, генерируется
`python scripts/build_replay_recordings.py`).

TC-013/014/015 доведены до автоматизации (visibility-батч 2026-07-18) — доказательство
того, что replay-фикстура пригодна (см. критерий готовности инкремента в
`bugs/AT-BUG-004.md`). TC-043/045 используют ту же фикстуру, но живут в
`test_rating_listing.py` (написаны раньше, в rating-батче) — не дублируются здесь.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, settings_steps


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-013")
@allure.title("Work с рейтингом Disliked скрыт на листинге при включённой фильтрации (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_disliked_hidden_on_listing(replay, seeded_library, driver):
    # Given приложение с засеянной библиотекой (в т.ч. работа W=DISLIKED с
    # rating=DISLIKE), фильтрация включена по умолчанию (Disliked в hidden-set,
    # window.__ao3HiddenRatings)
    app_steps.wait_ui_ready(driver)

    # When пользователь открывает replay-листинг, содержащий блёрбы всех эталонных
    # работ (framework/data/works.py::ALL), включая W
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then блёрб Disliked-работы скрыт (applyAllFilters), а блёрб Loved-работы
    # остаётся виден — фильтрация применяется избирательно, не разом ко всем блёрбам
    browser_steps.assert_blurb_hidden(driver, W.DISLIKED.ao3_id)
    browser_steps.assert_blurb_visible(driver, W.LOVED.ao3_id)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-014")
@allure.title("Work без рейтинга (или comment-only, rating=null) никогда не скрывается фильтрацией (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_no_rating_or_comment_only_never_hidden(replay, comment_only_work, driver):
    # Given работа A (LOVED) вообще не имеет строки WorkRating (clean_state внутри
    # comment_only_work её не засеивает — «отсутствие строки» и есть Given), работа B
    # (comment_only_work=KUDOSED) имеет rating=NULL и непустой comment; фильтрация
    # включена по умолчанию, Disliked в hidden-set
    work_b = comment_only_work
    work_a = W.LOVED
    app_steps.wait_ui_ready(driver)

    # When пользователь открывает replay-листинг, содержащий блёрбы обеих работ
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then обе работы видны — скрытие фильтрацией применяется ТОЛЬКО к непустому
    # rating, входящему в hidden-ratings set; ни отсутствие строки WorkRating (A), ни
    # явный rating=NULL при наличии comment (B) никогда не скрываются, независимо от
    # состояния фильтра/hidden-set — инвариант проверен на двух разных представителях
    # негативного случая сразу (полное отсутствие строки vs явный null)
    browser_steps.assert_blurb_visible(driver, work_a.ao3_id)
    browser_steps.assert_blurb_visible(driver, work_b.ao3_id)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-015")
@allure.title("Выключение per-rating тумблера «Hide Disliked works» показывает Disliked на листинге (replay)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_disliked_visible_after_hide_toggle_off(replay, seeded_library, driver):
    # Given приложение с засеянной библиотекой (в т.ч. работа W=DISLIKED, rating=DISLIKE),
    # тумблер «Hide Disliked works» включён по умолчанию (hiddenRatings={DISLIKE}) — то
    # же исходное состояние, что TC-013: открыт листинг, блёрб W скрыт
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_blurb_hidden(driver, W.DISLIKED.ao3_id)

    # When пользователь в Settings выключает тумблер «Hide Disliked works»
    # (viewModel.toggleHideRating(Rating.DISLIKE) удаляет DISLIKE из hiddenRatings) —
    # реальный продакшн-путь LIVE-PUSH'ит смену фильтра на уже открытую вкладку без
    # ре-навигации: MainActivity.kt:169-171 LaunchedEffect(hiddenRatings) реагирует на
    # смену settingsUiState.hiddenRatings, BrowserViewModel.kt:664-668 setHiddenRatings
    # зовёт evalJsAllTabs("window.setHiddenRatings(...)"), а ao3_bridge.js:443-446
    # window.setHiddenRatings сразу пишет __ao3HiddenRatings И вызывает applyAllFilters()
    # на текущей странице — поэтому здесь только возвращаем фокус на уже открытую
    # вкладку Browse, БЕЗ повторной навигации/reload листинга
    app_steps.open_tab(driver, "Settings")
    settings_steps.set_hide_rating(driver, "Disliked", False)
    app_steps.open_tab(driver, "Browse")

    # Then блёрб работы W теперь виден — hiddenRatings больше не содержит DISLIKE, ни
    # одна работа с этим рейтингом впредь не исключается из рендера (видимость и
    # хранимый rating — независимые свойства: тумблер влияет только на первое)
    browser_steps.assert_blurb_visible(driver, W.DISLIKED.ao3_id)
    # And бейдж/цвет Rate-кнопки работы W по-прежнему отражает Disliked — визуальный
    # бейдж не зависит от тумблера скрытия, только видимость самого блёрба
    browser_steps.assert_rating_badge_visible(driver, W.DISLIKED.ao3_id)
