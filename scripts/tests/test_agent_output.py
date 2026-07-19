"""Юнит-тесты парсера agent_output (F2)."""
from __future__ import annotations

import agent_output as ao

GOOD = """Готово, кейс автоматизирован, 3 зелёных прогона.

```yaml
agent_output:
  agent: test-automator
  artifact: test-cases/rating/TC-010.md
  result: success
  summary: "TC-010 → Automated, 3 стабильных прогона"
  changed_files: [framework/tests/test_rating.py]
  evidence: [runs/RUN-20260708-0100.md]
```
"""


def test_valid_block_parsed():
    data, errors = ao.parse(GOOD)
    assert errors == []
    assert data["agent"] == "test-automator" and data["result"] == "success"
    assert data["next_rules"] == [] and data["escalations"] == []   # нормализация


def test_no_block_is_degraded_signal():
    data, errors = ao.parse("просто свободный текст без блока")
    assert data is None and errors


def test_last_block_wins():
    text = ("```yaml\nagent_output: {agent: bug-reporter, artifact: BUG-1, result: failed}\n```\n"
            "передумал, вот итог:\n"
            "```yaml\nagent_output: {agent: bug-reporter, artifact: BUG-1, result: success}\n```")
    data, errors = ao.parse(text)
    assert errors == [] and data["result"] == "success"


def test_bad_result_and_agent_enum():
    text = "```yaml\nagent_output: {agent: mallory, artifact: X, result: done}\n```"
    data, errors = ao.parse(text)
    assert data is not None
    assert any("result" in e for e in errors) and any("agent" in e for e in errors)


def test_charter_and_reviewer_agents_valid():
    # enum-фикс 2026-07-19: exploratory-tester/test-reviewer диспатчатся
    # qa-loop (rules.yaml), но отсутствовали в enum — воркеры подставляли
    # ложные имена (CH-001..003). Граница enum'а закреплена тестом.
    for agent in ("exploratory-tester", "test-reviewer"):
        text = f"```yaml\nagent_output: {{agent: {agent}, artifact: CH-002, result: success}}\n```"
        data, errors = ao.parse(text)
        assert errors == [], f"{agent}: {errors}"
        assert data["agent"] == agent


def test_missing_required_and_nonlist():
    text = "```yaml\nagent_output: {agent: fix-verifier, evidence: не-список}\n```"
    data, errors = ao.parse(text)
    assert any("artifact" in e for e in errors)
    assert any("result" in e for e in errors)
    assert any("evidence" in e for e in errors)


def test_broken_yaml_block_ignored_falls_back():
    text = ("```yaml\nagent_output: {agent: fix-verifier, artifact: BUG-2, result: success}\n```\n"
            "```yaml\n{ это: не yaml: совсем\n```")
    data, errors = ao.parse(text)
    assert errors == [] and data["artifact"] == "BUG-2"
