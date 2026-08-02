"""Байтовые LF/CRLF-тесты писателей frontmatter в board_sync.py/board_inbound.py
(AT-BUG-038, по образцу test_gitlab_sync.py::test_writeback_is_byte_exact_insert_lf_and_crlf).

Класс 1 (EOL-перегон): фикстуры пишутся через write_bytes НАПРЯМУЮ (в обход
text-режима, который сам по себе на Windows транслирует '\\n' -> os.linesep при
записи и замаскировал бы баг) — только так тест реально ловит перегон. Проверяем,
что после записи файл остаётся ЧИСТО LF (или чисто CRLF кроме новых вставленных
строк, которые сами берут корректный eol) — никакого "перегона" всего файла.

Класс 2 (граница frontmatter): тело артефакта нарочно содержит строку, которая
синтаксически совпадает с полем frontmatter (`status: ...`/`priority: ...`/
`severity: ...`) — писатель обязан её НЕ трогать, редактируя только тело
frontmatter.

Тесты работают в изолированном tmp_path-репо (фикстура `repo` из conftest.py):
монкипатчат bs.REPO/bi.REPO на tmp_path, реальные test-cases/bugs НЕ трогают.
Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

import board_inbound as bi
import board_sync as bs


def _join(eol: str, lines: list[str]) -> bytes:
    return eol.join(lines).encode("utf-8")


# --- board_sync.approve_test_case -------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_approve_test_case_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: TC-900",
        "title: TC-900",
        "area: test",
        "priority: P1",
        "status: Review",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# TC-900",
        "",
        "Тело теста. Случайно похожая строка: status: Draft (не поле frontmatter).",
        "",
    ]
    p = repo.root / "test-cases" / "TC-900.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    ok, message = bs.approve_test_case("TC-900")
    assert ok, message

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bs.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "status: Approved" in m.group(1)
    # Класс 2: строка в ТЕЛЕ артефакта ("status: Draft" вне frontmatter) не тронута.
    body = text[m.end():]
    assert "status: Draft" in body
    # Класс 1: никакого перегона EOL всего файла — только сама изменённая строка
    # заменена (значение "Review"->"Approved" длиннее исходного; остальной файл
    # сохраняет исходный стиль EOL нетронутым).
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- board_sync.set_priority --------------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_set_priority_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: TC-901",
        "title: TC-901",
        "area: test",
        "priority: P1",
        "status: Approved",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# TC-901",
        "",
        "Тело. Похожая строка вне frontmatter: priority: P3.",
        "",
    ]
    p = repo.root / "test-cases" / "TC-901.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    ok, message = bs.set_priority("TC-901", "P2")
    assert ok, message

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bs.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "priority: P2" in m.group(1)
    body = text[m.end():]
    assert "priority: P3" in body  # тело не тронуто (класс 2)
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- board_sync.set_severity --------------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_set_severity_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: BUG-900",
        "title: BUG-900",
        "severity: major",
        "status: Open",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# BUG-900",
        "",
        "Тело. Похожая строка вне frontmatter: severity: blocker.",
        "",
    ]
    p = repo.root / "bugs" / "BUG-900.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    ok, message = bs.set_severity("BUG-900", "critical")
    assert ok, message

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bs.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "severity: critical" in m.group(1)
    body = text[m.end():]
    assert "severity: blocker" in body  # тело не тронуто (класс 2)
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- board_inbound.apply_status ----------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_apply_status_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: BUG-910",
        "title: BUG-910",
        "severity: major",
        "status: Open",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# BUG-910",
        "",
        "Тело. Похожая строка: status: Fixed (не поле frontmatter).",
        "",
    ]
    p = repo.root / "bugs" / "BUG-910.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    result = bi.apply_status(p, "Fixed", dry=False)
    assert "[OK]" in result

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bi.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "status: Fixed" in m.group(1)
    assert "status_since:" in m.group(1)
    body = text[m.end():]
    assert "status: Fixed (не поле frontmatter)" in body  # тело не тронуто
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0
        # вставленная строка status_since сама CRLF-терминирована (не перегон
        # на LF), т.е. между status: и status_since: — ровно один \r\n.
        assert "status: Fixed\r\nstatus_since:" in text


# --- board_inbound.apply_conflict ---------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_apply_conflict_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: BUG-920",
        "title: BUG-920",
        "severity: major",
        "status: Open",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# BUG-920",
        "",
        "тело",
        "",
    ]
    p = repo.root / "bugs" / "BUG-920.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    action = bi.Action("BUG-920", "conflict", "конфликт", src=p)
    result = bi.apply_conflict(action, "Fixed", "Blocked", dry=False)
    assert "[CONFLICT]" in result

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bi.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "status: Blocked" in m.group(1)
    assert "blocked_reason: product_decision" in m.group(1)
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- board_inbound.append_discussion ------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_append_discussion_new_content_matches_file_eol(repo, eol):
    lines = [
        "---",
        "id: BUG-930",
        "title: BUG-930",
        "severity: major",
        "status: Open",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# BUG-930",
        "",
        "тело",
    ]
    p = repo.root / "bugs" / "BUG-930.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    comment = bi.Comment(key="BUG-930", author="dev", created="2026-07-04T10:00:00Z",
                          body="Не воспроизводится.", cid="0001")
    result = bi.append_discussion(p, comment, dry=False)
    assert "[COMMENT]" in result

    after = p.read_bytes()
    text = after.decode("utf-8")
    assert "## Обсуждение" in text
    assert "**[dev @ 2026-07-04T10:00:00Z]** Не воспроизводится." in text
    m = bi.FRONTMATTER_RE.match(text)
    assert "awaiting: qa" in m.group(1)
    if eol == "\n":
        assert b"\r" not in after
    else:
        # Новый контент (пустые строки, заголовок раздела, реплика) — тоже
        # CRLF, не голый '\n' (проверяем отсутствие "перегона на LF").
        assert after.replace(b"\r\n", b"").count(b"\n") == 0
