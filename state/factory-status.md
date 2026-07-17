# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-17T23:04:04Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **379.5** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **0**
- p0_automation_coverage: **71%** (10/14)
- p1_automation_coverage: **50%** (17/34)
  - непокрытые P0: TC-009, TC-013, TC-014, TC-015
- Test debt открыт: **0**
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (65)

- Approved: **36** · Automated: **29**
- автотесты (B3): active: **29**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  | 2 | 6 |  |
| downloads |  |  | 3 | 5 |  |
| errors |  |  | 1 |  |  |
| filter-profiles |  |  | 2 | 1 |  |
| library |  |  | 8 | 6 |  |
| rating |  |  | 8 | 2 |  |
| settings |  |  | 4 | 3 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  | 5 |  |  |
| visibility |  |  | 3 |  |  |

## Баги (2)

- Open: **2**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [minor] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок

## Известные проблемы, known_issue (0)

- нет

## Test debt (0)

- нет

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **1**
- charters_executed: **1**
- bugs_from_charters: **0**
- tc_from_charters: **1**

## Активные локи (0)

- нет

## Эскалации (0)

- нет
