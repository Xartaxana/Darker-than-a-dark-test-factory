"""Юнит-тесты impact_select (scripts/impact_select.py), e4-impact-selection шаг 1.

Классификация (ignore/wide/rules/unknown, порядок, объединение областей, TC-выборка)
тестируется напрямую на классифицирующих функциях — без git. Диапазон коммитов
(--from/--to по умолчанию, невосстановимый диапазон, реальный diff) — на
СИНТЕТИЧЕСКОМ git-репозитории в tmp_path (git init + настоящие коммиты, решение
из отчёта builder'а: реальный git вместо мока subprocess — выше достоверность
для read-only git-обвязки, тот же класс проверки, что в build_watch, но там
мокали, т.к. gradle/checkout недопустимы в тестах; тут только diff/rev-parse,
безопасно гонять по-настоящему).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import impact_select as isel

MAP_YAML = (Path(__file__).resolve().parents[2] / "state" / "impact-map.yaml").read_text(encoding="utf-8")


def _patch(repo, monkeypatch) -> None:
    monkeypatch.setattr(isel, "REPO", repo.root, raising=True)
    monkeypatch.setattr(isel, "APP", repo.root / "app-under-test", raising=True)
    monkeypatch.setattr(isel, "MAP_PATH", repo.root / "state" / "impact-map.yaml", raising=True)
    monkeypatch.setattr(isel, "AUT_PATH", repo.root / "state" / "app-under-test.yaml", raising=True)


def _write_map(repo, text: str = MAP_YAML) -> Path:
    p = repo.root / "state" / "impact-map.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _tc(root: Path, key: str, area: str, priority: str = "P1", status: str = "Automated",
        automated_by: str | None = None) -> Path:
    extra = f'automated_by: "{automated_by}"\n' if automated_by else ""
    text = (
        f"---\nid: {key}\ntitle: TC {key}\narea: {area}\npriority: {priority}\n"
        f"status: {status}\n{extra}updated: \"2026-07-01T00:00:00Z\"\nlock: \"\"\n---\n\n# {key}\n\nтело\n"
    )
    p = root / "test-cases" / area / f"{key}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --- Реальный git-репо в tmp (app-under-test/) ---

def _git(args: list[str], cwd: Path) -> str:
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    assert p.returncode == 0, f"git {args} failed: {p.stdout}\n{p.stderr}"
    return p.stdout.strip()


def _init_app_repo(root: Path) -> Path:
    app = root / "app-under-test"
    app.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=app)
    _git(["config", "user.email", "test@example.com"], cwd=app)
    _git(["config", "user.name", "Test"], cwd=app)
    return app


def _commit(app: Path, files: dict[str, str], msg: str) -> str:
    for rel, content in files.items():
        p = app / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(["add", "-A"], cwd=app)
    _git(["commit", "-q", "-m", msg], cwd=app)
    return _git(["rev-parse", "HEAD"], cwd=app)


# --- Классификация: ignore / wide / unknown / порядок / объединение областей ---

def test_ignore_matches(repo, monkeypatch):
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    cat, areas, pat = isel.classify_file("README.md", cmap)
    assert cat == "ignore" and areas == [] and pat == "*.md"


def test_ignore_glob_nested(repo, monkeypatch):
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    cat, _areas, _pat = isel.classify_file("gradle/wrapper/gradle-wrapper.properties", cmap)
    assert cat == "ignore"


def test_wide_impact_matches(repo, monkeypatch):
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    cat, areas, pat = isel.classify_file(
        "app/src/main/java/com/example/ao3_wrapper/MainActivity.kt", cmap)
    assert cat == "wide" and areas == []
    cat2, _areas2, _pat2 = isel.classify_file(
        "app/src/main/java/com/example/ao3_wrapper/data/db/AppDatabase.kt", cmap)
    assert cat2 == "wide"


def test_unknown_source_outside_map(repo, monkeypatch):
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    cat, areas, _pat = isel.classify_file(
        "app/src/main/java/com/example/ao3_wrapper/ui/newfeature/NewScreen.kt", cmap)
    assert cat == "unknown" and areas == []


def test_specific_path_wins_over_glob_of_same_folder(repo, monkeypatch):
    """RatingOverlay.kt имеет СВОЁ правило раньше по файлу карты, чем глоб
    ui/components/**, который тоже покрыл бы этот путь — карта требует, чтобы
    матчился именно специфичный путь (первое совпадение по порядку)."""
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    path = "app/src/main/java/com/example/ao3_wrapper/ui/components/RatingOverlay.kt"
    _cat, _areas, pat = isel.classify_file(path, cmap)
    assert pat == path, f"ожидали матч специфичного правила, получили паттерн {pat!r}"

    other = "app/src/main/java/com/example/ao3_wrapper/ui/components/SomeOtherWidget.kt"
    _cat2, areas2, pat2 = isel.classify_file(other, cmap)
    assert pat2 == "app/src/main/java/com/example/ao3_wrapper/ui/components/**"
    assert areas2 == ["rating", "library", "browser"]


def test_union_of_areas_across_files(repo, monkeypatch):
    _patch(repo, monkeypatch)
    cmap = isel.load_map(_write_map(repo))
    files_result = {
        "matched": [], "areas": set(), "wide": [], "unknown": [],
    }
    for f in (
        "app/src/main/java/com/example/ao3_wrapper/ui/browser/TabStrip.kt",     # tabs, browser
        "app/src/main/java/com/example/ao3_wrapper/data/repository/DownloadRepository.kt",  # downloads, library, browser
    ):
        cat, areas, pat = isel.classify_file(f, cmap)
        assert cat == "rule"
        files_result["matched"].append((f, areas, pat))
        files_result["areas"].update(areas)
    assert files_result["areas"] == {"tabs", "browser", "downloads", "library"}


# --- select()/render(): full_regression, TC-выборка по области, smoke всегда ---

def test_select_full_regression_on_wide(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _write_map(repo)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"README.md": "a"}, "init")
    c2 = _commit(app, {
        "README.md": "b",
        "app/src/main/java/com/example/ao3_wrapper/MainActivity.kt": "x",
    }, "wide change")

    cmap = isel.load_map()
    result = isel.select(c1, c2, cmap)

    assert result["full_regression"] is True
    assert any("MainActivity.kt" in f for f in result["wide"])
    assert "README.md" in result["ignored"]


def test_select_full_regression_on_unknown(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _write_map(repo)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"README.md": "a"}, "init")
    c2 = _commit(app, {
        "app/src/main/java/com/example/ao3_wrapper/ui/newfeature/NewScreen.kt": "x",
    }, "unknown source")

    cmap = isel.load_map()
    result = isel.select(c1, c2, cmap)

    assert result["full_regression"] is True
    assert result["unknown"] and "NewScreen.kt" in result["unknown"][0]


def test_select_areas_and_render_lists_tc(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _write_map(repo)
    _tc(repo.root, "TC-050", "browser", priority="P1", status="Automated",
        automated_by="framework/tests/test_x.py::test_x")
    _tc(repo.root, "TC-001", "smoke", priority="P0", status="Automated",
        automated_by="framework/tests/test_smoke.py::test_smoke")
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"README.md": "a"}, "init")
    c2 = _commit(app, {
        "app/src/main/java/com/example/ao3_wrapper/ui/browser/TabStrip.kt": "x",
    }, "tabs/browser change")

    cmap = isel.load_map()
    result = isel.select(c1, c2, cmap)
    assert result["full_regression"] is False
    assert result["areas"] == ["browser", "tabs"]

    text = isel.render(c1, c2, result)
    assert "FULL REGRESSION" not in text
    assert "### browser" in text
    assert "TC-050 [P1, Automated] automated_by: framework/tests/test_x.py::test_x" in text
    # smoke упоминается всегда, даже если сам не в затронутых областях
    assert "## smoke (гоняется на любой сборке)" in text
    assert "TC-001 [P0, Automated] automated_by: framework/tests/test_smoke.py::test_smoke" in text


def test_render_full_regression_still_mentions_smoke(repo, monkeypatch):
    _patch(repo, monkeypatch)
    _write_map(repo)
    _tc(repo.root, "TC-001", "smoke", priority="P0", status="Automated")
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"README.md": "a"}, "init")
    c2 = _commit(app, {
        "app/src/main/java/com/example/ao3_wrapper/MainActivity.kt": "x",
    }, "wide")

    cmap = isel.load_map()
    result = isel.select(c1, c2, cmap)
    text = isel.render(c1, c2, result)
    assert "FULL REGRESSION" in text
    assert "## smoke (гоняется на любой сборке)" in text
    assert "TC-001" in text.split("## smoke")[1]


# --- Диапазон по умолчанию из state/app-under-test.yaml ---

def test_default_range_no_coalesced_uses_source_commit_parent(repo, monkeypatch):
    _patch(repo, monkeypatch)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"a.txt": "1"}, "c1")
    c2 = _commit(app, {"a.txt": "2"}, "c2")
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.write_text(f'app: ao3-wrapper\nsource_commit: {c2}\n', encoding="utf-8")

    frm, to = isel.default_range()

    assert to == c2
    assert frm == c1


def test_default_range_with_coalesced_uses_first_new_parent(repo, monkeypatch):
    _patch(repo, monkeypatch)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"a.txt": "1"}, "c1")
    c2 = _commit(app, {"a.txt": "2"}, "c2 (coalesced, skipped)")
    c3 = _commit(app, {"a.txt": "3"}, "c3 (tip)")
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.write_text(
        f'app: ao3-wrapper\nsource_commit: {c3}\ncoalesced_commits: [{c2[:8]}]\n',
        encoding="utf-8")

    frm, to = isel.default_range()

    assert to == c3
    assert frm == c1


def test_default_range_unrecoverable_shallow_history(repo, monkeypatch):
    """Единственный коммит без родителя (как реальный shallow-клон app-under-test/,
    depth=1) — честный RangeError, не тихий фолбэк."""
    _patch(repo, monkeypatch)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"a.txt": "1"}, "only commit")
    aut = repo.root / "state" / "app-under-test.yaml"
    aut.write_text(f'app: ao3-wrapper\nsource_commit: {c1}\n', encoding="utf-8")

    with pytest.raises(isel.RangeError):
        isel.default_range()


def test_default_range_missing_aut_file(repo, monkeypatch):
    _patch(repo, monkeypatch)
    with pytest.raises(isel.RangeError):
        isel.default_range()


# --- main(): коды возврата ---

def test_main_unrecoverable_range_nonzero_exit(repo, monkeypatch, capsys):
    _patch(repo, monkeypatch)
    _write_map(repo)
    # state/app-under-test.yaml не создан -> default_range() бросит RangeError
    rc = isel.main([])
    assert rc != 0
    captured = capsys.readouterr()
    assert "--from" in captured.err and "--to" in captured.err


def test_main_only_from_without_to_is_error(repo, monkeypatch):
    _patch(repo, monkeypatch)
    rc = isel.main(["--from", "deadbeef"])
    assert rc != 0


def test_main_explicit_range_success(repo, monkeypatch, capsys):
    _patch(repo, monkeypatch)
    _write_map(repo)
    app = _init_app_repo(repo.root)
    c1 = _commit(app, {"README.md": "a"}, "init")
    c2 = _commit(app, {
        "app/src/main/java/com/example/ao3_wrapper/ui/browser/TabStrip.kt": "x",
    }, "tabs")

    rc = isel.main(["--from", c1, "--to", c2])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Затронутые области" in out and "browser" in out and "tabs" in out
