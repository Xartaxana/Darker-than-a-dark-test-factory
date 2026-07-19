# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-19T04:37:00Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **409.0** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **0**
- p0_automation_coverage: **81%** (26/32)
- p1_automation_coverage: **94%** (32/34)
  - непокрытые P0: TC-078, TC-079, TC-080, TC-081, TC-082, TC-083
- Test debt открыт: **4** — AT-BUG-018, AT-BUG-019, AT-BUG-020, AT-BUG-021
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (83)

- Approved: **9** · Automated: **74**
- автотесты (B3): active: **74**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  |  | 1 |  |
| browser |  |  |  | 8 |  |
| canary |  |  | 6 | 12 |  |
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

## Test debt (5)

- AT-BUG-016 [broken_environment] Fixed — TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация
- AT-BUG-018 [broken_environment] Open — long-press по ссылке в WebView не триггерит нативный setOnLongClickListener надёжно через Appium/UiAutomator2 (TC-026, фоновая вкладка)
- AT-BUG-019 [weak_locator] Open — navigation.py::_find_pill фильтр "WebView" not in class не исключает a11y-потомков WebView — риск клика по ссылке/чекбоксу СТРАНИЦЫ вместо нативной ручки-пилюли
- AT-BUG-020 [flaky_test] Open — TC-009[READ-work2] детерминированно падает на open_tab("Library") после dismiss_rating_overlay — NoSuchElementError на UiSelector().text("Library")
- AT-BUG-021 [broken_environment] Open — Эмулятор дважды отваливается mid-test на driver.get()/switch_to.context внутри open_live_listing (Sort&Filter форма) — DevTools disconnected -> adb device not found; кандидат-сиблинг AT-BUG-016

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
