"""TC-021 — Backup -> Clear all ratings -> Restore возвращает исходные данные
(P0, area backup, risk R-01). Использует SAF-инфраструктуру AT-BUG-005
(`framework/screens/documents_ui.py`, `framework/steps/saf_steps.py`) — блокер
снят инкрементом 1 (probe `test_saf_infra_probe.py` зелёный 2x), см.
`bugs/AT-BUG-005.md`.

Полное покрытие полей (rating, comment, tags, fandom, word_count) — заметка
в теле TC-021 про то, что `seed_db.py` не умеет comment/tags, устарела:
`seed_with_comment` уже поддерживает оба поля, используется здесь для всех 5
работ (не урезанный вариант "только rating/fandom/word_count").
"""
from __future__ import annotations

import json
from functools import partial

import allure
import pytest

from framework.core import adb
from framework.data import works as W
from framework.steps import app_steps, backup_steps, library_steps, saf_steps, settings_steps

_EXPORT_FILENAME = "tc021_backup_restore.json"
_DOWNLOAD_DIR = "/sdcard/Download"

# Одна работа на каждый рейтинг (см. `seeded_library` в conftest.py), дополненные
# непустыми comment/tags через `seed_with_comment` — полное покрытие полей §9.
_ROWS: list[tuple] = [
    (W.LOVED, "SAVE", "Reread this every winter.", json.dumps(["fluff", "found-family"])),
    (W.KUDOSED, "LIKE", "Left kudos, would read again.", json.dumps(["angst"])),
    (W.READ, "READ", "Finished on a Sunday.", json.dumps(["slow-burn", "canon-divergent"])),
    (W.PENDING, "PENDING", "Queued for the long weekend.", json.dumps(["to-read"])),
    (W.DISLIKED, "DISLIKE", "Not for me, DNF at chapter 3.", json.dumps(["dnf"])),
]

_EXPECTED_AFTER_RESTORE = {
    work.ao3_id: {
        "rating": rating,
        "comment": comment,
        "tags": json.loads(tags_json),
        "fandom": work.fandom,
        "word_count": work.word_count,
    }
    for work, rating, comment, tags_json in _ROWS
}


@pytest.fixture()
def backup_restore_seeded():
    """5 работ `works.ALL` — по одной на каждый рейтинг, каждая с непустыми
    comment/tags (`seed_with_comment`). Сидинг до старта сессии Appium — тот же
    порядок, что и `seeded_library`/остальные фикстуры данных в conftest.py
    (иначе драйвер успевает запустить приложение раньше сидинга)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(w, r, c, t) for w, r, c, t in _ROWS])
    yield


@pytest.fixture()
def backup_file_workspace():
    """Целевой файл экспорта отсутствует ДО и ПОСЛЕ теста — SAF CreateDocument
    создаёт его заново на каждом прогоне (детерминированное имя, не
    предложенное приложением `ao3_backup_$date.json`). Единственный try/finally
    вокруг ВСЕГО (включая setup) — тот же паттерн гарантированного teardown, что
    `saf_probe_workspace` в `test_saf_infra_probe.py` (AT-BUG-005, инкремент 1,
    attempt 2): teardown обязан покрывать любую точку отказа, не только yield."""
    adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')
    try:
        yield
    finally:
        adb.shell(f'rm -f "{_DOWNLOAD_DIR}/{_EXPORT_FILENAME}"')


@pytest.mark.p0
@allure.id("TC-021")
@allure.title("Backup -> Clear all ratings -> Restore возвращает исходные данные")
def test_backup_clear_restore_returns_original_data(
    backup_restore_seeded, backup_file_workspace, driver
):
    # Given приложение с засеянными работами: по одной на каждый рейтинг, с
    # непустыми comment/tags/fandom/word_count
    saf_steps.open_settings_scrolled_to(driver, "Back up")

    # When пользователь выполняет «Back up data», выбирает файл через SAF
    # (CreateDocument, root Downloads, детерминированное имя), дожидается
    # результата приложения (диалог «Backup created» с корректным count)
    saf_steps.tap_settings_action(driver, "Back up")
    saf_steps.saf_save_document(
        driver,
        filename=_EXPORT_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_backup_created_dialog,
            expected_text=f"Backed up {len(_ROWS)} works, 0 filters.",
        ),
    )

    # And выполняет «Clear all ratings» и подтверждает диалог
    settings_steps.clear_all_ratings(driver)
    settings_steps.assert_no_ratings()

    # And выполняет «Restore from backup», выбирает тот же файл (GetContent,
    # тот же root Downloads) — повторный заход на Settings в той же сессии, без
    # повторной проверки WebView (см. saf_steps.rescroll_settings_to)
    saf_steps.rescroll_settings_to(driver, "Restore")
    saf_steps.tap_settings_action(driver, "Restore")

    # Then после Restore появляется диалог результата (counts, без ошибки)
    saf_steps.saf_pick_file(
        driver,
        _EXPORT_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_restore_result_dialog,
            expected_text=f"Restored {len(_ROWS)} works, 0 filters.",
        ),
    )

    # And количество работ в Library по каждой рейтинговой вкладке совпадает с
    # исходным (до Clear) — по одной работе на вкладку, ничего не потеряно
    app_steps.open_tab(driver, "Library")
    for work, rating, _comment, _tags in _ROWS:
        library_steps.assert_work_in_tab(driver, rating, work.title)

    # And для каждой восстановленной работы поля rating/comment/tags/fandom/
    # word_count совпадают с исходными значениями до Backup (сверка через Room,
    # не через локале-зависимый текст карточки — см. backup_steps.py)
    backup_steps.assert_restored_fields_match(_EXPECTED_AFTER_RESTORE)
