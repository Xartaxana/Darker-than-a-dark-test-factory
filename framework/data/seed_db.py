"""Сидинг Room-БД приложения без обращения к AO3.

Подход (устойчив к версии схемы Room): взять БД, созданную самим приложением
(она содержит `room_master_table` с корректным identity-hash), влить строки в
`work_ratings`, вернуть файл в песочницу. Так Room не падает на проверке схемы.

Требует debug-сборку (run-as). См. спайк C в docs/environment-setup.md.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from framework.config import settings
from framework.core import adb
from framework.core.waits import wait_for
from framework.data.works import Work

_DB_REL = "databases/ao3_ratings.db"
_WAL = _DB_REL + "-wal"
_SHM = _DB_REL + "-shm"
_RATING_ENUM = {"SAVE", "LIKE", "READ", "PENDING", "DISLIKE"}


def _db_exists() -> bool:
    out = adb.run_as(f"sh -c 'test -f {_DB_REL} && echo YES || echo NO'").strip()
    return out.endswith("YES")


def ensure_db_initialized() -> None:
    """После pm clear файла БД ещё нет — Room создаёт его при первом запуске.
    Запускаем приложение (явный am start -W, надёжнее monkey), ждём появления БД.
    Один ретрай на случай, если эмулятор был занят и запуск не состоялся."""
    if _db_exists():
        return
    for attempt in range(2):
        adb.shell(f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}")
        try:
            wait_for(_db_exists, timeout=40,
                     message="Room не создал ao3_ratings.db после запуска")
            break
        except TimeoutError:
            if attempt == 1:
                raise
            adb.force_stop()
    adb.force_stop()


def _pull_baseline(dst_dir: Path) -> Path:
    """Снимает актуальную БД приложения (db+wal+shm) и сворачивает WAL в единый файл."""
    db = dst_dir / "ao3_ratings.db"
    ok = adb.pull_app_file(_DB_REL, db)
    if not ok:
        raise RuntimeError("не удалось снять ao3_ratings.db — приложение установлено и запускалось?")
    # WAL/SHM могут отсутствовать — это нормально
    adb.pull_app_file(_WAL, dst_dir / "ao3_ratings.db-wal")
    adb.pull_app_file(_SHM, dst_dir / "ao3_ratings.db-shm")
    # Свернуть WAL в основной файл, чтобы дальше работать с одним db
    con = sqlite3.connect(db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.commit()
    con.close()
    return db


def _insert_rows(db: Path, works: list[tuple[Work, str]]) -> None:
    con = sqlite3.connect(db)
    cur = con.cursor()
    now = int(time.time() * 1000)
    for work, rating in works:
        assert rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, now,
             work.fandom, work.word_count, None, None, None),
        )
    con.commit()
    con.close()


def _insert_rows_full(
    db: Path,
    rows: list[tuple[Work, str | None, str | None, str | None]],
) -> None:
    """Как `_insert_rows`, но допускает `rating=None` (comment-only запись — см.
    `WorkRating.rating: Rating?` в app-under-test) и опциональные `comment`/`tags`.
    Используется `seed_with_comment` для кейсов, которым `seed()` не хватает
    (TC-014: work без рейтинга с непустым comment)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    now = int(time.time() * 1000)
    for work, rating, comment, tags in rows:
        assert rating is None or rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, now,
             work.fandom, work.word_count, comment, None, tags),
        )
    con.commit()
    con.close()


def seed(works: list[tuple[Work, str]]) -> None:
    """Заливает список (Work, rating) в БД приложения. Приложение должно быть остановлено;
    после вызова стартуйте его заново (Room прочитает свежий файл)."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows(db, works)
        # Убираем возможные wal/shm на устройстве и кладём свёрнутый db
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def seed_with_comment(
    rows: list[tuple[Work, str | None, str | None, str | None]],
) -> None:
    """Расширенный сидинг: каждая строка — (Work, rating, comment, tags), где `rating`
    и `comment`/`tags` независимо опциональны (`None`). Поддерживает comment-only
    записи (`rating=None`, непустой `comment`) — соответствует модели
    `WorkRating.rating: Rating?` в app-under-test (см.
    `app-under-test/.../data/model/WorkRating.kt`: null означает comment-only).
    Не заменяет `seed()` — отдельная функция для кейсов, которым нужен контроль
    над comment/tags/null-рейтингом (например TC-014)."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_full(db, rows)
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Сидинг фильтр-профилей (`filter_profiles`) — AT-BUG-006, инкремент 1 ---
# Схема таблицы: `app-under-test/.../data/model/FilterProfile.kt` (Entity) +
# `AppDatabase.kt` MIGRATION_3_4 (CREATE TABLE) —
#   id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, queryString TEXT NOT NULL,
#   timestamp INTEGER NOT NULL
# Нужна для TC-041 (применение сохранённого профиля) и TC-042 (удаление профиля из
# Settings) — оба сидят профиль(и) напрямую в Room, минуя UI (см. заметки в телах
# кейсов и `bugs/AT-BUG-006.md`).


def _insert_rows_filter_profiles(db: Path, rows: list[tuple[str, str, str, int]]) -> None:
    """rows: (id, name, queryString, timestamp). INSERT OR REPLACE — тот же паттерн,
    что `_insert_rows` для `work_ratings`: повторный вызов с тем же `id` заменяет
    строку (не дублирует и не падает на конфликте PK)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    for profile_id, name, query_string, timestamp in rows:
        cur.execute(
            """INSERT OR REPLACE INTO filter_profiles
               (id, name, queryString, timestamp)
               VALUES (?,?,?,?)""",
            (profile_id, name, query_string, timestamp),
        )
    con.commit()
    con.close()


def seed_filter_profiles(profiles: list[tuple[str, str]]) -> None:
    """Заливает список `(name, queryString)` в таблицу `filter_profiles` — аналог
    `seed()` для `work_ratings`, но для сохранённых фильтр-профилей (TC-041/TC-042).
    `id` (PK, TEXT) и `timestamp` генерируются автоматически (uuid4 / now-ms):
    вызывающему коду (кейсам) они не нужны — сверка идёт по URL query-параметрам и
    видимости профиля по имени в списке, не по внутреннему id. Если понадобится
    детерминированный `id` (например, для точечного теста INSERT OR REPLACE),
    используйте `_insert_rows_filter_profiles` напрямую.
    Приложение должно быть остановлено; после вызова стартуйте его заново (Room
    прочитает свежий файл) — тот же контракт, что у `seed()`."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        now = int(time.time() * 1000)
        rows = [(str(uuid.uuid4()), name, query_string, now) for name, query_string in profiles]
        _insert_rows_filter_profiles(db, rows)
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Сидинг «уже скачанной» работы (downloadPath) без реального скачивания ---
# TC-034/TC-035/TC-036 (downloads) требуют работу с заполненным downloadPath на
# РЕАЛЬНО существующий файл. Фикстура кладётся во ВНУТРЕННЮЮ песочницу приложения
# (files/..., НЕ getExternalFilesDir/ao3_downloads, как предполагали заметки
# кейсов) — на API 34 прямой `adb push`/`run-as` в app-specific external storage
# падает («remote secure_mkdirs failed: Operation not permitted» / «Permission
# denied» даже под run-as: Android 11+ scoped storage не даёт adb-процессу нужный
# FUSE-mount, независимо от совпадения UID). Внутренний путь поведенчески
# эквивалентен для black-box теста: приложение читает/удаляет файл по downloadPath
# голым `File(path)` (DownloadRepository.deleteDownload, BrowserScreen.loadTabContent)
# и не проверяет, что путь лежит именно под getExternalFilesDir.
_DOWNLOAD_FIXTURE_REL_DIR = "files/ao3_test_downloads"
_DEVICE_DATA_ROOT = f"/data/user/0/{settings.APP_PACKAGE}"


def _push_download_fixture(local_html: Path, work: Work) -> str:
    """Копирует локальный HTML-фикстур в internal-песочницу приложения на
    устройстве. Возвращает абсолютный путь для записи в `downloadPath`."""
    rel = f"{_DOWNLOAD_FIXTURE_REL_DIR}/{work.ao3_id}.html"
    adb.run_as(f"mkdir -p {_DOWNLOAD_FIXTURE_REL_DIR}")
    adb.push_app_file(local_html, rel)
    return f"{_DEVICE_DATA_ROOT}/{rel}"


def _insert_rows_with_download(db: Path, rows: list[tuple[Work, str, str]]) -> None:
    con = sqlite3.connect(db)
    cur = con.cursor()
    now = int(time.time() * 1000)
    for work, rating, download_path in rows:
        assert rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, now,
             work.fandom, work.word_count, None, download_path, None),
        )
    con.commit()
    con.close()


def seed_with_download(rows: list[tuple[Work, str, Path]]) -> dict[str, str]:
    """Как `seed()`, но дополнительно кладёт на устройство локальный HTML-фикстур
    для каждой строки и заполняет `downloadPath` результирующим путём — имитирует
    уже скачанную работу без обращения к `DownloadRepository`/сети (TC-034/035/036).
    rows: (work, rating, local_html_path). Возвращает {ao3_id: путь на устройстве}."""
    adb.force_stop()
    ensure_db_initialized()
    device_paths: dict[str, str] = {}
    for work, _rating, local_html in rows:
        device_paths[work.ao3_id] = _push_download_fixture(local_html, work)
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_with_download(
            db, [(work, rating, device_paths[work.ao3_id]) for work, rating, _ in rows]
        )
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return device_paths
