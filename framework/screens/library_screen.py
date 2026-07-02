"""Экран Library. Вкладки (ui/library/LibraryScreen.kt, enum LibTab):
Favorite | Kudosed | Read | Pending | Disliked | Files.

Примечание: подписи в UI ("Favorite"/"Kudosed"/"Files") отличаются от PROJECT.md
("Loved"/"Liked"/"Downloads") — расхождение зафиксировано для test-designer.
"""
from __future__ import annotations

from framework.screens.base_screen import BaseScreen

# Соответствие Rating.enum -> подпись вкладки Library.
# Вкладки Tab рендерятся в ВЕРХНЕМ РЕГИСТРЕ (accessibility-текст = uppercase).
TAB_BY_RATING = {
    "SAVE": "FAVORITE",
    "LIKE": "KUDOSED",
    "READ": "READ",
    "PENDING": "PENDING",
    "DISLIKE": "DISLIKED",
}
FILES_TAB = "FILES"


class LibraryScreen(BaseScreen):
    def open_tab(self, label: str):
        self.tap(self.by_text(label))
        return self

    def open_tab_for_rating(self, rating: str):
        return self.open_tab(TAB_BY_RATING[rating])

    def has_work(self, title: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text(title),
                               timeout=timeout or 8)

    def work_card(self, title: str, timeout: int | None = None):
        return self.find(self.by_text(title), timeout)
