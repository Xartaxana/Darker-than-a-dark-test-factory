"""Строит синтетические mitmproxy `.mitm`-записи (flow-файлы) для replay-тестов.

Зачем программно, а не живым `mitmdump`-прогоном: синтетические `ao3_id` из
`framework/data/works.py` намеренно НЕ существуют на archiveofourown.org (см.
`Work`/`ALL`) — записать живой листинг с блёрбами ЭТИХ работ физически невозможно.
Единственный путь (согласованный test-automator/test-designer при разборе AT-BUG-004,
см. TC-013.md «Заблокировано») — собрать `.mitm` того же формата, что читает
`framework/core/mitm.py::start_replay` (`mitmdump --server-replay`), с HTML-телом,
1:1 повторяющим проверенную разметку AO3 (`framework/web/selectors.py`,
`app-under-test/PROJECT.md` §Fragility note).

Матчинг server-replay (`mitmproxy.addons.serverplayback._hash`) учитывает
scheme+method+path+query+host+port (без заголовков) — поэтому воспроизводимость
не зависит от cookies/UA устройства, важна только точность URL, которым тест
навигирует WebView (см. `LISTING_BASIC_URL`).

Когда AO3 меняет разметку — чинить и здесь, и в `selectors.py`, затем
перегенерировать записи ЭТИМ модулем (`framework/.venv/Scripts/python.exe
scripts/build_replay_recordings.py`), а не редактировать бинарный `.mitm` руками.
"""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from urllib.parse import urlparse

from mitmproxy import connection, http
from mitmproxy.connection import ConnectionState
from mitmproxy.io import FlowWriter
from mitmproxy.proxy.mode_specs import ProxyMode

from framework.data.works import Work

# --- Идентификаторы базовой листинговой фикстуры (TC-013/014/015/043/045, AT-BUG-004) ---
LISTING_BASIC_FILENAME = "listing_basic.mitm"
# `ao3_companion_fixture=...` — маркерный query-параметр без смысла для реального AO3
# (сервер его просто проигнорирует и отдаст обычный листинг `/works`, без наших
# синтетических work_id) — используется только для читаемости URL в тестах/логах,
# а не как защита от live-режима: реальную защиту даёт requires-фикстуры маркер
# `@pytest.mark.replay` и явный teardown прокси в `replay`-фикстуре conftest.py.
LISTING_BASIC_URL = "https://archiveofourown.org/works?ao3_companion_fixture=listing_basic"

# --- Filtered-вариант той же листинговой страницы (TC-041, применение сохранённого
# FilterProfile из BottomBar.kt FilterPanel) — ВТОРОЙ flow в том же listing_basic.mitm
# (см. build_listing_basic в scripts/build_replay_recordings.py), тем же HTML: синтетика
# не фильтрует блёрбы по queryString сервер-сайд (в отличие от реального AO3), проверяемый
# факт TC-041 — сам URL активной вкладки после applyFilter, не изменившийся контент.
# `applyFilter` (BrowserViewModel.kt) строит URL как `filterableBaseUrl + '&' +
# stripDisplayParams(profile.queryString)` — воспроизводим ТОЧНО эту конкатенацию, чтобы
# server-replay (`_hash` парсит query через `parse_qsl` — порядок пар ЗНАЧИМ, кодирование
# key/value НЕ значимо, т.к. `parse_qsl` их декодирует) нашёл совпадение вместо ухода в
# live-сеть (`server_replay_extra=forward`) — тот же класс блокера, что AT-BUG-006
# обсуждение задокументировало для TC-041 (несовпадение filtered-URL с записанным flow),
# закрыт здесь расширением recording_builder, а не принятием live-перехода.
FILTER_APPLIED_QUERY_STRING = "work_search%5Bquery%5D=applied-filter-test"
LISTING_FILTERED_URL = f"{LISTING_BASIC_URL}&{FILTER_APPLIED_QUERY_STRING}"

# --- Идентификаторы дубль-листинговой фикстуры (TC-012, AT-BUG-004 инкремент 3) ---
# Один и тот же ao3_id встречается в ДВУХ разных `<li id="work_{id}">` на одной
# странице (не покрывается listing_basic.mitm, где каждая работа встречается один
# раз) — нужно доказать, что `applyRatings` (ao3_bridge.js) обновляет бейдж у ВСЕХ
# вхождений на странице, а не только у первого найденного querySelector'ом.
LISTING_DUPLICATE_FILENAME = "listing_duplicate_work.mitm"
LISTING_DUPLICATE_URL = "https://archiveofourown.org/works?ao3_companion_fixture=listing_duplicate_work"

# --- Идентификаторы фикстуры download-flow (TC-032/033, AT-BUG-004 инкремент 3) ---
# `DownloadRepository.downloadWork` (не WebView!) идёт по ДВУМ HTTP-транзакциям через
# `OkHttpClient`: сначала GET work-страницы, чтобы regex'ом (`fetchDownloadUrl`)
# вытащить download-ссылку из `li.download a[href*=".html"]` (см. PROJECT.md §Download
# flow, TC-032.md/TC-033.md «Причина»), затем GET самого `.html`-файла по найденному
# URL. Обе транзакции нужно записать в ОДИН `.mitm` — оба пути через один и тот же
# `replay`-прокси (`conftest.py`), см. `build_work_with_download` в
# `scripts/build_replay_recordings.py`.
WORK_WITH_DOWNLOAD_FILENAME = "work_with_download.mitm"

# --- Идентификаторы фикстуры маркерных страниц вкладок (TC-023/024/025, area=tabs) ---
# Каждая страница — статичная, ВЫСОКАЯ (гарантированный scrollHeight выше вьюпорта
# любого разумного эмулятора — см. AT-BUG-015 про короткие живые страницы) и с
# УНИКАЛЬНЫМ <title> — WebChromeClient.onReceivedTitle (BrowserScreen.kt) прокидывает
# его в TabInfo.title, рендерящийся НАТИВНО (Compose Text) в TabStrip.kt — что даёт
# способ различать вкладки БЕЗ обращения к WEBVIEW-контексту (см. докстринг
# `framework/screens/browser_screen.py::tab_chip_at` о недетерминизме chromedriver
# при нескольких одновременных WebView одного пакета — обнаружено при разведке
# TC-023/024/025/026, см. заметки автоматизации соответствующих кейсов). Полностью
# синтетическая (не time-sensitive) — детерминизм не зависит от состояния живого AO3.
TAB_MARKER_FILENAME = "tab_markers.mitm"
TAB_MARKER_COUNT = 8  # с запасом под TC-024 (7 вкладок) + TC-023/025 (2-3 вкладки)


def tab_marker_url(index: int) -> str:
    return f"https://archiveofourown.org/works?ao3_tab_marker={index}"


def tab_marker_title(index: int) -> str:
    """Отдельная функция (не только внутри HTML) — тесты сверяют РОВНО ЭТУ строку
    по нативному дереву (TabChip Text), без похода в WebView-контекст."""
    return f"TC-Tabs Marker {index}"


def render_tab_marker_html(index: int) -> str:
    # 80 коротких абзацев-филлеров — эмпирически с большим запасом выше innerHeight
    # любого разумного эмулятора (AT-BUG-015: живой Browse root дал scrollHeight=427
    # при innerHeight=798 — здесь на порядок выше, без зависимости от живого AO3).
    filler = "\n".join(
        f"    <p>Filler paragraph {i} for tab marker {index} — scroll padding, not real content.</p>"
        for i in range(80)
    )
    title = html.escape(tab_marker_title(index))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body>
  <h1>{title}</h1>
{filler}
</body>
</html>
"""


# --- Идентификаторы реальной записи формы AO3 Sort & Filter (TC-040, AT-BUG-006
# инкремент 2) — НЕ построена этим модулем: реальный `mitmdump -w` LIVE-захват страницы
# `archiveofourown.org/tags/Fluff/works` в исходной разметке (см. `bugs/AT-BUG-006.md`
# §Обсуждение, решение Lead 2026-07-10 «реальная запись — первично»). Константы здесь —
# только для единообразной ссылки из тестов/фикстур, тот же паттерн, что и у остальных
# идентификаторов файла (файл САМ не перегенерируется `scripts/build_replay_recordings.py`).
SORT_FILTER_FORM_FILENAME = "sort_filter_form.mitm"
SORT_FILTER_FORM_URL = "https://archiveofourown.org/tags/Fluff/works"


# --- Идентификаторы пагинированной листинговой фикстуры (эксплораторная клетка
# «infinite scroll/пагинация», матрица PERTURBATIONS × coverage — `CH-005`
# `mission_leftover`: "infinite_scroll НЕ ТРОНУТ (блокер фикстур, объявлен в Data
# setup): ни одна replay-запись не несёт пагинации. Запрос фикстуры
# listing_paginated.mitm — builder-класс, test-automator"; причина диспатча —
# `docs/HANDOFF.md` «Батч мелочей (новый, 2026-07-28)» пункт (а)).
#
# ПЯТЬ страниц (`page=1..5`, доработка attempt 2 критик-вход B2) — не две:
# эвикция `PAGE_WINDOW=3` (`ao3_bridge.js:594-605`) срабатывает только при >3
# ЗАГРУЖЕННЫХ страницах, двух страниц было бы недостаточно, чтобы её вообще
# достичь; пять дают эвикцию НА 4-й странице и ещё один шаг после (5-я). Каждая
# страница несёт РЕАЛЬНУЮ разметку пагинации AO3 (`render_pagination_html`,
# сверено с `sort_filter_form.mitm`), блок повторён ДВАЖДЫ на странице — сверху
# и снизу листинга (доработка attempt 2, критик-вход F3, как в реальной
# записи). Href пагинации — HOST-RELATIVE (доработка attempt 2, критик-вход F2:
# реальный AO3 рендерит их относительными, не абсолютными — см.
# `sort_filter_form.mitm`: `href="/tags/Fluff/works?page=2"`); резолвятся
# `urljoin(page_url, href)` перед сверкой с записанными URL (см.
# `framework/tests/test_recording_builder_unit.py::_pagination_hrefs_covered`).
# Страница 5 (последняя записанная) — БЕЗ next-ссылки (граница класса:
# следующая страница в фикстуре не существует).
#
# ИНВАРИАНТ (класс AT-BUG-006, `bugs/AT-BUG-006.md` — непокрытый href в записи
# уводит `server_replay_extra=forward` в live): КАЖДЫЙ href пагинационного
# блока КАЖДОЙ страницы обязан иметь свой flow в этом же `.mitm` — номерные/
# next-ссылки ведут ТОЛЬКО на соседние ЗАПИСАННЫЕ страницы (1..5), ссылок на
# страницы 6+ нет. По тому же классу (доработка attempt 2, критик-вход F4) —
# work-страницы ВСЕХ работ, чьи блёрбы встречаются на любой из 5 страниц,
# записаны в ЭТОМ ЖЕ `.mitm` (`render_work_page_html`, тот же приём, что
# `works_multi.mitm` ниже) — тап по любому блёрбу листинга не должен уходить в
# live.
#
# Высота/скролл (доработка attempt 2, критик-вход B1): каждая страница несёт
# `<meta name="viewport" content="width=device-width, initial-scale=1.0">` и 80
# филлер-абзацев ПО ЭТАЛОНУ `render_tab_marker_html`/AT-BUG-015 (см. докстринг
# там же). Device-замер СНЯТ первым device-прогоном фикстуры (TC-129,
# 2026-07-30, эмулятор конвейера): `scrollY≈4341.7 innerHeight=798
# scrollHeight=5104` — документ в 6.4 вьюпорта, скролл реален; замер
# ассертится и прикладывается каждым прогоном
# (`browser_steps.scroll_listing_to_bottom`, allure-attach), деталь — в
# `test-cases/settings/TC-129.md` «Заметки для автоматизации».
LISTING_PAGINATED_FILENAME = "listing_paginated.mitm"
LISTING_PAGINATED_URL = "https://archiveofourown.org/works?ao3_companion_fixture=listing_paginated"
LISTING_PAGINATED_PAGE_COUNT = 5


def listing_paginated_page_url(page: int) -> str:
    """Страница 1 -> `LISTING_PAGINATED_URL` (без `page=` — реальный AO3 не несёт
    `?page=1` в URL первой страницы, см. `sort_filter_form.mitm`); страница >=2 ->
    `LISTING_PAGINATED_URL + '&page={N}'` (та же конкатенация, что
    `LISTING_FILTERED_URL` выше)."""
    if page <= 1:
        return LISTING_PAGINATED_URL
    return f"{LISTING_PAGINATED_URL}&page={page}"

# --- Идентификаторы фикстуры с НЕСКОЛЬКИМИ work-страницами (CH-005 `mission_leftover`,
# Г7 "live-push настройки при 10 открытых вкладках... По существу механизм НЕ
# проверен: страницы tab_markers имеют pathname=/works, тап-зоны там выключены
# (ao3_bridge.js:1154)" — live-push/`applyRatings` на СТАРЫХ (уже открытых)
# вкладках непроверяем по существу без ВТОРОЙ реальной work-страницы, на которую
# можно перейти отдельной вкладкой; причина диспатча — `docs/HANDOFF.md` «Батч
# мелочей (новый, 2026-07-28)» пункт (а)). Листинг фикстуры несёт href на ОБЕ
# work-страницы — тот же класс покрытия URL, что и `listing_paginated`
# (AT-BUG-006): flow обязан существовать для каждого href, которым тест реально
# кликает по этой фикстуре (см. `scripts/build_replay_recordings.py::
# build_works_multi` — граница по DoD этой задачи, не все вспомогательные ссылки
# блёрба вроде author/tag).
WORKS_MULTI_FILENAME = "works_multi.mitm"
WORKS_MULTI_LISTING_URL = "https://archiveofourown.org/works?ao3_companion_fixture=works_multi"


def _deterministic_id(*parts: str) -> str:
    """UUID-формой (mitmproxy требует именно её для conn.id), но детерминированный:
    md5 от связки url/роли соединения вместо `uuid.uuid4()`. Без этого `.mitm`-файл
    менялся байт-в-байт при каждой перегенерации (случайные conn-id) — артефакт
    было невозможно сверить с генератором, diff шумел даже когда HTML не менялся
    (см. AT-BUG-004, приёмка critic). Матчинг server-replay не зависит от conn.id
    (см. модульный докстринг), так что детерминизм id не влияет на воспроизведение."""
    digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _client_conn(url: str) -> connection.Client:
    return connection.Client(
        id=_deterministic_id("client", url), peername=("127.0.0.1", 0), sockname=("", 0),
        mitmcert=None, timestamp_start=0, timestamp_tls_setup=None, timestamp_end=0,
        sni=None, cipher=None, alpn=None, tls_version=None, state=ConnectionState.OPEN,
        error=None, tls=False, certificate_list=[], alpn_offers=[], cipher_list=[],
        proxy_mode=ProxyMode.parse("regular"),
    )


def _server_conn(host: str, url: str) -> connection.Server:
    return connection.Server(
        id=_deterministic_id("server", url), address=(host, 443), peername=("0.0.0.0", 443),
        sockname=(host, 443), timestamp_start=0, timestamp_tcp_setup=0,
        timestamp_tls_setup=0, timestamp_end=0, sni=host, alpn=None,
        tls_version="TLSv1.2", via=None, state=ConnectionState.CLOSED, error=None,
        tls=True, certificate_list=[], alpn_offers=[], cipher=None, cipher_list=[],
    )


def make_html_get_flow(url: str, body: str, status: int = 200) -> http.HTTPFlow:
    """Один flow: `GET {url}` -> `{status} text/html`, тело `body`.

    `status` (AT-BUG-061, доработка): по умолчанию `200` — сигнатура/поведение
    для ВСЕХ существующих вызовов (без явного `status=`) байт-в-байт та же, что
    до этого параметра. Явный `status=404` (и т.п.) — синтетическая ошибка
    HTTP на РЕАЛЬНОМ пути через server-replay (не исключение транспорта): нужен
    `build_work_metadata_fetch` — `fetchAo3WorkPage` (SettingsScreen.kt:259-284)
    трактует код 404 как «работа не существует» и возвращает `null` НЕМЕДЛЕННО,
    без ретраев/`delay()` (в отличие от прочих кодов/исключений — до 3 попыток
    по 5с) — детерминированный и быстрый способ смоделировать «скрейп не дал
    результата» без ожидания реального таймаута.

    Все таймстемпы/id зафиксированы на детерминированные значения: `Flow.__init__`,
    `Request.make`/`Response.make` по умолчанию берут `uuid.uuid4()`/`time.time()`
    (не только conn-id, как выяснилось при чистке AT-BUG-004) — без обнуления
    `.mitm` менялся байт-в-байт при каждой перегенерации, даже когда HTML не менялся.
    Матчинг server-replay не зависит ни от одного из этих полей (см. модульный
    докстринг), так что фиксация значений не влияет на воспроизведение флоу."""
    host = urlparse(url).hostname or "archiveofourown.org"
    flow = http.HTTPFlow(_client_conn(url), _server_conn(host, url))
    flow.id = _deterministic_id("flow", url)
    flow.timestamp_created = 0
    flow.request = http.Request.make("GET", url, b"")
    flow.request.timestamp_start = 0
    flow.request.timestamp_end = 0
    flow.response = http.Response.make(
        status, body.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
    )
    flow.response.timestamp_start = 0
    flow.response.timestamp_end = 0
    return flow


def write_flows(path: Path, flows: list[http.HTTPFlow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fo:
        writer = FlowWriter(fo)
        for f in flows:
            writer.add(f)


# --- Разметка блёрба листинга — сверено с проверенными паттернами AO3 (см. модульный
# докстринг), инжектируемые ao3_bridge.js элементы (Rate/Note-кнопка) в фикстуру НЕ
# кладём — их вставляет сам bridge при первом проходе по `li[id^="work_"].work.blurb`. ---
def _blurb_html(work: Work) -> str:
    wid = html.escape(work.ao3_id)
    title = html.escape(work.title)
    author = html.escape(work.author)
    fandom = html.escape(work.fandom)
    return f"""
    <li id="work_{wid}" class="work blurb group work-{wid}" role="article">
      <h4 class="heading">
        <a href="/works/{wid}">{title}</a>
        <a rel="author" href="/users/{author}/pseuds/{author}">{author}</a>
      </h4>
      <h5 class="fandoms heading">
        <a class="tag" href="/tags/{fandom}/works">{fandom}</a>
      </h5>
      <p class="datetime">01 Jul 2026</p>
      <h6 class="landmark heading">Summary</h6>
      <blockquote class="userstuff summary">
        <p>Test fixture summary for {title}.</p>
      </blockquote>
      <ul class="tags commas">
        <li class="warnings"><a class="tag" href="/tags/Creator%20Chose%20Not%20To%20Use%20Archive%20Warnings/works">Creator Chose Not To Use Archive Warnings</a></li>
        <li class="relationships"><a class="tag" href="/tags/Test%20Ship*s*Other%20Ship/works">Test Ship/Other Ship</a></li>
        <li class="freeforms"><a class="tag" href="/tags/Fluff/works">Fluff</a></li>
      </ul>
      <dl class="stats">
        <dt class="words">Words:</dt><dd class="words">{work.word_count}</dd>
        <dt class="chapters">Chapters:</dt><dd class="chapters">1/1</dd>
        <dt class="comments">Comments:</dt><dd class="comments">0</dd>
        <dt class="kudos">Kudos:</dt><dd class="kudos">0</dd>
        <dt class="hits">Hits:</dt><dd class="hits">1</dd>
      </dl>
    </li>"""


def render_listing_html(
    works: list[Work],
    heading: str = "Test Fixture Listing",
    pagination_html: str = "",
    filler_html: str = "",
    include_viewport_meta: bool = False,
) -> str:
    """Минимальная, но структурно-валидная страница листинга AO3: `ol.work.index.group`
    с одним `li[id^="work_"].work.blurb` на каждую `Work`. Никаких внешних
    `<script src>`/`<link rel=stylesheet>` — самодостаточна, не требует
    `server_replay_extra=forward` на ассеты (детерминизм без сети).

    Принимает `works` как есть, БЕЗ дедупликации по `ao3_id` — намеренно: TC-012
    (AT-BUG-004 инкремент 3) требует листинг с ДВУМЯ `<li id="work_{id}">` одного и
    того же `ao3_id` (см. `build_listing_duplicate_work` в
    `scripts/build_replay_recordings.py`, вызывающий `render_listing_html([work, work])`).
    Дублирующиеся `id` невалидны по спеке HTML, но реальные браузеры/`querySelectorAll`
    это допускают — соответствует тому, что должен пережить `applyRatings`.

    Три опциональных параметра (доработка attempt 2, `listing_paginated.mitm`) —
    ВСЕ по умолчанию пустые/`False`, вывод БЕЗ них байт-в-байт идентичен прежней
    сигнатуре функции (`listing_basic.mitm`/`listing_duplicate_work.mitm`/
    `work_with_download.mitm`/`tab_markers.mitm` не меняются от этого расширения):
    - `pagination_html` — готовый `<ol class="pagination...">...</ol>` (см.
      `render_pagination_html`), вставляется ДВАЖДЫ — под `<h4 class="landmark
      heading">Navigation</h4>` ПЕРЕД листингом работ И ПОСЛЕ него (критик-вход
      F3: реальный AO3 показывает пагинацию сверху и снизу, см.
      `sort_filter_form.mitm`).
    - `filler_html` — готовый блок филлер-контента (см.
      `render_listing_filler_html`), вставляется В КОНЦЕ, после листинга/нижней
      пагинации — гарантирует прокручиваемость страницы (критик-вход B1,
      AT-BUG-015).
    - `include_viewport_meta` — добавляет `<meta name="viewport" content=
      "width=device-width, initial-scale=1.0">` в `<head>` (реальный AO3 несёт
      его на каждой странице, см. `sort_filter_form.mitm`)."""
    blurbs = "\n".join(_blurb_html(w) for w in works)
    pagination_top = (
        f'\n  <h4 class="landmark heading">Navigation</h4>\n  {pagination_html}'
        if pagination_html
        else ""
    )
    pagination_bottom = f"\n  {pagination_html}" if pagination_html else ""
    filler_block = f"\n  {filler_html}" if filler_html else ""
    viewport_meta = (
        '\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">'
        if include_viewport_meta
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">{viewport_meta}<title>{html.escape(heading)} | Archive of Our Own</title></head>
<body>
<div id="main" class="works-index dashboard region" role="main">
  <h2 class="heading">{html.escape(heading)}</h2>{pagination_top}
  <ol class="work index group">
    {blurbs}
  </ol>{pagination_bottom}{filler_block}
</div>
</body>
</html>
"""


def render_listing_filler_html(label: str) -> str:
    """80 коротких абзацев-филлеров — ТОТ ЖЕ приём и обоснование, что
    `render_tab_marker_html` (AT-BUG-015: короткая синтетическая страница не
    прокручивается — «страница не прыгнула» неотличимо от «зона/эвикция не
    сработала»). `label` — только для читаемости текста филлера (например,
    номер страницы), на детерминизм/высоту не влияет."""
    return "\n".join(
        f"    <p>Filler paragraph {i} for {html.escape(label)} — scroll padding, "
        f"not real content.</p>"
        for i in range(80)
    )


# --- Разметка блока пагинации — сверена с РЕАЛЬНОЙ записью AO3 (`sort_filter_form.mitm`,
# `https://archiveofourown.org/tags/Fluff/works`, флоу-эксплорация builder'а этой задачи):
# `<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">` с
# `li.previous` (disabled `<span>` на первой странице, иначе `<a href>`), текущая
# страница — `<a class="current" ...>` БЕЗ `href` (реальный AO3 не делает текущую
# страницу кликабельной — не участвует в инварианте покрытия), номерная ссылка на
# следующую страницу и `li.next` (оба — тот же `next_url`, как в реальной записи, где
# численная "2" и "Next →" ведут на один и тот же URL).
def _relative_href(absolute_url: str) -> str:
    """Host-relative форма абсолютного AO3 URL (доработка attempt 2, критик-вход
    F2) — реальный AO3 рендерит href пагинации HOST-RELATIVE, не абсолютными
    (`sort_filter_form.mitm`: `href="/tags/Fluff/works?page=2"`), а не
    `href="https://archiveofourown.org/tags/Fluff/works?page=2"`."""
    parsed = urlparse(absolute_url)
    rel = parsed.path
    if parsed.query:
        rel += f"?{parsed.query}"
    return rel


def render_pagination_html(prev_url: str | None, current_page: int, next_url: str | None) -> str:
    """`prev_url`/`next_url` — АБСОЛЮТНЫЕ URL соседних страниц (та же форма, что
    URL записанного flow) — внутри рендерятся HOST-RELATIVE href'ами
    (`_relative_href`); резолвить обратно для сверки с записанными URL — через
    `urljoin(page_url, href)` на стороне потребителя (см. `_pagination_hrefs_covered`
    в `framework/tests/test_recording_builder_unit.py`).

    `prev_url=None` — первая страница (disabled Previous, без ссылки).
    `next_url=None` — последняя страница (нет номерной ссылки вперёд и нет `li.next`) —
    граница класса AT-BUG-006: непокрытый href в записи увёл бы `server_replay_extra=
    forward` в live, поэтому на последней записанной странице ссылок ВПЕРЁД нет вовсе."""
    if prev_url is None:
        prev_li = '<li class="previous"><span class="disabled">← Previous</span></li>'
    else:
        prev_li = f'<li class="previous"><a href="{_relative_href(prev_url)}">← Previous</a></li>'
    current_li = (
        '<li><a role="link" aria-disabled="true" aria-current="page" '
        f'class="current">{current_page}</a></li>'
    )
    if next_url is None:
        next_number_li = ""
        next_li = ""
    else:
        next_href = _relative_href(next_url)
        next_number_li = f'<li><a href="{next_href}">{current_page + 1}</a></li>'
        next_li = f'<li class="next"><a href="{next_href}">Next →</a></li>'
    return (
        '<ol class="pagination actions pagy" role="navigation" aria-label="Pagination">'
        f"{prev_li}{current_li}{next_number_li}{next_li}"
        "</ol>"
    )


# --- Разметка work-страницы с download-ссылкой (TC-032/033, AT-BUG-004 инкремент 3) ---
# `DownloadRepository.fetchDownloadUrl` (не bridge/JS) ищет ПЕРВОЕ вхождение
# `href="(/downloads/[^"]*\.html[^"]*)"` в сыром HTML любым regex'ом — не обязательно
# внутри `li.download`, но реальная разметка AO3 кладёт download-ссылки именно там
# (PROJECT.md §Download flow, «li.download a[href*=".html"]») — воспроизводим 1:1.
def _download_slug(title: str) -> str:
    """Приближение AO3-слага download-ссылки (пробелы/спецсимволы -> `_`). Точный
    алгоритм AO3 не документирован публично и здесь не важен: `server-replay`
    матчит по URL (см. модульный докстринг), важна только внутренняя согласованность
    между `download_href` (используется и в атрибуте `href` work-страницы, и как URL
    самой `.html`-записи) — не человекочитаемость."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return safe or "work"


def download_href(work: Work, ext: str = "html") -> str:
    """Host-relative href, как отдаёт реальный AO3 markup."""
    return f"/downloads/{work.ao3_id}/{_download_slug(work.title)}.{ext}?updated_at=0"


def download_url(work: Work, ext: str = "html") -> str:
    """Абсолютный URL — так `DownloadRepository.fetchDownloadUrl` строит итоговый адрес
    для второго GET (`"https://archiveofourown.org" + href`, см. `DownloadRepository.kt`)."""
    return f"https://archiveofourown.org{download_href(work, ext)}"


def _download_list_html(work: Work) -> str:
    """`li.download` с вложенным `ul.download-list` (PDF/HTML/MOBI/EPUB) — тот же
    контейнер, что реальный AO3 кладёт в `ul.work.navigation.actions` work-страницы.
    `document.querySelector`/regex не требуют, чтобы `a[href*=".html"]` был прямым
    потомком `li.download` — вложенность допустима."""
    exts = ("pdf", "html", "mobi", "epub")
    items = "\n".join(
        f'        <li><a href="{download_href(work, ext)}" title="{ext.upper()}">{ext.upper()}</a></li>'
        for ext in exts
    )
    return f"""
    <li class="download" title="Download">
      <a>Download</a>
      <ul class="download-list expandable" title="Download">
{items}
      </ul>
    </li>"""


# --- Узлы 1/2 критерия готовности AT-BUG-030 (bridge-tap-zone-guard,
# TC-119/120/122) — поведенческий контроль guard'а тап-зон
# (`ao3_bridge.js:1152-1166`): узел 1 — whitelisted `<button>` со span-потомком
# (closest-семантика, TC-122), узел 2 — НЕ whitelisted `<div onclick>`
# (guard-пробой, TC-120). `position: absolute; top: Nvh` — намеренно НЕ
# `margin-top` от предыдущего контента: НИ ОДИН элемент этой страницы не несёт
# `position: relative/absolute/fixed` (`.preface`/`.wrapper`/`#workskin`/`#main`
# все статичные), поэтому у абсолютно спозиционированного узла containing
# block — initial containing block (верх ДОКУМЕНТА), и `top: Nvh`
# детерминированно даёт N% от ТЕКУЩЕГО `innerHeight` устройства независимо от
# непредсказуемой высоты предшествующего контента (заголовок/download-список)
# — устойчивее фиксированного пикселя под конкретный AVD. Узел 1 — 40vh
# (середина «средней трети» [33.3%, 66.7%] — диагностическая сила негативного
# Then TC-119/TC-122, см. `bugs/AT-BUG-030.md` «Геометрия узлов 1 и 2»). Узел 2
# — 50vh (середина измеренного рецепта CH-005 [44%, 56%] — геометрия здесь
# определяет САМ ожидаемый Then TC-120, не только диагностику). Button без
# padding/border у контента, span `display:block` во весь content-box кнопки —
# доминирующая кликабельная область (критик-вход C2 TC-122: координата
# автоматизации должна физически попадать в bounding rect span'а, не в padding
# кнопки). Узлы добавляются ПОСЛЕ `_download_list_html` в исходном HTML (не
# перед ней) — regression-требование AT-BUG-030: `DownloadRepository.
# fetchDownloadUrl` ищет ПЕРВОЕ совпадение `.html`-ссылки, порядок относительно
# неё не меняется.
_TAP_ZONE_BUTTON_TOP_VH = 40
_TAP_ZONE_DIV_TOP_VH = 50


def _tap_zone_guard_nodes_html() -> str:
    return f"""
    <button data-tap-marker="button"
            onclick="this.setAttribute('data-tapped', '1')"
            style="position:absolute; top:{_TAP_ZONE_BUTTON_TOP_VH}vh; left:24px;
                   width:200px; height:60px; margin:0; padding:0; border:1px solid #333;">
      <span data-tap-marker-child="span"
            style="display:block; width:100%; height:100%; margin:0; padding:0;">Tap target</span>
    </button>
    <div data-tap-marker="div"
         onclick="this.setAttribute('data-tapped', '1')"
         style="position:absolute; top:{_TAP_ZONE_DIV_TOP_VH}vh; left:24px;
                width:200px; height:60px; background:#eee; border:1px solid #333;">Tap target (div)</div>"""


# --- Узел `#kudo_submit` (AT-BUG-035) — наблюдаемость авто-клика kudos
# (`bugs/BUG-015.md`, `docs/01-test-strategy.md` §9). `BrowserViewModel.kt`
# (`applyRating:859`, `onRateWorkRequested/pendingPanelSave:1054`) выполняет
# `evalJs(tabId, "var b=document.getElementById('kudo_submit');if(b)b.click();")`
# — без узла `#kudo_submit` в фикстуре клик — no-op, а негативные Then (TC-139..
# 143) вакуумно-истинны независимо от того, сработал ли предикат приложения
# (тот же класс ложно-зелёного, что `AT-BUG-029`). Приём — тот же, что
# `_tap_zone_guard_nodes_html` (`onclick`, пишущий факт клика в атрибут DOM,
# читаемый `driver.execute_script` через `framework/core/contexts.py::in_webview`),
# но с ИНКРЕМЕНТНЫМ счётчиком, не константой (B2, critic attempt2,
# `bugs/AT-BUG-035.md`): `TC-138`/`TC-144` различают «ровно один клик» от «два
# клика» — атрибут-константа `'1'` не отличила бы одно от другого. Baseline
# (атрибута нет) читается как `0` (`Number(null||0)`), первый клик даёт `"1"`,
# гипотетический повторный клик — `"2"`. `return false` — предотвращает переход
# по фиктивному `href="#"` в синтетической фикстуре (реальный AO3-узел —
# кнопка/ссылка с собственным JS, не имеющим значения для проверяемого
# поведения нашего приложения).
#
# Место — СИБЛИНГ `<ul class="work navigation actions">`, НЕ внутрь неё
# (критик-ревью нит 5, `bugs/AT-BUG-035.md`): `<p>` внутри `<ul>` — невалидная
# вложенность. Вставка ПОСЛЕ закрывающего `</ul>` и ДО `<div class="wrapper">`
# не сдвигает порядок/индексы узлов `_download_list_html` (внутри `<ul>`,
# полностью предшествует новому узлу) и tap-zone-guard/reading-UX узлов
# (`AT-BUG-030`, внутри `.wrapper`, идут строго ПОСЛЕ) — оба regression-
# требования держатся.
def _kudo_submit_html() -> str:
    return (
        '<p class="kudos"><a href="#" id="kudo_submit" role="button" '
        "onclick=\"this.setAttribute('data-kudo-clicked', "
        "String(1+Number(this.getAttribute('data-kudo-clicked')||0)));"
        'return false;">'
        "Give Kudos</a></p>"
    )


# --- Узел 3 критерия готовности AT-BUG-030 — высота документа >= 3×innerHeight
# эталонного AVD (`innerHeight=1800`, CH-005) — общее предусловие ЛЮБОГО кейса
# тап-зон (`docs/01-test-strategy.md` §9: короткая страница не прокручивается,
# "зона не сработала" неотличимо от "страница уже была на границе"), нужен и
# TC-119/TC-120/TC-122 (canary), и TC-123..127 (reading-UX, доработка
# test-designer 2026-07-29). `min-height` (не только количество коротких `<p>`,
# как `render_tab_marker_html`/`render_listing_filler_html`) — гарантирует
# ИТОГОВУЮ высоту документа независимо от точных font-metrics конкретного
# WebView/устройства (line-height/margin браузера может отличаться между
# окружениями — подсчёт по количеству абзацев такой гарантии не даёт); с
# запасом выше 3×1800=5400px.
WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX = 6000


def render_reading_ux_filler_html(min_height_px: int = WORK_PAGE_READING_UX_FILLER_MIN_HEIGHT_PX) -> str:
    paragraphs = "\n".join(
        f"    <p>Filler paragraph {i} for reading-UX tap-to-scroll fixture "
        f"(AT-BUG-030) — scroll padding, not real content.</p>"
        for i in range(40)
    )
    return f'<div style="min-height: {min_height_px}px;">\n{paragraphs}\n    </div>'


# --- AT-BUG-074: узлы `dd.fandom a`/`dd.words` (`dl.work.meta.group`/`dl.stats`,
# реальная разметка AO3, ПО ОБРАЗЦУ уже существующей `render_work_metadata_page_
# html`, AT-BUG-061:754-770) — `onScroll` (`ao3_bridge.js:1191-1192`) скрейпит
# ИМЕННО эти узлы (не preface `h5.fandom.tags`, которую `render_work_page_html`
# уже несёт для людей). Литерально тот же HTML-фрагмент, что и в
# `render_work_metadata_page_html` (критерий готовности AT-BUG-074 п.1) —
# скопирован буквально В ЭТОТ модуль как отдельная функция (не общий рефактор
# обеих функций), чтобы не трогать байт-в-байт вывод `render_work_metadata_
# page_html` (regression-инвариант `test_work_metadata_fetch_markup_matches_
# generator`, AT-BUG-061).
def _work_meta_group_and_stats_html(fandom: str, word_count: int | None) -> str:
    word_count = word_count if word_count is not None else 0
    return f"""<dl class="work meta group">
      <dt class="fandom tags">Fandom:</dt>
      <dd class="fandom tags">
        <ul class="commas">
          <li><a class="tag" href="/tags/{fandom}/works">{fandom}</a></li>
        </ul>
      </dd>
    </dl>
    <dl class="stats">
      <dt class="words">Words:</dt><dd class="words">{word_count}</dd>
      <dt class="chapters">Chapters:</dt><dd class="chapters">1/1</dd>
      <dt class="comments">Comments:</dt><dd class="comments">0</dd>
      <dt class="kudos">Kudos:</dt><dd class="kudos">0</dd>
      <dt class="hits">Hits:</dt><dd class="hits">1</dd>
    </dl>"""


# --- AT-BUG-074: `<div id="chapters"><div class="userstuff module">...</div></div>`
# — без него `onScroll` (`ao3_bridge.js:1170-1171`, `if (!chaptersDiv) return`)
# не подписывает `scroll`-листенер вовсе, auto-mark-as-read (`onWorkFinished`)
# физически недостижим (TC-256). Единственная глава (URL этой страницы не несёт
# `/chapters/` — `isLastPage()` тривиально `true`, «Next Chapter →» заводить не
# нужно, критерий готовности п.2). Геометрия: узел — БУКВАЛЬНО последний элемент
# `<body>` (после закрытия `#main`), сразу ПОСЛЕ узла 3 AT-BUG-030
# (`render_reading_ux_filler_html`, высота >= 3×innerHeight, внутри `.wrapper`)
# — оба узла КОНЦЕПТУАЛЬНО не конфликтуют, т.к. #chapters лежит СНАРУЖИ
# `.wrapper`, строго после него: скролл документа до самого низа (browser
# clamps `scrollTo` к максимально возможной позиции) кладёт нижнюю границу
# ПОСЛЕДНЕГО узла документа `<= window.innerHeight` по построению (тот же
# приём геометрии, что уже физически проверен `scroll_listing_to_bottom`/TC-129
# на листинговой фикстуре) — без собственной большой высоты, чтобы не отодвигать
# фактическое дно документа дальше вниз.
def _chapters_html() -> str:
    return (
        '<div id="chapters">'
        '<div class="userstuff module">'
        "<p>Chapter content for auto-mark-as-read fixture (AT-BUG-074).</p>"
        "</div></div>"
    )


def render_work_page_html(work: Work) -> str:
    """Минимальная, но структурно-валидная work-страница AO3 (`#workskin`,
    `h2.title.heading`, `h3.byline.heading a[rel=author]` — сверено с Fragility note
    `PROJECT.md`) с валидной download-ссылкой (`li.download a[href*=".html"]`,
    `_download_list_html`). Самодостаточна — без внешних `<script src>`/`<link>`.

    AT-BUG-030: тело (`.wrapper`) несёт ТРИ дополнительных узла ПОСЛЕ исходного
    `<p>`-филлера — узлы 1/2 (`_tap_zone_guard_nodes_html`, whitelisted `<button>`
    + не-whitelisted `<div onclick>`) и узел 3 (`render_reading_ux_filler_html`,
    высота >= 3×innerHeight) — нужны поведенческому контролю guard'а тап-зон
    (TC-119/120/122) и reading-UX tap-to-scroll (TC-123..127). Все три — ПОСЛЕ
    `_download_list_html` в исходном HTML (regression-требование: порядок
    относительно download-ссылки не меняется, см. докстринг узлов 1/2 выше).

    AT-BUG-035: `#kudo_submit` (`_kudo_submit_html`) — СИБЛИНГ
    `<ul class="work navigation actions">`, между ней и `<div class="wrapper">`
    — не меняет порядок/индексы ни `_download_list_html` (внутри `<ul>`), ни
    tap-zone-guard/reading-UX узлов (внутри `.wrapper`, идут строго после).

    AT-BUG-074: `dd.fandom a`/`dd.words` (`_work_meta_group_and_stats_html`) —
    СИБЛИНГ `#kudo_submit`, между ним и `<div class="wrapper">` (не меняет
    порядок ul/kudo/wrapper regression-инварианта AT-BUG-035 выше — kudo_start
    по-прежнему СТРОГО между `</ul>` и `<div class="wrapper">`). `#chapters`
    (`_chapters_html`) — СНАРУЖИ `#workskin`/`#main`, буквально последний узел
    `<body>` (см. докстринг `_chapters_html` про геометрию scroll-to-bottom)."""
    title = html.escape(work.title)
    author = html.escape(work.author)
    fandom = html.escape(work.fandom)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title} | Archive of Our Own</title></head>
<body>
<div id="main" class="works-show region" role="main">
  <div id="workskin">
    <div class="preface group">
      <h2 class="title heading">{title}</h2>
      <h3 class="byline heading"><a rel="author" href="/users/{author}/pseuds/{author}">{author}</a></h3>
      <h5 class="fandom tags"><a class="tag" href="/tags/{fandom}/works">{fandom}</a></h5>
    </div>
    <ul class="work navigation actions" role="navigation">
      {_download_list_html(work)}
    </ul>
    {_kudo_submit_html()}
    {_work_meta_group_and_stats_html(fandom, work.word_count)}
    <div class="wrapper">
      <p>Test fixture body for download-flow recording ({work.word_count} words).</p>
      {_tap_zone_guard_nodes_html()}
      {render_reading_ux_filler_html()}
    </div>
  </div>
</div>
{_chapters_html()}
</body>
</html>
"""


def render_downloaded_work_html(work: Work) -> str:
    """Содержимое самого скачиваемого `.html`-файла — минимальный self-contained AO3
    download export (`#preface`/`#chapters .userstuff`). Приложение само инжектирует
    mobile viewport/reader CSS при открытии локального файла (`BrowserScreen.kt
    injectReaderCss/loadTabContent`, см. `framework/web/downloaded_work_page.py`) —
    фикстуре не нужно приносить свою стилизацию."""
    title = html.escape(work.title)
    author = html.escape(work.author)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<div id="preface">
  <h1>{title}</h1>
  <h3 class="byline">{author}</h3>
</div>
<div id="chapters">
  <div class="userstuff">
    <p>Downloaded fixture body for {title}.</p>
  </div>
</div>
</body>
</html>
"""


# --- AT-BUG-061: work-страница для HttpURLConnection-пути «Fetch missing
# metadata» (`SettingsViewModel.fetchAo3WorkPage`/`parseAo3WorkHtml`,
# SettingsScreen.kt:259-319) — URL-шаблон `works/<id>?view_adult=true`,
# ДРУГОЙ сетевой стек (голый `HttpURLConnection`, не WebView-навигация и не
# `OkHttpClient` download-flow) И ДРУГОЙ парсер (`parseAo3WorkHtml` — узкие
# regex на СЫРОЙ HTML-строке, не `document.querySelector`/bridge-JS). Матчинг
# server-replay не зависит от сетевого стека клиента (см. модульный докстринг —
# только scheme+method+path+query+host+port, без заголовков), поэтому тот же
# приём (`make_html_get_flow`) годится и для этого класса трафика; факт, что
# device-wide прокси реально перехватывает ИМЕННО `HttpURLConnection` этого
# пути (не только уже проверенные WebView/`OkHttpClient`), — эмпирически
# сверен отдельным мини-прогоном приложения в replay, задокументированным в
# `bugs/AT-BUG-061.md` §Обсуждение (по образцу проверки `work_with_download.mitm`
# в AT-BUG-004), не только выведен из кода.
#
# `parseAo3WorkHtml` регексы ОТЛИЧАЮТСЯ от `render_work_page_html`/`_blurb_html`
# (download-flow/листинг): fandom ищет `<dd[^>]+class="fandom tags"[^>]*>(.*?)</dd>`
# — ПОЛНЫЙ tags-список реального AO3 (`dl.work.meta.group`, "Associated names"),
# НЕ `<h5 class="fandom tags">` preface-строку (`render_work_page_html`); word
# count ищет `<dd[^>]+class="words"[^>]*>([\d,]+)</dd>` статистики (`dl.stats`),
# которой `render_work_page_html` вовсе не несёт (та функция строит
# download-flow страницу — `dl.stats` там не нужен). Поэтому — ОТДЕЛЬНЫЙ рендер,
# не переиспользование `render_work_page_html`/`_blurb_html`: смешение сломало
# бы позиционные инварианты существующих юнитов AT-BUG-030/035 (порядок узлов
# относительно `_download_list_html`/`.wrapper` в `render_work_page_html`) и
# дало бы разметку, НЕ бьющую с реальным regex-парсером этого пути.
WORK_METADATA_FETCH_FILENAME = "work_metadata_fetch.mitm"

# ao3_id из «безопасного» синтетического диапазона (конвенция `works.py`) — НЕ
# пересекается ни с одним ao3_id, зарезервированным в `framework/data/works.py`
# (сверено: 900000001-5, 900000901-10, 900000038/039/031/271/272/103).
# `title`/`author`/`fandom`/`word_count` этих `Work` — ЦЕЛЕВОЙ (скрейпнутый)
# результат, а НЕ текущее состояние строки Room: Given TC-186/187 засевает
# строку с ЭТИМ ЖЕ `ao3_id`, но `title=""` (см. `bugs/AT-BUG-061.md` критерий
# готовности) — сравнение "before/after" и есть проверяемый факт кейсов.
METADATA_FETCH_WORK_A = Work(
    "900000186", "TC-186 Scraped Work Title", "scraped_author_186",
    "Scraped Fandom One", 4321,
)
METADATA_FETCH_WORK_SECOND = Work(
    "900000187", "TC-187 Second Scraped Work Title", "scraped_author_187",
    "Scraped Fandom Two", 1234,
)
# Работа B (TC-186 Given, "скрейп НЕ даёт результата"): записана как HTTP 404
# (`make_html_get_flow(status=404)`) на ЭТОТ ao3_id — `fetchAo3WorkPage` трактует
# 404 как «работы не существует» и возвращает `null` НЕМЕДЛЕННО (без ретраев/
# `delay()`, в отличие от прочих кодов/исключений). Без отдельного `Work`
# (title/author/fandom для несуществующей страницы не нужны).
METADATA_FETCH_WORK_B_AO3_ID = "900000188"


def work_metadata_fetch_url(ao3_id: str) -> str:
    """`fetchAo3WorkPage` строит URL как
    `"https://archiveofourown.org/works/$ao3Id?view_adult=true"`
    (SettingsScreen.kt:260) — воспроизводим 1:1 (server-replay матчит по
    scheme+method+path+query+host+port, см. модульный докстринг)."""
    return f"https://archiveofourown.org/works/{ao3_id}?view_adult=true"


def render_work_metadata_page_html(work: Work) -> str:
    """Work-страница под РЕГЕКСЫ `parseAo3WorkHtml` (SettingsScreen.kt:287-318),
    не под bridge-JS/`document.querySelector` (см. блочный докстринг выше):
    - title: `<h2[^>]+class="[^"]*title[^"]*"[^>]*>...</h2>` — та же форма, что
      `render_work_page_html`/`_blurb_html` уже используют (`h2.title.heading`).
    - author: `<a[^>]+rel="author"[^>]*>...</a>` — форма не зависит от
      родительского тега (`h3.byline.heading`, как у реального AO3/download-flow).
    - fandom: `<dd[^>]+class="fandom tags"[^>]*>(.*?)</dd>` (DOT_MATCHES_ALL),
      внутри — `<a[^>]+class="tag"[^>]*>...</a>`. РЕАЛЬНЫЙ AO3 несёт fandom
      ДВАЖДЫ (preface `h5.fandom.tags` для людей + tags-список `dl.work.meta.group`
      `dd.fandom.tags` для машинного разбора) — эта фикстура несёт ОБА узла:
      preface (человекочитаемый, той же формы, что `render_work_page_html`) И
      `dd.fandom.tags` (то, что реально парсит приложение).
    - word count: `<dd[^>]+class="words"[^>]*>([\\d,]+)</dd>` — статистика
      `dl.stats`, отдельная от preface."""
    title = html.escape(work.title)
    author = html.escape(work.author)
    fandom = html.escape(work.fandom)
    word_count = work.word_count if work.word_count is not None else 0
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{title} | Archive of Our Own</title></head>
<body>
<div id="main" class="works-show region" role="main">
  <div id="workskin">
    <div class="preface group">
      <h2 class="title heading">{title}</h2>
      <h3 class="byline heading"><a rel="author" href="/users/{author}/pseuds/{author}">{author}</a></h3>
      <h5 class="fandom tags"><a class="tag" href="/tags/{fandom}/works">{fandom}</a></h5>
    </div>
    <dl class="work meta group">
      <dt class="fandom tags">Fandom:</dt>
      <dd class="fandom tags">
        <ul class="commas">
          <li><a class="tag" href="/tags/{fandom}/works">{fandom}</a></li>
        </ul>
      </dd>
    </dl>
    <div class="wrapper">
      <p>Test fixture body for metadata-fetch recording (AT-BUG-061).</p>
      <dl class="stats">
        <dt class="words">Words:</dt><dd class="words">{word_count}</dd>
        <dt class="chapters">Chapters:</dt><dd class="chapters">1/1</dd>
        <dt class="comments">Comments:</dt><dd class="comments">0</dd>
        <dt class="kudos">Kudos:</dt><dd class="kudos">0</dd>
        <dt class="hits">Hits:</dt><dd class="hits">1</dd>
      </dl>
    </div>
  </div>
</div>
</body>
</html>
"""
