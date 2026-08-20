"""Scratchpad D3 still-repro single trial for BUG-013 (0ms toggle->kill race).
NOT a permanent test case — deleted after the run. See bugs/BUG-013.md, mode=still-repro.

Trial B: NO intervening Appium tree read between tap and force-stop (a read between
tap and kill costs a UiAutomator page-source roundtrip, which in trial A measured
long enough to let SharedPreferences.apply() flush -- confounding the 0ms probe).
Tap-registers-reliably evidence comes from the ALREADY PASSING TC-050
("Contrast-иконка side panel переключает тему мгновенно"), not a per-trial tree read.
"""
from __future__ import annotations

import time

from framework.core import adb
from framework.config import settings
from framework.steps import app_steps, side_panel_steps


def test_bug013_stillrepro_0ms_trial(clean_app, driver):
    app_steps.wait_ui_ready(driver)

    # Pre-state: read raw prefs file BEFORE any toggle (clean_app already did pm clear)
    pre = adb.run_as("cat shared_prefs/ao3_settings.xml")
    print(f"PRE-STATE RAW: {pre!r}")

    side_panel_steps.expand(driver)
    side_panel_steps.assert_theme_is_light(driver)  # confirms pre = LIGHT via tree (contrast desc)

    # Toggle DARK via side panel contrast icon, then kill IMMEDIATELY -- no tree
    # read/assert between tap and force-stop this time (trial A's tree check added
    # enough latency for the write to flush, see docstring above).
    t0 = time.perf_counter()
    side_panel_steps.toggle_theme(driver)
    adb.force_stop()
    t1 = time.perf_counter()
    print(f"TOGGLE-TO-KILL ELAPSED: {(t1 - t0) * 1000:.1f} ms (no intervening Appium calls)")

    adb.shell(
        f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}",
        timeout=settings.ADB_LAUNCH_TIMEOUT,
    )
    app_steps.wait_ui_ready(driver)

    post = adb.run_as("cat shared_prefs/ao3_settings.xml")
    print(f"POST-RELAUNCH RAW: {post!r}")

    if "name=\"theme_mode\">DARK<" in post:
        print("RESULT: theme_mode=DARK persisted (bug NOT reproduced on this trial)")
    else:
        print("RESULT: theme_mode NOT DARK (DARK lost) -- race still reproduces")
