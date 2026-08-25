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


# --- Батч мелочей п.2: referential-проверка merged_into (WARN-ярус) ---------

def test_merged_into_target_exists_and_not_merged_is_clean(repo, schemas):
    """Happy path: цель существует и сама не Merged — ни ERROR, ни referential
    WARN про merged_into."""
    repo.test_case("TC-210", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: TC-211\n'
    ))
    repo.test_case("TC-211", "Approved")

    errors, warns = vf.validate()
    assert errors == []
    assert not any("TC-210" in w and "merged_into" in w for w in warns)


def test_merged_into_target_missing_is_warn(repo, schemas):
    """Цель НЕ существует в test-cases/ — WARN (не ERROR: не блокирует конвейер)."""
    repo.test_case("TC-212", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: TC-999\n'
    ))

    errors, warns = vf.validate()
    assert not any("TC-212" in e for e in errors)
    assert any("TC-212" in w and "TC-999" in w and "merged_into" in w for w in warns)


def test_merged_into_target_itself_merged_is_warn(repo, schemas):
    """Цепочка Merged->Merged: цель сама `status: Merged` — цель протухла, WARN."""
    repo.test_case("TC-213", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: TC-214\n'
    ))
    repo.test_case("TC-214", "Merged", extra=(
        'automated_by: ""\n'
        'automation_status: ""\n'
        'merged_into: TC-211\n'
    ))
    repo.test_case("TC-211", "Approved")

    errors, warns = vf.validate()
    assert not any("TC-213" in e for e in errors)
    assert any("TC-213" in w and "TC-214" in w and "merged_into" in w for w in warns)


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


# --- C1 (spec-C-v2, state/escalations.md CLASS-MECHANISM-STALE-TEXT-AFTER-
# STATUS-TRANSITION): stale-text WARN правило («словарь маркеров») ---------

def _bug_custom(root: Path, key: str, status: str, *, title: str, h1: str,
                 extra: str = "") -> Path:
    """Пишет bug-файл напрямую с УПРАВЛЯЕМЫМИ title/H1 — Repo.bug фиксирует
    оба (title='Тестовый баг {key}', H1='# {key}') и не даёт их переопределить."""
    text = (
        f"---\nid: {key}\ntitle: {title}\nseverity: major\nstatus: {status}\n"
        f"{extra}updated: \"2026-07-01T00:00:00Z\"\nlock: \"\"\n---\n\n# {h1}\n\nтело\n"
    )
    p = root / "bugs" / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_stale_text_marker_in_h1_at_fixed_warns(repo, schemas):
    """Дословная цитата эскалации (рецидив 6, AT-BUG-088): H1 держит
    додиагностический маркер при status Fixed без маркера снятия."""
    _bug_custom(repo.root, "AT-BUG-200", "Fixed",
                title="AT-BUG-200 test debt", extra="type: test_debt\n",
                h1="AT-BUG-200: Then-хелперы слепы к отказу adb")

    _errors, warns = vf.validate()
    assert any("AT-BUG-200" in w and "слепы к" in w for w in warns)


def test_stale_text_with_snyato_qualifier_clears(repo, schemas):
    """Квалификатор снятия ОБЯЗАТЕЛЕН как часть правила: «(СНЯТО ...)» в
    ТОЙ ЖЕ строке выключает WARN."""
    _bug_custom(repo.root, "AT-BUG-201", "Fixed",
                title="AT-BUG-201 test debt", extra="type: test_debt\n",
                h1="AT-BUG-201: Then-хелперы слепы к отказу adb (СНЯТО 2026-08-20T10:00:00Z)")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-201" in w and "слепы к" in w for w in warns)


def test_stale_text_with_byli_qualifier_clears(repo, schemas):
    _bug_custom(repo.root, "AT-BUG-202", "Fixed",
                title="AT-BUG-202 test debt", extra="type: test_debt\n",
                h1="AT-BUG-202: Then-хелперы БЫЛИ слепы к отказу adb")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-202" in w and "слепы к" in w for w in warns)


def test_stale_text_with_lowercase_byli_qualifier_clears(repo, schemas):
    """C2-F2 (критик-раунд): регистронезависимость — исходная реализация
    матчила ТОЛЬКО заглавную форму «БЫЛИ», строчная «были слепы к» была
    ложным срабатыванием."""
    _bug_custom(repo.root, "AT-BUG-210", "Fixed",
                title="AT-BUG-210 test debt", extra="type: test_debt\n",
                h1="AT-BUG-210: Then-хелперы были слепы к отказу adb")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-210" in w and "слепы к" in w for w in warns)


def test_stale_text_with_byla_qualifier_clears(repo, schemas):
    """C2-F2: словоформа «была» (не только «были»)."""
    _bug_custom(repo.root, "AT-BUG-211", "Fixed",
                title="AT-BUG-211: она была не разделено", extra="type: test_debt\n",
                h1="AT-BUG-211")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-211" in w and "не разделено" in w for w in warns)


def test_stale_text_with_ustraneno_qualifier_clears(repo, schemas):
    """C2-F2: новое слово словаря снятия — «устранено»."""
    _bug_custom(repo.root, "AT-BUG-212", "Fixed",
                title="AT-BUG-212 test debt", extra="type: test_debt\n",
                h1="AT-BUG-212: слепы к отказу adb, устранено")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-212" in w and "слепы к" in w for w in warns)


def test_stale_text_with_ispravleno_qualifier_clears(repo, schemas):
    """C2-F2: новое слово словаря снятия — «исправлено»."""
    _bug_custom(repo.root, "AT-BUG-213", "Fixed",
                title="AT-BUG-213 test debt", extra="type: test_debt\n",
                h1="AT-BUG-213: не разделено, исправлено")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-213" in w and "не разделено" in w for w in warns)


def test_stale_text_with_pofikshcheno_qualifier_clears(repo, schemas):
    """C2-F2: новое слово словаря снятия — «пофикшено»."""
    _bug_custom(repo.root, "AT-BUG-214", "Fixed",
                title="AT-BUG-214 test debt", extra="type: test_debt\n",
                h1="AT-BUG-214: слепы к отказу adb, пофикшено")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-214" in w and "слепы к" in w for w in warns)


def test_stale_text_ne_reshayu_marker_warns(repo, schemas):
    """C2-B3 (критик-раунд): восстановленный маркер словаря «не решаю»
    (сужен молча в первой реализации — восстановлен без сужения)."""
    _bug_custom(repo.root, "AT-BUG-215", "Fixed",
                title="AT-BUG-215: не решаю проблему гонки", extra="type: test_debt\n",
                h1="AT-BUG-215")

    _errors, warns = vf.validate()
    assert any("AT-BUG-215" in w and "не решаю" in w for w in warns)


def test_stale_text_zhivoy_remnant_marker_warns(repo, schemas):
    """C2-B3 (критик-раунд): восстановленный маркер словаря «живой
    remnant» (дословная цитата эскалации, рецидив 6/AT-BUG-088)."""
    _bug_custom(repo.root, "AT-BUG-216", "Fixed",
                title="AT-BUG-216 test debt", extra="type: test_debt\n",
                h1="AT-BUG-216: живой remnant AT-BUG-055")

    _errors, warns = vf.validate()
    assert any("AT-BUG-216" in w and "живой remnant" in w for w in warns)


def test_stale_text_byl_substring_inside_unrelated_word_does_not_clear(repo, schemas):
    """Граница `\\b`: «был» ВНУТРИ несвязанного слова («приБЫЛ») — НЕ
    квалификатор снятия (короткая подстрока без границ слова матчила бы
    ложно)."""
    _bug_custom(repo.root, "AT-BUG-218", "Fixed",
                title="AT-BUG-218 test debt", extra="type: test_debt\n",
                h1="AT-BUG-218: слепы к отказу adb, файл прибыл с сервера")

    _errors, warns = vf.validate()
    assert any("AT-BUG-218" in w and "слепы к" in w for w in warns)


def test_stale_text_chitayut_cherez_without_goliy_still_warns(repo, schemas):
    """C2-B3: маркер расширен «читают через голый» -> «читают через» (БЕЗ
    слова «голый» вовсе — маркер шире, не уже)."""
    _bug_custom(repo.root, "AT-BUG-217", "Fixed",
                title="AT-BUG-217 test debt", extra="type: test_debt\n",
                h1="AT-BUG-217: хелперы читают через adb напрямую")

    _errors, warns = vf.validate()
    assert any("AT-BUG-217" in w and "читают через" in w for w in warns)


def test_stale_text_bare_date_no_longer_clears(repo, schemas):
    """C2-F3 (критик-раунд): голая дата БЕЗ слова снятия рядом — НЕ
    квалификатор (сужено против первой реализации задачи, где дата САМА
    ПО СЕБЕ гасила WARN — «дата в поле — не снятие»)."""
    _bug_custom(repo.root, "AT-BUG-203", "Fixed",
                title="AT-BUG-203 test debt", extra="type: test_debt\n",
                h1="AT-BUG-203: слепы к отказу adb (2026-08-20)")

    _errors, warns = vf.validate()
    assert any("AT-BUG-203" in w and "слепы к" in w for w in warns)


def test_stale_text_date_near_snyato_still_clears(repo, schemas):
    """Дата РЯДОМ со словом снятия по-прежнему легальна — снятие несёт
    слово «СНЯТО», дата просто сопровождает его (не самостоятельный
    квалификатор)."""
    _bug_custom(repo.root, "AT-BUG-209", "Fixed",
                title="AT-BUG-209 test debt", extra="type: test_debt\n",
                h1="AT-BUG-209: слепы к отказу adb (СНЯТО, 2026-08-20)")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-209" in w and "слепы к" in w for w in warns)


def test_stale_text_marker_in_title_at_verified_warns(repo, schemas):
    _bug_custom(repo.root, "AT-BUG-204", "Verified",
                title="AT-BUG-204: не разделено два сценария",
                extra="type: test_debt\n", h1="AT-BUG-204")

    _errors, warns = vf.validate()
    assert any("AT-BUG-204" in w and "не разделено" in w for w in warns)


def test_stale_text_third_marker_raw_adb(repo, schemas):
    """Третий маркер словаря («читают через голый»), дословная цитата
    эскалации (рецидив 6, AT-BUG-088)."""
    _bug_custom(repo.root, "AT-BUG-205", "Fixed",
                title="AT-BUG-205 test debt", extra="type: test_debt\n",
                h1="AT-BUG-205: хелперы читают через голый adb.run_as")

    _errors, warns = vf.validate()
    assert any("AT-BUG-205" in w and "читают через голый" in w for w in warns)


def test_stale_text_marker_on_open_bug_is_silent(repo, schemas):
    """Гард по статусу: Open — не терминальный статус этого правила."""
    _bug_custom(repo.root, "AT-BUG-206", "Open",
                title="AT-BUG-206: слепы к отказу adb", h1="AT-BUG-206")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-206" in w and "слепы к" in w for w in warns)


def test_stale_text_no_marker_at_fixed_is_silent(repo, schemas):
    _bug_custom(repo.root, "AT-BUG-207", "Fixed",
                title="AT-BUG-207 test debt", extra="type: test_debt\n",
                h1="AT-BUG-207: фикс закатан")

    _errors, warns = vf.validate()
    assert not any("AT-BUG-207" in w and "stale-text" in w for w in warns)


def test_stale_text_non_bug_area_is_not_scanned(repo, schemas):
    """Правило — только для bugs/ (schema.get('type') == 'bug')."""
    repo.test_case("TC-208", "Approved", extra='title: "слепы к отказу adb"\n')

    _errors, warns = vf.validate()
    assert not any("stale-text" in w or "додиагностический маркер" in w for w in warns)


def test_real_repo_stale_text_baseline():
    """C1: пин на живом репо. В корпусе/git-истории истинных экземпляров
    НЕТ на момент задачи (все чинились ДО коммита, см. state/escalations.md
    CLASS-MECHANISM-STALE-TEXT-AFTER-STATUS-TRANSITION) — множество WARN
    правила stale_text ПУСТО. Дрейф множества — сигнал: рецидив (разобрать)
    либо ложное срабатывание (сузить маркер/охват)."""
    _errors, warns = vf.validate()
    hits = [w for w in warns if "додиагностический маркер" in w]
    assert hits == [], "\n".join(hits)


# --- C3 (spec-C-v2, ESC APP-UNDER-TEST-YAML-COHERENCE-GATE): AUT<->runs ---

def _aut(root: Path, *, source_commit: str | None = None,
         smoke: str = "not_run", regression: str = "not_run",
         canary: str = "not_run") -> Path:
    lines = ["app: ao3-wrapper\n"]
    if source_commit is not None:
        lines.append(f"source_commit: {source_commit}\n")
    lines.append(f"smoke_status: {smoke}\n")
    lines.append(f"regression_status: {regression}\n")
    lines.append(f"canary_status: {canary}\n")
    p = root / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(lines), encoding="utf-8")
    return p


FULL_COMMIT = "fdd3f72884105d1453448e0c9a7f2b109588b182"
SHORT_COMMIT = "fdd3f728"
OTHER_COMMIT = "aa377e0ec9664fcd5439fec9391638fabf94f448"


def test_aut_coherence_confirmed_by_matching_closed_run_is_clean(repo, schemas):
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1818", "Closed",
              extra=f'suite: smoke\nsource_commit: "{FULL_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_missing_confirming_run_warns(repo, schemas):
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")

    _errors, warns = vf.validate()
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_short_hash_prefix_matches(repo, schemas):
    """Короткий хэш в run, полный — в AUT: сравнение по префиксу."""
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1819", "Closed",
              extra=f'suite: smoke\nsource_commit: "{SHORT_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_short_hash_in_aut_matches_full_in_run(repo, schemas):
    """Обратное направление: короткий хэш в AUT, полный — в run."""
    _aut(repo.root, source_commit=SHORT_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1820", "Closed",
              extra=f'suite: smoke\nsource_commit: "{FULL_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_run_without_source_commit_not_counted(repo, schemas):
    """Прогон БЕЗ source_commit — пропускается явно, не считается совпавшим
    (8 таких в корпусе)."""
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1821", "Closed", extra="suite: smoke\n")

    _errors, warns = vf.validate()
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_non_closed_run_does_not_confirm(repo, schemas):
    """Triaged, не Closed — не подтверждает."""
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1822", "Triaged",
              extra=f'suite: smoke\nsource_commit: "{FULL_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_wrong_suite_does_not_confirm(repo, schemas):
    """Тот же коммит, тот же статус Closed, но ДРУГОЙ suite — не подтверждает."""
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1823", "Closed",
              extra=f'suite: regression\nsource_commit: "{FULL_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_not_run_status_is_silent(repo, schemas):
    """not_run — нечего сверять."""
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="not_run")

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_mismatched_commit_warns(repo, schemas):
    _aut(repo.root, source_commit=FULL_COMMIT, smoke="passed")
    repo.run("RUN-20260819-1824", "Closed",
              extra=f'suite: smoke\nsource_commit: "{OTHER_COMMIT}"\n')

    _errors, warns = vf.validate()
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_missing_aut_file_is_silent(repo, schemas):
    """Нет state/app-under-test.yaml вовсе — тишина, не падение."""
    repo.run("RUN-20260819-1825", "Closed", extra="suite: smoke\n")

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_missing_source_commit_field_is_silent(repo, schemas):
    """AUT без поля source_commit вовсе — нечего сверять (не ERROR/WARN)."""
    _aut(repo.root, source_commit=None, smoke="passed")

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


# --- C2-B2 (критик-раунд): canary — оракул СВЕЖЕСТИ, не commit-оракул ---

def _run_custom(root: Path, key: str, status: str, *, suite: str,
                 source_commit: str | None = None,
                 updated: str | None = None) -> Path:
    """Пишет run-файл напрямую (`Repo.run` жёстко фиксирует `updated` —
    не даёт управлять им, а именно `updated` управляет canary-свежестью
    в этих тестах)."""
    lines = [f"---\nid: {key}\ntitle: Прогон {key}\nstatus: {status}\nsuite: {suite}\n"]
    if source_commit is not None:
        lines.append(f'source_commit: "{source_commit}"\n')
    if updated is not None:
        lines.append(f'updated: "{updated}"\n')
    lines.append('lock: ""\n---\n\n# {}\n\nтело\n'.format(key))
    p = root / "runs" / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(lines), encoding="utf-8")
    return p


def _iso_days_ago(days: int) -> str:
    value = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return _iso(value)


def test_aut_coherence_canary_not_matched_by_commit(repo, schemas):
    """C2-B2: canary НЕ проверяется по source_commit — Closed canary-прогон
    с ЧУЖИМ коммитом, но свежий по времени, не даёт WARN (в отличие от
    smoke/regression, где чужой коммит = WARN)."""
    _aut(repo.root, source_commit=FULL_COMMIT, canary="passed")
    _run_custom(repo.root, "RUN-20260819-0100", "Closed", suite="canary",
                source_commit=OTHER_COMMIT, updated=_iso_days_ago(1))

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_fresh_is_clean(repo, schemas):
    _aut(repo.root, canary="passed")
    _run_custom(repo.root, "RUN-20260819-0101", "Closed", suite="canary",
                updated=_iso_days_ago(1))

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_stale_warns(repo, schemas):
    """ЗА границей: новейший Closed canary-прогон старше 14д (15д) — WARN."""
    _aut(repo.root, canary="passed")
    _run_custom(repo.root, "RUN-20260801-0100", "Closed", suite="canary",
                updated=_iso_days_ago(15))

    _errors, warns = vf.validate()
    assert any("canary_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_at_boundary_is_clean(repo, schemas):
    """НА границе: ровно 14д — ещё легально (`>`, не `>=`)."""
    _aut(repo.root, canary="passed")
    _run_custom(repo.root, "RUN-20260806-0100", "Closed", suite="canary",
                updated=_iso_days_ago(14))

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_no_closed_run_at_all_warns(repo, schemas):
    _aut(repo.root, canary="passed")

    _errors, warns = vf.validate()
    assert any("canary_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_falls_back_to_id_date(repo, schemas):
    """Легаси-прогон БЕЗ `updated` вовсе (реальный корпусный случай,
    RUN-20260814-0605) — дата из id-конвенции `RUN-YYYYMMDD-HHMM`."""
    old_id = "RUN-" + (dt.datetime.now(dt.timezone.utc)
                        - dt.timedelta(days=1)).strftime("%Y%m%d-%H%M")
    _aut(repo.root, canary="passed")
    _run_custom(repo.root, old_id, "Closed", suite="canary", updated=None)

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_not_run_status_is_silent(repo, schemas):
    _aut(repo.root, canary="not_run")

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_aut_coherence_canary_open_run_does_not_count(repo, schemas):
    """Triaged (не Closed) canary-прогон, даже свежий, не подтверждает свежесть."""
    _aut(repo.root, canary="passed")
    _run_custom(repo.root, "RUN-20260819-0102", "Triaged", suite="canary",
                updated=_iso_days_ago(1))

    _errors, warns = vf.validate()
    assert any("canary_status" in w and "AUT<->runs" in w for w in warns)


# --- C2-F5 (критик-раунд): минимальная длина префикса хэша 7 -------------

def test_aut_coherence_short_commit_prefix_warns(repo, schemas):
    """ЗА границей: `source_commit` короче 7 символов — WARN о подозрительно
    коротком хэше, C3-сверка smoke/regression по префиксу пропущена."""
    _aut(repo.root, source_commit="fdd3f72", smoke="passed")  # 7 (граница — см. ниже)
    _run_custom(repo.root, "RUN-20260819-0103", "Closed", suite="smoke",
                source_commit="fd")  # RUN несёт короткий (< 7) commit

    _errors, warns = vf.validate()
    # AUT commit сам по себе (7 симв.) валиден по длине — сверка идёт,
    # но подтверждающего прогона с ДЛИНОЙ >= 7 нет (RUN-овский короче).
    assert any("smoke_status" in w and "AUT<->runs" in w for w in warns)


def test_aut_coherence_aut_commit_below_min_len_warns_distinctly(repo, schemas):
    """ЗА границей: сам `source_commit` AUT короче 7 — отдельный WARN
    («подозрительно короткий хэш»), sverка smoke/regression пропускается
    целиком (не 3 разных WARN)."""
    _aut(repo.root, source_commit="fdd3f7", smoke="passed", regression="passed")  # 6 < 7

    _errors, warns = vf.validate()
    hits = [w for w in warns if "AUT<->runs" in w or "короткий хэш" in w]
    assert len(hits) == 1
    assert "короткий хэш" in hits[0]


def test_aut_coherence_commit_prefix_exactly_min_len_matches(repo, schemas):
    """НА границе: ровно 7 символов с обеих сторон — совпадение легально."""
    _aut(repo.root, source_commit=FULL_COMMIT[:7], smoke="passed")
    _run_custom(repo.root, "RUN-20260819-0104", "Closed", suite="smoke",
                source_commit=FULL_COMMIT[:7])

    _errors, warns = vf.validate()
    assert not any("AUT<->runs" in w for w in warns)


def test_real_repo_aut_coherence_baseline():
    """C3: пин ТОЧНОГО множества WARN на живом репо — критик-раунд подтвердил
    0 WARN (canary теперь сверяется оракулом свежести, не commit-оракулом;
    RUN-20260814-0605 моложе 14д на момент задачи)."""
    _errors, warns = vf.validate()
    hits = [w for w in warns if "AUT<->runs" in w or "короткий хэш" in w]
    assert hits == [], "\n".join(hits)


# --- Батч C v2 (критик C-B5): WARN-информатор untracked Approved test-case ---

def _git(root: Path, *args: str) -> None:
    import subprocess
    subprocess.run(["git", *args], cwd=root, check=True,
                    capture_output=True, text=True, encoding="utf-8")


def _git_init(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@test.local")
    _git(root, "config", "user.name", "t")


def _git_commit_all(root: Path, msg: str = "init") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def test_untracked_approved_test_case_warns(repo, schemas):
    _git_init(repo.root)
    repo.test_case("TC-300", "Draft")
    _git_commit_all(repo.root)
    # untracked: на диске, но не закоммичен
    repo.test_case("TC-301", "Approved")

    _errors, warns = vf.validate()
    assert any("TC-301" in w and "untracked" in w and "Approved" in w for w in warns)


def test_tracked_approved_test_case_no_untracked_warn(repo, schemas):
    """Уже закоммиченный Approved-кейс — не untracked, информатор молчит
    (штатный путь: аппрув СУЩЕСТВУЮЩЕГО файла human/qa-loop после коммита)."""
    _git_init(repo.root)
    repo.test_case("TC-302", "Approved")
    _git_commit_all(repo.root)

    _errors, warns = vf.validate()
    assert not any("TC-302" in w and "untracked" in w for w in warns)


def test_untracked_draft_test_case_no_warn(repo, schemas):
    _git_init(repo.root)
    repo.test_case("TC-303", "Draft")

    _errors, warns = vf.validate()
    assert not any("TC-303" in w and "untracked" in w for w in warns)


def test_no_git_repo_untracked_check_degrades_to_silence(repo, schemas):
    """Нет .git вовсе — git ls-tree отказывает, информатор молчит (fail-quiet)."""
    repo.test_case("TC-304", "Approved")

    _errors, warns = vf.validate()
    assert not any("TC-304" in w and "untracked" in w for w in warns)


# --- Б6 п.3 (критик-раунд 2, каденция compatibility 2026-08-25): поля,
# от которых зависит зачёт каденции (sla_sweep._compatibility_run_wanted),
# ловятся check_cross_field_warn на пути исполнения (WARN, не ERROR).


def test_run_compatibility_missing_device_avd_warns(repo, schemas):
    repo.run("RUN-060", "Closed", extra="suite: compatibility\nmode: live\n")

    _errors, warns = vf.validate()
    assert any("RUN-060" in w and "device_avd" in w for w in warns)


def test_run_compatibility_with_device_avd_no_device_avd_warn(repo, schemas):
    repo.run("RUN-061", "Closed",
             extra="suite: compatibility\nmode: live\ndevice_avd: ao3_test_api29\n")

    _errors, warns = vf.validate()
    assert not any("RUN-061" in w and "device_avd" in w for w in warns)


def test_run_canary_missing_device_avd_no_warn(repo, schemas):
    """Молчит на НЕ-compatibility: device_avd факультативен для прочих suites."""
    repo.run("RUN-062", "Closed", extra="suite: canary\n")

    _errors, warns = vf.validate()
    assert not any("RUN-062" in w and "device_avd" in w for w in warns)


def test_run_compatibility_mode_replay_warns(repo, schemas):
    repo.run("RUN-063", "Closed",
             extra="suite: compatibility\nmode: replay\ndevice_avd: ao3_test_api29\n")

    _errors, warns = vf.validate()
    assert any("RUN-063" in w and "требует mode: live" in w for w in warns)


def test_run_compatibility_mode_missing_warns(repo, schemas):
    repo.run("RUN-064", "Closed", extra="suite: compatibility\ndevice_avd: ao3_test_api29\n")

    _errors, warns = vf.validate()
    assert any("RUN-064" in w and "требует mode: live" in w for w in warns)


def test_run_compatibility_mode_live_no_mode_warn(repo, schemas):
    repo.run("RUN-065", "Closed",
             extra="suite: compatibility\nmode: live\ndevice_avd: ao3_test_api29\n")

    _errors, warns = vf.validate()
    assert not any("RUN-065" in w and "требует mode: live" in w for w in warns)


def test_run_canary_mode_replay_no_mode_warn(repo, schemas):
    """Молчит на НЕ-compatibility: mode-проверка каденции привязана к suite."""
    repo.run("RUN-066", "Closed", extra="suite: canary\nmode: replay\n")

    _errors, warns = vf.validate()
    assert not any("RUN-066" in w and "требует mode: live" in w for w in warns)


def test_run_missing_both_stamps_warns(repo, schemas):
    """`RUN без обоих штампов` — общий чек, НЕ привязан к suite (живой пример
    дефекта — RUN-20260814-0605, suite: canary, без status_since/updated)."""
    p = repo.run("RUN-067", "Closed", extra="suite: compatibility\nmode: live\n"
                 "device_avd: ao3_test_api29\n")
    text = p.read_text(encoding="utf-8").replace('updated: "2026-07-01T00:00:00Z"\n', "")
    p.write_text(text, encoding="utf-8")

    _errors, warns = vf.validate()
    assert any("RUN-067" in w and "status_since" in w and "updated" in w for w in warns)


def test_run_canary_missing_both_stamps_also_warns(repo, schemas):
    """Штамп-чек НЕ молчит на НЕ-compatibility — проблема общая (RUN-20260814-0605
    из живого корпуса — ровно canary без штампов)."""
    p = repo.run("RUN-068", "Closed", extra="suite: canary\n")
    text = p.read_text(encoding="utf-8").replace('updated: "2026-07-01T00:00:00Z"\n', "")
    p.write_text(text, encoding="utf-8")

    _errors, warns = vf.validate()
    assert any("RUN-068" in w and "status_since" in w and "updated" in w for w in warns)


def test_run_with_updated_only_no_stamp_warn(repo, schemas):
    """Хотя бы один штамп (updated по умолчанию от фикстуры) — тихо."""
    repo.run("RUN-069", "Closed", extra="suite: canary\n")

    _errors, warns = vf.validate()
    assert not any("RUN-069" in w and "status_since" in w and "не заполнены" in w for w in warns)


# --- З8 (критик-раунд 3, 2026-08-25): проверка «нет ни status_since, ни
# updated» была УЖЕ класса, который декларирует — стояла под условием
# schema.type == "run", хотя возраст через `sla_sweep._since` читается и у
# багов (severity-правила, question_unanswered, bug_fixed_waiting_build), и у
# test-case'ов (quarantine_expired), и у ЛЮБОГО артефакта в Blocked
# (blocked_any). Исключение — exploratory-charters: их возраст считается
# другим путём (charter_utils/executed_at), штампов у них нет по построению.

def _strip_stamps(p: Path) -> None:
    text = p.read_text(encoding="utf-8").replace('updated: "2026-07-01T00:00:00Z"\n', "")
    p.write_text(text, encoding="utf-8")


def test_bug_without_any_stamp_warns(repo, schemas):
    """КРАСНАЯ ПРОБА З8: недатированный БАГ так же невидим для SLA-надзора,
    как недатированный прогон. ДО правки — тишина (условие по типу `run`)."""
    p = repo.bug("BUG-140", "Open")
    _strip_stamps(p)

    _errors, warns = vf.validate()
    assert any("BUG-140" in w and "status_since" in w and "не заполнены" in w for w in warns)


def test_test_case_without_any_stamp_warns(repo, schemas):
    """КРАСНАЯ ПРОБА З8: то же для test-case (quarantine_expired/blocked_any
    считают его возраст через `_since`). ДО правки — тишина."""
    p = repo.test_case("TC-400", "Draft")
    _strip_stamps(p)

    _errors, warns = vf.validate()
    assert any("TC-400" in w and "status_since" in w and "не заполнены" in w for w in warns)


def test_bug_with_status_since_only_is_quiet(repo, schemas):
    """Достаточно ОДНОГО штампа (status_since) — тихо, как и у прогонов."""
    p = repo.bug("BUG-141", "Open", extra='status_since: "2026-07-01T00:00:00Z"\n')
    _strip_stamps(p)

    _errors, warns = vf.validate()
    assert not any("BUG-141" in w and "не заполнены" in w for w in warns)


def test_charter_without_stamps_stays_quiet(repo, schemas):
    """ЯВНОЕ ИСКЛЮЧЕНИЕ З8: у чартеров возраст считается через
    `charter_utils`/`executed_at`, status_since/updated им не заведены —
    живой корпус дал бы 11 ложных предупреждений. Проверка обязана молчать
    на этом типе (и до, и после правки)."""
    repo.charter("CH-020", "Done", extra='executed_at: "2026-07-01T00:00:00Z"\n')

    _errors, warns = vf.validate()
    assert not any("CH-020" in w and "не заполнены" in w for w in warns)
