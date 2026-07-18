# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-18T18:15:54Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **398.7** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **0**
- p0_automation_coverage: **44%** (14/32)
- p1_automation_coverage: **94%** (32/34)
  - непокрытые P0: TC-066, TC-067, TC-068, TC-069, TC-070, TC-071, TC-072, TC-073, TC-074, TC-075, TC-076, TC-077, TC-078, TC-079, TC-080, TC-081, TC-082, TC-083
- Test debt открыт: **2** — AT-BUG-016, AT-BUG-018
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (83)

- Approved: **21** · Automated: **62**
- автотесты (B3): active: **62**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  |  | 8 |  |
| canary |  |  | 18 |  |  |
| downloads |  |  |  | 8 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  | 1 | 2 |  |
| library |  |  |  | 14 |  |
| rating |  |  |  | 10 |  |
| settings |  |  | 1 | 6 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  | 1 | 4 |  |
| visibility |  |  |  | 3 |  |

## Баги (3)

- Open: **3**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [minor] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Известные проблемы, known_issue (0)

- нет

## Test debt (4)

- AT-BUG-015 [missing_evidence] Fixed — TC-047 scroll-preservation assert недобит — WebView scrollY на Browse root не даёт устойчивого ненулевого значения после scrollTo (нужна диагностика)
- AT-BUG-016 [broken_environment] Open — TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация
- AT-BUG-017 [broken_environment] Fixed — replay-фикстура: интермиттентный net::ERR_PROXY_CONNECTION_FAILED на первой навигации после set_device_proxy — не покрыт rerun-whitelist pytest.ini
- AT-BUG-018 [broken_environment] Open — long-press по ссылке в WebView не триггерит нативный setOnLongClickListener надёжно через Appium/UiAutomator2 (TC-026, фоновая вкладка)

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
