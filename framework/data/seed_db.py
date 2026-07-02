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
