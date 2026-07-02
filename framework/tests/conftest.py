"""Фикстуры и хуки прогона.

Стратегия состояния: тесты стартуют из известного состояния через фикстуры
(clean_app / seeded_library), порядок тестов не важен. Артефакты падения крепятся
автоматически хуком pytest_runtest_makereport.
"""
from __future__ import annotations

import pytest

from framework.core import adb, driver_factory, reporting
from framework.data import works as W
from framework.steps import app_steps


def pytest_configure(config):
    config.addinivalue_line("markers", "p0: smoke — гоняется на каждой сборке")
    config.addinivalue_line("markers", "p1: регрессия")
    config.addinivalue_line("markers", "live: требует живого AO3")
    config.addinivalue_line("markers", "replay: требует replay-прокси")


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    if not adb.is_installed():
        adb.install()
    yield


@pytest.fixture()
def driver():
    """Сессия Appium на тест. no_reset=True — состоянием управляют фикстуры данных."""
    drv = driver_factory.create_driver(no_reset=True)
    yield drv
    driver_factory.quit_driver(drv)


@pytest.fixture()
def clean_app():
    """Чистое приложение (pm clear) ДО старта сессии. Возвращает фабрику драйвера."""
    app_steps.clean_state()
    yield


@pytest.fixture()
def seeded_library():
    """Библиотека с по одной работе на каждый рейтинг (без обращения к AO3).
    Сидинг делается до создания сессии Appium."""
    app_steps.clean_state()
    app_steps.seed_library([
        (W.LOVED, "SAVE"),
        (W.KUDOSED, "LIKE"),
        (W.READ, "READ"),
        (W.PENDING, "PENDING"),
        (W.DISLIKED, "DISLIKE"),
    ])
    yield W


@pytest.fixture()
def loved_work_seeded():
    """Работа LOVED засеяна с рейтингом SAVE (Favorite) до старта сессии Appium —
    тот же порядок обязателен, что и в `seeded_library`/`comment_only_work`: иначе
    driver успевает запустить приложение до сидинга, а `pm clear`/сидинг после
    запуска сессии не перезапускает уже работающий процесс (WebView остаётся в
    неопределённом состоянии — см. TC-008)."""
    app_steps.clean_state()
    app_steps.seed_library([(W.LOVED, "SAVE")])
    yield W.LOVED


@pytest.fixture()
def placeholder_seeded_work(request):
    """Работа `request.param` засеяна как placeholder БЕЗ рейтинга (rating=None), но
    с полными title/author/fandom/wordCount — до старта сессии Appium (тот же порядок,
    что и `seeded_library`). Нужна для TC-007: `savePanelRating` (BrowserViewModel.kt)
    скрейпит title/author из живого DOM страницы работы только когда для `workId` ещё
    нет строки в Room; для синтетических `ao3_id` (не существующих на archiveofourown.org)
    скрейп страницы вернёт пустые поля. Предзаполненный placeholder переводит панель на
    ветку "обновить существующую строку" — без сетевого скрейпа, см. test_rating.py."""
    work = request.param
    app_steps.clean_state()
    app_steps.seed_with_comment([(work, None, None, None)])
    yield work


@pytest.fixture()
def comment_only_work():
    """Одна работа засеяна как comment-only (rating=NULL, непустой comment) —
    без обращения к AO3. Сидинг делается до создания сессии Appium (см.
    seeded_library — тот же порядок обязателен, иначе драйвер успевает
    запустить приложение раньше сидинга)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.KUDOSED, None, "test note", None)])
    yield W.KUDOSED


# --- Артефакты падений ---
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        drv = item.funcargs.get("driver")
        if drv is not None:
            reporting.attach_failure_artifacts(drv, item.name)
