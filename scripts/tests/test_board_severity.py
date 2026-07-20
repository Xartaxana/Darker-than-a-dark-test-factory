"""Юнит-тесты канала severity для багов на живой борде — по образцу priority для
test-case (board_sync.set_priority не имел юнитов до этой правки; заводим файл
по конвенции каталога, как test_board_sync.py/test_board_view.py).

Покрывает:
- board_sync.set_severity: happy-path, границы enum'а (все 4 валидных значения +
  адверсариальная батарея невалидных), смешение типов (test-case/несуществующий
  ключ), регистронезависимость входа.
- board_view.collect()/render(): сырая severity в карточке бага, live-дропдаун
  вместо статичного бейджа только для bug (не для test-case/run), P-класс цвета
  переиспользован из уже вычисленного производного приоритета.

Тесты работают в tmp_path-репо (фикстура `repo` из conftest.py), реальные
bugs/test-cases не затрагиваются. Запуск:
    python -m pytest scripts/tests -q
"""
from __future__ import annotations

import re

import board_sync as bs
import board_view as bv


def _bug_text(repo, key: str) -> str:
    return repo.read_artifact(f"bugs/{key}.md")


# --- board_sync.set_severity: happy path -------------------------------------

def test_happy_path_changes_severity_and_updated(repo):
    repo.bug("BUG-600", "Open")  # conftest.Repo.bug: severity: major, updated: 2026-07-01

    ok, message = bs.set_severity("BUG-600", "critical")

    assert ok, message
    text = _bug_text(repo, "BUG-600")
    assert re.search(r"(?m)^severity:\s*critical\s*$", text)
    assert "2026-07-01T00:00:00Z" not in text  # updated-штамп переписан
    assert "BUG-600" in message and "critical" in message


# --- граница enum'а: все 4 валидных значения проходят -------------------------

def test_all_four_valid_severities_accepted(repo):
    for i, sev in enumerate(("blocker", "critical", "major", "minor")):
        key = f"BUG-61{i}"
        repo.bug(key, "Open")
        ok, message = bs.set_severity(key, sev)
        assert ok, f"{sev}: {message}"
        assert re.search(rf"(?m)^severity:\s*{sev}\s*$", _bug_text(repo, key))


# --- за границей: адверсариальная батарея невалидных значений -----------------

def test_trivial_is_rejected_not_in_enum(repo):
    """schemas/bug.schema.yaml enum БЕЗ trivial (известная мёртвая ветка SEVERITY_TO_PRIORITY,
    не трогаем её, но set_severity обязан отказать)."""
    repo.bug("BUG-620", "Open")
    ok, message = bs.set_severity("BUG-620", "trivial")
    assert not ok
    assert "недопустимая" in message
    assert re.search(r"(?m)^severity:\s*major\s*$", _bug_text(repo, "BUG-620"))  # не записано


def test_empty_string_rejected(repo):
    repo.bug("BUG-621", "Open")
    ok, message = bs.set_severity("BUG-621", "")
    assert not ok
    assert re.search(r"(?m)^severity:\s*major\s*$", _bug_text(repo, "BUG-621"))


def test_garbage_rejected(repo):
    repo.bug("BUG-622", "Open")
    ok, message = bs.set_severity("BUG-622", "asdfghjkl123")
    assert not ok
    assert re.search(r"(?m)^severity:\s*major\s*$", _bug_text(repo, "BUG-622"))


def test_cyrillic_rejected(repo):
    repo.bug("BUG-623", "Open")
    ok, message = bs.set_severity("BUG-623", "блокер")
    assert not ok
    assert re.search(r"(?m)^severity:\s*major\s*$", _bug_text(repo, "BUG-623"))


def test_very_long_string_rejected(repo):
    repo.bug("BUG-624", "Open")
    ok, message = bs.set_severity("BUG-624", "a" * 10000)
    assert not ok
    assert re.search(r"(?m)^severity:\s*major\s*$", _bug_text(repo, "BUG-624"))


# --- регистр --------------------------------------------------------------

def test_uppercase_input_normalized(repo):
    repo.bug("BUG-630", "Open")
    ok, message = bs.set_severity("BUG-630", "BLOCKER")
    assert ok, message
    assert re.search(r"(?m)^severity:\s*blocker\s*$", _bug_text(repo, "BUG-630"))


def test_mixed_case_input_normalized(repo):
    repo.bug("BUG-631", "Open")
    ok, message = bs.set_severity("BUG-631", "CriTicaL")
    assert ok, message
    assert re.search(r"(?m)^severity:\s*critical\s*$", _bug_text(repo, "BUG-631"))


# --- смешение типов ---------------------------------------------------------

def test_test_case_key_rejected_severity_not_editable(repo):
    repo.test_case("TC-600", "Approved")
    ok, message = bs.set_severity("TC-600", "critical")
    assert not ok
    assert "severity нет" in message
    assert "priority" in message


def test_nonexistent_key_rejected(repo):
    ok, message = bs.set_severity("BUG-999999", "critical")
    assert not ok
    assert "не найден" in message


# --- board_view: сырая severity в карточке ------------------------------------

def test_collect_carries_raw_severity_for_bug(repo):
    repo.bug("BUG-640", "Open")  # severity: major (conftest default)
    by_type = bv.collect()
    bug = next(t for t in by_type["bug"] if t["key"] == "BUG-640")
    assert bug["severity"] == "major"


def test_collect_severity_none_for_test_case(repo):
    repo.test_case("TC-601", "Approved")
    by_type = bv.collect()
    tc = next(t for t in by_type["test-case"] if t["key"] == "TC-601")
    assert tc["severity"] is None


# --- board_view: live-дропдаун только для bug, не для test-case/run ----------

def _card_chunk(html_str: str, key: str) -> str:
    parts = html_str.split('<div class="card"')
    for p in parts:
        if f'data-key="{key}"' in p:
            return p
    raise AssertionError(f"карточка {key} не найдена в HTML")


def test_live_bug_renders_severity_select(repo):
    repo.bug("BUG-650", "Open")  # severity: major -> производный приоритет p1
    html_str = bv.render(bv.collect(), live=True)
    chunk = _card_chunk(html_str, "BUG-650")
    assert "<select" in chunk
    assert 'onchange="setSeverity(this)"' in chunk
    assert 'data-key="BUG-650"' in chunk
    # цвет — переиспользованный P-класс приоритета (major -> p1 -> "pP1"), без новой CSS
    assert 'class="pri pri-select pP1"' in chunk
    # текущее значение выбрано
    assert re.search(r'<option value="major" selected>major</option>', chunk)


def test_live_bug_select_has_all_four_options(repo):
    repo.bug("BUG-651", "Open")
    html_str = bv.render(bv.collect(), live=True)
    chunk = _card_chunk(html_str, "BUG-651")
    for sev in ("blocker", "critical", "major", "minor"):
        assert f'value="{sev}"' in chunk


def test_static_bug_render_shows_badge_not_select(repo):
    """Не-live рендер бага — как раньше: статичный бейдж производного приоритета."""
    repo.bug("BUG-652", "Open")
    html_str = bv.render(bv.collect(), live=False)
    chunk = _card_chunk(html_str, "BUG-652")
    assert "<select" not in chunk
    assert 'class="pri p' in chunk


def test_live_test_case_still_shows_priority_select_not_severity(repo):
    """test-case канал priority не задет — по-прежнему свой select, не /severity."""
    repo.test_case("TC-602", "Approved")
    html_str = bv.render(bv.collect(), live=True)
    chunk = _card_chunk(html_str, "TC-602")
    assert "<select" in chunk
    assert 'onchange="setPriority(this)"' in chunk
    # _card_chunk режет до конца документа (включая общий <script>, где всегда
    # определена функция setSeverity) — проверяем отсутствие ВЫЗОВА на этой
    # карточке, не отсутствие имени функции во всём хвосте документа.
    assert 'onchange="setSeverity(this)"' not in chunk


def test_live_run_shows_no_select_at_all(repo):
    repo.run("RUN-600", "NeedsTriage")
    html_str = bv.render(bv.collect(), live=True)
    chunk = _card_chunk(html_str, "RUN-600")
    assert "<select" not in chunk


def test_blocker_and_critical_both_map_to_p0_color(repo):
    repo.bug("BUG-660", "Open", extra="")  # severity: major по умолчанию, переопределим ниже
    bs.set_severity("BUG-660", "blocker")
    repo.bug("BUG-661", "Open")
    bs.set_severity("BUG-661", "critical")

    html_str = bv.render(bv.collect(), live=True)
    chunk_blocker = _card_chunk(html_str, "BUG-660")
    chunk_critical = _card_chunk(html_str, "BUG-661")
    assert 'class="pri pri-select pP0"' in chunk_blocker
    assert 'class="pri pri-select pP0"' in chunk_critical


def test_minor_maps_to_p2_color(repo):
    repo.bug("BUG-662", "Open")
    bs.set_severity("BUG-662", "minor")
    html_str = bv.render(bv.collect(), live=True)
    chunk = _card_chunk(html_str, "BUG-662")
    assert 'class="pri pri-select pP2"' in chunk
