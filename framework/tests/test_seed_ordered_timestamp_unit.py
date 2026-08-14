"""Device-free юнит-проба `seed_db._insert_rows_ordered`/`_insert_rows_full_ordered`
(rework attempt 2, критик-вход приёмки TC-186-188, блокер B4) — доказывает
САМ механизм, что критик указал как непокрытый: КАЖДАЯ строка списка
получает СТРОГО возрастающий `timestamp` по своей ПОЗИЦИИ (не по порядку
вставки/времени вызова), и `ORDER BY timestamp DESC` (реальный запрос
`WorkRatingDao.getWorksWithEmptyTitle`) отдаёт строки в порядке, ОБРАТНОМ
порядку в списке — последняя строка списка первая.

НЕ автоматизация TC-187/TC-062 (те требуют устройства + Appium: реального
UI-эффекта очереди). Эта проба — тот же приём, что
`test_seed_null_wordcount_unit.py` (AT-BUG-010): локальная sqlite-БД со
схемой приложения, без adb/Appium/эмулятора, `_ensure_app_installed`
переопределена в no-op.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import allure
import pytest

from framework.data.seed_db import _insert_rows_full_ordered, _insert_rows_ordered
from framework.data.works import Work

# Схема — та же копия, что test_seed_null_wordcount_unit.py (актуальная v7,
# MIGRATION_6_7 в app-under-test/.../data/db/AppDatabase.kt).
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
    """Переопределяет device-фикстуру conftest.py (см. docstring модуля) —
    эта проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture()
def work_ratings_db(tmp_path: Path) -> Path:
    db = tmp_path / "work_ratings_ordered_unit.db"
    con = sqlite3.connect(db)
    con.execute(_CREATE_WORK_RATINGS_SQL)
    con.commit()
    con.close()
    return db


def _select_ordered_ids(db: Path) -> list[str]:
    """Та же форма запроса, что `WorkRatingDao.getWorksWithEmptyTitle`
    (`ORDER BY timestamp DESC`, app-under-test :39) — реальный оракул
    порядка обработки очереди TC-187."""
    con = sqlite3.connect(db)
    cur = con.execute("SELECT ao3Id FROM work_ratings ORDER BY timestamp DESC")
    ids = [row[0] for row in cur]
    con.close()
    return ids


def _select_timestamps(db: Path) -> dict[str, int]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.execute("SELECT ao3Id, timestamp FROM work_ratings")
    out = {row["ao3Id"]: row["timestamp"] for row in cur}
    con.close()
    return out


@pytest.mark.p3
@allure.id("AT-BUG-069-insert-rows-ordered-monotonic")
@allure.title("Проба: _insert_rows_ordered даёт СТРОГО возрастающий timestamp по позиции в списке (device-free)")
def test_insert_rows_ordered_strictly_increasing_by_position(work_ratings_db):
    # Given три работы D, E — позиция в списке НЕ совпадает с алфавитным/
    # лексикографическим порядком ao3_id (E меньше по ao3_id, но идёт ПЕРВОЙ
    # в списке — то же расположение, что TC-187: E первая (queue[1], не
    # тронута), D вторая (queue[0], обрабатывается ДО Stop))
    work_e = Work("900000502", "", "", "Test Fandom", None)
    work_d = Work("900000501", "", "", "Test Fandom", None)

    # When обе засеяны ОДНИМ вызовом _insert_rows_ordered, E первой в списке
    _insert_rows_ordered(work_ratings_db, [(work_e, "PENDING"), (work_d, "PENDING")])

    # Then timestamp растёт СТРОГО по позиции (не по ao3_id/алфавиту):
    # E (индекс 0) < D (индекс 1)
    ts = _select_timestamps(work_ratings_db)
    assert ts[work_e.ao3_id] < ts[work_d.ao3_id], ts

    # And ORDER BY timestamp DESC (реальный запрос очереди) отдаёт D ПЕРВОЙ
    # (queue[0], обрабатывается ДО Stop), E ВТОРОЙ (queue[1], не тронута) —
    # ровно инверсия порядка в списке, а не порядок вставки/алфавит
    assert _select_ordered_ids(work_ratings_db) == [work_d.ao3_id, work_e.ao3_id]


@pytest.mark.p3
@allure.id("AT-BUG-069-insert-rows-ordered-many-rows")
@allure.title("Проба: _insert_rows_ordered держит монотонность на >2 строках, ORDER BY DESC — точная инверсия списка")
def test_insert_rows_ordered_many_rows_full_inversion(work_ratings_db):
    # Given 4 работы, вставленные в порядке A, B, C, D
    works = [
        Work("900000901", "", "", "Fandom", None),
        Work("900000902", "", "", "Fandom", None),
        Work("900000903", "", "", "Fandom", None),
        Work("900000904", "", "", "Fandom", None),
    ]

    # When все 4 засеяны одним вызовом
    _insert_rows_ordered(work_ratings_db, [(w, "PENDING") for w in works])

    # Then timestamp строго монотонно растёт по позиции
    ts = _select_timestamps(work_ratings_db)
    ordered_ts = [ts[w.ao3_id] for w in works]
    assert ordered_ts == sorted(ordered_ts), ts
    assert len(set(ordered_ts)) == len(ordered_ts), "timestamp'ы не должны совпадать между позициями"

    # And ORDER BY timestamp DESC — точная инверсия списка (последняя
    # вставленная работа обрабатывается очередью ПЕРВОЙ)
    assert _select_ordered_ids(work_ratings_db) == [w.ao3_id for w in reversed(works)]


@pytest.mark.p3
@allure.id("AT-BUG-069-insert-rows-full-ordered-monotonic")
@allure.title("Проба: _insert_rows_full_ordered (twin для seed_with_comment, TC-062) даёт тот же порядок timestamp по позиции")
def test_insert_rows_full_ordered_strictly_increasing_by_position(work_ratings_db):
    # Given три работы — тот же состав, что TC-062 (Mango, Apple, Zebra),
    # заголовки/алфавит намеренно НЕ совпадают с ожидаемым порядком timestamp
    mango = Work("900000621", "Mango Work", "author_mango", "Fandom TC062", 1000)
    apple = Work("900000622", "Apple Work", "author_apple", "Fandom TC062", 1000)
    zebra = Work("900000623", "Zebra Work", "author_zebra", "Fandom TC062", 1000)

    # When все три засеяны ОДНИМ вызовом _insert_rows_full_ordered (rating,
    # comment, tags — опциональны, как в _insert_rows_full)
    _insert_rows_full_ordered(work_ratings_db, [
        (mango, "SAVE", None, None),
        (apple, "SAVE", None, None),
        (zebra, "SAVE", None, None),
    ])

    # Then timestamp строго растёт по позиции: Mango < Apple < Zebra
    ts = _select_timestamps(work_ratings_db)
    assert ts[mango.ao3_id] < ts[apple.ao3_id] < ts[zebra.ao3_id], ts

    # And порядок "последний прочитанный" (ORDER BY timestamp DESC, оракул
    # TC-062) — Zebra, Apple, Mango: ни порядок вставки (Mango первый), ни
    # алфавит не совпадают с этим порядком
    assert _select_ordered_ids(work_ratings_db) == [zebra.ao3_id, apple.ao3_id, mango.ao3_id]


@pytest.mark.p3
@allure.id("AT-BUG-069-insert-rows-full-ordered-optional-rating")
@allure.title("Проба: _insert_rows_full_ordered допускает rating=None (comment-only) без потери порядка timestamp")
def test_insert_rows_full_ordered_null_rating_preserves_order(work_ratings_db):
    # Given работа с rating=None (comment-only, как в seed_with_comment) и
    # работа с валидным rating, в этом порядке в списке
    comment_only = Work("900000701", "", "", "Fandom", None)
    rated = Work("900000702", "", "", "Fandom", None)

    # When засеяны одним вызовом, comment-only первой
    _insert_rows_full_ordered(work_ratings_db, [
        (comment_only, None, "just a note", None),
        (rated, "LIKE", None, None),
    ])

    # Then rating сохранён как есть (NULL для comment-only, не искажён)
    con = sqlite3.connect(db := work_ratings_db)
    con.row_factory = sqlite3.Row
    row_comment = con.execute(
        "SELECT rating, comment FROM work_ratings WHERE ao3Id = ?", (comment_only.ao3_id,)
    ).fetchone()
    row_rated = con.execute(
        "SELECT rating FROM work_ratings WHERE ao3Id = ?", (rated.ao3_id,)
    ).fetchone()
    con.close()
    assert row_comment["rating"] is None
    assert row_comment["comment"] == "just a note"
    assert row_rated["rating"] == "LIKE"

    # And порядок timestamp по позиции сохранён независимо от rating
    ts = _select_timestamps(work_ratings_db)
    assert ts[comment_only.ao3_id] < ts[rated.ao3_id], ts
