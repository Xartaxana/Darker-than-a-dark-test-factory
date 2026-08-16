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


BLOCKED_REASON_ENUM = {"environment", "missing_fixture", "product_decision", "dev_answer",
                       "permissions"}


def test_blocked_reason_field_on_every_machine_with_blocked():
    """B5: любой тип, у которого в статусной машине есть Blocked, должен уметь
    объяснить причину — одинаковый enum во всех трёх схемах."""
    for itype in ("bug", "test-case", "run"):
        assert "Blocked" in tr.statuses(itype), itype
        schema = yaml.safe_load((SCHEMAS / f"{itype}.schema.yaml").read_text(encoding="utf-8"))
        assert set(schema["fields"]["blocked_reason"]["enum"]) == BLOCKED_REASON_ENUM, itype


def test_bug_schema_has_resolution_and_known_issue_fields():
    """B1/B2: поля недостающих веток workflow присутствуют в схеме бага."""
    schema = yaml.safe_load((SCHEMAS / "bug.schema.yaml").read_text(encoding="utf-8"))
    fields = schema["fields"]
    assert set(fields["resolution"]["enum"]) == {"accepted_risk", "wontfix"}
    assert "resolution_comment" in fields
    assert set(fields["known_issue"]["enum"]) == {"true", "false"}


# --- B3: машина automation (lifecycle автотеста) -----------------------------

def test_automation_machine_matches_tc_schema_enum():
    """Статусы машины automation == enum поля automation_status в схеме TC."""
    schema = yaml.safe_load((SCHEMAS / "test-case.schema.yaml").read_text(encoding="utf-8"))
    assert set(schema["fields"]["automation_status"]["enum"]) == set(tr.statuses("automation"))


# --- E5: машина charter (автозаведение exploratory-чартеров) ----------------

def test_charter_statuses_match_schema_enum():
    """Статусы машины charter == enum поля status в charter.schema.yaml.

    Не добавлена в test_statuses_match_schema_enums (bug/test-case/run) —
    та функция ЗАОДНО требует совпадающий enum blocked_reason
    (test_blocked_reason_field_on_every_machine_with_blocked), а charter.schema.yaml
    его не несёт (не входит в эту спеку); паритет статусов проверяем отдельно,
    по образцу test_automation_machine_matches_tc_schema_enum."""
    schema = yaml.safe_load((SCHEMAS / "charter.schema.yaml").read_text(encoding="utf-8"))
    assert set(schema["fields"]["status"]["enum"]) == set(tr.statuses("charter"))


def test_charter_actors_in_factory_group():
    """exploratory-tester (пробел, закрыт заодно) и charter-designer — в
    группе factory: оба фигурируют акторами переходов машины charter."""
    assert tr.is_allowed("charter", "Planned", "InProgress", "exploratory-tester")
    assert tr.is_allowed("charter", "InProgress", "Done", "exploratory-tester")


def test_charter_proposed_to_planned_gate():
    """Proposed→Planned — критик-на-план: только human/qa-loop, эффект
    plan_review_required."""
    assert tr.is_allowed("charter", "Proposed", "Planned", "human")
    assert tr.is_allowed("charter", "Proposed", "Planned", "qa-loop")
    assert not tr.is_allowed("charter", "Proposed", "Planned", "exploratory-tester")
    assert not tr.is_allowed("charter", "Proposed", "Planned", "charter-designer")
    assert "plan_review_required" in tr.effects_for("charter", "Proposed", "Planned")


def test_charter_initial_has_both_entry_points():
    """Прежний прямой путь (Planned) остаётся легальным рядом с новым (Proposed)."""
    assert set((yaml.safe_load(
        (SCHEMAS / "transitions.yaml").read_text(encoding="utf-8"))
        ["machines"]["charter"]["initial"])) == {"Proposed", "Planned"}


def test_charter_blocked_from_anywhere_by_factory_with_escalation():
    for frm in ("Proposed", "Planned", "InProgress"):
        assert tr.is_allowed("charter", frm, "Blocked", "sla_sweep"), frm
    assert not tr.is_allowed("charter", "Planned", "Blocked", "mallory")
    assert "escalation" in tr.effects_for("charter", "Planned", "Blocked")


def test_charter_blocked_to_planned_only_human():
    assert tr.is_allowed("charter", "Blocked", "Planned", "human")
    assert not tr.is_allowed("charter", "Blocked", "Planned", "exploratory-tester")
    assert not tr.is_allowed("charter", "Blocked", "Planned", "charter-designer")


def test_charter_done_is_terminal_no_factory_exit():
    """Из терминального Done фабрика не выводит форвард-переходами (те же
    границы, что и у машин bug/test-case/run: validate() проверяет это только
    для явных `from: <term>`, а не для `from: "*"` — эскалационный `"*" ->
    Blocked` намеренно легален из ЛЮБОГО статуса, включая терминальный, во
    всех машинах этой матрицы; здесь не переизобретаем это, проверяем только
    forward-переходы)."""
    for actor in ("exploratory-tester", "charter-designer", "sla_sweep", "qa-loop"):
        for to in ("Proposed", "Planned", "InProgress"):
            assert not tr.is_allowed("charter", "Done", to, actor), (actor, to)


def test_quarantine_actors_and_effects():
    """Карантинит триаж/маинтейнер; выводит из карантина ТОЛЬКО test-maintainer."""
    assert tr.is_allowed("automation", "active", "quarantined", "failure-analyst")
    assert tr.is_allowed("automation", "active", "quarantined", "test-maintainer")
    assert not tr.is_allowed("automation", "active", "quarantined", "test-automator")
    assert tr.is_allowed("automation", "quarantined", "active", "test-maintainer")
    assert not tr.is_allowed("automation", "quarantined", "active", "failure-analyst")
    # Вход в карантин обязан заполнить quarantine_*-поля (надзор sla_sweep).
    assert "quarantine_fields" in tr.effects_for("automation", "active", "quarantined")


def test_red_probe_needs_maintenance_actors():
    """Красная проба (red-probe-only, 2026-07-17): test-reviewer легально ставит
    active -> needs_maintenance («тест не умеет падать»), но выводит из
    needs_maintenance по-прежнему ТОЛЬКО test-maintainer (инвариант B3)."""
    assert tr.is_allowed("automation", "active", "needs_maintenance", "test-reviewer")
    assert tr.is_allowed("automation", "active", "needs_maintenance", "failure-analyst")
    assert not tr.is_allowed("automation", "active", "needs_maintenance", "test-automator")
    assert tr.is_allowed("automation", "needs_maintenance", "active", "test-maintainer")
    assert not tr.is_allowed("automation", "needs_maintenance", "active", "test-reviewer")


def test_deprecated_is_human_or_strategist_retired_is_terminal():
    assert tr.is_allowed("automation", "active", "deprecated", "human")
    assert tr.is_allowed("automation", "quarantined", "deprecated", "test-strategist")
    assert not tr.is_allowed("automation", "active", "deprecated", "test-maintainer")
    # Из терминального retired фабрика не выводит.
    for actor in ("test-maintainer", "test-automator", "qa-loop"):
        for to in ("active", "quarantined", "deprecated"):
            assert not tr.is_allowed("automation", "retired", to, actor), (actor, to)


# --- F1: гейт ревью нового автотеста ------------------------------------------

def test_review_gate_only_reviewer_automates():
    """Approved→Automated переводит ТОЛЬКО test-reviewer; автор (automator) — нет."""
    assert tr.is_allowed("test-case", "Approved", "Automated", "test-reviewer")
    assert not tr.is_allowed("test-case", "Approved", "Automated", "test-automator")
    assert not tr.is_allowed("test-case", "Approved", "Automated", "human")
    assert "automated_by_required" in tr.effects_for("test-case", "Approved", "Automated")


def test_review_field_in_tc_schema():
    schema = yaml.safe_load((SCHEMAS / "test-case.schema.yaml").read_text(encoding="utf-8"))
    assert schema["fields"]["review"]["enum"] == ["changes_requested"]


# --- B4: guard-переходы test_debt --------------------------------------------

def test_test_debt_guard_lets_factory_fix():
    """Долг фреймворка чинит фабрика, но ТОЛЬКО при type: test_debt в meta."""
    debt = {"type": "test_debt"}
    assert tr.is_allowed("bug", "Open", "Fixed", "test-maintainer", meta=debt)
    assert tr.is_allowed("bug", "Reopened", "Fixed", "test-automator", meta=debt)
    # Без meta (консервативно) и для app_bug — по-прежнему только человек.
    assert not tr.is_allowed("bug", "Open", "Fixed", "test-maintainer")
    assert not tr.is_allowed("bug", "Open", "Fixed", "test-maintainer",
                             meta={"type": "app_bug"})
    assert not tr.is_allowed("bug", "Open", "Fixed", "fix-verifier", meta=debt)
    # Человеку guard не мешает (его переход без guard'а).
    assert tr.is_allowed("bug", "Open", "Fixed", "human", meta=debt)


# --- M-D/E3 (spec-build-source-dual-mode v4): второй канал via_gitlab ------

def test_open_to_fixed_by_human_carries_via_gitlab_flag():
    """(C11/E3): флаг-сиблинг via_gitlab: true на строке Open->Fixed by human
    — МЕНЯЕТ машинную матрицу (не просто аннотация в ref); актор остаётся
    human (проводник — gitlab_inbound.py, тот же человек-разработчик)."""
    matrix = yaml.safe_load((SCHEMAS / "transitions.yaml").read_text(encoding="utf-8"))
    transitions = matrix["machines"]["bug"]["transitions"]
    t = next(x for x in transitions if x["from"] == "Open" and x["to"] == "Fixed"
             and x.get("by") == ["human"])
    assert t.get("via_gitlab") is True
    assert t.get("via_board") is True   # оба канала на одной строке


def test_reopened_to_fixed_by_human_also_carries_via_gitlab_flag():
    """(B3, критик-раунд 2026-08-10): код M-D флипает Open->Fixed И
    Reopened->Fixed одинаково (process_label_events принимает status ∈
    {Open, Reopened}) — матрица обязана описывать ОБА перехода, не только
    Open->Fixed."""
    matrix = yaml.safe_load((SCHEMAS / "transitions.yaml").read_text(encoding="utf-8"))
    transitions = matrix["machines"]["bug"]["transitions"]
    t = next(x for x in transitions if x["from"] == "Reopened" and x["to"] == "Fixed"
             and x.get("by") == ["human"])
    assert t.get("via_gitlab") is True
    assert t.get("via_board") is True


def test_gitlab_inbound_registered_in_factory_actor_group():
    """gitlab_inbound — новый актор группы factory (проводник второго
    канала M-D); validate() обязан знать его (иначе неизвестный актор был
    бы найден чеком целостности)."""
    matrix = yaml.safe_load((SCHEMAS / "transitions.yaml").read_text(encoding="utf-8"))
    assert "gitlab_inbound" in matrix["actors"]["groups"]["factory"]


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
    # B3: у машины автотеста переходов с борды нет — судьбой автотеста управляет
    # фабрика (человек решает только deprecated, и это правка frontmatter, не борда).
    "automation": {},
    # E5: у машины charter переходов с борды тоже нет — charter'ами борда не
    # управляет (exploratory-charters/ не в bs._iter_artifacts()/board_inbound).
    "charter": {},
}


def test_board_whitelist_parity_with_legacy_literal():
    assert tr.board_whitelist() == LEGACY_WHITELIST
    assert bi.WHITELIST == LEGACY_WHITELIST      # board_inbound берёт из матрицы


def test_run_has_no_board_transitions():
    assert tr.board_whitelist()["run"] == {}


# --- П1 Р0 п.3 (spec-p1-dedup v7, r4-r7): from_terminal + Merged --------------

def test_test_case_terminal_is_merged():
    assert tr.terminal("test-case") == {"Merged"}


def test_wildcard_without_flag_does_not_revive_terminal():
    """«* без флага не оживляет терминальный»: test-case `*`→Review НЕ несёт
    from_terminal — с Merged (терминал) он не матчит ни для одного актора без
    явного правила. test-automator не входит в акторы явного rollback-перехода
    Merged→Review — изолирует именно wildcard-гейт (не путать с рестором ниже)."""
    assert not tr.is_allowed("test-case", "Merged", "Review", "test-automator")
    assert not tr.is_allowed("test-case", "Merged", "Review", "test-maintainer")
    assert not tr.is_allowed("test-case", "Merged", "Review", "sla_sweep")


def test_factory_never_exits_merged():
    """«фабрика не выводит из Merged»: is_allowed по ВСЕМ фабричным акторам и
    ВСЕМ статусам test-case из Merged — пусто. Правило test-case `*`→Blocked
    несёт from_terminal: false намеренно (r6/r7) — фабрика эскалирует Merged-
    конфликт БЕЗ смены статуса (board_inbound.apply_conflict), не переходом."""
    factory = sorted((yaml.safe_load(
        (SCHEMAS / "transitions.yaml").read_text(encoding="utf-8"))
        ["actors"]["groups"]["factory"]))
    for actor in factory:
        for to in tr.statuses("test-case"):
            if to == "Merged":
                continue
            assert not tr.is_allowed("test-case", "Merged", to, actor), (actor, to)


def test_bug_verified_to_open_still_allowed_by_human_after_terminal_fix():
    """«Verified→Open человеком жив» — позитивный пин к from_terminal: true на
    bug `*`→Open (Verified — терминал bug, у него нет отдельного правила ИЗ
    Verified, только это *-правило)."""
    assert tr.is_allowed("bug", "Verified", "Open", "human")
    assert not tr.is_allowed("bug", "Verified", "Open", "fix-verifier")


def test_automation_retired_to_deprecated_human_strategist_still_allowed():
    """«retired→deprecated human/strategist жив» — позитив к
    test_deprecated_is_human_or_strategist_retired_is_terminal (:149-156):
    from_terminal: true на automation `*`→deprecated сохраняет прежнюю
    (уже легальную ДО фикса терминальности) семантику."""
    assert tr.is_allowed("automation", "retired", "deprecated", "human")
    assert tr.is_allowed("automation", "retired", "deprecated", "test-strategist")
    assert not tr.is_allowed("automation", "retired", "deprecated", "test-maintainer")


def test_merged_rollback_to_review_is_allowed_for_human_and_lead():
    """«откат rollback жив» — явный переход Merged→Review (rollback: true, БЕЗ
    via_board) матчит НЕЗАВИСИМО от from_terminal (флаг гейтит только
    "*"-правила, явный терминальный from — всегда)."""
    assert tr.is_allowed("test-case", "Merged", "Review", "human")
    assert tr.is_allowed("test-case", "Merged", "Review", "lead")
    assert not tr.is_allowed("test-case", "Merged", "Review", "test-automator")


def test_merged_to_review_not_in_board_whitelist():
    """Rollback БЕЗ via_board (r5) — Merged не попадает в board_whitelist,
    LEGACY_WHITELIST выше остаётся неизменным (паритет-тест
    test_board_whitelist_parity_with_legacy_literal уже это покрывает целиком;
    здесь — прицельная проверка на самом Merged-ключе)."""
    wl = tr.board_whitelist()["test-case"]
    assert "Merged" not in wl
    assert "Merged" not in wl.get("*", set())


def test_board_allowed_direct_merged_and_verified():
    """Прямые юниты на board_allowed() (не только через board_inbound.classify()):
    Merged-src отклонён (терминал без флага на *->Review), Verified-src (bug)
    принят (флаг from_terminal: true)."""
    assert not tr.board_allowed("test-case", "Merged", "Review")
    assert tr.board_allowed("bug", "Verified", "Open")
    assert not tr.board_allowed("bug", "Open", "Open")   # петля


def test_board_allowed_ignores_meta_signature():
    """board_allowed() не принимает meta вовсе (в отличие от is_allowed) —
    семантика board_whitelist(): guard-переходы (test_debt) существуют
    ПАРАЛЛЕЛЬНО обычному human-правилу (bug Open→Fixed несёт ОБА — human
    via_board:true и test-maintainer/test-automator guard:test_debt БЕЗ
    via_board); board_allowed находит человеческое via_board-правило
    независимо от guard-варианта, не падая на отсутствии meta."""
    assert tr.board_allowed("bug", "Open", "Fixed")


def test_merged_transitions_require_human_or_lead():
    assert tr.is_allowed("test-case", "Automated", "Merged", "human")
    assert tr.is_allowed("test-case", "Automated", "Merged", "lead")
    assert tr.is_allowed("test-case", "Approved", "Merged", "human")
    assert tr.is_allowed("test-case", "Approved", "Merged", "lead")
    assert not tr.is_allowed("test-case", "Automated", "Merged", "test-automator")
    assert not tr.is_allowed("test-case", "Automated", "Merged", "test-reviewer")


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
