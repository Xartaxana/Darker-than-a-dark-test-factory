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

TC-041 (test-automator, R14 filterprofiles-batch-040-041, 2026-07-18): блокер,
задокументированный test-maintainer'ом выше (`applyFilter` строит URL с
`work_search[...]`-параметрами профиля, не совпадающий ни с одним записанным flow
synthetic-фикстуры), закрыт РАСШИРЕНИЕМ `recording_builder.py`/
`scripts/build_replay_recordings.py::build_listing_basic` — теперь `listing_basic.mitm`
несёт ВТОРОЙ flow под `rb.LISTING_FILTERED_URL` (та же HTML, что и базовый listing).
`filter_profile_applied_seeded` (conftest.py) сеет профиль с `queryString`, для
которого `applyFilter` строит URL БАЙТ-В-БАЙТ равный этому второму flow — server-replay
находит совпадение, live-переход (`server_replay_extra=forward`) не требуется.
Выбор в пользу расширения recording_builder, а не принятия live-перехода — по
решению, оставленному в очереди test-maintainer'ом (см. `bugs/AT-BUG-006.md`
Обсуждение, запись 2026-07-15).

TC-040 (test-automator, тот же батч): реальная replay-запись формы Sort & Filter
(`framework/data/recordings/sort_filter_form.mitm`, AT-BUG-006 инкремент 2) уже
была записана и верифицирована — этот инкремент добавляет сам UI-тест. Форма
скрыта CSS-классом `narrow-hidden` на узких вьюпортах (реальный toggle — во внешнем
site-JS AO3, не воспроизведённом в записи); значение поля/клик по инжектированной
"Save filter" выполняются через JS DOM API вместо Selenium `.send_keys()/.click()`
(не требуют `displayed=True`, см. `framework/web/sort_filter_form_page.py`).
`queryString` сохранённого профиля НЕ проверяется посимвольно (см. заметки
TC-040.md) — после подтверждения диалога `confirmSaveFilter` (BrowserViewModel.kt)
дополнительно навигирует активную вкладку на URL с параметрами формы (включая
ВСЕГДА непустой `work_search[sort_column]=revised_at` — дефолтный `<select>`
формы, сверено на живом `.mitm`), который тест НЕ дожидается и не проверяет —
эта фоновая навигация уходит в live-сеть (`server_replay_extra=forward`), но
это ТОТ ЖЕ класс сетевой зависимости, что уже принят для этой фикстуры целиком
(реальная страница ссылается на внешние CSS/JS/картинки, не записанные в
`.mitm` — сам просмотр формы уже требует `forward` для суб-ресурсов), не новый
блокер: тест не ждёт и не проверяет состояние WebView после Save, поэтому
фоновая навигация не влияет на исход.
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


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-041")
@allure.title("Применение сохранённого фильтр-профиля из панели на листинговой странице")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_apply_filter_profile(replay, filter_profile_applied_seeded, driver):
    name = filter_profile_applied_seeded

    # Given открыта листинговая страница без применённого фильтра
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # When пользователь раскрывает фильтр-панель и выбирает "My saved search"
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)

    # Then страница обновляется с параметрами queryString этого профиля
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)
    # And фильтр-панель показывает "My saved search" как активно применённый
    browser_steps.assert_active_filter_shown(driver, name)


@pytest.mark.p1
@pytest.mark.replay
@pytest.mark.skip(reason="AT-BUG-016: детерминированно крашит qemu-эмулятор (0xc0000005) при live-рендере + переходе в Settings — временный guard, чтобы regression/p1-прогоны не роняли эмулятор до починки долга")
@allure.id("TC-040")
@allure.title("Save filter сохраняет текущий запрос AO3 Sort&Filter под именем")
@pytest.mark.parametrize("replay", [rb.SORT_FILTER_FORM_FILENAME], indirect=True)
def test_save_filter_profile(replay, clean_app, driver):
    profile_name = "My saved search"

    # Given открыта форма Sort & Filter AO3 с заданным значением поля (word count min),
    # форма не отправлена
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_sort_filter_form(driver, rb.SORT_FILTER_FORM_URL, "1000")

    # When пользователь нажимает инжектированный "Save filter", в диалоге вводит
    # имя "My saved search" и подтверждает
    browser_steps.tap_save_filter_button(driver)
    browser_steps.assert_save_filter_dialog_visible(driver)
    browser_steps.save_filter_profile_as(driver, profile_name)

    # Then новый профиль появляется в списке сохранённых фильтров в Settings
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_filter_profile_listed(driver, profile_name)
