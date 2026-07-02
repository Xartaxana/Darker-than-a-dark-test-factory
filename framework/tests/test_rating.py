"""Тесты области rating: простановка/снятие рейтинга через встроенную панель
работы (`RatingMenu` в `WorkRatingPanel`, см. app-under-test ui/browser/BottomBar.kt).

Дизайн следует test_library.py: точечные live-сценарии (открытие /works/{id})
неизбежны для панели работы — сеть AO3 не проверяется по содержимому, только
что приложение достигло страницы работы (onWorkPageLoaded) и панель реагирует.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.data import seed_db
from framework.steps import app_steps, library_steps, rating_steps


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-007")
@allure.title("Простановка рейтинга {rating} со страницы работы (панель)")
@pytest.mark.parametrize("rating,work", [
    ("SAVE", W.LOVED), ("LIKE", W.KUDOSED), ("READ", W.READ),
    ("PENDING", W.PENDING), ("DISLIKE", W.DISLIKED),
])
def test_rate_work_from_work_page_panel(driver, rating, work):
    # Given приложение с чистыми данными, ни один из 5 рейтингов ещё не выбран
    app_steps.clean_state()
    app_steps.wait_ui_ready(driver)

    # When пользователь открывает страницу работы и через панель RatingMenu
    # выставляет рейтинг R
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.rate_current_work(driver, rating)

    # Then работа W появляется в соответствующей вкладке Library — наблюдаемое
    # подтверждение того, что панель проставила рейтинг и он сохранён в Room
    # (без перезагрузки WebView, без прямого обращения к БД из UI-теста)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, rating, work.title)


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-008")
@allure.title("Повторный тап по выбранному рейтингу снимает его (deselect, панель работы)")
def test_deselect_rating_on_work_page_panel(driver):
    # Given работа W засеяна с рейтингом Loved (SAVE) и присутствует во вкладке FAVORITE
    app_steps.clean_state()
    seed_db.seed([(W.LOVED, "SAVE")])
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", W.LOVED.title)

    # When пользователь открывает страницу работы W и повторно нажимает уже
    # выбранную кнопку «Favorite» (Loved) на панели RatingMenu
    rating_steps.open_work_page(driver, W.LOVED.ao3_id)
    rating_steps.rate_current_work(driver, "SAVE")

    # Then работа W больше не отображается во вкладке FAVORITE экрана Library —
    # наблюдаемое подтверждение deselect (rating сброшен в null)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "SAVE", W.LOVED.title)
