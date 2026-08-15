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


def test_dry_run_writes_nothing(repo):
    repo.bug("BUG-021", "Open", extra=f"status_since: {OLD}\n")
    _sla(repo)

    report = ss.sweep(now=NOW, dry=True)

    assert any("[ESC+]" in r for r in report)
    assert not (repo.root / "state" / "escalations.md").exists()
    assert not (repo.root / "state" / "orchestrator-log.md").exists()
