# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-16T23:44:01Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **356.2** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **0**
- p0_automation_coverage: **71%** (10/14)
- p1_automation_coverage: **47%** (16/34)
  - непокрытые P0: TC-009, TC-013, TC-014, TC-015
- Test debt открыт: **5** — AT-BUG-005, AT-BUG-006, AT-BUG-009, AT-BUG-011, AT-BUG-012
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (65)

- Draft: **1** · Review: **1** · Approved: **35** · Automated: **28**
- автотесты (B3): active: **28**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  | 2 | 6 |  |
| downloads |  |  | 3 | 5 |  |
| errors |  |  | 1 |  |  |
| filter-profiles |  |  | 3 |  |  |
| library | 1 |  | 7 | 6 |  |
| rating |  |  | 8 | 2 |  |
| settings |  |  | 4 | 3 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  | 5 |  |  |
| visibility |  | 1 | 2 |  |  |

## Баги (2)

- Open: **2**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [minor] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок

## Известные проблемы, known_issue (0)

- нет

## Test debt (5)

- AT-BUG-005 [missing_fixture] Open — SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов
- AT-BUG-006 [missing_fixture] Reopened — Таблица filter_profiles не поддержана в seed_db.py и нет replay-записи формы AO3 Sort&Filter — блокирует автоматизацию батча filter-profiles (TC-040/041/042, P1)
- AT-BUG-009 [flaky_test] Open — FLAKY(?): test_disliked_hidden_on_listing (TC-013, replay) — ReadTimeoutError к локальному Appium внутри driver.get() при полном p0 после длинной сессии; в изоляции ранее многократно зелёный за 20-25s
- AT-BUG-011 [broken_environment] Open — Фикстура replay не проверяет присутствие mitm-CA перед тестом — без CA каждый replay-тест умирает 120–240с ReadTimeoutError вместо мгновенной диагностики (мисдиагнозы каскадом: ESC-001, ложный Reopened AT-BUG-006)
- AT-BUG-012 [broken_environment] Open — Start-Emulator: загрузка quickboot-снапшота default_boot нестабильна — qemu тихо крэшит (~20с, процесса нет), остаются стейл-локи multiinstance.lock; воспроизведено 4+ раза

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
