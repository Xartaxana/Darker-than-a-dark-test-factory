---
name: run-suite
description: Прогнать набор тестов (smoke/regression/canary) на эмуляторе и оформить отчёт о прогоне. Использовать, когда пользователь просит "прогнать тесты", "запустить smoke/регрессию/canary", "проверить сборку".
---

# /run-suite — прогон набора

Запусти агента **test-runner** (Task, subagent_type: test-runner) для указанного набора.

Разбор `$ARGUMENTS`:
- `smoke` (по умолчанию) → `pytest -m p0`, режим live.
- `regression` → `pytest -m "p0 or p1"`, режим replay (при доступности; иначе live с
  предупреждением).
- `canary` → `pytest -m live` (canary/tests), режим live — минимально, AO3 сторонний.
- допускается `--mode live|replay`.

Агент сам поднимет окружение (`scripts/tasks.ps1`: Start-Emulator/Start-Appium/Install-App),
прогонит набор, создаст `runs/RUN-<ts>.md` по шаблону и обновит
`state/app-under-test.yaml`. По завершении покажи пользователю итоги
(passed/failed/длительность, путь к отчёту и Allure) и, если есть падения, напомни,
что дальше нужен `/triage`.
