"""Тесты области filter-profiles (test-cases/filter-profiles/): управление
сохранёнными AO3-фильтрами (`FilterProfile`) — сохранение из формы Sort & Filter
(TC-040), применение сохранённого профиля (TC-041), удаление профиля (TC-042),
переименование профиля (TC-085/TC-086, test-automator, 2026-07-20).

TC-085/TC-086 переиспользуют существующую инфраструктуру без новой фикстуры/
сидинга (`filter_profile_applied_seeded`/`two_filter_profiles_seeded`, см. TC-041/
TC-042 выше). Новый локатор `SettingsScreen._rename_button_locator` — тот же
приём disambiguation `following::` от текстового узла с именем профиля, что и
`_delete_button_locator`; диалог "Rename filter" переиспользует то же
`className("android.widget.EditText")`, что диалог "Save filter"
(`browser_screen.py::_FILTER_NAME_FIELD`) — оба рендерятся BasicTextField-based
компонентами Compose. TC-086 не различает две одноимённые строки Settings по
UI (см. заметки TC-086.md) — Then читает `filter_profiles` напрямую через
`seed_db.read_filter_profiles()` (host-side, тот же приём, что
`backup_steps.assert_filter_profiles_match` использует для TC-021), не через
on-device sqlite3-бинарь (`settings_steps.assert_no_ratings`-деградация здесь
дала бы молчаливый false-green — у этого кейса нет UI-фолбэка по построению).

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
формы, сверено на живом `.mitm`).

AT-BUG-016 (закрыт test-maintainer, 2026-07-19, 3-я попытка, critic-directed —
см. bugs/AT-BUG-016.md «Обсуждение»/«Верификация»): исходный диагноз — тест не
дожидался фоновой пост-save навигации перед `open_tab("Settings")`, UiAutomator2
tree-dump конкурировал с GPU-компоновкой ещё рендерящейся live-страницы и
крашил qemu (0xc0000005). Три ремедиационных захода: (1) `save_filter_profile_as`
(`browser_steps.py`) дожидается `document.readyState == 'complete'` НОВОЙ
страницы перед возвратом управления; (2) `sort_filter_form.mitm` пересобран
самодостаточным для ПЕРВОЙ живой страницы; (3) добавлен ВТОРОЙ self-contained
flow для пост-save навигации (`work_search[sort_column]=revised_at&
work_search[words_from]=1000`, URL выведен статическим разбором
`#work-filters`/`ao3_bridge.js::injectSaveFilterButton`) — закрывает последнюю
live-forward точку. Это устранило краши qemu полностью, но вскрыло ВТОРУЮ,
ранее замаскированную причину нестабильности: усечение `<link rel=stylesheet>`
(self-contained truncation) снимает CSS-скрытие (`.narrow-hidden` на
`#work-filters`, `.dropdown .menu` на подменю хедера), на которое неявно
полагается `framework/screens/navigation.py::_find_pill` («самый нижний
кликабельный не-WebView View») — без него `_find_pill` подбирал ссылку ВНУТРИ
WebView (напр. `/people/search`) вместо нативной ручки-пилюли, кликал по ней
и уводил WebView на реальную live-страницу. Восстановлено минимальным inline
`<style>` в обоих flow (без единого сетевого запроса) — точное соответствие
исходному поведению живого AO3. 3 зелёных подряд подтверждены, `automated_by`
в TC-040.md заполнен, `@pytest.mark.skip` снят.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, settings_steps


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-085")
@allure.title("Переименование фильтр-профиля обновляет отображаемое имя и не меняет queryString")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_rename_filter_profile_keeps_query_string(replay, filter_profile_applied_seeded, driver):
    old_name = filter_profile_applied_seeded
    new_name = "My renamed search"

    # Given в Settings в секции "Saved AO3 Filters" отображается сохранённый профиль
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_filter_profile_listed(driver, old_name)

    # When пользователь нажимает "Rename", очищает предзаполненное поле и вводит
    # новое имя, подтверждает
    settings_steps.rename_filter_profile(driver, old_name, new_name)

    # Then профиль отображается под новым именем, прежнее имя отсутствует
    settings_steps.assert_filter_profile_listed(driver, new_name)
    settings_steps.assert_filter_profile_not_listed(driver, old_name)

    # And при переходе на листинговую страницу и выборе профиля под новым именем
    # страница обновляется тем же URL, что и до переименования — queryString
    # переименование не затронуло
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, new_name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)


@pytest.mark.p1
@allure.id("TC-086")
@allure.title("Переименование в имя-дубликат допускается: обе записи с queryString сохраняются раздельно")
def test_rename_filter_profile_to_duplicate_name(two_filter_profiles_seeded, driver):
    name_a, name_b = two_filter_profiles_seeded

    # Given в Settings отображаются 2 сохранённых профиля с разными именами
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_filter_profile_listed(driver, name_a)
    settings_steps.assert_filter_profile_listed(driver, name_b)

    # When пользователь переименовывает "Profile B" в имя, совпадающее с "Profile A"
    # (нет диалога ошибки/конфликта — операция просто завершается)
    settings_steps.rename_filter_profile(driver, name_b, name_a)

    # Then в Settings отображаются ДВЕ отдельные строки с именем "Profile A" —
    # список не схлопнулся в одну запись
    settings_steps.assert_filter_profile_count(driver, name_a, 2)

    # And в БД filter_profiles присутствуют ДВЕ записи с name="Profile A": одна с
    # исходным queryString первого профиля, другая — с queryString бывшего
    # "Profile B", неизменившимся при переименовании
    settings_steps.assert_filter_profiles_have_query_strings(
        name_a,
        [
            "work_search%5Bquery%5D=profile-a-test",
            "work_search%5Bquery%5D=profile-b-test",
        ],
    )


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
