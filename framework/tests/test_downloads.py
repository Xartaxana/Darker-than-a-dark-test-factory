"""Тесты области downloads (test-cases/downloads/): открытие и удаление уже
скачанного файла работы. Фикстура `downloaded_work_seeded` кладёт на устройство
готовый локальный `.html` и заполняет `downloadPath` в Room напрямую — без
обращения к `DownloadRepository`/сети (см. заметки TC-034/TC-035/TC-036).

TC-032/TC-033 (авто- и ручное скачивание) сюда намеренно не входят — оба требуют
replay-записи страницы работы с реальной разметкой `li.download a[href*=".html"]`,
которой в `framework/data/recordings/` пока нет (там только `ao3_home_smoke.mitm`,
запись главной страницы); соответствующие кейсы возвращены в Review с этим блокером
(см. TC-032.md/TC-033.md, тот же класс блокера, что у TC-009/013/014/015)."""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps, browser_steps, library_steps


@pytest.mark.p1
@allure.id("TC-034")
@allure.title("Открытие скачанного файла применяет мобильный viewport и reader.css")
def test_open_downloaded_file_applies_viewport_and_reader_css(downloaded_work_seeded, driver):
    # Given работа засеяна с downloadPath на реально существующий (фикстурный,
    # без сети) .html-файл; вкладка FILES содержит эту работу
    work = downloaded_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_files_tab(driver, work.title)

    # When пользователь тапает open-иконку карточки (единственный элемент карточки,
    # открывающий локальный файл — общий тап по карточке ведёт на живой AO3 URL,
    # см. WorkCard.onClick vs onOpenDownload в LibraryScreen.kt)
    library_steps.open_downloaded_file(driver, work.title)

    # Открытие файла ДОБАВЛЯЕТ вкладку рядом со стартовой Home (archiveofourown.org)
    # — closeLeftmostTab оставляет ровно одну WebView-страницу, иначе chromedriver
    # присоединяется к недетерминированной из двух в общем WEBVIEW-процессе
    browser_steps.close_other_tabs(driver)

    # Then файл открыт через file://, и в загруженном DOM инжектированы мобильный
    # viewport и reader.css (loadTabContent/injectReaderCss, BrowserScreen.kt) —
    # наблюдаемый потребительский симптом, а не деталь реализации
    browser_steps.assert_local_file_opened(driver)
    browser_steps.assert_downloaded_page_styled(driver)


@pytest.mark.p1
@allure.id("TC-035")
@allure.title("Delete downloaded file удаляет только файл, сохраняя строку рейтинга")
def test_delete_downloaded_file_keeps_rating_row(downloaded_work_seeded, driver):
    # Given работа W имеет рейтинг Loved и скачанный файл, вкладка FAVORITE
    # показывает open-иконку
    work = downloaded_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    library_steps.assert_open_icon_shown(driver, work.title)

    # When long-press по карточке W, в overlay выбрано «Delete downloaded file»
    library_steps.delete_via_overlay(driver, work.title, "Delete downloaded file")

    # Then работа W остаётся во вкладке FAVORITE с прежним рейтингом Loved, но
    # снова показывает download-иконку (downloadPath очищен, строка WorkRating цела)
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    library_steps.assert_download_icon_shown(driver, work.title)
    library_steps.assert_work_not_in_files_tab(driver, work.title)


@pytest.mark.p1
@allure.id("TC-036")
@allure.title("Delete work удаляет и файл, и строку рейтинга целиком")
def test_delete_work_removes_row_and_file(downloaded_work_seeded, driver):
    # Given работа W имеет рейтинг Loved и скачанный файл
    work = downloaded_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # When long-press по карточке W, в overlay выбрано «Delete work»
    library_steps.delete_via_overlay(driver, work.title, "Delete work")

    # Then работа W полностью исчезает из Library — ни FAVORITE, ни FILES
    library_steps.assert_work_not_in_tab(driver, "SAVE", work.title)
    library_steps.assert_work_not_in_files_tab(driver, work.title)
