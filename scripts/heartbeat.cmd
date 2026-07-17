@echo off
rem AO3 QA factory heartbeat (docs/06 §5, docs/11 gate §1).
rem Runs one non-interactive /qa-loop pass (limit 3 dispatches) as Sonnet
rem coordinator (standard mode: operator/Fable accepts queued Lead work).
rem Scheduled by Windows Task Scheduler task "AO3-QA-Heartbeat" (created
rem 2026-07-17, DISABLED by default - enable by operator word / rehearsal).
rem Log: logs\heartbeat.log (gitignored). Anti-overlap: the /qa-loop skill
rem itself acquires state\loop.lock via scripts\loop_lock.py (heartbeat-заход).
cd /d D:\AO3_tests
echo [%date% %time%] heartbeat start >> D:\AO3_tests\logs\heartbeat.log
call C:\Users\user\AppData\Roaming\npm\claude.cmd -p "/qa-loop 3" --model sonnet >> D:\AO3_tests\logs\heartbeat.log 2>&1
echo [%date% %time%] heartbeat end (exit %errorlevel%) >> D:\AO3_tests\logs\heartbeat.log
