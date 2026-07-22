# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-22T11:49:14Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **488.2** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (34/34)
- p1_automation_coverage: **89%** (47/53)
- Test debt открыт: **0**
- Карантин автотестов: **0**
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (111)

- Review: **12** · Automated: **98** · Blocked: **1**
- автотесты (B3): active: **98**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  | 3 |  |  |  |
| backup |  |  |  | 1 |  |
| browser |  |  |  | 9 |  |
| canary |  |  |  | 18 |  |
| compatibility |  | 3 |  |  |  |
| downloads |  |  |  | 8 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  |  | 5 |  |
| library |  |  |  | 15 |  |
| performance |  |  |  | 4 |  |
| rating |  |  |  | 14 |  |
| security |  | 6 |  |  |  |
| settings |  |  |  | 6 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 6 |  |
| visibility |  |  |  | 6 |  |

## Баги (4)

- Open: **4**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (1)

- AT-BUG-024 [missing_fixture] Fixed — Второй AVD (нижний API level, minSdk 26, rootable без Google Play) отсутствует в tools/avd — блокирует автоматизацию TC-109 (compatibility, P2)

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **4**
- charters_executed: **4**
- bugs_per_charter: **0.25**
- new_tc_from_charters: **1**

## Активные локи (0)

- нет

## Эскалации (3)

- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
