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
    # trace-matrix диспатч 1: без этого патча FEATURE_REGISTRY (посчитан на
    # импорте модуля от исходного REPO) указывал бы на боевой
    # docs/feature-registry.yaml — тесты read-only здесь, но нужна
    # управляемая пустота/наполнение, а не боевые 60+ записей.
    monkeypatch.setattr(vf, "FEATURE_REGISTRY", repo.root / "docs" / "feature-registry.yaml", raising=True)


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


def test_quarantine_without_reason_or_since_is_error(repo, schemas):
    """B3: карантин без причины/времени — слепое пятно SLA-надзора."""
    repo.test_case("TC-060", "Automated", extra="automation_status: quarantined\n")

    errors, _ = vf.validate()
    assert any("quarantine_reason" in e for e in errors)
    assert any("quarantine_since" in e for e in errors)


def test_quarantine_complete_is_clean(repo, schemas):
    repo.test_case("TC-061", "Automated", extra=(
        "automation_status: quarantined\n"
        "quarantine_reason: flaky на CI\n"
        "quarantine_since: \"2026-07-07T00:00:00Z\"\n"))

    errors, _ = vf.validate()
    assert errors == []


def test_automation_status_on_non_automated_warns(repo, schemas):
    """B3: lifecycle автотеста живёт только у Automated-кейса."""
    repo.test_case("TC-062", "Review", extra="automation_status: active\n")

    errors, warns = vf.validate()
    assert errors == []
    assert any("automation_status" in w for w in warns)


def test_test_debt_without_kind_warns(repo, schemas):
    """B4: категория долга нужна для digest."""
    repo.bug("AT-BUG-054", "Open", extra="type: test_debt\n")

    errors, warns = vf.validate()
    assert errors == []
    assert any("debt_kind" in w for w in warns)


def test_test_debt_without_at_prefix_is_error(repo, schemas):
    """Конвенция 2026-07-08: type: test_debt требует префикс AT-BUG-, иначе баг
    ошибочно уйдёт внешней команде разработки вместо фабрики."""
    repo.bug("BUG-070", "Open", extra="type: test_debt\ndebt_kind: flaky_test\n")

    errors, _warns = vf.validate()
    assert any("BUG-070" in e and "AT-BUG-" in e for e in errors)


def test_at_prefix_without_test_debt_is_error(repo, schemas):
    """Обратное направление: префикс AT-BUG- без type: test_debt — тоже ошибка."""
    repo.bug("AT-BUG-071", "Open")

    errors, _warns = vf.validate()
    assert any("AT-BUG-071" in e and "test_debt" in e for e in errors)


def test_valid_test_debt_prefix_pair_is_clean(repo, schemas):
    repo.bug("AT-BUG-072", "Open", extra="type: test_debt\ndebt_kind: flaky_test\n")

    errors, _warns = vf.validate()
    assert errors == []


def test_valid_app_bug_prefix_pair_is_clean(repo, schemas):
    """app_bug (или отсутствие type — обратная совместимость) с обычным BUG- — ок."""
    repo.bug("BUG-073", "Open")

    errors, _warns = vf.validate()
    assert errors == []


# --- E4 pipeline wiring: exploratory-charters/ в AREAS + schemas/charter.schema.yaml ---

def test_charter_valid_planned_passes(repo, schemas):
    repo.charter("CH-100", "Planned")

    errors, _warns = vf.validate()
    assert errors == []


def test_charter_inprogress_with_legacy_at_lock_passes(repo, schemas):
    """CH-001 живой формат лока `agent@YYYY-MM-DD` (легаси, заведён до схемы) —
    обязан проходить (спека задачи e4-pipeline-wiring)."""
    repo.charter("CH-101", "InProgress", lock="exploratory-tester@2026-07-14")

    errors, _warns = vf.validate()
    assert errors == []


def test_charter_inprogress_with_canonical_lock_passes(repo, schemas):
    """Канонический формат `agent:ISO-timestamp` (как у test-case/bug/run) —
    тоже валиден для новых charter'ов."""
    repo.charter("CH-102", "InProgress", lock="exploratory-tester:2026-07-14T10:00:00Z")

    errors, _warns = vf.validate()
    assert errors == []


def test_charter_bad_status_is_error(repo, schemas):
    repo.charter("CH-103", "Doing")   # не в enum [Planned, InProgress, Done]

    errors, _warns = vf.validate()
    assert any("CH-103" in e and "enum" in e for e in errors)


def test_charter_bad_id_pattern_is_error(repo, schemas):
    repo.charter("CHARTER-1", "Planned")   # не соответствует ^CH-\d+$

    errors, _warns = vf.validate()
    assert any("CHARTER-1" in e and "не соответствует" in e for e in errors)


def test_charter_empty_trigger_is_clean(repo, schemas):
    """Пустой trigger (шаблон docs/templates/charter.md несёт `trigger: ""`
    по умолчанию) НЕ должен быть ошибкой enum-проверки."""
    repo.charter("CH-104", "Planned", extra='trigger: ""\n')

    errors, _warns = vf.validate()
    assert errors == []


def test_charter_bad_trigger_is_error(repo, schemas):
    repo.charter("CH-105", "Planned", extra="trigger: random-nonsense\n")

    errors, _warns = vf.validate()
    assert any("CH-105" in e and "trigger" in e for e in errors)


def test_charter_readme_skipped(repo, schemas):
    (repo.root / "exploratory-charters").mkdir(parents=True, exist_ok=True)
    (repo.root / "exploratory-charters" / "README.md").write_text("# справка", encoding="utf-8")

    errors, _warns = vf.validate()
    assert not any("README" in e for e in errors)


# --- trace-matrix диспатч 1 (§1b спеки): test-case.features ↔ docs/feature-registry.yaml ---

def _registry(root: Path, feature_ids: list[str]) -> None:
    import yaml
    p = root / "docs" / "feature-registry.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(
            {
                "inventoried_at_commit": "x",
                "features": [
                    {"id": fid, "title": fid, "screen": "s", "source": "f.kt"}
                    for fid in feature_ids
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_feature_id_in_registry_is_clean(repo, schemas):
    _registry(repo.root, ["browse-deep-links"])
    repo.test_case("TC-080", "Approved", extra="features: [browse-deep-links]\n")

    errors, _warns = vf.validate()
    assert errors == []


def test_feature_id_unknown_is_error(repo, schemas):
    _registry(repo.root, ["browse-deep-links"])
    repo.test_case("TC-081", "Approved", extra="features: [totally-unknown-feature]\n")

    errors, _warns = vf.validate()
    assert any("totally-unknown-feature" in e and "feature-registry.yaml" in e for e in errors)


def test_feature_empty_is_warn_not_error(repo, schemas):
    """Отсутствующее/пустое `features` — WARNING (B2 спеки: error-flip только
    после backfill диспатча 2), не ERROR."""
    _registry(repo.root, ["browse-deep-links"])
    repo.test_case("TC-082", "Approved")  # без features вовсе

    errors, warns = vf.validate()
    assert errors == []
    assert any("features" in w and "TC-082" in w for w in warns)


def test_feature_registry_missing_is_warn_not_error(repo, schemas):
    # docs/feature-registry.yaml намеренно не создаётся
    repo.test_case("TC-083", "Approved", extra="features: [anything]\n")

    errors, warns = vf.validate()
    assert errors == []
    assert any("feature-registry.yaml не найден" in w for w in warns)


def test_charter_attachments_md_not_scanned(repo, schemas):
    """e4-charter-lock-reaper п.3: charter'ы валидируются ТОЛЬКО верхним
    уровнем (glob CH-*.md, не rglob) — attachments/CH-NNN/*.md (скриншоты
    сессий обычно .png/.xml, но если бы там оказался .md) не должен ни
    провалить, ни засчитать валидацию (находка critic N3)."""
    repo.charter("CH-106", "Planned")
    broken = repo.root / "exploratory-charters" / "attachments" / "CH-106" / "note.md"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("не frontmatter вовсе, просто текст вложения", encoding="utf-8")

    errors, _warns = vf.validate()
    assert errors == []  # битый "не-frontmatter" вложения не всплывает ошибкой
    assert not any("attachments" in e for e in errors) and \
        not any("attachments" in w for w in _warns)
