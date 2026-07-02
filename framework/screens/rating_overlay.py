"""Меню рейтинга (ui/components/RatingOverlay.kt). Кнопки-рейтинги имеют текстовую
подпись. ВНИМАНИЕ: подпись Rating.DISLIKE в меню — "Dislike" (в Library вкладка
называется "Disliked").
"""
from __future__ import annotations

from framework.screens.base_screen import BaseScreen

RATING_BUTTON_LABEL = {
    "SAVE": "Favorite",
    "LIKE": "Kudosed",
    "READ": "Read",
    "PENDING": "Pending",
    "DISLIKE": "Dislike",
}


class RatingOverlay(BaseScreen):
    def is_visible(self, timeout: int = 8) -> bool:
        # Меню видно, когда присутствует любая из кнопок рейтинга
        return self.is_present(self.by_text("Favorite"), timeout=timeout)

    def choose(self, rating: str):
        self.tap(self.by_text(RATING_BUTTON_LABEL[rating]))
        return self

    def add_note_toggle_visible(self) -> bool:
        return self.is_present(self.by_text("Add a note"), timeout=4)
