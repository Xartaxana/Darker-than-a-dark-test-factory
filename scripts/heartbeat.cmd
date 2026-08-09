@echo off
rem AO3 QA factory heartbeat (docs/06 §5, docs/11 gate §1).
rem Runs one non-interactive /qa-loop pass (limit 3 dispatches) as Sonnet
rem coordinator (standard mode: operator/Fable accepts queued Lead work).
rem Scheduled by Windows Task Scheduler task "AO3-QA-Heartbeat" (created
rem 2026-07-17, DISABLED by default - enable by operator word / rehearsal).
rem Log: logs\heartbeat.log (gitignored).
rem M1+M4 (2026-08-09, plan-m1-m4.md v3, runs/REHEARSAL-2026-08-04.md N1/N6):
rem anti-overlap lock ownership moved OUT of the /qa-loop skill and into this
rem long-lived wrapper (scripts\heartbeat_wrap.py) - programmatic
rem loop_lock.acquire/release with an honest wrapper pid, BUSY short-circuit
rem before claude is even launched, taskkill /T /F kill-tree + tasklist
rem post-check on timeout, and an orchestrator-log line on every child death.
rem Critic-fix (2026-08-09, item 7): absolute python.exe path, symmetric with
rem CLAUDE_CMD in heartbeat_wrap.py - Task Scheduler PATH is not measured, so
rem a bare `python` is not relied upon (same class as why claude.cmd already
rem used an absolute path).
cd /d D:\AO3_tests
echo [%date% %time%] heartbeat start >> D:\AO3_tests\logs\heartbeat.log
C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe scripts\heartbeat_wrap.py >> D:\AO3_tests\logs\heartbeat.log 2>&1
echo [%date% %time%] heartbeat end (exit %errorlevel%) >> D:\AO3_tests\logs\heartbeat.log
