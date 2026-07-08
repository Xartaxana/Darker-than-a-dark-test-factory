"""Тесты scripts/log_append.py — каноничное добавление строк в журналы."""
from __future__ import annotations

import json

import pytest

import log_append as la


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    routing = tmp_path / "logs" / "routing-log.jsonl"
    orch = tmp_path / "state" / "orchestrator-log.md"
    monkeypatch.setattr(la, "ROUTING_LOG", routing, raising=True)
    monkeypatch.setattr(la, "ORCH_LOG", orch, raising=True)
    return routing, orch


def test_routing_appends_json_line_with_ts(logs):
    routing, _ = logs
    la.main(["routing", "--event", "delegated", "--agent", "builder",
             "--model", "sonnet", "--category", "implementation",
             "--notes", "тест"])
    lines = routing.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event"] == "delegated"
    assert rec["agent"] == "builder"
    assert rec["model"] == "sonnet"
    assert rec["notes"] == "тест"
    assert rec["ts"].startswith("20") and "T" in rec["ts"]


def test_routing_model_required_for_delegated_escalated_accepted_rejected(logs):
    routing, _ = logs
    for event in ("delegated", "escalated", "accepted", "rejected"):
        with pytest.raises(SystemExit):
            la.append_routing(event, "builder")
    assert not routing.exists()


def test_routing_model_optional_for_other_events(logs):
    routing, _ = logs
    la.append_routing("lead_degraded", "lead", notes="лимит подписки")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "lead_degraded"
    assert "model" not in rec


def test_routing_events_match_claude_md_policy(logs):
    # CLAUDE.md «Журнал маршрутизации»: полный список событий политики.
    # Расхождение = скрипт молча отклоняет легитимное событие (прецедент:
    # dispatch_skipped, 2026-07-08).
    assert la.ROUTING_EVENTS == {
        "delegated", "accepted", "rejected", "escalated", "decomposable",
        "dispatch_skipped", "defect_found", "lead_degraded", "lead_restored",
    }


def test_routing_accepts_defect_found_without_model(logs):
    # D-0052 OS-репо: defect_found ссылается на исходный accepted;
    # model не требуется — её несёт исходное событие диспатча.
    routing, _ = logs
    la.append_routing("defect_found", "builder", category="implementation",
                      notes="что сломалось + ссылка на accepted <ts>")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "defect_found"
    assert "model" not in rec


def test_routing_accepts_dispatch_skipped_without_model(logs):
    routing, _ = logs
    la.append_routing("dispatch_skipped", "scout", category="recon",
                      notes="точечная сверка известных файлов")
    rec = json.loads(routing.read_text(encoding="utf-8"))
    assert rec["event"] == "dispatch_skipped"
    assert rec["agent"] == "scout"


def test_routing_rejects_unknown_event(logs):
    with pytest.raises(SystemExit):
        la.append_routing("started", "builder", model="sonnet")


def test_routing_appends_not_overwrites(logs):
    routing, _ = logs
    la.append_routing("delegated", "builder", model="sonnet")
    la.append_routing("accepted", "builder", model="sonnet")
    assert len(routing.read_text(encoding="utf-8").splitlines()) == 2


def test_orchestrator_row_format(logs):
    _, orch = logs
    la.main(["orchestrator", "Правило X", "test-automator", "TC-050", "OK: готово"])
    line = orch.read_text(encoding="utf-8").splitlines()[-1]
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert len(cells) == 5
    assert cells[0].endswith("Z")
    assert cells[1:] == ["Правило X", "test-automator", "TC-050", "OK: готово"]


def test_orchestrator_escapes_pipes_and_newlines(logs):
    _, orch = logs
    la.append_orchestrator(["a|b", "агент", "х", "строка\nдве"])
    line = orch.read_text(encoding="utf-8").splitlines()[-1]
    assert "a\\|b" in line
    assert "\nдве" not in line and "строка две" in line


def test_orchestrator_requires_exactly_four_cells(logs):
    with pytest.raises(SystemExit):
        la.append_orchestrator(["только", "три", "ячейки"])
