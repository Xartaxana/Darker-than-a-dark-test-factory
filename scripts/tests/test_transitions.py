"""Self-tests матрицы переходов (C3+F3, docs/09 Этап 2).

Матрица schemas/transitions.yaml — исполняемый контракт: эти тесты сверяют
её внутреннюю целостность, паритет с board_inbound-whitelist (который теперь
из неё выводится), согласованность с enum'ами schemas/*.schema.yaml и то, что
реализация эффектов в скриптах совпадает с декларацией.
"""
from __future__ import annotations

from pathlib import Path

import yaml

import board_inbound as bi
import transitions as tr

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


# --- целостность самой матрицы --------------------------------------------

def test_matrix_is_valid():
    assert tr.validate() == []


def test_statuses_match_schema_enums():
    """Статусные машины и enum'ы схем frontmatter (G3) не должны разъезжаться."""
    for itype in ("bug", "test-case", "run"):
        schema = yaml.safe_load((SCHEMAS / f"{itype}.schema.yaml").read_text(encoding="utf-8"))
        enum = set(schema["fields"]["status"]["enum"])
        assert enum == set(tr.statuses(itype)), f"{itype}: схема {enum} != матрица"


# --- паритет board-whitelist (регрессия на переезд с литерала) --------------

LEGACY_WHITELIST = {
    "bug": {
        "Open":     {"Fixed", "Rejected", "Intended", "Blocked"},
        "Reopened": {"Fixed", "Rejected", "Intended", "Blocked"},
        "*":        {"Open"},
    },
    "test-case": {
        "Draft":  {"Approved"},
        "Review": {"Approved"},
        "*":      {"Review"},
    },
    "run": {},
}


def test_board_whitelist_parity_with_legacy_literal():
    assert tr.board_whitelist() == LEGACY_WHITELIST
    assert bi.WHITELIST == LEGACY_WHITELIST      # board_inbound берёт из матрицы


def test_run_has_no_board_transitions():
    assert tr.board_whitelist()["run"] == {}


# --- границы ответственности акторов ---------------------------------------

def test_only_human_marks_fixed():
    assert tr.is_allowed("bug", "Open", "Fixed", "human")
    for actor in ("fix-verifier", "bug-reporter", "test-maintainer", "qa-loop"):
        assert not tr.is_allowed("bug", "Open", "Fixed", actor), actor


def test_fix_verifier_owns_verification():
    assert tr.is_allowed("bug", "Fixed", "Verified", "fix-verifier")
    assert tr.is_allowed("bug", "Fixed", "Reopened", "fix-verifier")
    assert not tr.is_allowed("bug", "Fixed", "Verified", "human")     # мимо верификации нельзя
    assert not tr.is_allowed("bug", "Fixed", "Verified", "bug-reporter")


def test_reopen_from_anywhere_only_human():
    assert tr.is_allowed("bug", "Verified", "Open", "human")
    assert tr.is_allowed("bug", "Rejected", "Open", "human")
    assert not tr.is_allowed("bug", "Verified", "Open", "fix-verifier")


def test_illegal_shortcuts_rejected():
    assert not tr.is_allowed("bug", "Open", "Verified", "fix-verifier")          # мимо Fixed
    assert not tr.is_allowed("run", "NeedsTriage", "Closed", "failure-analyst")  # мимо триажа
    assert not tr.is_allowed("test-case", "Draft", "Automated", "test-automator")  # мимо Approved
    assert not tr.is_allowed("bug", "Open", "Open", "human")                     # петля


def test_unknown_actor_denied_even_where_factory_allowed():
    assert tr.is_allowed("bug", "Open", "Blocked", "sla_sweep")     # factory-группа
    assert not tr.is_allowed("bug", "Open", "Blocked", "mallory")   # чужак — нет


def test_pingpong_sources_match_sla_sweep():
    """D8/D4: блокировать можно из Open/Reopened/Rejected, но НЕ из Fixed."""
    for frm in ("Open", "Reopened", "Rejected"):
        assert tr.is_allowed("bug", frm, "Blocked", "sla_sweep"), frm
    assert not tr.is_allowed("bug", "Fixed", "Blocked", "sla_sweep")
    assert not tr.is_allowed("bug", "Verified", "Blocked", "sla_sweep")


# --- эффекты: декларация ↔ реализация ---------------------------------------

def test_always_effects_on_every_transition():
    assert {"status_since", "updated"} <= tr.effects_for("bug", "Open", "Fixed")
    assert {"status_since", "updated"} <= tr.effects_for("run", "NeedsTriage", "Triaged")


def test_blocked_always_declares_escalation():
    for itype, frm in (("bug", "Open"), ("bug", "Rejected"),
                       ("test-case", "Approved"), ("run", "Triaged")):
        assert "escalation" in tr.effects_for(itype, frm, "Blocked"), (itype, frm)


def test_reopen_effect_declared_and_implemented(repo):
    assert "reopen_count+1" in tr.effects_for("bug", "Fixed", "Reopened")
    # реализация в board_inbound.apply_status: бамп счётчика + status_since
    p = repo.bug("BUG-500", "Fixed", extra="reopen_count: 1\n")
    bi.apply_status(p, "Reopened", dry=False)
    text = p.read_text(encoding="utf-8")
    assert "status: Reopened" in text
    assert "reopen_count: 2" in text
    assert "status_since:" in text
