"""Тесты scripts/wiring_check.py — SessionStart wiring-integrity check
(порт wiring-блока tools/session_context.py OS-репо, задача os-port-0722)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import wiring_check as wc

SCRIPT_PATH = Path(wc.__file__).resolve()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_hook(path: Path, executable: bool) -> None:
    _write(path, "#!/bin/sh\necho ok\n")
    # На POSIX git молча игнорирует хук без exec-бита (живой инцидент
    # 2026-07-23, облачный клон) — «полностью прошитый» хук обязан его
    # нести; на Windows бита нет, chmod — no-op для проверки.
    if executable and os.name == "posix":
        path.chmod(0o755)


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=True)


def _init_repo_with_hooks(tmp_path, hooks_path_value=".githooks",
                          make_commit_msg=True, make_pre_commit=True,
                          executable=True):
    _git("init", "-q", cwd=tmp_path)
    if hooks_path_value is not None:
        _git("config", "core.hooksPath", hooks_path_value, cwd=tmp_path)
    if make_commit_msg:
        _write_hook(tmp_path / ".githooks" / "commit-msg", executable)
    if make_pre_commit:
        _write_hook(tmp_path / ".githooks" / "pre-commit", executable)
    return tmp_path


# ---------------------------------------------------------------------------
# _ascii_sanitize -- boundary tests (introduced limit: max_len)
# ---------------------------------------------------------------------------

def test_ascii_sanitize_passthrough_for_plain_ascii():
    assert wc._ascii_sanitize("hello", 80) == "hello"


def test_ascii_sanitize_escapes_non_ascii():
    out = wc._ascii_sanitize("привет", 80)
    assert out.isascii()
    assert "\\u" in out


def test_ascii_sanitize_boundary_exact_length_passes_unchanged():
    text = "x" * 10
    assert wc._ascii_sanitize(text, 10) == text
    assert len(wc._ascii_sanitize(text, 10)) == 10


def test_ascii_sanitize_boundary_one_over_gets_truncated():
    text = "x" * 11
    out = wc._ascii_sanitize(text, 10)
    assert len(out) == 10
    assert out.endswith("...")
    assert out == "x" * 7 + "..."


def test_ascii_sanitize_non_string_input():
    assert wc._ascii_sanitize(12345, 80) == "12345"


# ---------------------------------------------------------------------------
# git_hooks_channel
# ---------------------------------------------------------------------------

def test_git_hooks_channel_fully_wired_no_warnings(tmp_path):
    _init_repo_with_hooks(tmp_path)
    assert wc.git_hooks_channel(tmp_path) == []


def test_git_hooks_channel_hooks_path_not_set(tmp_path):
    _init_repo_with_hooks(tmp_path, hooks_path_value=None)
    warnings = wc.git_hooks_channel(tmp_path)
    assert any("core.hooksPath not set" in w for w in warnings)


def test_git_hooks_channel_hooks_path_points_elsewhere(tmp_path):
    _init_repo_with_hooks(tmp_path, hooks_path_value="somewhere-else")
    warnings = wc.git_hooks_channel(tmp_path)
    assert any("does not resolve to" in w for w in warnings)


def test_git_hooks_channel_missing_pre_commit_file(tmp_path):
    _init_repo_with_hooks(tmp_path, make_pre_commit=False)
    warnings = wc.git_hooks_channel(tmp_path)
    assert any("pre-commit" in w and "missing" in w for w in warnings)
    assert not any("commit-msg" in w and "missing" in w for w in warnings)


def test_git_hooks_channel_missing_both_hook_files(tmp_path):
    _init_repo_with_hooks(tmp_path, make_commit_msg=False, make_pre_commit=False)
    warnings = wc.git_hooks_channel(tmp_path)
    assert sum("missing" in w for w in warnings) == 2


@pytest.mark.skipif(os.name != "posix",
                    reason="exec-бит осмыслен только на POSIX")
def test_git_hooks_channel_non_executable_hooks_warn(tmp_path):
    # Живой класс 2026-07-23: файлы на месте, hooksPath верен, но git
    # молча игнорирует неисполняемые хуки — прежний is_file()-чек давал
    # false-OK, механизменный коммит прошёл без гейта.
    _init_repo_with_hooks(tmp_path, executable=False)
    warnings = wc.git_hooks_channel(tmp_path)
    assert sum("not executable" in w for w in warnings) == 2
    assert not any("missing" in w for w in warnings)


def test_git_hooks_channel_index_mode_644_warns_cross_platform(tmp_path):
    # Порт формы OS-детектора (кросс-репо остаток, закрыт 2026-07-28):
    # индексная мода не зависит от хоста — hook, затреканный 100644,
    # молча игнорируется git'ом в любом СВЕЖЕМ POSIX-чекауте, даже если
    # на Windows-хосте X_OK-проверка самонейтрализуется.
    _init_repo_with_hooks(tmp_path)
    _git("add", ".githooks", cwd=tmp_path)
    _git("update-index", "--chmod=-x",
         ".githooks/commit-msg", ".githooks/pre-commit", cwd=tmp_path)
    warnings = wc.git_hooks_channel(tmp_path)
    assert sum("index mode 100644" in w for w in warnings) == 2


def test_git_hooks_channel_index_mode_755_no_warning(tmp_path):
    _init_repo_with_hooks(tmp_path)
    _git("add", ".githooks", cwd=tmp_path)
    _git("update-index", "--chmod=+x",
         ".githooks/commit-msg", ".githooks/pre-commit", cwd=tmp_path)
    warnings = wc.git_hooks_channel(tmp_path)
    assert not any("index mode" in w for w in warnings)


def test_git_hooks_channel_untracked_hooks_no_index_warning(tmp_path):
    # Untracked-хуки работают локально — индексная проверка молчит
    # (граница проверки: дисциплина трекинга — не её забота).
    _init_repo_with_hooks(tmp_path)
    warnings = wc.git_hooks_channel(tmp_path)
    assert not any("index mode" in w for w in warnings)


@pytest.mark.skipif(sys.platform != "win32", reason="drive-letter case only exists on Windows")
def test_git_hooks_channel_case_insensitive_and_slash_tolerant(tmp_path):
    # Windows: core.hooksPath can be configured/echoed with a different
    # slash style and drive-letter case than what Path.resolve() would
    # produce; the comparison must not false-positive-warn on that alone.
    _init_repo_with_hooks(tmp_path, hooks_path_value=None)
    absolute_githooks = str((tmp_path / ".githooks").resolve())
    variant = absolute_githooks.replace("\\", "/")
    if variant[:1].isalpha() and variant[1:2] == ":":
        variant = variant[0].upper() + variant[1:] if variant[0].islower() \
            else variant[0].lower() + variant[1:]
    _git("config", "core.hooksPath", variant, cwd=tmp_path)
    warnings = wc.git_hooks_channel(tmp_path)
    assert not any("does not resolve to" in w for w in warnings)


def test_git_hooks_channel_git_binary_missing_or_erroring(tmp_path, monkeypatch):
    def _boom(*a, **kw):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(wc.subprocess, "run", _boom, raising=True)
    warnings = wc.git_hooks_channel(tmp_path)
    assert len(warnings) == 1
    assert "git config core.hooksPath failed" in warnings[0]


# ---------------------------------------------------------------------------
# harness_channel
# ---------------------------------------------------------------------------

def _settings(tmp_path, commands):
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": c}
                                              for c in commands]}
            ]
        }
    }
    _write(tmp_path / ".claude" / "settings.json", json.dumps(settings))


def test_harness_channel_importable_script_counts_ok(tmp_path):
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    warnings, count = wc.harness_channel(tmp_path)
    assert warnings == []
    assert count == 1


def test_harness_channel_missing_hook_file(tmp_path):
    _settings(tmp_path, ["python scripts/does_not_exist.py"])
    warnings, count = wc.harness_channel(tmp_path)
    assert any("hook file not found" in w for w in warnings)
    assert count == 0


def test_harness_channel_import_raises_becomes_warning_not_crash(tmp_path):
    _write(tmp_path / "scripts" / "boom.py", "raise RuntimeError('boom at import time')\n")
    _settings(tmp_path, ["python scripts/boom.py"])
    warnings, count = wc.harness_channel(tmp_path)
    assert any("import failed" in w and "boom.py" in w for w in warnings)
    assert count == 0


def test_harness_channel_unparsed_command_form(tmp_path):
    _settings(tmp_path, ["python tools/other.py", "python scripts/x.py --flag"])
    warnings, count = wc.harness_channel(tmp_path)
    assert sum("unparsed hook command" in w for w in warnings) == 2


def test_harness_channel_absolute_form_inside_root_accepted(tmp_path):
    """Абсолютный твин канона (введён 2026-08-09 после живого cwd-инцидента):
    'python <root>/scripts/<file>.py' принимается и проверяется, если путь
    нормализуется ВНУТРЬ scripts/ этого корня (любой стиль слэшей)."""
    _write(tmp_path / "scripts" / "abs_hook.py", "VALUE = 1\n")
    abs_cmd = f"python {str(tmp_path / 'scripts' / 'abs_hook.py').replace(chr(92), '/')}"
    _settings(tmp_path, [abs_cmd])
    warnings, count = wc.harness_channel(tmp_path)
    assert warnings == []
    assert count == 1


def test_harness_channel_foreign_absolute_path_stays_unparsed(tmp_path):
    """Абсолютный путь ВНЕ scripts/ этого корня — честный 'unparsed', не
    догадка (граница за формой: чужой корень)."""
    foreign = tmp_path / "elsewhere" / "scripts" / "x.py"
    _settings(tmp_path, [f"python {foreign}"])
    warnings, count = wc.harness_channel(tmp_path)
    assert sum("unparsed hook command" in w for w in warnings) == 1
    assert count == 0


def test_harness_channel_missing_settings_file(tmp_path):
    warnings, count = wc.harness_channel(tmp_path)
    assert any("not readable" in w for w in warnings)
    assert count == 0


def test_harness_channel_malformed_settings_json(tmp_path):
    _write(tmp_path / ".claude" / "settings.json", "{not json")
    warnings, count = wc.harness_channel(tmp_path)
    assert any("not valid JSON" in w for w in warnings)
    assert count == 0


def test_harness_channel_empty_hooks_section(tmp_path):
    _write(tmp_path / ".claude" / "settings.json", json.dumps({"hooks": {}}))
    warnings, count = wc.harness_channel(tmp_path)
    assert warnings == []
    assert count == 0


def test_harness_channel_duplicate_command_checked_once(tmp_path):
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py", "python scripts/good_hook.py"])
    warnings, count = wc.harness_channel(tmp_path)
    assert warnings == []
    assert count == 1


def test_harness_channel_script_with_side_effect_print_is_swallowed(tmp_path, capsys):
    _write(tmp_path / "scripts" / "noisy.py", "print('leaked at import time')\n")
    _settings(tmp_path, ["python scripts/noisy.py"])
    warnings, count = wc.harness_channel(tmp_path)
    assert warnings == []
    assert count == 1
    captured = capsys.readouterr()
    assert "leaked at import time" not in captured.out


# ---------------------------------------------------------------------------
# skills_casing_channel (task t-342, port of the HQ OS repo's
# tools/wiring_check.py skills_casing_channel() -- Dog 2026-07-25 incident,
# synk 2026-07-29).
# ---------------------------------------------------------------------------

def _track_skill(tmp_path, rel_skill_path, content="# skill\n"):
    """Writes and `git add`s a file under .claude/skills/ at the given
    repo-relative path (used to control the exact tracked CASING of the
    basename, independent of the host filesystem's own case sensitivity)."""
    p = tmp_path / rel_skill_path
    _write(p, content)
    _git("add", rel_skill_path, cwd=tmp_path)
    return p


def _init_bare_git_repo(tmp_path):
    _git("init", "-q", cwd=tmp_path)
    _git("config", "user.email", "a@b.c", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    return tmp_path


def test_skills_casing_channel_correct_case_no_warnings(tmp_path):
    _init_bare_git_repo(tmp_path)
    _track_skill(tmp_path, ".claude/skills/board/SKILL.md")
    _track_skill(tmp_path, ".claude/skills/triage/SKILL.md")
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert warnings == []
    assert ok_count == 2


def test_skills_casing_channel_wrong_case_warns(tmp_path):
    # Live index fixture ONLY -- the real .claude/skills/ index is never
    # touched by this test (DoD к1: "фикстурой/моком -- ЖИВОЙ индекс не
    # трогать").
    _init_bare_git_repo(tmp_path)
    _track_skill(tmp_path, ".claude/skills/board/skill.md")
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert ok_count == 0
    assert len(warnings) == 1
    assert "skill.md" in warnings[0]
    assert "wrong case" in warnings[0]


def test_skills_casing_channel_mixed_correct_and_wrong(tmp_path):
    _init_bare_git_repo(tmp_path)
    _track_skill(tmp_path, ".claude/skills/board/SKILL.md")
    _track_skill(tmp_path, ".claude/skills/triage/skill.md")
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert ok_count == 1
    assert len(warnings) == 1


def test_skills_casing_channel_no_skills_dir_no_warnings(tmp_path):
    _init_bare_git_repo(tmp_path)
    (tmp_path / "foo.txt").write_text("x", encoding="utf-8")
    _git("add", "foo.txt", cwd=tmp_path)
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert warnings == []
    assert ok_count == 0


def test_skills_casing_channel_non_skill_files_ignored(tmp_path):
    _init_bare_git_repo(tmp_path)
    _track_skill(tmp_path, ".claude/skills/board/reference.md")
    _track_skill(tmp_path, ".claude/skills/board/SKILL.md")
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert warnings == []
    assert ok_count == 1


def test_skills_casing_channel_git_binary_missing_or_erroring(tmp_path, monkeypatch):
    def _boom(*a, **kw):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(wc.subprocess, "run", _boom, raising=True)
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert ok_count == 0
    assert len(warnings) == 1
    assert "not verifiable" in warnings[0]


def test_skills_casing_channel_git_nonzero_exit_is_unverifiable(tmp_path):
    # Not a git repo at all -- `git ls-files` exits non-zero.
    warnings, ok_count = wc.skills_casing_channel(tmp_path)
    assert ok_count == 0
    assert len(warnings) == 1
    assert "not verifiable" in warnings[0]


def test_real_repo_skills_casing_all_correct():
    # Live index control (command hygiene п.6): compute the expected count
    # independently via the SAME `git ls-files` call/form, rather than
    # hardcoding a number that would silently drift as skills are added.
    result = subprocess.run(
        ["git", "ls-files", "--", ".claude/skills/"],
        cwd=str(wc.REPO_ROOT), capture_output=True, text=True,
    )
    expected_ok = sum(
        1 for line in result.stdout.splitlines()
        if Path(line.strip()).name == "SKILL.md"
    )
    assert expected_ok > 0  # sanity: the live repo actually has skills
    warnings, ok_count = wc.skills_casing_channel(wc.REPO_ROOT)
    assert warnings == []
    assert ok_count == expected_ok


# ---------------------------------------------------------------------------
# wiring_lines: skills-casing is wired into the combined OK line / warnings.
# ---------------------------------------------------------------------------

def test_wiring_lines_ok_line_reports_skills_casing_count(tmp_path):
    _init_repo_with_hooks(tmp_path)
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    _track_skill(tmp_path, ".claude/skills/board/SKILL.md")
    lines = wc.wiring_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0].startswith("WIRING: OK (")
    assert "skills casing: 1 ok" in lines[0]


def test_wiring_lines_reports_skills_casing_warning(tmp_path):
    _init_repo_with_hooks(tmp_path)
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    _track_skill(tmp_path, ".claude/skills/board/skill.md")
    lines = wc.wiring_lines(tmp_path)
    assert all(l.startswith("WIRING WARNING:") for l in lines)
    assert any("skill.md" in l and "wrong case" in l for l in lines)


# ---------------------------------------------------------------------------
# python_channel
# ---------------------------------------------------------------------------

def test_python_channel_finds_something_on_this_machine():
    # This test itself runs under a python interpreter, so PATH must have one.
    assert wc.python_channel() is not None


def test_python_channel_none_when_which_finds_nothing(monkeypatch):
    monkeypatch.setattr(wc.shutil, "which", lambda name: None, raising=True)
    assert wc.python_channel() is None


# ---------------------------------------------------------------------------
# wiring_lines: combined output, fail-open guarantee, exit code
# ---------------------------------------------------------------------------

def test_wiring_lines_full_ok(tmp_path):
    _init_repo_with_hooks(tmp_path)
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    lines = wc.wiring_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0].startswith("WIRING: OK (")
    assert "harness hooks: 1 files importable" in lines[0]
    assert lines[0].isascii()


def test_wiring_lines_reports_every_channel_warning(tmp_path):
    _init_repo_with_hooks(tmp_path, make_pre_commit=False)
    _settings(tmp_path, ["python scripts/missing.py"])
    lines = wc.wiring_lines(tmp_path)
    assert all(l.startswith("WIRING WARNING:") for l in lines)
    assert any("pre-commit" in l for l in lines)
    assert any("hook file not found" in l for l in lines)


def test_wiring_lines_never_raises_collapses_to_one_warning(tmp_path, monkeypatch):
    def _boom(root):
        raise ValueError("internal blowup")
    monkeypatch.setattr(wc, "git_hooks_channel", _boom, raising=True)
    lines = wc.wiring_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0].startswith("WIRING WARNING: check failed internally")


def test_wiring_lines_python_not_found_is_reported(tmp_path, monkeypatch):
    _init_repo_with_hooks(tmp_path)
    monkeypatch.setattr(wc, "python_channel", lambda: None, raising=True)
    lines = wc.wiring_lines(tmp_path)
    assert any("python not found on PATH" in l for l in lines)


def test_wiring_lines_output_line_length_capped(tmp_path):
    _init_repo_with_hooks(tmp_path)
    # Force an overlong single warning via a very long unparsed command.
    _settings(tmp_path, ["python scripts/" + ("a" * 500) + ".py extra flags here"])
    lines = wc.wiring_lines(tmp_path)
    assert all(len(l) <= wc._WIRING_LINE_MAX_LEN for l in lines)


def test_main_exits_zero_even_when_everything_is_broken(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wc, "REPO_ROOT", tmp_path, raising=True)
    code = wc.main([])
    assert code == 0


# ---------------------------------------------------------------------------
# --check mode (task t-342, part B): fail-CLOSED probe mode, vs. the
# no-flag SessionStart printer which stays fail-open (regression, к2).
# ---------------------------------------------------------------------------

def test_main_no_flag_exit0_regardless_of_warnings_sessionstart_regression(
    tmp_path, monkeypatch
):
    # Named regression test (DoD к2): the plain SessionStart contract --
    # NO flag -- must exit 0 even on a fully broken tree, byte-for-byte the
    # pre-t-342 behavior. Companion to the --check test right below, which
    # exits 1 on the SAME broken tree.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wc, "REPO_ROOT", tmp_path, raising=True)
    assert wc.main([]) == 0
    assert wc.main(["--check"]) == 1


def test_main_check_flag_exit1_when_warnings_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wc, "REPO_ROOT", tmp_path, raising=True)
    code = wc.main(["--check"])
    assert code == 1


def test_main_check_flag_exit0_when_fully_clean(tmp_path, monkeypatch):
    _init_repo_with_hooks(tmp_path)
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wc, "REPO_ROOT", tmp_path, raising=True)
    code = wc.main(["--check"])
    assert code == 0


def test_main_check_flag_position_independent(tmp_path, monkeypatch):
    # The flag is recognized by membership, not position -- mirrors how
    # `python scripts/wiring_check.py --check` puts it at argv[1] while a
    # bare `main(["--check"])` (as used above) has it at index 0.
    _init_repo_with_hooks(tmp_path)
    _write(tmp_path / "scripts" / "good_hook.py", "VALUE = 1\n")
    _settings(tmp_path, ["python scripts/good_hook.py"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wc, "REPO_ROOT", tmp_path, raising=True)
    assert wc.main(["scripts/wiring_check.py", "--check"]) == 0


def test_cli_subprocess_check_flag_smoke_live_repo():
    # Live, clean tree (real repo) -- --check must exit 0 (DoD verification
    # run 3, "python scripts/wiring_check.py --check" from the repo root).
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        cwd=str(SCRIPT_PATH.parent.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("WIRING: OK (")


# ---------------------------------------------------------------------------
# real repo: the checked-in .claude/settings.json + .githooks against the
# live tree (positive run + CLI subprocess witness)
# ---------------------------------------------------------------------------

def test_real_repo_wiring_ok():
    lines = wc.wiring_lines(wc.REPO_ROOT)
    assert len(lines) == 1
    assert lines[0].startswith("WIRING: OK ("), lines


def test_cli_subprocess_smoke():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(SCRIPT_PATH.parent.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("WIRING:")
