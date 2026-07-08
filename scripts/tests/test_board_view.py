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

import board_view as bv


def _card_chunk(html_str: str, key: str) -> str:
    """Возвращает HTML-фрагмент одной карточки (между её `<div class="card"` и
    следующим), по data-key. Устойчиво к порядку карточек в колонке."""
    parts = html_str.split('<div class="card"')
    for p in parts:
        if f'data-key="{key}"' in p:
            return p
    raise AssertionError(f"карточка {key} не найдена в HTML")


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
