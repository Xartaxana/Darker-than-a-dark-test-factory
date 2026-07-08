"""Юнит-тесты бейджа «кто сейчас работает» на живой борде (board_view.py).

Контекст: board_view/board_server переиспользуют парсер и STATUS_MAP из board_sync,
но до этой правки не показывали assignee/labels — проекция lock (см. board_sync
_assignee_for) была не видна на карточке. Правило то же, что и в board_sync:
непустой lock -> бейдж с именем агента; пустой/отсутствующий lock -> ничего
(assignee "qa-agents" не показываем, чтобы не шуметь).

render() используется ОБОИМИ режимами (board_server.py live=True и статический
Save-BoardHtml через board_view.build() -> render(by_type)), поэтому тесты
прогоняют оба варианта live=True/False.

Тесты работают в tmp_path-репо (фикстура `repo` из conftest.py), реальные
test-cases/bugs/runs не затрагиваются. Запуск:
    python -m pytest scripts/tests -q
"""
from __future__ import annotations

import re

import board_view as bv


def _card_chunk(html_str: str, key: str) -> str:
    """Возвращает HTML-фрагмент одной карточки (между её `<div class="card"` и
    следующим), по data-key. Устойчиво к порядку карточек в колонке."""
    parts = html_str.split('<div class="card"')
    for p in parts:
        if f'data-key="{key}"' in p:
            return p
    raise AssertionError(f"карточка {key} не найдена в HTML")


def _column_for_card(html_str: str, key: str) -> str:
    """Текст заголовка колонки (colhead), в которой лежит карточка `key` —
    определяем по ближайшему предшествующему в документе colhead (карточки
    рендерятся ПОСЛЕ заголовка своей колонки)."""
    idx = html_str.index(f'data-key="{key}"')
    colheads = list(re.finditer(r'<div class="colhead"[^>]*>([^<]+)<b>', html_str))
    preceding = [m for m in colheads if m.start() < idx]
    assert preceding, f"колонка для {key} не найдена"
    return preceding[-1].group(1).strip()


def test_collect_sets_assignee_only_when_lock_present(repo):
    repo.test_case("TC-500", "Approved", lock="test-automator:2026-07-07T19:49:14Z")
    repo.test_case("TC-501", "Approved")  # lock отсутствует

    by_type = bv.collect()
    tc = {t["key"]: t for t in by_type["test-case"]}

    assert tc["TC-500"]["assignee"] == "test-automator"
    assert tc["TC-501"]["assignee"] is None


def test_static_render_shows_badge_only_on_locked_card(repo):
    """Статический режим (Save-BoardHtml -> render(by_type), live=False по умолчанию)."""
    repo.test_case("TC-502", "Approved", lock="test-automator:2026-07-07T19:49:14Z")
    repo.test_case("TC-503", "Approved")

    html_str = bv.render(bv.collect())

    locked = _card_chunk(html_str, "TC-502")
    unlocked = _card_chunk(html_str, "TC-503")

    assert 'class="agent"' in locked
    assert "test-automator" in locked
    assert 'class="agent"' not in unlocked


def test_live_render_shows_badge_too(repo):
    """Живой режим (board_server.py: render(collect(), live=True)) — тот же render()."""
    repo.test_case("TC-504", "Approved", lock="test-automator:2026-07-07T19:49:14Z")
    repo.test_case("TC-505", "Approved")

    html_str = bv.render(bv.collect(), live=True)

    locked = _card_chunk(html_str, "TC-504")
    unlocked = _card_chunk(html_str, "TC-505")

    assert 'class="agent"' in locked
    assert "test-automator" in locked
    assert 'class="agent"' not in unlocked


def test_manual_lock_without_colon_shows_whole_value_as_badge(repo):
    """Ручной лок человека ("wip", без agent:timestamp) — бейдж = значение целиком,
    так же, как assignee в board_sync (_assignee_for — общая логика, не дублируем)."""
    repo.bug("BUG-500", "Open", lock="wip")

    html_str = bv.render(bv.collect())

    chunk = _card_chunk(html_str, "BUG-500")
    assert 'class="agent"' in chunk
    assert "wip" in chunk


def test_empty_lock_renders_no_badge_for_run(repo):
    repo.run("RUN-500", "NeedsTriage")  # conftest.Repo.run всегда пишет lock: ""

    html_str = bv.render(bv.collect())

    chunk = _card_chunk(html_str, "RUN-500")
    assert 'class="agent"' not in chunk


# --- производная колонка "Awaiting Review" (F1) — общая с board_sync функция ---
#
# board_view импортирует _board_status_for из board_sync (не дублирует логику),
# поэтому оба рендера (static/live) должны согласованно показать новую колонку.

def test_approved_with_automated_by_in_awaiting_review_column_static(repo):
    """(5a) Approved + automated_by -> колонка "Awaiting Review" в статическом рендере."""
    repo.test_case("TC-510", "Approved", extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    html_str = bv.render(bv.collect())

    assert _column_for_card(html_str, "TC-510") == "Awaiting Review"


def test_approved_without_automated_by_in_approved_column(repo):
    """(5b) Approved без automated_by -> обычная колонка "Approved"."""
    repo.test_case("TC-511", "Approved")

    html_str = bv.render(bv.collect())

    assert _column_for_card(html_str, "TC-511") == "Approved"


def test_automated_status_in_automated_column_even_with_automated_by(repo):
    """(5c) status: Automated -> колонка "Automated" как раньше."""
    repo.test_case("TC-512", "Automated", extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    html_str = bv.render(bv.collect())

    assert _column_for_card(html_str, "TC-512") == "Automated"


def test_approved_with_automated_by_in_awaiting_review_column_live(repo):
    """Живой режим (board_server.py: render(collect(), live=True)) — тот же результат,
    потому что оба рендера используют board_sync._board_status_for."""
    repo.test_case("TC-513", "Approved", extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    html_str = bv.render(bv.collect(), live=True)

    assert _column_for_card(html_str, "TC-513") == "Awaiting Review"


def test_changes_requested_stays_in_awaiting_review_column(repo):
    repo.test_case("TC-514", "Approved",
                    extra='automated_by: "framework/tests/test_x.py::test_y"\nreview: changes_requested\n')

    html_str = bv.render(bv.collect())

    assert _column_for_card(html_str, "TC-514") == "Awaiting Review"
