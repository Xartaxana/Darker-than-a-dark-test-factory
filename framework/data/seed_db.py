"""Сидинг Room-БД приложения без обращения к AO3.

Подход (устойчив к версии схемы Room): взять БД, созданную самим приложением
(она содержит `room_master_table` с корректным identity-hash), влить строки в
`work_ratings`, вернуть файл в песочницу. Так Room не падает на проверке схемы.

Требует debug-сборку (run-as). См. спайк C в docs/environment-setup.md.
"""
from __future__ import annotations

import json
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
    """Существование ФАЙЛА БД — необходимое, но НЕ достаточное условие готовности
    (AT-BUG-044): Room создаёт файл раньше, чем прогоняет миграции/CREATE TABLE.
    Оставлена как отдельный дешёвый примитив (диагностика/будущие вызовы), но
    `ensure_db_initialized` полагается на `_schema_ready()`, не на эту функцию —
    см. её докстринг."""
    out = adb.run_as(f"sh -c 'test -f {_DB_REL} && echo YES || echo NO'").strip()
    return out.endswith("YES")


def _schema_ready() -> bool:
    """Готовность СХЕМЫ (таблица `work_ratings` существует и доступна для SELECT),
    а не только файла БД — AT-BUG-044 (диагноз: critic-вход приёмки D1
    `AT-BUG-042`, подтверждён двумя независимыми живыми воспроизведениями).
    `_db_exists()`/`test -f` раньше служил гейтом `ensure_db_initialized`, но
    Room создаёт ФАЙЛ БД раньше, чем прогоняет миграции/CREATE TABLE — окно, в
    котором `_pull_baseline` снимает файл без таблиц, и `_insert_rows` падает
    `sqlite3.OperationalError: no such table: work_ratings`.

    Проверка — `sqlite3 <db> "SELECT 1 FROM work_ratings LIMIT 0"` через
    `run-as` (доступно на этом образе — `adb shell which sqlite3` даёт
    `/system/bin/sqlite3`, живая сверка 2026-08-03, emulator-5554).
    `LIMIT 0` не возвращает строк даже при готовой схеме — единственное, что
    отличает «готово» от «не готово», это САМ факт ошибки, а не данные.

    `2>&1` ВНУТРИ remote-команды обязателен: `adb.run_as` идёт через
    `adb.shell()` -> `adb._run()`, который возвращает ТОЛЬКО `stdout`
    (`CompletedProcess.stdout`) — `adb shell` форвардит remote stdout/stderr в
    ДВА разных локальных потока, и текст ошибки sqlite3 CLI («no such table…»/
    «unable to open database file») уходит в stderr и терялся бы без явного
    редиректа (проверено живым прогоном: без `2>&1` `run_as()` видел пустую
    строку что при успехе, что при ошибке — ложный always-ready).

    ИНКРЕМЕНТ 2 (attempt 2, critic-вход rework AT-BUG-044): первая версия
    трактовала ПУСТОЙ вывод как «готово» — это fail-OPEN на отказе транспорта.
    `adb.run_as`→`adb.shell`→`adb._run(...).stdout` отбрасывает returncode;
    `2>&1` живёт ВНУТРИ remote-команды, значит форвардинг stderr работает,
    только если remote-shell вообще запустился. Если устройство offline/adb
    упал, `stdout` пуст (не текст ошибки, а именно ничего) — старая проверка
    `out == ""` читала это как «SELECT прошёл без ошибки» и возвращала True
    (ЛОЖЬ: схема НЕ проверена, транспорт просто не отработал). Живая проверка
    критика: `-s emulator-9999 shell "run-as ... 2>&1"` (несуществующее
    устройство) → rc=1, stdout='', stderr="device not found" — старая
    `_schema_ready()` вернула бы True на этом входе. Старый `_db_exists()`
    (`test -f`, тот же класс входа) давал False (fail-closed) — предыдущая
    правка ИНВЕРТИРОВАЛА полярность отказа, нарушив доктрину
    `framework/core/adb.py:49-81`/`:243-267` (AT-BUG-026 B2/N3: для логически
    критичных операций проверять returncode напрямую, не полагаться на
    shell()/run_as()).

    Фикс: remote-команда после успешного SELECT ЯВНО печатает маркер (`&&
    echo RDY`) — маркер попадает в stdout ТОЛЬКО если весь remote pipeline
    реально выполнился (SELECT прошёл, шелл жив, транспорт не упал). Позитивный
    контракт теперь: непустой суффикс `RDY` = таблица существует И
    remote-команда реально исполнилась. Любой другой вывод — «не готово»:
    текст ошибки sqlite3 без `RDY` (нет таблицы / нет файла БД), ПУСТАЯ строка
    (транспорт отказал целиком) — оба варианта fail-closed, различать не нужно
    вызывающему коду. Критик прогнал 4 ветки живьём: схема есть -> `...RDY` ->
    True; таблицы нет -> `Error: in prepare, no such table: work_ratings` (без
    RDY) -> False; устройство недоступно -> `''` -> False; файла БД нет ->
    `Error: unable to open database file` (без RDY) -> False."""
    out = adb.run_as(
        f"sh -c 'sqlite3 {_DB_REL} \"SELECT 1 FROM work_ratings LIMIT 0\" 2>&1 && echo RDY'"
    ).strip()
    return out.endswith("RDY")


def ensure_db_initialized() -> None:
    """После pm clear файла БД ещё нет — Room создаёт его (и прогоняет
    миграции/CREATE TABLE) при первом запуске. Запускаем приложение (явный
    am start -W, надёжнее monkey), ждём готовности СХЕМЫ (`_schema_ready()`,
    AT-BUG-044 — НЕ просто появления файла, см. её докстринг). Один ретрай на
    случай, если эмулятор был занят и запуск не состоялся.

    AT-BUG-009, инкремент 2 (закрытие шва инкремента 1): `adb.shell("am start
    -W ...")` теперь сам может кинуть `TimeoutError` (обёртка `adb._run()`,
    инкремент 1) — ЭТОТ вызов обязан быть ВНУТРИ того же `try`, что и
    `wait_for`, иначе `TimeoutError` из первой строки итерации улетает мимо
    ретрая наружу немедленно (наблюдение №3: 3 `ERROR at setup` на полном p0,
    все три — `TimeoutError` из `am start -W`, не пойманы этим циклом до
    фикса). `am start -W` — блокирующий вызов (ждёт полной прорисовки окна/
    onResume), не «быстрая» shell-команда из обоснования `ADB_SHELL_TIMEOUT`
    (`settings put`/`pm clear`/`force-stop`/`logcat -d`) — используем
    отдельный `ADB_LAUNCH_TIMEOUT`, см. обоснование в `settings.py`."""
    if _schema_ready():
        return
    for attempt in range(2):
        try:
            adb.shell(
                f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}",
                timeout=settings.ADB_LAUNCH_TIMEOUT,
            )
            wait_for(_schema_ready, timeout=40,
                     message="Room не создал схему work_ratings в ao3_ratings.db после запуска (AT-BUG-044)")
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
    """AT-BUG-010: `wordCount` — колонка `INTEGER` nullable (см. `AppDatabase.kt`).
    `work.word_count` идёт в INSERT как обычный bind-параметр — `Work(word_count=None)`
    (см. `works.NULL_WORD_COUNT_TARGET`) кладёт NULL штатным поведением sqlite3, без
    отдельной ветки/функции: не нужно расширять сигнатуру, как для `rating=None`
    (та ветка — `_insert_rows_full`/`seed_with_comment`, отдельная зависимость, т.к.
    `rating` там дополнительно проверяется по `_RATING_ENUM`)."""
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


def _insert_rows_ordered(db: Path, works: list[tuple[Work, str]]) -> None:
    """Как `_insert_rows`, но каждая строка получает СТРОГО возрастающий
    `timestamp` (`base_now + индекс_в_списке` мс) — нужно кейсам, где порядок
    обработки очереди определяется `ORDER BY timestamp DESC`
    (`WorkRatingDao.getWorksWithEmptyTitle`, app-under-test :39,
    `SettingsViewModel.fetchMissingMetadata`, TC-187). `_insert_rows` даёт
    ВСЕМ строкам списка ОДИНАКОВЫЙ `timestamp` (`now` вычисляется один раз на
    весь список, не по строке) — порядок среди РАВНЫХ `timestamp` в SQLite
    `ORDER BY` НЕ гарантирован стандартом (эмпирически поймано TC-187,
    2026-08-14: два ПОСЛЕДОВАТЕЛЬНЫХ вызова `seed()` — каждый со своим
    `force_stop()`/`ensure_db_initialized()` — вместо детерминированного
    порядка дали `sqlite3.OperationalError: no such table: work_ratings` на
    втором вызове, та же сигнатура, что закрывал `bugs/AT-BUG-044.md`
    [Verified]) — обходной путь ЗДЕСЬ: ОДИН round-trip вместо двух, порядок
    timestamp'ов гарантирован локально, без второго `force_stop`/relaunch.

    Заведён отдельный test_debt `bugs/AT-BUG-069.md` (`regression_of:
    AT-BUG-044`) — НЕ регрессия самого фикса AT-BUG-044 (тот правил только
    `_schema_ready()`, эта функция им не затронута), а соседний незакрытый
    механизм: `_pull_baseline` игнорирует возврат `pull_app_file` для
    `-wal`/`-shm`. Изолирующий эксперимент того же хода (20 живых прогонов
    на emulator-5554: 12x одиночный `ensure_db_initialized()` + немедленный
    ручной пулл, 8x буквальная реконструкция двух последовательных
    `seed()`-round-trip) НЕ воспроизвёл гонку (0/20, `pull_app_file` для
    WAL/SHM ни разу не вернул `False`, таблица 12/12 уже в main-файле сразу
    по `_schema_ready()==True`) — вклад этой гонки СНИЖЕН экспериментом, но
    НЕ исключён полностью (N=20 не исчерпывающе, см. AT-BUG-069
    §«Изолирующий эксперимент»). Более ранняя редакция этого докстринга
    утверждала «класс гонки не воспроизводится» — непроверенный каузальный
    негатив, заменён честной формулировкой.

    Порядок `works` в списке = порядок ВОЗРАСТАНИЯ `timestamp` — ПОСЛЕДНЯЯ
    строка списка получает САМЫЙ БОЛЬШОЙ `timestamp` (первой в `ORDER BY ...
    DESC`)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    base_now = int(time.time() * 1000)
    for i, (work, rating) in enumerate(works):
        assert rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, base_now + i,
             work.fandom, work.word_count, None, None, None),
        )
    con.commit()
    con.close()


def seed_ordered(works: list[tuple[Work, str]]) -> None:
    """Как `seed()`, но КАЖДАЯ строка получает СТРОГО возрастающий `timestamp`
    по своей позиции в списке (см. `_insert_rows_ordered`) — используется,
    когда порядок обработки очереди, читаемой `ORDER BY timestamp DESC`
    (`WorkRatingDao.getWorksWithEmptyTitle`), обязан быть детерминированным
    (TC-187: Stop должен застать процесс МЕЖДУ первой и второй засеянной
    работой, а не на случайной из них). ОДИН device round-trip (как и
    `seed()`) — НЕ эквивалент двух последовательных вызовов `seed()`."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_ordered(db, works)
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


def _insert_rows_full_ordered(
    db: Path,
    rows: list[tuple[Work, str | None, str | None, str | None]],
) -> None:
    """Twin `_insert_rows_ordered` для `_insert_rows_full`-семейства (rework
    attempt 2, критик-вход TC-186-188 B3): каждая строка получает СТРОГО
    возрастающий `timestamp` (`base_now + индекс_в_списке` мс) по своей
    позиции в `rows` — тот же приём, что `_insert_rows_ordered`, но для
    строк с опциональными `rating`/`comment`/`tags` (см. `_insert_rows_full`).
    Нужна кейсам вида TC-062 (`library_last_read_order_seeded`), которым
    раньше приходилось звать `seed_with_comment` НЕСКОЛЬКО раз подряд ради
    детерминированного порядка `timestamp` — каждый вызов открывал свой
    `force_stop()`/`ensure_db_initialized()` round-trip, тот же класс
    экспозиции, что закрывал `seed_ordered`/`_insert_rows_ordered` для
    TC-187 (см. их докстринги, `bugs/AT-BUG-069.md`)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    base_now = int(time.time() * 1000)
    for i, (work, rating, comment, tags) in enumerate(rows):
        assert rating is None or rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, base_now + i,
             work.fandom, work.word_count, comment, None, tags),
        )
    con.commit()
    con.close()


def seed_with_comment_ordered(
    rows: list[tuple[Work, str | None, str | None, str | None]],
) -> None:
    """Как `seed_with_comment()`, но КАЖДАЯ строка получает СТРОГО
    возрастающий `timestamp` по своей позиции в списке (см.
    `_insert_rows_full_ordered`) — ОДИН device round-trip вместо N
    последовательных вызовов `seed_with_comment` (TC-062:
    `library_last_read_order_seeded` мигрирована на эту функцию rework
    attempt 2, тот же мотив, что `seed_ordered`/TC-187)."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_full_ordered(db, rows)
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_work_ratings() -> dict[str, dict]:
    """Пуллит ТЕКУЩУЮ БД приложения (без записи/сидинга) и читает
    rating/comment/tags/fandom/wordCount по каждой строке `work_ratings` —
    используется для сверки round-trip Backup -> Clear -> Restore (TC-021):
    сравнение восстановленных полей с исходными засеянными значениями напрямую
    через Room, а не через текст UI (не зависит от локали форматирования чисел
    на карточке Library — см. заметки `framework/steps/backup_steps.py`).
    `tags` разбирается из JSON-массива (см. `Converters.fromTagList`/`toTagList`
    в app-under-test) обратно в список строк, `None` если пусто.

    В отличие от `seed()`/`seed_with_comment()` не требует остановленного
    приложения перед вызовом (запись не производится, только чтение уже
    зафиксированных Room данных) — вызывается, пока приложение открыто на
    экране Settings после Restore.

    НЕ расширяется полями `title`/`author`/`downloadPath` (AT-BUG-046) — эта
    сигнатура зафиксирована существующим потребителем `backup_steps.
    assert_restored_fields_match`/TC-021, который сравнивает `expected` (ровно
    эти 5 полей) с `actual` через `!=`: лишние ключи в `actual` сломали бы
    сравнение. Полный набор полей — `read_work_ratings_full()`."""
    tmp = Path(tempfile.mkdtemp(prefix="ao3read_"))
    try:
        db = _pull_baseline(tmp)
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT ao3Id, rating, comment, tags, fandom, wordCount FROM work_ratings"
        )
        rows: dict[str, dict] = {}
        for row in cur:
            tags = json.loads(row["tags"]) if row["tags"] else None
            rows[row["ao3Id"]] = {
                "rating": row["rating"],
                "comment": row["comment"],
                "tags": tags,
                "fandom": row["fandom"],
                "word_count": row["wordCount"],
            }
        con.close()
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read_full_rows(db: Path) -> dict[str, dict]:
    """Читает ВСЕ поля наблюдения `work_ratings` (ao3Id/title/author/url/
    downloadPath/rating/timestamp/comment/tags/fandom/wordCount) из уже
    локального файла БД `db` — без adb/pull, чистая SQL+parsing логика.
    Вынесена отдельно от `read_work_ratings_full()`, чтобы device-free юниты
    могли вызвать РЕАЛЬНЫЙ код разбора строки на временной sqlite-БД (см.
    `test_seed_db_full_baseline_unit.py`), не подделывая сам хелпер и не
    трогая устройство (AT-BUG-046, тот же приём, что `_insert_rows` в
    `test_seed_null_wordcount_unit.py`).

    ИНКРЕМЕНТ 2 (attempt 2, critic-вход rework): исходная версия отдавала 9
    из 11 полей строки, пропуская `url` и `timestamp`, при докстринге и DoD,
    обещающих ПОЛНЫЙ набор. `timestamp` — не косметика: это различающий
    оракул CH-008 («timestamp не изменился ⇒ записи не было вовсе»,
    единственный способ отличить «строка обновлена с тем же значением» от
    «строка не тронута»). Оба поля добавлены в SELECT и в возвращаемый dict."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT ao3Id, title, author, url, downloadPath, rating, timestamp, "
        "comment, tags, fandom, wordCount FROM work_ratings"
    )
    rows: dict[str, dict] = {}
    for row in cur:
        tags = json.loads(row["tags"]) if row["tags"] else None
        rows[row["ao3Id"]] = {
            "title": row["title"],
            "author": row["author"],
            "url": row["url"],
            "downloadPath": row["downloadPath"],
            "rating": row["rating"],
            "timestamp": row["timestamp"],
            "comment": row["comment"],
            "tags": tags,
            "fandom": row["fandom"],
            "word_count": row["wordCount"],
        }
    con.close()
    return rows


def read_work_ratings_full() -> dict[str, dict]:
    """Как `read_work_ratings()`, но отдаёт ПОЛНЫЙ набор полей строки
    `work_ratings` — все 11: `title`/`author`/`url`/`downloadPath`/`rating`/
    `timestamp`/`comment`/`tags`/`fandom`/`word_count` (AT-BUG-046) — нужно
    ассертам, проверяющим сохранность ВСЕХ полей строки (TC-151/152/155/156:
    `existing.copy(...)` панели против пересборки overlay; `timestamp` —
    различающий оракул CH-008: «не изменился ⇒ записи не было вовсе»). Новая
    функция РЯДОМ с `read_work_ratings()`, не расширение её сигнатуры — см.
    докстринг `read_work_ratings()` про существующего потребителя TC-021.

    Не требует остановленного приложения перед вызовом (только чтение) — тот
    же контракт, что у `read_work_ratings()`/`read_filter_profiles()`."""
    tmp = Path(tempfile.mkdtemp(prefix="ao3read_"))
    try:
        db = _pull_baseline(tmp)
        return _read_full_rows(db)
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


def read_filter_profiles() -> list[dict]:
    """Пуллит ТЕКУЩУЮ БД приложения (без записи/сидинга) и читает name/queryString
    по каждой строке `filter_profiles`, отсортированные по `name` — аналог
    `read_work_ratings()`, но для сохранённых фильтр-профилей (TC-021: сверка
    сохранности `filterProfiles` через round-trip Backup -> Clear -> Restore, C4).
    Не сравнивает по `id` — он генерируется сидингом (`seed_filter_profiles`) и
    приложением при импорте, вызывающему коду недоступен и не нужен: идентичность
    профиля для теста — пара (name, queryString), как и для работ в UI (сверка по
    заголовку, не по внутреннему ключу).

    Не требует остановленного приложения перед вызовом (только чтение) — тот же
    контракт, что у `read_work_ratings()`."""
    tmp = Path(tempfile.mkdtemp(prefix="ao3read_"))
    try:
        db = _pull_baseline(tmp)
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT name, queryString FROM filter_profiles ORDER BY name"
        )
        rows = [{"name": row["name"], "queryString": row["queryString"]} for row in cur]
        con.close()
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def seed_filter_profiles(profiles: list[tuple[str, str]]) -> list[str]:
    """Заливает список `(name, queryString)` в таблицу `filter_profiles` — аналог
    `seed()` для `work_ratings`, но для сохранённых фильтр-профилей (TC-041/TC-042).
    `timestamp` генерируется автоматически (now-ms, ОДИН на весь список — тот же
    приём, что `_insert_rows`).

    AT-BUG-073 (критерий готовности п.3): возвращает список сгенерированных `id`
    В ТОМ ЖЕ ПОРЯДКЕ, что `profiles` — нужен кейсам области `sync` (TC-212/213 и
    т.п.), которым нужно адресовать remote-сторону (мок GitLab-снимка,
    `gitlab_snippet_mock.py`) ПО ТОМУ ЖЕ `id`, что реально получила локальная
    строка (иначе слияние LWW/надгробие не найдёт совпадения по `id`). Раньше
    функция возвращала `None` — расширение сигнатуры backward-compatible: ВСЕ
    существующие вызывающие (`app_steps.seed_filter_profiles`,
    `conftest.py::filter_profile_applied_seeded`/`two_filter_profiles_seeded`)
    зовут её как statement, возврат не читают. Если нужен ДЕТЕРМИНИРОВАННЫЙ (не
    сгенерированный) `id` — используйте `_insert_rows_filter_profiles` напрямую.
    Приложение должно быть остановлено; после вызова стартуйте его заново (Room
    прочитает свежий файл) — тот же контракт, что у `seed()`."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        now = int(time.time() * 1000)
        ids = [str(uuid.uuid4()) for _ in profiles]
        rows = [
            (profile_id, name, query_string, now)
            for profile_id, (name, query_string) in zip(ids, profiles)
        ]
        _insert_rows_filter_profiles(db, rows)
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
        return ids
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Сидинг/чтение `sync_tombstones` (AT-BUG-073, критерий готовности п.2) ---
# Схема: `app-under-test/.../data/model/SyncTombstone.kt` (Entity) —
#   kind TEXT NOT NULL, id TEXT NOT NULL, deletedAt INTEGER NOT NULL,
#   PRIMARY KEY(kind, id)
# `kind` — `"work"`/`"profile"` (`SyncTombstone.KIND_WORK`/`KIND_PROFILE`). Нужна
# кейсам, воспроизводящим «работа/профиль уже удалены ранее» БЕЗ прохода через UI
# (TC-211: "работа Z несёт надгробие... прямой сидинг в Room, минуя UI") — по
# образцу `_insert_rows_filter_profiles`/`seed_filter_profiles`, найденному
# отсутствующим диагнозом AT-BUG-073 (`grep -rn "sync_tombstones" framework/`
# пуст ДО этого изменения — сверено `seed_db.py:515-524`/пустым grep перед
# началом работы над тикетом).


def _insert_rows_sync_tombstones(db: Path, rows: list[tuple[str, str, int]]) -> None:
    """rows: (kind, id, deletedAt). INSERT OR REPLACE по составному PK (kind, id) —
    тот же паттерн, что `_insert_rows_filter_profiles`: повторный сидинг с тем же
    (kind, id) заменяет надгробие (не дублирует, не падает на конфликте PK)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    for kind, entity_id, deleted_at in rows:
        cur.execute(
            """INSERT OR REPLACE INTO sync_tombstones (kind, id, deletedAt)
               VALUES (?,?,?)""",
            (kind, entity_id, deleted_at),
        )
    con.commit()
    con.close()


def seed_sync_tombstones(rows: list[tuple[str, str, int]]) -> None:
    """Заливает список `(kind, id, deletedAt)` напрямую в `sync_tombstones`,
    минуя UI — аналог `seed_filter_profiles`, но для надгробий. `kind` —
    `"work"`/`"profile"` (используйте `SYNC_TOMBSTONE_KIND_WORK`/`_PROFILE`
    константы этого модуля, а не хардкод строк на стороне вызывающего теста).
    Приложение должно быть остановлено; после вызова стартуйте его заново (Room
    прочитает свежий файл) — тот же контракт, что у `seed()`/`seed_filter_profiles`."""
    adb.force_stop()
    ensure_db_initialized()
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_sync_tombstones(db, rows)
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SYNC_TOMBSTONE_KIND_WORK = "work"
SYNC_TOMBSTONE_KIND_PROFILE = "profile"


def read_sync_tombstones() -> list[dict]:
    """Пуллит ТЕКУЩУЮ БД приложения (без записи/сидинга) и читает
    kind/id/deletedAt по каждой строке `sync_tombstones` — различающий оракул
    TC-211 Then («надгробие Z ФИЗИЧЕСКИ снято... прямое чтение таблицы
    sync_tombstones на устройстве не даёт строки для Z»), симметрично
    `read_filter_profiles()`/`read_work_ratings()`.

    Не требует остановленного приложения перед вызовом (только чтение) — тот же
    контракт, что у `read_filter_profiles()`."""
    tmp = Path(tempfile.mkdtemp(prefix="ao3read_"))
    try:
        db = _pull_baseline(tmp)
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        cur = con.execute("SELECT kind, id, deletedAt FROM sync_tombstones")
        rows = [
            {"kind": row["kind"], "id": row["id"], "deletedAt": row["deletedAt"]}
            for row in cur
        ]
        con.close()
        return rows
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


def _push_download_fixture(local_file: Path, work: Work) -> str:
    """Копирует локальный фикстур в internal-песочницу приложения на устройстве.
    Возвращает абсолютный путь для записи в `downloadPath`.

    AT-BUG-071: расширение устройственного пути ВЫВОДИТСЯ из `local_file.suffix`
    (не хардкодится `.html`) — вызывающая сторона передаёт локальный файл С
    РЕАЛЬНЫМ целевым расширением (`.html`/`.epub`), сидер сохраняет его 1:1 в
    имени на устройстве. MIME при открытии файла определяется РАСШИРЕНИЕМ пути
    (`MainActivity.kt:765`, `path.endsWith(".epub", ignoreCase = true)`), не
    содержимым — поэтому расширение устройственного пути — единственное, что
    имеет значение для сценариев «уже скачано как EPUB» (TC-239/TC-240-E).
    Байт-в-байт не меняет поведение для всех СУЩЕСТВУЮЩИХ вызовов (они всегда
    передавали `.html`-фикстуры — `framework/data/fixtures/downloaded_work.html` —
    и получали `.html` на устройстве, как и раньше)."""
    ext = local_file.suffix or ".html"
    rel = f"{_DOWNLOAD_FIXTURE_REL_DIR}/{work.ao3_id}{ext}"
    adb.run_as(f"mkdir -p {_DOWNLOAD_FIXTURE_REL_DIR}")
    adb.push_app_file(local_file, rel)
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


# --- Сидинг комбинированных baseline-строк (CH-008 baseline A/C, AT-BUG-046) ---
# `seed_with_comment` жёстко пишет `downloadPath=None` (`_insert_rows_full:190`),
# `seed_with_download` жёстко пишет `comment=tags=None` (`_insert_rows_with_download:385`)
# И ассертит `rating in _RATING_ENUM` (`rating=None` не проходит) — обе функции
# идут INSERT OR REPLACE на одну строку, композиция вызовов взаимно
# разрушительна. Функция ниже пишет comment+tags+downloadPath ОДНОЙ строкой,
# рейтинг независимо опционален (`None` легален, как в `_insert_rows_full`) —
# закрывает ОБЕ грани долга сразу: baseline A (rating не null, comment+tags+
# downloadPath) и baseline C (rating null, downloadPath, comment/tags опциональны).


def _insert_rows_full_with_download(
    db: Path,
    rows: list[tuple[Work, str | None, str | None, str | None, str]],
) -> None:
    """Как `_insert_rows_full`, но дополнительно пишет `downloadPath` (не
    жёстко `None`). rows: (work, rating, comment, tags, download_path) —
    `rating` опционален (`None` — comment/download-only запись, тот же
    инвариант `_RATING_ENUM`, что у `_insert_rows_full`: непустой `rating`
    ОБЯЗАН быть валидным значением enum, мусор по-прежнему ассертится);
    `download_path` НЕ опционален здесь — вызывающая сторона
    (`seed_with_comment_and_download`) всегда подставляет реальный путь на
    устройстве (для «нет файла» есть исходный `seed_with_comment`)."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    now = int(time.time() * 1000)
    for work, rating, comment, tags, download_path in rows:
        assert rating is None or rating in _RATING_ENUM, f"неизвестный rating: {rating}"
        cur.execute(
            """INSERT OR REPLACE INTO work_ratings
               (ao3Id, title, author, url, rating, timestamp, fandom, wordCount, comment, downloadPath, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (work.ao3_id, work.title, work.author, work.url, rating, now,
             work.fandom, work.word_count, comment, download_path, tags),
        )
    con.commit()
    con.close()


def seed_with_comment_and_download(
    rows: list[tuple[Work, str | None, str | None, str | None, Path]],
) -> dict[str, str]:
    """Сидинг комбинированного baseline «comment+tags+downloadPath одновременно»
    (CH-008 baseline A) И «rating=null+downloadPath» (baseline C) — ОДНОЙ
    функцией, т.к. обе грани долга AT-BUG-046 требуют одного и того же:
    независимость `downloadPath` от `comment`/`tags`/`rating`.

    rows: (work, rating, comment, tags, local_html_path) — `rating` может быть
    `None` (baseline C), `comment`/`tags` независимо опциональны (как в
    `seed_with_comment`), `local_html_path` — локальный HTML-фикстур,
    кладётся на устройство (как `seed_with_download`) и его device-путь
    пишется в `downloadPath`. Не заменяет `seed_with_comment`/
    `seed_with_download` — для строк, которым не нужна ОБА поля сразу,
    используйте их (дешевле — не кладут файл / не трогают comment/tags).
    Возвращает `{ao3_id: путь на устройстве}` (как `seed_with_download`)."""
    adb.force_stop()
    ensure_db_initialized()
    device_paths: dict[str, str] = {}
    for work, _rating, _comment, _tags, local_html in rows:
        device_paths[work.ao3_id] = _push_download_fixture(local_html, work)
    tmp = Path(tempfile.mkdtemp(prefix="ao3seed_"))
    try:
        db = _pull_baseline(tmp)
        _insert_rows_full_with_download(
            db,
            [
                (work, rating, comment, tags, device_paths[work.ao3_id])
                for work, rating, comment, tags, _ in rows
            ],
        )
        adb.run_as(f"rm -f {_WAL} {_SHM}")
        adb.push_app_file(db, _DB_REL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return device_paths
