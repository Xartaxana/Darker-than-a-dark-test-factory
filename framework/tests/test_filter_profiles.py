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

TC-181/182/183/184/185 (test-automator, 2026-08-14, батарея тумблера Auto-apply
on navigation, `docs/01-test-strategy.md §9`): пять кейсов вокруг одного и того
же механизма (`autoApplyFilter`/`pendingFilterApplication`/`activeFilterId`,
`BrowserViewModel.kt`) — дефолт+реактивность тумблера (TC-181), level-путь ON
(TC-182), edge/идемпотентность guard'а `!url.contains("work_search")` (TC-183),
off-инвариант (TC-184, регрессионный замок фактического поведения — задуманность
НЕ подтверждена, см. TC-184.md), edge-исключение внутри OFF-ветки через
`pendingFilterApplication` (TC-185). Общая инфраструктура — та же, что TC-041/
TC-042 (`filter_profile_applied_seeded`, `rb.LISTING_BASIC_URL`/
`LISTING_FILTERED_URL`, `browser_steps.open_filter_dropdown`/
`select_filter_option`/`assert_active_tab_url`/`assert_active_filter_shown`).

Достижение Given «профиль активен» во всех пяти кейсах — тем же путём, что уже
использует TC-041/TC-182 (выбор профиля из FilterPanel один раз ДО основного
When, см. заметки TC-182.md) — прямая seed-запись `active_filter_profile_id` в
SharedPreferences мимо UI не используется.

Разбор Given+When TC-184 (важно для чтения теста; переписано в rework attempt 2,
критик-вход B1 — прежняя редакция этого абзаца ошибочно утверждала, что
буквальное раздельное состояние недостижимо; критик проследил код и показал, что
это ФАКТИЧЕСКИ НЕВЕРНО): буквальное раздельное состояние «профиль активен, вкладка
уже на `LISTING_BASIC_URL` без параметров, тумблер OFF» ДОСТИЖИМО как отдельно
наблюдаемое устойчивое состояние — применить профиль кнопкой при ON (вкладка
временно на `LISTING_FILTERED_URL`), затем host-initiated `open_listing`
(`driver.get()`) обратно на `LISTING_BASIC_URL` (при ON `onPageLoaded` НЕ трогает
`activeFilterId` — снятие профиля обусловлено `!autoApplyFilter`,
`BrowserViewModel.kt:501-504`, а `autoApplyFilter` в этот момент ещё `true`),
затем переключить тумблер в OFF (Settings-действие без навигации WebView) — Given
достигнут, вкладка НИКУДА не навигировала после переключения OFF.

Тест тем не менее воспроизводит Given/When как ЕДИНУЮ последовательность (одна
прямая навигация `LISTING_FILTERED_URL` -> `LISTING_BASIC_URL`, которая
одновременно завершает Given и есть сам When), а не раздельно — настоящая причина
не в недостижимости раздельной формы, а в том, что раздельная форма потребовала
бы ВТОРОЙ, уже SAME-URL навигации на `LISTING_BASIC_URL` (вкладка на нём уже
стоит после промежуточного host-перехода) для срабатывания самого When — а
`driver.get()`/host-initiated `loadUrl` на уже открытый URL в этом репозитории
ЭМПИРИЧЕСКИ no-op (`onPageFinished`/`onPageLoaded` не вызывается, прецедент
TC-020, см. докстринг `settings_steps.reload_active_webview_page`). Схлопнутая
форма — единственная прямая `LISTING_FILTERED_URL` -> `LISTING_BASIC_URL`
навигация (разные строки URL, не same-URL ни для какого механизма навигации) —
свободна от этого класса риска независимо от выбора host/renderer-механизма для
самого перехода.

Дискриминатор от TC-185 (та же по форме навигация при OFF) — именно отсутствие
`select_filter_option` внутри самого When: TC-184 использует
`navigate_listing_via_page_js` (обычная renderer-initiated навигация, НЕ через
кнопку применения фильтра — rework attempt 2, критик-вход B1: заменено с
host-initiated `open_listing`, которая не доходит до `shouldOverrideUrlLoading`,
см. докстринг функции), TC-185 — `select_filter_option` (кнопка, host-initiated
`applyFilter`/`loadUrl`).

Предпосылка ОХВАТА TC-182/TC-183 закреплена ОТДЕЛЬНЫМ ПОСТОЯННЫМ узлом
`test_same_url_renderer_navigation_reaches_interceptor` (critic-раунд 4, блокер
B1). Не-вакуумность TC-183 держится на эмпирическом факте «same-URL
renderer-initiated навигация ДОХОДИТ до `shouldOverrideUrlLoading`», который до
раунда 4 существовал ТОЛЬКО как ПРОЗА в докстринге
`browser_steps.navigate_listing_via_page_js` (одноразовый живой прогон). Проза не
падает: умри предпосылка (смена WebView/chromedriver, регрессия в
`BrowserScreen.kt:616-631`) — TC-183 остался бы ЗЕЛЁНЫМ по посторонней причине
(«queryString не дописан, потому что навигация не дошла до кода, который guard
охраняет»), молча потеряв весь свой предмет. Узел-замок делает ту же предпосылку
наблюдаемой ПОЗИТИВНЫМ Then, поэтому её смерть = красный узел, а не тихо-зелёный
TC-183. Узел НЕ тест-кейс: TC-артефакта и ссылки `automated_by` на него нет,
`@allure.id` — описательный слаг (конвенция инфраструктурных узлов репозитория:
`assert-holds-for-*`, `AT-BUG-047-*`; `scripts/arch_check.py` требует `@allure.id`
И suite-маркер на КАЖДОМ тесте, поэтому вариант «без id» неисполним).
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


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-181")
@allure.title("«Auto-apply on navigation» включён по умолчанию и переключение в Settings доезжает до Browser без рестарта")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_apply_filter_default_on_reactive_toggle(replay, clean_app, driver):
    # Given приложение только что запущено на чистых данных
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")

    # Then тумблер «Auto-apply on navigation» в состоянии ON (дефолт)
    settings_steps.assert_auto_apply_filter_enabled(driver, True)

    # When пользователь переключает тумблер в OFF
    settings_steps.set_auto_apply_filter_toggle(driver, False)

    # Then SharedPreferences ao3_settings немедленно содержит auto_apply_filter=false
    settings_steps.assert_auto_apply_filter_pref(False)

    # When пользователь (без рестарта приложения, без ухода из Settings) сразу
    # переходит на Browse и открывает филируемую листинговую страницу
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # Then связка Settings->MainActivity->BrowserViewModel учла новое значение
    # СРАЗУ (реактивно, без рестарта): страница загружается штатно, БЕЗ дописанного
    # фильтра — полное поведение ON/OFF-путей закрывают TC-182..185, здесь предмет
    # кейса ограничен фактом немедленной реактивности переключения
    browser_steps.assert_active_tab_url(driver, rb.LISTING_BASIC_URL)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-182")
@allure.title("ON: переход на филируемую страницу листинга автоматически дописывает queryString активного профиля")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_apply_filter_on_navigation_appends_active_profile(replay, filter_profile_applied_seeded, driver):
    name = filter_profile_applied_seeded

    # Given тумблер Auto-apply — ON (дефолт, сверяется явным assert'ом — хардening
    # rework attempt 2, критик-вход: без него условие ON непроверяемо самим Then),
    # вкладка Browse на LISTING_BASIC_URL без параметров фильтра; профиль
    # устанавливается активным одноразовым ручным применением из FilterPanel ДО
    # основного When (тот же приём, что TC-041)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_auto_apply_filter_enabled(driver, True)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)
    browser_steps.assert_active_filter_shown(driver, name)

    # When пользователь переходит (навигирует WebView) на филируемую страницу
    # листинга ЗАНОВО — второй переход на базовый URL, уже после того, как профиль
    # стал активным (не повторяет TC-041/ручное применение). Renderer-initiated
    # навигация (`window.location.href`, не `driver.get()`) — `shouldOverrideUrlLoading`
    # перехватывает только навигации, инициированные САМОЙ страницей (клик по
    # ссылке/JS-редирект), см. докстринг `browser_steps.navigate_listing_via_page_js`
    # за красной пробой, доказавшей это эмпирически на этом самом кейсе.
    browser_steps.navigate_listing_via_page_js(driver, rb.LISTING_BASIC_URL)

    # Then shouldOverrideUrlLoading перехватывает загрузку и перезагружает вкладку
    # по URL с дописанным queryString активного профиля — итоговый URL побайтово
    # равен LISTING_FILTERED_URL
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)
    # And FilterPanel листинга показывает «My saved search» как активно применённый
    browser_steps.assert_active_filter_shown(driver, name)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-183")
@allure.title("ON: страница, уже несущая work_search, НЕ получает повторного авто-применения фильтра (guard, идемпотентность)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_apply_filter_guard_skips_url_with_work_search(replay, filter_profile_applied_seeded, driver):
    name = filter_profile_applied_seeded

    # Given профиль «My saved search» активен, тумблер Auto-apply ON (сверяется
    # явным assert'ом — хардening rework attempt 2, критик-вход: без него условие
    # ON непроверяемо самим Then), активная вкладка уже открыта на
    # LISTING_FILTERED_URL (URL уже содержит work_search)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_auto_apply_filter_enabled(driver, True)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)

    # When страница на этой же вкладке перезагружается (повторная загрузка того же
    # URL, симулируя pull-to-refresh). Renderer-initiated навигация
    # (`window.location.href`, ДОСТИГАЕТ shouldOverrideUrlLoading — делает эффект
    # гипотетического бага ДОСТИЖИМЫМ, не только «не дописан, потому что навигация
    # не дошла до перехватчика вовсе», см. докстринг
    # `browser_steps.navigate_listing_via_page_js`); НЕ `driver.navigate().refresh()`/
    # `window.location.reload()` — тот же официальный докстринг Android отдельно
    # исключает reload-навигацию из вызова колбэка, что сделало бы Then этого кейса
    # вакуумно истинным по ДРУГОЙ причине. Предпосылка «same-URL renderer-initiated
    # навигация доходит до shouldOverrideUrlLoading» НЕСЁТ всю не-вакуумность этого
    # кейса, поэтому закреплена ОТДЕЛЬНЫМ ПОСТОЯННЫМ УЗЛОМ
    # `test_same_url_renderer_navigation_reaches_interceptor` (ниже в этом файле,
    # critic-раунд 4, блокер B1): тот же ON + активный профиль, та же
    # `navigate_listing_via_page_js` на ТОТ ЖЕ URL, но Then ПОЗИТИВНЫЙ. Узел падает
    # ровно тогда, когда предпосылка перестаёт держаться (красная проба критика
    # 2026-08-14: подмена When на host-initiated `open_listing` роняет узел с
    # «URL активной вкладки не стал ...work_search%5Bquery%5D=applied-filter-test»).
    # До раунда 4 факт жил только прозой в докстринге и не имел ни одного падающего
    # носителя — текущий When валиден, но теперь ещё и охраняем.
    # `_proving_reload` дополнительно доказывает, что сама навигация РЕАЛЬНО
    # переисполнилась (staleness старого DOM-узла), а не что WORK_BLURB>0
    # удовлетворился прежним, не заменённым документом.
    browser_steps.navigate_listing_via_page_js_proving_reload(driver, rb.LISTING_FILTERED_URL)

    # Then URL активной вкладки ПОСЛЕ перезагрузки остаётся ПОБАЙТОВО тем же
    # LISTING_FILTERED_URL ВЕСЬ бюджет — параметр queryString профиля НЕ дописан
    # второй раз (guard !url.contains("work_search") не даёт перехвату сработать
    # дважды); держим негатив весь бюджет через assert_holds_for, не одним снимком
    # — `view.post {}` (`BrowserScreen.kt:626`) откладывает повторный `loadUrl` на
    # следующий цикл message loop, одноразовое чтение сразу после навигации могло
    # бы не застать отложенный повторный вызов, если бы guard был снят регрессией.
    browser_steps.assert_active_tab_url_holds(driver, rb.LISTING_FILTERED_URL)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-183-premise-same-url-renderer-nav-reaches-interceptor")
@allure.title(
    "Предпосылка TC-182/TC-183: same-URL renderer-initiated навигация ДОХОДИТ до "
    "shouldOverrideUrlLoading (позитивный контроль охвата, регрессионный замок)"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_same_url_renderer_navigation_reaches_interceptor(replay, filter_profile_applied_seeded, driver):
    """Инфраструктурный замок ОХВАТА (critic-раунд 4, блокер B1), не тест-кейс.

    ЧТО СТЕРЕЖЁТ: факт «same-URL renderer-initiated навигация
    (`window.location.href = <тот же URL>`) доходит до `shouldOverrideUrlLoading`».
    Факт нетривиален: host-initiated навигация до перехватчика НЕ доходит
    (официальный докстринг Android + красная проба TC-182), а `driver.get()` на уже
    открытый URL в этом репозитории вообще no-op (прецедент TC-020) — то есть
    «same-URL» здесь исторически особый случай. На этом факте стоит вся
    не-вакуумность TC-183; без падающего носителя его смерть превратила бы TC-183 в
    вечно-зелёный без детектора.

    ПАРНЫЙ НЕГАТИВ В ТОМ ЖЕ УЗЛЕ: промежуточный host-initiated `open_listing` на
    `LISTING_BASIC_URL` при ON и активном профиле обязан оставить URL БАЗОВЫМ —
    вторая половина дискриминатора host/renderer, на котором стоят TC-182/183/184.
    Профиль при этом НЕ снимается: снятие обусловлено `!autoApplyFilter`
    (`BrowserViewModel.kt:501-504`), а тумблер ON — `assert_active_filter_shown`
    фиксирует и это, делая Given самопроверяемым, а не предполагаемым."""
    name = filter_profile_applied_seeded

    # Given тумблер ON (дефолт), профиль активен, вкладка ВОЗВРАЩЕНА на
    # LISTING_BASIC_URL host-initiated навигацией
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_auto_apply_filter_enabled(driver, True)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)

    # парный НЕГАТИВ: host-initiated навигация до перехватчика НЕ доходит —
    # URL обязан остаться БАЗОВЫМ, активный профиль обязан сохраниться (ON)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_BASIC_URL)
    browser_steps.assert_active_filter_shown(driver, name)

    # When same-URL renderer-initiated навигация на ТОТ ЖЕ URL
    browser_steps.navigate_listing_via_page_js(driver, rb.LISTING_BASIC_URL)

    # Then перехватчик сработал: guard `!url.contains("work_search")` пропустил,
    # `getActiveFilterQueryString()` вернул qs, `view.post { loadUrl }` дописал его
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("AT-BUG-070-g2-contrast-door-non-zero-tab")
@allure.title(
    "Контраст-дверь Г2 (CH-010/BUG-070): content-initiated навигация на "
    "deep-link-вкладке (позиция != 0, НЕ sticky tab-0) ДОХОДИТ до "
    "shouldOverrideUrlLoading и дописывает queryString активного профиля"
)
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor(
    replay, filter_profile_applied_seeded, driver
):
    """Инфраструктурный регрессионный замок (test-maintainer, B4, AT-BUG-070
    закрытие test_debt + CH-010 mission_leftover #1 "контраст-дверь Г2"), не
    формальный тест-кейс (заведение TC — за test-designer, если решит
    поднять до продуктового покрытия R-09; `@allure.id` — описательный слаг,
    тот же паттерн, что `test_same_url_renderer_navigation_reaches_interceptor`
    выше и `AT-BUG-047-*`).

    ЧТО ПРОВЕРЯЕТ: `bugs/BUG-070.md` документирует, что ПРОГРАММНАЯ дверь
    (deep-link, `openOrNavigateDeepLink` -> `loadUrl`) НЕ проходит
    `shouldOverrideUrlLoading` — новая вкладка (позиция 1) остаётся
    нефильтрованной, хотя `activeFilterId` глобально жив (`TC-206`). CH-010
    (seed 2) попыталась проверить КОНТРАСТ — что дверь, инициированная
    СОДЕРЖИМЫМ страницы (клик по ссылке / `window.location.href`, тот же
    код-путь), НАПРОТИВ дописывает фильтр — но не смогла прочитать/направить
    действие именно на tab-1 из-за sticky WebView context (execute_script
    внутри `contexts.in_webview` бьёт по вкладке-0), поэтому находка осталась
    "remains open" (`bugs/BUG-070.md` Обсуждение) и заведена как test_debt
    (`bugs/AT-BUG-070.md`).

    Этот узел закрывает именно эту находку эмпирически, используя
    АДРЕСОВАННЫЙ механизм AT-BUG-070 (`browser_steps.webview_handle_for_url`/
    `navigate_tab_via_page_js_to`/`assert_webview_handle_url` —
    `driver.window_handles` внутри WEBVIEW-контекста, НЕ `driver.contexts`,
    см. `framework/core/contexts.py::in_webview_matching` за полной
    эмпирикой) — навигация РЕАЛЬНО выполняется и читается именно на tab-1,
    не на tab-0 по случайности sticky-прилипания.

    AT-BUG-070 rework (критик round1, блокер B1): `assert_webview_handle_url`
    ПО ХЕНДЛУ сам по себе не различает гипотезу «адресация по handle реально
    ушла на tab-1» от «handle молча деградировал до sticky tab-0» — под ЭТОЙ
    деградацией WebView-оракул тоже читал бы `LISTING_FILTERED_URL` (это URL
    tab-0 после Given), и узел вырождался бы в уже зелёного соседа
    `test_same_url_renderer_navigation_reaches_interceptor`. Добавлен
    НЕ-WebView оракул на ЦЕЛЕВУЮ вкладку (`app_steps.wait_persisted_tab_url_at`
    на позиции 1, persisted-prefs, тот же независимый источник, что уже
    использован для Given/негатива tab-0 ниже) — с поллингом, потому что запись
    в prefs после `shouldOverrideUrlLoading` асинхронна (`apply()`)."""
    name = filter_profile_applied_seeded

    # Given tab-0 несёт применённый профиль (LISTING_FILTERED_URL)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)

    # When реальный deep-link открывает tab-1 на БАЗОВОМ (нефильтрованном) URL —
    # программная дверь BUG-070, оракул вне WebView-контекста (тот же, что TC-206)
    app_steps.open_deep_link(rb.LISTING_BASIC_URL)
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.assert_persisted_tab_url_at(1, rb.LISTING_BASIC_URL)

    # Захватываем стабильный handle tab-1 ПО ЕЁ ИЗВЕСТНОМУ URL (не по
    # заголовку — обе фикстурные страницы, отфильтрованная и нет, несут
    # ОДИНАКОВЫЙ document.title "Test Fixture Listing | Archive of Our Own",
    # title-матчинг здесь неоднозначен, эмпирически обнаружено при разведке
    # этого узла — `webview_handle_for_url` существует ИМЕННО для этого случая)
    tab1_handle = browser_steps.webview_handle_for_url(driver, rb.LISTING_BASIC_URL, timeout=10)

    # When контраст: content-initiated (renderer) навигация на ТОТ ЖЕ URL,
    # адресованная ИМЕННО на tab-1 через захваченный handle (не sticky-контекст)
    browser_steps.navigate_tab_via_page_js_to(driver, tab1_handle, rb.LISTING_BASIC_URL, timeout=10)

    # Then URL tab-1 (тот же handle) становится LISTING_FILTERED_URL — контраст
    # подтверждён: content-initiated дверь ДОХОДИТ до перехватчика, в отличие
    # от deep-link (BUG-070), даже на НЕ-нулевой/НЕ-активной по chromedriver-
    # прилипанию вкладке
    browser_steps.assert_webview_handle_url(driver, tab1_handle, rb.LISTING_FILTERED_URL, timeout=10)

    # And НЕ-WebView оракул на ТУ ЖЕ цель (AT-BUG-070 rework B1): URL persisted
    # tab-1 (независимый от handle-адресации источник) тоже стал
    # LISTING_FILTERED_URL — различает "адресация по handle реально ушла на
    # tab-1" от "handle молча деградировал до sticky tab-0" (под этой
    # деградацией WebView-оракул выше был бы зелёным тривиально, т.к. tab-0 уже
    # LISTING_FILTERED_URL с Given). Поллинг: запись в prefs после
    # shouldOverrideUrlLoading асинхронна (apply()).
    app_steps.wait_persisted_tab_url_at(1, rb.LISTING_FILTERED_URL, timeout=10)

    # And tab-0 остаётся на своём уже отфильтрованном URL — без кросс-вкладочной утечки
    app_steps.assert_persisted_tab_url_at(0, rb.LISTING_FILTERED_URL)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-184")
@allure.title("OFF: обычная навигация не дописывает фильтр И снимает активный профиль (регрессионный замок фактического поведения)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_apply_filter_off_drops_active_profile_on_plain_navigation(replay, filter_profile_applied_seeded, driver):
    """ЭТО ФАКТИЧЕСКОЕ поведение текущей сборки, зафиксированное как регрессионный
    замок — НЕ вердикт «так и задумано»: задуманность ветки «OFF снимает активный
    профиль при первой же обычной навигации» НЕ подтверждена (вопрос вынесен
    владельцу/разработчику, §10 (ч) docs/01-test-strategy.md, см. TC-184.md). Given
    «профиль активен ДО переключения OFF» достигается через одноразовое ручное
    применение из FilterPanel ПРИ ON (тот же приём, что TC-182/TC-041) — см. докстринг
    модуля за разбором Given+When (rework attempt 2, критик-вход B1)."""
    name = filter_profile_applied_seeded

    # Given профиль «My saved search» активен (устанавливается ДО переключения
    # тумблера — приём TC-182), тумблер Auto-apply переключается в OFF
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)
    browser_steps.select_filter_option(driver, name)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)
    browser_steps.assert_active_filter_shown(driver, name)

    app_steps.open_tab(driver, "Settings")
    settings_steps.set_auto_apply_filter_toggle(driver, False)
    settings_steps.assert_auto_apply_filter_enabled(driver, False)

    # When пользователь переходит (обычная навигация, НЕ через кнопку применения
    # фильтра) на филируемую страницу листинга — повторный переход на базовый URL.
    # Renderer-initiated навигация (`window.location.href`, не `driver.get()`/
    # `open_listing`) — rework attempt 2 (критик-вход B1): предыдущая редакция
    # использовала `open_listing` (host-initiated `driver.get()`), который по
    # красной пробе TC-182 attempt 1 НЕ доходит до `shouldOverrideUrlLoading`
    # вовсе — негативный Then «queryString не дописан» был бы истинен ДАЖЕ если
    # удалить сам OFF-guard целиком (навигация физически не проходит через код,
    # который guard охраняет), падая только на удалении самого перехватчика, а не
    # на поломке его логики. `navigate_listing_via_page_js` реально достигает
    # перехватчика: при OFF `getActiveFilterQueryString()` вернёт `null`
    # (`!autoApplyFilter`), перехват вернёт `false`, штатная загрузка BASIC
    # пройдёт, `onPageLoaded` снимет активный профиль — оба Then теперь
    # ДОСТИЖИМО ложны при поломке OFF-guard.
    app_steps.open_tab(driver, "Browse")
    browser_steps.navigate_listing_via_page_js(driver, rb.LISTING_BASIC_URL)

    # Then URL активной вкладки — LISTING_BASIC_URL, параметр queryString профиля
    # НЕ дописан (явный негативный Then)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_BASIC_URL)
    # And активный профиль СНИМАЕТСЯ — панель фильтра листинга после этой навигации
    # показывает «None»
    browser_steps.assert_active_filter_shown(driver, "None")


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-185")
@allure.title("OFF: навигация, вызванная самой кнопкой применения фильтра, не снимает только что применённый профиль")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_auto_apply_filter_off_button_navigation_keeps_active_profile(replay, filter_profile_applied_seeded, driver):
    name = filter_profile_applied_seeded

    # Given тумблер Auto-apply — OFF, активного профиля нет, вкладка на
    # LISTING_BASIC_URL, FilterPanel раскрыта
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.set_auto_apply_filter_toggle(driver, False)
    settings_steps.assert_auto_apply_filter_enabled(driver, False)

    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)
    browser_steps.open_filter_dropdown(driver)

    # When пользователь ВЫБИРАЕТ профиль «My saved search» из FilterPanel (это и
    # есть кнопка применения — applyFilter взводит pendingFilterApplication при
    # OFF ПЕРЕД навигацией)
    browser_steps.select_filter_option(driver, name)

    # Then URL активной вкладки становится LISTING_FILTERED_URL (фильтр
    # ПРИМЕНИЛСЯ — прямое ручное действие пользователя, тумблер OFF ему не мешает)
    browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)
    # And ПОСЛЕ этой навигации активный профиль ОСТАЁТСЯ «My saved search» ВЕСЬ
    # бюджет — pendingFilterApplication потребляется onPageLoaded БЕЗ
    # setActiveFilter(null), в отличие от TC-184, где та же по форме навигация
    # СНИМАЕТ активный профиль. rework attempt 2 (критик-вход B3): `setActiveFilter`
    # ставится ДО навигации (см. `applyFilter`), а возможное снятие произошло бы
    # ПОЗЖЕ, внутри `onPageLoaded` (после коммита URL) — одноразовый снимок
    # (`assert_active_filter_shown`) читает состояние ДО момента, когда мог бы
    # проявиться гипотетический дефект; держим негатив «профиль не снят отложенно»
    # весь бюджет через assert_holds_for.
    browser_steps.assert_active_filter_shown_holds(driver, name)
