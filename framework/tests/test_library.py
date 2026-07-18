"""Тесты экрана Library вне базового smoke-набора (переносы между вкладками,
comment-only записи и т.д.). Дизайн следует test_smoke.py: минимизируем сеть,
но точечные live-сценарии (открытие /works/{id}) неизбежны для проверки
взаимодействия панели RatingMenu с Library.

Важно: сидинг (clean_state/seed_db) выполняется ДО создания сессии Appium
(в фикстуре `seeded_library`), а не в теле теста — иначе гонка с автозапуском
приложения драйвером при создании сессии (см. seeded_library в conftest.py).
"""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps, library_steps, rating_steps


@pytest.mark.p2
@allure.id("TC-006")
@allure.title("Подписи вкладок Library соответствуют фактическому UI (порядок и текст)")
def test_library_tab_labels(clean_app, driver):
    # Given приложение запущено с чистыми данными (сидинг не требуется — набор
    # вкладок статический) и открыт экран Library
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")

    # When пользователь смотрит на панель вкладок
    # Then подписи слева направо, верхний регистр:
    # FAVORITE, KUDOSED, READ, PENDING, DISLIKED, FILES
    library_steps.assert_library_tabs_order(driver, [
        "FAVORITE", "KUDOSED", "READ", "PENDING", "DISLIKED", "FILES",
    ])


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-016")
@allure.title("Смена рейтинга перемещает work из одной вкладки Library в другую")
def test_change_rating_moves_work_between_tabs(seeded_library, driver):
    # Given работа KUDOSED засеяна с рейтингом Liked и присутствует во вкладке KUDOSED
    work = seeded_library.KUDOSED
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "LIKE", work.title)

    # When пользователь открывает страницу работы W и меняет рейтинг на Loved
    rating_steps.open_work_page(driver, work.ao3_id)
    # Панель RatingMenu рендерится только на вкладке Browse (isWorkPage), поэтому
    # после навигации WebView возвращаемся на нативную вкладку Browse.
    app_steps.open_tab(driver, "Browse")
    rating_steps.rate_current_work(driver, "SAVE")

    # Then вкладка KUDOSED больше не содержит работу W, а FAVORITE — содержит
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "LIKE", work.title)
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)


@pytest.mark.p0
@allure.id("TC-017")
@allure.title("Comment-only запись (rating=null) не появляется ни в одной рейтинговой вкладке Library")
def test_comment_only_not_in_any_rating_tab(comment_only_work, driver):
    # Given работа W засеяна как comment-only (rating=NULL, comment не пуст)
    work = comment_only_work
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")

    # Then ни в одной из пяти рейтинговых вкладок работа W не отображается
    for rating in ("SAVE", "LIKE", "READ", "PENDING", "DISLIKE"):
        library_steps.assert_work_not_in_tab(driver, rating, work.title)
