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
    приём, что `build_work_with_download`."""
    html = rb.render_listing_html(ALL_WORKS)
    base_flow = rb.make_html_get_flow(rb.LISTING_BASIC_URL, html)
    filtered_flow = rb.make_html_get_flow(rb.LISTING_FILTERED_URL, html)
    first_work = ALL_WORKS[0]
    work_page_flow = rb.make_html_get_flow(first_work.url, rb.render_work_page_html(first_work))
    path = settings.RECORDINGS_DIR / rb.LISTING_BASIC_FILENAME
    rb.write_flows(path, [base_flow, filtered_flow, work_page_flow])
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


def main() -> None:
    for path in (
        build_listing_basic(),
        build_listing_duplicate_work(),
        build_work_with_download(),
        build_tab_markers(),
    ):
        print(f"written: {path}")


if __name__ == "__main__":
    main()
