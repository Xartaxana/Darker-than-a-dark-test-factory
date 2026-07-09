"""Инфраструктурные пробы AT-BUG-004, инкремент 3: доказывают пригодность
replay-фикстур для сценариев, которые ещё не автоматизированы как тест-кейсы.

ВАЖНО: тесты этого модуля — НЕ автоматизация конкретных TC-xxx. Они проверяют, что
сам replay-механизм (`conftest.py::replay` + `framework/data/recording_builder.py`)
выдерживает более сложный сценарий, чем уже доказанный TC-013
(`test_visibility.py`) — простановку рейтинга через нативный bottom-sheet,
открытый с Rate-кнопки листинга (нужно для TC-009, `bugs/AT-BUG-004.md`).
Решение о переводе TC-009 из `Review` в `Approved`/автоматизации самого кейса
остаётся за test-designer/test-automator — этот модуль не трогает
`test-cases/rating/TC-009.md`. `@allure.id` здесь намеренно НЕ повторяет "TC-009"
(и вообще не использует формат `TC-xxx`), чтобы не создавать у инструментов,
читающих allure-id (см. `scripts/arch_check.py` §Правило 2), ложное впечатление,
что кейс автоматизирован.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data import works as W
from framework.steps import app_steps, browser_steps, rating_steps


@pytest.mark.p1
@pytest.mark.replay
@allure.id("AT-BUG-004-rating-probe")
@allure.title("Проба: рейтинг из листинга через нативный bottom-sheet на replay-фикстуре (не автоматизация TC-009)")
@pytest.mark.parametrize("replay", [rb.LISTING_BASIC_FILENAME], indirect=True)
def test_rate_from_listing_bottom_sheet_on_replay_fixture(replay, clean_app, driver):
    # Given приложение с чистыми данными (работа W ещё не имеет рейтинга — для её
    # ao3_id нет строки в Room) и открыт replay-листинг (listing_basic.mitm),
    # содержащий блёрб W с инжектированной Rate-кнопкой без бейджа
    work = W.READ
    app_steps.wait_ui_ready(driver)
    browser_steps.open_listing(driver, rb.LISTING_BASIC_URL)

    # When пользователь нажимает Rate-кнопку блёрба W; в открывшемся нативном
    # bottom-sheet (RatingOverlay) выбирает рейтинг Read
    browser_steps.tap_rate_button(driver, work.ao3_id)
    rating_steps.rate_via_listing_overlay(driver, "READ")

    # Then на карточке блёрба W на листинге появляется бейдж рейтинга — наблюдаемое
    # подтверждение полного round-trip (JS-клик -> Android.rateWork -> Room ->
    # broadcastRatingChange -> window.applyRatings), без перезагрузки листинга.
    # Это НЕ полный Then TC-009 (нет проверки вкладки Library) — фикстура
    # доказывается достаточной для входа в сценарий, не весь кейс закодирован здесь.
    browser_steps.assert_rating_badge_visible(driver, work.ao3_id)
