"""Пилот L2 (docs/tasks/p2-pyramid-bridge.md N5): персистентность фильтра
"Main pairing only" через `localStorage['ao3_main_pairing']`
(`injectMainPairingCheckbox`, `ao3_bridge.js`) — находка r1 recon: работает
против jsdom, но требует реальную разметку формы Sort & Filter (факт 5 recon —
`#include_relationship_tags`/`#work-filters` живут ТОЛЬКО в записанной
`sort_filter_form.mitm`, не в генерируемых фикстурах `recording_builder.py`).

Path A (`/tags/[ship]/works`, `detectActiveShip`) — единственный практичный
путь для device-free пробы: Path B (ровно один relationship-чекбокс отмечен из
списка реальных AO3-тегов) требует знания конкретных id чекбоксов, зависящих
от текущего содержимого записи; Path A определяется URL, стабилен."""
from __future__ import annotations

import allure
import pytest
from mitmproxy.io import FlowReader

from framework.config import settings
from framework.data import recording_builder as rb

_SORT_FILTER_FORM_PATH = settings.RECORDINGS_DIR / rb.SORT_FILTER_FORM_FILENAME


@pytest.fixture(scope="module")
def sort_filter_form_html() -> str:
    assert _SORT_FILTER_FORM_PATH.exists(), (
        f"{_SORT_FILTER_FORM_PATH} отсутствует — реальная запись формы Sort & Filter "
        "(AT-BUG-006, НЕ перегенерируется build_replay_recordings.py, докстринг "
        "recording_builder.SORT_FILTER_FORM_FILENAME)"
    )
    with open(_SORT_FILTER_FORM_PATH, "rb") as fo:
        flows = list(FlowReader(fo).stream())
    flow = next(f for f in flows if f.request.url == rb.SORT_FILTER_FORM_URL)
    return flow.response.get_text()


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-main-pairing-restores-checked-state-on-matching-tag-url")
@allure.title("L2 bridge: сохранённый ao3_main_pairing восстанавливает checked+__ao3MainPairing на /tags/Fluff/works")
def test_saved_main_pairing_restores_checked_state_on_matching_tag_url(bridge_call, sort_filter_form_html):
    response = bridge_call({
        "html": sort_filter_form_html,
        "url": rb.SORT_FILTER_FORM_URL,
        "localStorage": {"ao3_main_pairing": "Fluff"},
        "actions": [
            {
                "id": "checked",
                "type": "eval",
                "code": "document.querySelector('[data-ao3-main-pairing-cb]').checked",
            },
            {"id": "mainPairing", "type": "eval", "code": "window.__ao3MainPairing"},
        ],
    })
    assert response["results"]["checked"] is True
    assert response["results"]["mainPairing"] == {"text": "Fluff"}


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-main-pairing-no-saved-value-leaves-checkbox-unchecked")
@allure.title("L2 bridge, красная проба: без localStorage-значения чекбокс main-pairing не отмечен")
def test_no_saved_main_pairing_leaves_checkbox_unchecked(bridge_call, sort_filter_form_html):
    """Красная проба (значимость): без localStorage-значения restore-ветка НЕ
    должна отмечать чекбокс — доказывает, что True выше пришёл ИМЕННО из
    localStorage, а не из безусловного дефолта инъекции."""
    response = bridge_call({
        "html": sort_filter_form_html,
        "url": rb.SORT_FILTER_FORM_URL,
        "actions": [
            {
                "id": "checked",
                "type": "eval",
                "code": "document.querySelector('[data-ao3-main-pairing-cb]').checked",
            },
        ],
    })
    assert response["results"]["checked"] is False


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-main-pairing-submit-checked-persists-ship-to-local-storage")
@allure.title("L2 bridge: submit формы с отмеченным чекбоксом сохраняет ship в localStorage")
def test_submitting_checked_filter_persists_ship_to_local_storage(bridge_call, sort_filter_form_html):
    response = bridge_call({
        "html": sort_filter_form_html,
        "url": rb.SORT_FILTER_FORM_URL,
        "actions": [
            {"id": "before", "type": "eval", "code": "localStorage.getItem('ao3_main_pairing')"},
            {
                "id": "check",
                "type": "eval",
                "code": "document.querySelector('[data-ao3-main-pairing-cb]').checked = true; 'checked'",
            },
            {
                "id": "submit",
                "type": "eval",
                "code": (
                    "document.getElementById('work-filters').dispatchEvent("
                    "new window.Event('submit', {bubbles: true, cancelable: true})); 'submitted'"
                ),
            },
            {"id": "after", "type": "eval", "code": "localStorage.getItem('ao3_main_pairing')"},
        ],
    })
    assert response["results"]["before"] is None
    assert response["results"]["after"] == "Fluff"


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-main-pairing-submit-unchecked-clears-local-storage")
@allure.title("L2 bridge, красная проба: submit формы с СНЯТЫМ чекбоксом очищает localStorage")
def test_submitting_unchecked_filter_clears_local_storage(bridge_call, sort_filter_form_html):
    """Красная проба (значимость): оставленный НЕотмеченным чекбокс на submit
    обязан ОЧИСТИТЬ прежде сохранённое значение (`localStorage.removeItem`),
    не оставлять его молча — доказывает, что submit-обработчик читает
    `cb.checked`, а не пишет безусловно."""
    response = bridge_call({
        "html": sort_filter_form_html,
        "url": rb.SORT_FILTER_FORM_URL,
        "localStorage": {"ao3_main_pairing": "Fluff"},
        "actions": [
            {
                "id": "uncheck",
                "type": "eval",
                "code": "document.querySelector('[data-ao3-main-pairing-cb]').checked = false; 'unchecked'",
            },
            {
                "id": "submit",
                "type": "eval",
                "code": (
                    "document.getElementById('work-filters').dispatchEvent("
                    "new window.Event('submit', {bubbles: true, cancelable: true})); 'submitted'"
                ),
            },
            {"id": "after", "type": "eval", "code": "localStorage.getItem('ao3_main_pairing')"},
        ],
    })
    assert response["results"]["after"] is None
