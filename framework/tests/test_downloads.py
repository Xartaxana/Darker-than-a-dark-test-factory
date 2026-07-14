"""Тесты области downloads (test-cases/downloads/): открытие и удаление уже
скачанного файла работы. Фикстура `downloaded_work_seeded` кладёт на устройство
готовый локальный `.html` и заполняет `downloadPath` в Room напрямую — без
обращения к `DownloadRepository`/сети (см. заметки TC-034/TC-035/TC-036).

TC-032/TC-033 (авто- и ручное скачивание) сюда намеренно не входят — оба требуют
replay-записи страницы работы с реальной разметкой `li.download a[href*=".html"]`,
которой в `framework/data/recordings/` пока нет (там только `ao3_home_smoke.mitm`,
запись главной страницы); соответствующие кейсы возвращены в Review с этим блокером
(см. TC-032.md/TC-033.md, тот же класс блокера, что у TC-009/013/014/015).

TC-038 (auto-scan/relink при смене папки загрузок) использует SAF-инфраструктуру
AT-BUG-005 (`framework/steps/saf_steps.py::saf_pick_folder`, блокер снят инкрементом 1,
доказано зелёным `test_saf_infra_probe.py::test_saf_pick_download_folder`) — заметка в
теле TC-038.md об отсутствии обходного пути устарела, см. правку кейса."""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import allure
import pytest

from framework.core import adb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, library_steps, saf_steps, settings_steps


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


# --- TC-038: смена папки загрузок автоматически запускает silent-скан ---
# (SettingsViewModel.setDownloadFolderUri -> scanForDownloads(silent=true),
# SettingsScreen.kt:523-530) и перелинковывает orphan-файл, если что-то реально
# найдено (DownloadRepository.scanForOrphanedDownloads, WORK_ID_PATTERN
# `_<цифры>.html`). Файл готовится adb-шеллом ДО сессии Appium — тот же детерминизм,
# что и `saf_probe_workspace` (AT-BUG-005 инкремент 1, test_saf_infra_probe.py):
# picker должен УВИДЕТЬ уже существующий файл, не создавать его кликами.
_ORPHAN_DOWNLOAD_DIR = "/sdcard/Download"

# Подпапка генерируется УНИКАЛЬНОЙ на каждый вызов фикстуры (не константа), а не
# фиксированным именем — обходит найденную flaky-особенность DocumentsUI
# (`bugs/AT-BUG-005.md`, дополнено этим прогоном): если OpenDocumentTree на СТАРТЕ
# открывается СРАЗУ в ТОЙ ЖЕ подпапке, что была подтверждена (ALLOW) на
# непосредственно предыдущем вызове этого же теста, корневой сегмент breadcrumb'а
# (`DocumentsUIScreen._root_breadcrumb_segment`, на который опирается
# `reset_to_root`) иногда рендерится с `enabled="false"` и `BaseScreen.tap`
# (`EC.element_to_be_clickable`) бесконечно таймаутит — воспроизведено дважды подряд
# как на этом тесте, так и НЕЗАВИСИМО на существующей пробе
# `test_saf_infra_probe.py::test_saf_pick_download_folder` (тот же класс, не
# специфично для TC-038). Уникальное имя гарантирует, что цель ТЕКУЩЕГО прогона
# никогда не совпадает с последней подтверждённой папкой ПРЕДЫДУЩЕГО прогона —
# ломает единственное известное условие репродукции. Сама находка не чинится
# здесь (документирована в `bugs/AT-BUG-005.md`, эта же дата) — это обход на
# уровне теста, а не фикс инфраструктуры.
def _orphan_subfolder() -> str:
    return f"tc038_orphan_relink_{uuid.uuid4().hex[:10]}"


def _orphan_filename(work: W.Work) -> str:
    """Соответствует `DownloadRepository.WORK_ID_PATTERN` (`_<цифры>.html` в конце
    имени) — сам workId вычитывается регекспом независимо от произвольного префикса."""
    return f"orphan_{work.ao3_id}.html"


@pytest.fixture()
def orphan_download_relink_seeded():
    """TC-038: `W.ORPHAN_RELINK_TARGET` засеяна в Room с рейтингом SAVE и
    `downloadPath=null` (`seed_library`/`seed_db.seed` не заполняет это поле — см.
    `seed_db._insert_rows`), и на устройстве заранее (adb-шеллом, ДО сессии Appium)
    лежит orphan `.html` файл во ВЛОЖЕННОЙ подпапке `/sdcard/Download/<subfolder>`
    (сам "Download" системная защита приватности SAF выбрать не даёт, см. докстринг
    `saf_steps.saf_pick_folder`). `<subfolder>` — уникальное имя на каждый вызов
    (`_orphan_subfolder`, см. заметку выше про DocumentsUI-flake). workId в имени
    файла совпадает с `ao3_id` засеянной работы — при смене папки загрузок на эту
    подпапку silent-скан находит файл и ПЕРЕЛИНКОВЫВАЕТ уже существующую строку
    (relinked, не added: строка в Room уже есть, меняется только downloadPath).

    Возвращает `(work, subfolder)`. Единственный try/finally вокруг ВСЕГО setup
    (mkdir + push, включая временный локальный файл) — тот же паттерн
    гарантированного teardown, что и `saf_probe_workspace`
    (test_saf_infra_probe.py): любая точка отказа setup покрыта уборкой, не
    только yield."""
    work = W.ORPHAN_RELINK_TARGET
    subfolder = _orphan_subfolder()
    app_steps.clean_state()
    app_steps.seed_library([(work, "SAVE")])
    remote_dir = f"{_ORPHAN_DOWNLOAD_DIR}/{subfolder}"
    remote_file = f"{remote_dir}/{_orphan_filename(work)}"
    tmp_dir = Path(tempfile.mkdtemp(prefix="tc038_orphan_"))
    local_html = tmp_dir / _orphan_filename(work)
    try:
        local_html.write_text(
            "<html><body>TC-038 orphan relink fixture</body></html>", encoding="utf-8"
        )
        adb.shell(f"mkdir -p {remote_dir}")
        adb.push_external(local_html, remote_file)
        yield work, subfolder
    finally:
        adb.shell(f'rm -rf "{remote_dir}"')
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.p2
@allure.id("TC-038")
@allure.title("Смена папки загрузок автоматически запускает silent-скан и перелинковывает orphan-файл")
def test_change_download_folder_triggers_silent_scan_and_relinks_orphan_file(
    orphan_download_relink_seeded, driver
):
    # Given работа засеяна в Room без downloadPath, в целевой (ещё не выбранной)
    # SAF-подпапке уже лежит orphan .html файл, чьё имя оканчивается на "_<ao3_id>.html"
    work, subfolder = orphan_download_relink_seeded
    saf_steps.open_settings_scrolled_to(driver, "Pick")

    # When пользователь меняет папку загрузок в Settings на целевую через системный
    # OpenDocumentTree picker (вложенная подпапка — сам "Download" системная защита
    # приватности выбрать не даёт, см. saf_steps.saf_pick_folder)
    saf_steps.tap_settings_action(driver, "Pick")
    saf_steps.saf_pick_folder(driver, f"Download/{subfolder}")

    # Then запускается silent-скан автоматически (без явного нажатия "Scan for
    # downloads") и появляется диалог результата, потому что реально что-то
    # перелинковано (1 файл найден, 1 relinked, 0 added — отличие от TC-037, где
    # диалог тоже появляется, но с "0", и от смены папки без orphan-файлов, где
    # диалог вообще не появляется)
    settings_steps.assert_scan_complete_dialog(
        driver, expected_text="Found 1 files — relinked 1, added 0 new."
    )
    settings_steps.dismiss_scan_dialog(driver)

    # And работа в Library получает связанный файл — карточка на вкладке FAVORITE
    # (SAVE) показывает open-иконку вместо download-иконки
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    library_steps.assert_open_icon_shown(driver, work.title)
