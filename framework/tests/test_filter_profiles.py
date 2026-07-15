"""Тесты области filter-profiles (test-cases/filter-profiles/): управление
сохранёнными AO3-фильтрами (`FilterProfile`) — сохранение из формы Sort & Filter
(TC-040), применение сохранённого профиля (TC-041), удаление профиля (TC-042).

AT-BUG-006, инкремент 2 (грань 3 критерия готовности): TC-042 доведён до
автоматизации в этом инкременте — кейс, наименее зависящий от реальной формы
Sort & Filter (bugs/AT-BUG-006.md критерий готовности прямо называет TC-041/
TC-042 «наименее зависящими от формы»). TC-042 использует только Settings screen
(секция «Saved AO3 Filters») и нативную `FilterPanel` листинга (BottomBar.kt) —
она видна на ЛЮБОЙ странице, чей URL проходит `BrowserViewModel.FILTERABLE_PAGE`
regex, независимо от того, есть ли на самой странице реальная разметка формы
Sort & Filter (`#work-filters`); существующая synthetic replay-фикстура
`listing_basic.mitm` (`.../works?...`) уже подходит под этот regex.

TC-041 НЕ автоматизирован в этом инкременте: `applyFilter` (BrowserViewModel.kt)
добавляет параметры `work_search[...]` к URL при выборе профиля — при
`server_replay` это НЕ совпадает ни с одним записанным flow synthetic-фикстуры
(хэш матчинга учитывает query, см. `framework/data/recording_builder.py`) и уходит
на живой AO3 (`server_replay_extra=forward`) — вносит сетевую зависимость в offline
по духу replay-тест. Решение (расширить `recording_builder.py` под filtered-URL,
либо явно принять live-переход) — вне скоупа этого инкремента, см.
`bugs/AT-BUG-006.md` Обсуждение.

TC-040 — не в этом инкременте (см. non-goals диспатча): реальная replay-запись
формы Sort & Filter (`framework/data/recordings/sort_filter_form.mitm`) записана
и верифицирована (запись + round-trip через Appium), но сам зелёный UI-тест по
TC-040 не обязателен критерием готовности AT-BUG-006 и не входит в этот файл.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, settings_steps


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-042")
@allure.title("Удаление фильтр-профиля из Settings убирает его из списка и панели")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_delete_filter_profile(replay, two_filter_profiles_seeded, driver):
    name_a, name_b = two_filter_profiles_seeded

    # Given в Settings в секции "Filters" отображаются 2 сохранённых профиля
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_filter_profile_listed(driver, name_a)
    settings_steps.assert_filter_profile_listed(driver, name_b)

    # When пользователь нажимает кнопку удаления рядом с "Profile A"
    settings_steps.delete_filter_profile(driver, name_a)

    # Then "Profile A" исчезает из списка в Settings, "Profile B" остаётся
    settings_steps.assert_filter_profile_not_listed(driver, name_a)
    settings_steps.assert_filter_profile_listed(driver, name_b)

    # And при переходе на листинговую страницу и раскрытии фильтр-панели
    # "Profile A" больше не предлагается в списке выбора
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.assert_filter_not_offered(driver, name_a)
    browser_steps.assert_filter_offered(driver, name_b)
