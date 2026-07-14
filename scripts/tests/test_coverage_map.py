"""Юнит-тесты coverage_map (scripts/coverage_map.py)."""
from __future__ import annotations

from pathlib import Path

import coverage_map as cm


def _patch(repo, monkeypatch) -> None:
    monkeypatch.setattr(cm, "REPO", repo.root, raising=True)
    monkeypatch.setattr(cm, "OUT_PATH", repo.root / "state" / "coverage-map.md", raising=True)
    monkeypatch.setattr(cm, "RISK_DOC_PATH", repo.root / "docs" / "01-test-strategy.md", raising=True)


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
         passed: int = 1, failed: int = 0) -> Path:
    text = (
        f"---\nid: {key}\ntitle: Прогон {key}\nsuite: {suite}\nstatus: {status}\n"
        f"totals: {{ passed: {passed}, failed: {failed} }}\n"
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
