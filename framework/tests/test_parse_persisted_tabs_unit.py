"""Device-free матрица `app_steps._parse_persisted_tabs` (AT-BUG-055, часть 2):
раньше БИТЫЙ/обрезанный `open_tabs_urls` (найден regex'ом, но `json.loads`
падает) молча становился `[]` — неотличимо от «вкладок реально нет». Ключ
ОТСУТСТВУЕТ (реально отсутствующий `open_tabs_urls`, до первой записи) —
единственный легитимный путь к пустому списку; НАЙДЕННЫЙ, но нечитаемый ключ —
теперь явный `RuntimeError`, не вакуумный `[]`.

Не требует устройства: `_parse_persisted_tabs` — чистая функция парсинга,
вызывается напрямую с синтетическим XML."""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


_VALID_ONE_TAB = (
    '<string name="open_tabs_urls">[{&quot;url&quot;:&quot;https://archiveofourown.org/&quot;,'
    '&quot;historyEntries&quot;:[],&quot;historyIndex&quot;:0,&quot;scrollY&quot;:0}]</string>'
)

_NO_KEY_AT_ALL = '<map>\n    <int name="active_tab_index" value="0" />\n</map>'

# Ключ ПРИСУТСТВУЕТ (regex матчит), но JSON внутри обрезан/битый — имитирует
# повреждённый/усечённый ответ run-as (например транспорт оборвал вывод на
# середине), а не легитимное отсутствие вкладок.
_TRUNCATED_JSON = '<string name="open_tabs_urls">[{&quot;url&quot;:&quot;https://ar</string>'
_GARBAGE_JSON = '<string name="open_tabs_urls">not json at all</string>'


@pytest.mark.p1
@allure.id("AT-BUG-055-parse-persisted-tabs-absent-key-is-legit-empty")
@allure.title("_parse_persisted_tabs: реально отсутствующий ключ open_tabs_urls — валидный []")
def test_absent_key_returns_empty_list():
    assert app_steps._parse_persisted_tabs(_NO_KEY_AT_ALL) == []


@pytest.mark.p1
@allure.id("AT-BUG-055-parse-persisted-tabs-valid-json-parsed")
@allure.title("_parse_persisted_tabs: валидный JSON парсится в список TabSnapshot")
def test_valid_json_parses():
    tabs = app_steps._parse_persisted_tabs(_VALID_ONE_TAB)
    assert tabs == [{"url": "https://archiveofourown.org/", "historyEntries": [], "historyIndex": 0, "scrollY": 0}]


@pytest.mark.p1
@allure.id("AT-BUG-055-parse-persisted-tabs-truncated-json-raises")
@allure.title("Регресс-замок: НАЙДЕННЫЙ, но обрезанный/битый open_tabs_urls — RuntimeError, не вакуумный [] (AT-BUG-055)")
@pytest.mark.parametrize("raw", [_TRUNCATED_JSON, _GARBAGE_JSON], ids=["truncated", "garbage"])
def test_present_but_malformed_key_raises(raw):
    with pytest.raises(RuntimeError, match="AT-BUG-055"):
        app_steps._parse_persisted_tabs(raw)
