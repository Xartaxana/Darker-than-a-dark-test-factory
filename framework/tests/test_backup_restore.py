"""TC-021 — Backup -> Clear all ratings -> Restore возвращает исходные данные
(P0, area backup, risk R-01). Использует SAF-инфраструктуру AT-BUG-005
(`framework/screens/documents_ui.py`, `framework/steps/saf_steps.py`) — блокер
снят инкрементом 1 (probe `test_saf_infra_probe.py` зелёный 2x), см.
`bugs/AT-BUG-005.md`.

Полное покрытие полей (rating, comment, tags, fandom, word_count) — заметка
в теле TC-021 про то, что `seed_db.py` не умеет comment/tags, устарела:
`seed_with_comment` уже поддерживает оба поля, используется здесь для всех 5
работ (не урезанный вариант "только rating/fandom/word_count").

Инвариант C4 (ревью 2026-07-14, замечание 1): формат бэкапа несёт
`{"version":2,"works":[…],"filterProfiles":[…]}` — round-trip обязан сохранять
ОБА множества, не только works. Один filter-профиль засеян через
`seed_db.seed_filter_profiles` (используется для TC-041/TC-042) ДО Appium-сессии
и сверяется через прямое чтение Room (`seed_db.read_filter_profiles()`,
`backup_steps.assert_filter_profiles_match`) после Restore.

ВАЖНО про счётчик «N filters» в диалоге Restore: «Clear all ratings» очищает
ТОЛЬКО `work_ratings` (`RatingRepository.clearAllRatings` -> `workDao.deleteAll()`,
см. `app-under-test/.../SettingsScreen.kt:503`) — `filter_profiles` этим действием
не затрагивается. Поэтому на шаге Restore профиль уже присутствует в Room
(`existingProfileIds` при импорте его находит) и корректно ПРОПУСКАЕТСЯ как
дубликат (`SettingsScreen.kt:373-388`, `id in existingProfileIds -> continue`):
диалог «Backup restored» показывает `0 filters` (ничего НОВОГО не импортировано),
тогда как диалог «Backup created» показывает `1 filters` (то, что было в Room на
момент экспорта). Это не баг: инвариант — «множество профилей после round-trip
== исходному множеству» (ничего не потеряно/не добавлено/не задублировано), а
НЕ «оба диалога показывают одно и то же число» — числа считают разные вещи
(экспортировано vs новых-импортировано). Итоговая Room-сверка
(`assert_filter_profiles_match`) проверяет именно инвариант, а не текст диалога.
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

# Один filter-профиль (сохранённый поиск) — покрытие round-trip filterProfiles
# из формата бэкапа (замечание ревью 1, C4). Имя/queryString — идентичность
# профиля для сверки (см. `backup_steps.assert_filter_profiles_match`), `id`
# генерируется сидингом и вызывающему коду не виден и не нужен.
_FILTER_PROFILE = ("TC-021 fluff search", "work_search%5Bquery%5D=fluff")
_EXPECTED_FILTER_PROFILES_AFTER_RESTORE = [
    {"name": _FILTER_PROFILE[0], "queryString": _FILTER_PROFILE[1]},
]


@pytest.fixture()
def backup_restore_seeded():
    """5 работ `works.ALL` — по одной на каждый рейтинг, каждая с непустыми
    comment/tags (`seed_with_comment`), плюс 1 filter-профиль
    (`seed_filter_profiles`). Сидинг до старта сессии Appium — тот же порядок,
    что и `seeded_library`/остальные фикстуры данных в conftest.py (иначе драйвер
    успевает запустить приложение раньше сидинга)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(w, r, c, t) for w, r, c, t in _ROWS])
    app_steps.seed_filter_profiles([_FILTER_PROFILE])
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
    # непустыми comment/tags/fandom/word_count, и 1 сохранённым filter-профилем
    saf_steps.open_settings_scrolled_to(driver, "Back up")

    # When пользователь выполняет «Back up data», выбирает файл через SAF
    # (CreateDocument, root Downloads, детерминированное имя), дожидается
    # результата приложения (диалог «Backup created» с корректным count работ
    # И профилей — 1 filters, ровно столько, сколько засеяно)
    saf_steps.tap_settings_action(driver, "Back up")
    saf_steps.saf_save_document(
        driver,
        filename=_EXPORT_FILENAME,
        before_dismiss=partial(
            backup_steps.assert_backup_created_dialog,
            expected_text=f"Backed up {len(_ROWS)} works, 1 filters.",
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

    # Then после Restore появляется диалог результата (counts, без ошибки).
    # «0 filters» здесь ОЖИДАЕМО, не пробел покрытия: «Clear all ratings» не
    # трогает `filter_profiles`, поэтому профиль уже есть в Room на момент
    # Restore и корректно пропускается как дубликат (см. докстринг модуля) —
    # инвариант проверяется ниже прямым чтением Room, а не этим текстом.
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

    # And сохранённый filter-профиль присутствует после Restore, без потери и
    # без дублирования (инвариант C4 распространяется на {поля работы} ∪
    # {filterProfiles}, не только на works)
    backup_steps.assert_filter_profiles_match(_EXPECTED_FILTER_PROFILES_AFTER_RESTORE)
