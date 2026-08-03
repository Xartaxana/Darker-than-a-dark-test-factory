# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-08-03T18:26:42Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: Closed · smoke_freshness_hours: **782.9** (RUN-20260702-0300)
- regression: not_run
- canary: not_run
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **1**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **83%** (77/93)
- Test debt открыт: **0**
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

## Баги (16)

- Open: **15** · Intended: **1**
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
- BUG-048 [major] Open — Overlay листинга молча перезаписывает title/fandom/wordCount скрейпом текущей страницы — работа исчезает из фандом-фильтра, прыгает в сортировке, а при rating=null пропадает со всех вкладок Library без какого-либо сообщения

## Известные проблемы, known_issue (1)

- BUG-012 [minor] Intended — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

## Test debt (0)

- нет

## Прогоны (1)

- Closed: **1**

## Exploratory

- Done: **8**
- charters_executed: **8**
- bugs_per_charter: **1.25**
- new_tc_from_charters: **15**

## Активные локи (0)

- нет

## Эскалации (4)

- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-01T16:01:07Z] **BUG-017** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-30T00:00:00Z | нужно: ответить в ## Обсуждение
