"""SessionStart wiring-integrity check (task os-port-0722, port of
D:\\Improving_AI\\Operating-System-for-LLMs tools/session_context.py's
wiring block, lines ~602-895).

Three independent, read-only checks:

    (a) git-channel     -- core.hooksPath resolves to <root>/.githooks AND
                            both required git hook files exist under it
                            (commit-msg, pre-commit).
    (b) harness-channel  -- every "python scripts/<file>.py" hook command
                            in .claude/settings.json (our pattern -- NOT
                            "tools/", the OS repo's pattern) names a file
                            that exists and imports cleanly.
    (c) python-channel   -- shutil.which("python") finds an interpreter on
                            THIS process's PATH.

Each channel turns its OWN known failure modes into WARNING detail
strings rather than raising; the whole combination is additionally
wrapped in one outer try/except so a wiring-block failure degrades to a
single WARNING line rather than blowing up SessionStart.

Output: one line, always ASCII, always exit 0 (fail-open -- this check
must never block session start):

    WIRING: OK (git hooks: commit-msg, pre-commit; harness hooks: N
    importable; python: <path>)

or one or more:

    WIRING WARNING: <fact>

Usage:
    python scripts/wiring_check.py
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
        if not (root / _GITHOOKS_DIRNAME / name).is_file():
            warnings.append(f"hook file missing: {_GITHOOKS_DIRNAME}/{name} -- {reason}")

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
    """Combines the three wiring-integrity channels into either a single
    'WIRING: OK (...)' line (everything wired) or one 'WIRING WARNING:
    <fact>' line per discrepancy across all three channels. ALWAYS
    returns at least one line and NEVER raises -- any internal exception
    collapses to a single WARNING line (spec requirement: this check must
    degrade gracefully, never block/crash SessionStart)."""
    try:
        root = Path(root) if root else REPO_ROOT
        git_warnings = git_hooks_channel(root)
        harness_warnings, importable_count = harness_channel(root)
        python_path = python_channel()
    except Exception as e:
        return [
            _ascii_sanitize(
                f"WIRING WARNING: check failed internally ({type(e).__name__})",
                _WIRING_LINE_MAX_LEN,
            )
        ]

    warnings = list(git_warnings) + list(harness_warnings)
    if not python_path:
        warnings.append("python not found on PATH")

    if not warnings:
        python_safe = _ascii_sanitize(python_path, 150)
        line = (
            "WIRING: OK (git hooks: commit-msg, pre-commit;"
            f" harness hooks: {importable_count} files importable; python: {python_safe})"
        )
        return [_ascii_sanitize(line, _WIRING_LINE_MAX_LEN)]
    return [
        _ascii_sanitize(f"WIRING WARNING: {w}", _WIRING_LINE_MAX_LEN) for w in warnings
    ]


def main(argv=None) -> int:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    for line in wiring_lines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
