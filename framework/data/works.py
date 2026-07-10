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
    word_count: int = 1000

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
