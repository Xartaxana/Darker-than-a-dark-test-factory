# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-21T14:33:07Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **467.0** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **91%** (29/32)
- p1_automation_coverage: **91%** (41/45)
  - непокрытые P0: TC-079, TC-081, TC-083
- Test debt открыт: **0**
- Карантин автотестов: **0**
- Automated без red_probe: **29** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005, TC-084
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (95)

- Approved: **7** · Automated: **87** · Blocked: **1**
- автотесты (B3): active: **87**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  |  | 9 |  |
| canary |  |  | 3 | 15 |  |
| downloads |  |  |  | 8 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  |  | 5 |  |
| library |  |  |  | 15 |  |
| rating |  |  | 1 | 13 |  |
| settings |  |  |  | 6 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 6 |  |
| visibility |  |  | 3 | 3 |  |

## Баги (4)

- Open: **4**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (2)

- AT-BUG-022 [missing_fixture] Fixed — Нет наблюдения, различающего рабочий switchTab от no-op, когда цель — вкладка-0: assert_active_tab_url(HOME) после reduce-to-one тривиально проходит независимо от факта переключения — блокирует TC-084
- AT-BUG-023 [missing_fixture] Fixed — 2 P0 canary tests не запускаются: отсутствуют фикстуры disliked_work_with_comment_seeded и disliked_work_with_custom_tag_seeded в conftest.py

## Прогоны (1)

- Closed: **1**

## Exploratory

- Planned: **1** · Done: **3**
- charters_executed: **3**
- bugs_per_charter: **0.33**
- new_tc_from_charters: **1**

## Активные локи (0)

- нет

## Эскалации (2)

- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
