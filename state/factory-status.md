# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-20T06:03:20Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **434.5** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **91%** (29/32)
- p1_automation_coverage: **78%** (35/45)
  - непокрытые P0: TC-079, TC-081, TC-083
- Test debt открыт: **1** — AT-BUG-023
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (95)

- Approved: **14** · Automated: **80** · Blocked: **1**
- автотесты (B3): active: **80**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  | 1 | 8 |  |
| canary |  |  | 3 | 15 |  |
| downloads |  |  |  | 8 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  | 2 | 3 |  |
| library |  |  | 1 | 14 |  |
| rating |  |  | 4 | 10 |  |
| settings |  |  |  | 6 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 6 |  |
| visibility |  |  | 3 | 3 |  |

## Баги (4)

- Open: **4**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [minor] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (2)

- AT-BUG-022 [missing_fixture] Fixed — Нет наблюдения, различающего рабочий switchTab от no-op, когда цель — вкладка-0: assert_active_tab_url(HOME) после reduce-to-one тривиально проходит независимо от факта переключения — блокирует TC-084
- AT-BUG-023 [missing_fixture] Open — 2 P0 canary tests не запускаются: отсутствуют фикстуры disliked_work_with_comment_seeded и disliked_work_with_custom_tag_seeded в conftest.py

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **3**
- charters_executed: **3**
- bugs_from_charters: **1**
- tc_from_charters: **1**

## Активные локи (0)

- нет

## Эскалации (0)

- нет
