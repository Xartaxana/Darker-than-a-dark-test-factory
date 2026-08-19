"""Device-free юнит-проба `framework/core/capture_addon.py` (AT-BUG-073,
критерий готовности п.4 «перехват исходящего тела запроса публикации»,
критик-вход attempt 4 — класс-пробел «новый примитив без device-free
юнит-пробы», собратья: `test_mitm_port_race_unit.py`/`test_mitm_proxy_
reachable_unit.py`/`test_mitm_upstream_guard_unit.py`).

Стиль пробы — критик-вход attempt 4: `ctx.options` заменён простым stub'ом
(`SimpleNamespace`, mitmproxy сам присваивает этот атрибут модулю `ctx`
динамически при живом мастере — здесь его нет, поэтому монки-патчим напрямую),
а `flow` — РЕАЛЬНЫЙ `mitmproxy.http.HTTPFlow`/`http.Request.make(...)`
(переиспользует `recording_builder._client_conn`/`_server_conn`, те же
хелперы, что строят flow'ы для `.mitm`-фикстур во ВСЕМ репозитории) — не
самодельный дубль-стаб класса `flow`, чтобы `flow.request.pretty_url`/
`.method`/`.get_text()` были НАСТОЯЩИМ поведением mitmproxy, не
реимплементацией его контракта в тесте.

Устройство/mitmdump/порт 8080 НЕ трогаются — `RequestBodyCapture.request()`
дергается напрямую с готовым flow, addon не поднимает никакого процесса.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import allure
import pytest

from framework.core import capture_addon
from framework.data import recording_builder as rb
from mitmproxy import http


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогаем (тот же приём, что соседние
    `test_mitm_*_unit.py`)."""
    yield


def _make_flow(method: str, url: str, body: bytes) -> http.HTTPFlow:
    """Строит РЕАЛЬНЫЙ `http.HTTPFlow` с непустым телом ЗАПРОСА — в отличие
    от `recording_builder.make_json_flow` (тело запроса там ВСЕГДА `b""`,
    это конструктор ОТВЕТА .mitm-мока, не входящего запроса приложения),
    здесь `body` — то, что addon должен перехватить как `flow.request.body`."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or "example.invalid"
    flow = http.HTTPFlow(rb._client_conn(url), rb._server_conn(host, url))
    flow.request = http.Request.make(method, url, body)
    return flow


def _capture(monkeypatch, out: str, substr: str) -> None:
    monkeypatch.setattr(
        capture_addon.ctx, "options",
        SimpleNamespace(capture_out=out, capture_url_substr=substr),
        raising=False,
    )


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-empty-substr-matches-all")
@allure.title("Проба: RequestBodyCapture.request() с ПУСТОЙ capture_url_substr перехватывает ЛЮБОЙ POST/PUT/PATCH (критик-вход attempt 4, блокер 1) (device-free)")
def test_request_empty_substr_captures_any_matching_method(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, str(out), "")
    addon = capture_addon.RequestBodyCapture()
    flow = _make_flow("PUT", "https://gitlab.com/api/v4/snippets/42", b'{"file_name":"x"}')

    addon.request(flow)

    assert out.exists(), "пустая capture_url_substr должна перехватывать ВСЕ, файл обязан появиться"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert '"method": "PUT"' in lines[0]
    assert '\\"file_name\\":\\"x\\"' in lines[0]  # тело записано JSON-строкой -> кавычки экранированы


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-empty-substr-multiple-urls")
@allure.title("Проба: пустая capture_url_substr перехватывает запросы НА РАЗНЫЕ хосты/пути (не просто 'не падает', реально ловит несовпадающие URL) (device-free)")
def test_request_empty_substr_matches_unrelated_urls(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, str(out), "")
    addon = capture_addon.RequestBodyCapture()

    addon.request(_make_flow("POST", "https://example.com/anything", b"{}"))
    addon.request(_make_flow("PUT", "https://gitlab.com/api/v4/snippets/1", b"{}"))

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-filters-by-substr")
@allure.title("Проба: заданная capture_url_substr фильтрует — совпадающий URL перехвачен, несовпадающий пропущен (device-free)")
def test_request_filters_by_substr(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, str(out), "/api/v4/snippets")
    addon = capture_addon.RequestBodyCapture()

    addon.request(_make_flow("POST", "https://example.com/unrelated", b"{}"))
    addon.request(_make_flow("PUT", "https://gitlab.com/api/v4/snippets/1", b'{"a":1}'))

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "api/v4/snippets" in lines[0]


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-ignores-get")
@allure.title("Проба: GET на совпадающий URL НЕ перехватывается (без тела публикации — нечего снимать) (device-free)")
def test_request_ignores_get_even_when_url_matches(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, str(out), "")
    addon = capture_addon.RequestBodyCapture()

    addon.request(_make_flow("GET", "https://gitlab.com/api/v4/snippets/1/raw", b""))

    assert not out.exists(), "GET не несёт тела публикации — перехватывать нечего, файл не должен появиться"


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-noop-without-capture-out")
@allure.title("Проба: capture_out пуст (аддон подключён 'на всякий случай' без активного перехвата) — request() НЕ пишет файл и не бросает (device-free)")
def test_request_noop_without_capture_out(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, "", "/api/v4/snippets")  # capture_out пуст -- ключевое условие
    addon = capture_addon.RequestBodyCapture()

    addon.request(_make_flow("PUT", "https://gitlab.com/api/v4/snippets/1", b"{}"))

    assert not out.exists()


@pytest.mark.p1
@allure.id("AT-BUG-073-capture-addon-put-post-patch-all-captured")
@allure.title("Проба: POST/PUT/PATCH ВСЕ три метода публикации перехватываются (не только PUT, используемый updateSnippet) (device-free)")
def test_request_captures_all_publish_methods(tmp_path, monkeypatch):
    out = tmp_path / "capture.jsonl"
    _capture(monkeypatch, str(out), "")
    addon = capture_addon.RequestBodyCapture()

    for method in ("POST", "PUT", "PATCH"):
        addon.request(_make_flow(method, "https://gitlab.com/api/v4/snippets/1", b"{}"))

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    methods_seen = [m for m in ("POST", "PUT", "PATCH") if any(f'"method": "{m}"' in l for l in lines)]
    assert sorted(methods_seen) == ["PATCH", "POST", "PUT"]
