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
@pytest.mark.live
@allure.id("TC-020")
@allure.title("Clear all ratings сбрасывает бейджи на открытых страницах AO3 без перезагрузки")
@pytest.mark.skip(
    reason=(
        "Then кейса не воспроизводится на реальном приложении (witness "
        "2026-07-18, device emulator-5554): SettingsViewModel.confirmClearAll() "
        "(SettingsScreen.kt:501-504) вызывает ТОЛЬКО repo.clearAllRatings() — "
        "не зовёт BrowserViewModel.refreshActiveTabRating/broadcastRatingChange "
        "(они вызываются лишь из applyRating/savePanelRating, см. "
        "BrowserViewModel.kt:767-789,868-878), поэтому currentPageRating "
        "открытой work-страницы (RatingMenu-панель) остаётся прежним без "
        "reload/повторной навигации (onPageLoaded, BrowserViewModel.kt:463-509 "
        "— единственное место, где currentPageRating перечитывается из БД). "
        "Прогон: baseline(selected)=134.2, luma после Clear all + возврата на "
        "Browse НЕ поднялась выше 178.9 за 10с — кнопка осталась в выбранном "
        "виде. Кейс's заметки для автоматизации сами предвидели этот сценарий "
        "('если по факту требуется reload — расхождение с PROJECT.md/§9, "
        "эскалировать через bug-reporter, не подгонять Then под предположение') "
        "— test-automator продуктовые баги не заводит (CLAUDE.md), поэтому "
        "TC-020.md остаётся Approved БЕЗ automated_by; тест написан и оставлен "
        "skip-помеченным как witness находки для триажа (test-runner/"
        "bug-reporter решают APP_BUG vs TEST_BUG)."
    )
)
def test_clear_all_ratings_resets_open_work_page_badge(loved_work_seeded, driver):
    # Given работа W засеяна с рейтингом Loved (SAVE), её страница /works/{id} открыта
    # на вкладке Browse — встроенная панель RatingMenu отражает выбранный рейтинг
    # «Favorite» (Loved), Settings ещё не открыт (мультитаб: WebView-вкладка остаётся
    # открытой при навигации между Browse и Settings)
    work = loved_work_seeded
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    selected_luma = rating_steps.capture_panel_rating_baseline(driver, "SAVE")

    # When пользователь переходит в Settings и подтверждает диалог «Clear all ratings»
    app_steps.open_tab(driver, "Settings")
    settings_steps.clear_all_ratings(driver)

    # Then при возврате на вкладку с открытой страницей работы W бейдж «Loved» исчез
    # (панель RatingMenu показывает отсутствие рейтинга) — без ручной перезагрузки
    # страницы пользователем, тот же прокси (цвет кнопки рейтинга), что TC-009/TC-010
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
