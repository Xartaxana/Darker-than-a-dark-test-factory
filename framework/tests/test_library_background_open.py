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
snackbar`)."""
from __future__ import annotations

import allure
import pytest

from framework.config import settings
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps

_DOWNLOADED_WORK_FIXTURE = settings.DATA_DIR / "fixtures" / "downloaded_work.html"


@pytest.fixture()
def downloaded_work_seeded_with_path():
    """Работа LOVED засеяна с рейтингом SAVE и скачанным локальным файлом — тот же
    приём, что `downloaded_work_seeded` в `conftest.py`, но ДОПОЛНИТЕЛЬНО возвращает
    device-путь `downloadPath` (нужен TC-174/TC-189, чтобы собрать ожидаемый
    `file://`-URL той же формулой, что `WorkRating.localFileUrl()`
    (LibraryScreen.kt:345-347: `file://$path`, path уже НЕ несёт схему), не хардкодя
    путь — тот же приём, что `test_security_file_access.py::_PROBE_TARGET_ABS_PATH`,
    только путь здесь получен из фактического возврата сидинга, а не собран вручную)."""
    app_steps.clean_state()
    device_path = app_steps.seed_downloaded_work(W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE)
    yield W.LOVED, device_path


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

    # Then число вкладок становится 2, активная вкладка не меняется (те же три
    # инварианта, что TC-173) — и новая (фоновая) вкладка несёт URL ЛОКАЛЬНОГО
    # файла (file://<downloadPath>), а НЕ https://archiveofourown.org/works/<id>
    app_steps.wait_persisted_tab_count(2, timeout=15)
    app_steps.assert_persisted_active_tab_index(0)
    app_steps.assert_persisted_tab_url_at(1, expected_url)


@pytest.mark.p1
@allure.id("TC-175")
@allure.title(
    "Потолок MAX_TABS через «Open in background tab» из Library: диалог лимита, "
    "снекбара НЕТ, экран остаётся Library"
)
def test_library_overlay_open_in_background_at_tab_limit_shows_dialog(
    loved_work_seeded, driver,
):
    work = loved_work_seeded

    # Given открыто 10 вкладок Browse (MAX_TABS) — рецепт TC-022/TC-137: стартовая
    # Home-вкладка (index 0) + 1 deep-link на HOME_URL (TabStrip ещё скрыт при
    # tabs.size==1) + 8 тапов «New tab». Каждый промежуточный тап не должен
    # преждевременно упереться в диалог лимита.
    app_steps.wait_home_ready_for_deep_link(driver)
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    for _ in range(8):
        browser_steps.open_new_tab(driver)
        browser_steps.assert_tab_limit_dialog_not_shown(driver)
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
    # Library — И снекбара «Opened in background» НЕТ (openTap возвращает false ДО
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

    # And при переключении на эту вкладку WebView рендерит содержимое файла —
    # сводим число вкладок к одной (закрываем Home), т.к. chromedriver прилипает
    # к вкладке-0 при >1 живой WebView (см. модульный докстринг test_tabs.py)
    app_steps.open_tab(driver, "Browse")
    browser_steps.switch_to_tab(driver, 1)
    browser_steps.close_other_tabs(driver)
    browser_steps.assert_local_file_opened(driver)
