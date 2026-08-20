"""Юнит-тесты new_case_status_gate (scripts/new_case_status_gate.py) — на
РЕАЛЬНОМ temp-git-репозитории (спека C v2 требует живой git, не мок)."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

import new_case_status_gate as gate


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=check,
    )


def _write_case(root: Path, filename: str, *, tc_id: str = "TC-001",
                 status: str = "Draft", body: str | None = None) -> Path:
    p = root / "test-cases" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    text = body if body is not None else (
        f"---\nid: {tc_id}\ntitle: t\narea: test\npriority: P1\n"
        f"status: {status}\nupdated: \"2026-01-01T00:00:00Z\"\n---\n\n"
        f"# {tc_id}\n\nтело\n"
    )
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def git_repo(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "t@test.local")
    _git(repo_dir, "config", "user.name", "t")
    monkeypatch.setattr(gate, "REPO", repo_dir, raising=True)
    return repo_dir


def test_added_approved_test_case_blocks_commit(git_repo, capsys):
    _write_case(git_repo, "TC-001.md", tc_id="TC-001", status="Approved")
    _git(git_repo, "add", "test-cases/TC-001.md")

    rc = gate.main()

    assert rc == 1
    out = capsys.readouterr().out
    assert "TC-001.md" in out
    assert "Approved" in out


def test_added_draft_test_case_passes(git_repo, capsys):
    _write_case(git_repo, "TC-002.md", tc_id="TC-002", status="Draft")
    _git(git_repo, "add", "test-cases/TC-002.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_added_review_test_case_passes(git_repo, capsys):
    _write_case(git_repo, "TC-003.md", tc_id="TC-003", status="Review")
    _git(git_repo, "add", "test-cases/TC-003.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_non_test_cases_path_is_ignored(git_repo, capsys):
    """Added-файл ВНЕ test-cases/ (даже со status: Approved где-то в теле) —
    вне scope, `-- test-cases` фильтрует его на уровне git-вызова."""
    p = git_repo / "bugs" / "BUG-100.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\nid: BUG-100\ntitle: t\nseverity: major\nstatus: Approved\n"
        "updated: \"2026-01-01T00:00:00Z\"\n---\n\n# BUG-100\n\nтело\n",
        encoding="utf-8",
    )
    _git(git_repo, "add", "bugs/BUG-100.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_no_staged_test_cases_is_silent(git_repo, capsys):
    """Пустой diff-filter список -> rc 0 МОЛЧА (даже с другими staged-файлами)."""
    p = git_repo / "README.md"
    p.write_text("# repo\n", encoding="utf-8")
    _git(git_repo, "add", "README.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_broken_frontmatter_warns_not_blocks(git_repo, capsys):
    """Битый frontmatter (нет закрывающего `---`) -> WARN, не rc=1."""
    _write_case(git_repo, "TC-004.md", body="не frontmatter вовсе, просто текст\n")
    _git(git_repo, "add", "test-cases/TC-004.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "[WARN]" in out
    assert "TC-004.md" in out


def test_git_failure_degrades_to_warn_rc0(tmp_path, monkeypatch, capsys):
    """Не git-репозиторий вовсе (нет .git) -> git diff отказывает -> rc 0 +
    [WARN], гейт не блокирует коммит битым git (fail-open)."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setattr(gate, "REPO", not_a_repo, raising=True)

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "[WARN]" in out


def test_cyrillic_filename_approved_blocks(git_repo, capsys):
    """Кириллическое имя файла: -z NUL-разделённый вывод git — устойчив к
    quotePath-экранированию (стандартный `git diff --name-status` без -z
    квотирует не-ASCII пути в кавычки с восьмеричным экранированием)."""
    _write_case(git_repo, "ТС-500.md", tc_id="TC-500", status="Approved")
    _git(git_repo, "add", "test-cases/ТС-500.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "ТС-500.md" in out


def test_cyrillic_filename_draft_passes(git_repo, capsys):
    _write_case(git_repo, "ТС-501.md", tc_id="TC-501", status="Draft")
    _git(git_repo, "add", "test-cases/ТС-501.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_filename_with_space_approved_blocks(git_repo, capsys):
    _write_case(git_repo, "TC 502 draft.md", tc_id="TC-502", status="Approved")
    _git(git_repo, "add", "test-cases/TC 502 draft.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "TC 502 draft.md" in out


def test_empty_test_case_file_warns_not_blocks(git_repo, capsys):
    """Пустой (0 байт) добавленный файл — frontmatter не парсится -> WARN,
    не rc=1 (адверсариальный кейс спеки)."""
    p = git_repo / "test-cases" / "TC-503.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    _git(git_repo, "add", "test-cases/TC-503.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "[WARN]" in out
    assert "TC-503.md" in out


def test_frontmatter_without_status_field_blocks(git_repo, capsys):
    """Frontmatter ПАРСИТСЯ, но без поля `status` вовсе — не Draft/Review,
    значит нелегальная инициализация (адверсариальный кейс спеки, ОТЛИЧАЕТСЯ
    от битого/непарсящегося frontmatter — там WARN, здесь ERROR)."""
    body = (
        "---\nid: TC-504\ntitle: t\narea: test\npriority: P1\n"
        "updated: \"2026-01-01T00:00:00Z\"\n---\n\n# TC-504\n\nтело\n"
    )
    _write_case(git_repo, "TC-504.md", body=body)
    _git(git_repo, "add", "test-cases/TC-504.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "TC-504.md" in out


def test_modified_existing_approved_case_is_not_added_filter(git_repo, capsys):
    """Граница --diff-filter=A: файл УЖЕ существующий в HEAD (committed
    Approved), staged-модификация (не добавление) — гейт его не видит
    (это остаточный tracked-флип детектор из докстринга, не эта задача)."""
    _write_case(git_repo, "TC-505.md", tc_id="TC-505", status="Draft")
    _git(git_repo, "add", "test-cases/TC-505.md")
    _git(git_repo, "commit", "-q", "-m", "init draft")
    _write_case(git_repo, "TC-505.md", tc_id="TC-505", status="Approved")
    _git(git_repo, "add", "test-cases/TC-505.md")

    rc = gate.main()

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_multiple_added_files_lists_all_violations(git_repo, capsys):
    _write_case(git_repo, "TC-506.md", tc_id="TC-506", status="Approved")
    _write_case(git_repo, "TC-507.md", tc_id="TC-507", status="Automated")
    _write_case(git_repo, "TC-508.md", tc_id="TC-508", status="Draft")
    _git(git_repo, "add", "test-cases/TC-506.md", "test-cases/TC-507.md",
         "test-cases/TC-508.md")

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "TC-506.md" in out and "TC-507.md" in out
    assert "TC-508.md" not in out


def test_git_mv_with_status_change_is_caught_with_no_renames(git_repo, capsys):
    """C2-F1 (критик-раунд, воспроизведено): БЕЗ `--no-renames` git
    классифицирует `git mv` + правку статуса как ПЕРЕИМЕНОВАНИЕ (R),
    similarity-эвристика — такая запись НЕ матчит `--diff-filter=A` и
    полностью обходит гейт (сосед по хуку enforcement_probe.py несёт тот
    же критик-фикс F2/t-339). С `--no-renames` git репортует пару
    D(старый путь)+A(новый путь) — новый путь ловится штатно."""
    _write_case(git_repo, "TC-600.md", tc_id="TC-600", status="Draft")
    _git(git_repo, "add", "test-cases/TC-600.md")
    _git(git_repo, "commit", "-q", "-m", "draft TC-600")

    # git mv (rename) + status edit внутри ОДНОГО staged-изменения
    _git(git_repo, "mv", "test-cases/TC-600.md", "test-cases/TC-600-renamed.md")
    new_path = git_repo / "test-cases" / "TC-600-renamed.md"
    text = new_path.read_text(encoding="utf-8").replace("status: Draft", "status: Approved")
    new_path.write_text(text, encoding="utf-8")
    _git(git_repo, "add", "test-cases/TC-600-renamed.md")

    # Sanity: без --no-renames git ДЕЙСТВИТЕЛЬНО детектирует это как
    # переименование (доказывает, что сценарий уязвимости реален, не
    # гипотетичен) — по умолчанию similarity-порог git'а (50%) легко
    # преодолевается однострочной правкой в коротком файле.
    default_diff = _git(git_repo, "diff", "--cached", "--name-status",
                         "--", "test-cases")
    assert default_diff.stdout.strip().startswith("R"), default_diff.stdout

    rc = gate.main()

    out = capsys.readouterr().out
    assert rc == 1
    assert "TC-600-renamed.md" in out


def test_runs_fast_without_added_cases(git_repo):
    """Спека: без added-кейсов скрипт должен отработать <0.5s. Заведомый
    прогон на реальном (но пустом по этому измерению) git-репо."""
    p = git_repo / "README.md"
    p.write_text("# repo\n", encoding="utf-8")
    _git(git_repo, "add", "README.md")

    start = time.monotonic()
    rc = gate.main()
    elapsed = time.monotonic() - start

    assert rc == 0
    assert elapsed < 0.5, f"{elapsed:.3f}s >= 0.5s"
