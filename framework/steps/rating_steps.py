"""Бизнес-шаги выставления рейтинга (GWT).

В live-режиме выставление рейтинга на странице работы требует навигации по AO3
(сторонний сайт). Основной P0-smoke опирается на сидинг данных; эти шаги —
для точечных сценариев и будущего replay-режима.
"""
from __future__ import annotations

import allure

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
