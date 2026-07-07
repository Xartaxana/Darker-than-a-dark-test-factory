"""Self-tests контракта доказательств (C2, docs/09 Этап 2).

schemas/evidence.yaml — исполняемый контракт: эти тесты сверяют его внутреннюю
целостность и паритет с каноническим реестром вердиктов триажа.
"""
from __future__ import annotations

import evidence as ev

# Канонический реестр вердиктов failure-analyst — литерал, зафиксирован намеренно
# (а не выведен из docstring/description), чтобы правка реестра требовала
# осознанной правки этого теста. Источники согласия (все перечисляют одно и то
# же множество): state/rules.yaml (комментарий "# Вердикты: ..."), frontmatter
# `description` .claude/agents/failure-analyst.md, docs/templates/run-report.md,
# docs/08-external-architecture-review.md §4 C2 (таблица Verdict → Minimum evidence).
VERDICT_REGISTRY = {"APP_BUG", "TEST_BUG", "SITE_CHANGED", "APP_CHANGED", "ENV_ISSUE", "FLAKY"}


def test_contract_is_valid():
    assert ev.validate() == []


def test_verdict_set_matches_registry():
    assert set(ev.verdicts()) == VERDICT_REGISTRY


def test_every_verdict_has_non_empty_evidence_list():
    for v in ev.verdicts():
        items = ev.evidence_for(v)
        assert items, f"{v}: пустой список evidence"
        for item in items:
            assert str(item.get("id") or "").strip(), f"{v}: элемент без id"
            assert str(item.get("description") or "").strip(), f"{v}: {item.get('id')} без описания"


def test_ids_unique_within_verdict():
    for v in ev.verdicts():
        ids = [item["id"] for item in ev.evidence_for(v)]
        assert len(ids) == len(set(ids)), f"{v}: дубликаты id {ids}"


def test_ids_for_matches_evidence_for():
    for v in ev.verdicts():
        assert ev.ids_for(v) == {item["id"] for item in ev.evidence_for(v)}


def test_missing_reports_uncollected_ids():
    some_verdict = "APP_BUG"
    all_ids = ev.ids_for(some_verdict)
    one = next(iter(all_ids))
    assert ev.missing(some_verdict, all_ids - {one}) == {one}
    assert ev.missing(some_verdict, all_ids) == set()


def test_flaky_requires_quarantine_decision():
    """B3/B4: FLAKY обязан нести решение о карантине (failure-analyst.md п.6)."""
    assert "quarantine_decision" in ev.ids_for("FLAKY")


def test_app_bug_requires_core_artifacts():
    """C2 таблица: build hash, TC, steps, screenshot, logcat, page source, expected/actual."""
    ids = ev.ids_for("APP_BUG")
    for expected in ("build_hash", "test_case", "steps", "screenshot", "logcat",
                     "page_source", "expected_actual"):
        assert expected in ids, expected


def test_unknown_verdict_returns_empty_not_error():
    assert ev.evidence_for("NOT_A_VERDICT") == []
    assert ev.ids_for("NOT_A_VERDICT") == set()
