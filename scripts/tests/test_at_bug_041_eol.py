"""AT-BUG-041: байтовые LF/CRLF-тесты для сиблингов класса 1 (EOL-перегон),
не вошедших в скоуп AT-BUG-038/040 своей frontmatter-границей:

  - build_watch.py::update_aut          (state/app-under-test.yaml, живой)
  - sla_sweep.py::rewrite_registry      (state/escalations.md, спящий)
  - loop_lock.py::_write_loop_escalation (state/escalations.md через
    _atomic_write_text, тот же механизм — read/write, не frontmatter)

Фикстуры пишутся через write_bytes НАПРЯМУЮ (в обход text-режима, который
сам по себе на Windows транслирует '\\n' -> os.linesep при записи и
замаскировал бы баг) — только так тест реально ловит перегон, тем же
приёмом, что scripts/tests/test_at_bug_040_eol.py.

Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

import datetime

import pytest

import build_watch as bw
import loop_lock as ll
import sla_sweep as ss

NOW = datetime.datetime(2026, 7, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _join(eol: str, lines: list[str]) -> bytes:
    return eol.join(lines).encode("utf-8")


# --- build_watch.update_aut --------------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_update_aut_byte_exact_eol_preserved(repo, eol):
    tip = "c" * 40
    lines = [
        "app: ao3-wrapper",
        "repo: https://gitlab.com/Xartaxana1/ao3-wrapper",
        f"source_commit: {'a' * 40}   # старая сборка",
        'version_name: "1.10"',
        "version_code: 11",
        "build_type: debug",
        'apk_sha256: "deadbeef"',
        'built_at: "2026-07-02T02:39:46"',
        "smoke_status: passed     # not_run | passed | failed",
        "regression_status: passed",
        "",
    ]
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_bytes(_join(eol, lines))

    bw.update_aut(tip, [], "newsha256")

    after = aut.read_bytes()
    text = after.decode("utf-8")
    assert f"source_commit: {tip}" in text
    # хвостовой комментарий на правленой строке пережил правку (граница поля)
    assert "# старая сборка" in text
    assert "# not_run | passed | failed" in text
    assert "smoke_status: not_run" in text
    assert "regression_status: not_run" in text
    assert '"newsha256"' in text
    # класс 1: никакого перегона EOL всего файла.
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_update_aut_field_without_comment_keeps_own_eol(repo, eol):
    """Граница регресса build_watch._rewrite_field: поле БЕЗ хвостового
    комментария теряло свой '\\r' в жадном [^#\\n]*.*$ (доказано эмпирически
    до фикса: 'version_code: 11\\r\\n' -> 'version_code: 99\\n'). Проверяем
    именно строку без комментария, а не только строку с ним."""
    tip = "d" * 40
    lines = [
        "app: ao3-wrapper",
        f"source_commit: {'a' * 40}",
        "version_code: 11",
        'apk_sha256: "deadbeef"',
        'built_at: "2026-07-02T02:39:46"',
        "smoke_status: passed",
        "regression_status: passed",
        "",
    ]
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.parent.mkdir(parents=True, exist_ok=True)
    aut.write_bytes(_join(eol, lines))

    bw.update_aut(tip, [], "newsha256")

    after = aut.read_bytes()
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- sla_sweep.rewrite_registry ----------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_registry_kept_only_pass_is_byte_identical(repo, eol):
    """Ничего не меняется (kept-only) -> ранний return без записи вовсе;
    но даже если бы записал — байты обязаны остаться теми же."""
    header = "# Эскалации фабрики"
    blank = ""
    line = ("- [2026-07-01T00:00:00Z] **BUG-900** [sla:blocked_any] — "
            "в Blocked | нужно: разобрать причину и вывести из Blocked")
    content = _join(eol, [header, blank, line, blank])
    esc = repo.root / "state" / "escalations.md"
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    wanted = {("BUG-900", "blocked_any"): "неважно — строка kept, текст не переписывается"}
    added, removed = ss.rewrite_registry(wanted, NOW, dry=False)

    assert added == [] and removed == []
    assert esc.read_bytes() == content


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_registry_removal_preserves_untouched_lines_eol(repo, eol):
    """Причина устранена (removed) -> файл переписывается; строки, не
    относящиеся к снятой, обязаны остаться байт-в-байт (EOL включительно)."""
    header = "# Эскалации фабрики"
    blank = ""
    kept_line = ("- [2026-07-01T00:00:00Z] **BUG-901** [sla:blocked_any] — "
                 "в Blocked | нужно: разобрать причину и вывести из Blocked")
    removed_line = ("- [2026-07-01T00:00:00Z] **BUG-900** [sla:blocked_any] — "
                     "в Blocked | нужно: разобрать причину и вывести из Blocked")
    content = _join(eol, [header, blank, kept_line, removed_line, blank])
    esc = repo.root / "state" / "escalations.md"
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    # BUG-900 больше не в wanted -> снимается; BUG-901 остаётся.
    wanted = {("BUG-901", "blocked_any"): "неважно"}
    added, removed = ss.rewrite_registry(wanted, NOW, dry=False)

    assert added == [] and removed == ["BUG-900(blocked_any)"]
    after = esc.read_bytes()
    assert b"BUG-900" not in after
    assert b"BUG-901" in after
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0
    # заголовок и kept-строка byte-в-byte как были (включая её собственный
    # EOL) — снятая строка вырезана целиком, ничего сверх неё не тронуто.
    expected = _join(eol, [header, blank, kept_line, ""])
    assert after == expected


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_registry_added_line_matches_file_eol(repo, eol):
    """attempt 2 (критик-вход приёмки): НОВАЯ строка (и догенерированный
    header, здесь не задействован — файл уже с header) обязана брать
    EOL-стиль САМОГО файла, не хардкод '\\n' — иначе первая же post-fix
    эскалация в живом (сегодня целиком CRLF) state/escalations.md заводит
    перманентно смешанный EOL. Старое содержимое остаётся байт-в-байт."""
    header = "# Эскалации фабрики"
    blank = ""
    kept_line = ("- [2026-07-01T00:00:00Z] **BUG-902** [sla:blocked_any] — "
                 "в Blocked | нужно: разобрать причину и вывести из Blocked")
    content = _join(eol, [header, blank, kept_line, ""])
    esc = repo.root / "state" / "escalations.md"
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    wanted = {
        ("BUG-902", "blocked_any"): "неважно — уже kept",
        ("BUG-903", "blocked_any"): "новая эскалация",
    }
    added, removed = ss.rewrite_registry(wanted, NOW, dry=False)

    assert added == ["BUG-903(blocked_any)"] and removed == []
    after = esc.read_bytes()
    assert after.startswith(content)              # старое содержимое нетронуто
    tail = after[len(content):]
    assert b"BUG-903" in tail
    assert tail.endswith(eol.encode("utf-8"))      # новая строка — в стиле файла
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# --- loop_lock._write_loop_escalation ----------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_write_loop_escalation_update_existing_preserves_eol(tmp_path, eol):
    """Обновление УЖЕ существующей LOOP-строки на месте (m matched) — граница
    регресса LOOP_LINE_RE: жадный '.*$' поглощал завершающий '\\r' строки в
    CRLF-файле (тот же класс, что _LOCK_FIELD_RE/_rewrite_field)."""
    header = "# Эскалации фабрики"
    blank = ""
    other = ("- [2026-07-01T00:00:00Z] **BUG-777** [sla:blocked_any] — "
             "не трогать, чужая строка")
    loop_line = ("- [2026-07-05T00:00:00Z] **LOOP-1** [loop:reaped] — "
                 "2 проходов подряд умерли с локом — фабрика систематически "
                 "падает, нужен разбор человеком")
    content = _join(eol, [header, blank, other, loop_line, blank])
    esc = tmp_path / "escalations.md"
    esc.write_bytes(content)

    key = ll._write_loop_escalation(esc, 3, NOW)

    assert key == "LOOP-1"
    after = esc.read_bytes()
    assert b"3 \xd0\xbf\xd1\x80\xd0\xbe\xd1\x85\xd0\xbe\xd0\xb4" in after  # "3 проход"
    assert after.count(b"LOOP-1") == 1
    assert b"BUG-777" in after
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0
    # строка перед LOOP-1 (other) byte-в-byte нетронута, включая её EOL.
    prefix = _join(eol, [header, blank, other, ""])
    assert after.startswith(prefix)
    # хвост после LOOP-1 (исходная trailing-blank строка -> её EOL) тоже
    # сохранён — файл заканчивается тем же EOL-символом, что и до правки.
    assert after.endswith(eol.encode("utf-8"))


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_write_loop_escalation_append_new_preserves_existing_eol(tmp_path, eol):
    """Первая эскалация (LOOP-строки ещё нет, файл заканчивается EOL) —
    существующий хвост файла обязан остаться нетронутым байт-в-байт, а
    НОВАЯ строка обязана взять EOL-стиль самого файла (attempt 2, критик-
    вход приёмки), не хардкод '\\n'."""
    header = "# Эскалации фабрики"
    blank = ""
    other = ("- [2026-07-01T00:00:00Z] **BUG-778** [sla:blocked_any] — "
             "не трогать, чужая строка")
    content = _join(eol, [header, blank, other, blank])
    esc = tmp_path / "escalations.md"
    esc.write_bytes(content)

    key = ll._write_loop_escalation(esc, 2, NOW)

    assert key == "LOOP-1"
    after = esc.read_bytes()
    assert after.startswith(content)     # старый хвост НЕ перегнан
    tail = after[len(content):]
    assert b"LOOP-1" in tail
    assert tail.endswith(eol.encode("utf-8"))      # новая строка — в стиле файла
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_write_loop_escalation_append_new_no_trailing_eol_uses_file_style(tmp_path, eol):
    """Граница за пределами предыдущего теста: файл БЕЗ хвостового EOL перед
    точкой вставки (`elif not text.endswith("\\n"): text += eol` — раньше
    хардкод '\\n'). И добивка перед новой строкой, и сама новая строка
    обязаны взять EOL-стиль файла."""
    header = "# Эскалации фабрики"
    blank = ""
    other = ("- [2026-07-01T00:00:00Z] **BUG-779** [sla:blocked_any] — "
             "не трогать, чужая строка")
    content = _join(eol, [header, blank, other])   # БЕЗ трейлинг-EOL в конце
    esc = tmp_path / "escalations.md"
    esc.write_bytes(content)

    key = ll._write_loop_escalation(esc, 2, NOW)

    assert key == "LOOP-1"
    after = esc.read_bytes()
    assert after.startswith(content)     # старый хвост НЕ перегнан
    tail = after[len(content):]
    assert b"LOOP-1" in tail
    # добивка перед новой строкой — тоже в стиле файла (не '\n' на CRLF-файле)
    assert tail.startswith(eol.encode("utf-8"))
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0
