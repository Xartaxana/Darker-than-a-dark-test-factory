"""TC-105 (security/logcat-leak): скан logcat на утечку чувствительных данных
(cookie/session/токены/локальные пути приложения) при представительном
smoke-прогоне.

Переиспользует буквально те же примитивы, что TC-098 (`adb.logcat_clear`/
`logcat_dump`, `perf_steps.logcat_clear_before_scenario`) и тот же
представительный smoke-путь (TC-001/006/007), РАСШИРЕННЫЙ шагом экспорта
бэкапа через SAF (TC-021) — так же явно указано в Then кейса. Не изобретает
новый маршрут (misc-batch-0722)."""
from __future__ import annotations

from functools import partial

import allure
import pytest

from framework.core import adb
from framework.data import works as W
from framework.steps import app_steps, backup_steps, library_steps, perf_steps, rating_steps, saf_steps, security_steps

_EXPORT_FILENAME = "tc105_logcat_smoke_backup.json"
_DOWNLOAD_DIR = "/sdcard/Download"


@pytest.fixture()
def logcat_smoke_backup_workspace():
    """Тот же паттерн гарантированного teardown, что `backup_file_workspace`
    (TC-021)/`backup_privacy_workspace` (TC-104) — ОТДЕЛЬНОЕ имя файла."""
    adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')
    try:
        yield
    finally:
        adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')


@pytest.mark.p1
@pytest.mark.live
@allure.id("TC-105")
@allure.title("Отсутствие чувствительных данных (cookie/session/токены/локальные пути) в logcat при представительном smoke-прогоне")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_logcat_has_no_sensitive_data_during_smoke_path(
    placeholder_seeded_work, logcat_smoke_backup_workspace, driver,
):
    work = placeholder_seeded_work
    # Given приложение запущено с чистыми данными (placeholder_seeded_work), logcat
    # очищен непосредственно перед началом сценария (тот же приём, что TC-098)
    perf_steps.logcat_clear_before_scenario()

    # When пользователь проходит представительный smoke-путь: запуск → Browse
    # (AO3-страница, TC-001)
    app_steps.wait_app_ready(driver)

    # → простановка рейтинга на существующей засеянной работе (TC-007: панель
    # RatingMenu рендерится на вкладке Browse)
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.rate_current_work(driver, "SAVE")
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # → Settings → экспорт бэкапа через SAF (TC-021, тот же путь SAF-экспорта).
    # `rescroll_settings_to` (не `open_settings_scrolled_to`): к этому шагу
    # приложение уже прошло Browse/Library (не свежий старт) — WebView этой
    # вкладки Browse больше не в дереве, `wait_ui_ready` внутри
    # `open_settings_scrolled_to` таймаутил бы (см. докстринг `rescroll_settings_to`).
    app_steps.open_tab(driver, "Settings")
    saf_steps.rescroll_settings_to(driver, "Back up")
    saf_steps.tap_settings_action(driver, "Back up")
    saf_steps.saf_save_document(
        driver,
        filename=_EXPORT_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_backup_created_dialog,
            expected_text="Backed up 1 works, 0 filters.",
        ),
    )

    # Then захваченный logcat за время прогона не содержит cookie/session-данных,
    # признаков токенов/сессионных идентификаторов, и полных локальных путей
    # приложения в прикладных строках (best-effort, E4-min — не полный аудит, §8)
    security_steps.assert_logcat_has_no_sensitive_data()
