@echo off
rem AO3 QA factory watchdog (docs/06 §5, spec-factory-window v7 = v6 + Д1
rem night-fallback, 2026-08-16). Scheduled by Windows Task Scheduler task
rem "AO3-QA-Heartbeat" (PT30M, InteractiveToken - WinRT toast capable).
rem Architecture: the factory is STANDARD-drives /qa-loop from an OPEN
rem Claude Code window via the /factory skill (.claude\skills\factory\
rem SKILL.md), not headless from this scheduled task as a primary driver.
rem THIS task's only DIRECT job is to run the watchdog, which checks
rem progress of that open window (state\factory-mode.json) and of
rem state\loop.lock, raising a toast + a singleton escalation
rem ([factory:stalled]) on stall - BUT (Д1, 2026-08-16 evening) this task
rem TRANSITIVELY DOES drive /qa-loop when the window is dead: the watchdog
rem itself spawns ONE reserve headless /qa-loop 5 pass via
rem scripts\heartbeat_wrap.py::run_fallback_pass (same child-spawn
rem machinery as the formerly-primary, now partially-deprecated run_pass -
rem see heartbeat_wrap.py's module docstring header) once STALLED persists
rem >=15 min and night_fallback/budget/breakage-series gates are clean.
rem scripts\factory_watchdog.py is non-throwing and always exits 0 - it
rem must never fail the scheduled task itself.
cd /d D:\AO3_tests
C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe scripts\factory_watchdog.py
