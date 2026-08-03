"""Device-free юнит-проба новых примитивов сидинга/чтения AT-BUG-046 —
`seed_db._insert_rows_full_with_download` (baseline A/C, CH-008) и
`seed_db._read_full_rows` (полное чтение строки, включая title/author/
downloadPath). Обе функции вызываются НАПРЯМУЮ на временной локальной
sqlite-БД со схемой приложения — тот же приём, что
`test_seed_null_wordcount_unit.py` (AT-BUG-010): device-free, эмулятор не
поднимается, `_ensure_app_installed` переопределена как no-op.

Живая device-верификация (сидинг НА устройстве через
`seed_with_comment_and_download`/чтение через `read_work_ratings_full`) —
отдельно, см. `bugs/AT-BUG-046.md` §Верификация; здесь проверяется только сам
механизм SQL-вставки/разбора, без adb/Appium."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import allure
import pytest

from framework.data.seed_db import _insert_rows_full_with_download, _read_full_rows
from framework.data.works import Work

# Схема — та же копия, что в test_seed_null_wordcount_unit.py (v7, MIGRATION_6_7,
# см. app-under-test/.../data/db/AppDatabase.kt).
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
    """Переопределяет device-фикстуру conftest.py — эта проба чисто локальная."""
    yield


@pytest.fixture()
def work_ratings_db(tmp_path: Path) -> Path:
    db = tmp_path / "work_ratings_unit.db"
    con = sqlite3.connect(db)
    con.execute(_CREATE_WORK_RATINGS_SQL)
    con.commit()
    con.close()
    return db


_WORK_A = Work("900046001", "AT-BUG-046 Baseline A Work", "seed_author_046a", "Fandom 046A", 777)
_WORK_C = Work("900046002", "AT-BUG-046 Baseline C Work", "seed_author_046c", "Fandom 046C", 888)


@pytest.mark.p2
@allure.id("AT-BUG-046-baseline-a-comment-tags-download-path-coexist")
@allure.title("Baseline A: comment+tags+downloadPath одной строкой, ничего не обнулилось (device-free)")
def test_baseline_a_comment_tags_download_path_all_present(work_ratings_db):
    # Given/When одна строка с непустыми rating/comment/tags/downloadPath —
    # ровно комбинация, которую `seed_with_comment`/`seed_with_download` по
    # отдельности не могут засеять без взаимного разрушения (AT-BUG-046 п.2)
    tags_json = json.dumps(["tagA", "tagB"])
    _insert_rows_full_with_download(
        work_ratings_db,
        [(_WORK_A, "SAVE", "note A", tags_json, "/data/user/0/pkg/files/ao3_test_downloads/900046001.html")],
    )

    # Then полное чтение назад (та же функция, что использует
    # read_work_ratings_full()) видит ВСЕ поля одновременно — ни downloadPath,
    # ни comment/tags не обнулены композицией
    rows = _read_full_rows(work_ratings_db)
    row = rows[_WORK_A.ao3_id]
    assert row["rating"] == "SAVE"
    assert row["comment"] == "note A"
    assert row["tags"] == ["tagA", "tagB"]
    assert row["downloadPath"] == "/data/user/0/pkg/files/ao3_test_downloads/900046001.html"
    assert row["title"] == _WORK_A.title
    assert row["author"] == _WORK_A.author
    assert row["fandom"] == _WORK_A.fandom
    assert row["word_count"] == _WORK_A.word_count


@pytest.mark.p2
@allure.id("AT-BUG-046-baseline-c-null-rating-with-download-path")
@allure.title("Baseline C: rating=None легален вместе с downloadPath (device-free)")
def test_baseline_c_null_rating_with_download_path(work_ratings_db):
    # Given/When rating=None (comment/download-only запись), downloadPath
    # непустой — `seed_with_download` эту комбинацию ассертом запрещает
    # (AT-BUG-046 п.3), новая функция обязана её принять
    _insert_rows_full_with_download(
        work_ratings_db,
        [(_WORK_C, None, "download-only note", None,
          "/data/user/0/pkg/files/ao3_test_downloads/900046002.html")],
    )

    rows = _read_full_rows(work_ratings_db)
    row = rows[_WORK_C.ao3_id]
    assert row["rating"] is None
    assert row["downloadPath"] == "/data/user/0/pkg/files/ao3_test_downloads/900046002.html"
    assert row["comment"] == "download-only note"
    assert row["tags"] is None


@pytest.mark.p2
@allure.id("AT-BUG-046-rating-enum-still-asserted")
@allure.title("Граница: rating='МУСОР' по-прежнему ассертится (инвариант _RATING_ENUM не ослаблен)")
def test_garbage_rating_still_asserted(work_ratings_db):
    # None легален (baseline C) — но НЕ любая строка: непустой rating обязан
    # остаться в _RATING_ENUM, иначе это молчаливая порча данных, а не
    # осознанный comment/download-only baseline.
    with pytest.raises(AssertionError, match="неизвестный rating"):
        _insert_rows_full_with_download(
            work_ratings_db,
            [(_WORK_A, "МУСОР", None, None, "/data/user/0/pkg/files/ao3_test_downloads/x.html")],
        )


@pytest.mark.p2
@allure.id("AT-BUG-046-insert-or-replace-does-not-clobber-across-calls")
@allure.title("INSERT OR REPLACE повторным вызовом обновляет строку целиком, не оставляя полей от предыдущей вставки")
def test_replace_updates_all_fields_not_partial(work_ratings_db):
    # Given строка засеяна с одним набором полей
    _insert_rows_full_with_download(
        work_ratings_db,
        [(_WORK_A, "SAVE", "old note", json.dumps(["old-tag"]), "/old/path.html")],
    )
    # When тот же ao3Id пересеян другим набором (в т.ч. downloadPath меняется)
    _insert_rows_full_with_download(
        work_ratings_db,
        [(_WORK_A, "LIKE", "new note", json.dumps(["new-tag"]), "/new/path.html")],
    )
    # Then видно только новое состояние — ни одно поле не «залипло» от старой строки
    row = _read_full_rows(work_ratings_db)[_WORK_A.ao3_id]
    assert row["rating"] == "LIKE"
    assert row["comment"] == "new note"
    assert row["tags"] == ["new-tag"]
    assert row["downloadPath"] == "/new/path.html"


@pytest.mark.p2
@allure.id("AT-BUG-046-read-full-rows-null-tags-and-comment")
@allure.title("_read_full_rows: comment/tags=None читаются как None, не как пустая строка/список (device-free)")
def test_read_full_rows_null_comment_and_tags(work_ratings_db):
    _insert_rows_full_with_download(
        work_ratings_db,
        [(_WORK_A, "SAVE", None, None, "/data/path.html")],
    )
    row = _read_full_rows(work_ratings_db)[_WORK_A.ao3_id]
    assert row["comment"] is None
    assert row["tags"] is None
    assert row["downloadPath"] == "/data/path.html"
