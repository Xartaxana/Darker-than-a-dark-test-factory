"""Бизнес-шаги выставления рейтинга (GWT).

В live-режиме выставление рейтинга на странице работы требует навигации по AO3
(сторонний сайт). Основной P0-smoke опирается на сидинг данных; эти шаги —
для точечных сценариев и будущего replay-режима.
"""
from __future__ import annotations

import allure

from framework.screens.browser_screen import BrowserScreen
from framework.screens.rating_overlay import RatingOverlay


@allure.step("When открыта страница работы {work_id}")
def open_work_page(driver, work_id: str):
    BrowserScreen(driver).open_work(work_id)


@allure.step("When на странице работы выставлен рейтинг {rating}")
def rate_current_work(driver, rating: str):
    overlay = RatingOverlay(driver)
    assert overlay.is_visible(), "меню рейтинга не появилось на странице работы"
    overlay.choose(rating)
