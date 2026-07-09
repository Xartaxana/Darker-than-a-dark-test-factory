"""Фикстуры и хуки прогона.

Стратегия состояния: тесты стартуют из известного состояния через фикстуры
(clean_app / seeded_library), порядок тестов не важен. Артефакты падения крепятся
автоматически хуком pytest_runtest_makereport.
"""
from __future__ import annotations

import pytest

from framework.config import settings
from framework.core import adb, driver_factory, mitm, reporting
from framework.data import works as W
from framework.steps import app_steps

_DOWNLOADED_WORK_FIXTURE = settings.DATA_DIR / "fixtures" / "downloaded_work.html"


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
def downloaded_work_seeded():
    """Работа LOVED засеяна с рейтингом Loved (SAVE) и уже «скачанным» локальным
    HTML-файлом (downloadPath заполнен, файл реально существует на устройстве) —
    без сетевого скачивания (DownloadRepository не задействован), см.
    TC-034/TC-035/TC-036. Тот же порядок (clean_state до сессии Appium), что и
    seeded_library/loved_work_seeded — обязателен."""
    app_steps.clean_state()
    app_steps.seed_downloaded_work(W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE)
    yield W.LOVED


@pytest.fixture()
def comment_only_work():
    """Одна работа засеяна как comment-only (rating=NULL, непустой comment) —
    без обращения к AO3. Сидинг делается до создания сессии Appium (см.
    seeded_library — тот же порядок обязателен, иначе драйвер успевает
    запустить приложение раньше сидинга)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.KUDOSED, None, "test note", None)])
    yield W.KUDOSED


@pytest.fixture()
def replay(request):
    """Поднимает mitmdump в режиме server-replay на записи `request.param` (имя файла
    в `framework/data/recordings/`) и направляет прокси устройства на него на время
    теста; гарантированный teardown возвращает прокси и глушит mitmdump независимо от
    исхода теста. Параметризуется indirect'ом (см. `test_visibility.py`) —
    `@pytest.mark.parametrize("replay", [<filename>], indirect=True)`.

    Требует `@pytest.mark.replay` на тесте (см. `pytest_configure`) и окружение,
    доведённое до Спайка B: эмулятор запущен с `-writable-system`
    (`Start-Emulator -WritableSystem`) и CA mitmproxy установлен
    (`bash scripts/install-mitm-ca.sh`) — см. `docs/environment-setup.md`.
    Подключение к conftest — часть AT-BUG-004, инкремент 1 (сам механизм record→replay
    доказан спайком B, до этой фикстуры не был подключён ни к одному тесту)."""
    flow_name = request.param
    flows_file = settings.RECORDINGS_DIR / flow_name
    assert flows_file.exists(), (
        f"replay-запись не найдена: {flows_file} "
        f"(сгенерировать: python scripts/build_replay_recordings.py)"
    )
    try:
        mitm.set_device_proxy()
        mitm.start_replay(flows_file)
        yield flows_file
    finally:
        # clear_device_proxy идемпотентен (check=False, ставит ":0" безусловно) —
        # безопасно звать даже если set_device_proxy выше не выполнился/упал:
        # teardown должен покрывать ЛЮБую точку отказа setup'а, не только yield.
        mitm.stop()
        mitm.clear_device_proxy()


# --- Артефакты падений ---
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        drv = item.funcargs.get("driver")
        if drv is not None:
            reporting.attach_failure_artifacts(drv, item.name)
