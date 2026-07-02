"""Тесты области rating: простановка/снятие рейтинга через встроенную панель
работы (`RatingMenu` в `WorkRatingPanel`, см. app-under-test ui/browser/BottomBar.kt).

Дизайн следует test_library.py: точечные live-сценарии (открытие /works/{id})
неизбежны для панели работы — сеть AO3 не проверяется по содержимому, только
что приложение достигло страницы работы (onWorkPageLoaded) и панель реагирует.

Важная особенность `savePanelRating` (BrowserViewModel.kt): если для `workId` ещё
нет строки в Room, панель СНАЧАЛА скрейпит title/author/fandom/wordCount из живого
DOM страницы работы (`workInfoJs`, селекторы `h2.title.heading` и т.д.) и только
затем сохраняет рейтинг. Наши `ao3_id` из `framework/data/works.py` синтетические
(не существуют на archiveofourown.org) — на реальном сайте такая страница отдаёт
404, скрейп возвращает пустые строки, и запись сохраняется с рейтингом, но БЕЗ
title/author (проверено на живом прогоне: "0 words", без имени). Поэтому здесь
предварительно сеется placeholder-строка (`rating=None`, но с полными
title/author/fandom/wordCount) — тогда `savePanelRating` идёт по ветке
`existing != null` (просто обновляет rating на уже существующей строке, без
обращения к DOM), и тест проверяет именно способность панели проставить/сохранить
рейтинг, а не сетевой скрейп (не являющийся предметом TC-007).
"""
from __future__ import annotations

import allure
import pytest

from framework.data import works as W
from framework.steps import app_steps, library_steps, rating_steps


@pytest.mark.p0
@pytest.mark.live
@allure.id("TC-007")
@allure.title("Простановка рейтинга {rating} со страницы работы (панель)")
@pytest.mark.parametrize(
    "rating,placeholder_seeded_work",
    [
        ("SAVE", W.LOVED), ("LIKE", W.KUDOSED), ("READ", W.READ),
        ("PENDING", W.PENDING), ("DISLIKE", W.DISLIKED),
    ],
    indirect=["placeholder_seeded_work"],
)
def test_rate_work_from_work_page_panel(placeholder_seeded_work, driver, rating):
    # Given приложение с чистыми данными и placeholder-строкой работы W без
    # рейтинга (rating=None, но title/author/fandom/wordCount заполнены — см.
    # docstring модуля и фикстуру `placeholder_seeded_work`), ни один из 5
    # рейтингов ещё не выбран. Сидинг выполнен фикстурой ДО старта сессии Appium.
    work = placeholder_seeded_work
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
def test_deselect_rating_on_work_page_panel(loved_work_seeded, driver):
    # Given работа W засеяна с рейтингом Loved (SAVE) и присутствует во вкладке FAVORITE
    # (сидинг выполнен фикстурой `loved_work_seeded` ДО старта сессии Appium)
    work = loved_work_seeded
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # When пользователь открывает страницу работы W и повторно нажимает уже
    # выбранную кнопку «Favorite» (Loved) на панели RatingMenu
    rating_steps.open_work_page(driver, work.ao3_id)
    # Панель RatingMenu рендерится только на вкладке Browse (isWorkPage) — после
    # проверки Library (см. Given выше) возвращаемся на нативную вкладку Browse,
    # иначе она остаётся скрыта за AnimatedVisibility (BottomBar.kt) на Library.
    app_steps.open_tab(driver, "Browse")
    rating_steps.rate_current_work(driver, "SAVE")

    # Then работа W больше не отображается во вкладке FAVORITE экрана Library —
    # наблюдаемое подтверждение deselect (rating сброшен в null)
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_not_in_tab(driver, "SAVE", work.title)
