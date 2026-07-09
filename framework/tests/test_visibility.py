"""Тесты области visibility (test-cases/visibility/): скрытие блёрбов работ на
листинговой странице AO3 фильтрацией по рейтингу (`applyAllFilters`, ao3_bridge.js).

Требует replay-фикстуру листинга (AT-BUG-004, инкремент 1): синтетические `ao3_id`
из `framework/data/works.py` не существуют на archiveofourown.org, поэтому листинг
с их блёрбами не может быть записан живым mitmdump-прогоном — только сконструирован
1:1 по проверенной разметке AO3 (`framework/data/recording_builder.py`,
`framework/data/recordings/listing_basic.mitm`, генерируется
`python scripts/build_replay_recordings.py`).

Только TC-013 доведён до автоматизации в этом инкременте — доказательство того, что
replay-фикстура пригодна (см. критерий готовности инкремента в `bugs/AT-BUG-004.md`).
TC-014/015/043/045 используют ту же фикстуру и разблокированы для test-automator, но
не закодированы здесь (решение о переводе Review → Approved не за test-maintainer).
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps


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
