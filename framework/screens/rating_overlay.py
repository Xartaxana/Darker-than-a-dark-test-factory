"""Меню рейтинга (ui/components/RatingOverlay.kt). Кнопки-рейтинги имеют текстовую
подпись. ВНИМАНИЕ: подпись Rating.DISLIKE в меню — "Dislike" (в Library вкладка
называется "Disliked").
"""
from __future__ import annotations

import io

from appium.webdriver.common.appiumby import AppiumBy
from PIL import Image

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

    def add_note_toggle_visible(self, timeout: int = 4) -> bool:
        return self.is_present(self.by_text("Add a note"), timeout=timeout)

    def dismiss(self):
        """Закрывает bottom-sheet тапом по затемнённой области ВЫШЕ карточки
        (`RatingOverlay.kt`: внешний `Box` — сплошной scrim с `clickable { onDismiss }`,
        карточка внутри — отдельный `Column` с СОБСТВЕННЫМ пустым `clickable {}`,
        глотающим клик, чтобы не проваливался в scrim под ней). Нужно ЯВНО тапать вне
        карточки: выбор рейтинга (`onSave`) вызывается с `dismiss=false` (позволяет
        добавить note/tags без переоткрытия overlay) — overlay НЕ закрывается сам
        после выбора, см. TC-009."""
        size = self.driver.get_window_size()
        x, y = size["width"] // 2, int(size["height"] * 0.06)
        self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        return self

    # --- TC-010: бейдж выбранного рейтинга в НАТИВНОЙ панели/overlay не имеет
    # accessibility-состояния "selected" (Compose TextButton его не проставляет) —
    # единственный наблюдаемый сигнал выбора — `animateColorAsState`, красящая фон
    # кнопки в ratingAccent (см. RatingOverlay.kt/Theme.kt RatingColorSet), поэтому
    # читаем средний luma прямоугольника кнопки по скриншоту (тот же приём, что
    # `BrowserScreen.top_chrome_avg_luma`/`webview_avg_luma`, только по rect кнопки,
    # не по доле экрана). Compose мёржит semantics кликабельного узла — `by_text`
    # находит узел с bounds всей кнопки (иконка+подпись), не только текст. ---
    def button_avg_luma(self, rating: str) -> float:
        el = self.find(self.by_text(RATING_BUTTON_LABEL[rating]))
        rect = el.rect
        png = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("L")
        box = (rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
        cropped = img.crop(box)
        hist = cropped.histogram()
        total = sum(hist)
        return sum(i * c for i, c in enumerate(hist)) / total

    # --- TC-044: поле комментария в RatingMenu тоглится "Add a note"/"Hide note"
    # (см. RatingOverlay.kt) — развёрнуто, когда виден именно "Hide note". ---
    def comment_expanded(self, timeout: int = 6) -> bool:
        return self.is_present(self.by_text("Hide note"), timeout=timeout)

    def comment_text_visible(self, text: str, timeout: int = 6) -> bool:
        """Читает текст предзаполненного поля комментария через частичное
        совпадение (Compose `BasicTextField` мёржит своё editable-содержимое в
        accessibility-текст узла)."""
        return self.is_present(self.by_text_contains(text), timeout=timeout)

    # --- TC-074/076: живой ввод комментария/личного тега через `RatingMenu`
    # (RatingOverlay.kt) — `BasicTextField` рендерится как безымянный Compose
    # `android.widget.EditText` (тот же паттерн, что `LibraryScreen`/`BrowserScreen`
    # поля ввода, см. `framework/screens/library_screen.py::_WORD_COUNT_FIELD`).
    # `instance(0)` корректен в обоих случаях: сценарии TC-074/076 раскрывают либо
    # комментарий, либо теги, НЕ оба сразу — на экране в этот момент ровно ОДНО
    # такое поле. ---
    _EDIT_TEXT_FIELD = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().className("android.widget.EditText").instance(0)',
    )

    def toggle_comment(self):
        """Раскрывает поле комментария (тоггл "Add a note"/"Hide note")."""
        self.tap(self.by_text("Add a note"))
        return self

    def enter_comment(self, text: str):
        field = self.find(self._EDIT_TEXT_FIELD)
        field.clear()
        field.send_keys(text)
        return self

    def save_note(self):
        """Тап "Save note" — сохраняет комментарий (`onSaveNote`), bottom-sheet
        сам не закрывается (см. `dismiss_rating_overlay`)."""
        self.tap(self.by_text("Save note"))
        return self

    def toggle_tags(self):
        """Раскрывает раздел личных тегов (тоггл "Add tags"/"Hide tags") — доступен
        только когда рейтинг уже выбран (`RatingMenu`: `enabled = selectedRating != null`).
        Лейбл тоггла в свёрнутом состоянии зависит от того, есть ли уже сохранённые
        теги: "Add tags" при нуле, "Saved tags (N)" при N>0 (TC-090/091) — оба ведут
        к одному и тому же тогглу, поэтому проверяем оба варианта."""
        if self.is_present(self.by_text("Add tags"), timeout=2):
            self.tap(self.by_text("Add tags"))
        else:
            self.tap(self.by_text_contains("Saved tags"))
        return self

    def hide_tags(self):
        """Сворачивает уже раскрытый раздел личных тегов (тоггл "Hide tags") — после
        сворачивания лейбл возвращается к "Add tags"/"Saved tags (N)" (TC-090/091)."""
        self.tap(self.by_text("Hide tags"))
        return self

    def enter_tag_input(self, text: str):
        field = self.find(self._EDIT_TEXT_FIELD)
        field.clear()
        field.send_keys(text)
        return self

    def confirm_tag_input(self):
        """Тап кнопки "Add" рядом с полем ввода личного тега — добавляет тег в
        список (`addTag`), который сразу же уходит в `onRatingTap`/сохранение."""
        self.tap(self.by_text("Add"))
        return self

    # --- TC-087/088: свёрнутое превью комментария и его очистка ---
    def tap_comment_preview(self, text: str):
        """Тап по свёрнутому превью комментария (иконка + текст, `RatingOverlay.kt`
        ~182: `Modifier...clickable { showComment = true }`) — раскрывает поле для
        редактирования. Тот же локатор, что читает `comment_text_visible`, только
        здесь по нему тапают, а не читают."""
        self.tap(self.by_text_contains(text))
        return self

    def clear_note(self):
        """Тап "Clear note" — очищает комментарий (`onSaveNote(rating, "", tags)`),
        видна только когда `comment.isNotBlank()` (`RatingOverlay.kt` ~224-235)."""
        self.tap(self.by_text("Clear note"))
        return self

    # --- TC-090/091: счётчик сохранённых тегов и работа с уже выбранными чипами ---
    def tags_count_label_visible(self, n: int, timeout: int = 6) -> bool:
        return self.is_present(self.by_text(f"Saved tags ({n})"), timeout=timeout)

    def tap_selected_chip(self, tag: str):
        """Тап по уже выбранному чипу тега — удаляет его (`removeTag`, `TagChip`
        `clickable` висит на родительском Row чипа, тот же паттерн, что
        `LibraryScreen.select_tag`)."""
        self.tap(self.by_text(tag))
        return self

    def chip_visible(self, tag: str, timeout: int = 6) -> bool:
        """Читает наличие/отсутствие текста чипа тега (частичное совпадение, тот же
        generic приём, что `comment_text_visible`)."""
        return self.is_present(self.by_text_contains(tag), timeout=timeout)
