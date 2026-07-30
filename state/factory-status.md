# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-30T23:54:14Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **692.3** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **93%** (66/71)
- Test debt открыт: **0**
- Карантин автотестов: **0**
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (135)

- Approved: **5** · Automated: **129** · Blocked: **1**
- автотесты (B3): active: **129**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  |  |  | 3 |  |
| backup |  |  |  | 1 |  |
| browser |  |  |  | 13 |  |
| canary |  |  |  | 23 |  |
| compatibility |  |  |  | 3 |  |
| downloads |  |  |  | 14 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  |  | 5 |  |
| library |  |  |  | 15 |  |
| performance |  |  |  | 4 |  |
| rating |  |  |  | 14 |  |
| security |  |  |  | 6 |  |
| settings |  |  |  | 10 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  | 5 | 6 |  |
| visibility |  |  |  | 6 |  |

## Баги (8)

- Open: **8**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-014 [major] Open — Авто-скачивание Favorite срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот
- BUG-017 [minor] Open — Быстрое закрытие вкладок → долгий парад снекбаров; подозрение на потерю Undo-токенов при задержке показа

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (0)

- нет

## Прогоны (1)

- Closed: **1**

## Exploratory

- Planned: **2** · Done: **5**
- charters_executed: **5**
- bugs_per_charter: **0.4**
- new_tc_from_charters: **1**

## Активные локи (1)

- TC-132 — `test-automator:2026-07-30T23:53:30Z`

## Эскалации (5)

- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
