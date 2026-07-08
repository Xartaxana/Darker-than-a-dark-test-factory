"""Юнит-тесты проекции frontmatter `lock` на assignee/labels борды (board_sync.build()).

Варианты (спека владельца, минимально инвазивный, БЕЗ изменения частоты сборки):
1. lock="<agent>:<ISO-timestamp>" -> assignee=<agent>, label "wip:<agent>".
2. lock="<значение без двоеточия>" (ручной лок человека) -> assignee=<значение>,
   label "wip:<значение>".
3. lock пуст/отсутствует -> assignee="qa-agents", без wip-label (как раньше).

Тесты работают в tmp_path-репо (фикстура `repo` из conftest.py), реальные
test-cases/bugs/runs не затрагиваются. Запуск:
    python -m pytest scripts/tests -q
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

import board_sync as bs

# Матрицу и схемы парсим здесь НЕЗАВИСИМО от board_sync._load_transitions_matrix —
# это и есть защита от разъезда (если реализация где-то ошибётся в фильтрации/
# развороте "*", тест это поймает, а не будет сверяться сам с собой).
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def _expected_board_transition_pairs() -> dict[str, set[tuple[str, str]]]:
    matrix = yaml.safe_load((SCHEMAS_DIR / "transitions.yaml").read_text(encoding="utf-8"))
    expected: dict[str, set[tuple[str, str]]] = {}
    for machine_key in ("test-case", "bug", "run"):
        machine = matrix["machines"][machine_key]
        statuses = machine["statuses"]
        pairs: set[tuple[str, str]] = set()
        for t in machine["transitions"]:
            if not t.get("via_board"):
                continue
            to = t["to"]
            frm = t["from"]
            froms = [s for s in statuses if s != to] if frm == "*" else [frm]
            pairs.update((f, to) for f in froms)
        expected[machine_key] = pairs
    return expected


def _issue_index(key: str) -> dict:
    index = json.loads((bs.BOARD / ".trackstate" / "index" / "issues.json").read_text(encoding="utf-8"))
    return next(i for i in index if i["key"] == key)


def _main_md(key: str) -> str:
    return (bs.BOARD / key / "main.md").read_text(encoding="utf-8")


def test_lock_agent_colon_timestamp_projects_agent(repo):
    """lock="test-automator:2026-07-07T19:49:14Z" -> assignee=test-automator, label wip:test-automator."""
    repo.test_case("TC-300", "Approved", lock="test-automator:2026-07-07T19:49:14Z")

    bs.build()

    card = _main_md("TC-300")
    assert 'assignee: "test-automator"' in card
    assert "wip:test-automator" in card

    entry = _issue_index("TC-300")
    assert entry["assignee"] == "test-automator"
    assert "wip:test-automator" in entry["labels"]


def test_lock_manual_no_colon_projects_whole_value(repo):
    """lock="wip" (ручной лок человека, без двоеточия) -> assignee="wip", label "wip:wip"."""
    repo.bug("BUG-300", "Open", lock="wip")

    bs.build()

    card = _main_md("BUG-300")
    assert 'assignee: "wip"' in card
    assert "wip:wip" in card

    entry = _issue_index("BUG-300")
    assert entry["assignee"] == "wip"
    assert "wip:wip" in entry["labels"]


def test_empty_lock_keeps_default_assignee_no_label(repo):
    """lock пуст -> assignee="qa-agents", без wip-label (текущее поведение не сломано)."""
    repo.test_case("TC-301", "Draft", lock="")

    bs.build()

    card = _main_md("TC-301")
    assert 'assignee: "qa-agents"' in card
    assert "wip:" not in card

    entry = _issue_index("TC-301")
    assert entry["assignee"] == "qa-agents"
    assert not any(lbl.startswith("wip:") for lbl in entry["labels"])


def test_no_lock_field_at_all_keeps_default_assignee(repo):
    """Артефакт без поля lock вовсе (legacy) -> assignee="qa-agents", без wip-label."""
    repo.run("RUN-300", "NeedsTriage")  # conftest.Repo.run пишет lock: "" всегда, но
    # проверим ещё и полное отсутствие поля через test_case с lock=None (без строки в YAML).
    repo.test_case("TC-302", "Draft", lock=None)

    bs.build()

    entry_run = _issue_index("RUN-300")
    assert entry_run["assignee"] == "qa-agents"

    entry_tc = _issue_index("TC-302")
    assert entry_tc["assignee"] == "qa-agents"
    assert not any(lbl.startswith("wip:") for lbl in entry_tc["labels"])


# --- паритет борды со schemas/transitions.yaml (колонки и кнопки-переходы) ---

def test_board_transitions_generated_from_matrix_via_board():
    """Кнопки каждого воркфлоу == множеству via_board-переходов матрицы (5a).

    Матрица парсится тестом независимо (см. _expected_board_transition_pairs) —
    так регрессия внутри board_sync._board_transitions_for_machine не спрячется
    за тем, что тест и реализация читают одно и то же одинаково неправильно."""
    expected = _expected_board_transition_pairs()
    cfg = bs._workflows_config()
    machine_by_workflow = {"test-workflow": "test-case", "bug-workflow": "bug", "run-workflow": "run"}
    for wf_id, machine_key in machine_by_workflow.items():
        actual_pairs = {(t["from"], t["to"]) for t in cfg[wf_id]["transitions"]}
        assert actual_pairs == expected[machine_key], f"{wf_id}: {actual_pairs} != {expected[machine_key]}"


def test_board_transitions_expected_shapes():
    """Явный ожидаемый результат из спеки — читаемая регрессия сверх паритета выше."""
    cfg = bs._workflows_config()

    tc_pairs = {(t["from"], t["to"]) for t in cfg["test-workflow"]["transitions"]}
    assert tc_pairs == {
        ("Draft", "Approved"), ("Review", "Approved"),
        ("Draft", "Review"), ("Approved", "Review"), ("Automated", "Review"), ("Blocked", "Review"),
    }

    bug_pairs = {(t["from"], t["to"]) for t in cfg["bug-workflow"]["transitions"]}
    assert bug_pairs == {
        ("Open", "Fixed"), ("Open", "Rejected"), ("Open", "Intended"), ("Open", "Blocked"),
        ("Reopened", "Fixed"), ("Reopened", "Rejected"), ("Reopened", "Intended"), ("Reopened", "Blocked"),
        ("Reopened", "Open"), ("Fixed", "Open"), ("Verified", "Open"), ("Rejected", "Open"),
        ("Intended", "Open"), ("Blocked", "Open"),
    }

    assert cfg["run-workflow"]["transitions"] == []


def test_transition_ids_deterministic_and_unique():
    cfg = bs._workflows_config()
    for wf_id, wf in cfg.items():
        ids = [t["id"] for t in wf["transitions"]]
        assert len(ids) == len(set(ids)), f"{wf_id}: дублирующиеся id переходов {ids}"


# --- 5b: каждый статус из enum'ов schemas/*.schema.yaml маппится в STATUS_MAP ---

def test_every_schema_status_enum_value_has_board_mapping():
    """Поймало бы регрессию Blocked (был в enum'ах, отсутствовал в STATUS_MAP)."""
    for itype, schema_file in (("test-case", "test-case"), ("bug", "bug"), ("run", "run")):
        schema = yaml.safe_load((SCHEMAS_DIR / f"{schema_file}.schema.yaml").read_text(encoding="utf-8"))
        enum = set(schema["fields"]["status"]["enum"])
        mapped = set(bs.STATUS_MAP[itype].keys())
        assert enum <= mapped, f"{itype}: немаппящиеся статусы {enum - mapped}"


# --- 5c: Blocked-кейс/Blocked-ран попадают в свои колонки ---------------------

def test_blocked_test_case_lands_in_blocked_column(repo):
    repo.test_case("TC-400", "Blocked")
    bs.build()
    assert _issue_index("TC-400")["status"] == "tc-blocked"


def test_blocked_run_lands_in_blocked_column(repo):
    repo.run("RUN-400", "Blocked")
    bs.build()
    assert _issue_index("RUN-400")["status"] == "run-blocked"


# --- 5d: warning-фолбэк на неизвестном статусе --------------------------------

def test_unknown_status_prints_warning_and_falls_back(repo, capsys):
    repo.bug("BUG-400", "TotallyUnknownStatus")
    bs.build()

    out = capsys.readouterr().out
    assert "BUG-400" in out
    assert "TotallyUnknownStatus" in out
    assert "WARN" in out

    fallback_status_str = next(iter(bs.STATUS_MAP["bug"]))
    assert _issue_index("BUG-400")["status"] == bs.STATUS_MAP["bug"][fallback_status_str]


def test_known_status_does_not_warn(repo, capsys):
    repo.bug("BUG-401", "Open")
    bs.build()
    out = capsys.readouterr().out
    assert "WARN" not in out


# --- 5e: labels automation:/review: для невидимых машин на test-case ---------

def test_automation_status_label(repo):
    repo.test_case("TC-401", "Automated", extra="automation_status: active\n")
    bs.build()
    assert "automation:active" in _issue_index("TC-401")["labels"]


def test_review_changes_requested_label(repo):
    repo.test_case("TC-402", "Approved", extra="review: changes_requested\n")
    bs.build()
    assert "review:changes_requested" in _issue_index("TC-402")["labels"]


def test_no_automation_or_review_fields_no_extra_labels(repo):
    repo.test_case("TC-403", "Draft")
    bs.build()
    labels = _issue_index("TC-403")["labels"]
    assert not any(lbl.startswith("automation:") for lbl in labels)
    assert not any(lbl.startswith("review:") for lbl in labels)


# --- производная колонка "Awaiting Review" (F1: Approved + automated_by) -----
#
# Чисто проекция борды: статусная машина test-case (schemas/) не меняется,
# "tc-awaiting-review" НЕ входит в STATUS_MAP — вот это и проверяем ниже.

def test_board_status_for_approved_with_automated_by():
    meta = {"status": "Approved", "automated_by": "framework/tests/test_x.py::test_y"}
    assert bs._board_status_for("test-case", meta) == "tc-awaiting-review"


def test_board_status_for_approved_without_automated_by():
    meta = {"status": "Approved"}
    assert bs._board_status_for("test-case", meta) is None
    meta_blank = {"status": "Approved", "automated_by": ""}
    assert bs._board_status_for("test-case", meta_blank) is None


def test_board_status_for_ignores_non_test_case():
    meta = {"status": "Approved", "automated_by": "x"}
    assert bs._board_status_for("bug", meta) is None
    assert bs._board_status_for("run", meta) is None


def test_awaiting_review_not_in_status_map():
    """Не добавлено в STATUS_MAP — чисто проекция, статусная машина не менялась."""
    assert "tc-awaiting-review" not in bs.STATUS_MAP["test-case"].values()
    assert "Awaiting Review" not in bs.STATUS_MAP["test-case"]


def test_approved_with_automated_by_lands_in_awaiting_review_column(repo):
    """(5a) Approved + automated_by -> колонка tc-awaiting-review в build()."""
    repo.test_case("TC-410", "Approved", extra='automated_by: "framework/tests/test_x.py::test_y"\n')
    bs.build()
    assert _issue_index("TC-410")["status"] == "tc-awaiting-review"


def test_approved_without_automated_by_stays_in_approved_column(repo):
    """(5b) Approved без automated_by -> обычная колонка tc-approved."""
    repo.test_case("TC-411", "Approved")
    bs.build()
    assert _issue_index("TC-411")["status"] == "tc-approved"


def test_automated_status_unaffected_by_derived_column(repo):
    """(5c) status: Automated -> tc-automated как раньше (даже если automated_by заполнен)."""
    repo.test_case("TC-412", "Automated", extra='automated_by: "framework/tests/test_x.py::test_y"\n')
    bs.build()
    assert _issue_index("TC-412")["status"] == "tc-automated"


def test_changes_requested_stays_in_awaiting_review_column(repo):
    """Approved + automated_by + review: changes_requested — тот же F1-цикл ревью,
    остаётся в Awaiting Review (не отдельная колонка); label различает подслучай."""
    repo.test_case("TC-413", "Approved",
                    extra='automated_by: "framework/tests/test_x.py::test_y"\nreview: changes_requested\n')
    bs.build()
    entry = _issue_index("TC-413")
    assert entry["status"] == "tc-awaiting-review"
    assert "review:changes_requested" in entry["labels"]


def test_awaiting_review_in_statuses_and_workflow_columns():
    assert any(sid == "tc-awaiting-review" for sid, _, _ in bs.STATUSES)
    cols = bs.WORKFLOWS["test-workflow"]["statuses"]
    assert cols.index("tc-approved") < cols.index("tc-awaiting-review") < cols.index("tc-automated")


def test_awaiting_review_has_no_board_transitions():
    """Кнопок переходов к ней не генерируется — её нет в матрице (не в schemas/)."""
    cfg = bs._workflows_config()
    targets = {t["to"] for t in cfg["test-workflow"]["transitions"]}
    sources = {t["from"] for t in cfg["test-workflow"]["transitions"]}
    assert "tc-awaiting-review" not in targets
    assert "tc-awaiting-review" not in sources
