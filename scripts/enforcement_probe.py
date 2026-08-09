"""scripts/enforcement_probe.py -- fail-closed pre-commit gate that
protects the enforcement chain ITSELF: a fix to a chain file is verified
against the OBSERVER that watches the chain (scripts/wiring_check.py),
not only against the symptom the fix targeted. Motive (synk from the
sibling Dog deployment, D-0082, 2026-07-29,
D:\\Improving_AI\\Operating-System-for-LLMs docs/tasks/2026-07-29_dog-
incoming-sync.md item 1): on 2026-07-25 Dog's own accepted fix to a
chain file silently broke their wiring_check parser for a whole day --
the fix's own DoD checked the symptom it targeted, never the wiring
auditor sitting downstream of it, so the breakage went unnoticed until
the next unrelated audit.

PORT NOTE (task t-342, part C): this is a port of
D:\\Improving_AI\\Operating-System-for-LLMs tools/enforcement_probe.py
(the version already carrying critic t-339's fixes -- --no-renames,
`-c core.quotePath=false`, recursive .githooks/ walk, honest fail-open
on a staged-list git failure, AUTOFIX handling, docstring limitations --
see "FIXES CARRIED OVER" below) onto THIS repo's tree and conventions:

  - REPO / SETTINGS_PATH / GITHOOKS_DIR resolve to THIS repo (derived
    from `__file__`'s own location under scripts/, same as the source).
  - The hook-command pattern is "python scripts/<name>.py" (this repo's
    canonical form, CLAUDE.md command hygiene), NOT "python tools/....py"
    -- `_PY_TOOL_CMD_RE` and `WIRING_CHECK_REL` are adapted accordingly
    (scripts/wiring_check.py, not tools/wiring_check.py).
  - The observer is invoked as `python scripts/wiring_check.py --check`
    (with the new fail-closed flag added by t-342 part B), NOT a bare
    `python scripts/wiring_check.py` -- THIS repo's wiring_check.py is a
    SessionStart printer whose no-flag contract is deliberately fail-OPEN
    (exit 0 always, see that file's own "CLI CONTRACT" docstring section);
    without `--check`, a subprocess run of it would report success even
    while printing warning lines, defeating this probe's whole purpose.
    `--check` is the mode that actually turns "does the observer see a
    problem" into a nonzero exit code.

DELIVERY NOTE (enforcement-file-review rule, CLAUDE.md rule 2 / routing
rule R2, D-0069): a builder dispatch never places a self-activating hook
file on its own live path. Delivered by the builder as the inert
neighbor file scripts/enforcement_probe_next.py; the Lead moved it onto
this live name and wired the call into .githooks/pre-commit at
acceptance of t-342 (2026-07-29).

DESIGN (mirrors the OS original's spec part E):
  1. Staged set: `git -c core.quotePath=false diff --cached --no-renames
     --name-only`, decoded byte-safely (see `_staged_files` for the
     `--no-renames`/`quotePath` rationale, F2/F9(д), critic t-339). An
     empty staged set is exit 0 immediately -- no git-index work happens
     on an ordinary commit that isn't touching the chain at all.
  2. The enforcement CHAIN is built DYNAMICALLY, not from a hardcoded
     list (a hardcoded list goes stale) -- see `_chain_paths`: every path
     under .githooks/ (RECURSIVELY -- F9(г), critic t-339: a hook script
     nested in a subdirectory under .githooks/ is walked too, not just
     its top level), `.claude/settings.json` itself, `scripts/wiring_check.py`
     by name, and every `scripts/<name>.py` referenced by a
     `python scripts/....py` hook command inside .claude/settings.json OR
     inside any script under .githooks/ (the same two sources
     scripts/wiring_check.py itself reads for its own harness/git-hooks
     checks -- D-0093 pattern; see "PARSER REUSE" below for why this file
     keeps its own separate reader rather than importing that one).
  3. Staged ∩ chain empty -> exit 0, the wiring check is NOT invoked at
     all (the cost on an ordinary commit is exactly the staged-list
     read, nothing more).
  4. Staged ∩ chain non-empty -> the wiring check is run (see
     `_default_run_wiring_check` -- `python scripts/wiring_check.py
     --check` as a subprocess, matching this deploy's own convention of
     running scripts/*.py via `python scripts/<name>.py`, same shape as
     every hook command already registered in .claude/settings.json,
     plus the new `--check` flag -- see "PORT NOTE" above). A non-zero
     exit code (or an import/parse/execution failure of any kind -- see
     `decide()`) is reported and the commit is rejected (exit 1); this IS
     genuinely fail-closed by design -- an observer that cannot even run
     is exactly the failure class this probe exists to catch, so silence
     there would defeat its own purpose. See "GIT-FAILURE HANDLING IS NOT
     THIS" below for the ONE step in this pipeline that is deliberately
     the opposite.
  5. .githooks/pre-commit is NOT touched by this delivery -- the Lead
     wires the call in at acceptance (non-goal, per the dispatch's
     manifest, D-0069).

FIXES CARRIED OVER FROM THE SOURCE (critic t-339, all preserved
unchanged by this port):
  - F2: `--no-renames` on the staged-diff call (see `_staged_files`) --
    without it, a same-content `git mv scripts/wiring_check.py
    scripts/wiring_check_v2.py` can collapse to a SINGLE name-only line
    naming only the NEW path, silently dropping the OLD (chain) path out
    of the staged-name list.
  - F9(д): `-c core.quotePath=false` on the same call -- without it, git
    C-style-quotes any non-ASCII path byte instead of emitting raw UTF-8,
    breaking this file's plain-UTF-8 decode/compare.
  - F9(г): `.githooks/` is walked RECURSIVELY (`_githooks_files`, via
    `os.walk`), not just its top level.
  - F9(a) / "GIT-FAILURE HANDLING IS NOT THIS": `_staged_files()` and
    `_chain_paths()` fold their OWN known failure modes (git missing,
    unreadable chain source) into an empty/partial result rather than
    raising -- this is FAIL-OPEN by design (see that section below),
    distinct from `decide()`'s genuinely fail-closed core.
  - Docstring limitations ("WAY OUT OF THE DEADLOCK" / "LIMITATION --
    STAGED CONTENT ITSELF IS NOT CHECKED" below) carried over verbatim in
    substance, paths adapted to this repo.

WAY OUT OF THE DEADLOCK (F9(б), critic t-339): this probe runs
`python scripts/wiring_check.py --check` against the WORKING TREE (a
plain subprocess invocation, not `git show :scripts/wiring_check.py` or
anything reading the INDEX) -- so fixing scripts/wiring_check.py (or
whatever it is that made wiring go wrong) in the working tree and
re-`git add`-ing/re-committing unblocks the commit IMMEDIATELY, on the
very next attempt. There is no separate "unwedge" step or override flag
needed: the observer this probe consults is the same one a developer
would fix by hand, read from the same place.

LIMITATION -- STAGED CONTENT ITSELF IS NOT CHECKED (F9(в), critic t-339):
the wiring check always runs against the CURRENT WORKING TREE files, not
the staged (about-to-be-committed) versions. A pathological sequence --
stage a BROKEN scripts/wiring_check.py, then fix the working tree copy
back to a working state WITHOUT re-staging the fix -- would pass this
probe (the working tree is healthy) while the actual commit still
carries the broken staged version. This is a known, accepted gap (not
chased preventively, same "warn/fail-closed is not an absolute security
boundary" principle the sibling hygiene_gate.py documents for its own
residuals in the OS repo): fixing it would require diffing the wiring
check against the STAGED blob (`git show :scripts/wiring_check.py`
executed in a temp location), a meaningfully bigger mechanism than this
port's scope.

PARSER REUSE (spec part E point 2 -- "переиспользуй парсер wiring_check,
если он импортируем; иначе -- минимальный собственный разбор тех же
источников"): `_chain_paths` below is the "minimal own parsing"
fallback, mirroring the source file's own choice. scripts/wiring_check.py
exists on this repo's path, but it does not expose a function shaped for
THIS use (build the set of repo-relative paths that constitute the
enforcement chain, for a git-diff intersection check) -- its own
hook-command parsing (`_parse_hook_commands`, wrapped by
`harness_channel`) answers a DIFFERENT question ("does each referenced
scripts/*.py file exist and import cleanly?"), not "which paths are in
the chain". `_chain_paths` reads the exact same two sources
(.claude/settings.json, .githooks/*) with its own regex-based
extraction, kept deliberately separate rather than forcing an ill-fitting
reuse of a differently-shaped internal helper.

GIT-FAILURE HANDLING IS NOT THIS (F9(a), critic t-339): `_staged_files()`
catches its OWN git failures (git missing, not a repo, timeout, non-zero
exit) internally and returns `[]` -- an empty staged set -- rather than
raising. Per design point 3, an empty staged set is exit 0 immediately.
So a git failure reading the staged set is, in fact, FAIL-OPEN: the
commit proceeds unchecked. This is DELIBERATE, not an oversight -- see
`_staged_files`'s own docstring: a git failure severe enough to reach
this point would also fail the commit itself well before this hook's
verdict matters, and a probe that could ITSELF block every commit
whenever git briefly hiccups (unrelated to the enforcement chain) is a
worse failure mode than the narrow gap it would close. `_chain_paths`
follows the same per-source best-effort philosophy: an unreadable
settings.json or .githooks/ entry silently contributes nothing to the
chain set rather than raising, so a chain-source read failure DEGRADES
the chain (potentially missing a member) rather than failing the commit.

The ONE place this probe is genuinely, deliberately fail-closed is
inside `decide()` itself (design point 4): once staged ∩ chain is
non-empty, a wiring-check run that errors, crashes, or reports non-OK
rejects the commit (exit 1) -- that IS the failure class this probe
exists to catch. `main()`'s own outer try/except is a narrow backstop
for a genuinely UNFORESEEN exception escaping `decide()` itself (a bug,
not a git/filesystem failure already handled above) -- it exits 1 there
too, but this is defensive residue, not the probe's primary fail-closed
guarantee, and should not be read as contradicting the fail-open
staged/chain-gathering behavior described above.

DELIVERY-STATE NOTE: delivered as the inert neighbor
scripts/enforcement_probe_next.py; placed on this live name and wired
into .githooks/pre-commit by the Lead at acceptance of t-342 (D-0069,
2026-07-29). Nothing about the code below assumes any particular
filename; REPO is derived from `__file__`'s own location under
scripts/, so it resolves correctly under either name.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(REPO, ".claude", "settings.json")
GITHOOKS_DIR = os.path.join(REPO, ".githooks")
WIRING_CHECK_REL = "scripts/wiring_check.py"

# Matches a `python scripts/<name>.py`-shaped hook command reference,
# inside either .claude/settings.json's JSON text or a .githooks/*
# shell script -- the same shape every hook in this repo already uses
# (see .claude/settings.json's own "command" values; adapted from the
# source's "tools/" pattern to this repo's "scripts/" pattern).
# 2026-08-09 (live cwd-drift incident, sibling of wiring_check's
# _hook_script_name): hook commands may now use the ABSOLUTE twin
# "python <drive>:/.../scripts/<name>.py" -- the optional non-capturing
# drive prefix strips it so group(1) stays the repo-relative
# "scripts/<name>.py" the chain is keyed on.
_PY_TOOL_CMD_RE = re.compile(
    r"python\s+(?:[A-Za-z]:[^\s\"']*[/\\])?(scripts/[A-Za-z0-9_./\\-]+\.py)")


def _read_text_best_effort(path):
    """Reads *path* as UTF-8 text, tolerating decode errors -- never
    raises; returns "" on any failure (missing file, permissions,
    binary content) so a chain-source read failure degrades to "found
    nothing more to add here" rather than crashing the whole probe."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _referenced_tool_paths(text):
    return {m.group(1).replace("\\", "/") for m in _PY_TOOL_CMD_RE.finditer(text)}


def _githooks_files():
    """F9(г) (critic t-339): walks .githooks/ RECURSIVELY (os.walk, not
    a single os.listdir) -- a hook script nested under a subdirectory
    (e.g. .githooks/lib/helper.sh) is a real chain member too, and a
    single-level listdir would silently miss it. Yields (relpath,
    abspath) pairs for every FILE found, relpath repo-relative with
    forward slashes. Never raises: a walk error on one subdirectory
    (permissions, a broken symlink) is swallowed by onerror=lambda,
    same best-effort philosophy as the rest of this function -- a
    partial chain is still better than none."""
    if not os.path.isdir(GITHOOKS_DIR):
        return
    for dirpath, _dirnames, filenames in os.walk(GITHOOKS_DIR, onerror=lambda _e: None):
        for name in filenames:
            abspath = os.path.join(dirpath, name)
            relpath = os.path.relpath(abspath, REPO).replace("\\", "/")
            yield relpath, abspath


def _chain_paths():
    """Builds the enforcement-chain path set DYNAMICALLY (design point
    2): every file under .githooks/, recursively (see `_githooks_files`,
    F9(г)), the exact file .claude/settings.json, scripts/wiring_check.py
    by name, plus every scripts/*.py referenced by a hook command inside
    .claude/settings.json or any .githooks/* file. Every path is
    repo-relative, forward-slash. Never raises -- an unreadable source
    contributes nothing, not a crash (module docstring "GIT-FAILURE
    HANDLING IS NOT THIS" covers the fail-open/best-effort posture of
    this whole function; a partial chain is still better than none)."""
    chain = {".claude/settings.json", WIRING_CHECK_REL}

    settings_text = _read_text_best_effort(SETTINGS_PATH)
    chain |= _referenced_tool_paths(settings_text)

    for relpath, abspath in _githooks_files():
        chain.add(relpath)
        chain |= _referenced_tool_paths(_read_text_best_effort(abspath))

    return chain


def _staged_files():
    """`git diff --cached --no-renames --name-only`, byte-decoded with
    errors="replace" (git's own output encoding on this host is not
    assumed clean -- same byte-safety posture as every stdin-reading
    hook in this repo). Returns [] on any git failure (git missing, not
    a repo, timeout) -- design point 1 treats an empty staged set as
    exit 0, so a git failure here degrades to "nothing staged", the SAFE
    direction for an ordinary-commit fast path (a git failure severe
    enough to reach this point would also fail the commit itself well
    before this hook runs).

    F2 (critic t-339): `--no-renames` is deliberate -- with rename
    detection ON (git's default), `git mv scripts/wiring_check.py
    scripts/wiring_check_v2.py` can report as a SINGLE line naming only
    the NEW path, silently dropping the OLD path (a real chain member)
    out of the staged-name list entirely -- a rename that effectively
    REMOVES the observer from scripts/wiring_check.py would then not
    even register as "chain touched". `--no-renames` forces git to
    report a rename as a plain delete-of-old-path + add-of-new-path
    pair, so BOTH sides are always visible to the chain intersection
    check (design point 2/3).

    F9(д) (critic t-339): `-c core.quotePath=false` -- without it, git
    C-style-quotes any path byte outside the printable-ASCII range
    (e.g. a non-ASCII filename renders as an octal-escaped string like
    "\\320\\277...") instead of emitting raw UTF-8 bytes; this repo's
    own decode step below assumes raw UTF-8, so a quoted path would
    silently fail to match a chain path expressed in plain UTF-8."""
    try:
        result = subprocess.run(
            [
                "git", "-c", "core.quotePath=false",
                "diff", "--cached", "--no-renames", "--name-only",
            ],
            cwd=REPO,
            capture_output=True,
            timeout=30,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    text = result.stdout.decode("utf-8", errors="replace")
    return [line.strip().replace("\\", "/") for line in text.splitlines() if line.strip()]


def _intersect(staged, chain):
    chain_lower = {c.lower() for c in chain}
    return [s for s in staged if s.lower() in chain_lower]


def _default_run_wiring_check():
    """Runs `python scripts/wiring_check.py --check` as a subprocess
    (design point 4). The `--check` flag (task t-342 part B) is
    load-bearing here -- see module docstring "PORT NOTE": this repo's
    scripts/wiring_check.py is fail-OPEN without it (SessionStart
    printer contract, always exit 0), which would make this probe unable
    to ever detect a wiring problem. Returns (ok, detail): ok is True iff
    the process exits 0 (standard Unix convention, consistent with every
    other exit-code contract in this repo); detail is combined
    stdout+stderr text, for the rejection message. Any exception (script
    missing entirely, interpreter not found, timeout) is NOT caught here:
    it propagates to `decide()`'s own try/except, which turns it into the
    fail-closed exit-1 path (design point 4's "ошибка импорта/запуска...
    тоже exit 1")."""
    script = os.path.join(REPO, "scripts", "wiring_check.py")
    result = subprocess.run(
        [sys.executable, script, "--check"],
        cwd=REPO,
        capture_output=True,
        timeout=60,
    )
    detail = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    return result.returncode == 0, detail


def decide(staged_files, chain_paths, run_wiring_check):
    """Pure decision core (still calls the injected *run_wiring_check*
    callable, kept as a parameter specifically so tests can exercise
    every state -- OK / non-OK / crash -- without depending on
    scripts/wiring_check.py actually existing on disk or behaving any
    particular way). Returns (exit_code, message): message is "" when
    nothing is printed."""
    if not staged_files:
        return 0, ""

    touched = _intersect(staged_files, chain_paths)
    if not touched:
        return 0, ""

    touched_list = ", ".join(sorted(touched))
    try:
        ok, detail = run_wiring_check()
    except Exception as exc:
        return 1, (
            "enforcement_probe: wiring_check crashed while the enforcement "
            f"chain is touched ({touched_list}) -- fail-closed. Error: {exc!r}"
        )
    if not ok:
        return 1, (
            "enforcement_probe: wiring_check reports a problem while the "
            f"enforcement chain is touched ({touched_list}):\n{detail}"
        )
    return 0, ""


def main():
    """See module docstring "GIT-FAILURE HANDLING IS NOT THIS" (F9(a),
    critic t-339): `_staged_files()`/`_chain_paths()` already fold their
    own known failure modes (git unavailable, unreadable chain sources)
    into an empty/partial result rather than raising -- this outer
    try/except is a narrow backstop for a genuinely UNFORESEEN exception
    escaping `decide()` itself, not this probe's primary fail-closed
    guarantee (that lives inside `decide()`, design point 4). Never
    raises out of `__main__`."""
    try:
        staged = _staged_files()
        chain = _chain_paths()
        exit_code, message = decide(staged, chain, _default_run_wiring_check)
    except Exception as exc:
        sys.stderr.write(
            f"enforcement_probe: crashed during staged/chain analysis -- "
            f"fail-closed. Error: {exc!r}\n"
        )
        return 1
    if message:
        sys.stderr.write(message + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
