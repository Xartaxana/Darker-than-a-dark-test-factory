"""Бизнес-шаги сценария Backup -> Clear all ratings -> Restore (TC-021, P0,
area backup, risk R-01). Использует SAF-инфраструктуру AT-BUG-005
(`framework/steps/saf_steps.py`, `framework/screens/documents_ui.py`) через
колбэк `before_dismiss`: эта инфраструктура сама закрывает generic-диалог
результата ("OK") сразу после появления — здесь нужно СНАЧАЛА прочитать его
содержимое (заголовок/текст с counts), поэтому функции ниже передаются в
`saf_steps.saf_save_document`/`saf_pick_file` как `before_dismiss`, вызываются
ДО тапа по OK (см. `saf_steps._dismiss_ok_dialog`).

Сверка полей rating/comment/tags/fandom/word_count после Restore идёт через
`seed_db.read_work_ratings()` (прямое чтение Room, см. докстринг функции) — не
через текст карточки Library (`stats`-строка на WorkCard комбинирует fandom +
word_count в одну Text-ноду с локале-зависимым форматированием числа,
`"%,d".format(wc)` без явного Locale в LibraryScreen.kt — сверка через БД не
зависит от того, как именно рантайм отформатирует разделитель тысяч)."""
from __future__ import annotations

import allure

from framework.data import seed_db
from framework.screens.base_screen import BaseScreen


@allure.step("Then появился диалог «Backup created» с текстом «{expected_text}»")
def assert_backup_created_dialog(driver, expected_text: str) -> None:
    b = BaseScreen(driver)
    assert b.is_present(b.by_text("Backup created"), timeout=2), (
        "диалог результата экспорта не «Backup created» — возможно, экспорт завершился "
        "ошибкой (Backup failed)"
    )
    assert b.is_present(b.by_text(expected_text), timeout=2), (
        f"текст результата Backup не совпал с ожидаемым «{expected_text}»"
    )


@allure.step("Then появился диалог «Backup restored» с текстом «{expected_text}»")
def assert_restore_result_dialog(driver, expected_text: str) -> None:
    b = BaseScreen(driver)
    assert b.is_present(b.by_text("Backup restored"), timeout=2), (
        "диалог результата restore не «Backup restored» — возможно, restore завершился "
        "ошибкой (Restore failed)"
    )
    assert b.is_present(b.by_text(expected_text), timeout=2), (
        f"текст результата Restore не совпал с ожидаемым «{expected_text}»"
    )


@allure.step("Then rating/comment/tags/fandom/word_count всех восстановленных работ совпадают с исходными")
def assert_restored_fields_match(expected: dict[str, dict]) -> None:
    """`expected`: ao3Id -> {"rating", "comment", "tags", "fandom", "word_count"} —
    те же поля и типы, что возвращает `seed_db.read_work_ratings()` (`tags` — список
    строк или `None`). Проверяет и точный набор ao3Id (ничего не потеряно/не
    задублировано), и полное совпадение полей на каждую строку."""
    actual = seed_db.read_work_ratings()
    assert len(actual) == len(expected), (
        f"ожидали {len(expected)} строк в work_ratings после Restore, реально "
        f"{len(actual)}: {sorted(actual)}"
    )
    missing = [aid for aid in expected if aid not in actual]
    assert not missing, f"work_ratings не содержит ожидаемые ao3Id после Restore: {missing}"
    mismatches = {
        aid: {"expected": expected[aid], "actual": actual[aid]}
        for aid in expected
        if actual[aid] != expected[aid]
    }
    assert not mismatches, f"поля отличаются от исходных после Restore: {mismatches}"
