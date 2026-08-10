"""Device-free юниты для двух новых replay-фикстур (батч мелочей 2026-07-28,
`docs/HANDOFF.md` «Батч мелочей (новый, 2026-07-28)» пункт (а)) —
`listing_paginated.mitm` (эксплораторная клетка «infinite scroll/пагинация»,
`CH-005 mission_leftover`, ПЯТЬ страниц — доработка attempt 2, критик-вход B2)
и `works_multi.mitm` (`CH-005 mission_leftover` Г7, live-push на старых
вкладках), плюс `listing_basic.mitm` (доработка attempt 2, критик-вход B3,
`AT-BUG-029`, `Fixed` — недостающая `.html`-транзакция для TC-115).

Парсинг СОБРАННЫХ `.mitm`-файлов через `mitmproxy.io.FlowReader` — симметрично
тому, как `recording_builder.write_flows`/`FlowWriter` их пишет — без
устройства/Appium. Требует, чтобы `framework/.venv/Scripts/python.exe
scripts/build_replay_recordings.py` уже отработал (файлы лежат в
`settings.RECORDINGS_DIR`, коммитятся как остальные `.mitm`-фикстуры этого
пакета).

Переопределяет `_ensure_app_installed` (тот же приём, что
`test_seed_filter_profiles_unit.py`/`test_device_liveness_guard_unit.py`) —
модуль не трогает устройство; `download_oracle` (`conftest.py`) сам себя
пропускает по отсутствию фикстуры `driver` в этом модуле.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import allure
import pytest
from mitmproxy.io import FlowReader

from framework.config import settings
from framework.data import recording_builder as rb
from framework.data.works import ALL as ALL_WORKS


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля)."""
    yield


def _read_flows(path: Path) -> list:
    with open(path, "rb") as fo:
        return list(FlowReader(fo).stream())


_HREF_RE = re.compile(r'href="([^"]+)"')


def _extract_ol_blocks(html_body: str, class_needle: str) -> list[str]:
    """Достаёт ВСЕ `<ol class="...{class_needle}...">...</ol>` блоки, не только
    первый — узкий, не полноценный HTML-парсер, но достаточный для проверки
    инварианта на синтетической, контролируемой самим генератором разметке.

    Критично со времени F3 (доработка attempt 2): каждая страница
    `listing_paginated.mitm` несёт пагинационный блок ДВАЖДЫ (сверху и снизу
    листинга). Функция, читающая только ПЕРВЫЙ блок, слепа к непокрытому href,
    оказавшемуся ТОЛЬКО во втором — это и есть блокер, найденный критик-входом
    attempt 3 (проба критика: верхний блок покрыт, нижний несёт непокрытый
    `...&page=77` — старая версия `_pagination_hrefs` возвращала `True`,
    хотя ссылка реально увела бы `server_replay_extra=forward` в live,
    AT-BUG-006)."""
    needle = f'<ol class="{class_needle}'
    blocks = []
    pos = 0
    while True:
        start = html_body.find(needle, pos)
        if start == -1:
            break
        end = html_body.index("</ol>", start) + len("</ol>")
        blocks.append(html_body[start:end])
        pos = end
    return blocks


def _extract_ol_block(html_body: str, class_needle: str) -> str:
    """Первый блок из `_extract_ol_blocks` — используется ТОЛЬКО там, где важна
    структура/присутствие (оба блока страницы идентичны по построению, см.
    `test_listing_paginated_top_and_bottom_pagination_blocks_are_identical`),
    НЕ для проверки полноты покрытия href (для этого — `_pagination_hrefs`,
    которая обязана агрегировать ВСЕ блоки, не только первый)."""
    return _extract_ol_blocks(html_body, class_needle)[0]


def _pagination_hrefs(html_body: str, page_url: str) -> set[str]:
    """Href ИЗ ВСЕХ пагинационных блоков страницы (`_extract_ol_blocks` —
    страница несёт блок пагинации ДВАЖДЫ, F3), РЕЗОЛВЛЕННЫЕ в абсолютные URL
    через `urljoin(page_url, href)` (доработка attempt 2, критик-вход F2 —
    реальный AO3, и теперь наша фикстура, рендерит href HOST-RELATIVE, не
    абсолютными). Форма-граница: распознаёт только href в ДВОЙНЫХ кавычках
    (`_HREF_RE` — `href="..."`) — генератор (`recording_builder.py`) всегда
    рендерит атрибуты двойными кавычками, одинарные/без кавычек не
    поддерживаются этим узким regex-парсером."""
    raw_hrefs: set[str] = set()
    for block in _extract_ol_blocks(html_body, "pagination"):
        raw_hrefs.update(_HREF_RE.findall(block))
    return {urljoin(page_url, href) for href in raw_hrefs}


def _pagination_hrefs_covered(html_body: str, page_url: str, recorded_urls: set[str]) -> bool:
    """Инвариант AT-BUG-006 (`bugs/AT-BUG-006.md`): КАЖДЫЙ href КАЖДОГО
    пагинационного блока страницы (резолвленный относительно `page_url`)
    обязан быть среди `recorded_urls` — иначе `server-replay` не находит
    совпадения и уходит в live-сеть через `server_replay_extra=forward`."""
    return _pagination_hrefs(html_body, page_url).issubset(recorded_urls)


# --- listing_paginated.mitm ---

@pytest.fixture(scope="module")
def listing_paginated_flows():
    path = settings.RECORDINGS_DIR / rb.LISTING_PAGINATED_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py ({path})"
    )
    return _read_flows(path)


@pytest.fixture(scope="module")
def listing_paginated_recorded_urls(listing_paginated_flows) -> set[str]:
    return {f.request.url for f in listing_paginated_flows}


def _listing_page_body(listing_paginated_flows, page: int) -> str:
    url = rb.listing_paginated_page_url(page)
    flow = next(f for f in listing_paginated_flows if f.request.url == url)
    return flow.response.get_text()


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-page1-has-pagination")
@allure.title("listing_paginated.mitm: страница 1 несёт ol.pagination")
def test_listing_paginated_page1_has_pagination_block(listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, 1)
    assert 'class="pagination' in body
    # Находится без исключения — иначе _extract_ol_block бросил бы ValueError.
    block = _extract_ol_block(body, "pagination")
    assert "pagy" in block


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-pagination-appears-twice")
@allure.title("listing_paginated.mitm: блок пагинации присутствует ДВАЖДЫ на КАЖДОЙ странице (F3)")
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5])
def test_listing_paginated_pagination_block_appears_twice_per_page(page, listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, page)
    assert body.count('<ol class="pagination') == 2
    assert len(_extract_ol_blocks(body, "pagination")) == 2


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-top-bottom-blocks-identical")
@allure.title("listing_paginated.mitm: верхний и нижний блок пагинации идентичны на КАЖДОЙ странице")
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5])
def test_listing_paginated_top_and_bottom_pagination_blocks_are_identical(page, listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, page)
    top_block, bottom_block = _extract_ol_blocks(body, "pagination")
    assert top_block == bottom_block


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-hrefs-covered")
@allure.title("listing_paginated.mitm: href пагинации КАЖДОЙ страницы покрыты записанными URL (AT-BUG-006)")
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5])
def test_listing_paginated_pagination_hrefs_covered_by_recorded_urls(
    page, listing_paginated_flows, listing_paginated_recorded_urls
):
    body = _listing_page_body(listing_paginated_flows, page)
    page_url = rb.listing_paginated_page_url(page)
    assert _pagination_hrefs_covered(body, page_url, listing_paginated_recorded_urls)
    if page < 5:
        # Непусто на непоследних страницах — иначе assert выше проходил бы
        # вырожденно (пустое множество — подмножество любого).
        assert _pagination_hrefs(body, page_url)


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-page5-no-next")
@allure.title("listing_paginated.mitm: страница 5 (последняя) без next-ссылки — граница класса")
def test_listing_paginated_last_page_has_no_next_link(listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, 5)
    assert 'class="pagination' in body
    block = _extract_ol_block(body, "pagination")
    assert 'class="next"' not in block


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-pages-2-5-have-previous")
@allure.title("listing_paginated.mitm: страницы 2-5 несут рабочую previous-ссылку (не disabled)")
@pytest.mark.parametrize("page", [2, 3, 4, 5])
def test_listing_paginated_non_first_pages_have_previous_link(page, listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, page)
    block = _extract_ol_block(body, "pagination")
    assert 'class="previous"><span class="disabled"' not in block
    assert 'class="previous"><a href=' in block


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-viewport-and-filler")
@allure.title("listing_paginated.mitm: КАЖДАЯ страница несёт viewport meta и филлер-контент (B1)")
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5])
def test_listing_paginated_pages_have_viewport_meta_and_filler(page, listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, page)
    assert 'name="viewport" content="width=device-width, initial-scale=1.0"' in body
    assert "Filler paragraph 79" in body  # 80-й (индекс 0..79) абзац филлера присутствует


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-urls-unique")
@allure.title("listing_paginated.mitm: все записанные URL уникальны")
def test_listing_paginated_urls_unique(listing_paginated_flows):
    urls = [f.request.url for f in listing_paginated_flows]
    assert len(urls) == len(set(urls))


@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-all-blurb-works-have-flows")
@allure.title("listing_paginated.mitm: work-страницы ВСЕХ работ, чьи блёрбы есть на любой странице, записаны (F4)")
def test_listing_paginated_all_blurb_works_have_recorded_work_pages(
    listing_paginated_flows, listing_paginated_recorded_urls
):
    for work in ALL_WORKS:
        assert work.url in listing_paginated_recorded_urls


# --- AT-BUG-054: у фабрики не было ни одной проверки, что содержимое `.mitm`-записи
# соответствует своему генератору — `listing_paginated.mitm` разошёлся руками-правкой
# со СВОИМ генератором (`_blurb_html` выпускает `class="work blurb ..."`, запись несла
# `class="work blurp ..."` на всех 5 страницах): тест не видел блёрбы (`open_listing`
# ждёт `li[id^="work_"].work.blurb`), И приложение тоже (`ao3_bridge.js:530`
# infinite-scroll гейт на том же селекторе). Класс, не экземпляр (CLAUDE.md п.9):
# та же побайтовая сверка «блёрб записи == `_blurb_html(work)` СЕЙЧАС» повторена ниже
# для `listing_basic.mitm`/`works_multi.mitm`/`listing_duplicate_work.mitm` — любых
# записей, встраивающих блёрб в `render_listing_html`, — ловит будущий дрейф
# записи от генератора за секунды device-free юнитом, а не 40-минутным device-прогоном.
@pytest.mark.p2
@allure.id("recording-builder-listing-paginated-blurb-matches-generator")
@allure.title("listing_paginated.mitm: разметка блёрба КАЖДОЙ страницы побайтово совпадает с recording_builder._blurb_html (AT-BUG-054)")
@pytest.mark.parametrize("page", [1, 2, 3, 4, 5])
def test_listing_paginated_blurb_markup_matches_generator(page, listing_paginated_flows):
    body = _listing_page_body(listing_paginated_flows, page)
    work = ALL_WORKS[page - 1]
    expected = rb._blurb_html(work)
    assert expected in body, (
        f"блёрб страницы {page} разошёлся со своим генератором _blurb_html (AT-BUG-054) — "
        "запись правили руками мимо recording_builder; перегенерируй: "
        "framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py"
    )


# --- listing_basic.mitm (AT-BUG-029, доработка attempt 2 — B3 критик-входа) ---


@pytest.fixture(scope="module")
def listing_basic_flows():
    path = settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py ({path})"
    )
    return _read_flows(path)


@pytest.mark.p2
@allure.id("recording-builder-listing-basic-has-eight-flows")
@allure.title("listing_basic.mitm: несёт РОВНО 8 flow (2 листинга + 5 work-страниц + 1 .html-транзакция, батч D-0081)")
def test_listing_basic_has_exactly_eight_flows(listing_basic_flows):
    assert len(listing_basic_flows) == 8


@pytest.mark.p2
@allure.id("recording-builder-listing-basic-has-download-html-flow")
@allure.title("listing_basic.mitm: несёт GET rb.download_url(first_work), тело == rb.render_downloaded_work_html(first_work) (AT-BUG-029)")
def test_listing_basic_has_download_html_flow_for_first_work(listing_basic_flows):
    first_work = ALL_WORKS[0]
    download_url = rb.download_url(first_work)

    flow = next((f for f in listing_basic_flows if f.request.url == download_url), None)
    assert flow is not None, (
        f"недостаёт flow для {download_url} — AT-BUG-029 регрессировал бы "
        "(фоновый DownloadRepository.downloadWork ушёл бы в live-сеть, TC-115 стал бы неинформативным)"
    )
    assert flow.response.get_text() == rb.render_downloaded_work_html(first_work)


@pytest.mark.p2
@allure.id("recording-builder-listing-basic-all-blurb-works-have-recorded-work-pages")
@allure.title("listing_basic.mitm: КАЖДАЯ работа ALL_WORKS несёт свой /works/<id> flow (латентный класс AT-BUG-029 — раньше только ALL_WORKS[0])")
def test_listing_basic_all_blurb_works_have_recorded_work_pages(listing_basic_flows):
    recorded_urls = {f.request.url for f in listing_basic_flows}
    missing = [work.url for work in ALL_WORKS if work.url not in recorded_urls]
    assert not missing, (
        f"work-страницы не записаны для: {missing} — клик/long-press по этим блёрбам "
        "листинга ушёл бы в live-forward (тот же класс, что AT-BUG-006/AT-BUG-029)"
    )


@pytest.mark.p2
@allure.id("recording-builder-listing-basic-blurb-matches-generator")
@allure.title("listing_basic.mitm: разметка блёрба КАЖДОЙ работы побайтово совпадает с recording_builder._blurb_html (AT-BUG-054, класс)")
def test_listing_basic_blurb_markup_matches_generator(listing_basic_flows):
    flow = next(f for f in listing_basic_flows if f.request.url == rb.LISTING_BASIC_URL)
    body = flow.response.get_text()
    for work in ALL_WORKS:
        expected = rb._blurb_html(work)
        assert expected in body, (
            f"блёрб {work.ao3_id} разошёлся со своим генератором _blurb_html (AT-BUG-054, класс) — "
            "перегенерируй: framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py"
        )


# --- listing_duplicate_work.mitm (TC-012, AT-BUG-004 инкремент 3) ---


@pytest.fixture(scope="module")
def listing_duplicate_work_flows():
    path = settings.RECORDINGS_DIR / rb.LISTING_DUPLICATE_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py ({path})"
    )
    return _read_flows(path)


@pytest.mark.p2
@allure.id("recording-builder-listing-duplicate-work-blurb-matches-generator")
@allure.title("listing_duplicate_work.mitm: разметка блёрба побайтово совпадает с recording_builder._blurb_html (AT-BUG-054, класс)")
def test_listing_duplicate_work_blurb_markup_matches_generator(listing_duplicate_work_flows):
    flow = next(f for f in listing_duplicate_work_flows if f.request.url == rb.LISTING_DUPLICATE_URL)
    body = flow.response.get_text()
    work = ALL_WORKS[0]
    expected = rb._blurb_html(work)
    assert expected in body, (
        f"блёрб {work.ao3_id} разошёлся со своим генератором _blurb_html (AT-BUG-054, класс) — "
        "перегенерируй: framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py"
    )
    # Given TC-012 требует ДВА вхождения одного и того же work_id — блёрб обязан
    # встречаться в записи ровно дважды (сама разметка, не только счётчик id).
    assert body.count(expected) == 2


# --- works_multi.mitm ---

_WORK_PATH_RE = re.compile(r"^/works/(\d+)$")


@pytest.fixture(scope="module")
def works_multi_flows():
    path = settings.RECORDINGS_DIR / rb.WORKS_MULTI_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py ({path})"
    )
    return _read_flows(path)


@pytest.mark.p2
@allure.id("recording-builder-works-multi-two-distinct-work-pages")
@allure.title("works_multi.mitm: >=2 flow с /works/<id>, id различны")
def test_works_multi_has_two_distinct_work_page_flows(works_multi_flows):
    work_ids = []
    for flow in works_multi_flows:
        path = urlparse(flow.request.url).path
        m = _WORK_PATH_RE.match(path)
        if m:
            work_ids.append(m.group(1))
    assert len(work_ids) >= 2
    assert len(work_ids) == len(set(work_ids))


@pytest.mark.p2
@allure.id("recording-builder-works-multi-listing-has-both-hrefs")
@allure.title("works_multi.mitm: листинговый flow содержит href обеих work-страниц")
def test_works_multi_listing_contains_both_work_hrefs(works_multi_flows):
    listing = next(f for f in works_multi_flows if f.request.url == rb.WORKS_MULTI_LISTING_URL)
    body = listing.response.get_text()
    work_a, work_b = ALL_WORKS[0], ALL_WORKS[1]
    assert f'href="/works/{work_a.ao3_id}"' in body
    assert f'href="/works/{work_b.ao3_id}"' in body


@pytest.mark.p2
@allure.id("recording-builder-works-multi-urls-unique")
@allure.title("works_multi.mitm: все записанные URL уникальны")
def test_works_multi_urls_unique(works_multi_flows):
    urls = [f.request.url for f in works_multi_flows]
    assert len(urls) == len(set(urls))


@pytest.mark.p2
@allure.id("recording-builder-works-multi-blurb-matches-generator")
@allure.title("works_multi.mitm: разметка блёрбов ОБЕИХ работ побайтово совпадает с recording_builder._blurb_html (AT-BUG-054, класс)")
def test_works_multi_blurb_markup_matches_generator(works_multi_flows):
    flow = next(f for f in works_multi_flows if f.request.url == rb.WORKS_MULTI_LISTING_URL)
    body = flow.response.get_text()
    for work in (ALL_WORKS[0], ALL_WORKS[1]):
        expected = rb._blurb_html(work)
        assert expected in body, (
            f"блёрб {work.ao3_id} разошёлся со своим генератором _blurb_html (AT-BUG-054, класс) — "
            "перегенерируй: framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py"
        )


# --- AT-BUG-030 (доработка attempt 2, критик-вход B4, S-3): device-free юниты
# на присутствие узлов 1/2/3 guard'а тап-зон (bridge-tap-zone-guard,
# TC-119/120/122) в теле work-flow — по образцу
# `test_listing_paginated_pages_have_viewport_meta_and_filler` (проверка
# СОБРАННОЙ записи, не сырого вывода `render_work_page_html` напрямую).
# `works_multi_flows` несёт ДВА независимых work-page flow — оба сверяются, не
# только первый (симметрично `test_works_multi_has_two_distinct_work_page_flows`).


@pytest.mark.p2
@allure.id("recording-builder-works-multi-work-pages-have-tap-zone-guard-and-filler-nodes")
@allure.title("works_multi.mitm: КАЖДАЯ work-страница несёт узлы 1 (button+span), 2 (div[onclick]), 3 (reading-UX филлер) (AT-BUG-030)")
def test_works_multi_work_pages_have_tap_zone_guard_and_filler_nodes(works_multi_flows):
    work_bodies = [
        f.response.get_text()
        for f in works_multi_flows
        if _WORK_PATH_RE.match(urlparse(f.request.url).path)
    ]
    assert len(work_bodies) >= 2  # sanity — симметрично test_works_multi_has_two_distinct_work_page_flows
    for body in work_bodies:
        assert 'data-tap-marker="button"' in body
        assert 'data-tap-marker-child="span"' in body
        assert 'data-tap-marker="div"' in body
        assert f"min-height: {rb.WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX}px" in body


# --- AT-BUG-030 (доработка attempt 2, критик-вход B4, S-4): граница класса M6
# (CLAUDE.md — «у КАЖДОГО введённого воркером лимита/границы (MAX_*, потолки
# глубины/длины, отсечки) — тест НА границе и ЗА ней»). Тест НЕ трогает
# устройство — чистая арифметика над самой константой, подтверждающая
# документированный запас (`WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX=6000` >=
# 3×1800=5400, ~11% запаса, `recording_builder.py` докстринг узла 3) и
# показывающая, ГДЕ инвариант перестаёт держаться (за границей — больший
# гипотетический `innerHeight`, не покрытый текущим эталонным AVD).
@pytest.mark.p2
@allure.id("recording-builder-reading-ux-filler-min-height-3x-boundary")
@allure.title("WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX держит инвариант >=3xinnerHeight эталонного AVD (1800px), но НЕ держит его за границей большего innerHeight (M6)")
def test_reading_ux_filler_min_height_holds_reference_but_not_beyond_boundary():
    reference_inner_height = 1800  # CH-005: innerHeight вне fullscreen на эталонном AVD
    assert rb.WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX >= 3 * reference_inner_height

    # За границей: гипотетический больший innerHeight (2100, например планшетный
    # AVD) — фиксированная константа 6000px больше НЕ покрывает 3xinnerHeight
    # (6000 < 3*2100=6300) — инвариант держится ТОЛЬКО в пределах текущего
    # эталонного AVD, не универсально.
    larger_hypothetical_inner_height = 2100
    assert rb.WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX < 3 * larger_hypothetical_inner_height


# --- Негативные пробы формы (класс F-34, CLAUDE.md «Дисциплина команд» п.6):
# предикат обязан ЛОВИТЬ непокрытый href, не только пропускать покрытый — иначе
# позитивные assert'ы выше могли бы быть слепы по форме (например, если бы
# `_pagination_hrefs` по ошибке всегда возвращала пустое множество, все
# позитивные проверки прошли бы вырожденно-зелёными).

_PAGE_URL = "https://archiveofourown.org/works?ao3_companion_fixture=listing_paginated"


@pytest.mark.p2
@allure.id("recording-builder-pagination-hrefs-covered-predicate-catches-violation")
@allure.title("Негатив F-34: _pagination_hrefs_covered ловит непокрытый href пагинации (проверка в обе стороны)")
def test_pagination_hrefs_covered_predicate_catches_uncovered_href():
    # Given синтетический пагинационный блок с href, которому НЕ дали flow
    uncovered_url = "https://archiveofourown.org/works?ao3_companion_fixture=NEVER_RECORDED&page=999"
    html_with_uncovered_href = (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        '<li class="previous"><span class="disabled">← Previous</span></li>'
        '<li><a role="link" aria-disabled="true" aria-current="page" class="current">1</a></li>'
        f'<li class="next"><a href="{uncovered_url}">Next →</a></li>'
        "</ol>"
    )
    recorded_urls = {_PAGE_URL}

    # Then предикат обнаруживает нарушение (False) — не пропускает молча
    assert _pagination_hrefs_covered(html_with_uncovered_href, _PAGE_URL, recorded_urls) is False

    # И (sanity, тот же тест «в обе стороны»): добавив ИМЕННО этот href в
    # recorded_urls, предикат переключается на True — доказывает, что False
    # выше был обнаружением непокрытости, а не сломанным regex/формой проверки.
    recorded_urls_with_it = recorded_urls | {uncovered_url}
    assert _pagination_hrefs_covered(html_with_uncovered_href, _PAGE_URL, recorded_urls_with_it) is True


@pytest.mark.p2
@allure.id("recording-builder-pagination-hrefs-covered-relative-href-resolves-mut-c")
@allure.title("MUT-C: относительный href резолвится в записанный абсолютный URL -> covered=True")
def test_pagination_hrefs_covered_predicate_resolves_relative_href_against_absolute_recorded_url():
    # Given ТОЛЬКО относительный href (как реальный AO3/наша фикстура, F2) —
    # без urljoin-резолюции он НИКОГДА не совпадёт с абсолютным recorded_urls.
    relative_href = "/works?ao3_companion_fixture=listing_paginated&page=2"
    html_with_relative_href = (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        f'<li class="next"><a href="{relative_href}">Next →</a></li>'
        "</ol>"
    )
    recorded_urls = {"https://archiveofourown.org/works?ao3_companion_fixture=listing_paginated&page=2"}

    # Then резолюция urljoin(page_url, href) находит совпадение -> covered=True
    assert _pagination_hrefs_covered(html_with_relative_href, _PAGE_URL, recorded_urls) is True

    # Контрольный негатив в той же пробе: БЕЗ резолюции (сравнение "в лоб" сырых
    # href с recorded_urls) совпадения нет — доказывает, что True выше именно
    # результат urljoin, а не случайное совпадение строк.
    raw_hrefs = set(_HREF_RE.findall(html_with_relative_href))
    assert not raw_hrefs.issubset(recorded_urls)


@pytest.mark.p2
@allure.id("recording-builder-pagination-hrefs-covered-gap-plus-forward-link-without-next-li-mutant")
@allure.title("Мутант критика: gap + номерная ссылка вперёд БЕЗ li.next всё равно ловится covered-проверкой")
def test_pagination_hrefs_covered_predicate_catches_gap_plus_forward_link_without_next_li_mutant():
    # Given мутант реальной формы AO3 (см. sort_filter_form.mitm: '<li><span
    # class="gap">&hellip;</span></li><li><a href="...page=5000">5000</a></li>')
    # — есть `gap` (без href, не участвует в инварианте) и номерная ссылка
    # ВПЕРЁД на непокрытую страницу, но БЕЗ отдельного `li.next` вовсе. Проверка
    # не должна полагаться на присутствие `class="next"`, чтобы найти href.
    uncovered_far_page = "https://archiveofourown.org/works?ao3_companion_fixture=listing_paginated&page=5000"
    mutant_html = (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        '<li><a role="link" aria-disabled="true" aria-current="page" class="current">1</a></li>'
        '<li><span class="gap">&hellip;</span></li>'
        f'<li><a href="{uncovered_far_page}">5000</a></li>'
        "</ol>"
    )
    recorded_urls = {_PAGE_URL}

    # Then covered-проверка ловит непокрытый href, даже без li.next в разметке
    assert _pagination_hrefs_covered(mutant_html, _PAGE_URL, recorded_urls) is False


@pytest.mark.p2
@allure.id("recording-builder-pagination-hrefs-covered-second-block-uncovered-href-mutant")
@allure.title("Проба критика attempt 3: непокрытый href ТОЛЬКО во ВТОРОМ (нижнем) блоке пагинации ловится covered-проверкой")
def test_pagination_hrefs_covered_predicate_catches_uncovered_href_in_second_block_only():
    # Given ДВА блока пагинации на странице (F3, как в реальной фикстуре) — ВЕРХНИЙ
    # блок целиком покрыт recorded_urls, а НИЖНИЙ несёт непокрытый href
    # (`...&page=77`), которого в верхнем блоке нет. Это ТОЧНАЯ проба критика
    # (attempt 3): версия `_extract_ol_block`/`_pagination_hrefs`, читающая
    # ТОЛЬКО первый блок, была слепа именно к этому случаю — вернула бы `True`,
    # хотя ссылка из второго блока реально увела бы `server_replay_extra=forward`
    # в live (класс AT-BUG-006).
    covered_href = "/works?ao3_companion_fixture=listing_paginated&page=2"
    uncovered_href = "/works?ao3_companion_fixture=listing_paginated&page=77"
    top_block = (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        f'<li class="next"><a href="{covered_href}">Next →</a></li>'
        "</ol>"
    )
    bottom_block_with_uncovered_href = (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        f'<li class="next"><a href="{uncovered_href}">Next →</a></li>'
        "</ol>"
    )
    html_two_blocks = f"{top_block}\n<ol class=\"work index group\"></ol>\n{bottom_block_with_uncovered_href}"
    recorded_urls = {urljoin(_PAGE_URL, covered_href)}

    # Sanity: подтверждаем, что _extract_ol_blocks действительно видит ОБА блока
    # (иначе тест ничего не доказывает о втором блоке).
    assert len(_extract_ol_blocks(html_two_blocks, "pagination")) == 2

    # Then: непокрытый href из ВТОРОГО блока обязан быть найден -> covered=False
    assert _pagination_hrefs_covered(html_two_blocks, _PAGE_URL, recorded_urls) is False


# --- AT-BUG-035: `#kudo_submit` — наблюдаемость авто-клика kudos
# (`bugs/AT-BUG-035.md`). Узел — СИБЛИНГ `<ul class="work navigation actions">`
# (не внутри неё — валидность вложенности), с ИНКРЕМЕНТНЫМ (не константным)
# счётчиком `data-kudo-clicked`, читаемым `driver.execute_script`.

_KUDO_ONCLICK_RE = re.compile(r'<a[^>]*id="kudo_submit"[^>]*onclick="([^"]*)"')


class _FakeKudoNode:
    """Минимальная эмуляция DOM `this` узла `#kudo_submit` — без node/JS-движка
    (критерий готовности AT-BUG-035 явно допускает «JS-среду юнита ИЛИ
    эквивалентную эмуляцию»)."""

    def __init__(self) -> None:
        self._attrs: dict[str, str] = {}

    def getAttribute(self, name: str):  # noqa: N802 - имя JS DOM API
        return self._attrs.get(name)

    def setAttribute(self, name: str, value: str) -> None:  # noqa: N802
        self._attrs[name] = value


def _js_number(x) -> float | int:
    """Эмуляция JS `Number(...)` для узкого домена этого выражения:
    `null`/`""`/`False` -> `0`; иначе строка с целым числом (или само число) ->
    `int`."""
    if x is None or x == "" or x is False:
        return 0
    return int(x)


def _js_string(x) -> str:
    return str(x)


def _run_kudo_onclick(js_snippet: str, node: _FakeKudoNode) -> None:
    """Выполняет РЕАЛЬНЫЙ текст `onclick`, извлечённый regex'ом из
    отрендеренного HTML (не переписанную вручную копию формулы) — переводит
    узкое JS-подмножество, которое несёт `_kudo_submit_html`
    (`this.` -> `node.`, `||` -> `or`), в Python-выражение и исполняет `eval`.
    Узкий транслятор — рассчитан именно на форму этого выражения, не общий
    JS-интерпретатор; ловит регресс формулы (например, откат на
    атрибут-константу) так же надёжно, как реальный JS-движок, потому что
    исполняет буквально извлечённый текст, а не собственный пересказ."""
    for stmt in (s.strip() for s in js_snippet.split(";") if s.strip()):
        if stmt.startswith("return"):
            continue
        py_expr = (
            stmt.replace("this.getAttribute", "node.getAttribute")
            .replace("this.setAttribute", "node.setAttribute")
            .replace("||", " or ")
        )
        eval(  # noqa: S307 - узкий, контролируемый namespace, не пользовательский ввод
            py_expr, {"node": node, "Number": _js_number, "String": _js_string}
        )


def _extract_kudo_onclick(body: str) -> str:
    m = _KUDO_ONCLICK_RE.search(body)
    assert m is not None, "узел #kudo_submit с onclick не найден в отрендеренном HTML"
    return m.group(1)


@pytest.mark.p2
@allure.id("recording-builder-work-page-has-kudo-submit-node")
@allure.title("render_work_page_html: несёт узел #kudo_submit (AT-BUG-035)")
def test_render_work_page_html_has_kudo_submit_node():
    work = ALL_WORKS[0]
    body = rb.render_work_page_html(work)
    assert 'id="kudo_submit"' in body
    assert 'class="kudos"' in body


@pytest.mark.p2
@allure.id("recording-builder-work-page-kudo-submit-is-sibling-of-navigation-actions-ul")
@allure.title("render_work_page_html: #kudo_submit — СИБЛИНГ ul.work.navigation.actions, не внутри неё (AT-BUG-035)")
def test_render_work_page_html_kudo_submit_is_sibling_not_nested():
    work = ALL_WORKS[0]
    body = rb.render_work_page_html(work)

    ul_start = body.index('<ul class="work navigation actions"')
    ul_end = body.index("</ul>", ul_start) + len("</ul>")
    ul_block = body[ul_start:ul_end]
    # Then: узел НЕ внутри <ul> (валидность вложенности — критик-ревью нит 5)
    assert 'id="kudo_submit"' not in ul_block

    kudo_start = body.index('id="kudo_submit"')
    wrapper_start = body.index('<div class="wrapper">')
    # И: порядок в исходном HTML — </ul> ... #kudo_submit ... <div class="wrapper">
    # (regression-требование AT-BUG-030: не сдвигает _download_list_html внутри
    # <ul>, ни tap-zone-guard/reading-UX узлы внутри .wrapper).
    assert ul_end < kudo_start < wrapper_start


@pytest.mark.p2
@allure.id("recording-builder-work-page-kudo-submit-onclick-increments-not-constant")
@allure.title("render_work_page_html: onclick #kudo_submit — ИНКРЕМЕНТНЫЙ счётчик data-kudo-clicked, не константа (B2, AT-BUG-035)")
def test_render_work_page_html_kudo_submit_onclick_is_incremental_counter():
    work = ALL_WORKS[0]
    body = rb.render_work_page_html(work)
    onclick_js = _extract_kudo_onclick(body)
    assert "data-kudo-clicked" in onclick_js

    node = _FakeKudoNode()
    # Given: baseline — атрибута ещё нет (Number(null||0) == 0)
    assert node.getAttribute("data-kudo-clicked") is None

    # When: первый клик (реальный извлечённый JS-текст, не пересказ)
    _run_kudo_onclick(onclick_js, node)
    # Then: "1" — не совпадает с гипотетической атрибут-константой обеих проб
    assert node.getAttribute("data-kudo-clicked") == "1"

    # When: второй клик подряд
    _run_kudo_onclick(onclick_js, node)
    # Then: "2" — отличим от одинарного клика (TC-138/TC-144 различают "ровно
    # один" от "два"; атрибут-константа '1' дала бы "1" оба раза — B2, critic attempt2)
    assert node.getAttribute("data-kudo-clicked") == "2"


@pytest.mark.p2
@allure.id("recording-builder-work-pages-in-collected-recordings-have-kudo-submit-node")
@allure.title("works_multi.mitm: КАЖДАЯ work-страница несёт узел #kudo_submit (AT-BUG-035, собранная запись)")
def test_works_multi_work_pages_have_kudo_submit_node(works_multi_flows):
    work_bodies = [
        f.response.get_text()
        for f in works_multi_flows
        if _WORK_PATH_RE.match(urlparse(f.request.url).path)
    ]
    assert len(work_bodies) >= 2  # sanity — симметрично тесту AT-BUG-030 выше
    for body in work_bodies:
        assert 'id="kudo_submit"' in body
        onclick_js = _extract_kudo_onclick(body)
        assert "data-kudo-clicked" in onclick_js


# --- work_metadata_fetch.mitm (AT-BUG-061) — HttpURLConnection-путь «Fetch
# missing metadata» (`SettingsViewModel.fetchAo3WorkPage`/`parseAo3WorkHtml`,
# `works/<id>?view_adult=true`), закрывает блокер TC-186/TC-187.
#
# Регекс-эквивалент `parseAo3WorkHtml` (SettingsScreen.kt:287-318), извлечённый
# в Python — ТЕ ЖЕ regex-строки, что читает приложение, не переписанный от руки
# пересказ: тест доказывает, что ЗАПИСАННАЯ страница парсится РЕАЛЬНЫМ regex'ом
# приложения в непустой результат, а не только что она "похожа на разметку".
_APP_TITLE_RE = re.compile(r'<h2[^>]+class="[^"]*title[^"]*"[^>]*>\s*(.*?)\s*</h2>', re.DOTALL)
_APP_AUTHOR_RE = re.compile(r'<a[^>]+rel="author"[^>]*>(.*?)</a>')
_APP_FANDOM_BLOCK_RE = re.compile(r'<dd[^>]+class="fandom tags"[^>]*>(.*?)</dd>', re.DOTALL)
_APP_FANDOM_TAG_RE = re.compile(r'<a[^>]+class="tag"[^>]*>(.*?)</a>')
_APP_WORDS_RE = re.compile(r'<dd[^>]+class="words"[^>]*>([\d,]+)</dd>')


def _app_parse_title(body: str) -> str:
    """`stripTags`/`decodeEntities` не нужны для этой синтетической разметки
    (никаких вложенных тегов/сущностей в title кроме экранированных html.escape) —
    узкая проверка домена этого генератора, не полный порт Kotlin-функции."""
    m = _APP_TITLE_RE.search(body)
    return m.group(1).strip() if m else ""


@pytest.fixture(scope="module")
def work_metadata_fetch_flows():
    path = settings.RECORDINGS_DIR / rb.WORK_METADATA_FETCH_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py ({path})"
    )
    return _read_flows(path)


def _metadata_flow_for(work_metadata_fetch_flows, ao3_id: str):
    url = rb.work_metadata_fetch_url(ao3_id)
    return next(f for f in work_metadata_fetch_flows if f.request.url == url)


@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-has-three-flows-unique-urls")
@allure.title("work_metadata_fetch.mitm: несёт РОВНО 3 flow (работа A, работа SECOND, работа B 404), URL уникальны (AT-BUG-061)")
def test_work_metadata_fetch_has_three_unique_flows(work_metadata_fetch_flows):
    assert len(work_metadata_fetch_flows) == 3
    urls = [f.request.url for f in work_metadata_fetch_flows]
    assert len(urls) == len(set(urls))


@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-urls-match-app-url-builder")
@allure.title("work_metadata_fetch.mitm: URL каждого flow совпадает с fetchAo3WorkPage (works/<id>?view_adult=true) (AT-BUG-061)")
def test_work_metadata_fetch_urls_match_app_url_shape(work_metadata_fetch_flows):
    for f in work_metadata_fetch_flows:
        assert f.request.url.startswith("https://archiveofourown.org/works/")
        assert f.request.url.endswith("?view_adult=true")


@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-work-a-parses-nonempty-title-author-fandom-words")
@allure.title("work_metadata_fetch.mitm: работа A парсится РЕГЕКСАМИ parseAo3WorkHtml в непустые title/author/fandom/words (AT-BUG-061, TC-186 позитив)")
def test_work_metadata_fetch_work_a_parses_via_app_regexes(work_metadata_fetch_flows):
    flow = _metadata_flow_for(work_metadata_fetch_flows, rb.METADATA_FETCH_WORK_A.ao3_id)
    assert flow.response.status_code == 200
    body = flow.response.get_text()

    title = _app_parse_title(body)
    assert title == rb.METADATA_FETCH_WORK_A.title
    assert title != ""

    authors = _APP_AUTHOR_RE.findall(body)
    assert rb.METADATA_FETCH_WORK_A.author in authors

    fandom_block = _APP_FANDOM_BLOCK_RE.search(body)
    assert fandom_block is not None, "dd.fandom.tags не найден — parseAo3WorkHtml вернул бы fandom=null"
    fandom_tags = _APP_FANDOM_TAG_RE.findall(fandom_block.group(1))
    assert rb.METADATA_FETCH_WORK_A.fandom in fandom_tags

    words_match = _APP_WORDS_RE.search(body)
    assert words_match is not None, "dd.words не найден — parseAo3WorkHtml вернул бы wordCount=null"
    assert int(words_match.group(1).replace(",", "")) == rb.METADATA_FETCH_WORK_A.word_count


@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-work-second-parses-nonempty")
@allure.title("work_metadata_fetch.mitm: работа SECOND (TC-187 работа E) тоже парсится в непустые title/author (AT-BUG-061)")
def test_work_metadata_fetch_work_second_parses_via_app_regexes(work_metadata_fetch_flows):
    flow = _metadata_flow_for(work_metadata_fetch_flows, rb.METADATA_FETCH_WORK_SECOND.ao3_id)
    assert flow.response.status_code == 200
    body = flow.response.get_text()
    title = _app_parse_title(body)
    assert title == rb.METADATA_FETCH_WORK_SECOND.title
    authors = _APP_AUTHOR_RE.findall(body)
    assert rb.METADATA_FETCH_WORK_SECOND.author in authors


@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-work-b-is-404")
@allure.title("work_metadata_fetch.mitm: работа B — HTTP 404 (fetchAo3WorkPage возвращает null НЕМЕДЛЕННО, без ретраев) (AT-BUG-061, TC-186 негатив)")
def test_work_metadata_fetch_work_b_is_404(work_metadata_fetch_flows):
    flow = _metadata_flow_for(work_metadata_fetch_flows, rb.METADATA_FETCH_WORK_B_AO3_ID)
    assert flow.response.status_code == 404


# --- AT-BUG-054, класс: разметка ОБЕИХ успешных work-страниц побайтово
# совпадает со своим генератором — та же дисциплина дрейфа, что уже покрывает
# listing_paginated/listing_basic/listing_duplicate_work/works_multi выше.
@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-markup-matches-generator")
@allure.title("work_metadata_fetch.mitm: разметка работ A/SECOND побайтово совпадает с render_work_metadata_page_html (AT-BUG-054, класс)")
def test_work_metadata_fetch_markup_matches_generator(work_metadata_fetch_flows):
    for work in (rb.METADATA_FETCH_WORK_A, rb.METADATA_FETCH_WORK_SECOND):
        flow = _metadata_flow_for(work_metadata_fetch_flows, work.ao3_id)
        assert flow.response.get_text() == rb.render_work_metadata_page_html(work), (
            f"work-страница {work.ao3_id} разошлась со своим генератором "
            "render_work_metadata_page_html (AT-BUG-054, класс) — перегенерируй: "
            "framework/.venv/Scripts/python.exe scripts/build_replay_recordings.py"
        )


# --- Негатив формы (класс F-34, CLAUDE.md «Дисциплина команд» п.6): регекс
# `_APP_FANDOM_BLOCK_RE`/`_APP_WORDS_RE` обязаны ЛОВИТЬ отсутствие своего блока
# (h5.fandom.tags preface БЕЗ dd.fandom.tags не должен пройти), не только
# пропускать присутствие — иначе позитивные проверки выше могли бы быть слепы.
@pytest.mark.p2
@allure.id("recording-builder-work-metadata-fetch-fandom-regex-rejects-preface-only-markup")
@allure.title("Негатив F-34: dd.fandom.tags-regex НЕ находит fandom в preface-only (h5.fandom.tags) разметке — доказывает, что позитив выше бьёт именно по dd, не по h5")
def test_app_fandom_regex_does_not_match_preface_only_markup():
    preface_only = '<h5 class="fandom tags"><a class="tag" href="/tags/X/works">X</a></h5>'
    assert _APP_FANDOM_BLOCK_RE.search(preface_only) is None
