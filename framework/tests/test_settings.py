"""Тесты экрана Settings (app-under-test ui/settings/SettingsScreen.kt): переключение
темы Light/Dark/System и его мгновенное применение к нативному Compose UI и к WebView
(fragile-область, см. app-under-test/CLAUDE.md «Dark mode has broken four times»).

Дизайн следует test_side_panel.py: тема приводится к известному состоянию (Light)
через Settings перед каждым сценарием, зависимость от живого AO3 неизбежна (WebView
должен реально догрузить страницу, чтобы проверять её визуальный результат).
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import seed_db
from framework.data.works import Work
from framework.steps import (
    app_steps,
    browser_steps,
    library_steps,
    rating_steps,
    settings_steps,
    side_panel_steps,
)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-047")
@allure.title("Переключение Dark в Settings применяется мгновенно, Activity не пересоздаётся")
def test_theme_dark_applies_instantly_without_recreating_activity(clean_app, driver):
    # Given приложение в светлой теме, на вкладке Browse отображается загруженная страница
    # AO3 с достаточным для скролла И СТАБИЛЬНЫМ контентом. Browse root
    # (`archiveofourown.org` без пути) НЕ годится — измерением (AT-BUG-015, 2026-07-18)
    # подтверждено: document.body.scrollHeight=427 < window.innerHeight=798 на
    # использованном эмуляторе, `scrollTo` там легитимно клампится к 0. Живой листинг
    # `/works` тоже не годится: он достаточно высок, но time-sensitive (сортировка по
    # revised_at) — переключение темы триггерит реальный `reload()` WebView (см. TC-048),
    # а контент листинга успевает измениться между двумя загрузками, из-за чего пиксельный
    # scrollY после reload честно уезжает (899 -> 930 на диагностике, не баг приложения —
    # волатильность выбранной страницы). `browser_steps.open_stable_tall_page` открывает
    # статическую страницу (`/tos`) — тоже проходит через reload(), но контент не
    # time-sensitive, scrollY совпадает с точностью <1px (см. docstring за деталями).
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")
    app_steps.wait_app_ready(driver)
    url_before = browser_steps.open_stable_tall_page(driver)
    # Устройство-независимая величина прокрутки (закрытие класса, начатого в
    # TC-111 — критик-раунд 2026-08-25, «геометрическая хрупкость оракула»):
    # было `scroll_webview_to(driver, 900)`, абсолютный пиксель снятой на
    # геометрии одного AVD. Множитель подобран ПОД МИССИЮ ИМЕННО этого теста,
    # не скопирован из TC-111 механически: TC-111 после поворота допускает
    # ПОТЕРЮ до 50% позиции (`scroll_landscape > scroll_before * 0.5`) —
    # поворот реально переверстывает страницу (другая ширина/side panel), и
    # запас 2×innerHeight там нужен, чтобы позиция осталась заметно
    # ненулевой даже после реальной потери точности. Здесь инвариант —
    # ПРОТИВОПОЛОЖНЫЙ: смена темы Light->Dark — чисто цветовая перекраска
    # Compose-слоя, WebView-viewport/лейаут не меняется (сам тест это и
    # проверяет: `assert abs(scroll_after - scroll_before) <= 2` ниже —
    # почти точное совпадение, не 50%-допуск), значит запас TC-111 здесь не
    # нужен и вреден: чем ближе целевая точка к границе `scrollHeight -
    # innerHeight`, тем выше риск попасть под клампинг скролла на
    # устройстве с большим viewport, а неточность клампинга — ложный источник
    # шума именно для тесной 2px-проверки. Взят множитель 1 (один экран
    # вниз) — заведомо ненулевая, пропорциональная любому viewport величина
    # с максимальным запасом до границы клампинга (страница `/tos`
    # гарантированно выше 2000px scrollHeight — `open_stable_tall_page`,
    # реальный текст ToS на порядок длиннее одного viewport).
    inner_height = browser_steps.get_webview_inner_height(driver)
    browser_steps.scroll_webview_to(driver, int(inner_height * 1))
    scroll_before = browser_steps.get_webview_scroll_y(driver)

    # When пользователь в Settings выбирает тему "Dark"
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "DARK")
    app_steps.open_tab(driver, "Browse")

    # Then нативные Compose-экраны немедленно перекрашиваются в тёмную схему (side panel
    # мгновенно отражает новую тему — без перезапуска приложения, тот же прокси, что TC-050)
    side_panel_steps.expand(driver)
    side_panel_steps.assert_theme_is_dark(driver)
    side_panel_steps.collapse(driver)

    # And после возврата на экран Browse открытая вкладка/URL и позиция прокрутки остаются
    # теми же, что были до переключения — наблюдаемый прокси отсутствия recreation Activity
    # (см. заметки TC-047: прямая проверка PID/instance не UI-наблюдаема и не подходит для
    # black-box теста)
    url_after = app_steps.wait_app_ready(driver)
    assert url_after == url_before, (
        f"URL вкладки Browse изменился после переключения темы (похоже на recreation): "
        f"{url_before} -> {url_after}"
    )
    scroll_after = browser_steps.get_webview_scroll_y(driver)
    # Допуск 2px — сама позиция не должна меняться (WebView не перезагружается, Activity не
    # пересоздаётся), но int(scrollY) в get_webview_scroll_y усекает дробную часть CSS px;
    # округление в разные стороны на двух замерах теоретически может дать разницу в 1px.
    assert abs(scroll_after - scroll_before) <= 2, (
        f"Позиция прокрутки страницы Browse изменилась после переключения темы (похоже на "
        f"recreation/reload вместо мгновенной смены темы): {scroll_before} -> {scroll_after}"
    )


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-048")
@allure.title("WebView dark mode применяется мгновенно вместе с остальным UI (без холодного рестарта)")
def test_webview_dark_mode_applies_instantly(clean_app, driver):
    # Given приложение в светлой теме, страница AO3 в WebView отображается светлой
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")
    app_steps.wait_app_ready(driver)
    baseline_luma = browser_steps.measure_webview_luma(driver)

    # When пользователь переключает тему на Dark в Settings и возвращается на экран
    # Browse без перезапуска приложения
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "DARK")
    app_steps.open_tab(driver, "Browse")

    # Then содержимое WebView немедленно переходит в тёмную цветовую схему — наблюдаемый
    # визуальный результат (алгоритмическое затемнение), не internal API; опрос даёт время
    # на программный reload()+перерисовку (см. заметки TC-048 по таймингу)
    browser_steps.assert_webview_darkened(driver, baseline_luma)
    dark_luma = browser_steps.measure_webview_luma(driver)

    # When пользователь переключает тему обратно на Light в Settings (C4-ретрофит
    # 2026-07-18: инвариант кейса заявлен СИММЕТРИЧНЫМ — до этого блока проверялось
    # только Light→Dark, требование CLAUDE.md app-under-test п.2 чек-листа Dark mode
    # "Toggle light → pages go light immediately" оставалось недоказанным)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    app_steps.open_tab(driver, "Browse")

    # Then содержимое WebView немедленно возвращается в светлую цветовую схему —
    # тот же наблюдаемый визуальный результат, симметрично Then выше
    browser_steps.assert_webview_lightened(driver, dark_luma)


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-049")
@allure.title("Тема System переключается вместе с системной темой ОС")
def test_system_theme_follows_os_dark_mode(clean_app, driver):
    try:
        # Given в приложении выбрана тема "System", системная тема ОС — Light, нативные
        # экраны приложения отображаются светлыми
        app_steps.wait_ui_ready(driver)
        app_steps.set_system_dark_mode(False)
        app_steps.open_tab(driver, "Settings")
        settings_steps.select_theme(driver, "SYSTEM")
        app_steps.open_tab(driver, "Browse")
        side_panel_steps.expand(driver)
        side_panel_steps.assert_theme_is_light(driver)

        # When системная тема ОС переключается на Dark (без действий пользователя внутри
        # приложения)
        app_steps.set_system_dark_mode(True)

        # Then нативные Compose-экраны приложения отображаются в тёмной схеме без
        # дополнительных действий пользователя внутри приложения (следование за System,
        # configChanges="uiMode" не пересоздаёт Activity)
        side_panel_steps.assert_theme_is_dark(driver)

        # When системная тема ОС переключается обратно на Light (C4-ретрофит
        # 2026-07-18: инвариант кейса заявлен СИММЕТРИЧНЫМ "в обоих направлениях",
        # прежде обратный переход выполнялся только в finally как уборка общего
        # ресурса — БЕЗ assert'а, что приложение реально следует за ним обратно)
        app_steps.set_system_dark_mode(False)

        # Then нативные Compose-экраны приложения возвращаются в светлую схему —
        # тот же прокси (side panel), симметрично Then выше
        side_panel_steps.assert_theme_is_light(driver)
    finally:
        # Системная тема ОС — общий ресурс эмулятора, переживающий тест; возвращаем её
        # к Light, чтобы не протекало в другие тесты (не полагающиеся на System-тему).
        app_steps.set_system_dark_mode(False)


@pytest.mark.p2
@allure.id("TC-018")
@allure.title("Clear all ratings показывает диалог подтверждения перед очисткой")
def test_clear_all_ratings_shows_confirmation_dialog(seeded_library, driver):
    # Given приложение с засеянными работами по всем рейтингам, открыт экран Settings
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")

    # When пользователь нажимает кнопку «Clear…» (секция Data)
    settings_steps.open_clear_all_dialog(driver)

    # Then появляется диалог подтверждения (AlertDialog) с текстом про очистку всех рейтингов
    settings_steps.assert_clear_all_dialog_visible(driver)
    settings_steps.assert_clear_all_dialog_body(driver)

    # And данные в БД остаются нетронуты, пока диалог не подтверждён (проверка напрямую
    # через adb, независимо от того, что модальный диалог блокирует навигацию по UI —
    # тот же деградационный приём, что `settings_steps.assert_no_ratings`, TC-004)
    settings_steps.assert_ratings_present()


@pytest.mark.p2
@allure.id("TC-019")
@allure.title("Отмена диалога Clear all ratings не удаляет данные")
def test_cancel_clear_all_dialog_keeps_data(seeded_library, driver):
    # Given приложение с засеянными работами по всем рейтингам, на экране Settings
    # открыт диалог подтверждения «Clear all ratings» (кнопка «Clear…» нажата)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.open_clear_all_dialog(driver)
    settings_steps.assert_clear_all_dialog_visible(driver)

    # When пользователь нажимает «Cancel», не подтверждая
    settings_steps.cancel_clear_all_dialog(driver)

    # Then диалог закрывается без удаления
    settings_steps.assert_clear_all_dialog_closed(driver)

    # And экран Library по всем рейтинговым вкладкам по-прежнему содержит засеянные
    # работы (данные в БД не изменены)
    app_steps.open_tab(driver, "Library")
    for rating, work in (
        ("SAVE", seeded_library.LOVED),
        ("LIKE", seeded_library.KUDOSED),
        ("READ", seeded_library.READ),
        ("PENDING", seeded_library.PENDING),
        ("DISLIKE", seeded_library.DISLIKED),
    ):
        library_steps.assert_work_in_tab(driver, rating, work.title)


@pytest.mark.p3
@pytest.mark.replay
@allure.id("TC-020")
@allure.title(
    "Бейджи открытых вкладок сохраняют состояние до перезагрузки страницы; "
    "после reload — сброшены"
)
@pytest.mark.parametrize("replay", [rb.WORKS_MULTI_FILENAME], indirect=True)
def test_clear_all_ratings_badge_persists_without_reload(loved_work_seeded, replay, driver):
    """Автоматизирует ТОЛЬКО Then (а) кейса (см. TC-020.md) — наблюдаемый факт:
    badge остаётся выбранным сразу после Clear all ratings, без перезагрузки
    страницы (причина не утверждается здесь — R2, критик D5 2026-08-02; см.
    `bugs/BUG-012.md`/`bugs/AT-BUG-042.md` за анализом возможных причин). Это
    подтверждённое, стабильно зелёное Intended-поведение (BUG-012, решение
    владельца 2026-08-02).

    Переведён с `@pytest.mark.live` на `@pytest.mark.replay` (координатор,
    2026-08-03, устранение ESC-015/R-03): сценарий не проверяет НИЧЕГО из
    реального содержимого страницы AO3 — бейдж/панель управляются Room, не
    DOM; `works_multi.mitm` уже несёт work-страницу `W.LOVED`
    (`ALL_WORKS[0]`, `recording_builder.render_work_page_html`, тот же URL,
    что `work.url`/`BrowserScreen.open_work`), `server_replay_reuse=true`
    отдаёт ОДИН И ТОТ ЖЕ ответ на повторные запросы — то же самое нужно для
    Then (б) (см. соседнюю функцию) при `reload()`.

    Then (б) («после перезагрузки бейдж отражает очищенное состояние») —
    отдельная функция ниже (`test_clear_all_ratings_badge_resets_after_reload`;
    там reload делается ДО возврата на Browse — это ОБХОД дефекта приложения
    `BUG-022`, а не порядок из пользовательского сценария, см. её докстринг)."""
    # Given работа W засеяна с рейтингом Loved (SAVE), её страница /works/{id} открыта
    # на вкладке Browse — встроенная панель RatingMenu отражает выбранный рейтинг
    # «Favorite» (Loved), Settings ещё не открыт (мультитаб: WebView-вкладка остаётся
    # открытой при навигации между Browse и Settings). wait_ui_ready (не
    # wait_app_ready) — домашняя страница HOME_URL НЕ записана в
    # works_multi.mitm, ждать её загрузки означало бы уйти в live (тот же
    # приём, что test_rating_listing.py::test_rate_work_from_listing_overlay).
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    # R1 (критик D5): якорь Given — baseline обязан соответствовать ВЫБРАННОМУ
    # состоянию, иначе тест был бы ложно-зелёным на сломанном Given. Шаг
    # ОПРАШИВАЕТ (onPageLoaded читает Room асинхронно) и возвращает осевшее
    # значение — baseline берём именно его, не ранний снимок.
    baseline_luma = rating_steps.capture_panel_rating_baseline(driver, "SAVE")
    selected_luma = settings_steps.assert_baseline_indicates_selected(driver, "SAVE", baseline_luma)

    # When пользователь переходит в Settings и подтверждает диалог «Clear all ratings»
    app_steps.open_tab(driver, "Settings")
    settings_steps.clear_all_ratings(driver)

    # Then (а) — наблюдаемый факт (BUG-012, Intended, 2026-08-02): при возврате
    # на вкладку с открытой страницей работы W, БЕЗ перезагрузки, бейдж «Loved»
    # ОСТАЁТСЯ визуально выбранным (весь бюджет assert_holds_for, не
    # одноразовый снимок — B6, критик D5). Причина НЕ утверждается здесь (R2):
    # владелец продукта принял это как задуманное поведение независимо от
    # того, каким именно внутренним механизмом оно объясняется.
    app_steps.open_tab(driver, "Browse")
    settings_steps.assert_panel_rating_still_selected(driver, "SAVE", selected_luma)


@pytest.mark.p3
@pytest.mark.replay
@allure.id("TC-020")
@allure.title(
    "После перезагрузки страницы работы бейдж отражает очищенный рейтинг (Then б)"
)
@pytest.mark.parametrize("replay", [rb.WORKS_MULTI_FILENAME], indirect=True)
def test_clear_all_ratings_badge_resets_after_reload(loved_work_seeded, replay, driver):
    """Порядок шагов ЗДЕСЬ — reload ДО возврата на Browse — это ОБХОД
    ПОДТВЕРЖДЁННОГО ДЕФЕКТА ПРИЛОЖЕНИЯ `BUG-022`, а не оптимизация и не
    пользовательская последовательность из кейса.

    ЧЕСТНО О ГРАНИЦЕ ПРОВЕРЯЕМОГО (критик D5, финальный раунд 2026-08-03):
    пользователь в жизни делает «возврат на Browse -> reload». В ЭТОМ порядке
    на текущей сборке ожидание кейса НЕ выполняется — `BUG-022`
    (`WorkRatingPanel` dispose-save воскрешает удалённую запись ещё на самом
    возврате, ДО того как reload успевает что-либо перечитать). Данный тест
    НЕ проверяет пользовательский порядок и не должен трактоваться как его
    замок: он проверяет ровно то, что в этой сборке проверяемо, — что
    перезагрузка страницы работы ПЕРЕЧИТЫВАЕТ рейтинг из Room и панель
    отражает очищенное состояние. Регрессионный замок пользовательского
    порядка появится при фиксе `BUG-022` и будет носителем ТОГО бага, не
    этого кейса (решение Lead, развязка TC-020 <-> BUG-022; см.
    `test-cases/settings/TC-020.md`, блок «Границы проверяемого»).

    Механизм обхода (`AT-BUG-042` R8, подтверждён различающим замером
    `ao3Id|rating|timestamp`, НЕ COUNT): воскресшая строка появляется ИМЕННО в
    момент возврата на вкладку Browse, с `rating=SAVE` (никогда `READ` —
    `onWorkFinished` auto-mark НЕ участвует в этом сценарии: `works_multi.mitm`
    с AT-BUG-074 ТЕПЕРЬ несёт `<div id="chapters">` тоже, но auto-mark
    срабатывает ТОЛЬКО на реальном браузерном `scroll`-событии, а этот тест ни
    разу не скроллит WebView — reload/навигация сами по себе `scroll` не
    порождают). Источник — транзитный mount+dispose
    `WorkRatingPanel` во время exit-анимации `AnimatedVisibility` на возврате
    (`onSelect` ставит `navExpanded=false` одновременно с `selectedTab=BROWSE`,
    `MainActivity.kt:426-429`/`BottomBar.kt:99-105`): dispose захватывает
    СТУХШЕЕ `latestRating=SAVE`, если `currentPageRating` к этому моменту ещё
    не обнулён (`BUG-012` Intended — обнуляется только `onPageLoaded`).

    Почему обход работает: `BrowserScreen` (и его WebView) композится
    БЕЗУСЛОВНО независимо от `selectedTab` (`MainActivity.kt:471-472`,
    "Browser is always rendered to keep WebViews alive"), поэтому
    `window.location.reload()` срабатывает и с экрана Settings, ДО возврата на
    Browse. `onPageLoaded` обнуляет `currentPageRating`
    (`BrowserViewModel.kt:463-509`) — когда мы ПОТОМ возвращаемся на Browse,
    транзитный dispose захватывает `latestRating=null`, и `onSave` не
    вызывается вовсе (guard `latestRating != null`, `BottomBar.kt:159-167`) —
    воскрешения не происходит. Подтверждено различающим замером: строка
    остаётся ПУСТОЙ на каждом чекпоинте после reload (в т.ч. сразу после
    возврата на Browse).

    Переведён с `@pytest.mark.live` на `@pytest.mark.replay` (координатор,
    2026-08-03, устранение ESC-015/R-03) — см. докстринг соседней функции за
    обоснованием."""
    # Given работа W засеяна с рейтингом Loved (SAVE), её страница /works/{id}
    # открыта на вкладке Browse — панель RatingMenu отражает выбранный рейтинг
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    # R1 (критик D5): якорь Given — baseline обязан соответствовать ВЫБРАННОМУ
    # состоянию, иначе тест был бы ложно-зелёным на сломанном Given. Шаг
    # ОПРАШИВАЕТ (onPageLoaded читает Room асинхронно) и возвращает осевшее
    # значение — baseline берём именно его, не ранний снимок.
    baseline_luma = rating_steps.capture_panel_rating_baseline(driver, "SAVE")
    selected_luma = settings_steps.assert_baseline_indicates_selected(driver, "SAVE", baseline_luma)

    # When пользователь переходит в Settings и подтверждает диалог «Clear all ratings»
    app_steps.open_tab(driver, "Settings")
    settings_steps.clear_all_ratings(driver)

    # And якорь состояния БД: очистка ДЕЙСТВИТЕЛЬНО опустошила work_ratings к
    # моменту перезагрузки — иначе провал Then (б) не различал бы «панель не
    # перечитала Room» и «в Room по-прежнему лежит рейтинг» (BUG-022-класс);
    # сырые строки ao3Id|rating|timestamp, не COUNT — только значение rating
    # различает конкурирующих писателей.
    settings_steps.assert_rating_rows_empty()

    # When пользователь перезагружает страницу работы — ЗДЕСЬ, ПОКА мы ещё на
    # Settings: ОБХОД дефекта приложения BUG-022 (в пользовательском порядке
    # «возврат на Browse -> reload» ожидание кейса на текущей сборке НЕ
    # выполняется), см. докстринг. Реальный WebView reload
    # (window.location.reload()), НЕ повторная навигация на тот же URL:
    # красный прогон 2026-08-02 показал, что Chromium не триггерит
    # onPageFinished на навигации к уже открытому URL, см. docstring
    # `settings_steps.reload_active_webview_page`.
    settings_steps.reload_active_webview_page(driver)

    # Then (б) при возврате на Browse панель RatingMenu отражает очищенное
    # состояние (бейдж «Loved» исчез) — onPageLoaded перечитал
    # currentPageRating из Room ДО того, как транзитный dispose на возврате
    # мог бы захватить стухшее значение (обход R8 выше), тот же luma-прокси,
    # что TC-009/TC-010
    app_steps.open_tab(driver, "Browse")
    rating_steps.assert_panel_rating_deselected(driver, "SAVE", selected_luma)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-059")
@allure.title("System-тема: WebView следует за системной сменой uiMode без in-app toggle")
def test_webview_follows_system_theme_without_in_app_toggle(clean_app, driver):
    try:
        # Given тема приложения = System, системная тема ОС = Light, на Browse открыта
        # загруженная страница AO3 (WebView содержимое видно светлым)
        app_steps.wait_ui_ready(driver)
        app_steps.set_system_dark_mode(False)
        app_steps.open_tab(driver, "Settings")
        settings_steps.select_theme(driver, "SYSTEM")
        app_steps.open_tab(driver, "Browse")
        app_steps.wait_app_ready(driver)
        url_before = browser_steps.open_stable_tall_page(driver)
        baseline_luma = browser_steps.measure_webview_luma(driver)

        # When системная тема ОС переключается на Dark, БЕЗ какого-либо действия
        # внутри приложения (без захода в Settings, без in-app toggle)
        app_steps.set_system_dark_mode(True)

        # Then содержимое WebView переходит в тёмную цветовую схему вслед за системной
        # сменой — LaunchedEffect(darkTheme) в BrowserScreen.kt срабатывает независимо
        # от источника darkTheme (isSystemInDarkTheme() при themeMode=SYSTEM тоже его
        # меняет, см. MainActivity.kt), тот же прокси, что TC-048
        browser_steps.assert_webview_darkened(driver, baseline_luma)
        dark_luma = browser_steps.measure_webview_luma(driver)

        # And активная вкладка Browse и её URL не меняются при переключении (смена
        # темы не пересоздаёт WebView и не роняет навигацию)
        assert app_steps.wait_app_ready(driver).rstrip("/") == url_before.rstrip("/"), (
            "URL активной вкладки Browse изменился после системной смены темы на Dark"
        )

        # When системная тема ОС переключается обратно на Light — эффект воспроизводится
        # в обе стороны
        app_steps.set_system_dark_mode(False)

        # Then содержимое WebView возвращается в светлую цветовую схему
        browser_steps.assert_webview_lightened(driver, dark_luma)

        # And URL/активная вкладка по-прежнему не изменились
        assert app_steps.wait_app_ready(driver).rstrip("/") == url_before.rstrip("/"), (
            "URL активной вкладки Browse изменился после системной смены темы обратно на Light"
        )
    finally:
        # Системная тема ОС — общий ресурс эмулятора, переживающий тест; возвращаем её
        # к Light в finally, как TC-049.
        app_steps.set_system_dark_mode(False)


# --- Fetch missing metadata (секция "Data", SettingsScreen.kt:231-264/999-1053,
# TC-186/TC-187, AT-BUG-061 Verified) ---
#
# AT-BUG-061 УЖЕ Verified: replay-запись `work_metadata_fetch.mitm`
# (`rb.WORK_METADATA_FETCH_FILENAME`) существует и эмпирически подтверждена
# рабочей device-пробой test-maintainer (`bugs/AT-BUG-061.md` §Обсуждение,
# 2026-08-10) — `HttpURLConnection`-путь `fetchAo3WorkPage` реально
# перехватывается device-wide прокси в replay-режиме, ушёл в этот же файл
# как ОБЫЧНЫЙ replay-flow (`make_html_get_flow` матчит только
# scheme+method+path+query+host+port — заголовки запроса, включая Cookie, на
# матчинг не влияют).
#
# Given-строки сеются с ТЕМИ ЖЕ ao3_id, что несёт запись (`rb.METADATA_FETCH_
# WORK_A`/`rb.METADATA_FETCH_WORK_SECOND`/`rb.METADATA_FETCH_WORK_B_AO3_ID`),
# но с `title=""` — ТЕКУЩЕЕ (до fetch) состояние строки; запись несёт ЦЕЛЕВОЙ
# (скрейпнутый) результат. Сравнение "before/after" — сам проверяемый факт
# обоих кейсов.
_METADATA_WORK_A_EMPTY = Work(rb.METADATA_FETCH_WORK_A.ao3_id, "", "", "Test Fandom", None)
_METADATA_WORK_B_EMPTY = Work(rb.METADATA_FETCH_WORK_B_AO3_ID, "", "", "Test Fandom", None)
# ao3_id вне диапазона, зарезервированного `rb`/`works.py` (сверено: не
# 900000186/187/188, не пересекается ни с одной существующей константой) —
# работа C НЕ должна попасть в очередь `getWorksWithEmptyTitle` (title уже
# заполнен), её неприкосновенность — явный Then TC-186 (анти-ловушка BUG-048).
_METADATA_WORK_C_FILLED = Work(
    "900000189", "TC-186 Already Filled Work", "existing_author_186", "Existing Fandom", 999,
)


@pytest.fixture()
def metadata_fetch_queue_seeded():
    """TC-186 Given: три работы — A/B с пустым `title` (попадают в очередь), C с
    уже заполненным `title` (вне очереди по построению — `WorkRatingDao.
    getWorksWithEmptyTitle`: `WHERE title = ''`, RatingRepository.kt:62)."""
    app_steps.clean_state()
    app_steps.seed_library([
        (_METADATA_WORK_A_EMPTY, "PENDING"),
        (_METADATA_WORK_B_EMPTY, "PENDING"),
        (_METADATA_WORK_C_FILLED, "PENDING"),
    ])
    yield


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-186")
@allure.title(
    "Fetch missing metadata дозаполняет ТОЛЬКО работы с пустым title, показывает "
    "прогресс N/total и пишет в Room лишь непустые результаты скрейпа"
)
@pytest.mark.parametrize("replay", [rb.WORK_METADATA_FETCH_FILENAME], indirect=True)
def test_fetch_missing_metadata_fills_only_empty_titles(metadata_fetch_queue_seeded, replay, driver):
    """Cookie для `fetchAo3WorkPage` (SettingsScreen.kt:1023-1024) берётся из
    `CookieManager.getInstance().getCookie(...)` — в replay-режиме, без
    предварительного логина, скорее всего пуст. Server-replay матчит flow
    ТОЛЬКО по scheme+method+path+query+host+port (`recording_builder.py`
    модульный докстринг «Матчинг server-replay») — заголовки запроса
    (включая Cookie) на матчинг не влияют, отсутствие cookie не мешает
    получить записанный ответ. Подтверждено этим же прогоном: работа A
    получает ПОЛНЫЙ скрейпнутый результат без предварительного логина/cookie."""
    # Given в Room три работы: A (пустой title, скрейп даст успех), B (пустой
    # title, скрейп не даст успеха — HTTP 404 на записанной странице), C
    # (title уже заполнен, вне очереди по построению)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")

    # Then подпись показывает «2 works have no title yet» — очередь = только A и B
    settings_steps.assert_metadata_fetch_queue_count(driver, 2)

    # When пользователь нажимает «Fetch»
    settings_steps.start_metadata_fetch(driver)

    # Then пока идёт процесс, подпись показывает «Fetching 1 / 2…», затем
    # «Fetching 2 / 2…» (наблюдаемый прогресс N/total), кнопка на месте «Fetch»
    # временно становится «Stop»
    settings_steps.assert_metadata_fetch_stop_button_visible(driver)
    settings_steps.assert_metadata_fetch_progress(driver, 1, 2)
    settings_steps.assert_metadata_fetch_progress(driver, 2, 2, timeout=5)

    # Then по завершении (без нажатия Stop) состояние — Done: подпись «Updated
    # 1 works» (обновилась только A — единственная, для которой скрейп дал
    # непустой title)
    settings_steps.assert_metadata_fetch_done(driver, 1)

    # And в Room: title работы A ЗАПОЛНЕН скрейпнутым значением (плюс
    # author/fandom/wordCount), title работы B ОСТАЁТСЯ пустым (запись не
    # перезаписана), работа C НЕ ТРОНУТА (исходные title/author/fandom
    # неизменны байт-в-байт — анти-ловушка BUG-048)
    rows = seed_db.read_work_ratings_full()
    scraped_a = rb.METADATA_FETCH_WORK_A
    row_a = rows[_METADATA_WORK_A_EMPTY.ao3_id]
    assert row_a["title"] == scraped_a.title, row_a
    assert row_a["author"] == scraped_a.author, row_a
    assert row_a["fandom"] == scraped_a.fandom, row_a
    assert row_a["word_count"] == scraped_a.word_count, row_a

    row_b = rows[_METADATA_WORK_B_EMPTY.ao3_id]
    assert row_b["title"] == "", (
        f"title работы B не должен был обновиться (скрейп HTTP 404), реально: {row_b['title']!r}"
    )

    row_c = rows[_METADATA_WORK_C_FILLED.ao3_id]
    assert row_c["title"] == _METADATA_WORK_C_FILLED.title, (
        f"работа C не должна была попасть в очередь/измениться, title реально: {row_c['title']!r}"
    )
    assert row_c["author"] == _METADATA_WORK_C_FILLED.author, row_c
    assert row_c["fandom"] == _METADATA_WORK_C_FILLED.fandom, row_c
    assert row_c["word_count"] == _METADATA_WORK_C_FILLED.word_count, row_c


# --- TC-187: Stop мид-fetch ---

# D переиспользует ao3_id работы A (TC-186) — записанный скрейп идентичен;
# E — ao3_id `rb.METADATA_FETCH_WORK_SECOND` (AT-BUG-061: "работа A
# переиспользуется как D... работа SECOND как E").
_METADATA_WORK_D_EMPTY = Work(rb.METADATA_FETCH_WORK_A.ao3_id, "", "", "Test Fandom", None)
_METADATA_WORK_E_EMPTY = Work(rb.METADATA_FETCH_WORK_SECOND.ao3_id, "", "", "Test Fandom", None)


@pytest.fixture()
def metadata_fetch_stop_queue_seeded():
    """TC-187 Given: ДВЕ работы с пустым title (D, E), обе дают успешный скрейп.

    `WorkRatingDao.getWorksWithEmptyTitle` — `ORDER BY timestamp DESC`
    (:39) — порядок обработки очереди определяется относительным порядком
    timestamp'ов ВСТАВКИ. `app_steps.seed_library_ordered` (`seed_db.
    seed_ordered`) даёт КАЖДОЙ строке списка СТРОГО возрастающий timestamp по
    её позиции — E ПЕРВЫМ (меньший timestamp), D ВТОРЫМ (больший) —
    единственный детерминированный способ поставить D первым в очереди
    (queue[0], обрабатывается ДО Stop), E вторым (queue[1], не тронута), не
    полагаясь на порядок среди РАВНЫХ timestamp (не гарантирован SQLite
    `ORDER BY`).

    ДВА РАЗДЕЛЬНЫХ вызова `seed()`/`seed_library` (каждый — свой
    `force_stop()`/`ensure_db_initialized()` device round-trip) эмпирически
    провалились здесь `sqlite3.OperationalError: no such table: work_ratings`
    на втором вызове (2026-08-14, живой прогон) — та же сигнатура, что
    закрывал `bugs/AT-BUG-044.md` [Verified]; `seed_ordered` делает ОДИН
    round-trip вместо двух, снижая экспозицию к этому классу гонки в этом
    конкретном кейсе. Заведён `bugs/AT-BUG-069.md` (`regression_of:
    AT-BUG-044`) — НЕ регрессия того фикса (он правит `_schema_ready()`,
    другую функцию), а кандидат-дефект в `_pull_baseline` (игнорирует
    возврат `pull_app_file` для `-wal`/`-shm`). Изолирующий эксперимент (20
    живых прогонов, см. AT-BUG-069) НЕ воспроизвёл гонку — вклад СНИЖЕН, но
    НЕ исключён при N=20; формулировка «класс гонки не воспроизводится» была
    непроверенным каузальным негативом (CLAUDE.md правило 14), заменена
    честной."""
    app_steps.clean_state()
    app_steps.seed_library_ordered([
        (_METADATA_WORK_E_EMPTY, "PENDING"),
        (_METADATA_WORK_D_EMPTY, "PENDING"),
    ])
    yield


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-187")
@allure.title(
    "Fetch missing metadata: Stop останавливает процесс мид-fetch — Stopped(N) "
    "с частичным счётчиком, оставшиеся работы не тронуты"
)
@pytest.mark.parametrize("replay", [rb.WORK_METADATA_FETCH_FILENAME], indirect=True)
def test_fetch_missing_metadata_stop_mid_process(metadata_fetch_stop_queue_seeded, replay, driver):
    # Given в Room две работы с пустым title (D, E), обе дают успешный скрейп
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_metadata_fetch_queue_count(driver, 2)

    # When пользователь нажимает «Fetch»
    settings_steps.start_metadata_fetch(driver)

    # And ДО завершения обработки работы E (пока видна подпись «Fetching 1 / 2…»,
    # ДО «Fetching 2 / 2…») нажимает «Stop» — окно не меньше 1.5с реального
    # времени (`delay(1_500L)` между работами, SettingsScreen.kt:248), ловим
    # момент по появлению подписи, не по sleep
    settings_steps.assert_metadata_fetch_progress(driver, 1, 2)
    settings_steps.stop_metadata_fetch(driver)

    # Then состояние становится Stopped — подпись «Stopped — 1 works updated»
    # (обновилась только D — та, что уже была обработана ДО отмены)
    settings_steps.assert_metadata_fetch_stopped(driver, 1)

    # And кнопка на месте «Stop» возвращается к виду «Fetch», доступна для
    # повторного запуска
    settings_steps.assert_metadata_fetch_button_visible(driver)

    # And в Room: title работы D ЗАПОЛНЕН, title работы E ОСТАЁТСЯ пустым
    # (цикл прерван `if (!isActive) break` до итерации E)
    rows = seed_db.read_work_ratings_full()
    scraped_d = rb.METADATA_FETCH_WORK_A
    row_d = rows[_METADATA_WORK_D_EMPTY.ao3_id]
    assert row_d["title"] == scraped_d.title, row_d
    assert row_d["author"] == scraped_d.author, row_d
    assert row_d["fandom"] == scraped_d.fandom, row_d
    assert row_d["word_count"] == scraped_d.word_count, row_d

    row_e = rows[_METADATA_WORK_E_EMPTY.ao3_id]
    assert row_e["title"] == "", (
        f"title работы E не должен был обновиться (Stop до её обработки), реально: {row_e['title']!r}"
    )


# --- TC-188: Show copy-URL button (секция DEBUG) ---
#
# Продуктовый контракт «Copied!»/1500мс-таймер/содержимое буфера — DEFERRED,
# НЕ реализован здесь: отложен решением ESC-032 (путь б.1) по
# `bugs/AT-BUG-068.md` (`DOMException: Write permission denied` бросался
# permission-слоем Blink ДО Android `ClipboardManager` на этом AVD/WebView,
# путь (а) АРХИТЕКТУРНО недостижим). Сам AT-BUG-068 закрыт (Fixed,
# 2026-08-21) — закрыт блокер АВТОМАТИЗАЦИИ ЯДРА (якорь факта вызова), а не
# продуктовая грань; пересмотр deferred-части — за Lead/test-designer.
# ВАЖНО (критик-раунд 2, 2026-08-21): наблюдаемая в прогонах подпись «Copied!»
# НЕ означает, что clipboard разрешён — после фикса BUG-069 (Verified,
# `fixed_in 85fbed4`) её печатают ОБЕ ветки `ao3_bridge.js:1157-1186`: и резолв
# `writeText` (:1180), и `execCommandFallback` при РЕДЖЕКТЕ (:1173). Исход
# промиса этим тестом как вердикт НЕ определяется — только пишется в
# диагностическое allure-вложение (счётчики resolved/rejected window-пробы),
# вопрос «резолвится или фолбэк» остаётся открытым для триажа AT-BUG-068.
# Ядро кейса, переформулированное по
# решению ESC-032 путь (б.1) и автоматизируемое сейчас: обе стороны тумблера
# переключаются немедленно без reload, кнопка «Copy URL» не перекрыта
# тап-зонами (guard, образец TC-119), клик доходит до DOM-узла и
# `navigator.clipboard.writeText` РЕАЛЬНО вызывается (позитивный
# артефакт-якорь — счётчик window-пробы, взводимой `arm_clipboard_write_probe`
# ДО тапа; см. `browser_steps.assert_copy_url_write_text_invoked`). Связанный
# продуктовый баг `bugs/BUG-069.md` (`ao3_bridge.js` без `.catch()`) —
# ПОФИКШЕН и Verified 2026-08-15, вне мандата этого теста.

@pytest.mark.p2
@pytest.mark.replay
@allure.id("TC-188")
@allure.title(
    "Show copy-URL button: обе стороны тумблера переключаются немедленно, "
    "без перекрытия инжектированного интерактива"
)
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_debug_copy_url_toggle_both_directions_without_overlap(loved_work_seeded, replay, driver):
    # Given тумблер «Show copy-URL button» — OFF (дефолт, подтверждено явным
    # assert'ом — класс ложно-зелёных #2, CLAUDE.md), tap_to_scroll — ON (нужен
    # для последней грани Then — guard тап-зон), открыта replay work-страница.
    # Порядок ВАЖЕН: `swipe_to_text`/`BaseScreen._swipe_search` свайпает только
    # ВНИЗ по экрану (`y1_frac=0.8 -> y2_frac=0.25`) — секция "Reader" (Tap to
    # scroll) стоит ВЫШЕ секции "Debug" (Show copy-URL button, последняя на
    # экране); проверка Debug-тумблера ПЕРЕД Reader увела бы прокрутку мимо
    # Reader без пути назад (красный прогон 2026-08-14 поймал это дважды).
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_tap_to_scroll(driver)
    # Readback после идемпотентного условного сеттера (класс 2 ложно-зелёных
    # негативов, CLAUDE.md): `enable_tap_to_scroll` тапает, только если
    # прочитанное состояние не совпало с желаемым — без сверки несработавший
    # тап оставил бы Given несоответствующим кейсу, а финальный
    # `assert_scroll_unchanged` ниже проходил бы тривиально (зональный эффект
    # не заряжен). Тот же приём уже применён рядом к debug_copy_url и
    # собратом TC-124 (`test_reading_ux.py:312`).
    settings_steps.assert_tap_to_scroll_enabled(driver, expected=True)
    settings_steps.assert_debug_copy_url_enabled(driver, False)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)

    # Then плавающая кнопка «Copy URL» НЕ ВИДНА пользователю
    browser_steps.assert_copy_url_button_hidden(driver)

    # Given документ work-страницы помечен уникальным маркером идентичности
    # (позитивный якорь класса 1 ложно-зелёных негативов, CLAUDE.md/TC-124):
    # BrowserScreen.kt несёт ДВА структурно разных механизма с одинаковым
    # наблюдаемым результатом «кнопка появилась» — реактивный
    # `LaunchedEffect(debugCopyUrl)` (evaluateJavascript, БЕЗ reload, :200-205)
    # и переинъекция `window.__ao3DebugCopyUrl` в `onPageFinished` при ЛЮБОМ
    # reload (:668-673). Кейс требует ИМЕННО первого пути («без перезагрузки
    # страницы») — без маркера регрессия «debugCopyUrl тоже стал
    # перезагружать» (по образцу соседних `LaunchedEffect(darkTheme)`/
    # `LaunchedEffect(einkMode)`, реально вызывающих `wv.reload()`) была бы не
    # поймана.
    doc_marker = browser_steps.mark_document_identity(driver)

    # When пользователь, НЕ покидая эту же страницу, переключает тумблер «Show
    # copy-URL button» в ON (через Settings, без reload WebView)
    app_steps.open_tab(driver, "Settings")
    settings_steps.set_debug_copy_url(driver, True)
    app_steps.open_tab(driver, "Browse")

    # Then кнопка «Copy URL» появляется НЕМЕДЛЕННО, без перезагрузки страницы
    # (window.setDebugCopyUrl вызывается реактивно, BrowserScreen.kt:182) —
    # маркер идентичности документа доказывает это позитивно, не полагаясь
    # только на совпадающий наблюдаемый эффект
    browser_steps.assert_document_identity_preserved(driver, doc_marker)
    browser_steps.assert_copy_url_button_visible(driver)

    # Given вызов navigator.clipboard.writeText помечен window-пробой ДО тапа
    # (эскалация TC-188-automate, 2026-08-21, AT-BUG-068): якорь факта вызова
    # живёт в window ТЕКУЩЕГО документа и переживает пере-аттач
    # chromedriver-сессии на каждом contexts.in_webview — в отличие от прежнего
    # якоря (запись DOMException в эфемерном driver.get_log('browser')),
    # дававшего флак ~20% и маскировавшего tooling-потерю под вердикт «клик не
    # дошёл». Обёртка зовёт оригинал — семантика приложения не меняется.
    probe_token = browser_steps.arm_clipboard_write_probe(driver)

    # When пользователь тапает по кнопке «Copy URL»
    scroll_before = browser_steps.get_webview_scroll_y(driver)
    browser_steps.tap_copy_url_button(driver)

    # Then (ядро, автоматизируемое; ESC-032 путь б.1) клик доходит до DOM-узла
    # кнопки, и navigator.clipboard.writeText РЕАЛЬНО вызывается — позитивный
    # артефакт-якорь (счётчик window-пробы; либо подпись «Copied!» при своём
    # токене — резолв ЛИБО execCommand-фолбэк, ветки неразличимы по подписи;
    # замер 2026-08-21: rejected=1 NotAllowedError — печатает фолбэк), не
    # ассертит продуктовый Then «Copied!»/1.5с-таймер
    # (deferred, AT-BUG-068). Утрата пробы (пересозданный документ/недоступный
    # WEBVIEW-контекст) поднимает ClipboardWriteProbeLost, а не ложный
    # AssertionError про продукт.
    browser_steps.assert_copy_url_write_text_invoked(driver, probe_token)

    # And (грань nf-a11y-interactive-overlap) тап по кнопке НЕ запускает
    # зональный эффект tap_to_scroll (страница не скроллится), несмотря на то,
    # что кнопка физически лежит в нижней трети экрана (position:fixed;
    # bottom:12px) — узел <button> входит в whitelist guard'а тап-зон
    # (ao3_bridge.js:1155), тот же контракт, что уже верифицирован TC-119 на
    # другом <button>-узле
    browser_steps.assert_scroll_unchanged(driver, scroll_before, timeout=5)

    # When пользователь переключает тумблер обратно в OFF (та же страница, без reload)
    app_steps.open_tab(driver, "Settings")
    settings_steps.set_debug_copy_url(driver, False)
    app_steps.open_tab(driver, "Browse")

    # Then кнопка «Copy URL» немедленно скрывается — маркер идентичности
    # проверяется и для обратного направления (Инвариант TC-188 требует ОБЕИХ
    # сторон тумблера, не только ON)
    browser_steps.assert_document_identity_preserved(driver, doc_marker)
    browser_steps.assert_copy_url_button_hidden(driver)
