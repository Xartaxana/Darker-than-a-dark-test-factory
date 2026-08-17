"""Экран Library. Вкладки (ui/library/LibraryScreen.kt, enum LibTab):
Favorite | Kudosed | Read | Pending | Disliked | Files.

Примечание: подписи в UI ("Favorite"/"Kudosed"/"Files") отличаются от PROJECT.md
("Loved"/"Liked"/"Downloads") — расхождение зафиксировано для test-designer.
"""
from __future__ import annotations

import logging

from appium.webdriver.common.appiumby import AppiumBy

from framework.core.waits import poll_until_stable
from framework.screens.base_screen import BaseScreen

logger = logging.getLogger(__name__)

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

# --- Tab-switch settle (AT-BUG-082 Б2/Б3, критик-вход rework) ---
# HorizontalPager (`LibraryScreen.kt:238`) animates the tab transition
# (`pagerState.animateScrollToPage`, triggered by `Tab.onClick` in
# `PrimaryTabRow`) — right after `tap()` returns, the OUTGOING page's content
# can still be present in the accessibility tree alongside the INCOMING
# page's while the scroll is still mid-flight. Any reader that scans the
# WHOLE SCREEN immediately afterwards (`has_work`/`by_text`, no card/tab
# scope — the accessibility tree carries no per-tab boundary) risks matching
# the OUTGOING tab's content:
#   - false GREEN for a POSITIVE Then (`assert_work_in_files_tab` et al.) —
#     a title that's really on the outgoing tab satisfies the query even
#     though the target tab doesn't have it (Б2, critic grep: 9 risky call
#     sites across 6 files);
#   - false RED for a NEGATIVE Then — handled separately by the settle+hold
#     poll in `library_steps._poll_files_tab_absent` (Б1), which also needs
#     the pager to have stopped moving before its own settle-phase reads are
#     meaningful.
#
# `open_tab` now waits for the visible-text fingerprint (`_scroll_fingerprint`,
# same primitive already validated for `_settle_clipped_anchor`,
# AT-BUG-048/080) to stop changing across `_TAB_SWITCH_SETTLE_STABLE_READS`
# consecutive polls before returning. No dedicated "pager idle"/`selected`
# UI signal is used — not verified reliable on this Compose `Tab` on the
# live tree within this rework's time budget; the fingerprint-stabilize
# primitive is proven and already lives in the codebase for the structurally
# identical problem (list settle after a swipe). Best-effort/bounded
# (`_TAB_SWITCH_SETTLE_TIMEOUT`): does not raise if it never converges (same
# spirit as `_settle_clipped_anchor` — an unmeasurable/slower-than-budget
# settle must not block the caller) — logs a diagnostic warning instead, so a
# caller that reads a still-transitioning tree afterwards leaves a paper
# trail rather than failing silently (Б4).
#
# ALL FIVE existing readers that go through `open_tab`/`open_tab_for_rating`
# (`library_steps.assert_work_in_tab`, `assert_work_not_in_tab` — AT-BUG-083
# sibling, `assert_work_tags_visible`, `assert_work_note_icon_visible`,
# `assert_work_in_files_tab`) get this settle "for free" — the fix lives at
# the ONE place all of them share (D-0043: chini class, not instance;
# AT-BUG-082 Б3 критик-вход).
_TAB_SWITCH_SETTLE_TIMEOUT = 2.0
_TAB_SWITCH_SETTLE_INTERVAL = 0.2
_TAB_SWITCH_SETTLE_STABLE_READS = 2


class LibraryScreen(BaseScreen):
    def open_tab(self, label: str):
        self.tap(self.by_text(label))
        self._settle_tab_switch(label)
        return self

    def _settle_tab_switch(self, label: str) -> None:
        """AT-BUG-082 Б2/Б3 — см. блок-комментарий у констант выше."""
        _, converged = poll_until_stable(
            self._scroll_fingerprint,
            stable_reads=_TAB_SWITCH_SETTLE_STABLE_READS,
            timeout=_TAB_SWITCH_SETTLE_TIMEOUT,
            interval=_TAB_SWITCH_SETTLE_INTERVAL,
        )
        if not converged:
            logger.warning(
                "AT-BUG-082 Б4 (LibraryScreen._settle_tab_switch): вкладка %r "
                "не устаканилась за %.1fs бюджета (visible-text fingerprint "
                "продолжал меняться) — следующее чтение может застать "
                "переходное состояние HorizontalPager'а",
                label, _TAB_SWITCH_SETTLE_TIMEOUT,
            )

    def open_tab_for_rating(self, rating: str):
        return self.open_tab(TAB_BY_RATING[rating])

    # --- Позиция вкладок (TC-006: порядок подписей слева направо) ---
    def tab_label_x(self, label: str, timeout: int = 5) -> int | None:
        if not self.is_present(self.by_text(label), timeout=timeout):
            return None
        return self.find(self.by_text(label)).location["x"]

    def has_work(self, title: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text(title),
                               timeout=timeout or 8)

    # TODO(class: screen-wide card locator, misc-batch-lead-queue-0729 attempt 2,
    # заодно-минор): `has_tags_text`/`has_note_icon` ниже ищут ПО ВСЕМУ экрану
    # (`by_text_contains`/`by_desc` без title-скоупа) — тот же класс, что был
    # у `has_download_icon`/`has_open_icon` ДО card-scoped фикса `_card_icon_locator`
    # (батч мелочей D-0081, см. комментарий там же): на экране с НЕСКОЛЬКИМИ
    # карточками с разными тегами/заметками эти методы могут подтвердить
    # значение ЧУЖОЙ карточки. НЕ чинится в этом инкременте (вне минимального
    # скоупа attempt 2 — вынесено в очередь координатора).

    # --- Личные теги на карточке (WorkCard, LibraryScreen.kt ~960:
    # `Text(work.tags.joinToString(" · "))`, рендерится только при непустых `tags`) ---
    def has_tags_text(self, text: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text_contains(text), timeout=timeout or 6)

    # --- Note-иконка карточки (WorkCard, LibraryScreen.kt ~974-979:
    # `if (work.comment != null) NoteIconButton(...)`, contentDescription="View note"
    # ~1014-1038, по образцу has_download_icon/has_open_icon ниже) ---
    def has_note_icon(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc("View note"), timeout=timeout or 8)

    def work_card(self, title: str, timeout: int | None = None):
        return self.find(self.by_text(title), timeout)

    # --- Открытие работы в Browse (WorkCard.onClick -> onOpenWork(work.url),
    # LibraryScreen.kt ~878; combinedClickable висит на родительском Column
    # заголовка, не на самом Text-узле — тап по найденному текстовому узлу
    # физически попадает в его область, тот же паттерн, что и long_press_work
    # ниже. `openTab` (BrowserViewModel.kt) ВСЕГДА добавляет вкладку и
    # переключает MainActivity на Browse — используется как альтернативный
    # способ получить вторую вкладку Browse, см. TC-058.) ---
    def open_work(self, title: str, timeout: int | None = None):
        self.tap(self.by_text(title), timeout=timeout)
        return self

    # --- Иконки download/open на карточке (WorkCard в LibraryScreen.kt:
    # Icons.Default.Download contentDescription="Download", Icons.Default.Book
    # contentDescription="Open downloaded") ---
    #
    # Card-scoped (батч мелочей D-0081, 2026-07-29): раньше `by_desc(...)` искал
    # ПО ВСЕМУ экрану — при НЕСКОЛЬКИХ работах на экране мог подтвердить иконку
    # ЧУЖОЙ карточки (например, `assert_download_icon_shown` для работы X молча
    # прошёл бы, найдя "Download" на карточке Y). Живой замер (emulator-5554,
    # 2026-07-29, 2 работы с разным download-статусом — LOVED уже скачана,
    # KUDOSED нет) подтвердил: старый `is_present(by_desc("Download"))` находит
    # ЛЮБУЮ карточку с этой иконкой независимо от `title`. Все текущие
    # потребители (TC-032/033/034/035/115) засевают ОДНУ работу за раз — риск
    # ЛАТЕНТНЫЙ (не даёт красного сегодня), но реальный при будущем
    # multi-work сценарии — тот же класс, что уже решён позиционно для
    # `visible_card_y`/`topmost_visible_title` выше.
    #
    # Card-scoped дискриминация ИСПРАВЛЕННОГО локатора (ниже) отдельно проверена
    # device-witness'ом на ДВУХ карточках ОДНОЙ вкладки (B2, misc-batch-lead-
    # queue-0729 attempt 2, критик-вход — замер выше доказывал только СТАРЫЙ
    # баг, не корректность фикса): `test_library.py::
    # test_download_open_icon_discriminates_between_two_cards` (фикстура
    # `library_mixed_download_status_seeded`, conftest.py) — 4 утверждения:
    # своя иконка видна на своей карточке И НЕ видна иконка соседа, для ОБЕИХ
    # карточек сразу.
    #
    # Скоуп — XPath от TextView заголовка вверх РОВНО на 2 предка-View до корня
    # карточки (`ancestor::android.view.View[2]`), затем вниз до иконки по
    # `content-desc`. Число «2» не эвристика — сверено по живому accessibility-
    # дереву (`uiautomator dump` через Appium, emulator-5554): `WorkCard`
    # (LibraryScreen.kt ~895-1010) — фиксированная Compose-разметка `Row(root)
    # -> [Column(заголовок, combinedClickable), Row(иконки)]`; TextView
    # заголовка — первый ребёнок `Column`, поэтому 1-й предок-View — сам
    # `Column`, 2-й — корневой `Row` карточки (общий для Column и Row(иконки)).
    def _card_icon_locator(self, title: str, desc: str):
        return (
            AppiumBy.XPATH,
            f'//android.widget.TextView[@text="{title}"]'
            f'/ancestor::android.view.View[2]//*[@content-desc="{desc}"]',
        )

    def has_download_icon(self, title: str, timeout: int | None = None) -> bool:
        return self.is_present(self._card_icon_locator(title, "Download"), timeout=timeout or 8)

    def has_open_icon(self, title: str, timeout: int | None = None) -> bool:
        return self.is_present(self._card_icon_locator(title, "Open downloaded"), timeout=timeout or 8)

    def tap_open_icon(self, title: str, timeout: int | None = None):
        self.tap(self._card_icon_locator(title, "Open downloaded"), timeout=timeout)
        return self

    def tap_download_icon(self, title: str, timeout: int | None = None):
        self.tap(self._card_icon_locator(title, "Download"), timeout=timeout)
        return self

    # --- Пустая вкладка (LibraryScreen.kt EmptyState, TC-037) ---
    def is_empty(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text("Nothing here yet"), timeout=timeout or 8)

    # --- Long-press overlay (WorkActionsSheetContent в LibraryScreen.kt:
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

    # --- Overlay action «Open in background tab» (WorkActionsSheetContent,
    # LibraryScreen.kt ~376-384: первый пункт того же overlay, что «Delete
    # work»/«Delete downloaded file» выше) — TC-173/174/175/176/189. ---
    def tap_open_in_background(self):
        self.tap(self.by_text("Open in background tab"))
        return self

    # --- Filter panel (MainActivity top bar "Filter library" -> LibraryScreen.kt
    # FilterSheetContent, ModalBottomSheet). Сверено на живом дереве
    # (scripts/ui_snapshot.py, lib_filter_sheet.xml) — Min/Max word count поля
    # рендерятся как безымянные Compose EditText (нет content-desc/text до ввода),
    # порядок в дереве Search -> Min -> Max, отсюда позиционный instance(). ---
    _WORD_COUNT_FIELD = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().className("android.widget.EditText").instance({index})',
    )
    _DOWNLOADED_ONLY_CHECKBOX = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().className("android.widget.CheckBox")',
    )

    def open_filter_sheet(self, timeout: int | None = None):
        self.tap(self.by_desc("Filter library"), timeout=timeout)
        return self

    def is_filter_sheet_open(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text("Filters"), timeout=timeout or 6)

    def open_fandom_picker(self):
        """Триггер фандом-пикера рендерится как "All fandoms" (дефолт, без выбора) —
        своего content-desc не имеет, см. LibraryScreen.kt FilterSheetContent."""
        self.tap(self.by_text("All fandoms"))
        return self

    def select_fandom_option(self, fandom: str):
        self.tap(self.by_text(fandom))
        return self

    # ── Search any field (TC-061) — первый (index 0) EditText в FilterSheetContent,
    # рендерится ДО Fandom/Min/Max (см. комментарий у `_WORD_COUNT_FIELD` выше:
    # "порядок в дереве Search -> Min -> Max"). ──
    _SEARCH_FIELD = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().className("android.widget.EditText").instance(0)',
    )

    def set_search_query(self, value: str):
        field = self.find(self._SEARCH_FIELD)
        field.clear()
        field.send_keys(value)
        return self

    def clear_search_query(self):
        """Крестик очистки (`contentDescription = "Clear"`) виден только при непустом
        значении поля — тот же content-desc, что у крестика "Search tags", но тот
        рендерится лишь при непустом `tagQuery`, который этот метод не трогает."""
        self.tap(self.by_desc("Clear"))
        return self

    # ── Личные теги (TC-060) — TagChip: `clickable` висит на родительском Row чипа,
    # тап по найденному текстовому узлу тега физически попадает в его область (тот
    # же паттерн, что WorkCard.open_work). ──
    def select_tag(self, tag: str):
        self.tap(self.by_text(tag))
        return self

    def set_min_words(self, value: str):
        cls, sel = self._WORD_COUNT_FIELD
        field = self.find((cls, sel.format(index=1)))
        field.clear()
        field.send_keys(value)
        return self

    def set_max_words(self, value: str):
        cls, sel = self._WORD_COUNT_FIELD
        field = self.find((cls, sel.format(index=2)))
        field.clear()
        field.send_keys(value)
        return self

    def is_downloaded_only_checked(self, timeout: int | None = None) -> bool:
        el = self.find(self._DOWNLOADED_ONLY_CHECKBOX, timeout)
        return el.get_attribute("checked") == "true"

    def set_downloaded_only(self, checked: bool):
        """Тап по строке "Downloaded only" — тумблер, поэтому таплю только если
        текущее состояние не совпадает с желаемым (идемпотентно)."""
        if self.is_downloaded_only_checked() != checked:
            self.tap(self.by_text("Downloaded only"))
        return self

    def tap_apply_filters(self):
        self.tap(self.by_text("Apply filters"))
        return self

    # --- Sort control (MainActivity top bar, icon-only trigger; contentDescription
    # encodes текущий выбор — "Sort library: {label}" — LibraryViewModel.LibrarySort) ---
    def open_sort_menu(self, current_label: str = "Last read", timeout: int | None = None):
        self.tap(self.by_desc(f"Sort library: {current_label}"), timeout=timeout)
        return self

    def select_sort_option(self, label: str):
        self.tap(self.by_text(label))
        return self

    def close_sort_menu(self):
        """Закрывает dropdown БЕЗ выбора опции (TC-065: проверка отсутствия опции
        "Rating" вне вкладки Files). `AppDropdownMenu` — `Popup` с дефолтным
        `PopupProperties(dismissOnBackPress = true)` (см. `AppDropdownMenu.kt` —
        `focusable = true` задан явно, `dismissOnBackPress` не переопределён и
        остаётся дефолтным true), поэтому системная кнопка Back гасит только сам
        popup, не уводит с экрана Library."""
        self.driver.back()
        return self

    def sort_trigger_label(self, timeout: int | None = None) -> str:
        """Читает текущий выбор сортировки из content-desc триггера (единственное
        место, где подпись отображается — сама иконка icon-only, см. заметки TC-030)."""
        loc = (AppiumBy.ANDROID_UIAUTOMATOR,
               'new UiSelector().descriptionStartsWith("Sort library:")')
        desc = self.find(loc, timeout).get_attribute("contentDescription") or ""
        return desc.removeprefix("Sort library: ")

    # --- Позиция карточек на экране (для проверки сортировки/сброса скролла без
    # завязки на внутренний порядок дерева — сравниваем видимые Y-координаты) ---
    def visible_card_y(self, title: str, timeout: int = 2) -> int | None:
        if not self.is_present(self.by_text(title), timeout=timeout):
            return None
        return self.find(self.by_text(title)).location["y"]

    def topmost_visible_title(self, titles: list[str]) -> str | None:
        positions = [(t, self.visible_card_y(t)) for t in titles]
        visible = [(t, y) for t, y in positions if y is not None]
        if not visible:
            return None
        return min(visible, key=lambda p: p[1])[0]
