"""Бизнес-шаги выставления рейтинга (GWT).

В live-режиме выставление рейтинга на странице работы требует навигации по AO3
(сторонний сайт). Основной P0-smoke опирается на сидинг данных; эти шаги —
для точечных сценариев и будущего replay-режима.
"""
from __future__ import annotations

import allure

from framework.core.waits import wait_until
from framework.screens.browser_screen import BrowserScreen
from framework.screens.navigation import BottomNav
from framework.screens.rating_overlay import RatingOverlay


@allure.step("When открыта страница работы {work_id}")
def open_work_page(driver, work_id: str):
    BrowserScreen(driver).open_work(work_id)


@allure.step("When на странице работы выставлен рейтинг {rating}")
def rate_current_work(driver, rating: str):
    # Встроенная панель WorkRatingPanel (RatingMenu) на странице работы, как и
    # нижняя навигация, скрыта на вкладке Browse за нижней ручкой-пилюлей
    # (BottomBar.kt: AnimatedVisibility(selectedTab != BROWSE || navExpanded)) —
    # раскрываем её тем же механизмом, что и BottomNav.
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "меню рейтинга не появилось на странице работы"
    overlay.choose(rating)


@allure.step("When в открывшемся с листинга bottom-sheet выбран рейтинг {rating}")
def rate_via_listing_overlay(driver, rating: str):
    """Нативный `RatingOverlay` (bottom-sheet, ui/components/RatingOverlay.kt),
    открытый Rate-кнопкой листинга (`browser_steps.tap_rate_button`) — в отличие от
    встроенной панели (`rate_current_work`) НЕ спрятан за `AnimatedVisibility` нижней
    навигации (рендерится в `BrowserScreen.kt` безусловно при `showRatingOverlay=true`,
    поверх WebView), поэтому `BottomNav.ensure_visible()` здесь не нужен."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не появился после Rate-кнопки листинга"
    overlay.choose(rating)


@allure.step("When bottom-sheet рейтинга закрыт тапом по затемнённой области")
def dismiss_rating_overlay(driver):
    """`onSave`/`onSaveNote` (BrowserScreen.kt) вызывают `applyRating(..., dismiss=false)` —
    bottom-sheet НЕ закрывается сам после выбора рейтинга (позволяет дописать note/tags
    без переоткрытия), закрывается только явным тапом по scrim (см.
    `RatingOverlay.dismiss`, TC-009)."""
    RatingOverlay(driver).dismiss()


@allure.step("Given зафиксирован baseline цвета кнопки рейтинга {rating} на панели работы")
def capture_panel_rating_baseline(driver, rating: str) -> float:
    """Раскрывает панель `RatingMenu` (если ещё не раскрыта) и измеряет исходный
    (невыбранный) цвет её кнопки `rating` — baseline для `assert_rating_button_selected`
    (TC-010, см. `RatingOverlay.button_avg_luma`)."""
    BottomNav(driver).ensure_visible()
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "меню рейтинга не появилось на странице работы"
    return overlay.button_avg_luma(rating)


@allure.step("Given зафиксирован baseline цвета кнопки рейтинга {rating} в открытом bottom-sheet листинга")
def capture_listing_overlay_baseline(driver, rating: str) -> float:
    """Как `capture_panel_rating_baseline`, но для bottom-sheet, открытого Rate-кнопкой
    листинга (`rate_via_listing_overlay`) — тот же виджет `RatingMenu`, но не спрятан
    за `AnimatedVisibility` нижней навигации, `BottomNav.ensure_visible()` не нужен
    (см. докстринг `rate_via_listing_overlay`, TC-009)."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не появился после Rate-кнопки листинга"
    return overlay.button_avg_luma(rating)


@allure.step("Then кнопка рейтинга {rating} визуально отражает выбор немедленно")
def assert_rating_button_selected(driver, rating: str, baseline_luma: float, timeout: int = 6, ratio: float = 0.75):
    """Опрашивает luma кнопки (общий приём для встроенной панели work-page И
    bottom-sheet листинга — оба используют один и тот же composable `RatingMenu`),
    пока она не потемнеет относительно `baseline_luma` (переход в `ratingAccent` —
    насыщенный тёмный цвет против светлого невыбранного фона, см.
    `RatingOverlay.button_avg_luma`) — опрос вместо одноразового чтения, тот же
    паттерн, что `browser_steps.assert_webview_darkened` (анимация
    `animateColorAsState`, 180мс tween, не мгновенна кадр-в-кадр). TC-009/TC-010."""
    def _selected(d):
        luma = RatingOverlay(d).button_avg_luma(rating)
        return luma < baseline_luma * ratio
    wait_until(
        driver, _selected, timeout=timeout,
        message=f"кнопка рейтинга {rating} не изменила цвет относительно baseline={baseline_luma:.1f} за {timeout}с",
    )


@allure.step("Then панель рейтинга на странице работы БОЛЬШЕ НЕ отражает выбор {rating}")
def assert_panel_rating_deselected(driver, rating: str, selected_baseline_luma: float, timeout: int = 10, ratio: float = 0.75):
    """Симметрично `assert_rating_button_selected` — обратное направление
    (TC-020: панель должна вернуться к невыбранному светлому цвету кнопки после
    Clear all ratings). `selected_baseline_luma` — luma, снятая ПОКА рейтинг ещё
    был выставлен (тёмный `ratingAccent`); ждём, пока кнопка не посветлеет
    заметно выше этого значения — тот же приём деления на `ratio`, что
    `browser_steps.assert_webview_lightened`. Раскрывает панель (`BottomNav.
    ensure_visible()`), если она успела свернуться после переключения вкладок."""
    from framework.screens.navigation import BottomNav
    BottomNav(driver).ensure_visible()
    def _deselected(d):
        luma = RatingOverlay(d).button_avg_luma(rating)
        return luma > selected_baseline_luma / ratio
    wait_until(
        driver, _deselected, timeout=timeout,
        message=(
            f"кнопка рейтинга {rating} осталась в выбранном виде (luma не поднялась выше "
            f"{selected_baseline_luma / ratio:.1f}, baseline выбранного={selected_baseline_luma:.1f}) "
            f"после Clear all ratings — панель не отразила очистку без reload"
        ),
    )


@allure.step("When в открытом bottom-sheet листинга раскрыто поле комментария и сохранён текст «{comment}»")
def add_note_via_listing_overlay(driver, comment: str):
    """TC-074/075 (live-ветвь): раскрывает поле комментария в уже открытом (Rate-
    кнопкой листинга) нативном `RatingOverlay` и сохраняет текст через "Save note" —
    живой аналог `seed_with_comment` из TC-075/077 (replay), доказывающий тот же
    контракт `applyRatings` через реальный UI-ввод, а не сидинг."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не открыт — нечего раскрывать"
    overlay.toggle_comment()
    overlay.enter_comment(comment)
    overlay.save_note()


@allure.step("When в открытом bottom-sheet листинга раскрыт раздел тегов и добавлен личный тег «{tag}»")
def add_tag_via_listing_overlay(driver, tag: str):
    """TC-076/077 (live-ветвь): раскрывает раздел личных тегов в уже открытом bottom-
    sheet и добавляет `tag` через поле ввода + кнопку "Add" — требует уже выставленного
    рейтинга (раздел недоступен без него, см. `RatingOverlay.toggle_tags`)."""
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "нативный bottom-sheet рейтинга не открыт — нечего раскрывать"
    overlay.toggle_tags()
    overlay.enter_tag_input(tag)
    overlay.confirm_tag_input()


@allure.step("Then overlay рейтинга открыт с развёрнутым полем комментария, предзаполненным «{expected_text}»")
def assert_note_overlay_expanded_with_text(driver, expected_text: str):
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "overlay рейтинга не открылся по Note-кнопке"
    assert overlay.comment_expanded(), (
        "поле комментария должно быть развёрнуто сразу («Hide note» виден), "
        "а не свёрнуто за «Add a note»"
    )
    assert overlay.comment_text_visible(expected_text), (
        f"поле комментария не предзаполнено текстом «{expected_text}»"
    )
