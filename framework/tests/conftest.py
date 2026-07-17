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
def library_all_one_rating_seeded():
    """5 работ `works.ALL` засеяны с ОДНИМ рейтингом (PENDING) — все пять оказываются
    на одной вкладке Library, что нужно для TC-027 (фильтр word count)/TC-029
    (фильтр по фандому): фильтр сравнивает работы в пределах одной вкладки, а не
    вперемешку с рейтинговой раскладкой по вкладкам (см. заметки в телах кейсов).
    Порядок (clean_state до сессии Appium) — тот же контракт, что и seeded_library."""
    app_steps.clean_state()
    app_steps.seed_library([(w, "PENDING") for w in W.ALL])
    yield W.ALL


@pytest.fixture()
def library_wordcount_scroll_seeded():
    """`works.ALL` + `works.SCROLL_FILLERS` (10 доп. работ с малым word_count), все с
    ОДНИМ рейтингом (PENDING) на одной вкладке — список выше высоты экрана, нужен
    для TC-030 (проверка сброса скролла при смене сортировки на Word count high-to-low:
    филлеры с малым word_count гарантированно уходят в конец после сортировки, не
    мешая проверке относительного порядка пяти эталонных работ)."""
    app_steps.clean_state()
    rows = [(w, "PENDING") for w in W.ALL] + [(w, "PENDING") for w in W.SCROLL_FILLERS]
    app_steps.seed_library(rows)
    yield W.ALL


@pytest.fixture()
def library_downloaded_only_seeded():
    """3 работы с одним рейтингом (SAVE/Favorite): 2 без файла (downloadPath=null), 1 —
    с уже «скачанным» локальным файлом (downloadPath заполнен, файл реально существует
    на устройстве) — без сетевого скачивания, тот же приём, что и downloaded_work_seeded
    (TC-034/035/036). Нужна для TC-028 (фильтр downloaded-only).

    Сидинг в ДВА последовательных вызова: сначала обе без-файловые строки через
    `seed_library` (seed_db.seed), затем файловая — через `seed_downloaded_work`
    (seed_db.seed_with_download). Второй вызов пуллит уже записанную первым вызовом
    БД с устройства и ДОБАВЛЯЕТ свою строку (INSERT OR REPLACE по ao3Id, см.
    seed_db._insert_rows_with_download) — прежние две строки не затираются, это тот
    же паттерн, каким уже сосуществуют последовательные сидинг-вызовы в этом файле.
    Порядок (clean_state до сессии Appium) — тот же контракт, что и остальные
    фикстуры данных."""
    app_steps.clean_state()
    app_steps.seed_library([(W.KUDOSED, "SAVE"), (W.READ, "SAVE")])
    app_steps.seed_downloaded_work(W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE)
    yield {"downloaded": W.LOVED, "no_file": [W.KUDOSED, W.READ]}


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
def two_filter_profiles_seeded():
    """Два фильтр-профиля ("Profile A"/"Profile B", различимые queryString) засеяны
    в `filter_profiles` ДО старта сессии Appium — тот же порядок обязателен, что и
    `seeded_library` (AT-BUG-006, грань 3: TC-042 требует ДВА одновременных профиля,
    чтобы отличить «удалён именно нужный» от «весь список случайно очищен»).
    `seed_db.seed_filter_profiles` генерирует `id`/`timestamp` сама — вызывающему
    коду (кейсам) они не нужны, сверка по имени/queryString."""
    app_steps.clean_state()
    app_steps.seed_filter_profiles([
        ("Profile A", "work_search%5Bquery%5D=profile-a-test"),
        ("Profile B", "work_search%5Bquery%5D=profile-b-test"),
    ])
    yield ("Profile A", "Profile B")


_ca_checked = False  # AT-BUG-011: fail-fast проверка mitm-CA — один раз на сессию


def _ensure_replay_ca() -> None:
    """Предусловие replay-тестов (AT-BUG-011): без mitm-CA в системном APEX-сторе
    WebView отвергает TLS к mitmproxy, и тест виснет `ReadTimeoutError` через
    120–240с (APPIUM_HTTP_TIMEOUT x rerun-гейт AT-BUG-007) вместо мгновенной
    понятной ошибки. Кешируется в module-level `_ca_checked` — проверяется
    (adb + openssl вызов) один раз на первом replay-тесте сессии, не на каждом."""
    global _ca_checked
    if _ca_checked:
        return
    if not mitm.is_ca_installed():
        raise RuntimeError(
            "mitm-CA отсутствует в системном сторе доверия (стирается любым "
            "ребутом эмулятора без -writable-system) — поднимите среду "
            "`Start-Emulator -WritableSystem` или выполните "
            "`Install-MitmCA`/`bash scripts/install-mitm-ca.sh` (AT-BUG-011)."
        )
    _ca_checked = True


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
    доказан спайком B, до этой фикстуры не был подключён ни к одному тесту).
    Перед стартом проверяет присутствие CA (`_ensure_replay_ca`, AT-BUG-011) —
    падает мгновенно и явно вместо таймаута, если среда поднята без CA."""
    _ensure_replay_ca()
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
