"""Юнит-тесты pre_step sla_sweep (scripts/sla_sweep.py).

Время инжектится через sweep(now=...). Пороги задаются repo.sla(...) в часах.
"""
from __future__ import annotations

import datetime

import pytest

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
    # То же для compatibility_run_stale (каденция 2026-08-25): свежий
    # Closed-прогон suite=compatibility, mode=live, device_avd=api29, с
    # выполненными тестами держит правило тихим (критик-раунд доработки
    # Б1/Б2: mode/device_avd/totals теперь ОБЯЗАТЕЛЬНЫ для зачёта).
    repo.run("RUN-20260707-1000", "Closed",
             extra=f"suite: compatibility\nmode: live\ndevice_avd: ao3_test_api29\n"
                   f"totals: {{ passed: 10, failed: 0 }}\n"
                   f"status_since: {FRESH}\n")
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


# --- charter_followup_unprocessed (спека Lead 2026-08-03) ---


def _quiet_charter_queue(repo):
    """Держит charter_queue_empty тихим, чтобы тесты ниже проверяли ТОЛЬКО
    новый чек (тот же приём, что test_open_major_fresh_is_quiet)."""
    repo.charter("CH-900", "Planned")


def test_followup_tc_candidate_without_id_flags(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-010", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "КАНДИДАТ (id за test-designer): что-то важное без id"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-010:followup_tc#0" in text


def test_followup_tc_candidate_with_tc_id_is_quiet(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-011", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО → TC-200 (test-designer): что-то важное"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_candidate_with_at_bug_id_is_quiet(repo):
    """Спека Lead 2026-08-15: followup_tc легально закрывается долгом/
    тестгэпом через AT-BUG-NNN, не только новым TC (живой прецедент CH-010
    followup_tc#2 → AT-BUG-070, до фикса ложно эскалировался каждым проходом)."""
    _quiet_charter_queue(repo)
    repo.charter("CH-010", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО → AT-BUG-070 (test-designer, 2026-08-15, '
        'test_debt): Test-gap инфраструктуры: нужен надёжный приём адресации '
        'execute_script/навигации к КОНКРЕТНОЙ не-нулевой вкладке."\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_candidate_with_bug_id_is_quiet(repo):
    """Форма без AT- префикса (BUG-NNN) тоже легальна."""
    _quiet_charter_queue(repo)
    repo.charter("CH-018", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО → BUG-068 (test-designer): долг, не кейс"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_candidate_with_tc_id_regression_pin_is_quiet(repo):
    """Регресс-пин (DoD п.2): TC-id остаётся легальной формой закрытия
    followup_tc после расширения регекса до TC/BUG."""
    _quiet_charter_queue(repo)
    repo.charter("CH-019", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО → TC-205 (test-designer, 2026-08-15): '
        'TC-новый на BUG-068."\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_malformed_bug_token_forms_still_flag(repo):
    """Граница формы id-токена (правило 6a): "ABUG-12"/"ATBUG-12" —
    склеенные/битые формы без разделителя ПЕРЕД "BUG" — НЕ матчатся (\\b
    требует границы слова перед токеном), запись остаётся необработанной."""
    _quiet_charter_queue(repo)
    repo.charter("CH-020", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n'
        '  - "ЗАКРЫТО → ABUG-12 (битая форма, без разделителя)"\n'
        '  - "ЗАКРЫТО → ATBUG-12 (тоже битая форма)"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text
    assert "CH-020:followup_tc#0" in text
    assert "CH-020:followup_tc#1" in text


def test_found_bugs_candidate_without_id_flags(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-012", "Done", extra=(
        'found_bugs:\n  - "видел странное поведение, но баг ещё не заведён"\n'
        'followup_tc: []\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-012:found_bugs#0" in text


def test_found_bugs_candidate_with_bug_id_is_quiet(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-013", "Done", extra=(
        'found_bugs:\n  - "BUG-500: описание находки"\n'
        'followup_tc: []\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_candidate_on_non_done_charter_is_quiet(repo):
    """(в): follow-up ещё не долг, пока чартер не Done."""
    _quiet_charter_queue(repo)
    for status in ("Proposed", "Planned", "InProgress"):
        repo.charter(f"CH-{status}", status, extra=(
            'found_bugs:\n  - "кандидат без id"\n'
            'followup_tc:\n  - "кандидат без id"\n'
            'new_risks:\n  - "риск без маркера"\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_new_risks_with_marker_is_quiet(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-014", "Done", extra=(
        'found_bugs: []\nfollowup_tc: []\n'
        'new_risks:\n  - "предложение риска"\n'))
    docs = repo.root / "docs" / "01-test-strategy.md"
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text("...\nПересмотр по чартеру CH-014 (2026-08-03)\n...\n", encoding="utf-8")
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_new_risks_without_marker_flags(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-015", "Done", extra=(
        'found_bugs: []\nfollowup_tc: []\n'
        'new_risks:\n  - "предложение риска"\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-015:new_risks" in text


def test_followup_all_empty_lists_is_quiet(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-016", "Done", extra=(
        'found_bugs: []\nfollowup_tc: []\nnew_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_unprocessed_idempotent(repo):
    _quiet_charter_queue(repo)
    repo.charter("CH-017", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "кандидат без id"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)
    first = _esc(repo)
    ss.sweep(now=NOW + datetime.timedelta(hours=5))
    second = _esc(repo)

    assert second == first
    assert second.count("CH-017:followup_tc#0") == 1


# --- defect_found 2026-08-03 16:36: id-токен-ЦИТАТА чужой записи ≠ обработано ---
# (регрессия на живой ложный негатив; дословный текст — git-история CH-007
# (5d6f834^:exploratory-charters/CH-007.md), followup_tc[0] ДО фикса
# test-designer'ом: "id-токен где-то в тексте" гасил эскалацию, хотя запись
# сама ещё не обработана — TC-115/TC-114 в ней ЦИТАТА чужого существующего
# кейса, а не собственный id этой записи.)

LIVE_QUOTED_FOLLOWUP_TC = (
    "КАНДИДАТ (id за test-designer): downloadPath ПЕРЕЖИВАЕТ правку "
    "заметки/тега у скачанной работы — замок под находку 1; TC-115/TC-114 "
    "этот инвариант не держат (они про отсутствие файла у нескачанной "
    "работы)."
)


def test_followup_tc_quoting_foreign_id_still_flags(repo):
    """Дословный живой ложный негатив (CH-007 followup_tc[0] до фикса):
    цитата "TC-115/TC-114" идёт ПОСЛЕ двоеточия/тире прозы — не свой id,
    запись остаётся необработанным кандидатом."""
    _quiet_charter_queue(repo)
    repo.charter("CH-107", "Done", extra=(
        'found_bugs: []\n'
        f'followup_tc:\n  - "{LIVE_QUOTED_FOLLOWUP_TC}"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-107:followup_tc#0" in text


def test_followup_tc_zakryto_arrow_prefix_is_quiet(repo):
    """Конвенция "ЗАКРЫТО → TC-NNN" (эталон CH-006/CH-008, обработано этой
    сессией) — id идёт ПЕРЕД первым ":"/тире (тире — это "→", не ":"/"—")."""
    _quiet_charter_queue(repo)
    repo.charter("CH-108", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО → TC-157 (test-designer, 2026-08-03): '
        'гейт на границе навигации, покрытия не было."\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_pokryt_sushchestvuyushchim_prefix_is_quiet(repo):
    """Вторая легальная форма закрытия (эталон CH-007, дословно): "ПОКРЫТ
    СУЩЕСТВУЮЩИМ → TC-NNN" — кандидат закрыт УЖЕ существующим кейсом, не
    новым; та же позиция id (перед ":"/тире) — тихо."""
    _quiet_charter_queue(repo)
    repo.charter("CH-109", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ПОКРЫТ СУЩЕСТВУЮЩИМ → TC-129 (test-designer, '
        '2026-08-03): замок под находку уже существует в другом кейсе."\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_followup_tc_marker_colon_without_arrow_still_flags(repo):
    """Граница классификатора (правило 6a): маркер-слово, за которым сразу
    ':' БЕЗ стрелки "→" — это НЕ распознанная конвенция закрытия (id идёт
    ПОСЛЕ ':', как в цитате) — намеренно флагуется, чтобы не открыть дыру
    вида "ЗАКРЫТО: <проза с чужим id>" без реального назначения id этой
    записи."""
    _quiet_charter_queue(repo)
    repo.charter("CH-110", "Done", extra=(
        'found_bugs: []\n'
        'followup_tc:\n  - "ЗАКРЫТО: TC-202 без стрелки — не наша конвенция"\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-110:followup_tc#0" in text


def test_found_bugs_quoting_foreign_id_still_flags(repo):
    """Симметрично followup_tc (DoD п.1: found_bugs тем же приёмом):
    кандидат, упоминающий ЧУЖОЙ существующий BUG-id как контекст, но не
    несущий СВОЙ id первым — остаётся необработанным. (Представительная
    фикстура класса; дословного живого примера с этой формой в found_bugs
    на момент фикса в данных не найдено — found_bugs пишется сразу с
    собственным id при заведении бага, см. CH-008.)"""
    _quiet_charter_queue(repo)
    repo.charter("CH-111", "Done", extra=(
        'found_bugs:\n  - "видели похожее в этой же сессии — BUG-021 не '
        'единственный случай такого рода, но отдельно ещё не заведено"\n'
        'followup_tc: []\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:charter_followup_unprocessed]" in text and "CH-111:found_bugs#0" in text


def test_found_bugs_own_id_at_start_is_quiet(repo):
    """Эталон CH-008 (дословно): found_bugs несёт свой id ПРЯМО в начале
    записи, без маркера-слова — тихо."""
    _quiet_charter_queue(repo)
    repo.charter("CH-112", "Done", extra=(
        'found_bugs:\n  - "BUG-046: ручной «Scan for downloads» при ДВУХ '
        'файлах с одним ao3Id рапортует несходящийся результат."\n'
        'followup_tc: []\n'
        'new_risks: []\n'))
    _sla(repo)

    ss.sweep(now=NOW)

    assert "charter_followup_unprocessed" not in _esc(repo)


def test_record_processed_unit_dash_inside_id_not_a_delimiter():
    """Граница (правило 6a): ASCII-дефис ВНУТРИ самого id-токена ("TC-151",
    "BUG-021") — не разделитель прозы (разделитель — ":"/тире "—"/"–", не
    дефис-дефис); id-токен на позиции 0 всегда "свой", даже если он сам
    содержит дефис."""
    assert ss._record_processed("BUG-021 (расширение): текст", ss.FOUND_BUGS_ID_RE) is True
    assert ss._record_processed("TC-151/TC-152 (test-designer): текст", ss.FOLLOWUP_TC_ID_RE) is True


def test_record_processed_unit_no_id_at_all_is_unprocessed():
    assert ss._record_processed("КАНДИДАТ без id вовсе", ss.FOLLOWUP_TC_ID_RE) is False


# --- FOLLOWUP_TC_ID_RE расширение до TC|BUG/AT-BUG (спека Lead 2026-08-15) ---


def test_followup_tc_id_re_unit_at_bug_token_matches():
    assert ss.FOLLOWUP_TC_ID_RE.search("AT-BUG-070") is not None
    assert ss._record_processed("ЗАКРЫТО → AT-BUG-070: долг", ss.FOLLOWUP_TC_ID_RE) is True


def test_followup_tc_id_re_unit_bug_token_matches():
    assert ss.FOLLOWUP_TC_ID_RE.search("BUG-068") is not None
    assert ss._record_processed("ЗАКРЫТО → BUG-068: долг", ss.FOLLOWUP_TC_ID_RE) is True


def test_followup_tc_id_re_unit_tc_token_still_matches():
    """Регресс-пин: TC-NNN остаётся валидным после расширения регекса."""
    assert ss.FOLLOWUP_TC_ID_RE.search("TC-205") is not None
    assert ss._record_processed("ЗАКРЫТО → TC-205: кейс", ss.FOLLOWUP_TC_ID_RE) is True


def test_followup_tc_id_re_unit_malformed_forms_do_not_match():
    """Граница формы (правило 6a): "ABUG-12"/"ATBUG-12" — нет разделителя
    слова ПЕРЕД "BUG" (\\b не срабатывает между двумя word-символами) —
    НЕ матчатся вовсе."""
    assert ss.FOLLOWUP_TC_ID_RE.search("ABUG-12") is None
    assert ss.FOLLOWUP_TC_ID_RE.search("ATBUG-12") is None


# --- compatibility_run_stale (каденция «раз в неделю», слово владельца 2026-08-25) ---

# З5 (критик-раунд 2): порог приведён к прецеденту charter_queue_empty
# (168ч правило * 1.33 = 224ч, было 336ч = 2x) — таймстампы ниже пересчитаны
# под новый порог, семантика (fresh/stale) сохранена.
COMPAT_FRESH = '"2026-07-03T08:00:00Z"'   # 100ч до NOW — внутри порога 224ч
COMPAT_STALE = '"2026-06-20T00:00:00Z"'   # 420ч до NOW — за порогом

# Критик-раунд доработки Б1 (2026-08-25): mode/device_avd теперь ОБЯЗАТЕЛЬНЫ
# для зачёта каденции. VALID_* — минимальный набор полей, при которых прогон
# считается свежим сам по себе (используется как база во всех тестах ниже,
# чтобы изолировать проверяемое условие).
VALID_MODE = "mode: live\n"
VALID_AVD = "device_avd: ao3_test_api29\n"   # топология CLAUDE.md — стек 2
WRONG_AVD = "device_avd: ao3_test_api34\n"   # чужой стек/API level (не api29)
# Б8 (критик-раунд 2): хотя бы один выполненный тест — тоже ОБЯЗАТЕЛЬНОЕ
# условие зачёта каденции; добавляется к VALID_MODE/VALID_AVD везде, где
# фикстура должна пройти ВСЕ условия целиком (изолирует проверяемое условие
# от НОВОГО обязательного поля, не связанного с этим конкретным тестом).
VALID_TOTALS = "totals: { passed: 10, failed: 0 }\n"


def _quiet_neighbours(repo):
    """Гасит соседние правила, чтобы в escalations остался только предмет теста."""
    repo.charter("CH-901", "Planned")


def test_compatibility_no_run_at_all_escalates(repo):
    """Прогонов compatibility нет вовсе — fail-safe эскалация (недоказанная
    свежесть != свежесть). Это ровно исходное состояние 2026-08-25, из-за
    которого набор и простоял вне правил."""
    _quiet_neighbours(repo)
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "[sla:compatibility_run_stale]" in _esc(repo)
    assert "COMPATIBILITY-RUN" in _esc(repo)
    assert "нет ни одного" in _esc(repo)


def test_compatibility_fresh_run_is_quiet(repo):
    _quiet_neighbours(repo)
    repo.run("RUN-20260701-0000", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}"
                   f"status_since: {COMPAT_FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


def test_compatibility_stale_run_escalates(repo):
    _quiet_neighbours(repo)
    repo.run("RUN-20260620-0000", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}"
                   f"status_since: {COMPAT_STALE}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "порог 224ч превышен" in text


def test_compatibility_other_suite_does_not_count(repo):
    """Свежий canary НЕ закрывает каденцию compatibility — граница по suite."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0900", "Closed",
             extra=f"suite: canary\nstatus_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "[sla:compatibility_run_stale]" in _esc(repo)


def test_compatibility_unclosed_run_does_not_count(repo):
    """Прогон есть, но не разобран (NeedsTriage) — каденция не считается
    соблюдённой: прогон без вердикта не доказывает совместимость."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0800", "NeedsTriage",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "[sla:compatibility_run_stale]" in _esc(repo)


def test_compatibility_broken_status_since_falls_back_to_updated(repo):
    """Битый `status_since` НЕ делает прогон недатированным: модульная
    семантика `_since` (status_since, иначе updated) держится и здесь —
    фикстура пишет свежий `updated`, каденция считается соблюдённой.
    Пин именно на фолбэк: тихо здесь — это осознанное поведение, а не
    пропущенная ветка (ветка «даты нет вовсе» закрыта тестом
    no_run_at_all, где newest is None)."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0700", "Closed",
             extra=f'suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}'
                   f'status_since: "не-дата"\n')
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


# --- Б1 (критик-раунд 2026-08-25): mode/device_avd обязательны — адверсариальная
# батарея (DoD п.2): отсутствующее поле, пустая строка, неверный регистр, мусор
# вместо mode, отсутствующий device_avd, device_avd чужого стека.


def test_compatibility_replay_mode_does_not_count(repo):
    """Б1: mode=replay больше НЕ глушит детектор (было — критикуемый дефект:
    ЛЮБОЙ Closed compatibility считался свежим). TC-111 требует живую
    страницу (framework/steps/browser_steps.py:118-121)."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0600", "Closed",
             extra=f"suite: compatibility\nmode: replay\n{VALID_AVD}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "mode=replay" in text


def test_compatibility_mode_missing_does_not_count(repo):
    """Адверсариальная батарея: поле mode отсутствует вовсе."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0601", "Closed",
             extra=f"suite: compatibility\n{VALID_AVD}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "mode=?" in text


def test_compatibility_mode_empty_string_does_not_count(repo):
    """Адверсариальная батарея: mode — пустая строка."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0602", "Closed",
             extra=f'suite: compatibility\nmode: ""\n{VALID_AVD}status_since: {FRESH}\n')
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "mode=?" in text


def test_compatibility_mode_garbage_does_not_count(repo):
    """Адверсариальная батарея: мусор вместо mode."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0603", "Closed",
             extra=f"suite: compatibility\nmode: banana\n{VALID_AVD}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "mode=banana" in text


def test_compatibility_device_avd_missing_does_not_count(repo):
    """Адверсариальная батарея: device_avd отсутствует вовсе — прогон на
    неверном устройстве обесценивал бы TC-109 (фикстура
    api26_device_required), поэтому отсутствие свидетельства не засчитывается."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0604", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "без device_avd" in text


def test_compatibility_device_avd_empty_string_does_not_count(repo):
    """Адверсариальная батарея: device_avd — пустая строка."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0605", "Closed",
             extra=f'suite: compatibility\n{VALID_MODE}device_avd: ""\nstatus_since: {FRESH}\n')
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "без device_avd" in text


def test_compatibility_device_avd_wrong_stack_does_not_count(repo):
    """Адверсариальная батарея: device_avd чужого стека (api34, не api29) —
    именованный пример из спеки (Б1)."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0606", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{WRONG_AVD}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "device_avd=ao3_test_api34" in text


def test_compatibility_device_avd_register_insensitive_is_quiet(repo):
    """Признак api29 — подстрока БЕЗ учёта регистра (спека Б1): смешанный
    регистр в имени AVD не должен ложно отклонять валидный прогон."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0607", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}device_avd: AO3_Test_API29\n"
                   f"{VALID_TOTALS}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


# --- З3: штамп из будущего (класс ESC-040) ---

FUTURE_1S = '"2026-07-07T12:00:01Z"'   # NOW + 1с — строго позже, допуск 0


def test_compatibility_future_timestamp_does_not_count(repo):
    """З3 (класс ESC-040): штамп ПОЗЖЕ now не считается свежим, даже с
    валидными mode/device_avd — допуск перекоса строго 0."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-1201", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}status_since: {FUTURE_1S}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "ESC-040" in text


# --- DoD п.3 (класс M6): границы порога 224ч (З5) + отдельно штамп из будущего ---

AT_224H = '"2026-06-28T04:00:00Z"'          # ровно 224ч до NOW
JUST_INSIDE_224H = '"2026-06-28T04:01:00Z"'  # 223ч59м до NOW — чуть внутри
JUST_OVER_224H = '"2026-06-28T03:59:00Z"'    # 224ч01м до NOW — чуть за порогом


def test_compatibility_exactly_at_threshold_is_quiet(repo):
    """Граница (класс M6): ровно на пороге — ещё НЕ эскалация (<=, не <),
    тот же приём, что test_charter_queue_empty_exactly_at_threshold_is_quiet."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260628-0400", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}"
                   f"status_since: {AT_224H}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


def test_compatibility_just_inside_threshold_is_quiet(repo):
    _quiet_neighbours(repo)
    repo.run("RUN-20260628-0401", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}"
                   f"status_since: {JUST_INSIDE_224H}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


def test_compatibility_just_over_threshold_escalates(repo):
    _quiet_neighbours(repo)
    repo.run("RUN-20260628-0359", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}{VALID_TOTALS}"
                   f"status_since: {JUST_OVER_224H}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "порог 224ч превышен" in text


# --- Б7 (критик-раунд 2): признак api29 — набор ВСЕХ api-токенов в имени,
# не голая подстрока (промахивалась в обе стороны). Батарея — 20 имён,
# включая все шесть именованных в спеке промахов + штатные имена AVD Manager.

_API29_BATTERY = [
    # (device_avd, ожидание _is_api29)
    ("ao3_test_api29", True),
    ("ao3_corridor_api29", True),
    ("Pixel_5_API_29", True),
    ("Nexus_5X_API_29", True),
    ("ao3_test_api_29", True),
    ("AO3_Test_API29", True),
    ("api29", True),
    ("API_29", True),
    ("ao3_test_api34_was_api29", False),    # был ложный accept (голая подстрока)
    ("ao3_migrate_api29_to_api34", False),  # был ложный accept
    ("ao3_test_api294", False),             # был ложный accept ("29" — префикс "294")
    ("ao3_api290", False),                  # был ложный accept ("29" — префикс "290")
    ("ao3_test_api34", False),
    ("ao3_test_api26", False),
    ("Pixel_3a_API_30_Google_APIs", False),
    ("Nexus_5X_API_28", False),
    ("emulator-5554", False),               # без api-токена вовсе
    ("", False),
    ("api29api34", False),                  # два разных уровня без разделителя
    ("api2900", False),                     # один уровень, но не ровно "29"
    # З7 (критик-раунд 3): ГРАНИЦА признака, задокументированная рядом с
    # регексом в sla_sweep — не дефект, а требование к именованию AVD.
    # Отказ идёт в ГРОМКУЮ сторону (эскалация называет device_avd=<значение>).
    ("ao3_test_api029", False),             # ведущий ноль не поддерживается
    ("api029", False),
    ("ao3_corridor_lower", False),          # имя без токена api<уровень> вовсе
]


@pytest.mark.parametrize("avd,expected", _API29_BATTERY)
def test_is_api29_battery(avd, expected):
    assert ss._is_api29(avd) is expected


def test_compatibility_avd_multiple_api_levels_now_rejected(repo):
    """Красная проба Б7 (интеграция): миграционное имя с ДВУМЯ api-уровнями
    раньше ложно засчитывалось голой подстрокой "api29" — теперь отклоняется."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0608", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}device_avd: ao3_test_api34_was_api29\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "device_avd=ao3_test_api34_was_api29" in text


def test_compatibility_avd_standard_avd_manager_name_now_accepted(repo):
    """Красная проба Б7 (интеграция): штатное имя AVD Manager
    (`Pixel_5_API_29`) раньше ложно отклонялось голой подстрокой — теперь
    засчитывается."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0609", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}device_avd: Pixel_5_API_29\n"
                   f"{VALID_TOTALS}status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


# --- Б8 (критик-раунд 2): каденция спрашивает «прогон СОСТОЯЛСЯ?», не
# «прогон зелёный?» — прогон с падениями каденцию соблюдает, прогон без
# единого выполненного теста — нет. Адверсариальная батарея на уровне
# _has_executed_tests (DoD п.2): all-red, zero-tests, all-skipped,
# отсутствующий tc_results, битый tc_results, totals с мусором.

def test_has_executed_tests_all_red_counts():
    meta = {"tc_results": {"TC-109": "failed", "TC-110": "failed", "TC-111": "failed"},
            "totals": {"passed": 0, "failed": 3}}
    assert ss._has_executed_tests(meta) is True


def test_has_executed_tests_zero_tests_does_not_count():
    meta = {"totals": {"passed": 0, "failed": 0, "skipped": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_all_skipped_does_not_count():
    meta = {"tc_results": {"TC-109": "skipped", "TC-110": "skipped", "TC-111": "skipped"},
            "totals": {"passed": 0, "failed": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_missing_tc_results_falls_back_to_totals():
    meta = {"totals": {"passed": 3, "failed": 0}}
    assert ss._has_executed_tests(meta) is True


def test_has_executed_tests_malformed_tc_results_not_dict_falls_back():
    meta = {"tc_results": "oops", "totals": {"passed": 0, "failed": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_totals_garbage_is_false():
    meta = {"totals": {"passed": "banana", "failed": "oops"}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_totals_not_dict_is_false():
    meta = {"totals": "garbage"}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_no_fields_at_all_is_false():
    assert ss._has_executed_tests({}) is False


def test_compatibility_all_red_run_counts_as_cadence_met(repo):
    """Красная проба Б8: прогон с падениями каденцию СОБЛЮДАЕТ — красный
    уходит в триаж по своему SLA (run_needs_triage), дублировать его
    каденцией неправильно. До фикса ЭТОТ прогон уже был quiet (падения не
    мешали), пин остаётся регрессом на будущее."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0610", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: 0, failed: 3 }}\n"
                   f"tc_results:\n  TC-109: failed\n  TC-110: failed\n  TC-111: failed\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


def test_compatibility_zero_tests_does_not_meet_cadence(repo):
    """Красная проба Б8: totals все нули, tc_results отсутствует — ничего
    не выполнено, до фикса гасило детектор на полный порог."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0611", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: 0, failed: 0, skipped: 0 }}\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "выполненных тестов ноль" in text


def test_compatibility_all_skipped_does_not_meet_cadence(repo):
    """Красная проба Б8 (худший случай критика): tc_results TC-109/110/111
    все skipped, totals нулевые — падений нет, но и покрытия нет; до фикса
    это гасило детектор на полный порог (падений нет => Closed сразу =>
    триаж не запускается => покрытие нулевое при полной тишине)."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0612", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: 0, failed: 0, skipped: 3 }}\n"
                   f"tc_results:\n  TC-109: skipped\n  TC-110: skipped\n  TC-111: skipped\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "выполненных тестов ноль" in text


def test_compatibility_missing_tc_results_falls_back_to_totals(repo):
    """Адверсариальная батарея (DoD п.2): tc_results отсутствует вовсе,
    totals>0 — засчитывается по totals."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0613", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: 3, failed: 0 }}\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "compatibility_run_stale" not in _esc(repo)


def test_compatibility_malformed_tc_results_does_not_meet_cadence(repo):
    """Адверсариальная батарея: tc_results битый (не dict), totals пустые —
    не засчитывается, не роняется исключением."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0614", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"tc_results: garbage\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "выполненных тестов ноль" in text


def test_compatibility_totals_garbage_does_not_meet_cadence(repo):
    """Адверсариальная батарея: totals с нечисловым мусором — не роняется
    исключением, трактуется как «не доказано»."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0615", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: banana, failed: oops }}\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "выполненных тестов ноль" in text


# --- Б6 п.4 (критик-раунд 2): недатированный Closed compatibility RUN не
# должен молча выпадать из диагностики (`ts is None: continue` терял запись
# ДО регистрации diag-кандидата — сообщение лгало «нет ни одного», хотя
# файл существовал; живая форма дефекта — RUN-20260814-0605).

def test_compatibility_closed_but_undated_names_file_not_generic_nothing(repo):
    """Красная проба Б6 п.4: сообщение обязано называть файл, а не
    утверждать «нет ни одного»."""
    _quiet_neighbours(repo)
    p = repo.run("RUN-20260814-0605", "Closed",
                 extra="suite: compatibility\nmode: live\ndevice_avd: ao3_test_api29\n")
    text = p.read_text(encoding="utf-8").replace('updated: "2026-07-01T00:00:00Z"\n', "")
    p.write_text(text, encoding="utf-8")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    esc = _esc(repo)
    assert "[sla:compatibility_run_stale]" in esc
    assert "RUN-20260814-0605" in esc
    assert "нет ни одного" not in esc
    assert "нет штампа времени" in esc


def test_compatibility_no_run_and_no_undated_candidate_still_says_nothing(repo):
    """Регресс-пин: без каких-либо compatibility-прогонов вовсе (ни
    датированных, ни недатированных) сообщение остаётся «нет ни одного» —
    ветка diag_untimed_meta не сломала исходный fail-safe."""
    _quiet_neighbours(repo)
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    assert "нет ни одного" in _esc(repo)


# --- Б11 (критик-раунд 3, 2026-08-25): «более грубый оракул перекрывает
# более специфичный». `tc_results` — оракул ПО ИМЕНИ кейса, `totals` —
# безымянный счётчик всего прогона. Прежняя редакция, не найдя среди
# TC-109/110/111 ни одного passed/failed, МОЛЧА падала в `totals` — и отчёт,
# ЯВНО заявляющий «эти три не выполнялись», засчитывался каденцией из-за
# любого ЧУЖОГО пройденного теста. Правило: если tc_results — словарь и в нём
# ЕСТЬ хотя бы один из трёх ключей, решаем ТОЛЬКО по ним.

def test_has_executed_tests_all_skipped_with_foreign_totals_does_not_count():
    """КРАСНАЯ ПРОБА Б11 (юнит, проба критика дословно): три skipped +
    totals.passed=5 (чужие тесты). ДО фикса — True (падение в totals),
    ПОСЛЕ — False."""
    meta = {"tc_results": {"TC-109": "skipped", "TC-110": "skipped", "TC-111": "skipped"},
            "totals": {"passed": 5, "failed": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_partial_tc_results_skipped_with_foreign_totals():
    """Присутствует только ОДИН из трёх ключей и он skipped — решаем по нему,
    в totals не падаем (ключ есть => per-TC свидетельство существует)."""
    meta = {"tc_results": {"TC-110": "skipped"}, "totals": {"passed": 5, "failed": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_one_of_three_passed_counts():
    """Хотя бы один из ПРИСУТСТВУЮЩИХ ключей passed/failed — True."""
    meta = {"tc_results": {"TC-109": "skipped", "TC-110": "passed", "TC-111": "skipped"},
            "totals": {"passed": 0, "failed": 0}}
    assert ss._has_executed_tests(meta) is True


def test_has_executed_tests_tc_results_none_value_is_not_executed():
    """Ключ есть, значение пустое (`TC-109:` без значения → None) — ключ
    ПРИСУТСТВУЕТ, значит решаем по нему: не passed/failed → False, в totals
    не падаем."""
    meta = {"tc_results": {"TC-109": None}, "totals": {"passed": 5, "failed": 0}}
    assert ss._has_executed_tests(meta) is False


def test_has_executed_tests_foreign_tc_keys_only_falls_back_to_totals():
    """tc_results — словарь, но НИ ОДНОГО из трёх ключей в нём нет (чужие
    кейсы) — per-TC свидетельства о TC-109/110/111 нет вовсе, легальный
    фолбэк в totals сохранён."""
    meta = {"tc_results": {"TC-042": "passed"}, "totals": {"passed": 5, "failed": 0}}
    assert ss._has_executed_tests(meta) is True


def test_compatibility_all_skipped_with_foreign_totals_does_not_meet_cadence(repo):
    """КРАСНАЯ ПРОБА Б11 (end-to-end, проба критика дословно): отчёт заявляет
    TC-109/110/111 = skipped, но несёт totals.passed=5 чужих тестов. ДО фикса
    детектор каденции ГАС на полный порог (224ч) при нулевом покрытии
    compatibility; ПОСЛЕ — эскалация с причиной «выполненных тестов ноль»."""
    _quiet_neighbours(repo)
    repo.run("RUN-20260707-0616", "Closed",
             extra=f"suite: compatibility\n{VALID_MODE}{VALID_AVD}"
                   f"totals: {{ passed: 5, failed: 0 }}\n"
                   f"tc_results:\n  TC-109: skipped\n  TC-110: skipped\n  TC-111: skipped\n"
                   f"status_since: {FRESH}\n")
    _sla(repo, compatibility_run_stale=224)

    ss.sweep(now=NOW)

    text = _esc(repo)
    assert "[sla:compatibility_run_stale]" in text
    assert "выполненных тестов ноль" in text


# Битый ввод (9 форм, замер критика раунда 3 — «всё False, исключений нет»)
# ПЕРЕПРОГОН ПОСЛЕ правки Б11: приоритет tc_results не должен был сломать
# устойчивость к чужеформатным полям.
_MALFORMED_FORMS = [
    ("tc_results строкой, totals нет", {"tc_results": "oops"}),
    ("tc_results списком, totals нет", {"tc_results": ["TC-109"]}),
    ("totals строкой", {"totals": "garbage"}),
    ("totals списком", {"totals": [1, 2]}),
    ("totals None", {"totals": None}),
    ("totals нечисловые значения", {"totals": {"passed": "banana", "failed": "oops"}}),
    ("tc_results строкой + totals строкой", {"tc_results": "oops", "totals": "garbage"}),
    ("tc_results списком + totals None", {"tc_results": ["TC-109"], "totals": None}),
    ("tc_results пустой словарь + totals None", {"tc_results": {}, "totals": None}),
]


@pytest.mark.parametrize("label,meta", _MALFORMED_FORMS,
                         ids=[f[0] for f in _MALFORMED_FORMS])
def test_has_executed_tests_malformed_input_battery(label, meta):
    assert ss._has_executed_tests(meta) is False, label


def test_dry_run_writes_nothing(repo):
    repo.bug("BUG-021", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)

    report = ss.sweep(now=NOW, dry=True)

    assert any("[ESC+]" in r for r in report)
    assert not (repo.root / "state" / "escalations.md").exists()
    assert not (repo.root / "state" / "orchestrator-log.md").exists()
