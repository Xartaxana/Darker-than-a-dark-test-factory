# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-19T16:03:04Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **420.5** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **81%** (26/32)
- p1_automation_coverage: **91%** (32/35)
  - непокрытые P0: TC-078, TC-079, TC-080, TC-081, TC-082, TC-083
- Test debt открыт: **1** — AT-BUG-022
- Карантин автотестов: **0**
- Automated без red_probe: **28** — TC-021, TC-050, TC-051, TC-052, TC-053, TC-054, TC-055, TC-034, TC-035, TC-036, TC-038, TC-039, TC-016, TC-017, TC-027, TC-028, TC-029, TC-030, TC-007, TC-008, TC-047, TC-048, TC-049, TC-001, TC-002, TC-003, TC-004, TC-005
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (84)

- Review: **1** · Approved: **8** · Automated: **74** · Blocked: **1**
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
| settings |  |  |  | 6 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  | 1 | 1 | 4 |  |
| visibility |  |  |  | 3 |  |

## Баги (4)

- Open: **4**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [minor] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (4)

- AT-BUG-019 [weak_locator] Fixed — navigation.py::_find_pill фильтр "WebView" not in class не исключает a11y-потомков WebView — риск клика по ссылке/чекбоксу СТРАНИЦЫ вместо нативной ручки-пилюли
- AT-BUG-020 [weak_locator] Fixed — TC-009[READ-work2] детерминированно падает на open_tab("Library") после dismiss_rating_overlay — NoSuchElementError на UiSelector().text("Library")
- AT-BUG-021 [broken_environment] Fixed — Эмулятор дважды отваливается mid-test на driver.get()/switch_to.context внутри open_live_listing (Sort&Filter форма) — DevTools disconnected -> adb device not found; кандидат-сиблинг AT-BUG-016
- AT-BUG-022 [missing_fixture] Open — Нет наблюдения, различающего рабочий switchTab от no-op, когда цель — вкладка-0: assert_active_tab_url(HOME) после reduce-to-one тривиально проходит независимо от факта переключения — блокирует TC-084

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
