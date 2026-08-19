"""N6 контракт-слой (Р2, `docs/tasks/p2-pyramid-bridge.md`), Requirement 2:
«каждая страница несёт узлы заявленных на неё селекторов» —
`framework/data/bridge_selectors.py::REGISTRY`, поле `pages`.

Покрывает И генерируемые фикстуры (`render_*_html (generator)` — вызов
генератора напрямую), И записанные `.mitm` (`framework/data/recordings/`,
включая `sort_filter_form.mitm` — реальная запись AO3, факт 5 recon). Чтение
`.mitm` — той же библиотекой/тем же способом, что `recording_builder.py`/
`scripts/build_replay_recordings.py` (`rb.read_flows`, `mitmproxy.io.
FlowReader`) — не повторный парсер.

Присутствие узла проверяется РЕАЛЬНЫМ CSS-движком (jsdom, тот же
bridge-harness, что пилотные тесты N5, `framework/bridge_harness/
run_bridge.js`, subprocess-протокол `conftest.py`) через `document.
querySelectorAll(selector).length` — не самодельным Python CSS-парсером
(в venv нет ни `bs4`/`soupsieve`, ни `lxml`/`cssselect` — сверено
`framework/requirements.txt` + `.venv/Lib/site-packages`, признанное
отклонение от буквы DoD п.4 «сверься, как записи читает mitm.py» в части
"чем матчить CSS": сам движок для чтения БАЙТОВ записи — mitmproxy
(`read_flows`), а для чтения СЕЛЕКТОРА внутри HTML — тот же jsdom, что уже
несёт весь пакет `bridge/`, а не второй парсер). Полный `ao3BridgeInit`
исполняется как побочный эффект загрузки харнесса (`run_bridge.js` ВСЕГДА
исполняет `window.eval(bridgeText)`) — безвреден для присутствия ИСХОДНЫХ
узлов разметки (bridge только ДОБАВЛЯЕТ элементы вроде Rate-кнопки, не
удаляет уже существующие узлы, которые эти селекторы ищут).

`selector_presence_matrix` (session-scoped) считает КАЖДУЮ страницу
РОВНО ОДИН РАЗ (все селекторы этой страницы — одним батчем eval-actions на
flow), а не по разу на каждую пару (селектор, страница) — иначе
`sort_filter_form.mitm` (196 КБ реальной разметки AO3, ~2с/вызов харнесса)
пересчитывался бы для КАЖДОГО из 4 селекторов, на него завязанных."""
from __future__ import annotations

import json

import allure
import pytest

from framework.config import settings
from framework.data import recording_builder as rb
from framework.data.bridge_selectors import REGISTRY
from framework.data.works import LOVED
from framework.tests.bridge.conftest import _bridge_call_raw as _harness_call

# --- страница -> (html, url) для генерируемых фикстур (не читаются из .mitm) ---
# Один представитель на генератор (та же форма данных, что реальные `.mitm`
# используют для этого генератора — `render_listing_html([LOVED])` зеркалит
# `test_badges.py`/`test_get_work_data.py`; `render_work_page_html(LOVED)` —
# дефолтные аргументы, byte-идентично тому, что несёт КАЖДЫЙ `work_*.mitm`).
_GENERATOR_PAGES = {
    "render_listing_html (generator)": (
        lambda: rb.render_listing_html([LOVED]),
        "https://archiveofourown.org/works",
    ),
    "render_work_page_html (generator)": (
        lambda: rb.render_work_page_html(LOVED),
        LOVED.url,
    ),
}


def _page_html_bodies(page: str) -> list[tuple[str, str]]:
    """Возвращает список `(html, url)` — по одной паре на КАЖДЫЙ
    `text/html` flow записи (не-HTML flow вроде JSON API/картинок в
    `sort_filter_form.mitm` пропускаются — узлы разметки там не живут)."""
    if page in _GENERATOR_PAGES:
        factory, url = _GENERATOR_PAGES[page]
        return [(factory(), url)]
    path = settings.RECORDINGS_DIR / page
    flows = rb.read_flows(path)
    bodies = []
    for flow in flows:
        if not flow.response:
            continue
        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            continue
        bodies.append((flow.response.text, flow.request.url))
    return bodies


def _selector_hit_counts(html: str, url: str, selectors: list[str]) -> dict[str, int]:
    """Один вызов bridge-harness — батч `querySelectorAll(selector).length`
    на КАЖДЫЙ селектор `selectors` за один subprocess (не по одному на
    селектор)."""
    payload = {
        "html": html,
        "url": url,
        "actions": [
            {"id": f"sel{i}", "type": "eval", "code": f"document.querySelectorAll({json.dumps(sel)}).length"}
            for i, sel in enumerate(selectors)
        ],
    }
    response = _harness_call(payload)
    if not response.get("ok", False):
        raise RuntimeError(
            f"bridge-harness вернул ok=false при проверке страницы {url!r}: "
            f"error={response.get('error')!r} stack={response.get('stack')!r}"
        )
    return {sel: response["results"][f"sel{i}"] for i, sel in enumerate(selectors)}


def _build_presence_matrix(page_to_selectors: dict[str, list[str]]) -> dict[str, dict[str, bool]]:
    """`page -> {selector: найден ли хотя бы один узел в ЛЮБОМ text/html
    flow этой страницы}` — общий строительный блок и для реестра (сессионная
    фикстура ниже), и для красной пробы (синтетические данные, без
    session-кеша)."""
    matrix: dict[str, dict[str, bool]] = {}
    for page, selectors in page_to_selectors.items():
        counts = {sel: 0 for sel in selectors}
        bodies = _page_html_bodies(page)
        assert bodies, (
            f"страница {page!r} из реестра не дала НИ ОДНОГО text/html flow "
            "(файл записи пуст/не содержит HTML, либо генератор незарегистрирован "
            "в _GENERATOR_PAGES) — сам реестр указывает на страницу без содержимого"
        )
        for html, url in bodies:
            hits = _selector_hit_counts(html, url, selectors)
            for sel, count in hits.items():
                counts[sel] += count
        matrix[page] = {sel: count > 0 for sel, count in counts.items()}
    return matrix


@pytest.fixture(scope="session")
def selector_presence_matrix() -> dict[str, dict[str, bool]]:
    """Считает `page -> {selector: present}` РОВНО ОДИН РАЗ за сессию для
    ВСЕХ пар (селектор, страница) реестра (`REGISTRY`) — параметризованный
    тест ниже только читает готовую матрицу, не зовёт харнесс повторно."""
    page_to_selectors: dict[str, list[str]] = {}
    for entry in REGISTRY:
        for page in entry.pages:
            bucket = page_to_selectors.setdefault(page, [])
            if entry.selector not in bucket:
                bucket.append(entry.selector)
    return _build_presence_matrix(page_to_selectors)


_SELECTOR_PAGE_PAIRS = [
    (entry.selector, page) for entry in REGISTRY for page in entry.pages
]


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-contract-page-carries-declared-selector")
@allure.title("N6 контракт: КАЖДАЯ страница реестра несёт узел КАЖДОГО заявленного на неё селектора")
@pytest.mark.parametrize(
    "selector,page",
    _SELECTOR_PAGE_PAIRS,
    ids=[f"{page}__{selector}" for selector, page in _SELECTOR_PAGE_PAIRS],
)
def test_page_carries_declared_selector(selector_presence_matrix, selector, page):
    assert selector_presence_matrix[page][selector], (
        f"реестр (framework/data/bridge_selectors.py) заявляет, что {page!r} обязана "
        f"нести узел {selector!r}, но querySelectorAll не нашёл ни одного совпадения "
        "ни в одном text/html flow этой записи/генератора — либо разметка страницы "
        "дрейфовала (класс AT-BUG-074), либо запись реестра ошибочна."
    )


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-contract-page-selector-check-catches-absent-node")
@allure.title("N6 контракт, красная проба: проверка присутствия узла ловит ОТСУТСТВУЮЩИЙ селектор (не вакуумно-истинна)")
def test_page_selector_presence_check_catches_absent_node():
    """Красная проба (CLAUDE.md builder п.4/6а): доказывает, что
    `_build_presence_matrix`/`test_page_carries_declared_selector` умеют
    ПАДАТЬ, а не всегда возвращают True. Фабрикует ФИКТИВНУЮ пару
    (заведомо отсутствующий CSS-селектор на реальной странице листинга) —
    не трогает REGISTRY/реальные `.mitm`, синтетические тестовые данные."""
    fake_selector = "[data-does-not-exist-in-any-fixture]"
    matrix = _build_presence_matrix({"render_listing_html (generator)": [fake_selector]})
    assert matrix["render_listing_html (generator)"][fake_selector] is False, (
        "красная проба провалена: заведомо отсутствующий селектор помечен как "
        "присутствующий -- проверка вакуумно-истинна, не различает "
        "присутствие/отсутствие узла"
    )
    # sanity: тот же генератор, тот же вызов харнесса, но РЕАЛЬНЫЙ селектор -
    # доказывает, что False выше НЕ из-за сломанного вызова харнесса вообще.
    real_matrix = _build_presence_matrix(
        {"render_listing_html (generator)": ['li[id^="work_"].work.blurb']}
    )
    assert real_matrix["render_listing_html (generator)"]['li[id^="work_"].work.blurb'] is True
