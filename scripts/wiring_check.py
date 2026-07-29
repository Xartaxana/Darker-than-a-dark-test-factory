"""SessionStart wiring-integrity check (task os-port-0722, port of
D:\\Improving_AI\\Operating-System-for-LLMs tools/session_context.py's
wiring block, lines ~602-895).

Four independent, read-only checks:

    (a) git-channel      -- core.hooksPath resolves to <root>/.githooks AND
                            both required git hook files exist under it
                            (commit-msg, pre-commit) AND, on POSIX, carry
                            the executable bit (git silently ignores a
                            non-executable hook -- found live 2026-07-23:
                            a cloud Linux checkout of this repo had both
                            files present but mode 100644, so a mechanism
                            commit went through with NO gate run and NO
                            warning; Windows has no exec bit, there
                            os.access(X_OK) is trivially true and the
                            check self-neutralizes).
    (b) harness-channel  -- every "python scripts/<file>.py" hook command
                            in .claude/settings.json (our pattern -- NOT
                            "tools/", the OS repo's pattern) names a file
                            that exists and imports cleanly.
    (c) skills-casing     -- every git-INDEX path under .claude/skills/
                            whose basename, lowercased, equals "skill.md"
                            is tracked as EXACTLY "SKILL.md" (task t-342,
                            port from D:\\Improving_AI\\Operating-System-for-LLMs
                            tools/wiring_check.py's skills_casing_channel(),
                            2026-07-29). See skills_casing_channel()'s own
                            docstring for the incident motive (Dog
                            2026-07-25, sibling synk 2026-07-29).
    (d) python-channel   -- shutil.which("python") finds an interpreter on
                            THIS process's PATH.

Each channel turns its OWN known failure modes into WARNING detail
strings rather than raising; the whole combination is additionally
wrapped in one outer try/except so a wiring-block failure degrades to a
single WARNING line rather than blowing up SessionStart.

Output: one line, always ASCII:

    WIRING: OK (git hooks: commit-msg, pre-commit; harness hooks: N
    importable; skills casing: M ok; python: <path>)

or one or more:

    WIRING WARNING: <fact>

CLI CONTRACT (task t-342, part B): main() with NO flag behaves BYTE-FOR-
BYTE as before -- prints the line(s) above and always returns 0 (this is
the SessionStart hook contract: a wiring-integrity check must never
block session start, fail-open). main() with `--check` prints the same
line(s) but returns 1 if at least one "WIRING WARNING:" line was printed
(fail-CLOSED), 0 if the run was fully clean -- this is the mode a
pre-commit-time caller (scripts/enforcement_probe.py) invokes to
actually gate on wiring state; the plain no-flag mode stays the
SessionStart printer and is unsuitable for that job on its own.

AUTOFIX-FACT CARVE-OUT (task t-342, part B; class F3 of the HQ critic's
tools/wiring_check.py review, 2026-07-29): a RESOLVED discrepancy
(self-heal already fixed it) must not flip --check's exit code to 1.
n/a HERE: this repo's git_hooks_channel() (below) has no self-heal /
autofix logic of any kind -- every fact it returns is an open,
unresolved WARNING. There is therefore no autofix-fact class to carve
out of the --check failure set in this file; --check treats every
"WIRING WARNING:" line as failing. If git_hooks_channel() ever grows a
self-heal step (mirroring the OS original's VG-1), this carve-out must
be revisited at that time, not assumed to still be n/a.

Usage:
    python scripts/wiring_check.py            # SessionStart mode, exit 0 always
    python scripts/wiring_check.py --check    # fail-closed mode, exit 1 on any warning
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

_GITHOOKS_DIRNAME = ".githooks"
_REQUIRED_GITHOOKS = ("commit-msg", "pre-commit")
_SETTINGS_RELPATH = Path(".claude") / "settings.json"

# Outer cap on the WHOLE finished line (a WIRING line legitimately carries
# a full repo path plus an explanatory clause -- wider than the ~80-char
# bound that would suit a single-token value). Boundary-tested: exactly
# at the limit passes through unchanged, one char over gets truncated
# with an ellipsis marker (see _ascii_sanitize).
_WIRING_LINE_MAX_LEN = 300

# The command shape every hook line in THIS repo's .claude/settings.json
# actually uses (CLAUDE.md command-hygiene: canonical forms, no ad hoc
# variants): exactly "python scripts/<file>.py", no extra flags, forward
# slashes. Anything else is reported as an honest "unparsed hook command"
# WARNING rather than guessed at. `[^/\\]+` (not `[\w ]+`) deliberately
# allows spaces in the filename so a path-with-spaces command is still
# recognized and checked, not silently misparsed.
_HOOK_COMMAND_RE = re.compile(r"^python scripts/([^/\\]+\.py)$")


def _ascii_sanitize(text, max_len=80):
    """Best-effort ASCII-only, length-bounded rendering of a dynamic value
    for interpolation into a WIRING line. Non-ASCII characters are
    backslash-escaped (ascii() semantics, applied per-character via
    encode/decode so we do not also add surrounding quotes); the result is
    then truncated to max_len with a trailing marker if it overflows.
    Boundary: a value whose sanitized form is EXACTLY max_len characters
    long is returned unchanged (no truncation marker); ONE character over
    triggers truncation."""
    if not isinstance(text, str):
        text = str(text)
    safe = text.encode("ascii", "backslashreplace").decode("ascii")
    if len(safe) <= max_len:
        return safe
    keep = max(0, max_len - 3)
    return safe[:keep] + "..."


def git_hooks_channel(root: Path) -> list:
    """git-channel: core.hooksPath must resolve to <root>/.githooks, AND
    both .githooks/commit-msg and .githooks/pre-commit must exist.
    Comparison is case-insensitive and slash-normalized (Windows: mixed
    "/" and "\\", drive-letter case can differ). Returns a list of WARNING
    detail strings (empty = fully wired). Never raises: git being absent,
    the subprocess call failing, or any other problem while reading the
    config is folded into one WARNING string here."""
    root = Path(root)
    expected = (root / _GITHOOKS_DIRNAME).resolve()
    reason = "escape_check/mechanism_gate do not run on commits"

    try:
        result = subprocess.run(
            ["git", "config", "core.hooksPath"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        detail = _ascii_sanitize(f"git config core.hooksPath failed ({type(e).__name__})", 120)
        return [f"{detail} -- {reason}"]

    raw = (result.stdout or "").strip()
    warnings = []
    if result.returncode != 0 or not raw:
        warnings.append(f"core.hooksPath not set -- {reason}")
    else:
        configured = Path(raw)
        if not configured.is_absolute():
            configured = root / configured
        try:
            configured_resolved = configured.resolve()
        except OSError:
            configured_resolved = configured
        # Case-insensitive, slash-normalized comparison (Windows: drive
        # letter case and separator style can both differ harmlessly).
        if os.path.normcase(str(configured_resolved)) != os.path.normcase(str(expected)):
            raw_safe = _ascii_sanitize(raw, 150)
            expected_safe = _ascii_sanitize(str(expected), 150)
            warnings.append(
                f"core.hooksPath={raw_safe!r} does not resolve to {expected_safe} -- {reason}"
            )

    for name in _REQUIRED_GITHOOKS:
        hook_file = root / _GITHOOKS_DIRNAME / name
        if not hook_file.is_file():
            warnings.append(f"hook file missing: {_GITHOOKS_DIRNAME}/{name} -- {reason}")
        elif os.name == "posix" and not os.access(hook_file, os.X_OK):
            # git ignores a present-but-non-executable hook SILENTLY
            # (only an advice-hint at commit time, invisible to a boot
            # check) -- the exact "hooks die silently" failure mode this
            # whole channel exists to surface.
            warnings.append(
                f"hook file not executable: {_GITHOOKS_DIRNAME}/{name} -- {reason}"
            )

    # Index-mode twin of the POSIX X_OK check above (form ported from the
    # OS-repo detector, cross-repo remainder closed 2026-07-28): on Windows
    # there is no working-tree exec bit and the check above
    # self-neutralizes, but the GIT INDEX mode is host-independent -- a
    # required hook tracked with a non-755 mode means every fresh POSIX
    # checkout gets a present-but-silently-ignored hook (the live
    # 2026-07-23 cloud-clone incident). Untracked hooks are skipped
    # (they still run locally; tracking discipline is not this check's
    # concern). Never raises: a failing git call becomes one WARNING.
    try:
        ls = subprocess.run(
            ["git", "ls-files", "-s", "--", _GITHOOKS_DIRNAME],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        detail = _ascii_sanitize(
            f"git ls-files -s {_GITHOOKS_DIRNAME} failed ({type(e).__name__})", 120)
        warnings.append(f"{detail} -- {reason}")
        return warnings
    if ls.returncode == 0:
        for line in (ls.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 3 or "\t" not in line:
                continue
            mode = parts[0]
            tracked_path = line.split("\t", 1)[1].strip()
            name = tracked_path.replace("\\", "/").rsplit("/", 1)[-1]
            if name in _REQUIRED_GITHOOKS and mode != "100755":
                warnings.append(
                    f"hook index mode {mode} (not 100755): {tracked_path} -- "
                    f"fresh POSIX checkout gets a silently ignored hook -- {reason}"
                )

    return warnings


def _parse_hook_commands(settings) -> list:
    """Walks every hooks section of a parsed .claude/settings.json
    (structure: {"hooks": {"<Event>": [{"hooks": [{"command": "..."}]}]}}),
    collecting each hook's raw command string in encounter order. Tolerant
    of any malformed shape -- a piece that isn't a dict/list where
    expected is simply skipped, never raised on (a malformed
    settings.json is exactly the condition this whole check exists to
    survive, fail-open)."""
    commands = []
    hooks_root = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks_root, dict):
        return commands
    for matchers in hooks_root.values():
        if not isinstance(matchers, list):
            continue
        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            entries = matcher.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                command = entry.get("command")
                if isinstance(command, str) and command:
                    commands.append(command)
    return commands


def harness_channel(root: Path):
    """harness-channel: every hook command line in .claude/settings.json
    of the form "python scripts/<file>.py" names a file that (a) exists
    and (b) imports cleanly via importlib. Returns (warnings,
    importable_count) -- importable_count is the number of DISTINCT
    scripts/<file>.py names that were checked and had NO warning. Never
    raises: a missing/unreadable/invalid settings.json, a missing hook
    file, or an import failure all become WARNING strings.

    Hardening (mirrors the OS original): exec_module runs with
    stdout/stderr redirected to os.devnull, so a hook file that prints at
    import time cannot dump arbitrary, non-ASCII-sanitized text into this
    hook's own stdout. If a checked script has top-level side effects that
    raise, that raise is caught here and turned into a WARNING -- never a
    crash of this whole check (spec requirement: import failure is a
    WARNING, not a fatal error)."""
    root = Path(root)
    settings_path = root / _SETTINGS_RELPATH

    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError as e:
        path_safe = _ascii_sanitize(str(settings_path), 150)
        return [f"{path_safe} not readable ({type(e).__name__})"], 0

    try:
        settings = json.loads(text)
    except Exception as e:
        path_safe = _ascii_sanitize(str(settings_path), 150)
        return [f"{path_safe} not valid JSON ({type(e).__name__})"], 0

    commands = _parse_hook_commands(settings)
    warnings = []
    ok_files = set()
    seen_files = set()
    for command in commands:
        m = _HOOK_COMMAND_RE.match(command.strip())
        if not m:
            command_safe = _ascii_sanitize(command, 150)
            warnings.append(f"unparsed hook command: {command_safe}")
            continue
        filename = m.group(1)
        if filename in seen_files:
            continue
        seen_files.add(filename)

        file_path = root / "scripts" / filename
        filename_safe = _ascii_sanitize(filename, 150)
        if not file_path.is_file():
            warnings.append(f"hook file not found: scripts/{filename_safe}")
            continue

        module_name = f"_wiring_check_{re.sub(r'[^0-9A-Za-z_]', '_', file_path.stem)}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"no loader for {file_path}")
            module = importlib.util.module_from_spec(spec)
            with open(os.devnull, "w", encoding="utf-8") as _devnull, \
                    contextlib.redirect_stdout(_devnull), \
                    contextlib.redirect_stderr(_devnull):
                spec.loader.exec_module(module)
        except Exception as e:
            warnings.append(f"import failed: scripts/{filename_safe} ({type(e).__name__})")
            continue

        ok_files.add(filename)

    return warnings, len(ok_files)


def skills_casing_channel(root: Path):
    """(c) skills-casing channel (task t-342, port of
    D:\\Improving_AI\\Operating-System-for-LLMs tools/wiring_check.py's
    skills_casing_channel(), 2026-07-29): every git-INDEX path under
    .claude/skills/ whose basename, lowercased, equals "skill.md" must be
    tracked as EXACTLY "SKILL.md".

    MOTIVE: on a case-insensitive filesystem (this Windows host), a
    lowercase skill.md already committed to the index makes a later
    `git add .../SKILL.md` SILENTLY no-op (git treats the path as "the
    same file, unchanged casing" case-insensitively) while the command
    itself reports success -- the file that is actually live on disk
    never gets its correct-cased entry into the index. This is the exact
    incident the sibling Dog deployment hit on 2026-07-25 and reported
    again in its 2026-07-29 synk (D-0082, docs/tasks -- see the OS repo's
    2026-07-29_dog-incoming-sync.md item 2).

    Returns (warnings, ok_count), same shape as harness_channel() above:
    warnings is a list of detail strings (empty = every skill.md-named
    index path is correctly cased); ok_count is the number of
    correctly-cased SKILL.md index entries found, used for the OK line's
    "skills casing: M ok". Never raises: a git failure (missing binary,
    timeout, non-zero exit -- e.g. run outside a git repo) folds into ONE
    warning naming the check as unverifiable, the same subprocess idiom
    (timeout=5, fold-to-one-warning) this file's own git_hooks_channel()
    already uses for its `git ls-files -s` call."""
    root = Path(root)
    unverifiable = "skills casing not verifiable"

    try:
        result = subprocess.run(
            ["git", "ls-files", "--", ".claude/skills/"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        detail = _ascii_sanitize(f"git ls-files failed ({type(e).__name__})", 120)
        return [f"{detail} -- {unverifiable}"], 0

    if result.returncode != 0:
        detail = _ascii_sanitize(f"git ls-files exited {result.returncode}", 120)
        return [f"{detail} -- {unverifiable}"], 0

    warnings = []
    ok_count = 0
    for line in (result.stdout or "").splitlines():
        path_str = line.strip()
        if not path_str:
            continue
        basename = Path(path_str).name
        if basename.lower() != "skill.md":
            continue
        if basename == "SKILL.md":
            ok_count += 1
            continue
        path_safe = _ascii_sanitize(path_str, 150)
        warnings.append(
            f"skill file wrong case: {path_safe} -- on a case-insensitive"
            " filesystem `git add .../SKILL.md` silently no-ops against an"
            " already-tracked differently-cased skill.md (Dog 2026-07-25"
            " incident, synk 2026-07-29)"
        )

    return warnings, ok_count


def python_channel():
    """python-channel: shutil.which("python") on THIS process's PATH.
    LIMITATION (same as the OS original, deliberately not fixable here):
    this is a statement about the PATH of the process running this hook
    right now (a SessionStart hook invocation) -- the PATH available to a
    git hook (pre-commit/commit-msg) at actual commit time is a SEPARATE
    shell invocation and can differ. Returns the resolved path string, or
    None if no "python" was found."""
    return shutil.which("python")


def wiring_lines(root: Path = None) -> list:
    """Combines the four wiring-integrity channels into either a single
    'WIRING: OK (...)' line (everything wired) or one 'WIRING WARNING:
    <fact>' line per discrepancy across all four channels. ALWAYS
    returns at least one line and NEVER raises -- any internal exception
    collapses to a single WARNING line (spec requirement: this check must
    degrade gracefully, never block/crash SessionStart)."""
    try:
        root = Path(root) if root else REPO_ROOT
        git_warnings = git_hooks_channel(root)
        harness_warnings, importable_count = harness_channel(root)
        skills_warnings, skills_ok_count = skills_casing_channel(root)
        python_path = python_channel()
    except Exception as e:
        return [
            _ascii_sanitize(
                f"WIRING WARNING: check failed internally ({type(e).__name__})",
                _WIRING_LINE_MAX_LEN,
            )
        ]

    warnings = list(git_warnings) + list(harness_warnings) + list(skills_warnings)
    if not python_path:
        warnings.append("python not found on PATH")

    if not warnings:
        python_safe = _ascii_sanitize(python_path, 150)
        line = (
            "WIRING: OK (git hooks: commit-msg, pre-commit;"
            f" harness hooks: {importable_count} files importable;"
            f" skills casing: {skills_ok_count} ok; python: {python_safe})"
        )
        return [_ascii_sanitize(line, _WIRING_LINE_MAX_LEN)]
    return [
        _ascii_sanitize(f"WIRING WARNING: {w}", _WIRING_LINE_MAX_LEN) for w in warnings
    ]


def main(argv=None) -> int:
    """See module docstring "CLI CONTRACT". No flag: prints the
    wiring_lines() output and ALWAYS returns 0 (byte-for-byte the
    original SessionStart-printer contract, untouched -- fail-open).
    `--check`: same printed output, but returns 1 if any printed line
    starts with "WIRING WARNING:", 0 otherwise (fail-closed probe mode,
    task t-342 part B). *argv* defaults to sys.argv (the whole list,
    including argv[0]) when not given, matching this file's own
    `__main__` call below; the flag is looked up by membership, not
    position, so both `main(sys.argv)` and a bare `main(["--check"])`
    (as used by tests) work identically."""
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    if argv is None:
        argv = sys.argv
    check_mode = "--check" in argv
    lines = wiring_lines()
    for line in lines:
        print(line)
    if not check_mode:
        return 0
    has_warning = any(line.startswith("WIRING WARNING:") for line in lines)
    return 1 if has_warning else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
