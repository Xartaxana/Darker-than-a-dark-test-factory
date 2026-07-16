"""Юнит-тесты coverage_map (scripts/coverage_map.py)."""
from __future__ import annotations

from pathlib import Path

import coverage_map as cm


def _patch(repo, monkeypatch) -> None:
    monkeypatch.setattr(cm, "REPO", repo.root, raising=True)
    monkeypatch.setattr(cm, "OUT_PATH", repo.root / "state" / "coverage-map.md", raising=True)
    monkeypatch.setattr(cm, "RISK_DOC_PATH", repo.root / "docs" / "01-test-strategy.md", raising=True)
    # trace-matrix диспатч 1: изоляция от реального docs/feature-registry.yaml —
    # без этого патча тесты читали бы боевой реестр репозитория (нестабильно:
    # реестр эволюционирует независимо от фикстур этого файла).
    monkeypatch.setattr(cm, "FEATURE_REGISTRY_PATH", repo.root / "docs" / "feature-registry.yaml", raising=True)
    monkeypatch.setattr(cm, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)


def _tc(root: Path, key: str, area: str, status: str, priority: str = "P1",
        risk: str | None = None, automated_by: str | None = None) -> Path:
    extra = ""
    if risk is not None:
        extra += f"risk: {risk}\n"
    if automated_by is not None:
        extra += f'automated_by: "{automated_by}"\n'
    text = (
        f"---\nid: {key}\ntitle: TC {key}\narea: {area}\npriority: {priority}\n"
        f"status: {status}\n{extra}updated: \"2026-07-01T00:00:00Z\"\nlock: \"\"\n---\n\n# {key}\n\nтело\n"
    )
    p = root / "test-cases" / area / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _run(root: Path, key: str, *, suite: str, status: str, updated: str,
         passed: int = 1, failed: int = 0, tc_results: dict[str, str] | None = None) -> Path:
    tc_line = ""
    if tc_results is not None:
        body = ", ".join(f"{k}: {v}" for k, v in tc_results.items())
        tc_line = f"tc_results: {{ {body} }}\n"
    text = (
        f"---\nid: {key}\ntitle: Прогон {key}\nsuite: {suite}\nstatus: {status}\n"
        f"totals: {{ passed: {passed}, failed: {failed} }}\n{tc_line}"
        f"updated: \"{updated}\"\nlock: \"\"\n---\n\n# {key}\n\nтело\n"
    )
    p = root / "runs" / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _risk_table(root: Path, rows: list[tuple[str, str, str]]) -> Path:
    header = (
        "# 01 — Тестовая стратегия (фикстура)\n\n"
        "## 5. Риск-матрица (вероятность × влияние, 1–3)\n\n"
        "| ID | Категория | Риск | P | I | Счёт | Митигация |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    body = "".join(f"| {rid} | {cat} | {desc} | 2 | 2 | 4 | — |\n" for rid, cat, desc in rows)
    footer = "\n## 6. Приоритеты покрытия\n\n(не используется в тесте)\n"
    p = root / "docs" / "01-test-strategy.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header + body + footer, encoding="utf-8")
    return p


def test_empty_area_reported(repo, monkeypatch):
    """Пустая папка области (без единого кейса) — явная строка, не падение."""
    _patch(repo, monkeypatch)
    (repo.root / "test-cases" / "canary").mkdir(parents=True)
    _tc(repo.root, "TC-100", "smoke", "Automated", priority="P0", risk="R-01")

    text = cm.render(cm.collect(), "T")

    assert "| canary | 0 | 0 | область без кейсов |" in text
    assert "### canary" in text
    assert "Область без кейсов." in text.split("### canary")[1]


def test_case_without_risk_listed(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-101", "backup", "Approved", priority="P1")  # без risk

    text = cm.render(cm.collect(), "T")

    section = text.split("### backup")[1]
    assert "кейсы без risk: TC-101" in section


def test_risk_without_cases(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _risk_table(repo.root, [("R-01", "DATA", "риск раз"), ("R-02", "TECH", "риск два")])
    _tc(repo.root, "TC-102", "backup", "Automated", priority="P0", risk="R-01")

    text = cm.render(cm.collect(), "T")

    risk_section = text.split("## Риски")[1].split("## Области")[0]
    assert "| R-01 | DATA | backup:TC-102 |" in risk_section
    assert "| R-02 | TECH | риск не покрыт дизайном |" in risk_section


def test_last_green_run_degraded_to_global(repo, monkeypatch):
    """Схема run не связывает прогон ни с конкретным TC, ни с областью —
    деградация до глобального последнего зелёного прогона, честно помечена."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-103", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-001", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         passed=5, failed=0)
    _run(repo.root, "RUN-002", suite="regression", status="Closed", updated="2026-07-05T00:00:00Z",
         passed=3, failed=1)  # красный, не должен быть выбран как last_green

    text = cm.render(cm.collect(), "T")

    section = text.split("### backup")[1]
    assert "last_green_run: RUN-001" in section
    assert "деградировано до ГЛОБАЛЬНОГО прогона" in section
    assert "RUN-002" not in section


def test_last_green_run_none_when_no_green_runs(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-104", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-003", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         passed=0, failed=1)

    text = cm.render(cm.collect(), "T")

    section = text.split("### backup")[1]
    assert "last_green_run: нет зелёных прогонов" in section


def test_coverage_status_none_partial_full(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-110", "a-none", "Review", priority="P1")
    _tc(repo.root, "TC-111", "a-partial", "Approved", priority="P1")
    _tc(repo.root, "TC-112", "a-partial", "Automated", priority="P1")
    _tc(repo.root, "TC-113", "a-full", "Automated", priority="P1")

    text = cm.render(cm.collect(), "T")

    assert "| a-none | 1 | 0 | none |" in text
    assert "| a-partial | 2 | 1 | partial |" in text
    assert "| a-full | 1 | 1 | designed-full |" in text


def test_p0_p1_not_automated_listed(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-120", "rating", "Approved", priority="P0", risk="R-04")
    _tc(repo.root, "TC-121", "rating", "Automated", priority="P0", risk="R-04")
    _tc(repo.root, "TC-122", "rating", "Approved", priority="P2", risk="R-04")  # не P0/P1

    text = cm.render(cm.collect(), "T")

    section = text.split("### rating")[1]
    assert "P0/P1 не в Automated: TC-120 [P0, Approved]" in section
    assert "TC-122" not in section


def test_idempotent_same_state(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-130", "smoke", "Automated", priority="P0", risk="R-01")

    a = cm.render(cm.collect(), "T")
    b = cm.render(cm.collect(), "T")
    assert a == b


def test_automated_by_listed(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-140", "smoke", "Automated", priority="P0", risk="R-01",
        automated_by="framework/tests/test_smoke.py::test_x")

    text = cm.render(cm.collect(), "T")

    section = text.split("### smoke")[1]
    assert "framework/tests/test_smoke.py::test_x" in section


def test_risk_catalog_fallback_when_doc_missing(repo, monkeypatch):
    """§5 не найден (док отсутствует/переименован) — явная fallback-строка,
    не падение (ревью N1: главный риск диффа — хрупкость парсинга прозы)."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-150", "smoke", "Automated", priority="P0", risk="R-01")
    # docs/01-test-strategy.md намеренно НЕ создаётся

    text = cm.render(cm.collect(), "T")

    assert "| — | — | docs/01-test-strategy.md §5 не найден/не распознан |" in text


def test_multi_risk_field_indexed_for_each_id(repo, monkeypatch):
    """Поле risk с несколькими id («R-01, R-02») попадает в обратный индекс
    по КАЖДОМУ риску (ревью N2: match терял все id после первого)."""
    _patch(repo, monkeypatch)
    _risk_table(repo.root, [("R-01", "DATA", "риск раз"), ("R-02", "TECH", "риск два")])
    _tc(repo.root, "TC-151", "backup", "Automated", priority="P0", risk="R-01, R-02")

    text = cm.render(cm.collect(), "T")

    risk_section = text.split("## Риски")[1].split("## Области")[0]
    assert "| R-01 | DATA | backup:TC-151 |" in risk_section
    assert "| R-02 | TECH | backup:TC-151 |" in risk_section


# --- E4 (Этап 4 п.12 uplift): last_green_run per-TC из tc_results ---

def test_no_run_carries_tc_results_flags_detector_but_keeps_fallback(repo, monkeypatch):
    """Ни один run не несёт tc_results — область/last_green_run остаются
    прежним глобальным поведением (без per-TC секции), НО детекторная строка
    всё равно ловит этот вырожденный случай (спека п.4: «или все без поля»,
    подтверждено DoD координатора для боевых run'ов без tc_results).

    Baseline-случай (ни один run не несёт tc_results вообще) — отдельная
    формулировка «поле ещё не внедрено», не «свежие» (e4-charter-lock-reaper
    п.4: «свежий» вводит в заблуждение, когда baseline отсутствует у ВСЕХ)."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-160", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-500", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z")

    text = cm.render(cm.collect(), "T")

    assert "прогоны без tc_results (поле ещё не внедрено): RUN-500" in text
    assert "свежие прогоны без tc_results" not in text
    section = text.split("### backup")[1]
    assert "per-TC last green" not in section
    assert "деградировано до ГЛОБАЛЬНОГО прогона" in section


def test_per_tc_last_green_picked_for_automated_case(repo, monkeypatch):
    """Хотя бы один run несёт tc_results — для Automated-кейса берём последний
    (по updated) run, где tc_results[<TC-id>] == passed."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-200", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-600", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         tc_results={"TC-200": "passed"})
    _run(repo.root, "RUN-601", suite="regression", status="Closed", updated="2026-07-05T00:00:00Z",
         tc_results={"TC-200": "passed"})

    text = cm.render(cm.collect(), "T")
    section = text.split("### backup")[1]

    assert "per-TC last green:" in section
    assert "TC-200: RUN-601 (updated: 2026-07-05T00:00:00Z)" in section
    assert "RUN-600" not in section.split("per-TC last green:")[1].split("\n")[1]


def test_per_tc_no_passed_entry_is_explicit(repo, monkeypatch):
    """Automated-кейс без единого passed-вхождения в tc_results — явная строка
    «нет зелёного per-TC», не молчаливый пропуск."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-201", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-610", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         tc_results={"TC-201": "failed"})

    text = cm.render(cm.collect(), "T")
    section = text.split("### backup")[1]

    assert "TC-201: нет зелёного per-TC" in section


def test_non_automated_case_excluded_from_per_tc_section(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-202", "backup", "Approved", priority="P1", risk="R-01")
    _run(repo.root, "RUN-620", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         tc_results={"TC-202": "passed"})

    text = cm.render(cm.collect(), "T")
    section = text.split("### backup")[1]

    assert "per-TC last green:" in section
    assert "нет Automated-кейсов" in section
    assert "TC-202" not in section.split("per-TC last green:")[1]


def test_newer_runs_without_tc_results_flagged_by_detector(repo, monkeypatch):
    """Дисциплина: если существует run НОВЕЕ самого свежего run-с-tc_results —
    строка «свежие прогоны без tc_results: RUN-...» в файле."""
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-210", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-700", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         tc_results={"TC-210": "passed"})
    _run(repo.root, "RUN-701", suite="regression", status="Closed", updated="2026-07-10T00:00:00Z")

    text = cm.render(cm.collect(), "T")

    assert "свежие прогоны без tc_results: RUN-701" in text


def test_no_newer_runs_without_tc_results_no_detector_line(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _tc(repo.root, "TC-211", "backup", "Automated", priority="P0", risk="R-01")
    _run(repo.root, "RUN-710", suite="smoke", status="Closed", updated="2026-07-01T00:00:00Z",
         tc_results={"TC-211": "passed"})

    text = cm.render(cm.collect(), "T")

    assert "свежие прогоны без tc_results" not in text


# --- trace-matrix диспатч 1 (§1c спеки): «Фичи → покрытие» / «без единого кейса» ---

def _registry(root: Path, commit: str | None, features: list[dict]) -> Path:
    import yaml
    p = root / "docs" / "feature-registry.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    doc: dict = {"features": features}
    if commit is not None:
        doc["inventoried_at_commit"] = commit
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


def _aut(root: Path, source_commit: str) -> Path:
    p = root / "state" / "app-under-test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"app: ao3-wrapper\nsource_commit: {source_commit}\nversion_code: 1\n",
                 encoding="utf-8")
    return p


def _tc_features(root: Path, key: str, area: str, status: str, features: list[str],
                  priority: str = "P1") -> Path:
    feat_line = "features: [" + ", ".join(features) + "]\n" if features else ""
    text = (
        f"---\nid: {key}\ntitle: TC {key}\narea: {area}\npriority: {priority}\n"
        f"status: {status}\n{feat_line}updated: \"2026-07-01T00:00:00Z\"\nlock: \"\"\n---\n\n# {key}\n\nтело\n"
    )
    p = root / "test-cases" / area / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_feature_covered_by_case_listed_with_area_id_status(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _registry(repo.root, "abc123", [
        {"id": "browse-deep-links", "title": "Deep links", "screen": "browse", "source": "x.kt"},
    ])
    _tc_features(repo.root, "TC-300", "browser", "Approved", features=["browse-deep-links"])

    text = cm.render(cm.collect(), "T")
    section = text.split("## Фичи → покрытие")[1].split("## Фичи без единого кейса")[0]

    assert "| browse-deep-links | browse | browser:TC-300[Approved] |" in section


def test_feature_without_case_listed_in_uncovered_section(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _registry(repo.root, "abc123", [
        {"id": "browse-deep-links", "title": "Deep links", "screen": "browse", "source": "x.kt"},
        {"id": "browse-tap-to-scroll", "title": "Tap to scroll", "screen": "browse", "source": "y.js"},
    ])
    _tc_features(repo.root, "TC-301", "browser", "Approved", features=["browse-deep-links"])

    text = cm.render(cm.collect(), "T")

    assert "| browse-deep-links | browse | browser:TC-301[Approved] |" in text
    uncovered = text.split("## Фичи без единого кейса")[1]
    assert "browse-tap-to-scroll" in uncovered
    assert "Tap to scroll" in uncovered
    assert "browse-deep-links" not in uncovered


def test_feature_registry_missing_shows_placeholder_in_both_sections(repo, monkeypatch):
    _patch(repo, monkeypatch)
    # docs/feature-registry.yaml намеренно не создаётся
    _tc(repo.root, "TC-302", "smoke", "Automated", priority="P0", risk="R-01")

    text = cm.render(cm.collect(), "T")

    assert "| — | — | docs/feature-registry.yaml не найден/пуст |" in text
    assert "docs/feature-registry.yaml не найден/пуст." in text.split("## Фичи без единого кейса")[1]


def test_stale_registry_detector_fires_on_commit_mismatch(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _registry(repo.root, "old-commit", [
        {"id": "browse-deep-links", "title": "Deep links", "screen": "browse", "source": "x.kt"},
    ])
    _aut(repo.root, "new-commit")

    text = cm.render(cm.collect(), "T")

    assert "⚠ реестр фич протух: сборка new-commit, реестр инвентаризован против old-commit" in text


def test_stale_registry_detector_silent_on_commit_match(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _registry(repo.root, "same-commit", [
        {"id": "browse-deep-links", "title": "Deep links", "screen": "browse", "source": "x.kt"},
    ])
    _aut(repo.root, "same-commit")

    text = cm.render(cm.collect(), "T")

    assert "реестр фич протух" not in text


def test_stale_registry_detector_silent_when_no_build_yet(repo, monkeypatch):
    """Реестр несёт inventoried_at_commit, но state/app-under-test.yaml ещё
    нет (свежий репо/тест-окружение) — детектор не должен падать/шуметь."""
    _patch(repo, monkeypatch)
    _registry(repo.root, "some-commit", [
        {"id": "browse-deep-links", "title": "Deep links", "screen": "browse", "source": "x.kt"},
    ])
    # state/app-under-test.yaml намеренно не создаётся

    text = cm.render(cm.collect(), "T")

    assert "реестр фич протух" not in text
