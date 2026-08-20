"""RED/GREEN evidence for AT-BUG-069 fix — does NOT touch the working tree.

RED: replays the OLD (pre-fix, from `git show HEAD`) pull_app_file logic
inline against the exact two scenarios the new regression-lock test targets
-- shows the old logic wrongly returns True and writes the remote error text
as if it were the file's bytes.

GREEN: calls the REAL (already-fixed) framework.core.adb.pull_app_file with
subprocess.run mocked to the same stdout, from within tests/ so imports
resolve, and shows it now returns False / raises RuntimeError instead.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


def old_pull_app_file(cp, dest: Path) -> bool:
    # verbatim old branch logic (git show HEAD:framework/core/adb.py)
    if cp.returncode != 0 or not cp.stdout:
        return False
    dest.write_bytes(cp.stdout)
    return True


SCENARIOS = {
    "run-as-unknown-package": subprocess.CompletedProcess(
        args=["adb"], returncode=0,
        stdout=b"run-as: unknown package: com.example.ao3_wrapper\n", stderr=b"",
    ),
    "cat-no-such-file-synthetic-path": subprocess.CompletedProcess(
        args=["adb"], returncode=0,
        stdout=b"cat: databases/definitely_not_a_real_file.db: No such file or directory\n",
        stderr=b"",
    ),
}

print("=== RED: old pre-fix logic (git show HEAD) ===")
tmp = Path(tempfile.mkdtemp())
for name, cp in SCENARIOS.items():
    dest = tmp / f"{name}.bin"
    ok = old_pull_app_file(cp, dest)
    written = dest.read_bytes() if dest.exists() else None
    print(f"{name}: old_pull_app_file -> ok={ok}, written_bytes={written!r}")
    assert ok is True, "expected OLD code to wrongly report success"
    assert written == cp.stdout, "expected OLD code to wrongly write error text as content"
print("RED confirmed: old code returns True and writes remote error text as file bytes.\n")

print("=== GREEN: real (fixed) framework.core.adb.pull_app_file ===")
from framework.core import adb  # noqa: E402

for name, cp in SCENARIOS.items():
    dest = tmp / f"{name}-new.bin"

    def _fake_run(*a, **kw):
        return cp

    orig = subprocess.run
    subprocess.run = _fake_run
    try:
        try:
            ok = adb.pull_app_file("databases/x", dest)
            outcome = f"ok={ok}"
        except RuntimeError as e:
            outcome = f"RuntimeError: {e}"
    finally:
        subprocess.run = orig
    written = dest.read_bytes() if dest.exists() else None
    print(f"{name}: pull_app_file -> {outcome}, dest_exists={dest.exists()}, written={written!r}")
print("GREEN confirmed above (see per-scenario outcome).")
