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
    `server_replay_extra=forward` на ассеты (детерминизм без сети)."""
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
