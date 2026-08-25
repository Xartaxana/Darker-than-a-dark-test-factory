---
name: run-suite
description: Прогнать набор тестов (smoke/regression/canary) на эмуляторе и оформить отчёт о прогоне. Использовать, когда пользователь просит "прогнать тесты", "запустить smoke/регрессию/canary", "проверить сборку".
---

# /run-suite — прогон набора

Запусти агента **test-runner** (Task, subagent_type: test-runner) для указанного набора.

Разбор `$ARGUMENTS`:
- `smoke` (по умолчанию) → `pytest -m p0`, режим live.
- `regression` → `pytest -m "p0 or p1"`, режим replay (при доступности; иначе live с
  предупреждением). Включает L2 bridge-тесты (маркер `bridge`, всегда несут
  `p1`, device-free, docs/tasks/p2-pyramid-bridge.md Р3). **Device-метрики
  времени** (сравнение длительности прогонов между собой) считаются
  ОТДЕЛЬНЫМ фильтром `-m "(p0 or p1) and not bridge"` — bridge не грузит
  эмулятор, включать его в базу счёта device-времени нельзя (docs/tasks/
  p2-pyramid-bridge.md Р5).
- `canary` → `pytest -m live` (canary/tests), режим live — минимально, AO3 сторонний.
- `compatibility` → `pytest tests/test_compatibility.py`, режим live, **стек 2
  (`Use-DeviceStack -N 2`, лиза обязательна)**. Каденция — раз в неделю
  (правило rules.yaml «Еженедельный compatibility-прогон», слово владельца
  2026-08-25); набор — TC-109/110/111 (второй, нижний практичный API level
  api29 + системная dark/light матрица + portrait/landscape). Единственный
  набор, где api29 — не черновой коридор, а САМ объект проверки: посменный
  api34-якорь топологии 2026-08-21 сюда не применяется. Отказ лизы
  (`DEVICE_LEASE_BLOCKED`) = `Blocked` + доклад, НЕ «битая среда».
- допускается `--mode live|replay`.

Агент сам поднимет окружение (`scripts/tasks.ps1`: `Use-DeviceStack -N 1` (spec-
p3-second-emulator N3 — берёт машинную лизу стека 1 ДО Start-Emulator/Start-
Appium; стек по умолчанию, `/run-suite` не принимает выбор стека — параллельный
прогон на стеке 2 запускается отдельно, вручную) → Start-Emulator/Start-Appium/
Install-App; топология эмуляторов — оператор 2026-08-21: пара = 2×api29, стек 1
поднимается ЯВНО `Start-Emulator -AvdName ao3_corridor_api29`, api34 — только
посменный вердиктный прогон в 1 проход, см. docs/tasks/p3-second-emulator.md
§«Решение оператора по топологии»), прогонит набор, создаст `runs/RUN-<ts>.md` по шаблону и обновит
`state/app-under-test.yaml`. По завершении покажи пользователю итоги
(passed/failed/длительность, путь к отчёту и Allure) и, если есть падения, напомни,
что дальше нужен `/triage`. Если агент вернул `status: Blocked` с маркером
`DEVICE_LEASE_BLOCKED` — сообщи это пользователю как есть, не как провал
набора. Такой отказ означает РОВНО одно из двух: под лизой идёт ЖИВОЙ чужой
прогон (его PID назван в сообщении) либо `AO3_DEVICE`/`APPIUM_URL`
рассинхронизированы с лизой. Лиза, оставшаяся от ПРЕДЫДУЩЕГО завершённого
прогона того же пользователя, `Blocked` НЕ даёт — повторный
`Use-DeviceStack` продолжает её сам. Лиза транзиентна — в артефакт
причину не записываем: `status: Blocked` здесь — статус отчёта прогона,
поле `blocked_reason` не заполняется (в его enum у лизы дома нет).
