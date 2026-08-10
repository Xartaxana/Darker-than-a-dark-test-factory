"""Тесты области library — overlay действий «Open in background tab»
(LibraryScreen.kt WorkActionsSheetContent, feature=library-card-open-background-tab):
TC-173 (основной путь, экран остаётся Library), TC-174 (цель на вкладке Files —
локальный файл, не AO3-URL), TC-175 (потолок MAX_TABS=10 через эту дверь),
TC-189 (персистентность фоновой вкладки на локальный файл через kill+relaunch).

Общая инфраструктура: `app_steps.wait_persisted_tab_count`/
`assert_persisted_tab_url_at`/`assert_persisted_active_tab_index` (persisted-prefs
оракулы, НЕ WEBVIEW-контекст — тот же приём и обоснование sticky-context
(AT-BUG-018/022), что TC-131/132/136/137, см. модульный докстринг `test_tabs.py`).
`library_steps.open_in_background_via_overlay` — long-press карточки + тап первого
пункта overlay («Open in background tab») — тот же оверлей, что уже используют
`delete_via_overlay`/TC-034/035.

TC-176 (снекбар подтверждения, area=tabs, красный замок BUG-059) — в `test_tabs.py`,
не здесь: другая область (`tabs`), другой feature-тег (`browse-background-open-
snackbar`).

`downloaded_work_seeded_with_path` (TC-174/TC-189) — фикстура `conftest.py`, НЕ
локальная копия `downloaded_work_seeded` (F1-ревью TC-174, замечание 2, D-0043):
оба conftest-фикстуры делят один сидинг-хелпер `_seed_downloaded_work_default`,
эта дополнительно возвращает device-путь `downloadPath`."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, library_steps


@pytest.mark.p1
@allure.id("TC-173")
@allure.title(
    "«Open in background tab» из overlay Library открывает работу в фоновой "
    "вкладке, не покидая экран Library"
)
def test_library_overlay_open_in_background_stays_on_library(loved_work_seeded, driver):
    work = loved_work_seeded

    # Given приложение на экране Library, вкладка Favorite активна, карточка видна,
    # открыта ровно 1 вкладка Browse (Home) — позитивный якорь ДО When (A2-приём
    # TC-136: делает Then про счёт вкладок дельтой, а не голой абсолютной проверкой).
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    app_steps.wait_persisted_tab_count(1, timeout=10)
    topmost_before = library_steps.capture_topmost_card_y(driver, [work.title])

    # When пользователь долгим нажатием по карточке открывает overlay действий и
    # тапает первый пункт «Open in background tab»
    library_steps.open_in_background_via_overlay(driver, work.title)

    # Then число вкладок Browse становится 2, новая (фоновая) вкладка несёт URL
    # самой работы, активная вкладка НЕ меняется (остаётся вкладка-0/Home)
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.assert_persisted_tab_url_at(1, work.url)
    app_steps.assert_persisted_active_tab_index(0)

    # And экран остаётся Library — оверлей закрыт, TabStrip (рендерится только на
    # Browse, MainActivity.kt:408) не появился, карточка всё ещё видна на месте
    library_steps.assert_actions_overlay_closed(driver)
    browser_steps.assert_tab_strip_not_visible(driver)
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # And позиция списка Library не изменилась (та же карточка на той же Y)
    topmost_after = library_steps.capture_topmost_card_y(driver, [work.title])
    assert topmost_after == topmost_before, (
        f"позиция списка Library изменилась: было Y={topmost_before}, стало Y={topmost_after}"
    )


@pytest.mark.p1
@allure.id("TC-174")
@allure.title(
    "«Open in background tab» с вкладки Files открывает ЛОКАЛЬНУЮ копию, а не AO3-URL"
)
def test_library_files_tab_overlay_open_in_background_targets_local_file(
    downloaded_work_seeded_with_path, driver,
):
    work, device_path = downloaded_work_seeded_with_path
    expected_url = f"file://{device_path}"

    # Given приложение на экране Library, активна вкладка Files, карточка скачанной
    # работы видна, открыта ровно 1 вкладка Browse
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_files_tab(driver)
    library_steps.assert_work_in_files_tab(driver, work.title)
    app_steps.wait_persisted_tab_count(1, timeout=10)

    # When пользователь долгим нажатием по карточке открывает overlay и тапает
    # «Open in background tab»
    library_steps.open_in_background_via_overlay(driver, work.title)

    # Then число вкладок становится 2, активная вкладка не меняется, экран остаётся
    # Library (те же три инварианта, что TC-173 — F1-ревью замечание 1: третий
    # инвариант, TabStrip не появился, был назван в Then, но не проверен) — и
    # новая (фоновая) вкладка несёт URL ЛОКАЛЬНОГО файла (file://<downloadPath>),
    # а НЕ https://archiveofourown.org/works/<id>
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.assert_persisted_active_tab_index(0)
    browser_steps.assert_tab_strip_not_visible(driver)
    app_steps.assert_persisted_tab_url_at(1, expected_url)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-175")
@allure.title(
    "Потолок MAX_TABS через «Open in background tab» из Library: диалог лимита, "
    "снекбара НЕТ, экран остаётся Library"
)
@pytest.mark.parametrize("replay", [rb.TAB_MARKER_FILENAME], indirect=True)
def test_library_overlay_open_in_background_at_tab_limit_shows_dialog(
    loved_work_seeded, replay, driver,
):
    """F1-ревью TC-175 (блокер): прежняя версия набирала потолок deep-link'ом на
    `HOME_URL` + 8 тапами «New tab» (TabStrip.kt onNewTab -> `openTab(HOME_URL)`) —
    КАЖДЫЙ тап заново грузит живой archiveofourown.org (9 загрузок home за прогон,
    измерено `adb shell settings get global http_proxy` -> `:0`), без фикстуры
    `replay`/маркера. При недоступном/изменившемся AO3 Given падал ТАЙМАУТОМ (страница
    ошибки с baseUrl about:blank не инжектит `__ao3AppDark`), не содержательным
    ассертом. Рецепт TC-131 (тот же потолок, дверь deep-link) избегает этого: набор
    потолка — deep-link'и на детерминированные маркерные страницы `tab_markers.mitm`
    (`marker1..marker7` + повтор `marker1`/`marker2`, `openTab` не дедуплицирует URL),
    ЖИВОЙ остаётся только САМЫЙ ПЕРВЫЙ безусловный старт-ап загрузки Home-вкладки
    (`wait_home_ready_for_deep_link` — тот же принятый минимум зависимости, что у
    ЛЮБОГО теста этого рецепта, TC-131/TC-137), а не девять."""
    work = loved_work_seeded

    # Given открыто 10 вкладок Browse (MAX_TABS) — рецепт TC-131: стартовая
    # Home-вкладка (index 0) + 9 deep-link'ов на маркерные страницы (marker1..marker7,
    # затем повтор marker1/marker2 — `openTab` не дедуплицирует URL, повтор штатно
    # даёт отдельную вкладку). Каждый маркер обслуживается replay детерминированно.
    app_steps.wait_home_ready_for_deep_link(driver)
    for i in (1, 2, 3, 4, 5, 6, 7, 1, 2):
        app_steps.open_deep_link(rb.tab_marker_url(i))
        browser_steps.assert_tab_title_visible(driver, rb.tab_marker_title(i), timeout=15)
    app_steps.wait_persisted_tab_count(10, timeout=15)

    # Given пользователь на экране Library — карточка работы видна (засеяна
    # `loved_work_seeded`, рейтинг SAVE, дефолтная первая вкладка Favorite)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    topmost_before = library_steps.capture_topmost_card_y(driver, [work.title])

    # When пользователь долгим нажатием по карточке открывает overlay и тапает
    # «Open in background tab»
    library_steps.open_in_background_via_overlay(driver, work.title)

    # Then диалог «Tab limit reached» с дословным текстом появляется ПОВЕРХ экрана
    # Library — И снекбара «Opened in background» НЕТ (openTab возвращает false ДО
    # записи сигнала backgroundTabOpen, до dismiss — дольше живое окно проверки)
    browser_steps.assert_tab_limit_dialog_shown(
        driver, expected_max=10,
        expected_message="You have 10 tabs open. Close some tabs before opening a new one.",
    )
    browser_steps.assert_opened_in_background_snackbar_not_shown(driver)
    browser_steps.dismiss_tab_limit_dialog(driver)

    # And overlay действий Library уже закрыт (независимо от исхода действия), И
    # экран НЕ переключился — остаётся Library (TabStrip не появился, в отличие
    # от TC-137, где тело карточки переключает экран безусловно)
    library_steps.assert_actions_overlay_closed(driver)
    browser_steps.assert_tab_strip_not_visible(driver)
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # And wait_persisted_tab_count(10) держится (не выросло) — вкладка не создана,
    # позиция списка Library до и после диалога идентична
    app_steps.wait_persisted_tab_count(10, timeout=5)
    topmost_after = library_steps.capture_topmost_card_y(driver, [work.title])
    assert topmost_after == topmost_before, (
        f"позиция списка Library изменилась: было Y={topmost_before}, стало Y={topmost_after}"
    )

    # And отклонённый URL не приезжает отложенно — держит бюджет без появления
    # новой вкладки (регрессионный замок класса CH-005, тот же приём TC-131/TC-137)
    app_steps.assert_persisted_marker_absent_for(work.url, budget_s=4.0, expected_total=10)


@pytest.mark.p1
@allure.id("TC-189")
@allure.title(
    "Фоновая вкладка на локальный файл (открытая с вкладки Files) переживает "
    "kill+relaunch с тем же file://-URL"
)
def test_background_local_file_tab_persists_after_kill_relaunch(
    downloaded_work_seeded_with_path, driver,
):
    work, device_path = downloaded_work_seeded_with_path
    expected_url = f"file://{device_path}"

    # Given на вкладке Files долгим нажатием по карточке через overlay открыта
    # фоновая вкладка (тот же приём, что TC-174) — persisted open_tabs_urls несёт
    # file://<downloadPath> на позиции 1
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.open_files_tab(driver)
    library_steps.assert_work_in_files_tab(driver, work.title)
    app_steps.wait_persisted_tab_count(1, timeout=10)

    library_steps.open_in_background_via_overlay(driver, work.title)
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.assert_persisted_tab_url_at(1, expected_url)

    # When процесс приложения убит и перезапущен (реальная смерть процесса, не
    # пересоздание Activity)
    app_steps.restart_app_via_adb_asserting_new_process(driver)
    app_steps.wait_ui_ready(driver)

    # Then после перезапуска обе вкладки восстановлены, URL восстановленной
    # вкладки побайтово совпадает с тем, что был до перезапуска
    app_steps.wait_persisted_tab_count(2, timeout=20)
    app_steps.assert_persisted_tab_url_at(1, expected_url)

    # And при переключении на эту вкладку WebView РЕАЛЬНО рендерит содержимое файла
    # (не только схему URL — F1-ревью замечание: `assert_local_file_opened` одна
    # доказывает лишь `file://`-схему current_url, не факт рендера DOM; вторая
    # строка по образцу TC-034, `test_downloads.py:110-111`, доказывает, что
    # мобильный viewport/reader.css реально инжектированы, т.е. DOM загрузился) —
    # сводим число вкладок к одной (закрываем Home), т.к. chromedriver прилипает
    # к вкладке-0 при >1 живой WebView (см. модульный докстринг test_tabs.py)
    app_steps.open_tab(driver, "Browse")
    browser_steps.switch_to_tab(driver, 1)
    browser_steps.close_other_tabs(driver)
    browser_steps.assert_local_file_opened(driver)
    browser_steps.assert_downloaded_page_styled(driver)
