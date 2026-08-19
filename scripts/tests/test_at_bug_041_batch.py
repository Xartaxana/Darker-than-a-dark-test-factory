"""AT-BUG-041 остаток (батч 5 позиций, bugs/AT-BUG-041.md §«Известные
остатки (вне скоупа, по evidence рецидива)» (а)-(г) + loop_lock
decode-под-локом, главная позиция):

  1. loop_lock.acquire()/_write_loop_escalation — I/O-отказ записи
     эскалации (не-UTF8 escalations.md ⊂ ValueError на decode(), или
     PermissionError ⊂ OSError из os.replace) НИКОГДА не пробрасывается
     наружу acquire() (класс BL-4 — свежевзятый loop.lock иначе оставался
     бы сиротой; образец guard'а — heartbeat_wrap.
     _write_singleton_escalation, докстринг «Rework attempt 2»).
  2. build_watch._rewrite_field (п.а) — [ \\t]* вместо \\s*: поле с ПУСТЫМ
     значением не съедает следующую строку файла.
  3. sla_sweep.rewrite_registry (п.б) — добивка EOL перед append на файле
     БЕЗ хвостового перевода строки (строки не сливаются).
  4. Аппендеры без newline="" (п.в): build_watch._append_escalation/
     _append_orch_log, doctor._append_escalation, board_inbound.
     _append_escalation — не льют os.linesep (CRLF на Windows) в
     LF/CRLF-файл независимо от его фактического стиля.

Позиция 5 (п.г, build_watch._read_field: последний читатель через
read_text -> read_bytes/decode) поведенчески нейтральна (.strip() уже
нейтрализует CRLF/LF-разницу) — отдельного теста не требует, покрыта
существующим зелёным сьютом (см. bugs/AT-BUG-041.md критерий готовности).

Дозаказ (Lead, приёмка ядра пройдена, D-0043 — класс целиком):
  1. Ещё 4 аппендера без newline="" того же класса — factory_watchdog.
     _append_orchestrator_line, gitlab_sync._append_escalation, sla_sweep.
     _append_orch_log, stale_locks._append_orch_log.
  2. Добивка EOL перед append (п.3 главного отчёта) — теперь и в четырёх
     УЖЕ правленных аппендерах (build_watch x2/doctor/board_inbound), и в
     четырёх новых из п.1 выше.
  3. build_watch._repo_url (п.3 главного отчёта, аналог п.г) — read_text
     -> read_bytes/decode, унификация, yaml.safe_load не задета.

Запуск: python -m pytest scripts/tests -q
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

import board_inbound as bi
import build_watch as bw
import doctor as dr
import factory_watchdog as fwd
import gitlab_sync as gs
import loop_lock as ll
import sla_sweep as ss
import stale_locks as sl

NOW = datetime.datetime(2026, 7, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _join(eol: str, lines: list[str]) -> bytes:
    return eol.join(lines).encode("utf-8")


# =============================================================================
# 1. loop_lock: отказ записи эскалации не роняет acquire (главная позиция)
# =============================================================================

def _loop_paths(tmp_path):
    sla = tmp_path / "state" / "sla.yaml"
    sla.parent.mkdir(parents=True, exist_ok=True)
    sla.write_text("version: 1\nthresholds:\n  lock_stale: 2\n", encoding="utf-8")
    return {
        "lock_file": tmp_path / "state" / "loop.lock",
        "reaps_path": tmp_path / "state" / "loop-lock-reaps.json",
        "escalations_path": tmp_path / "state" / "escalations.md",
        "sla_path": sla,
    }


def _reach_reap_streak_two(p, tmp_path):
    """h0 -> h1 -> streak=1 (эскалации ещё нет); следующий вызов доводит
    streak до 2 = REAP_ESCALATION_THRESHOLD, триггерит запись эскалации."""
    t0 = NOW
    t1 = t0 + datetime.timedelta(hours=3)
    t2 = t1 + datetime.timedelta(hours=3)
    ll.acquire(holder="h0", now=t0, **p)
    code, lines = ll.acquire(holder="h1", now=t1, **p)
    assert not any(l.startswith("ESCALATION") for l in lines)  # streak=1 — рано
    return t2


def test_acquire_non_utf8_escalations_survives(tmp_path, capsys):
    p = _loop_paths(tmp_path)
    t2 = _reach_reap_streak_two(p, tmp_path)

    garbage = b"\xff\xfe\x00garbage-not-utf8-\x80\x81"
    p["escalations_path"].write_bytes(garbage)

    code, lines = ll.acquire(holder="h2", now=t2, **p)

    assert code == 0
    assert any(l.startswith("ACQUIRED:") and "h2" in l for l in lines)
    assert "ESCALATION write failed (см. вывод)" in lines
    assert not any(l.startswith("ESCALATION:") for l in lines)
    out = capsys.readouterr().out
    assert "ESCALATION write failed:" in out
    # лок реально взят несмотря на отказ записи эскалации (не сирота)
    payload = json.loads(p["lock_file"].read_text(encoding="utf-8"))
    assert payload["holder"] == "h2"
    # файл эскалаций НЕ перезаписан мусором — байты те же, что были ДО попытки
    assert p["escalations_path"].read_bytes() == garbage


def test_acquire_escalation_permission_error_survives(tmp_path, monkeypatch, capsys):
    p = _loop_paths(tmp_path)
    t2 = _reach_reap_streak_two(p, tmp_path)

    real_replace = ll.os.replace
    esc_path = p["escalations_path"]

    def fake_replace(src, dst):
        if Path(dst) == esc_path:
            raise PermissionError(13, "Permission denied", str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(ll.os, "replace", fake_replace, raising=True)

    code, lines = ll.acquire(holder="h2", now=t2, **p)

    assert code == 0
    assert any(l.startswith("ACQUIRED:") and "h2" in l for l in lines)
    assert "ESCALATION write failed (см. вывод)" in lines
    assert not any(l.startswith("ESCALATION:") for l in lines)
    out = capsys.readouterr().out
    assert "ESCALATION write failed:" in out
    payload = json.loads(p["lock_file"].read_text(encoding="utf-8"))
    assert payload["holder"] == "h2"
    # эскалации не появилось — ни LOOP-строки, ни файла с мусорным .tmp-содержимым
    assert not esc_path.exists() or "LOOP-" not in esc_path.read_text(encoding="utf-8")


def test_acquire_escalation_write_ok_is_unaffected_by_guard(tmp_path):
    """Контроль: штатный успешный путь (без отказа) не сломан оборачиванием
    в try/except — тот же сценарий, что test_two_reaps_in_a_row_escalate_
    third_no_duplicate в test_loop_lock.py, продублирован здесь узко под
    защиту границы этого фикса."""
    p = _loop_paths(tmp_path)
    t2 = _reach_reap_streak_two(p, tmp_path)

    code, lines = ll.acquire(holder="h2", now=t2, **p)

    assert code == 0
    assert any(l.startswith("ESCALATION:") and "LOOP-1" in l for l in lines)
    assert "2 проход" in p["escalations_path"].read_text(encoding="utf-8")


# =============================================================================
# 2. build_watch._rewrite_field (п.а): [ \t]* не пересекает перевод строки
# =============================================================================

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_field_empty_value_keeps_next_line(eol):
    text = eol.join(["coalesced_commits:", "version_code: 11", ""])
    result = bw._rewrite_field(text, "coalesced_commits", "[abc1234]")
    assert "coalesced_commits: [abc1234]" in result
    assert "version_code: 11" in result   # не съедено пустым значением поля


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_field_empty_value_border_no_blank_line_between(eol):
    """Граница ЗА пределами предыдущего теста: следующая строка начинается
    СРАЗУ (без пустой строки-разделителя) — старый жадный '\\s*' пересекал
    бы ровно этот перевод строки и продолжал есть дальше в глубину файла."""
    text = eol.join(["field_a:", "field_b: keep-me", "field_c: also-keep", ""])
    result = bw._rewrite_field(text, "field_a", "newvalue")
    assert "field_a: newvalue" in result
    assert "field_b: keep-me" in result
    assert "field_c: also-keep" in result


# =============================================================================
# 3. sla_sweep.rewrite_registry (п.б): добивка EOL перед append
# =============================================================================

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_rewrite_registry_no_trailing_eol_before_append(repo, eol):
    header = "# Эскалации фабрики"
    blank = ""
    kept_line = ("- [2026-07-01T00:00:00Z] **BUG-904** [sla:blocked_any] — "
                 "в Blocked | нужно: разобрать причину и вывести из Blocked")
    content = _join(eol, [header, blank, kept_line])   # БЕЗ хвостового EOL
    esc = repo.root / "state" / "escalations.md"
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    wanted = {
        ("BUG-904", "blocked_any"): "неважно — уже kept",
        ("BUG-905", "blocked_any"): "новая эскалация",
    }
    added, removed = ss.rewrite_registry(wanted, NOW, dry=False)

    assert added == ["BUG-905(blocked_any)"] and removed == []
    after = esc.read_bytes()
    assert after.startswith(content)                  # старый хвост не перегнан
    tail = after[len(content):]
    assert tail.startswith(eol.encode("utf-8"))        # добивка перед новой строкой
    assert b"BUG-905" in tail
    # строки не слиплись (никакой конкатенации без разделителя)
    assert (kept_line + "- [").encode("utf-8") not in after
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# =============================================================================
# 4. Аппендеры без newline="" (п.в) — не льют os.linesep поверх стиля файла
# =============================================================================

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_build_watch_append_escalation_matches_file_eol(repo, eol):
    esc = repo.root / "state" / "escalations.md"
    header = "# Эскалации фабрики"
    blank = ""
    existing = "- [2026-07-01T00:00:00Z] **BUILD** — старая запись"
    content = _join(eol, [header, blank, existing, ""])
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    bw._append_escalation("новая причина")

    after = esc.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"BUILD" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_build_watch_append_orch_log_matches_file_eol(repo, eol):
    log = repo.root / "state" / "orchestrator-log.md"
    header = "# Журнал оркестратора"
    row = "| Время | Правило | Агент | Артефакт | Исход |"
    sep = "|---|---|---|---|---|"
    content = _join(eol, [header, "", row, sep, ""])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(content)

    bw._append_orch_log("OK: тест")

    after = log.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"build_watch" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_doctor_append_escalation_matches_file_eol(repo, monkeypatch, eol):
    esc = repo.root / "state" / "escalations.md"
    monkeypatch.setattr(dr, "ESCALATIONS_PATH", esc, raising=True)
    header = "# Эскалации фабрики"
    blank = ""
    existing = "- [2026-07-01T00:00:00Z] **DOCTOR** — старая запись"
    content = _join(eol, [header, blank, existing, ""])
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    dr._append_escalation("новая причина doctor")

    after = esc.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"DOCTOR" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_board_inbound_append_escalation_matches_file_eol(repo, eol):
    esc = repo.root / "state" / "escalations.md"
    header = "# Эскалации фабрики"
    blank = ""
    existing = "- [2026-07-01T00:00:00Z] **BUG-1** — старая запись"
    content = _join(eol, [header, blank, existing, ""])
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    bi._append_escalation("BUG-2", "новая причина board_inbound")

    after = esc.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"BUG-2" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# =============================================================================
# Дозаказ п.1: ещё 4 аппендера того же класса (не в исходной спеке)
# =============================================================================

@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_factory_watchdog_append_orchestrator_line_matches_file_eol(tmp_path, eol):
    log = tmp_path / "orchestrator-log.md"
    header = "# Журнал оркестратора"
    row = "| Время | Правило | Агент | Артефакт | Исход |"
    sep = "|---|---|---|---|---|"
    content = _join(eol, [header, "", row, sep, ""])
    log.write_bytes(content)

    fwd._append_orchestrator_line(log, "state/something.md", "OK: тест", NOW)

    after = log.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_gitlab_sync_append_escalation_matches_file_eol(tmp_path, monkeypatch, eol):
    esc = tmp_path / "state" / "escalations.md"
    monkeypatch.setattr(gs, "ESCALATIONS_PATH", esc, raising=True)
    header = "# Эскалации фабрики"
    blank = ""
    existing = "- [2026-07-01T00:00:00Z] **QAREADY-1** — старая запись"
    content = _join(eol, [header, blank, existing, ""])
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    gs._append_escalation("QAREADY-2", "новая причина gitlab_sync")

    after = esc.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"QAREADY-2" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_sla_sweep_append_orch_log_matches_file_eol(repo, eol):
    log = repo.root / "state" / "orchestrator-log.md"
    header = "# Журнал оркестратора"
    row = "| Время | Правило | Агент | Артефакт | Исход |"
    sep = "|---|---|---|---|---|"
    content = _join(eol, [header, "", row, sep, ""])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(content)

    ss._append_orch_log("OK: тест", NOW, dry=False)

    after = log.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"sla_sweep" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_stale_locks_append_orch_log_matches_file_eol(repo, eol):
    log = repo.root / "state" / "orchestrator-log.md"
    header = "# Журнал оркестратора"
    row = "| Время | Правило | Агент | Артефакт | Исход |"
    sep = "|---|---|---|---|---|"
    content = _join(eol, [header, "", row, sep, ""])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(content)

    sl._append_orch_log("bugs/BUG-1.md", "OK: тест", dry=False)

    after = log.read_bytes()
    assert after.startswith(content)
    tail = after[len(content):]
    assert b"stale_locks" in tail
    assert tail.endswith(eol.encode("utf-8"))
    if eol == "\n":
        assert b"\r" not in after
    else:
        assert after.replace(b"\r\n", b"").count(b"\n") == 0


# =============================================================================
# Дозаказ п.2: граница «файл без хвостового EOL» — по представителю на
# каждую из двух групп (уже правленные позицией 4 + новые из п.1 выше);
# не все 8 аппендеров — обе ветки (группы) покрыты.
# =============================================================================

def test_build_watch_append_escalation_no_trailing_eol_pads(repo):
    """Представитель группы «уже правлены позицией 4» (build_watch)."""
    esc = repo.root / "state" / "escalations.md"
    header = "# Эскалации фабрики"
    blank = ""
    existing = "- [2026-07-01T00:00:00Z] **BUILD** — старая запись"
    content = _join("\n", [header, blank, existing])   # БЕЗ хвостового EOL
    esc.parent.mkdir(parents=True, exist_ok=True)
    esc.write_bytes(content)

    bw._append_escalation("граница без хвостового EOL")

    after = esc.read_bytes()
    assert after[:len(content)] == content
    assert after[len(content):len(content) + 1] == b"\n"   # добивка перед новой строкой
    assert b"BUILD" in after[len(content):]


def test_factory_watchdog_append_orchestrator_line_no_trailing_eol_pads(tmp_path):
    """Представитель группы «новые из дозаказа п.1» (factory_watchdog)."""
    log = tmp_path / "orchestrator-log.md"
    header = "# Журнал оркестратора"
    row = "| Время | Правило | Агент | Артефакт | Исход |"
    content = _join("\n", [header, "", row])   # БЕЗ хвостового EOL
    log.write_bytes(content)

    fwd._append_orchestrator_line(log, "state/something.md", "OK: граница", NOW)

    after = log.read_bytes()
    assert after[:len(content)] == content
    assert after[len(content):len(content) + 1] == b"\n"   # добивка перед новой строкой
    assert b"OK" in after[len(content):]
