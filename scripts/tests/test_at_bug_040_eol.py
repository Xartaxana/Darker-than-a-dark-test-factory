"""AT-BUG-040: байтовые LF/CRLF-тесты + демонстрация data-loss для
scripts/sla_sweep.py::apply_pingpong_block и scripts/stale_locks.py::_clear_lock
(сиблинги класса AT-BUG-038, найденные критик-входом D1-верификации AT-BUG-038
целиком по оси scripts/ — писатели полей frontmatter артефактов, не вошедшие
в скоуп AT-BUG-038 своим DoD).

Класс 1 (EOL-перегон): фикстуры пишутся через write_bytes НАПРЯМУЮ (в обход
text-режима, который сам по себе на Windows транслирует '\\n' -> os.linesep при
записи и замаскировал бы баг) — только так тест реально ловит перегон.

Класс 2 (граница frontmatter) — для _clear_lock: тело артефакта нарочно
содержит строку, синтаксически похожую на поле lock, ВНЕ frontmatter —
писатель обязан её не трогать.

Data-loss регресс (bugs/AT-BUG-040.md, найдено критиком эмпирически на
pre-fix коде): протухший `lock:` без значения на своей строке + соседнее поле
frontmatter `extra_field: keepme` — жадный `(?m)^lock:\\s*.*$` без границы
frontmatter поглощал перенос строки и всю строку extra_field целиком через
`\\s*`-класс (переносы строк матчятся `\\s` в (?m)-режиме). Байт-в-байт
воспроизводит иллюстрацию из bugs/AT-BUG-040.md:
    до:    lock:\\n\\nextra_field: keepme\\n---
    после: lock: ""\\n---
На pre-fix коде тест ДОЛЖЕН падать (extra_field теряется, подтверждено перед
коммитом фикса); после фикса ([^\\r\\n]* вместо \\s*.*$, граница тела
frontmatter) — проходит (extra_field сохранена).

Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

import datetime

import pytest

import board_inbound as bi
import board_sync as bs
import sla_sweep as ss
import stale_locks as sl

NOW = datetime.datetime(2026, 7, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
STALE = "test-automator:2026-07-02T22:22:24Z"


def _join(eol: str, lines: list[str]) -> bytes:
    return eol.join(lines).encode("utf-8")


# --- sla_sweep.apply_pingpong_block -----------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_apply_pingpong_block_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: BUG-950",
        "title: BUG-950",
        "severity: major",
        "status: Reopened",
        'status_since: "2026-07-01T00:00:00Z"',
        "reopen_count: 2",
        'updated: "2026-07-01T00:00:00Z"',
        'lock: ""',
        "---",
        "",
        "# BUG-950",
        "",
        "Тело. Похожая строка вне frontmatter: status: Fixed (не поле frontmatter).",
        "",
    ]
    p = repo.root / "bugs" / "BUG-950.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    result = ss.apply_pingpong_block(p, NOW, dry=False)
    assert "[BLOCK]" in result

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bi.FRONTMATTER_RE.match(text)
    assert m is not None
    assert "status: Blocked" in m.group(1)
    assert "blocked_reason: product_decision" in m.group(1)
    body = text[m.end():]
    # класс 2 (унаследован из AT-BUG-038 через bi._rewrite_field/_set_field):
    # похожая строка вне frontmatter не тронута.
    assert "status: Fixed (не поле frontmatter)" in body
    # класс 1: никакого перегона EOL всего файла.
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- stale_locks._clear_lock --------------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_clear_lock_byte_exact_eol_preserved(repo, eol):
    lines = [
        "---",
        "id: TC-950",
        "title: TC-950",
        "area: test",
        "priority: P1",
        "status: Approved",
        f'lock: "{STALE}"',
        'updated: "2026-07-01T00:00:00Z"',
        "---",
        "",
        "# TC-950",
        "",
        'Тело. Похожая строка вне frontmatter: lock: "fake:2020-01-01T00:00:00Z".',
        "",
    ]
    p = repo.root / "test-cases" / "TC-950.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_join(eol, lines))

    cleared = sl._clear_lock(p, dry=False)
    assert cleared

    after = p.read_bytes()
    text = after.decode("utf-8")
    m = bs.FRONTMATTER_RE.match(text)
    assert m is not None
    assert 'lock: ""' in m.group(1)
    body = text[m.end():]
    # класс 2: похожая строка вне frontmatter не тронута.
    assert 'lock: "fake:2020-01-01T00:00:00Z"' in body
    # класс 1: никакого перегона EOL всего файла.
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


def test_clear_lock_data_loss_regression_at_bug_040(tmp_path):
    """Байт-в-байт воспроизводит демонстрированный критиком data-loss сценарий
    (bugs/AT-BUG-040.md): протухший lock без значения на своей строке frontmatter
    + СОСЕДНЕЕ поле extra_field — pre-fix regex `(?m)^lock:\\s*.*$` (без границы
    frontmatter) поглощал перенос строки и всю строку extra_field. Регресс:
    extra_field ДОЛЖНО остаться после снятия лока."""
    p = tmp_path / "BUG-999.md"
    p.write_bytes(
        b"---\nid: BUG-999\nlock:\n\nextra_field: keepme\n---\n\n# BUG-999\n\nbody\n"
    )

    cleared = sl._clear_lock(p, dry=False)
    assert cleared

    text = p.read_bytes().decode("utf-8")
    assert "extra_field: keepme" in text, (
        "AT-BUG-040 data-loss: соседнее поле extra_field уничтожено жадным "
        "regex без границы тела frontmatter")
    assert 'lock: ""' in text
