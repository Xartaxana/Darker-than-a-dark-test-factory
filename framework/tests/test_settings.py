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
    browser_steps.scroll_webview_to(driver, 900)
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
    `onWorkFinished` auto-mark структурно исключён на этой фикстуре:
    `works_multi.mitm` не несёт `<div id="chapters">`; на живой странице
    слушатель существует, но пишет `READ`). Источник — транзитный mount+dispose
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
