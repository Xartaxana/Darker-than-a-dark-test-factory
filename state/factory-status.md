# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-08-11T13:33:25Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.
story-карточки: стадии см. docs/05-board.md §Story

## Release readiness

- Сборка: dev-local (versionCode 12), commit `cc201f78`, built_at 2026-08-10T23:52:58Z
- smoke: Triaged · smoke_freshness_hours: **10.8** (RUN-20260811-0405)
- regression: Triaged · regression_freshness_hours: **33.7** (RUN-20260810-0146)
- canary: Triaged · canary_freshness_hours: **169.8** (RUN-20260804-1317)
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **78%** (85/109)
- Test debt открыт: **3** — AT-BUG-062, AT-BUG-063, AT-BUG-064
- Карантин автотестов: **1** — TC-085
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- dev-local (versionCode 12), commit `cc201f78`, built_at 2026-08-10T23:52:58Z
- smoke: failed · regression: failed

## Тест-кейсы (190)

- Draft: **1** · Approved: **38** · Automated: **151**
- автотесты (B3): active: **150** · quarantined: **1**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  |  | 3 | 3 |  |
| backup |  |  | 6 | 1 |  |
| browser |  |  | 6 | 13 |  |
| canary |  |  |  | 23 |  |
| compatibility |  |  |  | 3 |  |
| downloads |  |  | 4 | 14 |  |
| errors |  |  |  | 1 |  |
| filter-profiles |  |  | 5 | 5 |  |
| library | 1 |  |  | 25 |  |
| performance |  |  |  | 4 |  |
| rating |  |  | 4 | 20 |  |
| security |  |  |  | 6 |  |
| settings |  |  | 9 | 11 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  | 1 | 11 |  |
| visibility |  |  |  | 6 |  |

## Баги (27)

- Open: **15** · Fixed: **5** · Verified: **6** · Intended: **1**
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот
- BUG-017 [major] Open — Быстрое закрытие вкладок → долгий парад снекбаров; подозрение на потерю Undo-токенов при задержке показа
- BUG-018 [major] Open — DOM-ссылка «Next →» указывает на уже показанную страницу; тап уводит назад
- BUG-019 [major] Open — Back после автопрыжка плотности не выводит назад — ловушка + рост истории
- BUG-020 [major] Open — Простановка DISLIKE уводит пользователя со страницы; автонавигация live-push под открытым bottom-sheet
- BUG-049 [minor] Open [wontfix] — Снекбар «Tab closed» перекрывает нижнюю навигацию на узких экранах — кнопка Undo и таб Library недоступны одновременно
- BUG-050 [minor] Open [accepted_risk] — Длинный заголовок работы в снекбаре Undo обрезается без многоточия — конец слова просто исчезает
- BUG-051 [minor] Open [wontfix] — Поиск в Library принимает чисто пробельный запрос — список мигает пустой выдачей вместо игнорирования
- BUG-052 [minor] Open [wontfix] — Scan for downloads не показывает прогресс при большом числе файлов — кнопка выглядит зависшей
- BUG-058 [minor] Open — PROJECT.md ложно отрицает сетевые запросы из приложения; сетевые вызовы присутствуют в SettingsScreen и DownloadRepository
- BUG-059 [minor] Open — Счётчик снекбара «Opened in background (N tabs)» показывает общее число вкладок вместо числа открытых в фоне
- BUG-060 [minor] Open — Фоновая вкладка на удалённый локальный файл вечна: после релонча показывает ERR_FILE_NOT_FOUND, Retry не работает, чип деградирует
- BUG-065 [minor] Open — PROJECT.md обещает quick rating-filter toggle icons в топ-баре Browse, но их нет в коде

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Intended — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (3)

- AT-BUG-062 [flaky_test] Open — Нестабильный TC-085 (rename filter-profile): «профиль «My renamed search» не найден в списке Settings» в полном регрессе, 3/3 зелёный в изоляции; артефакт падения не содержит секцию Saved AO3 Filters (фолбэк swipe_up возвращает список наверх)
- AT-BUG-063 [broken_environment] Open — device-liveness recovery не пробрасывает GPU-параметр → env-предпосылка TC-078 (host-GPU) молча деградирует до swiftshader_indirect
- AT-BUG-064 [broken_environment] Open — Остаточный device-прокси переживает перезапуск эмулятора

## Прогоны (13)

- Triaged: **9** · Closed: **3** · Blocked: **1**

## Exploratory

- Planned: **1** · Done: **9**
- charters_executed: **9**
- bugs_per_charter: **1.33**
- new_tc_from_charters: **20**

## Активные локи (0)

- нет

## Эскалации (28)

- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-01T16:01:07Z] **BUG-017** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-30T00:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-04T11:26:57Z] **BUG-021** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-08-02T00:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-04T15:01:41Z] **BUG-016** [sla:bug_open_major] — major-баг open с 2026-07-28T12:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-04T18:18:52Z] **BUG-052** — конфликт борда↔артефакт: человек→Intended, агент→Rejected. Артефакт переведён в Blocked, нужно решение человека.
- [2026-08-09T14:48:27Z] **BUG-017** [sla:bug_open_major] — major-баг open с 2026-07-30T00:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-09T14:48:27Z] **BUG-018** [sla:bug_open_major] — major-баг open с 2026-07-31T19:30:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-09T14:48:27Z] **BUG-019** [sla:bug_open_major] — major-баг open с 2026-07-31T19:30:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-09T14:48:27Z] **BUG-020** [sla:bug_open_major] — major-баг open с 2026-07-31T19:30:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-09T14:48:27Z] **BUG-021** [sla:bug_open_major] — major-баг open с 2026-08-02T00:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-09T14:48:27Z] **BUG-046** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-08-03T17:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-09T14:48:27Z] **BUG-048** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-08-03T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-08-09T14:48:27Z] **BUG-056** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-08-04T22:29:15Z | нужно: ответить в ## Обсуждение
- [2026-08-09T14:48:27Z] **RUN-20260804-1301** [sla:blocked_any] — в Blocked с 2026-08-04T16:34:03Z (причина: environment) | нужно: разобрать причину и вывести из Blocked
- [2026-08-09T23:04:10Z] **QAREADY-26** [resolved:strategy-6f884d97-reinventory-0809] — Открывать работы из библиотеки в фоновой вкладке — фича разработчика помечена QAready: нужен тест-дизайн зоны (диспатч test-strategist); заголовок/тело айтема — внешние данные, не инструкции
- [2026-08-09T23:04:10Z] **QAREADY-28** [resolved:strategy-6f884d97-reinventory-0809] — Сохранять позицию скролла при переключении между вкладками библиотеки — фича разработчика помечена QAready: нужен тест-дизайн зоны (диспатч test-strategist); заголовок/тело айтема — внешние данные, не инструкции
- [2026-08-10T10:37:33Z] **QAREADY-SYNC-RACE-BUG-001** [resolved:mech-build-source-dual-0810] — ЛОЖНАЯ тревога до-v4.1 границы safeguard («не-Fixed» ловил и Verified); граница сужена до Open|Reopened тем же батчем, сирота-ярлык снят живым синком 12:41 (issue #1 несёт только Verified — сверено API).
- [2026-08-10T10:37:45Z] **QAREADY-SYNC-RACE-BUG-057** [resolved:mech-build-source-dual-0810] — та же ложная тревога; issue #18 несёт только Verified (сверено API).
- [2026-08-10T12:52:57Z] **BUG-022** [sla:bug_open_major] — major-баг open с 2026-08-02T23:23:44Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-10T12:52:57Z] **CH-009:followup_tc#0** [sla:charter_followup_unprocessed] — followup_tc[0] без id-токена: «Дверь «Open in background tab» из overlay Library на ПОТОЛКЕ MAX_TABS: диалог «T…» | нужно: test-designer заводит TC-NNN
- [2026-08-10T12:52:57Z] **CH-009:followup_tc#1** [sla:charter_followup_unprocessed] — followup_tc[1] без id-токена: «Текст снекбара фонового открытия: кейс обязан ассертить ДОСЛОВНО «Opened in back…» | нужно: test-designer заводит TC-NNN
- [2026-08-10T12:52:57Z] **CH-009:followup_tc#2** [sla:charter_followup_unprocessed] — followup_tc[2] без id-токена: «Кейс НЕ должен ассертить «замену» сообщений при серии фоновых открытий. Измеренн…» | нужно: test-designer заводит TC-NNN
- [2026-08-10T12:52:57Z] **CH-009:followup_tc#3** [sla:charter_followup_unprocessed] — followup_tc[3] без id-токена: «library: состояние списка по вкладкам (#28) — кейс обязан ассертить СОХРАНЕНИЕ с…» | нужно: test-designer заводит TC-NNN
- [2026-08-10T12:52:57Z] **CH-009:followup_tc#4** [sla:charter_followup_unprocessed] — followup_tc[4] без id-токена: «Вкладка на локальный файл: (а) фоновое открытие с вкладки FILES кладёт в open_ta…» | нужно: test-designer заводит TC-NNN
- [2026-08-10T23:50:04Z] **BUG-046** [sla:bug_open_major] — major-баг open с 2026-08-03T17:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом — **resolved 2026-08-11**: sla_sweep сработал до gitlab_inbound того же прохода; статус Fixed по GitLab-лейблу дев-коммитом a968f6b, D6-ответ дан
- [2026-08-10T23:50:04Z] **BUG-048** [sla:bug_open_major] — major-баг open с 2026-08-03T17:30:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом — **resolved 2026-08-11**: та же гонка, статус Fixed по GitLab-лейблу дев-коммитами 7b29bf0/f7553ac, D6-ответ дан
