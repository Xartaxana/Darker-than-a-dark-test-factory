"""Реестр эталонных тестовых работ. Значения синтетические — используются для
сидинга Room без обращения к живому AO3. ao3_id намеренно из «безопасного» диапазона,
на реальный сайт с ними не ходим.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Work:
    ao3_id: str
    title: str
    author: str
    fandom: str = "Test Fandom"
    # `int | None` — AT-BUG-010: колонка `wordCount INTEGER` в `work_ratings`
    # nullable (см. `AppDatabase.kt`, CREATE TABLE work_ratings_new), сидинг
    # (`seed_db._insert_rows`/`seed()`) передаёт значение поля напрямую в
    # INSERT — `None` кладёт NULL штатным поведением sqlite3-биндинга
    # параметров, без отдельной функции. Явный `None` — сознательный выбор
    # автора `Work`, а не забытый дефолт: используйте `word_count=None` для
    # граничных кейсов вида TC-031 (сортировка при отсутствующем word_count).
    word_count: int | None = 1000

    @property
    def url(self) -> str:
        return f"https://archiveofourown.org/works/{self.ao3_id}"


# Стабильные фикстурные работы для smoke/регрессии Library.
LOVED = Work("900000001", "A Loved Test Work", "seed_author_a", "Fandom Alpha", 4200)
KUDOSED = Work("900000002", "A Kudosed Test Work", "seed_author_b", "Fandom Beta", 1500)
READ = Work("900000003", "A Read Test Work", "seed_author_c", "Fandom Gamma", 800)
PENDING = Work("900000004", "A Pending Test Work", "seed_author_d", "Fandom Delta", 12000)
DISLIKED = Work("900000005", "A Disliked Test Work", "seed_author_e", "Fandom Eps", 300)

ALL = [LOVED, KUDOSED, READ, PENDING, DISLIKED]

# Филлер-работы для гарантированной прокрутки списка Library (TC-030: сброс скролла
# при смене сортировки нужно проверять на списке ВЫШЕ высоты экрана). word_count
# намеренно меньше самого маленького в ALL (300 у DISLIKED), чтобы после сортировки
# Word count (high to low) все филлеры ушли в конец списка и не мешали проверке
# относительного порядка пяти эталонных работ.
SCROLL_FILLERS = [
    Work(f"9000009{i:02d}", f"Filler Scroll Work {i:02d}", f"filler_author_{i:02d}",
         "Filler Fandom", 10 + i)
    for i in range(1, 11)
]

# TC-038: работа для сценария auto-scan/relink при смене папки загрузок — засевается
# с downloadPath=null (seed_library не заполняет это поле), затем на устройстве уже
# лежит orphan-файл, чьё имя оканчивается на "_<ao3_id>.html".
ORPHAN_RELINK_TARGET = Work("900000038", "TC-038 Orphan Relink Target", "seed_author_orphan",
                            "Fandom Orphan", 750)

# TC-039: работа НЕ засевается в Room заранее (Library пуста по Given кейса) — этот
# ao3_id участвует только в backup JSON (importFromUri вставляет строку с
# downloadPath=null) и в имени orphan-файла, положенного в SAF-папку загрузок ПОСЛЕ
# её выбора (см. `app_steps.place_file_in_download_folder`).
RESTORE_SCAN_TARGET = Work("900000039", "TC-039 Restore Scan Target", "seed_author_restore_scan",
                           "Fandom Restore Scan", 650)

# TC-031: work с `word_count=None` — сортировка по Word count должна отправлять
# такую работу в конец списка независимо от направления (граница отсутствующего
# значения, AT-BUG-010). `seed()`/`seed_library` кладут её через тот же `_insert_rows`,
# что и обычные работы — None доходит до колонки `wordCount` как NULL без отдельной
# функции сидинга (см. комментарий у поля `Work.word_count` выше).
NULL_WORD_COUNT_TARGET = Work("900000031", "TC-031 Null Word Count Target",
                              "seed_author_null_wc", "Fandom Null WC", None)

# TC-027 (C4-ретрофит 2026-07-18) — граничные значения фильтра word count.
# `ALL` не содержит ни одного word_count, равного точно min/max диапазона
# [1000, 5000], проверенного тестом — свойство «включительность границ»
# (инлайн-фильтр в composable: `(it.wordCount ?: 0) >= min` /
# `(it.wordCount ?: Int.MAX_VALUE) <= max`, LibraryScreen.kt:164-169 — обе
# границы `>=`/`<=`, не строгие; подпись файла исправлена critic'ом) остаётся
# недоказанным на самих границах. Отдельные work вместо расширения `ALL`,
# чтобы не менять состав данных `library_all_one_rating_seeded` (используется
# и TC-029 — фильтр по фандому, не должен получить лишние 2 работы).
WORD_COUNT_MIN_BOUNDARY = Work("900000271", "TC-027 Word Count Min Boundary",
                               "seed_author_wc_min", "Fandom WC Min", 1000)
WORD_COUNT_MAX_BOUNDARY = Work("900000272", "TC-027 Word Count Max Boundary",
                               "seed_author_wc_max", "Fandom WC Max", 5000)
