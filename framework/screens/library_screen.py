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

    # --- Иконки download/open на карточке (WorkCard в LibraryScreen.kt:
    # Icons.Default.Download contentDescription="Download", Icons.Default.Book
    # contentDescription="Open downloaded") ---
    def has_download_icon(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc("Download"), timeout=timeout or 8)

    def has_open_icon(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc("Open downloaded"), timeout=timeout or 8)

    def tap_open_icon(self, timeout: int | None = None):
        self.tap(self.by_desc("Open downloaded"), timeout=timeout)
        return self

    # --- Long-press overlay (DeleteWorkSheetContent в LibraryScreen.kt:
    # "Delete work" / "Delete downloaded file") ---
    def long_press_work(self, title: str, timeout: int | None = None):
        el = self.find(self.by_text(title), timeout)
        self.driver.execute_script(
            "mobile: longClickGesture", {"elementId": el.id, "duration": 1000})
        return self

    def delete_overlay_visible(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text("Delete work"), timeout=timeout or 6)

    def tap_delete_work(self):
        self.tap(self.by_text("Delete work"))
        return self

    def tap_delete_downloaded_file(self):
        self.tap(self.by_text("Delete downloaded file"))
        return self
