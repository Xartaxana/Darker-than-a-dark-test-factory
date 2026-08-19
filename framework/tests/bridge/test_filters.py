"""Пилот L2 (docs/tasks/p2-pyramid-bridge.md N5): `applyAllFilters` — hide/dim
режимы фильтрации по рейтингу (`ao3_bridge.js`, R-06 docs/01-test-strategy.md).
hide -> `li.style.display='none'`; dim -> `li.style.display=''`,
`li.style.opacity='0.3'`. Не layout-гейтировано (B4 fail-open граница НЕ
задета) — display/opacity читаются напрямую из inline-style, не из
`getBoundingClientRect()`/scroll."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import DISLIKED, LOVED


def _listing_html() -> str:
    return rb.render_listing_html([LOVED, DISLIKED])


def _display_opacity_action(work_id: str, action_id: str) -> dict:
    return {
        "id": action_id,
        "type": "eval",
        "code": (
            f"var li = document.getElementById('work_{work_id}'); "
            "JSON.stringify({display: li.style.display, opacity: li.style.opacity})"
        ),
    }


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-hide-mode-sets-display-none-for-hidden-rating")
@allure.title("L2 bridge: hide-режим ставит display=none для скрытого рейтинга")
def test_hide_mode_sets_display_none_for_hidden_rating(bridge_call):
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "apply",
                "type": "eval",
                "code": (
                    "window.applyRatings(JSON.stringify("
                    f"{{'{LOVED.ao3_id}':'SAVE','{DISLIKED.ao3_id}':'DISLIKE'}}"
                    ")); window.setHiddenRatings(['DISLIKE']); 'done'"
                ),
            },
            _display_opacity_action(DISLIKED.ao3_id, "hidden"),
            _display_opacity_action(LOVED.ao3_id, "visible"),
        ],
    })
    hidden = response["results"]["hidden"]
    visible = response["results"]["visible"]
    assert '"display":"none"' in hidden
    assert '"display":""' in visible


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-dim-mode-sets-opacity-instead-of-display-none")
@allure.title("L2 bridge: dim-режим ставит opacity=0.3, НЕ display=none")
def test_dim_mode_sets_opacity_instead_of_display_none(bridge_call):
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "apply",
                "type": "eval",
                "code": (
                    "window.setFilterMode('dim'); "
                    "window.applyRatings(JSON.stringify("
                    f"{{'{LOVED.ao3_id}':'SAVE','{DISLIKED.ao3_id}':'DISLIKE'}}"
                    ")); window.setHiddenRatings(['DISLIKE']); 'done'"
                ),
            },
            _display_opacity_action(DISLIKED.ao3_id, "dimmed"),
        ],
    })
    dimmed = response["results"]["dimmed"]
    assert '"display":""' in dimmed
    assert '"opacity":"0.3"' in dimmed


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-unhidden-work-keeps-full-opacity")
@allure.title("L2 bridge, красная проба: невидимость затемняет ТОЛЬКО исключённую работу, не всех")
def test_unhidden_work_keeps_full_opacity(bridge_call):
    """Красная проба (значимость): без реальной фильтрации `dim` красил бы
    (или оставлял затемнённой) КАЖДУЮ работу, не только исключённую — доказываем,
    что LOVED (SAVE, не в hidden-set) остаётся `opacity=''`, отличая
    "затемнена конкретно DISLIKED" от "затемнено всё подряд"."""
    response = bridge_call({
        "html": _listing_html(),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "apply",
                "type": "eval",
                "code": (
                    "window.setFilterMode('dim'); "
                    "window.applyRatings(JSON.stringify("
                    f"{{'{LOVED.ao3_id}':'SAVE','{DISLIKED.ao3_id}':'DISLIKE'}}"
                    ")); window.setHiddenRatings(['DISLIKE']); 'done'"
                ),
            },
            _display_opacity_action(LOVED.ao3_id, "loved"),
        ],
    })
    loved = response["results"]["loved"]
    assert '"opacity":""' in loved
    assert '"display":""' in loved
