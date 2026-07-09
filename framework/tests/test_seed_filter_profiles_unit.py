"""Device-free юнит-проба сидинга `filter_profiles` — AT-BUG-006, инкремент 1.

НЕ автоматизация TC-041/TC-042 (те требуют устройства + Appium). Эта проба
доказывает только сам механизм вставки: `seed_db._insert_rows_filter_profiles`
на временной локальной sqlite-БД, без adb/Appium/эмулятора — в этом инкременте
устройство занято параллельным fix-verifier (AT-BUG-006 диспатч, ЖЁСТКОЕ
ограничение среды).

Переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` (которая иначе дёрнула бы `adb pm list packages` при любом сборе
тестов в этой директории) — стандартный механизм pytest: fixture, определённая в
самом тестовом модуле, перекрывает одноимённую fixture из conftest.py для тестов
этого модуля. Модуль не использует `driver`/`clean_app`/`replay` и другие
device-фикстуры.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import allure
import pytest

from framework.data.seed_db import _insert_rows_filter_profiles

# Схема — точная копия `CREATE TABLE filter_profiles` из MIGRATION_3_4 в
# `app-under-test/app/src/main/java/com/example/ao3_wrapper/data/db/AppDatabase.kt`
# (согласуется с `@Entity` в data/model/FilterProfile.kt: id/name/queryString/timestamp).
_CREATE_FILTER_PROFILES_SQL = """
    CREATE TABLE filter_profiles (
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL,
        queryString TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )
"""


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. docstring модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture()
def filter_profiles_db(tmp_path: Path) -> Path:
    """Временная sqlite-БД с таблицей `filter_profiles`, созданной по схеме
    приложения (см. `_CREATE_FILTER_PROFILES_SQL`)."""
    db = tmp_path / "filter_profiles_unit.db"
    con = sqlite3.connect(db)
    con.execute(_CREATE_FILTER_PROFILES_SQL)
    con.commit()
    con.close()
    return db


def _select_all(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    cur = con.execute(
        "SELECT id, name, queryString, timestamp FROM filter_profiles ORDER BY name"
    )
    rows = cur.fetchall()
    con.close()
    return rows


@pytest.mark.p2
@allure.id("AT-BUG-006-seed-filter-profiles-insert")
@allure.title("Проба: _insert_rows_filter_profiles вставляет ожидаемые строки (device-free)")
def test_insert_rows_filter_profiles_inserts_expected_rows(filter_profiles_db):
    # Given две записи фильтр-профилей (аналог Given TC-042: "Profile A"/"Profile B")
    rows = [
        ("id-a", "Profile A", "work_search[query]=tag_a", 1000),
        ("id-b", "Profile B", "work_search[query]=tag_b", 2000),
    ]

    # When вставляем их через внутреннюю функцию сидинга
    _insert_rows_filter_profiles(filter_profiles_db, rows)

    # Then в БД лежат обе строки с ожидаемыми полями
    stored = _select_all(filter_profiles_db)
    assert stored == [
        ("id-a", "Profile A", "work_search[query]=tag_a", 1000),
        ("id-b", "Profile B", "work_search[query]=tag_b", 2000),
    ]


@pytest.mark.p2
@allure.id("AT-BUG-006-seed-filter-profiles-replace")
@allure.title("Проба: _insert_rows_filter_profiles заменяет строку при дубликате PK (device-free)")
def test_insert_rows_filter_profiles_replaces_on_duplicate_pk(filter_profiles_db):
    # Given профиль уже засеян с id "dup-id"
    _insert_rows_filter_profiles(
        filter_profiles_db, [("dup-id", "My saved search", "work_search[query]=old", 1000)]
    )

    # When вставляем запись с ТЕМ ЖЕ id, но другими name/queryString/timestamp
    _insert_rows_filter_profiles(
        filter_profiles_db, [("dup-id", "My saved search v2", "work_search[query]=new", 2000)]
    )

    # Then строка ЗАМЕНЕНА (INSERT OR REPLACE), не задублирована
    stored = _select_all(filter_profiles_db)
    assert stored == [("dup-id", "My saved search v2", "work_search[query]=new", 2000)]
