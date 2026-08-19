"""Пилот L2 (docs/tasks/p2-pyramid-bridge.md N5): бейдж рейтинга Rate-кнопки
листинга (`updateRateButton`, `ao3_bridge.js`) — `window.applyRatings(...)`
красит `[data-ao3-rate-btn]` цветом `BADGE[rating]` (bg/border), без рейтинга —
`transparent`/дефолтный цвет.

Красная проба (класс — тест обязан уметь падать, CLAUDE.md builder п.4):
`test_badge_color_assertion_catches_missing_rating` доказывает, что позитивная
проверка НЕ вакуумно-истинна — тот же приём, что F-34 негативы в
`test_recording_builder_unit.py` (непокрытый href/regex ловится, не только
пропускается)."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import LOVED

_SAVE_BG_RGB = "rgb(245, 237, 228)"  # #f5ede4 — pal() светлый вариант BADGE.SAVE.bg
_SAVE_BORDER_RGB = "rgb(160, 120, 96)"  # #a07860 — BADGE.SAVE.border
_LIKE_BG_RGB = "rgb(234, 240, 232)"  # #eaf0e8 — BADGE.LIKE.bg


def _listing_html() -> str:
    return rb.render_listing_html([LOVED])


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-rate-button-uncolored-before-any-rating")
@allure.title("L2 bridge: Rate-кнопка без рейтинга -- style.background == transparent")
def test_rate_button_uncolored_before_any_rating(bridge_call):
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {"id": "bg", "type": "eval", "code": "document.querySelector('[data-ao3-rate-btn]').style.background"},
        ],
    })
    assert response["results"]["bg"] == "transparent"


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-rate-button-colored-by-applied-rating")
@allure.title("L2 bridge: applyRatings(SAVE) красит Rate-кнопку цветом BADGE.SAVE (bg+border)")
def test_rate_button_colored_by_applied_rating(bridge_call):
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "apply",
                "type": "eval",
                "code": f"window.applyRatings(JSON.stringify({{'{LOVED.ao3_id}':'SAVE'}})); 'done'",
            },
            {"id": "bg", "type": "eval", "code": "document.querySelector('[data-ao3-rate-btn]').style.background"},
            {
                "id": "border",
                "type": "eval",
                "code": "document.querySelector('[data-ao3-rate-btn]').style.borderColor",
            },
        ],
    })
    assert response["results"]["bg"] == _SAVE_BG_RGB
    assert response["results"]["border"] == _SAVE_BORDER_RGB


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-rate-button-recolors-on-rating-change")
@allure.title("L2 bridge: смена SAVE -> LIKE перекрашивает Rate-кнопку заново")
def test_rate_button_recolors_on_rating_change(bridge_call):
    """SAVE -> LIKE — бейдж перекрашивается заново (не залипает на первом
    применённом цвете), доказывает, что `updateRateButton` перечитывает
    `rating`, а не красит один раз при первой инъекции."""
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "applySave",
                "type": "eval",
                "code": f"window.applyRatings(JSON.stringify({{'{LOVED.ao3_id}':'SAVE'}})); 'done'",
            },
            {
                "id": "applyLike",
                "type": "eval",
                "code": f"window.applyRatings(JSON.stringify({{'{LOVED.ao3_id}':'LIKE'}})); 'done'",
            },
            {"id": "bg", "type": "eval", "code": "document.querySelector('[data-ao3-rate-btn]').style.background"},
        ],
    })
    assert response["results"]["bg"] == _LIKE_BG_RGB


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-rate-button-reverts-to-transparent-when-rating-removed")
@allure.title("L2 bridge: снятие рейтинга возвращает Rate-кнопку к transparent")
def test_rate_button_reverts_to_transparent_when_rating_removed(bridge_call):
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "applySave",
                "type": "eval",
                "code": f"window.applyRatings(JSON.stringify({{'{LOVED.ao3_id}':'SAVE'}})); 'done'",
            },
            {"id": "applyEmpty", "type": "eval", "code": "window.applyRatings(JSON.stringify({})); 'done'"},
            {"id": "bg", "type": "eval", "code": "document.querySelector('[data-ao3-rate-btn]').style.background"},
        ],
    })
    assert response["results"]["bg"] == "transparent"


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-badge-color-assertion-catches-missing-rating")
@allure.title("L2 bridge, красная проба: пустой applyRatings НЕ красит бейдж (различает покрашено/не покрашено)")
def test_badge_color_assertion_catches_missing_rating(bridge_call):
    """Красная проба: если бы `applyRatings` НЕ красил бейдж (регресс класса
    "бейдж не обновляется без ручного reload", R-04 docs/01-test-strategy.md),
    цвет остался бы `transparent` — этот тест доказывает, что позитивы выше
    ДЕЙСТВИТЕЛЬНО различают "покрашено"/"не покрашено", подавая заведомо ПУСТОЙ
    объект рейтингов и требуя `transparent`, а НЕ SAVE-цвет."""
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {"id": "applyEmpty", "type": "eval", "code": "window.applyRatings(JSON.stringify({})); 'done'"},
            {"id": "bg", "type": "eval", "code": "document.querySelector('[data-ao3-rate-btn]').style.background"},
        ],
    })
    assert response["results"]["bg"] != _SAVE_BG_RGB
    assert response["results"]["bg"] == "transparent"
