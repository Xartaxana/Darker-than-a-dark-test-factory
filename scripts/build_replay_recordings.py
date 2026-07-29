"""Генератор synthetic-recordings для replay-режима (AT-BUG-004).

Пересобирает `.mitm`-файлы в `framework/data/recordings/` из
`framework/data/recording_builder.py`. Идемпотентен — перезаписывает существующие
файлы. Запускать при любой правке разметки листинга (`_blurb_html`) или после того,
как AO3 поменяла реальную структуру `li.work.blurb` (сверять с
`framework/web/selectors.py` и живым деревом, `python scripts/ui_snapshot.py`).

Использование (из корня репозитория, как и любой скрипт обвязки):
    python scripts/build_replay_recordings.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from framework.config import settings  # noqa: E402
from framework.data import recording_builder as rb  # noqa: E402
from framework.data.works import ALL as ALL_WORKS  # noqa: E402


def build_listing_basic() -> Path:
    """Одна листинговая страница с блёрбами всех эталонных работ
    (`framework/data/works.py::ALL`) — покрывает TC-013/014/015/043/045
    (см. `bugs/AT-BUG-004.md` §Обсуждение, оценка объёма test-automator).

    ВТОРОЙ flow (тем же HTML) под `LISTING_FILTERED_URL` — TC-041: `applyFilter`
    (BrowserViewModel.kt) навигирует на `LISTING_BASIC_URL + '&' + <queryString
    профиля>` при выборе сохранённого FilterProfile из FilterPanel; без записанного
    flow под ЭТОТ URL server-replay не находит совпадения и уходит в live-сеть
    (см. докстринг `LISTING_FILTERED_URL` в `recording_builder.py`).

    ТРЕТИЙ flow — work-страница ПЕРВОЙ работы листинга (`ALL_WORKS[0]`, `LOVED`,
    `href="/works/900000001"`) — TC-026 (`bugs/AT-BUG-018.md`, Fixed): long-press
    по первой ссылке блёрба (`BLURB_TITLE` querySelector, тот же первый элемент)
    открывает её в фоновой вкладке; без записанного flow под этим URL
    `server_replay_extra=forward` увёл бы непокрытый TC-026 в живую сеть на
    несуществующий синтетический id — тест перестал бы быть self-contained
    replay-сценарием. Переиспользует `render_work_page_html`/`work.url`, тот же
    приём, что `build_work_with_download`.

    ЧЕТВЁРТЫЙ flow — сам скачиваемый `.html`-файл (`rb.download_url(first_work)`)
    той же первой работы (`W.LOVED`) — `bugs/AT-BUG-029.md`, нужен TC-115: фоновый
    OkHttp-вызов `DownloadRepository.downloadWork` (GET work-страницы + GET
    `.html`), если он случится из-за edge-vs-level дефекта BUG-014 при правке
    заметки уже-Favorite работы через bottom-sheet листинга, обязан РЕАЛЬНО
    завершиться файлом — иначе `server_replay_extra=forward` уводит незаписанный
    запрос в живую сеть, где синтетического download-пути нет, и негативный Then
    кейса истинен независимо от того, сработал баг или нет. Тот же приём, что
    `download_flow` в `build_work_with_download`."""
    html = rb.render_listing_html(ALL_WORKS)
    base_flow = rb.make_html_get_flow(rb.LISTING_BASIC_URL, html)
    filtered_flow = rb.make_html_get_flow(rb.LISTING_FILTERED_URL, html)
    first_work = ALL_WORKS[0]
    work_page_flow = rb.make_html_get_flow(first_work.url, rb.render_work_page_html(first_work))
    download_flow = rb.make_html_get_flow(
        rb.download_url(first_work), rb.render_downloaded_work_html(first_work)
    )
    path = settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME
    rb.write_flows(path, [base_flow, filtered_flow, work_page_flow, download_flow])
    return path


def build_listing_duplicate_work() -> Path:
    """Листинг с ОДНОЙ и той же работой в ДВУХ разных `<li id="work_{id}">` на одной
    странице — нужен TC-012 (`applyRatings` должен обновить бейдж у ВСЕХ вхождений,
    не только у первого querySelector-совпадения). Не покрывается `listing_basic.mitm`
    (там каждая работа встречается один раз). Работа выбрана произвольно из
    `ALL_WORKS` (`LOVED`) — сценарий TC-012 не завязан на конкретный рейтинг
    (см. `bugs/AT-BUG-004.md` §Обсуждение, оценка объёма test-automator)."""
    work = ALL_WORKS[0]
    html = rb.render_listing_html([work, work], heading="Test Fixture Duplicate Listing")
    flow = rb.make_html_get_flow(rb.LISTING_DUPLICATE_URL, html)
    path = settings.RECORDINGS_DIR / rb.LISTING_DUPLICATE_FILENAME
    rb.write_flows(path, [flow])
    return path


def build_work_with_download() -> Path:
    """Work-страница с валидной download-ссылкой (`li.download a[href*=".html"]`)
    + сам скачиваемый `.html`-файл — ДВЕ HTTP-транзакции в ОДНОМ `.mitm`, т.к.
    `DownloadRepository.downloadWork` (не WebView) идёт по обеим через один и тот же
    `replay`-прокси (см. `recording_builder.py` докстринг у `WORK_WITH_DOWNLOAD_FILENAME`).
    Работа — `LOVED` (та же, что `build_listing_duplicate_work`; произвольный выбор,
    сценарий TC-032/033 не завязан на конкретную работу набора `ALL_WORKS`)."""
    work = ALL_WORKS[0]
    work_page_flow = rb.make_html_get_flow(work.url, rb.render_work_page_html(work))
    download_flow = rb.make_html_get_flow(rb.download_url(work), rb.render_downloaded_work_html(work))
    path = settings.RECORDINGS_DIR / rb.WORK_WITH_DOWNLOAD_FILENAME
    rb.write_flows(path, [work_page_flow, download_flow])
    return path


def build_tab_markers() -> Path:
    """`TAB_MARKER_COUNT` статичных высоких страниц с уникальными `<title>` — area=tabs
    (TC-023/024/025): различение вкладок по НАТИВНО видимому заголовку чипа
    (`TabInfo.title`), без обращения к WEBVIEW-контексту (см. докстринг
    `recording_builder.py` у `TAB_MARKER_FILENAME`)."""
    flows = [
        rb.make_html_get_flow(rb.tab_marker_url(i), rb.render_tab_marker_html(i))
        for i in range(1, rb.TAB_MARKER_COUNT + 1)
    ]
    path = settings.RECORDINGS_DIR / rb.TAB_MARKER_FILENAME
    rb.write_flows(path, flows)
    return path


def build_listing_paginated() -> Path:
    """ПЯТЬ листинговых страниц (`page=1..5`) с реальной разметкой пагинации AO3
    (`rb.render_pagination_html`, сверено с `sort_filter_form.mitm`) — закрывает
    эксплораторную клетку «infinite scroll/пагинация», непокрытую ни одной
    replay-записью (`CH-005 mission_leftover`, `docs/HANDOFF.md` «Батч мелочей
    (новый, 2026-07-28)» пункт (а); полное обоснование B1/B2/F2/F3/F4 (доработка
    attempt 2, критик-вход) — докстринг `LISTING_PAGINATED_FILENAME` в
    `recording_builder.py`).

    `ALL_WORKS` (5 работ) — по одной работе на страницу (1:1), НЕТ страницы без
    work-блёрба. Пагинация: страница `N` несёт `previous` на страницу `N-1`
    (`None`/disabled на странице 1) и `next`+номерную ссылку на страницу `N+1`
    (`None` на странице 5 — последняя записанная, граница класса AT-BUG-006).
    Каждая страница несёт `include_viewport_meta=True` и `filler_html`
    (`render_listing_filler_html`) — гарантированная прокручиваемость (B1).
    F4: work-страница КАЖДОЙ из 5 работ записана в ЭТОМ ЖЕ `.mitm`
    (`render_work_page_html`, тот же приём, что `build_works_multi`) — клик по
    любому блёрбу любой из 5 страниц не уходит в live."""
    page_count = rb.LISTING_PAGINATED_PAGE_COUNT
    listing_flows = []
    for page in range(1, page_count + 1):
        page_url = rb.listing_paginated_page_url(page)
        prev_url = rb.listing_paginated_page_url(page - 1) if page > 1 else None
        next_url = rb.listing_paginated_page_url(page + 1) if page < page_count else None
        pagination_html = rb.render_pagination_html(prev_url, page, next_url)
        filler_html = rb.render_listing_filler_html(f"paginated listing page {page}")
        page_html = rb.render_listing_html(
            [ALL_WORKS[page - 1]],
            heading=f"Test Fixture Paginated Listing (page {page})",
            pagination_html=pagination_html,
            filler_html=filler_html,
            include_viewport_meta=True,
        )
        listing_flows.append(rb.make_html_get_flow(page_url, page_html))
    work_page_flows = [
        rb.make_html_get_flow(work.url, rb.render_work_page_html(work)) for work in ALL_WORKS
    ]
    path = settings.RECORDINGS_DIR / rb.LISTING_PAGINATED_FILENAME
    rb.write_flows(path, listing_flows + work_page_flows)
    return path


def build_works_multi() -> Path:
    """Листинг + ДВЕ РАЗНЫЕ work-страницы в одном `.mitm` — закрывает CH-005
    `mission_leftover` Г7 (live-push/`applyRatings` на старых вкладках непроверяем
    без второй реальной work-страницы, см. докстринг `WORKS_MULTI_FILENAME` в
    `recording_builder.py`). Работы выбраны произвольно (`ALL_WORKS[0]`/`[1]`,
    `LOVED`/`KUDOSED`) — сценарий не завязан на конкретную пару. Листинговый flow
    несёт блёрбы обеих работ (кликабельные ссылки на их work-страницы), обе
    work-страницы записаны — тот же класс покрытия URL, что AT-BUG-006
    (непокрытый клик уводит `server_replay_extra=forward` в live)."""
    work_a, work_b = ALL_WORKS[0], ALL_WORKS[1]
    listing_html = rb.render_listing_html([work_a, work_b], heading="Test Fixture Multi-Work Listing")
    listing_flow = rb.make_html_get_flow(rb.WORKS_MULTI_LISTING_URL, listing_html)
    work_a_flow = rb.make_html_get_flow(work_a.url, rb.render_work_page_html(work_a))
    work_b_flow = rb.make_html_get_flow(work_b.url, rb.render_work_page_html(work_b))
    path = settings.RECORDINGS_DIR / rb.WORKS_MULTI_FILENAME
    rb.write_flows(path, [listing_flow, work_a_flow, work_b_flow])
    return path


def main() -> None:
    for path in (
        build_listing_basic(),
        build_listing_duplicate_work(),
        build_work_with_download(),
        build_tab_markers(),
        build_listing_paginated(),
        build_works_multi(),
    ):
        print(f"written: {path}")


if __name__ == "__main__":
    main()
