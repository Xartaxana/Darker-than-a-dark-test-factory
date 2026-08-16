@echo off
rem AO3 QA factory watchdog (docs/06 §5, spec-factory-window v6, 2026-08-16).
rem Scheduled by Windows Task Scheduler task "AO3-QA-Heartbeat" (PT30M,
rem InteractiveToken - WinRT toast capable). Architecture change: the
rem factory no longer drives /qa-loop headless from this scheduled task
rem (that was scripts\heartbeat_wrap.py, now DEPRECATED - see its module
rem docstring header). The factory is driven from an OPEN Claude Code
rem window by the /factory skill (.claude\skills\factory\SKILL.md);
rem THIS task's only job is to run the watchdog, which checks progress of
rem that open window (state\factory-mode.json) and of state\loop.lock,
rem raising a toast + a singleton escalation ([factory:stalled]) on
rem stall. scripts\factory_watchdog.py is non-throwing and always exits
rem 0 - it must never fail the scheduled task itself.
cd /d D:\AO3_tests
C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe scripts\factory_watchdog.py
