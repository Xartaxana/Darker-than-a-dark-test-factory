"""Device-free юниты для двух новых replay-фикстур (батч мелочей 2026-07-28,
`docs/HANDOFF.md` «Батч мелочей (новый, 2026-07-28)» пункт (а)) —
`listing_paginated.mitm` (эксплораторная клетка «infinite scroll/пагинация»,
`CH-005 mission_leftover`, ПЯТЬ страниц — доработка attempt 2, критик-вход B2)
и `works_multi.mitm` (`CH-005 mission_leftover` Г7, live-push на старых
вкладках).

Парсинг СОБРАННЫХ `.mitm`-файлов через `mitmproxy.io.FlowReader` — симметрично
тому, как `recording_builder.write_flows`/`FlowWriter` их пишет — без
устройства/Appium. Требует, чтобы `python scripts/build_replay_recordings.py`
уже отработал (файлы лежат в `settings.RECORDINGS_DIR`, коммитятся как
остальные `.mitm`-фикстуры этого пакета).

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
        f"фикстура не собрана — прогони python scripts/build_replay_recordings.py ({path})"
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


# --- works_multi.mitm ---

_WORK_PATH_RE = re.compile(r"^/works/(\d+)$")


@pytest.fixture(scope="module")
def works_multi_flows():
    path = settings.RECORDINGS_DIR / rb.WORKS_MULTI_FILENAME
    assert path.exists(), (
        f"фикстура не собрана — прогони python scripts/build_replay_recordings.py ({path})"
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
