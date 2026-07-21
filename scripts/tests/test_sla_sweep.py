"""Юнит-тесты pre_step sla_sweep (scripts/sla_sweep.py).

Время инжектится через sweep(now=...). Пороги задаются repo.sla(...) в часах.
"""
from __future__ import annotations

import datetime

import sla_sweep as ss

NOW = datetime.datetime(2026, 7, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)
OLD = '"2026-07-01T00:00:00Z"'      # ~156 ч до NOW
FRESH = '"2026-07-07T10:00:00Z"'    # 2 ч до NOW


def _sla(repo, **over):
    base = dict(bug_open_blocker=24, bug_open_critical=72, bug_open_major=100,
                bug_open_minor=720, bug_fixed_waiting_build=72, blocked_any=24,
                run_needs_triage=12, question_unanswered=48, reopened_pingpong=2)
    base.update(over)
    repo.sla(**base)


def _esc(repo) -> str:
    p = repo.root / "state" / "escalations.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_open_major_over_threshold_escalates(repo):
    repo.bug("BUG-010", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:bug_open_major]" in _esc(repo) and "BUG-010" in _esc(repo)


def test_open_major_fresh_is_quiet(repo):
    repo.bug("BUG-011", "Open", extra=f"status_since: {FRESH}\n")
    # E5: charter_queue_empty — отдельное правило, не то, что здесь проверяем;
    # активный charter держит его тихим, чтобы sweep() остался пуст.
    repo.charter("CH-900", "Planned")
    _sla(repo)

    assert ss.sweep(now=NOW) == []
    assert "BUG-011" not in _esc(repo)


def test_blocker_escalates_immediately(repo):
    p = repo.bug("BUG-012", "Open", extra=f"status_since: {FRESH}\n")
    p.write_text(p.read_text(encoding="utf-8").replace("severity: major", "severity: blocker"),
                 encoding="utf-8")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:bug_open_blocker]" in _esc(repo)


def test_fixed_without_new_build_escalates(repo):
    repo.bug("BUG-013", "Fixed", extra=f"status_since: {OLD}\n")
    repo.app_under_test(built_at="2026-06-28T00:00:00")   # сборка СТАРШЕ перевода в Fixed
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:bug_fixed_waiting_build]" in _esc(repo)


def test_fixed_with_newer_build_is_quiet(repo):
    repo.bug("BUG-014", "Fixed", extra=f"status_since: {OLD}\n")
    repo.app_under_test(built_at="2026-07-06T00:00:00")   # сборка НОВЕЕ — очередь fix-verifier
    _sla(repo)

    ss.sweep(now=NOW)

    assert "bug_fixed_waiting_build" not in _esc(repo)


def test_blocked_any_and_run_needs_triage(repo):
    repo.bug("BUG-015", "Blocked", extra=f"status_since: {OLD}\n")
    repo.run("RUN-001", "NeedsTriage", extra=f"status_since: {OLD}\n")
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:blocked_any]" in text and "BUG-015" in text
    assert "[sla:run_needs_triage]" in text and "RUN-001" in text


def test_awaiting_dev_unanswered(repo):
    repo.bug("BUG-016", "Open", extra=f"status_since: {FRESH}\nawaiting: dev\n")  # свежий — тихо
    repo.bug("BUG-017", "Open", extra=f"status_since: {OLD}\nawaiting: dev\n")    # старый — варнинг
    _sla(repo, bug_open_major=100000)   # отключаем open-правило, изолируем question_unanswered

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "BUG-017" in text and "[sla:question_unanswered]" in text
    assert "BUG-016" not in text


def test_pingpong_not_applied_while_fixed(repo):
    """Из Fixed не блокируем (матрица): у fix-verifier должен остаться шанс
    верифицировать свежий фикс; заблокируем, только если снова reopened."""
    p = repo.bug("BUG-030", "Fixed", extra=f"status_since: {FRESH}\nreopen_count: 2\n")
    _sla(repo)

    report = ss.sweep(now=NOW)

    assert not any("[BLOCK]" in r for r in report)
    assert "status: Fixed" in p.read_text(encoding="utf-8")
    assert "pingpong" not in _esc(repo)


def test_pingpong_from_rejected_dispute(repo):
    """D4: спор по Rejected достиг порога → Blocked + эскалация."""
    p = repo.bug("BUG-031", "Rejected", extra=f"status_since: {FRESH}\ndispute_count: 2\n")
    _sla(repo)

    report = ss.sweep(now=NOW)

    assert any("[BLOCK]" in r for r in report)
    assert "status: Blocked" in p.read_text(encoding="utf-8")
    assert "[sla:pingpong]" in _esc(repo)


def test_pingpong_blocks_bug(repo):
    p = repo.bug("BUG-018", "Reopened", extra=f"status_since: {FRESH}\nreopen_count: 2\n")
    _sla(repo)

    report = ss.sweep(now=NOW)

    assert any("[BLOCK]" in r for r in report)
    text = p.read_text(encoding="utf-8")
    assert "status: Blocked" in text
    assert "[sla:pingpong]" in _esc(repo)
    # B5: причина известна детерминированно — проставляется автоматически.
    assert "blocked_reason: product_decision" in text


def test_known_issue_skips_severity_escalation(repo):
    """B2: сознательно оставленный known_issue не шлёт периодический SLA-варнинг."""
    repo.bug("BUG-040", "Open", extra=f"status_since: {OLD}\nknown_issue: true\n")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "BUG-040" not in _esc(repo)


def test_resolution_skips_severity_escalation(repo):
    """B1: risk-accepted/wontfix — тоже не нагружает SLA по severity."""
    repo.bug("BUG-041", "Open",
             extra=f"status_since: {OLD}\nresolution: accepted_risk\nresolution_comment: ok\n")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "BUG-041" not in _esc(repo)


def test_blocked_any_includes_reason_when_present(repo):
    repo.bug("BUG-042", "Blocked", extra=f"status_since: {OLD}\nblocked_reason: dev_answer\n")
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "BUG-042" in text and "причина: dev_answer" in text


def test_quarantine_expiry_passed_escalates(repo):
    """B3: явный quarantine_expiry в прошлом → эскалация quarantine_expired."""
    repo.test_case("TC-070", "Automated", extra=(
        "automation_status: quarantined\nquarantine_reason: flaky\n"
        "quarantine_since: \"2026-07-01T00:00:00Z\"\n"
        "quarantine_expiry: \"2026-07-05T00:00:00Z\"\n"))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:quarantine_expired]" in _esc(repo) and "TC-070" in _esc(repo)


def test_quarantine_max_fallback_without_expiry(repo):
    """B3: без expiry дедлайн = quarantine_since + quarantine_max."""
    repo.test_case("TC-071", "Automated", extra=(
        "automation_status: quarantined\nquarantine_reason: flaky\n"
        "quarantine_since: \"2026-07-01T00:00:00Z\"\n"))   # 156 ч до NOW
    _sla(repo, quarantine_max=100)                          # порог 100 ч — просрочен

    ss.sweep(now=NOW)

    assert "[sla:quarantine_expired]" in _esc(repo) and "TC-071" in _esc(repo)


def test_fresh_quarantine_is_quiet(repo):
    repo.test_case("TC-072", "Automated", extra=(
        "automation_status: quarantined\nquarantine_reason: flaky\n"
        f"quarantine_since: {FRESH}\n"))
    _sla(repo)   # quarantine_max default 336 ч

    ss.sweep(now=NOW)

    assert "TC-072" not in _esc(repo)


def test_test_debt_skips_severity_and_build_rules(repo):
    """B4: долг фреймворка не шумит bug_open_* и не ждёт сборку в Fixed."""
    repo.bug("BUG-070", "Open", extra=f"status_since: {OLD}\ntype: test_debt\n")
    repo.bug("BUG-071", "Fixed", extra=f"status_since: {OLD}\ntype: test_debt\n")
    repo.app_under_test(built_at="2026-06-28T00:00:00")   # сборки новее нет
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "BUG-070" not in text
    assert "BUG-071" not in text


# --- E5: charter_queue_empty (fail-safe надзор за очередью exploratory-чартеров) ---

AT_THRESH = '"2026-07-05T10:00:00Z"'    # ровно 50ч до NOW
OVER_THRESH = '"2026-07-05T09:00:00Z"'  # 51ч до NOW — за порогом 50ч


def test_charter_queue_empty_dir_missing_escalates(repo):
    """Каталог exploratory-charters/ не создан вовсе — fail-safe эскалация."""
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:charter_queue_empty]" in _esc(repo) and "CHARTER-QUEUE" in _esc(repo)


def test_charter_queue_empty_active_charter_is_quiet(repo):
    repo.charter("CH-100", "Planned")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_queue_empty" not in _esc(repo)


def test_charter_queue_empty_no_done_at_all_escalates(repo):
    """Чартеры есть, но ни один не Proposed/Planned/InProgress и ни один не Done."""
    repo.charter("CH-101", "Blocked")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:charter_queue_empty]" in _esc(repo)


def test_charter_queue_empty_executed_at_malformed_escalates(repo):
    repo.charter("CH-102", "Done", extra='executed_at: "not-a-date"\n')
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:charter_queue_empty]" in _esc(repo)


def test_charter_queue_empty_executed_at_missing_escalates(repo):
    repo.charter("CH-103", "Done")   # executed_at пуст (фикстура по умолчанию)
    _sla(repo)

    ss.sweep(now=NOW)

    assert "[sla:charter_queue_empty]" in _esc(repo)


def test_charter_queue_empty_over_threshold_escalates(repo):
    repo.charter("CH-104", "Done", extra=f"executed_at: {OVER_THRESH}\n")
    _sla(repo, charter_queue_empty=50)

    ss.sweep(now=NOW)

    assert "[sla:charter_queue_empty]" in _esc(repo)


def test_charter_queue_empty_exactly_at_threshold_is_quiet(repo):
    """Граница (класс M6): ровно на пороге — ещё НЕ эскалация (<=, не <)."""
    repo.charter("CH-105", "Done", extra=f"executed_at: {AT_THRESH}\n")
    _sla(repo, charter_queue_empty=50)

    ss.sweep(now=NOW)

    assert "charter_queue_empty" not in _esc(repo)


def test_charter_queue_empty_fresh_done_is_quiet(repo):
    repo.charter("CH-106", "Done", extra=f"executed_at: {FRESH}\n")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_queue_empty" not in _esc(repo)


def test_dedup_and_timestamp_preserved(repo):
    repo.bug("BUG-019", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)

    ss.sweep(now=NOW)
    first = _esc(repo)
    later = NOW + datetime.timedelta(hours=5)
    ss.sweep(now=later)
    second = _esc(repo)

    assert second == first                          # ни дубля, ни смены времени
    assert second.count("BUG-019") == 1


def test_autoresolve_removes_only_tagged(repo):
    bug = repo.bug("BUG-020", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)
    ss.sweep(now=NOW)
    assert "BUG-020" in _esc(repo)

    # человек/агент закрыл баг + в реестре есть строка БЕЗ тега (конфликт борды)
    bug.write_text(bug.read_text(encoding="utf-8").replace("status: Open", "status: Verified"),
                   encoding="utf-8")
    esc_path = repo.root / "state" / "escalations.md"
    esc_path.write_text(_esc(repo) + "- [2026-07-05T00:00:00Z] **BUG-999** — конфликт борды\n",
                        encoding="utf-8")

    report = ss.sweep(now=NOW)

    text = _esc(repo)
    assert "BUG-020" not in text                    # причина устранена — снято
    assert "BUG-999" in text                        # без тега — не трогаем
    assert any("[ESC-]" in r for r in report)


def test_dry_run_writes_nothing(repo):
    repo.bug("BUG-021", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)

    report = ss.sweep(now=NOW, dry=True)

    assert any("[ESC+]" in r for r in report)
    assert not (repo.root / "state" / "escalations.md").exists()
    assert not (repo.root / "state" / "orchestrator-log.md").exists()
