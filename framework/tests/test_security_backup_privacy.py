"""TC-104 (security/backup-privacy): allowBackup сопровождён явным ограничением
области (static, манифест) + SAF-экспортный JSON не получает мир-читаемые
права (behavioral, поведение).

**Независимость static/behavioral (misc-batch-0722, обязательное требование
дизайна кейса):** оформлены ДВУМЯ отдельными тест-функциями с ОДНИМ
`@allure.id("TC-104")` — падение манифест-инспекции не маскирует поведенческую
проверку и наоборот, оба результата собираются и диагностируются независимо.

Static-часть — build-level, не требует Appium-сессии; behavioral-часть
переиспользует SAF-инфраструктуру AT-BUG-005 (`saf_steps.py`, `backup_steps.py`)
и тот же путь SAF-экспорта, что TC-021 (`test_backup_restore.py`), с ОТДЕЛЬНЫМ
именем файла и меньшим сидингом (не дублирует TC-021 — та проверяет round-trip
сохранности полей, эта — приватность/права доступа экспортированного артефакта
и манифест-декларацию области бэкапа)."""
from __future__ import annotations

from functools import partial

import allure
import pytest

from framework.core import adb
from framework.data import works as W
from framework.steps import app_steps, backup_steps, saf_steps, security_steps

_EXPORT_FILENAME = "tc104_backup_privacy.json"
_DOWNLOAD_DIR = "/sdcard/Download"


@pytest.mark.p1
@allure.id("TC-104")
@allure.title("Приватность бэкапа: android:allowBackup=true сопровождён явным ограничением области (static)")
def test_backup_privacy_manifest_scope_declared():
    # Given APK тестируемой сборки доступен на диске (build-артефакт)
    # When манифест инспектируется статически (тот же приём, что TC-100/101)
    tree = security_steps.dump_manifest_tree()

    # Then android:allowBackup=true сопровождён fullBackupContent ИЛИ
    # dataExtractionRules — область бэкапа явно ограничена, не голый allowBackup
    security_steps.assert_backup_scope_declared(tree)


@pytest.fixture()
def backup_privacy_seeded():
    """Минимальный сидинг (1 работа) — этому тесту не нужен полный набор TC-021
    (round-trip сохранности полей), только сам факт экспорта существующего файла."""
    app_steps.clean_state()
    app_steps.seed_library([(W.LOVED, "SAVE")])
    yield


@pytest.fixture()
def backup_privacy_workspace():
    """Целевой файл экспорта отсутствует ДО и ПОСЛЕ теста — тот же паттерн
    гарантированного teardown, что `backup_file_workspace` в `test_backup_restore.py`
    (TC-021), ОТДЕЛЬНОЕ имя файла — не пересекается с TC-021."""
    adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')
    try:
        yield
    finally:
        adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')


@pytest.mark.p1
@allure.id("TC-104")
@allure.title("Приватность бэкапа: SAF-экспортный JSON не получает мир-читаемые права (behavioral)")
def test_backup_privacy_saf_export_file_permissions_not_widened(
    backup_privacy_seeded, backup_privacy_workspace, driver,
):
    # Given приложение с засеянной работой, SAF file picker доступен
    saf_steps.open_settings_scrolled_to(driver, "Back up")

    # When пользователь выполняет «Back up data», выбирает файл через SAF,
    # дожидается результата
    saf_steps.tap_settings_action(driver, "Back up")
    saf_steps.saf_save_document(
        driver,
        filename=_EXPORT_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_backup_created_dialog,
            expected_text="Backed up 1 works, 0 filters.",
        ),
    )

    # Then созданный SAF-экспортный файл НЕ имеет прав доступа шире контрольного
    # файла, положенного в ту же директорию — приложение не расширяет права файла
    # вручную сверх того, что даёт сам SAF/файловая система по умолчанию
    security_steps.assert_saf_export_permissions_not_widened(_DOWNLOAD_DIR, _EXPORT_FILENAME)
