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


# --- r10-release-readiness (docs/10 D2+P1): секция "Release readiness" ---

def test_release_readiness_build_na_without_aut(repo, monkeypatch):
    """Item 1: state/app-under-test.yaml отсутствует -> явное n/a, не падение."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")

    assert "## Release readiness" in text
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]
    assert "- Сборка: n/a (state/app-under-test.yaml не найден)" in section


def test_release_readiness_build_from_aut(repo, monkeypatch):
    """Item 1: сборка читается из app-under-test.yaml; отсутствующие поля -> n/a."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.app_under_test(built_at="2026-07-06T00:00:00")

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "versionCode 11" in section
    assert "built_at 2026-07-06T00:00:00" in section
    # version_name не задан фикстурой app_under_test -> n/a, не "?" и не падение
    assert "n/a (versionCode" in section


def test_release_readiness_suite_freshness_and_not_run(repo, monkeypatch):
    """Item 2: последний run по suite -> статус + возраст в часах; suite без
    прогонов -> not_run."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    # updated фикстуры run() зафиксирован на "2026-07-01T00:00:00Z"
    repo.run("RUN-100", "Closed", extra="suite: smoke\n")

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "smoke: Closed · smoke_freshness_hours: **168.0** (RUN-100)" in section
    assert "- regression: not_run" in section
    assert "- canary: not_run" in section


def test_release_readiness_blocker_critical_and_known_issues(repo, monkeypatch):
    """Item 3/4: открытые blocker/critical app_bug (не test_debt) + счётчик known_issue."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.bug("BUG-200", "Open", extra="severity: critical\n")           # считается
    repo.bug("BUG-201", "Fixed", extra="severity: blocker\n")           # не Open/Reopened
    repo.bug("BUG-202", "Open")                                        # severity: major — не считается
    repo.bug("BUG-203", "Open", extra="severity: blocker\nknown_issue: true\n")

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Открытые blocker/critical: **2**" in section
    assert "BUG-200" in section and "BUG-203" in section
    assert "BUG-201" not in section.split("Открытые blocker/critical")[1].split("\n")[0]
    assert "- Известные проблемы (known_issue): **1**" in section


def test_release_readiness_p0_p1_coverage_and_uncovered(repo, monkeypatch):
    """Item 5: доля Automated по priority P0/P1 + явный список непокрытых P0."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.test_case("TC-100", "Automated", extra="priority: P0\n")
    repo.test_case("TC-101", "Approved", extra="priority: P0\n")   # непокрытый P0
    repo.test_case("TC-102", "Review", extra="priority: P1\n")     # непокрытый P1 (список не требуется)

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- p0_automation_coverage: **50%** (1/2)" in section
    assert "- p1_automation_coverage: **0%** (0/1)" in section
    assert "непокрытые P0: TC-101" in section


def test_release_readiness_test_debt_open_and_quarantine(repo, monkeypatch):
    """Item 6/7: test_debt Open|Reopened (Fixed исключён) + карантин автотестов."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.bug("BUG-300", "Open", extra="type: test_debt\ndebt_kind: flaky_test\n")
    repo.bug("BUG-301", "Fixed", extra="type: test_debt\ndebt_kind: flaky_test\n")
    repo.test_case("TC-200", "Automated", extra=(
        "automation_status: quarantined\nquarantine_reason: flaky\n"
        "quarantine_since: \"2026-07-01T00:00:00Z\"\n"))

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Test debt открыт: **1**" in section
    assert "BUG-300" in section.split("Test debt открыт")[1].split("\n")[0]
    assert "BUG-301" not in section.split("Test debt открыт")[1].split("\n")[0]
    assert "- Карантин автотестов: **1**" in section
    assert "TC-200" in section.split("Карантин автотестов")[1].split("\n")[0]


# --- red-probe-видимость (docs/09 п.10, 2026-07-17): ретрофит-долг ---

def test_release_readiness_red_probe_missing_counts_automated_active_without_field(repo, monkeypatch):
    """Automated+active без red_probe -> считается и перечисляется; заполненный
    red_probe, неактивный automation_status и не-Automated статус — не считаются."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.test_case("TC-500", "Automated", extra="automation_status: active\n")               # без red_probe -> считается
    repo.test_case("TC-501", "Automated", extra=(
        "automation_status: active\nred_probe: \"2026-07-17T00:00:00Z\"\n"))                 # есть red_probe -> нет
    repo.test_case("TC-502", "Automated", extra="automation_status: quarantined\n")           # не active -> нет
    repo.test_case("TC-503", "Approved")                                                      # не Automated -> нет

    text = qs.render(qs.collect(), "2026-07-17T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Automated без red_probe: **1**" in section
    assert "TC-500" in section.split("Automated без red_probe")[1].split("\n")[0]
    assert "TC-501" not in section.split("Automated без red_probe")[1].split("\n")[0]
    assert "TC-502" not in section.split("Automated без red_probe")[1].split("\n")[0]


def test_release_readiness_red_probe_missing_zero_when_all_covered(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.test_case("TC-510", "Automated", extra=(
        "automation_status: active\nred_probe: \"2026-07-17T00:00:00Z\"\n"))

    text = qs.render(qs.collect(), "2026-07-17T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Automated без red_probe: **0**" in section


def test_release_readiness_untriaged_age(repo, monkeypatch):
    """Item 8: runs NeedsTriage — счёт + максимальный возраст (untriaged_failure_age)."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.run("RUN-400", "NeedsTriage")   # updated фикстуры: 2026-07-01T00:00:00Z

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Untriaged: **1** · untriaged_failure_age: **168.0**" in section


def test_release_readiness_untriaged_zero_when_none(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")
    section = text.split("## Release readiness")[1].split("## Сборка под тестом")[0]

    assert "- Untriaged: **0** · untriaged_failure_age: **0**" in section


# --- E4 pipeline wiring: секция "Exploratory" (charter'ы из exploratory-charters/) ---

def test_exploratory_section_zeros_when_dir_missing(repo, monkeypatch):
    """Каталог exploratory-charters/ отсутствует — секция с нулями, не падение."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    text = qs.render(qs.collect(), "T")

    assert "## Exploratory" in text
    section = text.split("## Exploratory")[1].split("## Активные локи")[0]
    assert "charters_executed: **0**" in section
    assert "bugs_from_charters: **0**" in section
    assert "tc_from_charters: **0**" in section


def test_exploratory_section_counts_by_status(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.charter("CH-001", "InProgress", lock="exploratory-tester@2026-07-14")
    repo.charter("CH-002", "Planned")
    repo.charter("CH-003", "Done")

    text = qs.render(qs.collect(), "T")
    section = text.split("## Exploratory")[1].split("## Активные локи")[0]

    assert "Planned: **1**" in section
    assert "InProgress: **1**" in section
    assert "Done: **1**" in section
    assert "charters_executed: **1**" in section


def test_exploratory_bugs_and_tc_from_done_charters(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.charter("CH-010", "Done", extra=(
        'found_bugs: ["AT-BUG-005", "AT-BUG-007"]\n'
        'followup_tc: ["TC-030"]\n'))
    repo.charter("CH-011", "Planned", extra='found_bugs: ["AT-BUG-999"]\n')  # не Done — не считается

    text = qs.render(qs.collect(), "T")
    section = text.split("## Exploratory")[1].split("## Активные локи")[0]

    assert "bugs_from_charters: **2**" in section
    assert "tc_from_charters: **1**" in section


def test_exploratory_attachments_md_not_counted(repo, monkeypatch):
    """e4-charter-lock-reaper п.2: _iter_charters сканирует ТОЛЬКО верхний
    уровень (glob CH-*.md) — attachments/CH-NNN/*.md (если бы там были .md)
    не должны попадать в счётчики (находка critic N3)."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)
    repo.charter("CH-030", "Done")
    attachment = repo.root / "exploratory-charters" / "attachments" / "CH-030" / "note.md"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("---\nid: CH-030\nstatus: Done\n---\n\nвложение, не артефакт\n",
                           encoding="utf-8")

    text = qs.render(qs.collect(), "T")
    section = text.split("## Exploratory")[1].split("## Активные локи")[0]

    assert "Done: **1**" in section          # не **2**
    assert "charters_executed: **1**" in section


def test_exploratory_section_placed_before_locks(repo, monkeypatch):
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    text = qs.render(qs.collect(), "T")

    assert text.index("## Прогоны") < text.index("## Exploratory") < text.index("## Активные локи")


def test_release_readiness_section_placed_after_header(repo, monkeypatch):
    """Оформление: секция идёт заметно — сразу после generated_at-метки, до
    остальных секций дайджеста."""
    monkeypatch.setattr(qs, "REPO", repo.root, raising=True)
    monkeypatch.setattr(qs, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)
    monkeypatch.setattr(qs, "ESCALATIONS_PATH", repo.root / "state" / "escalations.md", raising=True)

    text = qs.render(qs.collect(), "2026-07-08T00:00:00Z")

    assert text.index("## Release readiness") < text.index("## Сборка под тестом")
    assert text.index("generated_at:") < text.index("## Release readiness")
