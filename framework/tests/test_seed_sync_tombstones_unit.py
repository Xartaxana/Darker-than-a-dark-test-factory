"""Device-free юнит-проба сидинга `sync_tombstones` (AT-BUG-073, критерий
готовности п.2 «сидер/хелпер прямой записи `sync_tombstones`» — критик-вход
attempt 4, класс-пробел «новый примитив без device-free юнит-пробы»).

НЕ автоматизация TC-211 (тот требует устройства + Appium, уже покрыт
`framework/tests/test_sync.py`). Эта проба доказывает только сам механизм
вставки/чтения: `seed_db._insert_rows_sync_tombstones` на временной
локальной sqlite-БД, без adb/Appium/эмулятора — ТОТ ЖЕ приём, что
`test_seed_filter_profiles_unit.py` (AT-BUG-006) использует для
`_insert_rows_filter_profiles`: схема таблицы — точная копия `CREATE TABLE
sync_tombstones` (`AppDatabase.kt:14`, `@Entity(tableName = "sync_tombstones",
primaryKeys = ["kind", "id"])` в `SyncTombstone.kt`), составной PRIMARY KEY
(kind, id).

Переопределяет session-scoped autouse-фикстуру `_ensure_app_installed` из
`conftest.py` (та иначе дёрнула бы `adb pm list packages` при сборе тестов
этой директории) — тот же приём, что `test_seed_filter_profiles_unit.py`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import allure
import pytest

from framework.data.seed_db import (
    SYNC_TOMBSTONE_KIND_PROFILE,
    SYNC_TOMBSTONE_KIND_WORK,
    _insert_rows_sync_tombstones,
)

# Схема — точная копия `CREATE TABLE sync_tombstones`, выведенная из
# `@Entity(tableName = "sync_tombstones", primaryKeys = ["kind", "id"])`
# (`SyncTombstone.kt`) — Room генерирует составной PRIMARY KEY(kind, id) для
# этой аннотации.
_CREATE_SYNC_TOMBSTONES_SQL = """
    CREATE TABLE sync_tombstones (
        kind TEXT NOT NULL,
        id TEXT NOT NULL,
        deletedAt INTEGER NOT NULL,
        PRIMARY KEY (kind, id)
    )
"""


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) —
    эта проба чисто локальная, устройство не трогаем."""
    yield


@pytest.fixture()
def tombstones_db(tmp_path: Path) -> Path:
    """Временная sqlite-БД с таблицей `sync_tombstones`, созданной по схеме
    приложения (см. `_CREATE_SYNC_TOMBSTONES_SQL`)."""
    db = tmp_path / "sync_tombstones_unit.db"
    con = sqlite3.connect(db)
    con.execute(_CREATE_SYNC_TOMBSTONES_SQL)
    con.commit()
    con.close()
    return db


def _select_all(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    cur = con.execute(
        "SELECT kind, id, deletedAt FROM sync_tombstones ORDER BY kind, id"
    )
    rows = cur.fetchall()
    con.close()
    return rows


@pytest.mark.p1
@allure.id("AT-BUG-073-insert-rows-sync-tombstones-inserts-expected-rows")
@allure.title("Проба: _insert_rows_sync_tombstones вставляет ожидаемые строки, kind=work и kind=profile сосуществуют (device-free)")
def test_insert_rows_sync_tombstones_inserts_expected_rows(tombstones_db):
    # Given два надгробия разного kind (work/profile), разные id
    rows = [
        (SYNC_TOMBSTONE_KIND_WORK, "900000211", 1_000),
        (SYNC_TOMBSTONE_KIND_PROFILE, "profile-id-a", 2_000),
    ]

    # When вставляем их через внутреннюю функцию сидинга
    _insert_rows_sync_tombstones(tombstones_db, rows)

    # Then в БД лежат обе строки с ожидаемыми полями
    stored = _select_all(tombstones_db)
    assert stored == [
        (SYNC_TOMBSTONE_KIND_PROFILE, "profile-id-a", 2_000),
        (SYNC_TOMBSTONE_KIND_WORK, "900000211", 1_000),
    ]


@pytest.mark.p1
@allure.id("AT-BUG-073-insert-rows-sync-tombstones-replaces-on-duplicate-composite-pk")
@allure.title("Проба: _insert_rows_sync_tombstones заменяет deletedAt при повторном сидинге ТОГО ЖЕ (kind, id) — составной PK, не дублирует строку (device-free)")
def test_insert_rows_sync_tombstones_replaces_on_duplicate_composite_pk(tombstones_db):
    # Given надгробие работы уже засеяно с deletedAt=1000
    _insert_rows_sync_tombstones(
        tombstones_db, [(SYNC_TOMBSTONE_KIND_WORK, "900000211", 1_000)]
    )

    # When вставляем СТРОКУ С ТЕМ ЖЕ составным ключом (kind, id), но другим deletedAt
    _insert_rows_sync_tombstones(
        tombstones_db, [(SYNC_TOMBSTONE_KIND_WORK, "900000211", 9_999)]
    )

    # Then строка ЗАМЕНЕНА (INSERT OR REPLACE по составному PK), не задублирована
    stored = _select_all(tombstones_db)
    assert stored == [(SYNC_TOMBSTONE_KIND_WORK, "900000211", 9_999)]


@pytest.mark.p1
@allure.id("AT-BUG-073-insert-rows-sync-tombstones-same-id-different-kind-independent")
@allure.title("Проба: ОДИНАКОВЫЙ id, но РАЗНЫЙ kind — две независимые строки (составной PK, не просто PK по id) (device-free)")
def test_insert_rows_sync_tombstones_same_id_different_kind_are_independent(tombstones_db):
    # Given/When work-надгробие и profile-надгробие с ОДИНАКОВЫМ id (граница:
    # составной PK (kind, id) обязан различать их, PK по одному id — нет)
    _insert_rows_sync_tombstones(tombstones_db, [
        (SYNC_TOMBSTONE_KIND_WORK, "shared-id", 1_000),
        (SYNC_TOMBSTONE_KIND_PROFILE, "shared-id", 2_000),
    ])

    # Then ОБЕ строки присутствуют — не схлопнулись в одну по id
    stored = _select_all(tombstones_db)
    assert stored == [
        (SYNC_TOMBSTONE_KIND_PROFILE, "shared-id", 2_000),
        (SYNC_TOMBSTONE_KIND_WORK, "shared-id", 1_000),
    ]
