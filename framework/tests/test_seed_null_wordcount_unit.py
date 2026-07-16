"""Device-free юнит-проба сидинга NULL `wordCount` в `work_ratings` — AT-BUG-010.

НЕ автоматизация TC-031 (тот требует устройства + Appium: сортировку в UI). Эта
проба доказывает только сам механизм вставки/чтения: `seed_db._insert_rows` на
временной локальной sqlite-БД со схемой приложения, без adb/Appium/эмулятора —
DEVICE-FREE задача (эмулятор намеренно не поднимался, ESC-001 этой задачи не
касается), тот же приём, что `test_seed_filter_profiles_unit.py` (AT-BUG-006,
инкремент 1): локальная фикстура переопределяет session-scoped
`_ensure_app_installed` из `conftest.py`, чтобы не дёргать `adb pm list packages`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import allure
import pytest

from framework.data.seed_db import _insert_rows
from framework.data.works import Work

# Схема — копия актуальной (v7, MIGRATION_6_7) `work_ratings` из
# `app-under-test/.../data/db/AppDatabase.kt` (см. MIGRATION_5_6 CREATE TABLE +
# MIGRATION_6_7 ALTER TABLE ADD COLUMN tags): все поля, кроме ao3Id/title/author/
# url/timestamp, nullable — включая `wordCount INTEGER`.
_CREATE_WORK_RATINGS_SQL = """
    CREATE TABLE work_ratings (
        ao3Id TEXT NOT NULL PRIMARY KEY,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        url TEXT NOT NULL,
        rating TEXT,
        timestamp INTEGER NOT NULL,
        fandom TEXT,
        wordCount INTEGER,
        comment TEXT,
        downloadPath TEXT,
        tags TEXT
    )
"""


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. docstring модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture()
def work_ratings_db(tmp_path: Path) -> Path:
    """Временная sqlite-БД с таблицей `work_ratings`, созданной по схеме
    приложения (см. `_CREATE_WORK_RATINGS_SQL`)."""
    db = tmp_path / "work_ratings_unit.db"
    con = sqlite3.connect(db)
    con.execute(_CREATE_WORK_RATINGS_SQL)
    con.commit()
    con.close()
    return db


def _select_word_count(db: Path, ao3_id: str):
    """Читает `wordCount` тем же способом, что `read_work_ratings()`
    (`SELECT ... wordCount FROM work_ratings`, доступ по `sqlite3.Row["wordCount"]`)
    — без обращения к устройству, само чтение (`_pull_baseline`) здесь не тестируется."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.execute("SELECT wordCount FROM work_ratings WHERE ao3Id = ?", (ao3_id,))
    row = cur.fetchone()
    con.close()
    return row["wordCount"] if row is not None else None


@pytest.mark.p3
@allure.id("AT-BUG-010-seed-null-wordcount-insert")
@allure.title("Проба: _insert_rows кладёт NULL для wordCount=None (device-free)")
def test_insert_rows_null_word_count_stores_null(work_ratings_db):
    # Given работа с word_count=None (граница TC-031: work без word_count) и две
    # работы с валидным word_count — тот же состав, что Given TC-031 (800, 4200, null)
    with_wc_low = Work("900000801", "With word count low", "author_low", "Fandom", 800)
    with_wc_high = Work("900000802", "With word count high", "author_high", "Fandom", 4200)
    null_wc = Work("900000031", "Null word count", "author_null", "Fandom", None)

    # When все три засеяны с одним рейтингом через _insert_rows (как seed()/seed_library)
    _insert_rows(
        work_ratings_db,
        [(with_wc_low, "PENDING"), (with_wc_high, "PENDING"), (null_wc, "PENDING")],
    )

    # Then у null_wc в БД лежит NULL, у остальных — исходные значения (не 0, не искажено)
    assert _select_word_count(work_ratings_db, null_wc.ao3_id) is None
    assert _select_word_count(work_ratings_db, with_wc_low.ao3_id) == 800
    assert _select_word_count(work_ratings_db, with_wc_high.ao3_id) == 4200


@pytest.mark.p3
@allure.id("AT-BUG-010-seed-null-wordcount-replace")
@allure.title("Проба: INSERT OR REPLACE не искажает NULL wordCount при повторной вставке (device-free)")
def test_insert_rows_null_word_count_survives_replace(work_ratings_db):
    # Given работа уже засеяна с валидным word_count
    work = Work("900000803", "Replaced work", "author_r", "Fandom", 1500)
    _insert_rows(work_ratings_db, [(work, "SAVE")])
    assert _select_word_count(work_ratings_db, work.ao3_id) == 1500

    # When тот же ao3Id пересеян с word_count=None (INSERT OR REPLACE)
    work_null = Work(work.ao3_id, work.title, work.author, work.fandom, None)
    _insert_rows(work_ratings_db, [(work_null, "SAVE")])

    # Then значение заменено на NULL, а не осталось прежним/не превратилось в 0
    assert _select_word_count(work_ratings_db, work.ao3_id) is None
