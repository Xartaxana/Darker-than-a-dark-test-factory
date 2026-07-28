# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-28T20:10:49Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **640.6** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **87%** (33/38)
- p1_automation_coverage: **93%** (54/58)
  - непокрытые P0: TC-118, TC-119, TC-120, TC-121, TC-122
- Test debt открыт: **3** — AT-BUG-029, AT-BUG-030, AT-BUG-031
- Карантин автотестов: **0**
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (122)

- Review: **11** · Automated: **110** · Blocked: **1**
- автотесты (B3): active: **110**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  |  |  | 3 |  |
| backup |  |  |  | 1 |  |
| browser |  |  |  | 9 |  |
| canary |  | 5 |  | 18 |  |
| compatibility |  |  |  | 3 |  |
| downloads |  | 6 |  | 8 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  |  | 5 |  |
| library |  |  |  | 15 |  |
| performance |  |  |  | 4 |  |
| rating |  |  |  | 14 |  |
| security |  |  |  | 6 |  |
| settings |  |  |  | 6 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 6 |  |
| visibility |  |  |  | 6 |  |

## Баги (7)

- Open: **7**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-014 [major] Open — Авто-скачивание Favorite срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (4)

- AT-BUG-026 [broken_environment] Fixed — qemu-system-x86_64.exe крашится (0xc0000005) mid-test на тяжёлом live-рендере AO3 в эмуляторном WebView — sibling AT-BUG-016/ESC-002, охватывает LIVE-canary-поверхность
- AT-BUG-029 [missing_fixture] Open — listing_basic.mitm не несёт .html-файл скачивания (недостаёт одной транзакции) — блокирует автоматизацию TC-115 (edge-vs-level BUG-014 через листинг)
- AT-BUG-030 [missing_fixture] Open — render_work_page_html не несёт ни whitelisted <button> (со span-потомком), ни НЕ-whitelisted интерактивного узла, ни достаточной высоты в теле работы — блокирует TC-119/TC-120/TC-122 (bridge-tap-zone-guard)
- AT-BUG-031 [broken_environment] Open — Stop-NodeProcesses (tasks.ps1) убивает ЛЮБОЙ node.exe по имени — коллатеральный риск для чужих неAO3 node-процессов на этом же хосте

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **5**
- charters_executed: **5**
- bugs_per_charter: **0.4**
- new_tc_from_charters: **1**

## Активные локи (0)

- нет

## Эскалации (4)

- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
