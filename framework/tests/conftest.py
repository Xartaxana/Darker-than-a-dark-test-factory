"""Фикстуры и хуки прогона.

Стратегия состояния: тесты стартуют из известного состояния через фикстуры
(clean_app / seeded_library), порядок тестов не важен. Артефакты падения крепятся
автоматически хуком pytest_runtest_makereport.
"""
from __future__ import annotations

import json

import pytest

from framework.config import settings
from framework.core import adb, driver_factory, mitm, reporting
from framework.data import recording_builder as rb
from framework.data import works as W
from framework.data.works import Work
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
def library_word_count_boundary_seeded():
    """`works.ALL` + два work'а с word_count РОВНО на границах диапазона фильтра
    ([1000, 5000] — `WORD_COUNT_MIN_BOUNDARY`/`WORD_COUNT_MAX_BOUNDARY`), все с
    ОДНИМ рейтингом (PENDING) на одной вкладке — нужно для TC-027 (C4-ретрофит
    2026-07-18): доказать включительность границ фильтра (`>= min`/`<= max`),
    непроверяемую на исходной пятёрке `ALL` (ни одно её значение не совпадает
    с 1000/5000 точно). ОТДЕЛЬНАЯ фикстура от `library_all_one_rating_seeded`
    (не расширяет её состав) — та же пятёрка используется TC-029 (фильтр по
    фандому), которому 2 лишние работы не нужны."""
    app_steps.clean_state()
    rows = [(w, "PENDING") for w in W.ALL] + [
        (W.WORD_COUNT_MIN_BOUNDARY, "PENDING"),
        (W.WORD_COUNT_MAX_BOUNDARY, "PENDING"),
    ]
    app_steps.seed_library(rows)
    yield W.ALL + [W.WORD_COUNT_MIN_BOUNDARY, W.WORD_COUNT_MAX_BOUNDARY]


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
def library_null_wordcount_seeded():
    """TC-031: 2 работы с валидным word_count (READ=800, LOVED=4200) +
    `works.NULL_WORD_COUNT_TARGET` (word_count=None), все три с ОДНИМ рейтингом
    (PENDING) на одной вкладке — граница отсутствующего word_count в сортировке
    (AT-BUG-010, Fixed). `seed_library`/`seed()` уже достаточно — `Work.word_count`
    типизирован `int | None`, `seed_with_comment` не нужен (rating не NULL, comment/
    tags не участвуют)."""
    app_steps.clean_state()
    app_steps.seed_library([
        (W.READ, "PENDING"),
        (W.LOVED, "PENDING"),
        (W.NULL_WORD_COUNT_TARGET, "PENDING"),
    ])
    yield {"with_wordcount": [W.READ, W.LOVED], "null_wordcount": W.NULL_WORD_COUNT_TARGET}


@pytest.fixture()
def library_tags_and_seeded():
    """TC-060: 3 работы с ОДНИМ рейтингом (SAVE), различающиеся только `tags` —
    W1 оба выбранных тега, W2 только один (частичное пересечение), W3 ни одного.
    Работы не входят в `works.ALL` (специфичны для этого кейса) — созданы напрямую,
    тот же приём, что и `NULL_WORD_COUNT_TARGET`/`WORD_COUNT_MIN_BOUNDARY`."""
    app_steps.clean_state()
    w1 = Work("900000601", "TC-060 Both Tags Work", "seed_author_tc060_w1", "Fandom TC060", 1000)
    w2 = Work("900000602", "TC-060 One Tag Work", "seed_author_tc060_w2", "Fandom TC060", 1000)
    w3 = Work("900000603", "TC-060 No Match Work", "seed_author_tc060_w3", "Fandom TC060", 1000)
    app_steps.seed_with_comment([
        (w1, "SAVE", None, json.dumps(["fluff", "hurt-comfort"])),
        (w2, "SAVE", None, json.dumps(["fluff"])),
        (w3, "SAVE", None, json.dumps(["canon-divergent"])),
    ])
    yield (w1, w2, w3)


@pytest.fixture()
def library_freetext_search_seeded():
    """TC-061: 3 работы с ОДНИМ рейтингом (SAVE) — только W1 содержит подстроку
    "wintersong" (в `comment`), W2/W3 не содержат её ни в одном текстовом поле
    (title/author/fandom/tags/comment)."""
    app_steps.clean_state()
    w1 = Work("900000611", "TC-061 Match In Comment Work", "seed_author_tc061_w1",
              "Fandom TC061 Alpha", 1000)
    w2 = Work("900000612", "TC-061 No Match Work Two", "seed_author_tc061_w2",
              "Fandom TC061 Beta", 1000)
    w3 = Work("900000613", "TC-061 No Match Work Three", "seed_author_tc061_w3",
              "Fandom TC061 Gamma", 1000)
    app_steps.seed_with_comment([
        (w1, "SAVE", "Reread this every wintersong", None),
        (w2, "SAVE", None, None),
        (w3, "SAVE", None, None),
    ])
    yield (w1, w2, w3)


@pytest.fixture()
def library_last_read_order_seeded():
    """TC-062: 3 работы с ОДНИМ рейтингом (SAVE), засеянные ТРЕМЯ ПОСЛЕДОВАТЕЛЬНЫМИ
    вызовами `seed_with_comment` (по одной работе на вызов — разные `timestamp`, см.
    заметки TC-062 про `now`, вычисляемый один раз на батч) в хронологическом
    порядке Mango -> Apple -> Zebra. Заголовки подобраны так, чтобы ни порядок
    вставки, ни алфавит не совпадали с ожидаемым порядком по `timestamp`
    (Zebra, Apple, Mango)."""
    app_steps.clean_state()
    mango = Work("900000621", "Mango Work", "seed_author_tc062_mango", "Fandom TC062", 1000)
    apple = Work("900000622", "Apple Work", "seed_author_tc062_apple", "Fandom TC062", 1000)
    zebra = Work("900000623", "Zebra Work", "seed_author_tc062_zebra", "Fandom TC062", 1000)
    app_steps.seed_with_comment([(mango, "SAVE", None, None)])
    app_steps.seed_with_comment([(apple, "SAVE", None, None)])
    app_steps.seed_with_comment([(zebra, "SAVE", None, None)])
    yield (mango, apple, zebra)


@pytest.fixture()
def library_author_sort_seeded():
    """TC-064: 3 работы с ОДНИМ рейтингом (PENDING) — W1 author="Zoe Martinez",
    W2 author="Amy Chen", W3 author="" (пустой, допустим схемой) — плюс
    `works.SCROLL_FILLERS` (непустой author) для гарантированного скролла, тот
    же приём, что TC-030/TC-063."""
    app_steps.clean_state()
    w1 = Work("900000641", "TC-064 Zoe Work", "Zoe Martinez", "Fandom TC064", 1000)
    w2 = Work("900000642", "TC-064 Amy Work", "Amy Chen", "Fandom TC064", 1000)
    w3 = Work("900000643", "TC-064 Empty Author Work", "", "Fandom TC064", 1000)
    rows = [(w1, "PENDING"), (w2, "PENDING"), (w3, "PENDING")] + [
        (w, "PENDING") for w in W.SCROLL_FILLERS
    ]
    app_steps.seed_library(rows)
    yield (w1, w2, w3)


@pytest.fixture()
def library_files_rating_seeded():
    """TC-065: `works.ALL`, каждая с рейтингом, соответствующим её "естественному"
    имени (LOVED=SAVE, KUDOSED=LIKE, READ=READ, PENDING=PENDING, DISLIKED=DISLIKE —
    тот же маппинг, что `seeded_library`), и с уже «скачанным» локальным HTML-файлом
    (общий переиспользуемый файл `_DOWNLOADED_WORK_FIXTURE`, downloadPath заполнен) —
    все 5 видны на вкладке Files. Засеяны ОДНИМ батчем в порядке DISLIKED, PENDING,
    READ, KUDOSED, LOVED (обратном ожидаемому результату сортировки Rating) —
    защита от случайного совпадения результата с порядком вставки."""
    app_steps.clean_state()
    app_steps.seed_downloaded_works([
        (W.DISLIKED, "DISLIKE", _DOWNLOADED_WORK_FIXTURE),
        (W.PENDING, "PENDING", _DOWNLOADED_WORK_FIXTURE),
        (W.READ, "READ", _DOWNLOADED_WORK_FIXTURE),
        (W.KUDOSED, "LIKE", _DOWNLOADED_WORK_FIXTURE),
        (W.LOVED, "SAVE", _DOWNLOADED_WORK_FIXTURE),
    ])
    yield W.ALL


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
def disliked_work_with_tags_seeded():
    """TC-045: ПАРА работ с ОДИНАКОВЫМИ личными тегами, различающихся только
    `rating` — доказывает независимость видимости от `tags` как СВОЙСТВО, не на
    единичном примере (test-reviewer changes_requested, 2026-07-18): `W.DISLIKED`
    (скрывается фильтрацией по умолчанию — Disliked в hidden-set) и `W.LOVED`
    (rating=SAVE, НЕ в hidden-set) засеяны с ОДНИМ и тем же набором тегов
    `["spoiler", "reread-candidate"]`. Если бы `tags` хоть как-то влияли на
    excluded/visible, одинаковые теги дали бы одинаковый исход для обеих работ —
    вместо этого исход противоположный (DISLIKED скрыта, LOVED видна), что и
    доказывает, что переключает видимость исключительно `rating`
    (`applyAllFilters`, `ao3_bridge.js`, читает только `ratings[workId]`/`hidden`,
    см. TC-045.md «Причина»)."""
    app_steps.clean_state()
    tags = json.dumps(["spoiler", "reread-candidate"])
    app_steps.seed_with_comment([
        (W.DISLIKED, "DISLIKE", None, tags),
        (W.LOVED, "SAVE", None, tags),
    ])
    yield W.DISLIKED, W.LOVED


@pytest.fixture()
def tagged_work_seeded():
    """TC-056: работа `works.LOVED` засеяна с рейтингом LIKE и личными тегами
    `["Fluff", "Angst"]` — «Fluff» совпадает (без учёта регистра) с freeform-тегом
    карточки, зашитым в КАЖДЫЙ блёрб `listing_basic.mitm`
    (`recording_builder._blurb_html`), «Angst» не совпадает ни с одним AO3-тегом
    фикстуры."""
    app_steps.clean_state()
    app_steps.seed_with_comment([
        (W.LOVED, "LIKE", None, json.dumps(["Fluff", "Angst"])),
    ])
    yield W.LOVED


@pytest.fixture()
def note_work_seeded():
    """TC-044: работа `works.READ` засеяна с рейтингом LIKE и непустым комментарием —
    Note-кнопка (карандаш) на листинге инжектируется `applyRatings` только когда для
    работы есть непустой `comment` (см. `ao3_bridge.js`)."""
    app_steps.clean_state()
    app_steps.seed_with_comment([(W.READ, "LIKE", "Existing note text", None)])
    yield W.READ


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


@pytest.fixture()
def filter_profile_applied_seeded():
    """Один фильтр-профиль ("My saved search") засеян ДО старта сессии Appium (тот
    же порядок, что `two_filter_profiles_seeded`) — TC-041: применение сохранённого
    профиля из FilterPanel листинга.

    `queryString` — НЕ произвольная строка (в отличие от `two_filter_profiles_seeded`,
    где кейс TC-042 никогда не навигирует по ней): это РОВНО
    `recording_builder.FILTER_APPLIED_QUERY_STRING`, подобранный так, что
    `applyFilter` (BrowserViewModel.kt) построит URL, БАЙТ-В-БАЙТ совпадающий с
    `recording_builder.LISTING_FILTERED_URL` — вторым flow, записанным в
    `listing_basic.mitm` (`scripts/build_replay_recordings.py::build_listing_basic`).
    Без этого совпадения server-replay не находит flow и уходит в live-сеть
    (`server_replay_extra=forward`) — см. докстринг `LISTING_FILTERED_URL`."""
    app_steps.clean_state()
    app_steps.seed_filter_profiles([("My saved search", rb.FILTER_APPLIED_QUERY_STRING)])
    yield "My saved search"


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
    падает мгновенно и явно вместо таймаута, если среда поднята без CA.
    После `set_device_proxy()`+`start_replay()` ждёт достижимости прокси СО
    СТОРОНЫ УСТРОЙСТВА (`mitm.wait_device_proxy_reachable`, AT-BUG-017) — до
    `yield`: `start_replay()` подтверждает готовность только хост-порта, а
    первая навигация теста иногда ловила интермиттентный
    `net::ERR_PROXY_CONNECTION_FAILED` (race NAT-уровня qemu / задержка
    применения системной настройки прокси Android'ом), не покрытый
    rerun-whitelist `pytest.ini` — тест теперь не видит этот транзиент."""
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
        mitm.wait_device_proxy_reachable()
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
