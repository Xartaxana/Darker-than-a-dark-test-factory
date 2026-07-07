"""Юнит-тесты validate_frontmatter (scripts/validate_frontmatter.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

import validate_frontmatter as vf

SCHEMAS_SRC = Path(__file__).resolve().parents[2] / "schemas"


@pytest.fixture()
def schemas(repo, monkeypatch):
    """Реальные схемы репозитория, пути валидатора — на tmp-репо."""
    monkeypatch.setattr(vf, "REPO", repo.root, raising=True)
    monkeypatch.setattr(vf, "SCHEMAS", SCHEMAS_SRC, raising=True)


def test_valid_artifacts_pass(repo, schemas):
    repo.test_case("TC-001", "Approved")
    repo.bug("BUG-001", "Open")
    repo.run("RUN-20260707-0100", "NeedsTriage", extra="suite: smoke\n")

    errors, _warns = vf.validate()
    assert errors == []


def test_bad_status_and_priority(repo, schemas):
    p = repo.test_case("TC-002", "Aproved")   # опечатка в статусе
    text = p.read_text(encoding="utf-8").replace("priority: P1", "priority: P9")
    p.write_text(text, encoding="utf-8")

    errors, _ = vf.validate()
    assert any("Aproved" in e and "enum" in e for e in errors)
    assert any("P9" in e for e in errors)


def test_missing_required_field(repo, schemas):
    p = repo.bug("BUG-002", "Open")
    p.write_text(p.read_text(encoding="utf-8").replace("severity: major\n", ""),
                 encoding="utf-8")

    errors, _ = vf.validate()
    assert any("BUG-002" in e or "severity" in e for e in errors)


def test_duplicate_id(repo, schemas):
    repo.test_case("TC-003", "Draft")
    # тот же id в другом файле
    (repo.root / "test-cases" / "copy.md").write_text(
        repo.read_artifact("test-cases/TC-003.md"), encoding="utf-8")

    errors, _ = vf.validate()
    assert any("дубль id" in e for e in errors)


def test_no_frontmatter_is_error_but_readme_skipped(repo, schemas):
    (repo.root / "bugs").mkdir(exist_ok=True)
    (repo.root / "bugs" / "broken.md").write_text("просто текст", encoding="utf-8")
    (repo.root / "bugs" / "README.md").write_text("# справка", encoding="utf-8")

    errors, _ = vf.validate()
    assert any("broken.md" in e for e in errors)
    assert not any("README" in e for e in errors)


def test_unknown_field_is_warn_not_error(repo, schemas):
    repo.test_case("TC-004", "Review")
    p = repo.root / "test-cases" / "TC-004.md"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "priority: P1", "priority: P1\nnovel_field: x"), encoding="utf-8")

    errors, warns = vf.validate()
    assert errors == []
    assert any("novel_field" in w for w in warns)


def test_bad_lock_format(repo, schemas):
    repo.test_case("TC-005", "Approved", lock="не лок а мусор")

    errors, _ = vf.validate()
    assert any("lock" in e for e in errors)


def test_resolution_without_comment_is_error(repo, schemas):
    """B1: resolution без resolution_comment — обоснование обязательно."""
    repo.bug("BUG-050", "Open", extra="resolution: accepted_risk\n")

    errors, _ = vf.validate()
    assert any("resolution_comment" in e for e in errors)


def test_resolution_with_comment_is_clean(repo, schemas):
    repo.bug("BUG-051", "Open",
             extra="resolution: wontfix\nresolution_comment: не в этом релизе\n")

    errors, _ = vf.validate()
    assert errors == []


def test_blocked_without_reason_warns(repo, schemas):
    """B5: WARN, не ERROR — переход с борды может не нести причину сразу."""
    repo.bug("BUG-052", "Blocked")

    errors, warns = vf.validate()
    assert errors == []
    assert any("blocked_reason" in w for w in warns)


def test_blocked_with_reason_no_warn(repo, schemas):
    repo.bug("BUG-053", "Blocked", extra="blocked_reason: environment\n")

    _errors, warns = vf.validate()
    assert not any("blocked_reason" in w for w in warns)
