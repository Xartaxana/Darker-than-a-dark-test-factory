"""Тесты scripts/mechanism_gate.py — осевой гейт D-0055 (твин OS-репо)."""
from __future__ import annotations

import mechanism_gate as mg

MAP_SAMPLE = "## Ось 1 — Деплои\n## Ось 3 — Роли\n## Ось 6 — Внутренние оси\n"


def test_parse_axes_follows_the_map_not_a_constant():
    assert mg.parse_axes(MAP_SAMPLE) == [1, 3, 6]
    assert mg.parse_axes("") == []


def test_mechanism_paths_filters_ao3_prefixes_with_boundary():
    staged = ["CLAUDE.md", ".claude/agents/scout.md",
              ".claude/skills/qa-loop/SKILL.md", "schemas/agent-output.json",
              "state/rules.yaml", "scripts/log_append.py", "framework/conftest.py"]
    assert mg.mechanism_paths(staged) == [
        "CLAUDE.md", ".claude/agents/scout.md", ".claude/skills/qa-loop/SKILL.md",
        "schemas/agent-output.json", "state/rules.yaml"]
    # F-D: файловые префиксы матчатся точно.
    assert mg.mechanism_paths(["CLAUDE.md.bak", "state/rules.yaml.orig"]) == []
    # D-0065 OS-репо: самозащита цепочки; прочие scripts/ вне (D-0055).
    assert mg.mechanism_paths(["scripts/mechanism_gate.py",
                               ".githooks/commit-msg"]) == [
        "scripts/mechanism_gate.py", ".githooks/commit-msg"]
    assert mg.mechanism_paths(["scripts/board_sync.py"]) == []


def test_decide_skip_and_block_only_from_commit_message():
    # F-A: в твине нет DECISIONS_FULL — и блок, и отказ только из сообщения.
    code, _ = mg.decide("feat: X\n\nось 1: покрыта\nось 3: н-п (ролей не трогает)\n"
                        "ось 6: покрыта — schemas тем же коммитом",
                        ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 1 and "1, 3, 6" in reason
    code, _ = mg.decide("docs: опечатка\n\nоси: не-механизм (опечатка)",
                        ["CLAUDE.md"], MAP_SAMPLE)
    assert code == 0


def test_decide_merge_and_non_mechanism_pass_and_fail_closed():
    code, _ = mg.decide("Merge branch 'x'", ["CLAUDE.md"], MAP_SAMPLE, merging=True)
    assert code == 0
    code, _ = mg.decide("chore: тесты", ["framework/conftest.py"], MAP_SAMPLE)
    assert code == 0
    code, reason = mg.decide("feat: X", ["CLAUDE.md"], None)
    assert code == 1 and "fail-closed" in reason


def test_prose_is_not_an_answer():
    assert mg.find_missing("все оси покрыты", [1, 3]) == [1, 3]
