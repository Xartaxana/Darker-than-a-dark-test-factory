"""Пилот L2 (docs/tasks/p2-pyramid-bridge.md N5): `getWorkData` (`ao3_bridge.js`)
— payload, отправляемый в `Android.rateWork(...)` при клике по Rate-кнопке
листинга (`signalRate`). Клик по `[data-ao3-rate-btn]` — реальный DOM-эвент
(`.click()`), не прямой вызов внутренней функции (та не экспортирована на
`window`) — тест доказывает контракт end-to-end через ту же цепочку событий,
что использует приложение."""
from __future__ import annotations

import json

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import LOVED


def _click_rate_button_action() -> dict:
    return {
        "id": "click",
        "type": "eval",
        "code": f"document.querySelector('[data-ao3-rate-btn=\"{LOVED.ao3_id}\"]').click(); 'clicked'",
    }


def _rate_work_call(response: dict) -> dict:
    calls = [c for c in response["androidCalls"] if c["method"] == "rateWork"]
    assert len(calls) == 1, f"ожидался ровно один Android.rateWork(...) вызов, получено: {calls}"
    return calls[0]


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-get-work-data-payload-matches-blurb-fields")
@allure.title("L2 bridge: клик по Rate-кнопке шлёт Android.rateWork с payload'ом getWorkData, полностью совпадающим с блёрбом")
def test_get_work_data_payload_matches_blurb_fields(bridge_call):
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": "https://archiveofourown.org/works",
        "actions": [_click_rate_button_action()],
    })
    call = _rate_work_call(response)
    work_id, title, author, fandom, word_count, rel_tags_json, freeform_tags_json = call["args"]

    assert work_id == LOVED.ao3_id
    assert title == LOVED.title
    assert author == LOVED.author
    assert fandom == LOVED.fandom
    assert word_count == str(LOVED.word_count)
    # relTags/freeformTags — литералы _blurb_html (recording_builder.py), не
    # поля Work (Work не несёт relationship/freeform, докстринг Р3).
    assert json.loads(rel_tags_json) == ["Test Ship/Other Ship"]
    assert json.loads(freeform_tags_json) == ["Fluff"]


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-get-work-data-word-count-reflects-fixture-value-not-hardcoded-zero")
@allure.title("L2 bridge, красная проба: wordCount payload'а отражает РЕАЛЬНОЕ значение фикстуры, не дефолтный 0")
def test_get_work_data_word_count_reflects_fixture_value_not_hardcoded_zero(bridge_call):
    """Красная проба: если бы `getWorkData` читал wordCount неправильным
    селектором (регресс класса AT-BUG-074 — узел заявлен, но не читается),
    `parseInt` на пустом узле дал бы `0` НЕЗАВИСИМО от реального значения
    фикстуры — доказываем на РАЗНЫХ word_count двух работ, что оба доходят до
    payload'а различными, не совпадающими с дефолтным нулём."""
    from framework.data.works import KUDOSED  # noqa: WPS433 - локальный импорт для ясности сравнения

    html = rb.render_listing_html([LOVED, KUDOSED])
    response = bridge_call({
        "html": html,
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "clickLoved",
                "type": "eval",
                "code": f"document.querySelector('[data-ao3-rate-btn=\"{LOVED.ao3_id}\"]').click(); 'clicked'",
            },
            {
                "id": "clickKudosed",
                "type": "eval",
                "code": f"document.querySelector('[data-ao3-rate-btn=\"{KUDOSED.ao3_id}\"]').click(); 'clicked'",
            },
        ],
    })
    calls = {c["args"][0]: c for c in response["androidCalls"] if c["method"] == "rateWork"}
    assert calls[LOVED.ao3_id]["args"][4] == str(LOVED.word_count)
    assert calls[KUDOSED.ao3_id]["args"][4] == str(KUDOSED.word_count)
    assert LOVED.word_count != KUDOSED.word_count  # sanity — иначе проба вырождена
    assert calls[LOVED.ao3_id]["args"][4] != "0"
    assert calls[KUDOSED.ao3_id]["args"][4] != "0"
