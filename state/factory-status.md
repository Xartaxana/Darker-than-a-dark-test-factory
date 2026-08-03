# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-08-03T16:38:05Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **781.1** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **83%** (77/93)
- Test debt открыт: **1** — AT-BUG-046
- Карантин автотестов: **0**
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (168)

- Review: **24** · Approved: **1** · Automated: **143**
- автотесты (B3): active: **143**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  | 3 |  | 3 |  |
| backup |  | 4 |  | 1 |  |
| browser |  | 6 |  | 13 |  |
| canary |  |  |  | 23 |  |
| compatibility |  |  |  | 3 |  |
| downloads |  | 4 |  | 14 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  |  | 5 |  |
| library |  |  |  | 17 |  |
| performance |  |  |  | 4 |  |
| rating |  | 3 | 1 | 20 |  |
| security |  |  |  | 6 |  |
| settings |  | 4 |  | 11 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 11 |  |
| visibility |  |  |  | 6 |  |

## Баги (15)

- Open: **14** · Intended: **1**
- BUG-001 [minor] Open — PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-014 [major] Open — Авто-скачивание Favorite срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот
- BUG-017 [major] Open — Быстрое закрытие вкладок → долгий парад снекбаров; подозрение на потерю Undo-токенов при задержке показа
- BUG-018 [major] Open — DOM-ссылка «Next →» указывает на уже показанную страницу; тап уводит назад
- BUG-019 [major] Open — Back после автопрыжка плотности не выводит назад — ловушка + рост истории
- BUG-020 [major] Open — Простановка DISLIKE уводит пользователя со страницы; автонавигация live-push под открытым bottom-sheet
- BUG-021 [major] Open — Снятие рейтинга через overlay листинга у скачанной работы обнуляет downloadPath и личные теги; правка заметки — то же
- BUG-022 [major] Open — Панель рейтинга work-страницы при dispose переписывает рейтинг, который пользователь не менял — возврат на Browse после Clear all ratings воскрешает удалённую запись
- BUG-046 [major] Open — Ручной скан при двух файлах одного ao3Id не сходится: счётчик relinked=2 на одну работу, повторный скан рапортует то же, не становясь 0
- BUG-047 [major] Open — Удаление скачанного файла из карточки удаляет только один файл; при двух файлах одного ao3Id второй остаётся на диске и воскрешает работу при повторном сканировании

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Intended — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (2)

- AT-BUG-045 [flaky_test] Fixed — settings_steps.py::assert_ratings_present/assert_no_ratings/assert_rating_rows_empty — пустой stdout (в т.ч. отказ транспорта) неотличим от 'нет sqlite3 на образе', степень тихо пропускает проверку
- AT-BUG-046 [missing_fixture] Open — seed_db.py не даёт прямого сидинга комбинированных baseline-строк work_ratings (comment+tags+downloadPath; rating=null+downloadPath), а read_work_ratings() не отдаёт title/author/downloadPath — TC-151/152/155/156 вынуждены строить состояние дверями приложения

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **8**
- charters_executed: **8**
- bugs_per_charter: **1.25**
- new_tc_from_charters: **15**

## Активные локи (1)

- AT-BUG-045 — `test-maintainer:2026-08-03T18:35:57+02:00`

## Эскалации (13)

- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-01T16:01:07Z] **BUG-017** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-30T00:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-03T16:07:33Z] **CH-006:followup_tc#0** [sla:charter_followup_unprocessed] — followup_tc[0] без id-токена: «КАНДИДАТ (id за test-designer): гейт infinite-scroll на ГРАНИЦЕ навигации — ON→a…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-006:followup_tc#1** [sla:charter_followup_unprocessed] — followup_tc[1] без id-токена: «КАНДИДАТ: автопрыжок плотности checkPageDensity — одиночный (пустая стр.1 → page…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-006:followup_tc#2** [sla:charter_followup_unprocessed] — followup_tc[2] без id-токена: «КАНДИДАТ: эвикция окна PAGE_WINDOW=3 — состав DOM после каскада + подмена listin…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-006:followup_tc#3** [sla:charter_followup_unprocessed] — followup_tc[3] без id-токена: «КАНДИДАТ: browse-tap-to-scroll как live-push в СТАРУЮ вкладку — флаг доехал без …» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-006:new_risks** [sla:charter_followup_unprocessed] — new_risks предложен (2 запис.), но в docs/01-test-strategy.md нет маркера «Пересмотр по чартеру CH-006» | нужно: test-strategist доносит риск до §10
- [2026-08-03T16:07:33Z] **CH-007:followup_tc#2** [sla:charter_followup_unprocessed] — followup_tc[2] без id-токена: «КАНДИДАТ: формат бэкапа как контракт — верхний уровень ровно {version, works, fi…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-007:followup_tc#3** [sla:charter_followup_unprocessed] — followup_tc[3] без id-токена: «КАНДИДАТ: фильтр-профили × Restore — локально ПЕРЕИМЕНОВАННЫЙ профиль остаётся п…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-007:followup_tc#4** [sla:charter_followup_unprocessed] — followup_tc[4] без id-токена: «КАНДИДАТ: негатив Restore — не-JSON и пустой файл: 'Restore failed', база не изм…» | нужно: test-designer заводит TC-NNN
- [2026-08-03T16:07:33Z] **CH-007:new_risks** [sla:charter_followup_unprocessed] — new_risks предложен (4 запис.), но в docs/01-test-strategy.md нет маркера «Пересмотр по чартеру CH-007» | нужно: test-strategist доносит риск до §10
