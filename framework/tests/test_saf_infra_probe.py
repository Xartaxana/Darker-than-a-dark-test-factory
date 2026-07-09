"""Инфраструктурные пробы AT-BUG-005, инкремент 1: доказывают, что системный SAF
picker (DocumentsUI) автоматизируется штатной UiAutomator2-сессией через
`framework/screens/documents_ui.py` + `framework/steps/saf_steps.py`.

ВАЖНО: тесты этого модуля — НЕ автоматизация TC-021 (P0, backup/restore,
`test-cases/backup/TC-021.md`). Они доказывают пригодность инфраструктуры на
трёх поверхностях picker'а (CreateDocument/GetContent/OpenDocumentTree) по
образцу `test_replay_infra_probe.py` (AT-BUG-004, инкремент 3). Полная сборка
сценария TC-021 (Backup -> Clear all ratings -> Restore) — задача
test-automator ПОСЛЕ снятия блокера; критерий Fixed в `bugs/AT-BUG-005.md`
закрывается зелёным прогоном самого TC-021, не этим модулем. `@allure.id`
здесь намеренно НЕ использует формат "TC-xxx" (см. `scripts/arch_check.py`
§Правило 2) — чтобы не создавать ложное впечатление, что кейс автоматизирован.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import allure
import pytest

from framework.config import settings
from framework.core import adb
from framework.steps import app_steps, library_steps, saf_steps

_DOWNLOAD_DIR = "/sdcard/Download"
_EXPORT_FILENAME = "at_bug_005_export_probe.json"
_IMPORT_FILENAME = "at_bug_005_import_fixture.json"
_PROBE_SUBFOLDER = "at_bug_005_saf_probe"
_IMPORT_AO3_ID = "999005"
_IMPORT_TITLE = "AT-BUG-005 probe work"

# Схема — SettingsViewModel.importFromUri (SettingsScreen.kt:321-405): объект
# {"version", "works": [...], "filterProfiles": [...]}, поля work'а — ao3Id (обязательное)
# + опциональные title/author/url/rating/comment/fandom/wordCount/tags/timestamp.
_IMPORT_FIXTURE_CONTENT = {
    "version": 2,
    "works": [
        {
            "ao3Id": _IMPORT_AO3_ID,
            "title": _IMPORT_TITLE,
            "author": "SAF Probe",
            "url": f"https://archiveofourown.org/works/{_IMPORT_AO3_ID}",
            "rating": "READ",
            "comment": None,
            "fandom": None,
            "wordCount": None,
            "tags": None,
            "timestamp": 1720000000000,
            "downloadFile": None,
        }
    ],
    "filterProfiles": [],
}


def _adb_push(local_path: Path, remote_path: str) -> None:
    """Прямой `adb push` (не `framework.core.adb.push_app_file` — тот кладёт файл в
    приватную песочницу приложения через `run-as`; здесь нужен публичный `/sdcard`,
    видимый системному picker'у, а не самому приложению)."""
    cp = subprocess.run(
        [settings.ADB, "-s", settings.DEVICE_NAME, "push", str(local_path), remote_path],
        capture_output=True, text=True,
    )
    assert cp.returncode == 0, f"adb push не выполнился: {cp.stdout}{cp.stderr}"


def _rm_download(name: str) -> None:
    adb.shell(f'rm -rf "{_DOWNLOAD_DIR}/{name}"')


@pytest.fixture()
def saf_probe_workspace():
    """Готовит на устройстве (adb-шеллом, ДО открытия любого пикера — детерминизм,
    AT-BUG-005 п.4 спеки фикса) артефакты, нужные трём сценариям:
    - файл-фикстуру для импорта (`_IMPORT_FILENAME`, валиден по схеме
      `SettingsViewModel.importFromUri`);
    - подпапку `_PROBE_SUBFOLDER` внутри Download для OpenDocumentTree (сам
      "Download" системная защита приватности не даёт выбрать — см. докстринг
      `saf_steps.saf_pick_folder`).

    Тот же паттерн гарантированного teardown, что и фикстура `replay` в
    `conftest.py`: ВЕСЬ device-setup (mkdir + push) и `yield` — внутри ОДНОГО
    `try`, единственный `finally` чистит все три цели БЕЗУСЛОВНО (`rm -rf`
    идемпотентен — не страшно звать на то, что не успело создаться). Раньше
    push был вне общего try/finally — если mkdir отрабатывал, а push падал (до
    yield), собственный finally уборки никогда не выполнялся и подпапка
    утекала на устройство (тот же класс, что AT-BUG-004 инкремент 2: teardown
    обязан покрывать ЛЮБУЮ точку отказа setup, не только yield) — исправлено."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(_IMPORT_FIXTURE_CONTENT, f)
        local_fixture = Path(f.name)
    try:
        adb.shell(f"mkdir -p {_DOWNLOAD_DIR}/{_PROBE_SUBFOLDER}")
        _adb_push(local_fixture, f"{_DOWNLOAD_DIR}/{_IMPORT_FILENAME}")
        yield
    finally:
        local_fixture.unlink(missing_ok=True)
        _rm_download(_EXPORT_FILENAME)
        _rm_download(_IMPORT_FILENAME)
        _rm_download(_PROBE_SUBFOLDER)


@pytest.mark.p1
@allure.id("AT-BUG-005-saf-export-probe")
@allure.title("Проба: экспорт бэкапа через системный CreateDocument picker (не автоматизация TC-021)")
def test_saf_export_via_create_document(saf_probe_workspace, clean_app, driver):
    # Given чистое приложение (без рейтингов — бэкап будет пустым, это не важно для
    # пробы), открыт Settings, докручено до "Back up"
    saf_steps.open_settings_scrolled_to(driver, "Back up")

    # When нажата "Back up"; в системном CreateDocument picker'е явно выбран root
    # Downloads, файл переименован в детерминированное имя, SAVE
    saf_steps.tap_settings_action(driver, "Back up")
    saf_steps.saf_save_document(driver, filename=_EXPORT_FILENAME)

    # Then файл реально существует на устройстве и содержит валидный JSON ожидаемой
    # схемы (SettingsViewModel.exportToUri) — сквозная проверка ROUND-TRIP через
    # систему, не мок picker'а
    out = adb.shell(f'cat "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')
    data = json.loads(out)
    assert data.get("version") == 2
    assert "works" in data and "filterProfiles" in data


@pytest.mark.p1
@allure.id("AT-BUG-005-saf-import-probe")
@allure.title("Проба: импорт бэкапа через системный GetContent picker (не автоматизация TC-021)")
def test_saf_import_via_get_content(saf_probe_workspace, clean_app, driver):
    # Given чистое приложение, файл-фикстура с одной работой уже на устройстве
    # (saf_probe_workspace, ДО сессии Appium), открыт Settings, докручено до "Restore"
    saf_steps.open_settings_scrolled_to(driver, "Restore")

    # When нажата "Restore"; в системном GetContent picker'е явно выбран root
    # Downloads и файл-фикстура
    saf_steps.tap_settings_action(driver, "Restore")
    saf_steps.saf_pick_file(driver, _IMPORT_FILENAME)

    # Then приложение реально приняло данные — работа из фикстуры видна в Library на
    # вкладке READ (наблюдаемое состояние приложения после round-trip через Room,
    # а не пересказ текста уже закрытого диалога-результата)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "READ", _IMPORT_TITLE)


@pytest.mark.p1
@allure.id("AT-BUG-005-saf-folder-probe")
@allure.title("Проба: выбор папки загрузок через системный OpenDocumentTree picker (не автоматизация TC-021)")
def test_saf_pick_download_folder(saf_probe_workspace, clean_app, driver):
    # Given чистое приложение, подпапка Download/<probe> уже создана на устройстве
    # (saf_probe_workspace), открыт Settings, докручено до "Pick" (Download folder)
    saf_steps.open_settings_scrolled_to(driver, "Pick")

    # When нажата "Pick"; в системном OpenDocumentTree picker'е выбрана ВЛОЖЕННАЯ
    # подпапка (сам "Download" системная защита приватности выбрать не даёт),
    # подтверждены USE THIS FOLDER и системный ALLOW
    saf_steps.tap_settings_action(driver, "Pick")
    saf_steps.saf_pick_folder(driver, f"Download/{_PROBE_SUBFOLDER}")

    # Then лейбл "Download folder" в Settings отражает выбранную папку — persisted
    # URI-грант реально применился, не только сам факт закрытия picker'а
    saf_steps.assert_download_folder_label(driver, _PROBE_SUBFOLDER)
