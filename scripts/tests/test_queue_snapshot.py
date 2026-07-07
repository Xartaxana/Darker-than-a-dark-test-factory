"""Юнит-тесты queue_snapshot (scripts/queue_snapshot.py)."""
from __future__ import annotations

import queue_snapshot as qs


def test_counts_and_sections(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "OUT_PATH", repo.root / "state" / "factory-status.md", raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    repo.test_case("TC-001", "Approved")
    repo.test_case("TC-002", "Approved")
    repo.test_case("TC-003", "Automated")
    repo.bug("BUG-001", "Open")
    repo.bug("BUG-002", "Fixed")
    repo.run("RUN-001", "NeedsTriage")
    repo.test_case("TC-004", "Approved", lock="test-automator:2026-07-07T10:00:00Z")
    repo.app_under_test(built_at="2026-07-06T00:00:00")
    (repo.root / "state" / "escalations.md").write_text(
        "# Эскалации фабрики\n\n- [2026-07-07T00:00:00Z] **BUG-001** [sla:bug_open_major] — висит\n",
        encoding="utf-8")

    text = qs.render(qs.collect(), "2026-07-07T12:00:00Z")

    assert "Approved: **3**" in text and "Automated: **1**" in text
    assert "Open: **1**" in text and "Fixed: **1**" in text
    assert "NeedsTriage: **1**" in text
    assert "BUG-001" in text                          # открытый баг в списке
    assert "TC-004 — `test-automator:2026-07-07T10:00:00Z`" in text
    assert "Эскалации (1)" in text
    assert "НЕ редактировать руками" in text


def test_known_issue_section_and_resolution_tag(repo, monkeypatch):
    """B1/B2: known_issue — отдельная секция дайджеста; resolution — тег у Open-бага."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    repo.bug("BUG-060", "Open", extra="known_issue: true\n")
    repo.bug("BUG-061", "Open", extra="resolution: accepted_risk\nresolution_comment: ok\n")

    text = qs.render(qs.collect(), "T")

    assert "Известные проблемы, known_issue (1)" in text
    assert "BUG-060" in text.split("## Известные проблемы")[1]
    assert "BUG-061 [major] Open [accepted_risk]" in text


def test_test_debt_section_and_automation_counter(repo, monkeypatch):
    """B3/B4: test debt — своя секция (не в счётчиках багов); карантин виден в TC."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    repo.bug("BUG-080", "Open", extra="type: test_debt\ndebt_kind: flaky_test\n")
    repo.bug("BUG-081", "Open")   # обычный app_bug
    repo.test_case("TC-080", "Automated", extra=(
        "automation_status: quarantined\nquarantine_reason: flaky\n"
        "quarantine_since: \"2026-07-07T00:00:00Z\"\n"))

    text = qs.render(qs.collect(), "T")

    assert "Test debt (1)" in text
    assert "BUG-080 [flaky_test] Open" in text.split("## Test debt")[1]
    # test_debt не считается в секции багов: там только BUG-081
    assert "## Баги (1)" in text
    assert "quarantined: **1**" in text


def test_stable_output_same_state(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.test_case("TC-001", "Review")

    a = qs.render(qs.collect(), "T")
    b = qs.render(qs.collect(), "T")
    assert a == b
