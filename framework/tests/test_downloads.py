"""Тесты области downloads (test-cases/downloads/): открытие и удаление уже
скачанного файла работы. Фикстура `downloaded_work_seeded` кладёт на устройство
готовый локальный `.html` и заполняет `downloadPath` в Room напрямую — без
обращения к `DownloadRepository`/сети (см. заметки TC-034/TC-035/TC-036).

TC-032 (авто-скачивание при простановке Loved) и TC-033 (ручное скачивание из
Library) АВТОМАТИЗИРОВАНЫ (2026-07-18) — блокер AT-BUG-004 снят (Verified
2026-07-09), инфраструктура доведена инкрементом 3: `framework/data/recordings/
work_with_download.mitm` (генерируется `build_work_with_download` в
`scripts/build_replay_recordings.py`) несёт ОБЕ HTTP-транзакции (GET work-страницы
с `li.download a[href*=".html"]` + GET самого `.html`), и `replay`-фикстура
(`conftest.py`) уже подключена к `mitm.set_device_proxy`/`start_replay`. Оба пути
(авто — `BrowserViewModel.applyRating`/`savePanelRating` при `rating=SAVE` и
включённом `autoDownloadSaved`; ручной — `LibraryViewModel.downloadWork`) в итоге
идут через ОДИН И ТОТ ЖЕ `DownloadRepository.downloadWork` (OkHttp, не WebView) —
устаревшее описание PROJECT.md §Download flow про JS `querySelector` для
авто-пути не соответствует фактическому коду (см. `BrowserViewModel.kt:756-758,
862-864,1057-1059` — все три места просто вызывают `downloadWork(workId)`); код
app-under-test — источник истины при расхождении с PROJECT.md. OkHttp использует
системный HTTP-прокси устройства
(`ProxySelector.getDefault()`), поэтому один и тот же `mitm.set_device_proxy()`
покрывает и WebView-навигацию, и сетевой вызов `DownloadRepository` без
дополнительной настройки.

TC-038 (auto-scan/relink при смене папки загрузок) использует SAF-инфраструктуру
AT-BUG-005 (`framework/steps/saf_steps.py::saf_pick_folder`, блокер снят инкрементом 1,
доказано зелёным `test_saf_infra_probe.py::test_saf_pick_download_folder`) — заметка в
теле TC-038.md об отсутствии обходного пути устарела, см. правку кейса.

TC-039 (Restore from backup сворачивает scanForOrphanedDownloads в один диалог)
переиспользует тот же уникальный-subfolder приём (`_orphan_subfolder`/
`_orphan_filename` — уже общие, не только для TC-038) и SAF-инфраструктуру
AT-BUG-005, но требует ДРУГОГО порядка: сама папка загрузок выбирается ДО того,
как в неё кладётся orphan-файл (`app_steps.place_file_in_download_folder`) — иначе
silent-скан самого выбора папки поглотит orphan-файл ДО Restore (см. докстринг
той функции)."""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from functools import partial
from pathlib import Path

import allure
import pytest

from framework.core import adb
from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import (
    app_steps,
    backup_steps,
    browser_steps,
    library_steps,
    rating_steps,
    saf_steps,
    settings_steps,
)


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


# --- TC-032: авто-скачивание при простановке Loved (Auto-download включён) ---
# `rb.WORK_WITH_DOWNLOAD_FILENAME` несёт ДВЕ HTTP-транзакции (work-страница +
# сам .html) для `ALL_WORKS[0]` (`W.LOVED`) — обе идут через ОДИН и тот же
# `replay`-прокси (WebView-навигация НА work-страницу, затем OkHTTP-скачивание
# внутри `DownloadRepository.downloadWork`, см. докстринг модуля выше).
_DOWNLOAD_OPEN_ICON_TIMEOUT = 25  # сеть через локальный mitmdump + запись Room


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-032")
@allure.title("Авто-скачивание запускается при простановке Loved с включённым Auto-download")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_auto_download_triggers_on_loved_rating(replay, clean_app, driver):
    # Given "Auto-download saved works" включена в Settings, открыта страница
    # работы без рейтинга (Library чистая — ни одной строки WorkRating), страница
    # содержит валидную download-ссылку в разметке AO3 (replay-запись).
    # wait_app_ready (не wait_ui_ready) ПЕРЕД навигацией по Settings — тот же
    # паттерн, что закрыл гонку в TC-057/TC-007 (см. test_rating.py): даём стартовой
    # live-загрузке Home осесть ДО того, как открытие Settings/навигация Browse
    # начнут перекладывать активную вкладку.
    app_steps.wait_app_ready(driver)
    saf_steps.open_settings_scrolled_to(driver, "Auto-download favorite works")
    settings_steps.enable_auto_download(driver)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, W.LOVED.ao3_id)

    # When пользователь через панель RatingMenu ставит рейтинг Loved
    rating_steps.rate_current_work(driver, "SAVE")

    # Then запускается скачивание файла без ручного вызова Download — по завершении
    # работа в Library (вкладка FAVORITE) имеет заполненный downloadPath (проверяется
    # косвенно — open-иконка на карточке); таймаут увеличен относительно дефолта:
    # скачивание асинхронное, через сеть (OkHttp -> replay-прокси -> Room)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", W.LOVED.title)
    library_steps.assert_open_icon_shown(driver, W.LOVED.title, timeout=_DOWNLOAD_OPEN_ICON_TIMEOUT)

    # And файл открывается через file:// и содержит стилизованный (не сырой) контент
    # работы (мобильный viewport + reader.css, тот же наблюдаемый факт, что TC-034)
    library_steps.open_downloaded_file(driver, W.LOVED.title)
    browser_steps.close_other_tabs(driver)
    browser_steps.assert_local_file_opened(driver)
    browser_steps.assert_downloaded_page_styled(driver)


# --- TC-033: ручное скачивание работы из Library (Auto-download выключен) ---

@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-033")
@allure.title("Ручное скачивание работы из Library добавляет локальный файл")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_manual_download_from_library_adds_local_file(replay, loved_work_seeded, driver):
    # Given работа засеяна с рейтингом Loved (SAVE), downloadPath=null, Auto-download
    # выключен (дефолт после clean_state — см. loved_work_seeded); карточка на вкладке
    # Library показывает download-иконку (файл ещё не скачан)
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    library_steps.assert_download_icon_shown(driver, work.title)

    # When пользователь нажимает download-иконку на карточке
    library_steps.download_via_card(driver, work.title)

    # Then запускается ручное скачивание (`downloadWork`: сначала regex-поиск
    # download-ссылки на странице работы, затем сохранение файла) — по завершении
    # download-иконка заменяется на open-иконку
    library_steps.assert_open_icon_shown(driver, work.title, timeout=_DOWNLOAD_OPEN_ICON_TIMEOUT)

    # And работа появляется на вкладке FILES (Downloads) экрана Library
    library_steps.assert_work_in_files_tab(driver, work.title)


# --- TC-037: ручной Scan for downloads показывает диалог даже при 0 файлов ---

@pytest.mark.p3
@allure.id("TC-037")
@allure.title("Scan for downloads (ручной триггер) показывает диалог результата даже при 0 файлов")
def test_manual_scan_for_downloads_shows_dialog_on_zero_files(clean_app, driver):
    # Given приложение запущено с чистыми данными: пустая Library, пустая папка
    # загрузок (`pm clear` в `clean_app` очищает и app-private external files dir)
    saf_steps.open_settings_scrolled_to(driver, "Scan")

    # When пользователь нажимает кнопку "Scan for downloads" в Settings
    saf_steps.tap_settings_action(driver, "Scan")

    # Then появляется диалог результата сканирования (`AlertDialog`), даже когда файлов
    # не найдено — сообщение указывает на 0 найденных/перелинкованных файлов. Ручной
    # триггер (`scanForDownloads(silent=false)`, дефолт параметра) ВСЕГДА показывает
    # Done-диалог — отличие от auto-триггера (silent=true, см. TC-038), который при
    # totalFound=0 остаётся в Idle и диалог не показывает.
    settings_steps.assert_scan_complete_dialog(
        driver, expected_text="No .html files found in the download folder."
    )
    settings_steps.dismiss_scan_dialog(driver)

    # And Library остаётся пустой после закрытия диалога
    app_steps.open_tab(driver, "Library")
    library_steps.assert_library_empty(driver)


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
#
# Переиспользуется TC-039 (`restore_scan_workspace`) — тот же класс flaky и та же
# необходимость уникального имени на каждый вызов, не только TC-038; префикс имени
# каталога на устройстве исторический, самой уникальности не вредит.
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


# --- TC-039: Restore from backup сворачивает scanForOrphanedDownloads в один диалог ---
# (importFromUri вызывает downloadRepo.scanForOrphanedDownloads() НАПРЯМУЮ и
# сворачивает счётчики в тот же ImportState.Done, не через ScanDownloadsState —
# SettingsScreen.kt:390-400/1181-1200). Backup-файл кладётся adb-шеллом заранее в
# Downloads root (видим для GetContent сразу, тот же приём, что и orphan-файл
# TC-038 для OpenDocumentTree) — SAF-раунд-трип через собственный «Back up» приложения
# (как в TC-021) здесь не нужен, кейс не про целостность экспорта.
_RESTORE_SCAN_BACKUP_FILENAME = "tc039_restore_scan_backup.json"

# Синтетический ao3Id, НЕ совпадающий ни с одним `Work` в `works.py` — используется
# ТОЛЬКО как decoy-файл (см. докстринг `restore_scan_workspace`), сам по себе не
# несёт продуктовой семантики и не фигурирует ни в одном assert'е.
_DECOY_ORPHAN_ID = "900000940"


@pytest.fixture()
def restore_scan_workspace():
    """TC-039: Library пуста (без сидинга работ — `app_steps.clean_state()`
    единственная подготовка Room). Готовит ДО сессии Appium:
    - backup JSON (`{"version":2,"works":[1 работа без downloadPath],
      "filterProfiles":[]}`) в `/sdcard/Download` (root) — тот файл, который
      Restore выберет через `saf_steps.saf_pick_file`;
    - вложенную SAF-подпапку с уникальным именем (`_orphan_subfolder`, тот же
      обход DocumentsUI-flake AT-BUG-005, что и TC-038), в которой уже лежит
      DECOY-файл (`_DECOY_ORPHAN_ID`, НЕ совпадает с ao3_id работы из backup).

    Почему decoy, а не сразу реальный orphan-файл (как в TC-038): `setDownloadFolderUri`
    (`SettingsScreen.kt:523-529`) запускает `scanForDownloads(silent=true)` АСИНХРОННО
    (`viewModelScope.launch`) — тап ALLOW возвращает управление раньше, чем эта
    корутина гарантированно успевает пройтись по каталогу. Если положить РЕАЛЬНЫЙ
    orphan-файл (тот же ao3Id, что в backup) заранее и просто выбрать папку, возможна
    гонка: корутина видит файл ПОЗЖЕ, чем ожидалось (или наоборот раньше — оба исхода
    небезопасны), и в любом случае `existing == null` в момент её скана (строки из
    backup ещё нет) добавляет STUB-строку (`added++`) с этим ao3Id ДО Restore — тогда
    `importFromUri` находит `id in existingIds` и ПРОПУСКАЕТ работу как дубликат
    (`skippedCount++`), тест ловит «Restored 0 works ... (1 works already existed)»
    вместо ожидаемого объединённого диалога (воспроизведено на первом прогоне этого
    теста). Decoy с ДРУГИМ ao3Id решает это детерминированно: раз что-то найдено
    (totalFound=1, added=1 для decoy), `scanForDownloads` показывает диалог «Scan
    complete» НЕСМОТРЯ на silent=true (подавляется только ветка «ничего не найдено») —
    само появление и закрытие этого диалога в тесте (см. `test_...`) СИНХРОННО
    доказывает, что асинхронная корутина уже отработала: только ПОСЛЕ этого в ту же
    папку кладётся уже РЕАЛЬНЫЙ orphan-файл (`app_steps.place_file_in_download_folder`),
    и никакой гонки для него уже нет — эта повторная корутина запускается ТОЛЬКО
    Restore (`importFromUri`, синхронно внутри одной корутины импорта).

    Возвращает `(work, subfolder)`. Единственный try/finally вокруг ВСЕГО setup —
    тот же паттерн гарантированного teardown, что у `orphan_download_relink_seeded`/
    `backup_file_workspace`."""
    app_steps.clean_state()
    work = W.RESTORE_SCAN_TARGET
    subfolder = _orphan_subfolder()
    remote_subdir = f"{_ORPHAN_DOWNLOAD_DIR}/{subfolder}"
    decoy_filename = f"decoy_{_DECOY_ORPHAN_ID}.html"
    backup_path = f"{_ORPHAN_DOWNLOAD_DIR}/{_RESTORE_SCAN_BACKUP_FILENAME}"
    payload = {
        "version": 2,
        "works": [
            {
                "ao3Id": work.ao3_id,
                "title": work.title,
                "author": work.author,
                "url": work.url,
                "rating": "SAVE",
                "comment": None,
                "fandom": work.fandom,
                "wordCount": work.word_count,
                "tags": None,
                "timestamp": 0,
            }
        ],
        "filterProfiles": [],
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="tc039_restore_scan_"))
    try:
        adb.shell(f"mkdir -p {remote_subdir}")
        local_decoy = tmp_dir / decoy_filename
        local_decoy.write_text(
            "<html><body>TC-039 decoy (sync marker) fixture</body></html>", encoding="utf-8"
        )
        adb.push_external(local_decoy, f"{remote_subdir}/{decoy_filename}")
        local_backup = tmp_dir / _RESTORE_SCAN_BACKUP_FILENAME
        local_backup.write_text(json.dumps(payload), encoding="utf-8")
        adb.push_external(local_backup, backup_path)
        yield work, subfolder
    finally:
        adb.shell(f'rm -rf "{remote_subdir}"')
        adb.shell(f'rm -f "{backup_path}"')
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.p2
@allure.id("TC-039")
@allure.title("Restore from backup сворачивает результат scanForOrphanedDownloads в один диалог")
def test_restore_folds_orphan_scan_into_single_dialog(restore_scan_workspace, driver):
    # Given Library пуста, backup-файл с 1 работой (без downloadPath) уже лежит в
    # Downloads root, готова SAF-подпапка загрузок с decoy-файлом (см. докстринг фикстуры)
    work, subfolder = restore_scan_workspace
    saf_steps.open_settings_scrolled_to(driver, "Pick")

    # And пользователь выбирает эту подпапку как папку загрузок — silent-скан находит
    # decoy-файл (чужой ao3Id) и показывает «Scan complete»; закрытие этого диалога —
    # детерминированное доказательство, что асинхронная корутина скана уже отработала
    # (см. докстринг фикстуры), НЕ часть Then этого кейса (кейс про диалог ПОСЛЕ Restore)
    saf_steps.tap_settings_action(driver, "Pick")
    saf_steps.saf_pick_folder(driver, f"Download/{subfolder}")
    settings_steps.assert_scan_complete_dialog(
        driver, expected_text="Found 1 files — relinked 0, added 1 new."
    )
    settings_steps.dismiss_scan_dialog(driver)

    # And ТОЛЬКО теперь (гонка исключена) в ту же папку кладётся РЕАЛЬНЫЙ orphan-файл
    # с тем же ao3_id, что и работа в backup
    remote_subdir = f"{_ORPHAN_DOWNLOAD_DIR}/{subfolder}"
    app_steps.place_file_in_download_folder(
        remote_subdir,
        _orphan_filename(work),
        "<html><body>TC-039 restore orphan fixture</body></html>",
    )

    # When пользователь выполняет «Restore from backup» и выбирает подготовленный файл
    saf_steps.rescroll_settings_to(driver, "Restore")
    saf_steps.tap_settings_action(driver, "Restore")

    # Then появляется РОВНО один диалог результата (не пустая проверка присутствия —
    # точный текст подтверждает, что restore- И scan-счётчики объединены: 1 работа
    # восстановлена, 0 filters (backup без профилей), 1 файл релинкован силами
    # scanForOrphanedDownloads внутри того же importFromUri, 0 добавлено новых —
    # SettingsScreen.kt:1186-1191)
    saf_steps.saf_pick_file(
        driver,
        _RESTORE_SCAN_BACKUP_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_restore_result_dialog,
            expected_text=(
                "Restored 1 works, 0 filters. Also relinked 1 and added 0 downloaded file(s)."
            ),
        ),
    )

    # And после закрытия первого диалога ВТОРОЙ диалог («Scan complete») НЕ
    # появляется — ключевой наблюдаемый факт кейса, явная проверка отсутствия, а
    # не только присутствия первого
    settings_steps.assert_no_scan_complete_dialog(driver)

    # And восстановленная работа в Library имеет заполненный downloadPath —
    # карточка на вкладке FAVORITE (SAVE) показывает open-иконку
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)
    library_steps.assert_open_icon_shown(driver, work.title)
