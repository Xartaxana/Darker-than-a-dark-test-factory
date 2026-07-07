"""Юнит-тесты pre_step stale_locks (scripts/stale_locks.py).

Изолированное мини-репо из conftest.Repo; время инжектится через sweep(now=...) —
тесты детерминированы, реального времени не касаются.
"""
from __future__ import annotations

import datetime

import stale_locks as sl

NOW = datetime.datetime(2026, 7, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)

FRESH = "test-automator:2026-07-07T11:30:00Z"    # 0.5 ч
STALE = "test-automator:2026-07-02T22:22:24Z"    # ~110 ч (прецедент TC-021)


def test_stale_lock_removed_and_logged(repo):
    p = repo.test_case("TC-021", "Approved", lock=STALE)
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[STALE]" in r and "TC-021" in r for r in report)
    assert 'lock: ""' in p.read_text(encoding="utf-8")
    log = repo.read_artifact("state/orchestrator-log.md")
    assert "pre_step stale_locks" in log and STALE in log
    # завершения в логе не было — формулировка «агент упал»
    assert "упал" in log


def test_fresh_lock_untouched(repo):
    p = repo.test_case("TC-001", "Approved", lock=FRESH)
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[OK]" in r and "TC-001" in r for r in report)
    assert f'lock: "{FRESH}"' in p.read_text(encoding="utf-8")


def test_wip_lock_is_human_pause(repo):
    p = repo.bug("BUG-100", "Open", lock="wip")
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[SKIP]" in r and "BUG-100" in r for r in report)
    assert 'lock: "wip"' in p.read_text(encoding="utf-8")


def test_empty_lock_ignored(repo):
    repo.bug("BUG-101", "Open")  # lock: ""
    repo.sla(lock_stale=2)

    assert sl.sweep(now=NOW) == []


def test_malformed_lock_cleared_with_warn(repo):
    p = repo.test_case("TC-002", "Approved", lock="какая-то ерунда")
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[WARN]" in r and "TC-002" in r for r in report)
    assert 'lock: ""' in p.read_text(encoding="utf-8")


def test_dry_run_changes_nothing(repo):
    p = repo.test_case("TC-021", "Approved", lock=STALE)
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW, dry=True)

    assert any("[STALE]" in r for r in report)
    assert f'lock: "{STALE}"' in p.read_text(encoding="utf-8")   # лок на месте
    assert not (repo.root / "state" / "orchestrator-log.md").exists()


def test_idempotent_second_run_noop(repo):
    repo.test_case("TC-021", "Approved", lock=STALE)
    repo.sla(lock_stale=2)

    first = sl.sweep(now=NOW)
    second = sl.sweep(now=NOW)

    assert any("[STALE]" in r for r in first)
    assert second == []  # лок уже снят, второй проход тихий


def test_completion_in_log_changes_wording(repo):
    repo.test_case("TC-030", "Approved", lock=STALE)
    repo.sla(lock_stale=2)
    repo.orch_log("| 2026-07-02T23:00:00Z | Автоматизировать | test-automator | TC-030.md | OK, лок снят |")

    sl.sweep(now=NOW)

    log = repo.read_artifact("state/orchestrator-log.md")
    assert "забыл снять лок" in log


def test_missing_sla_uses_default(repo):
    # sla.yaml нет — дефолт 2ч; лок возрастом 3ч должен сняться
    repo.test_case("TC-003", "Approved", lock="test-runner:2026-07-07T09:00:00Z")

    report = sl.sweep(now=NOW)

    assert any("[STALE]" in r and "TC-003" in r for r in report)
