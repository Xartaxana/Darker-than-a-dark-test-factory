# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-14T09:45:53Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **294.2** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **0**
- p0_automation_coverage: **64%** (9/14)
- p1_automation_coverage: **41%** (12/29)
  - непокрытые P0: TC-021, TC-009, TC-013, TC-014, TC-015
- Test debt открыт: **3** — AT-BUG-005, AT-BUG-006, AT-BUG-008
- Карантин автотестов: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (58)

- Draft: **1** · Review: **17** · Approved: **19** · Automated: **21**
- автотесты (B3): active: **21**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  | 1 |  |  |
| browser |  | 2 |  | 6 |  |
| downloads |  | 3 | 2 | 3 |  |
| errors |  |  | 1 |  |  |
| filter-profiles |  |  | 3 |  |  |
| library | 1 | 1 | 4 | 2 |  |
| rating |  | 6 | 2 | 2 |  |
| settings |  | 1 | 2 | 3 |  |
| smoke |  |  |  | 5 |  |
| tabs |  | 1 | 4 |  |  |
| visibility |  | 3 |  |  |  |

## Баги (1)

- Open: **1**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»

## Известные проблемы, known_issue (0)

- нет

## Test debt (4)

- AT-BUG-005 [missing_fixture] Open — SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов
- AT-BUG-006 [missing_fixture] Open — Таблица filter_profiles не поддержана в seed_db.py и нет replay-записи формы AO3 Sort&Filter — блокирует автоматизацию батча filter-profiles (TC-040/041/042, P1)
- AT-BUG-007 [broken_environment] Fixed — Нет таймаут-гейта на висящие Appium-вызовы: зависший in-flight запрос вешает весь suite вместо падения одного теста (нет pytest-timeout / client read-timeout)
- AT-BUG-008 [flaky_test] Open — FLAKY: test_rate_work_from_work_page_panel (live AO3) — тихая смерть процесса приложения на splash внутри полного p0-прогона; в изоляции проходит

## Прогоны (1)

- Closed: **1**

## Активные локи (0)

- нет

## Эскалации (0)

- нет
