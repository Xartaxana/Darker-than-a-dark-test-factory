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
перегенерировать записи ЭТИМ модулем (`python scripts/build_replay_recordings.py`),
а не редактировать бинарный `.mitm` руками.
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


def make_html_get_flow(url: str, body: str) -> http.HTTPFlow:
    """Один flow: `GET {url}` -> `200 text/html`, тело `body`.

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
        200, body.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
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


def render_listing_html(works: list[Work], heading: str = "Test Fixture Listing") -> str:
    """Минимальная, но структурно-валидная страница листинга AO3: `ol.work.index.group`
    с одним `li[id^="work_"].work.blurb` на каждую `Work`. Никаких внешних
    `<script src>`/`<link rel=stylesheet>` — самодостаточна, не требует
    `server_replay_extra=forward` на ассеты (детерминизм без сети).

    Принимает `works` как есть, БЕЗ дедупликации по `ao3_id` — намеренно: TC-012
    (AT-BUG-004 инкремент 3) требует листинг с ДВУМЯ `<li id="work_{id}">` одного и
    того же `ao3_id` (см. `build_listing_duplicate_work` в
    `scripts/build_replay_recordings.py`, вызывающий `render_listing_html([work, work])`).
    Дублирующиеся `id` невалидны по спеке HTML, но реальные браузеры/`querySelectorAll`
    это допускают — соответствует тому, что должен пережить `applyRatings`."""
    blurbs = "\n".join(_blurb_html(w) for w in works)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{html.escape(heading)} | Archive of Our Own</title></head>
<body>
<div id="main" class="works-index dashboard region" role="main">
  <h2 class="heading">{html.escape(heading)}</h2>
  <ol class="work index group">
    {blurbs}
  </ol>
</div>
</body>
</html>
"""


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


def render_work_page_html(work: Work) -> str:
    """Минимальная, но структурно-валидная work-страница AO3 (`#workskin`,
    `h2.title.heading`, `h3.byline.heading a[rel=author]` — сверено с Fragility note
    `PROJECT.md`) с валидной download-ссылкой (`li.download a[href*=".html"]`,
    `_download_list_html`). Самодостаточна — без внешних `<script src>`/`<link>`."""
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
    <div class="wrapper">
      <p>Test fixture body for download-flow recording ({work.word_count} words).</p>
    </div>
  </div>
</div>
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
