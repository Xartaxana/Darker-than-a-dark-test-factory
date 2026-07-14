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


# --- e4-charter-lock-reaper: exploratory-charters/CH-*.md тоже в обходе ---

def test_stale_charter_lock_removed_and_logged(repo):
    """Блокер critic-ревью: charter'ы не входят в bs._iter_artifacts(), их
    протухший лок раньше никто не снимал (класс TC-021, теперь и для CH-*)."""
    p = repo.charter("CH-020", "InProgress", lock=STALE)
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[STALE]" in r and "CH-020" in r for r in report)
    assert 'lock: ""' in p.read_text(encoding="utf-8")
    log = repo.read_artifact("state/orchestrator-log.md")
    assert "pre_step stale_locks" in log and STALE in log


def test_fresh_charter_lock_untouched(repo):
    p = repo.charter("CH-021", "InProgress", lock=FRESH)
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[OK]" in r and "CH-021" in r for r in report)
    assert f'lock: "{FRESH}"' in p.read_text(encoding="utf-8")


def test_charter_dir_missing_is_not_an_error(repo):
    """Каталог exploratory-charters/ отсутствует — не ошибка, просто нет charter-локов."""
    repo.test_case("TC-030", "Approved")  # хоть один артефакт, чтобы sweep был непустым
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert report == []  # TC-030 без лока — молчит; charter'ов нет — тоже молчит


def test_charter_attachments_md_ignored(repo):
    """exploratory-charters/attachments/CH-020/*.md (если бы там были .md) не
    входит в обход — сканируем только верхний уровень CH-*.md."""
    p = repo.charter("CH-022", "InProgress", lock=STALE)
    attachment = repo.root / "exploratory-charters" / "attachments" / "CH-022" / "note.md"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text(
        f'---\nid: CH-022\nlock: "{STALE}"\n---\n\nне артефакт, вложение\n', encoding="utf-8")
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    # ровно одно действие по CH-022 (верхний уровень), не два (вложение молчит)
    stale_ch022 = [r for r in report if "[STALE]" in r and "CH-022" in r]
    assert len(stale_ch022) == 1
    assert "attachments" not in "".join(report)
    assert 'lock: ""' in p.read_text(encoding="utf-8")
    # вложение не тронуто вовсе (его не сканировали)
    assert STALE in attachment.read_text(encoding="utf-8")


def test_charter_legacy_at_lock_is_unreadable_and_cleared_with_warn(repo):
    """Легаси-формат `agent@YYYY-MM-DD` (CH-001, схема допускает) не матчит
    LOCK_RE — трактуется как нечитаемый лок и снимается безусловно, тем же
    путём, что «какая-то ерунда» у test-case/bug/run (см. докстринг модуля)."""
    p = repo.charter("CH-023", "InProgress", lock="exploratory-tester@2026-07-14")
    repo.sla(lock_stale=2)

    report = sl.sweep(now=NOW)

    assert any("[WARN]" in r and "CH-023" in r for r in report)
    assert 'lock: ""' in p.read_text(encoding="utf-8")
