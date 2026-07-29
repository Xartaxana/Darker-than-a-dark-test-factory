"""Tests for scripts/enforcement_probe.py -- fail-closed pre-commit
gate protecting the enforcement chain against a fix that silently breaks
its own observer (scripts/wiring_check.py). See the module's own
docstring for the motive (Dog synk, D-0082, 2026-07-29) and port notes
(task t-342, part C; port of D:\\Improving_AI\\Operating-System-for-LLMs
tools/enforcement_probe.py / tools/test_enforcement_probe.py). Most
tests in this file exercise the OK/non-OK/crash matrix via an INJECTED
wiring-check callable (`decide()`'s design) or via a throwaway fake repo
with its own stub scripts/wiring_check.py (coverage that does not depend
on any particular real-file state), PLUS real, non-mocked end-to-end
tests that invoke the ACTUAL `python scripts/wiring_check.py --check`
against the live repo.

DoD matrix covered (к3 of the t-342 dispatch):
  - staged empty -> exit 0.
  - chain untouched -> exit 0, wiring check NOT invoked (marker-file
    proof at the CLI level, call-tracking proof at the decide() level).
  - chain touched + wiring OK -> exit 0 (injected callable AND a real,
    non-mocked subprocess run against the now-existing
    scripts/wiring_check.py --check).
  - chain touched + wiring non-OK (nonzero exit) -> exit 1.
  - chain touched + wiring crashes (raises) -> exit 1, fail-closed.
  - chain touched + scripts/wiring_check.py entirely missing (isolated
    fake repo without the file) -> exit 1, fail-closed.
  - rename of a chain member via `git mv` -> the wiring check is STILL
    invoked (class F2, critic t-339).

Run from the repo root: python -m pytest scripts/tests/test_enforcement_probe.py -q
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import enforcement_probe as enforcement_probe

SOURCE_SCRIPT = Path(__file__).resolve().parent.parent / "enforcement_probe.py"

_WIRING_OK_BODY = textwrap.dedent(
    """
    import pathlib
    pathlib.Path(__file__).resolve().parent.joinpath(".wiring_invoked_marker").write_text("x")
    print("wiring ok")
    """
)

_WIRING_FAIL_BODY = textwrap.dedent(
    """
    import pathlib
    import sys
    pathlib.Path(__file__).resolve().parent.joinpath(".wiring_invoked_marker").write_text("x")
    print("WIRING PROBLEM: pre-commit hook missing", file=sys.stderr)
    sys.exit(1)
    """
)


def _git(repo, *args):
    subprocess.run(["git"] + list(args), cwd=repo, check=True, capture_output=True)


def _init_fake_repo(tmp_path, wiring_check_body=None):
    """A throwaway repo (its own .git, .claude/, .githooks/, scripts/)
    so the CLI-level tests never touch this real repo's git index.
    The probe script determines its own REPO from `__file__`, so it is
    COPIED into the fake repo's scripts/ -- running the copy makes
    REPO resolve to the fake repo, not this one."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".githooks").mkdir(parents=True)
    (repo / ".claude").mkdir(parents=True)
    (repo / "scripts" / "enforcement_probe.py").write_text(
        SOURCE_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / ".claude" / "settings.json").write_text(
        '{"hooks": {"PreToolUse": [{"hooks": '
        '[{"type": "command", "command": "python scripts/dummy_hook.py"}]}]}}',
        encoding="utf-8",
    )
    (repo / ".githooks" / "pre-commit").write_text(
        "#!/bin/sh\npython scripts/journal_validator_stub.py\n", encoding="utf-8"
    )
    (repo / "scripts" / "dummy_hook.py").write_text("print('dummy')\n", encoding="utf-8")
    (repo / "scripts" / "journal_validator_stub.py").write_text(
        "print('ok')\n", encoding="utf-8"
    )
    if wiring_check_body is not None:
        (repo / "scripts" / "wiring_check.py").write_text(wiring_check_body, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "probe-test@example.com")
    _git(repo, "config", "user.name", "probe-test")
    return repo


def _run_probe(repo):
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "enforcement_probe.py")],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------
# decide() -- pure decision core, injected wiring-check callable
# ---------------------------------------------------------------------


def test_decide_empty_staged_exit0_runner_not_called():
    called = []

    def runner():
        called.append(1)
        return True, ""

    exit_code, message = enforcement_probe.decide([], {"a"}, runner)
    assert exit_code == 0
    assert message == ""
    assert called == []


def test_decide_chain_untouched_exit0_runner_not_called():
    called = []

    def runner():
        called.append(1)
        return True, ""

    exit_code, message = enforcement_probe.decide(
        ["README.md"], {".claude/settings.json"}, runner
    )
    assert exit_code == 0
    assert message == ""
    assert called == []


def test_decide_chain_touched_wiring_ok_exit0():
    exit_code, message = enforcement_probe.decide(
        [".claude/settings.json"], {".claude/settings.json"}, lambda: (True, "")
    )
    assert exit_code == 0
    assert message == ""


def test_decide_chain_touched_wiring_not_ok_exit1():
    exit_code, message = enforcement_probe.decide(
        [".claude/settings.json"],
        {".claude/settings.json"},
        lambda: (False, "missing pre-commit hook"),
    )
    assert exit_code == 1
    assert "missing pre-commit hook" in message


def test_decide_chain_touched_wiring_crashes_exit1_fail_closed():
    def runner():
        raise RuntimeError("boom")

    exit_code, message = enforcement_probe.decide(
        [".githooks/pre-commit"], {".githooks/pre-commit"}, runner
    )
    assert exit_code == 1
    assert "boom" in message


def test_decide_multiple_staged_only_some_touch_chain():
    exit_code, message = enforcement_probe.decide(
        ["README.md", ".claude/settings.json", "docs/notes.md"],
        {".claude/settings.json"},
        lambda: (True, ""),
    )
    assert exit_code == 0


def test_intersect_case_insensitive_match():
    touched = enforcement_probe._intersect(
        ["Scripts/Wiring_Check.py"], {"scripts/wiring_check.py"}
    )
    assert touched == ["Scripts/Wiring_Check.py"]


# ---------------------------------------------------------------------
# _chain_paths() / _referenced_tool_paths() -- dynamic chain building,
# read-only against the REAL repo's actual hook registrations.
# ---------------------------------------------------------------------


def test_referenced_tool_paths_extracts_from_text():
    text = 'blah "command": "python scripts/foo_bar.py" more python scripts/baz.py end'
    paths = enforcement_probe._referenced_tool_paths(text)
    assert paths == {"scripts/foo_bar.py", "scripts/baz.py"}


def test_referenced_tool_paths_empty_text_empty_set():
    assert enforcement_probe._referenced_tool_paths("") == set()


def test_chain_paths_includes_known_repo_hooks():
    chain = enforcement_probe._chain_paths()
    # Always-included anchors (design point 2).
    assert ".claude/settings.json" in chain
    assert "scripts/wiring_check.py" in chain
    # Referenced from .claude/settings.json's actual hook commands.
    assert "scripts/hygiene_gate.py" in chain
    # Referenced from .githooks/pre-commit and commit-msg.
    assert "scripts/escape_check.py" in chain
    assert "scripts/mechanism_gate.py" in chain
    # .githooks/* files themselves, by relative path.
    assert ".githooks/pre-commit" in chain
    assert ".githooks/commit-msg" in chain


def test_githooks_files_recursive_walk(tmp_path, monkeypatch):
    # F9(г) (critic t-339): .githooks/ is walked RECURSIVELY, not just
    # its top level -- a nested file must be found too.
    githooks_dir = tmp_path / ".githooks"
    (githooks_dir / "lib").mkdir(parents=True)
    (githooks_dir / "pre-commit").write_text("x", encoding="utf-8")
    (githooks_dir / "lib" / "helper.sh").write_text("y", encoding="utf-8")
    monkeypatch.setattr(enforcement_probe, "REPO", str(tmp_path))
    monkeypatch.setattr(enforcement_probe, "GITHOOKS_DIR", str(githooks_dir))
    relpaths = sorted(rel for rel, _abs in enforcement_probe._githooks_files())
    assert relpaths == [".githooks/lib/helper.sh", ".githooks/pre-commit"]


def test_chain_paths_includes_nested_githooks_file(tmp_path, monkeypatch):
    githooks_dir = tmp_path / ".githooks"
    (githooks_dir / "lib").mkdir(parents=True)
    (githooks_dir / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    (githooks_dir / "lib" / "helper.sh").write_text("# nested\n", encoding="utf-8")
    monkeypatch.setattr(enforcement_probe, "REPO", str(tmp_path))
    monkeypatch.setattr(enforcement_probe, "GITHOOKS_DIR", str(githooks_dir))
    monkeypatch.setattr(
        enforcement_probe, "SETTINGS_PATH", str(tmp_path / "does-not-exist.json")
    )
    chain = enforcement_probe._chain_paths()
    assert ".githooks/pre-commit" in chain
    assert ".githooks/lib/helper.sh" in chain


def test_githooks_files_missing_dir_yields_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(enforcement_probe, "GITHOOKS_DIR", str(tmp_path / "no-such-dir"))
    assert list(enforcement_probe._githooks_files()) == []


# ---------------------------------------------------------------------
# _staged_files() -- isolated against a throwaway git repo (never the
# real repo's index).
# ---------------------------------------------------------------------


def test_staged_files_reads_real_staged_set(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@b.c")
    _git(repo, "config", "user.name", "t")
    (repo / "foo.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "foo.txt")
    monkeypatch.setattr(enforcement_probe, "REPO", str(repo))
    assert enforcement_probe._staged_files() == ["foo.txt"]


def test_staged_files_empty_when_nothing_staged(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    monkeypatch.setattr(enforcement_probe, "REPO", str(repo))
    assert enforcement_probe._staged_files() == []


def test_staged_files_git_failure_returns_empty_list(tmp_path, monkeypatch):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setattr(enforcement_probe, "REPO", str(not_a_repo))
    assert enforcement_probe._staged_files() == []


def test_staged_files_rename_reports_both_old_and_new_paths(tmp_path, monkeypatch):
    # F2 (critic t-339): --no-renames must make a `git mv` of a
    # same-content file report BOTH the old and the new path as
    # separate name-only lines, not collapse to a single "new path
    # only" line (which would hide the old chain member entirely).
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@b.c")
    _git(repo, "config", "user.name", "t")
    (repo / "old_name.txt").write_text("identical content\n" * 5, encoding="utf-8")
    _git(repo, "add", "old_name.txt")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "mv", "old_name.txt", "new_name.txt")
    monkeypatch.setattr(enforcement_probe, "REPO", str(repo))
    staged = enforcement_probe._staged_files()
    assert "old_name.txt" in staged
    assert "new_name.txt" in staged


# ---------------------------------------------------------------------
# real, NON-MOCKED subprocess invocation of the now-existing
# scripts/wiring_check.py --check against the actual live repo -- proves
# the "chain touched + wiring actually OK -> exit 0" cell of the DoD
# matrix with a real run, not only via the injected-callable tests
# above. `decide()` is called directly with a fabricated (staged, chain)
# pair that FORCES an intersection -- no git staging happens, nothing in
# the real repo is touched -- while `run_wiring_check` is
# `_default_run_wiring_check` UNCHANGED, which subprocess-launches the
# real `python scripts/wiring_check.py --check` against this repo's
# actual current state (empirically WIRING: OK at the time of this
# delivery, see the delivery report's witness).
# ---------------------------------------------------------------------


def test_real_wiring_check_ok_real_run():
    exit_code, message = enforcement_probe.decide(
        ["scripts/wiring_check.py"],
        {"scripts/wiring_check.py"},
        enforcement_probe._default_run_wiring_check,
    )
    assert exit_code == 0
    assert message == ""


def test_default_run_wiring_check_real_subprocess_returns_ok_tuple():
    ok, detail = enforcement_probe._default_run_wiring_check()
    assert ok is True
    assert "WIRING: OK" in detail


# ---------------------------------------------------------------------
# CLI / subprocess-level end-to-end matrix (к3), against a fully
# isolated fake repo -- the real script logic, real git, real subprocess
# invocation of scripts/wiring_check.py (a stub, at this level -- the
# stub bodies below do not read argv, so passing --check to them is a
# harmless no-op, same as the real invocation).
# ---------------------------------------------------------------------


def test_cli_empty_staged_exit0(tmp_path):
    repo = _init_fake_repo(tmp_path, wiring_check_body=None)
    result = _run_probe(repo)
    assert result.returncode == 0


def test_cli_chain_untouched_exit0_wiring_not_invoked(tmp_path):
    repo = _init_fake_repo(tmp_path, wiring_check_body=_WIRING_OK_BODY)
    (repo / "scripts" / "unrelated.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "scripts/unrelated.py")
    result = _run_probe(repo)
    assert result.returncode == 0
    assert not (repo / "scripts" / ".wiring_invoked_marker").exists()


def test_cli_chain_touched_wiring_ok_exit0(tmp_path):
    repo = _init_fake_repo(tmp_path, wiring_check_body=_WIRING_OK_BODY)
    _git(repo, "add", ".claude/settings.json")
    result = _run_probe(repo)
    assert result.returncode == 0
    assert (repo / "scripts" / ".wiring_invoked_marker").exists()


def test_cli_chain_touched_wiring_fails_exit1(tmp_path):
    repo = _init_fake_repo(tmp_path, wiring_check_body=_WIRING_FAIL_BODY)
    _git(repo, "add", ".githooks/pre-commit")
    result = _run_probe(repo)
    assert result.returncode == 1
    assert "WIRING PROBLEM" in result.stderr


def test_cli_chain_touched_wiring_check_missing_exit1_fail_closed(tmp_path):
    # Isolated fake repo without scripts/wiring_check.py at all -- the
    # probe must fail closed (exit 1), not pass silently, when the
    # observer it depends on cannot even be launched.
    repo = _init_fake_repo(tmp_path, wiring_check_body=None)
    _git(repo, "add", ".claude/settings.json")
    result = _run_probe(repo)
    assert result.returncode == 1


def test_cli_chain_file_renamed_via_git_mv_wiring_still_invoked(tmp_path):
    # F2 (critic t-339): `git mv` of a chain member (scripts/dummy_hook.py,
    # referenced by .claude/settings.json's own hook command) must still
    # register as "chain touched" -- with git's DEFAULT rename detection,
    # `--name-only` can collapse a same-content rename into a SINGLE line
    # naming only the NEW path (not itself a chain member), silently
    # hiding that the OLD (chain) path was removed. `--no-renames` (see
    # `_staged_files`) forces old+new as two separate name-only lines, so
    # the old chain path is still visible to the intersection check.
    repo = _init_fake_repo(tmp_path, wiring_check_body=_WIRING_OK_BODY)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    _git(repo, "mv", "scripts/dummy_hook.py", "scripts/dummy_hook_renamed.py")
    result = _run_probe(repo)
    assert result.returncode == 0
    assert (repo / "scripts" / ".wiring_invoked_marker").exists()


def test_cli_referenced_tool_touched_via_githooks_script_exit1_when_missing(tmp_path):
    # A scripts/*.py file referenced from .githooks/pre-commit (not
    # settings.json) also counts as chain-touched: the fake repo's
    # .githooks/pre-commit references "scripts/journal_validator_stub.py"
    # (see _init_fake_repo) -- staging exactly that file must touch the
    # chain, and with scripts/wiring_check.py missing, fail closed.
    repo = _init_fake_repo(tmp_path, wiring_check_body=None)
    _git(repo, "add", "scripts/journal_validator_stub.py")
    result = _run_probe(repo)
    assert result.returncode == 1
