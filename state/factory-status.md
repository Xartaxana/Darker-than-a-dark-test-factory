# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-08-02T01:37:57Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **742.0** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **91%** (71/78)
- Test debt открыт: **2** — AT-BUG-037, AT-BUG-038
- Карантин автотестов: **0**
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (144)

- Approved: **9** · Automated: **134** · Blocked: **1**
- автотесты (B3): active: **134**

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
| library |  |  | 2 | 15 |  |
| performance |  |  |  | 4 |  |
| rating |  |  | 7 | 14 |  |
| security |  |  |  | 6 |  |
| settings |  |  |  | 10 | 1 |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 11 |  |
| visibility |  |  |  | 6 |  |

## Баги (12)

- Open: **12**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-014 [major] Open — Авто-скачивание Favorite срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот
- BUG-017 [major] Open — Быстрое закрытие вкладок → долгий парад снекбаров; подозрение на потерю Undo-токенов при задержке показа
- BUG-018 [major] Open — DOM-ссылка «Next →» указывает на уже показанную страницу; тап уводит назад
- BUG-019 [major] Open — Back после автопрыжка плотности не выводит назад — ловушка + рост истории
- BUG-020 [major] Open — Простановка DISLIKE уводит пользователя со страницы; автонавигация live-push под открытым bottom-sheet
- BUG-021 [major] Open — Правка заметки скачанной работы через overlay листинга обнуляет downloadPath в Room

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Open — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (4)

- AT-BUG-035 [missing_fixture] Fixed — render_work_page_html не несёт узел #kudo_submit ни в одной replay-фикстуре — блокирует автоматизацию всей области rating/bridge auto-kudos (TC-138..144, ядро BUG-015)
- AT-BUG-036 [flaky_test] Fixed — app_steps.wait_persisted_tab_count: диагностика «последнее наблюдение» мертва — f-строка message вычисляется до первого опроса, holder всегда None
- AT-BUG-037 [flaky_test] Open — except TimeoutError глотает исключение wait_for, env-контекст теряется
- AT-BUG-038 [flaky_test] Open — писатели frontmatter в board-скриптах: EOL-перегон + отсутствие границы frontmatter

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **7**
- charters_executed: **7**
- bugs_per_charter: **1.0**
- new_tc_from_charters: **10**

## Активные локи (0)

- нет

## Эскалации (6)

- [2026-07-21T08:57:20Z] **BUG-012** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-18T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-07-21T08:57:20Z] **TC-020** [sla:blocked_any] — в Blocked с 2026-07-19T09:55:00Z (причина: product_decision) | нужно: разобрать причину и вывести из Blocked
- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-01T16:01:07Z] **BUG-017** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-30T00:00:00Z | нужно: ответить в ## Обсуждение
