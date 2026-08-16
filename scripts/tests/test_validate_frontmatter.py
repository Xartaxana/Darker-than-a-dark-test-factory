"""Юнит-тесты validate_frontmatter (scripts/validate_frontmatter.py)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import validate_frontmatter as vf

SCHEMAS_SRC = Path(__file__).resolve().parents[2] / "schemas"


def _iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


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


# --- vf-dup-key-detector (2026-08-02): дублирующийся YAML-ключ верхнего
# уровня во frontmatter = ERROR (BUG-021 живьём — gitlab_sync writeback
# слепо вставил вторую строку gitlab_issue поверх шаблонного плейсхолдера).

def test_duplicate_top_level_key_is_error(repo, schemas):
    """Образец — вчерашняя живая форма BUG-021: пустой плейсхолдер
    `gitlab_issue: ""` в середине frontmatter (из шаблона) + вторая строка
    `gitlab_issue: 12` (writeback-вставка), обе на нулевом отступе."""
    repo.bug("BUG-090", "Open", extra='gitlab_issue: ""\n')
    p = repo.root / "bugs" / "BUG-090.md"
    text = p.read_text(encoding="utf-8")
    text = text.replace('lock: ""\n---', 'lock: ""\ngitlab_issue: 12\n---')
    p.write_text(text, encoding="utf-8")

    errors, _warns = vf.validate()
    assert any("BUG-090" in e and "gitlab_issue" in e for e in errors)


def test_clean_file_no_duplicate_key_error(repo, schemas):
    repo.bug("BUG-091", "Open")

    errors, _warns = vf.validate()
    assert not any("дублирующийся ключ" in e for e in errors)


def test_nested_same_name_key_is_not_duplicate(repo, schemas):
    """Вложенный ключ (отступ) с тем же именем, что и ключ верхнего уровня
    (`type:`), НЕ считается дублем — только строки с нулевым отступом."""
    repo.bug("BUG-092", "Open", extra=(
        "type: app_bug\n"
        "nested_block:\n"
        "  type: not-a-top-level-duplicate\n"))

    errors, _warns = vf.validate()
    assert not any("дублирующийся ключ" in e and "BUG-092" in e for e in errors)


def test_duplicate_key_three_times_is_single_error(repo, schemas):
    """Граница: ключ, повторённый 3 раза — ОДИН ERROR (не три), с числом
    повторов в тексте. Решение задокументировано в check_duplicate_keys."""
    repo.bug("BUG-093", "Open", extra=(
        "gitlab_issue: 1\n"
        "gitlab_issue: 2\n"
        "gitlab_issue: 3\n"))

    errors, _warns = vf.validate()
    dup_errors = [e for e in errors if "BUG-093" in e and "дублирующийся ключ" in e]
    assert len(dup_errors) == 1
    assert "3x" in dup_errors[0]


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


# --- D14-Intended (ESC-029, решение Lead 2026-08-12): Intended держит
# known_issue "true" — единственный гард D3 still-repro для принятого
# поведения (P3-замки отсечены фильтром штатного регресса).

def test_intended_without_known_issue_warns(repo, schemas):
    repo.bug("BUG-054", "Intended",
             extra="resolution_comment: принято владельцем\n")

    errors, warns = vf.validate()
    assert errors == []
    assert any("Intended" in w and "known_issue" in w for w in warns)


def test_intended_with_known_issue_false_warns(repo, schemas):
    """Граница: явный сброс в \"false\" — тот же WARN, что и отсутствие."""
    repo.bug("BUG-055", "Intended",
             extra='known_issue: "false"\nresolution_comment: принято\n')

    _errors, warns = vf.validate()
    assert any("Intended" in w and "known_issue" in w for w in warns)


def test_intended_with_known_issue_true_no_warn(repo, schemas):
    repo.bug("BUG-056", "Intended",
             extra='known_issue: "true"\nresolution_comment: принято\n')

    _errors, warns = vf.validate()
    assert not any("Intended" in w and "known_issue" in w for w in warns)


def test_open_with_known_issue_false_no_intended_warn(repo, schemas):
    """За границей: чек стреляет ТОЛЬКО на Intended — Open с false легален."""
    repo.bug("BUG-057", "Open", extra='known_issue: "false"\n')

    _errors, warns = vf.validate()
    assert not any("Intended" in w and "known_issue" in w for w in warns)


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


def test_charter_perturbations_skipped(repo, schemas):
    # PERTURBATIONS.md — служебная библиотека возмущений (charter-designer,
    # 2026-07-21), намеренно без frontmatter — не артефакт-чартер.
    (repo.root / "exploratory-charters").mkdir(parents=True, exist_ok=True)
    (repo.root / "exploratory-charters" / "PERTURBATIONS.md").write_text(
        "# матрица возмущений", encoding="utf-8")

    errors, _warns = vf.validate()
    assert not any("PERTURBATIONS" in e for e in errors)


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


def test_feature_empty_is_error_after_flip(repo, schemas):
    """Отсутствующее/пустое `features` — ERROR (error-flip 2026-07-17 после
    полного backfill 65/65, B2 спеки; до флипа было WARNING)."""
    _registry(repo.root, ["browse-deep-links"])
    repo.test_case("TC-082", "Approved")  # без features вовсе

    errors, warns = vf.validate()
    assert any("features" in e and "TC-082" in e for e in errors)
    assert not any("TC-082" in w and "features" in w for w in warns)


def test_feature_not_list_is_error(repo, schemas):
    """Замечание критика: `features` заполнено, но не списком (напр. голая строка
    вместо `[id1, id2]`) — ERROR, не молчаливое проглатывание (check_feature_ids
    возвращает `errors` до итерации по элементам, когда isinstance-проверка
    проваливается)."""
    _registry(repo.root, ["browse-deep-links"])
    repo.test_case("TC-084", "Approved", extra="features: browse-deep-links\n")

    errors, _warns = vf.validate()
    assert any("TC-084" in e and "должен быть списком" in e for e in errors)


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


# --- red_lock (Lead 2026-08-03, прецедент TC-139/BUG-015): красный замок ---

def test_red_lock_valid_pair_is_clean(repo, schemas):
    """red_lock на существующий баг при заполненном automated_by — чисто."""
    repo.bug("BUG-080", "Open")
    repo.test_case("TC-080", "Approved",
                   extra='automated_by: "framework/tests/test_x.py::test_lock"\n'
                         'red_lock: "BUG-080"\n')

    errors, _warns = vf.validate()
    assert errors == []


def test_red_lock_dangling_bug_is_error(repo, schemas):
    """Битая ссылка замка: red_lock на несуществующий bugs/<id>.md — ERROR."""
    repo.test_case("TC-081", "Approved",
                   extra='automated_by: "framework/tests/test_x.py::test_lock"\n'
                         'red_lock: "BUG-999"\n')

    errors, _warns = vf.validate()
    assert any("TC-081" in e and "BUG-999" in e and "несуществующий" in e for e in errors)


def test_red_lock_without_automated_by_is_error(repo, schemas):
    """Замок без теста бессмыслен: red_lock при пустом automated_by — ERROR."""
    repo.bug("BUG-082", "Open")
    repo.test_case("TC-082", "Approved", extra='red_lock: "BUG-082"\n')

    errors, _warns = vf.validate()
    assert any("TC-082" in e and "automated_by" in e for e in errors)


def test_red_lock_bad_format_is_error(repo, schemas):
    """За границей паттерна: мусорное значение red_lock ловится схемой."""
    repo.bug("BUG-083", "Open")
    repo.test_case("TC-083", "Approved",
                   extra='automated_by: "framework/tests/test_x.py::test_lock"\n'
                         'red_lock: "не-баг-вовсе"\n')

    errors, _warns = vf.validate()
    assert any("TC-083" in e and "red_lock" in e for e in errors)


# --- AT-BUG-029 (2 инцидента 2026-08-11): будущий `updated`/`status_since` ---

def test_future_updated_over_slack_is_error(repo, schemas):
    """ЗА границей допуска (10м): +10м01с в будущее — ERROR."""
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10, seconds=1)
    p = repo.bug("BUG-100", "Open")
    text = p.read_text(encoding="utf-8").replace(
        'updated: "2026-07-01T00:00:00Z"', f'updated: "{_iso(future)}"')
    p.write_text(text, encoding="utf-8")

    errors, _warns = vf.validate()
    assert any("BUG-100" in e and "updated" in e and "будущем" in e for e in errors)


def test_future_updated_under_slack_is_clean(repo, schemas):
    """НА границе допуска (10м), но ещё внутри: +9м59с — чисто (clock skew)."""
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=9, seconds=59)
    p = repo.bug("BUG-101", "Open")
    text = p.read_text(encoding="utf-8").replace(
        'updated: "2026-07-01T00:00:00Z"', f'updated: "{_iso(future)}"')
    p.write_text(text, encoding="utf-8")

    errors, _warns = vf.validate()
    assert not any("BUG-101" in e and "будущем" in e for e in errors)


def test_past_updated_is_clean(repo, schemas):
    """Прошлое (дефолт фикстуры, 2026-07-01) — чисто."""
    repo.bug("BUG-102", "Open")

    errors, _warns = vf.validate()
    assert not any("BUG-102" in e and "будущем" in e for e in errors)


# --- П1 Р0 п.1 (spec-p1-dedup v7): статус Merged — двустороннее правило -----

def test_merged_status_clean_pair(repo, schemas):
    repo.test_case("TC-200", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: TC-201\n'
    ))

    errors, _warns = vf.validate()
    assert errors == []


def test_merged_with_automated_by_is_error(repo, schemas):
    repo.test_case("TC-202", "Merged", extra=(
        'automated_by: "framework/tests/test_x.py::test_y"\n'
        'automation_status: ""\n'
        'merged_into: TC-201\n'
    ))

    errors, _warns = vf.validate()
    assert any("TC-202" in e and "automated_by" in e for e in errors)


def test_merged_with_automation_status_is_error(repo, schemas):
    repo.test_case("TC-203", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: active\n'
        'merged_into: TC-201\n'
    ))

    errors, _warns = vf.validate()
    assert any("TC-203" in e and "automation_status" in e for e in errors)


def test_merged_without_merged_into_is_error(repo, schemas):
    repo.test_case("TC-204", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
    ))

    errors, _warns = vf.validate()
    assert any("TC-204" in e and "merged_into" in e for e in errors)


def test_merged_into_without_merged_status_is_error(repo, schemas):
    """Обратная сторона: merged_into непуст, но status != Merged (протухшее поле
    после ручного отката без обнуления, r5)."""
    repo.test_case("TC-205", "Review", extra='merged_into: TC-201\n')

    errors, _warns = vf.validate()
    assert any("TC-205" in e and "merged_into" in e and "status: Merged" in e for e in errors)


def test_merged_into_bad_pattern_is_error(repo, schemas):
    """Схема: merged_into — `^$|^TC-\\d+$`."""
    repo.test_case("TC-206", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: not-a-tc-id\n'
    ))

    errors, _warns = vf.validate()
    assert any("TC-206" in e and "merged_into" in e for e in errors)


# --- П2 Р1 (spec-p2-pyramid v4): поле `layer` — старые кейсы не краснеют ----

def test_layer_empty_is_clean(repo, schemas):
    """Пустая строка/отсутствие layer проходит МОЛЧА (гейт «непусто И в enum»
    держит F1-промпт, не код схемы) — старые 257 кейсов не краснеют."""
    repo.test_case("TC-210", "Approved")

    errors, _warns = vf.validate()
    assert errors == []


def test_layer_valid_enum_is_clean(repo, schemas):
    repo.test_case("TC-211", "Approved", extra="layer: L2\n")

    errors, _warns = vf.validate()
    assert errors == []


def test_layer_bad_enum_is_error(repo, schemas):
    repo.test_case("TC-212", "Approved", extra="layer: L1\n")   # L1 намеренно вне enum

    errors, _warns = vf.validate()
    assert any("TC-212" in e and "layer" in e for e in errors)


# --- П1 Р3 (spec-p1-dedup v7): машинный детектор проб на journey-чекпойнты --

def _journey_case(root: Path, key: str, status: str, body_extra: str, *, extra: str = "") -> Path:
    """Пишет test-case напрямую (repo.test_case не даёт управлять телом файла) —
    frontmatter в стиле Repo.test_case + произвольное markdown-тело ПОСЛЕ него."""
    text = (
        f"---\nid: {key}\ntitle: TC {key}\narea: test\npriority: P1\nstatus: {status}\n"
        f"{extra}updated: \"2026-07-01T00:00:00Z\"\n---\n\n# {key}\n\n{body_extra}\n"
    )
    p = root / "test-cases" / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_checkpoint_probes_zero_checkpoints_is_error_fail_closed(repo, schemas):
    """Н1 критик-диффа (fail-closed): раздел «## Чекпойнты» ЕСТЬ, но
    нумерованных пунктов 0 — битая форма journey-кейса, гейт даёт ERROR,
    а не выключается молча (защита объявлена тотальной — реализована
    тотальной). Кейс БЕЗ раздела — по-прежнему не journey (следующий тест)."""
    _journey_case(repo.root, "TC-220", "Automated",
                  "## Чекпойнты\n\n## Красная проба (red_probe, ретрофит — n/a)\n",
                  extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert any("TC-220" in e and "нумерованных пунктов 0" in e for e in errors)


def test_checkpoint_probes_header_with_suffix_still_gates(repo, schemas):
    """Н1: заголовок с суффиксом («## Чекпойнты (journey)») НЕ выключает гейт
    молча — префикс-матч симметричен заголовку проб."""
    _journey_case(repo.root, "TC-222", "Automated",
                  "## Чекпойнты (journey)\n\n1. первый\n2. второй\n\n"
                  "## Красная проба (red_probe)\n\n- проба: одна\n",
                  extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert any("TC-222" in e and "2" in e for e in errors)   # 2 чекпойнта, 1 проба


def test_checkpoint_probes_missing_section_is_silent(repo, schemas):
    """Кейс без раздела «## Чекпойнты» вовсе — не journey, правило не касается."""
    _journey_case(repo.root, "TC-221", "Automated", "Обычное тело без секций.\n",
                  extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert not any("TC-221" in e and "Чекпойнты" in e for e in errors)


def test_checkpoint_probes_prose_instead_of_probe_lines_is_error(repo, schemas):
    """1 чекпойнт, раздел «Красная проба» есть, но прозой — не матчит `- проба:`
    — ERROR."""
    _journey_case(repo.root, "TC-222", "Automated", (
        "## Чекпойнты\n1. Открыть файл\n\n"
        "## Красная проба (red_probe, ретрофит — n/a)\n"
        "Проверили руками, тест падает на порче.\n"
    ), extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert any("TC-222" in e and "Чекпойнты" in e for e in errors)


def test_checkpoint_probes_review_case_without_probes_is_silent(repo, schemas):
    """Статус-гард: Review с чекпойнтами без проб — молчание (F1 ещё впереди)."""
    _journey_case(repo.root, "TC-223", "Review",
                  "## Чекпойнты\n1. Открыть файл\n2. Удалить файл\n")

    errors, _warns = vf.validate()
    assert not any("TC-223" in e and "Чекпойнты" in e for e in errors)


def test_checkpoint_probes_automated_without_probes_is_error(repo, schemas):
    """Automated без единой пробы — ERROR (граница: 1 чекпойнт, 0 проб)."""
    _journey_case(repo.root, "TC-224", "Automated",
                  "## Чекпойнты\n1. Открыть файл\n\n## Красная проба (red_probe, ретрофит — n/a)\n",
                  extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert any("TC-224" in e and "1 пункт" in e and "0 строк" in e for e in errors)


def test_checkpoint_probes_exact_match_is_clean(repo, schemas):
    """Граница НА месте: 3 чекпойнта, ровно 3 пробы — чисто."""
    _journey_case(repo.root, "TC-225", "Automated", (
        "## Чекпойнты\n1. Открыть файл (CSS)\n2. Удалить файл (рейтинг жив)\n"
        "3. Удалить работу (всё удалено)\n\n"
        "## Красная проба (red_probe, ретрофит — n/a)\n"
        "- проба: чекпойнт 1 упал на порче локатора\n"
        "- проба: чекпойнт 2 упал на порче сида\n"
        "- проба: чекпойнт 3 упал на порче assert'а\n"
    ), extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert not any("TC-225" in e and "Чекпойнты" in e for e in errors)


def test_checkpoint_probes_one_short_is_error(repo, schemas):
    """Граница ЗА местом: 3 чекпойнта, только 2 пробы — ERROR."""
    _journey_case(repo.root, "TC-226", "Automated", (
        "## Чекпойнты\n1. Открыть файл\n2. Удалить файл\n3. Удалить работу\n\n"
        "## Красная проба (red_probe, ретрофит — n/a)\n"
        "- проба: чекпойнт 1\n- проба: чекпойнт 2\n"
    ), extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert any("TC-226" in e and "3 пункт" in e and "2 строк" in e for e in errors)


def test_checkpoint_probes_header_matched_by_prefix(repo, schemas):
    """Заголовок «## Красная проба» матчится ПРЕФИКСОМ — существующие 16 секций
    несут суффикс «(red_probe, ретрофит — …)», это не должно ломать детектор."""
    _journey_case(repo.root, "TC-227", "Automated", (
        "## Чекпойнты\n1. Открыть файл\n\n"
        "## Красная проба (red_probe, ретрофит — 2026-08-16T10:00:00Z)\n"
        "- проба: упал на порче\n"
    ), extra='automated_by: "framework/tests/test_x.py::test_y"\n')

    errors, _warns = vf.validate()
    assert not any("TC-227" in e and "Чекпойнты" in e for e in errors)


def test_future_status_since_is_error(repo, schemas):
    """Тот же детектор — на `status_since`, не только на `updated` (второй
    инцидент AT-BUG-029: +4..11ч в будущее)."""
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)
    repo.bug("BUG-103", "Open", extra=f'status_since: "{_iso(future)}"\n')

    errors, _warns = vf.validate()
    assert any("BUG-103" in e and "status_since" in e and "будущем" in e for e in errors)
