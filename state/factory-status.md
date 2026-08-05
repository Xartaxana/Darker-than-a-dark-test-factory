# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-08-05T03:30:51Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Release readiness

- Сборка: 1.11 (versionCode 12), commit `bfc8f41a`, built_at 2026-08-04T20:03:38Z
- smoke: Triaged · smoke_freshness_hours: **0.2** (RUN-20260805-0432)
- regression: Triaged · regression_freshness_hours: **0.2** (RUN-20260805-0437)
- canary: Triaged · canary_freshness_hours: **15.8** (RUN-20260804-1317)
- Открытые blocker/critical: **0**
- Известные проблемы (known_issue): **2**
- p0_automation_coverage: **100%** (37/37)
- p1_automation_coverage: **80%** (77/96)
- Test debt открыт: **7** — AT-BUG-047, AT-BUG-048, AT-BUG-053, AT-BUG-054, AT-BUG-055, AT-BUG-057, AT-BUG-058
- Карантин автотестов: **3** — TC-016, TC-134, TC-135
- Automated без red_probe: **0**
- Untriaged: **0** · untriaged_failure_age: **0**

## Сборка под тестом

- 1.11 (versionCode 12), commit `bfc8f41a`, built_at 2026-08-04T20:03:38Z
- smoke: failed · regression: failed

## Тест-кейсы (172)

- Review: **27** · Approved: **2** · Automated: **143**
- автотесты (B3): active: **140** · quarantined: **3**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| accessibility |  | 2 | 1 | 3 |  |
| backup |  | 6 |  | 1 |  |
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
| settings |  | 6 |  | 11 |  |
| smoke |  |  |  | 5 |  |
| tabs |  |  |  | 11 |  |
| visibility |  |  |  | 6 |  |

## Баги (22)

- Open: **17** · Rejected: **1** · Intended: **2** · Blocked: **2**
- BUG-011 [major] Open — Restore from backup пропускает работы молча, если файл с тем же ao3Id уже лежит в папке загрузок
- BUG-013 [minor] Open — Смена темы, затем немедленный kill процесса (<100 мс) теряет theme_mode — выбор темы не персистится
- BUG-014 [major] Blocked — Авто-скачивание Favorite срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы
- BUG-016 [major] Open — Undo закрытия вкладки на потолке 10 молча теряет вкладку и её снапшот
- BUG-017 [major] Open — Быстрое закрытие вкладок → долгий парад снекбаров; подозрение на потерю Undo-токенов при задержке показа
- BUG-018 [major] Open — DOM-ссылка «Next →» указывает на уже показанную страницу; тап уводит назад
- BUG-019 [major] Open — Back после автопрыжка плотности не выводит назад — ловушка + рост истории
- BUG-020 [major] Open — Простановка DISLIKE уводит пользователя со страницы; автонавигация live-push под открытым bottom-sheet
- BUG-021 [major] Open — Снятие рейтинга через overlay листинга у скачанной работы обнуляет downloadPath и личные теги; правка заметки — то же
- BUG-022 [major] Open — Панель рейтинга work-страницы при dispose переписывает рейтинг, который пользователь не менял — возврат на Browse после Clear all ratings воскрешает удалённую запись
- BUG-046 [major] Open — Ручной скан при двух файлах одного ao3Id не сходится: счётчик relinked=2 на одну работу, повторный скан рапортует то же, не становясь 0
- BUG-048 [major] Open — Overlay листинга молча перезаписывает title/fandom/wordCount скрейпом текущей страницы — работа исчезает из фандом-фильтра, прыгает в сортировке, а при rating=null пропадает со всех вкладок Library без какого-либо сообщения
- BUG-049 [minor] Open — Снекбар «Tab closed» перекрывает нижнюю навигацию на узких экранах — кнопка Undo и таб Library недоступны одновременно
- BUG-050 [minor] Open [accepted_risk] — Длинный заголовок работы в снекбаре Undo обрезается без многоточия — конец слова просто исчезает
- BUG-051 [minor] Open — Поиск в Library принимает чисто пробельный запрос — список мигает пустой выдачей вместо игнорирования
- BUG-052 [minor] Blocked — Scan for downloads не показывает прогресс при большом числе файлов — кнопка выглядит зависшей
- BUG-056 [major] Open — Bridge-скрипт падает на document.head.appendChild — Rate-кнопки не инжектируются
- BUG-057 [major] Open — Авто-скачивание НЕ запускается при первичной простановке Favorite через панель work-страницы (регрессия фикса BUG-014, путь onRateWorkRequested)

## Известные проблемы, known_issue (2)

- BUG-012 [minor] Intended — Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии
- BUG-015 [major] Open — Авто-клик kudos на AO3 срабатывает ретроактивно при правке тега ранее отмеченной работы

## Test debt (7)

- AT-BUG-047 [flaky_test] Open — Гонка «wait_ui_ready → немедленная WebView-навигация»: стартовая загрузка Home ещё в полёте, chromedriver теряет цель (`cannot determine loading status from no such window`) — 27 call sites, экземпляр TC-043 в RUN-20260803-2012
- AT-BUG-048 [flaky_test] Open — BaseScreen.swipe_to_text проскакивает искомую секцию под нагрузкой (fling-инерция + опрос раз в свайп) — Settings докручивается до конца списка, ассерт «секция не найдена прокруткой»; экземпляр TC-093 в RUN-20260803-2012
- AT-BUG-053 [weak_locator] Open — settings_screen.rename_filter_button_locator ищет content-desc «Renam3» вместо «Rename» — TC-085/TC-086 broken на шаге переименования профиля
- AT-BUG-054 [missing_fixture] Open — Replay-фикстура listing_paginated.mitm несёт class="work blurp" вместо "work blurb" — листинговая страница не опознаётся ни тестом, ни bridge'ем (TC-129/TC-130 broken)
- AT-BUG-055 [flaky_test] Open — Нестабильные TC-134/TC-135: наблюдение вкладок через `run-as cat ao3_settings.xml` слепое — пустой/неудавшийся ответ adb неотличим от «0 вкладок»
- AT-BUG-057 [flaky_test] Open — Нестабильный TC-016 (p0, live): RatingOverlay не открывается на странице работы после open_work_page → open_tab(Browse); в изоляции 3/3 зелёный
- AT-BUG-058 [broken_environment] Open — TC-096 замеряет холодный старт (force-stop+pm clear+am start -W) ПОД активной Appium-сессией — запуск не рапортует завершение, TimeoutError 60s; та же последовательность без сессии — 6/6 успешных, ~6.0-6.3s

## Прогоны (8)

- Triaged: **5** · Closed: **2** · Blocked: **1**

## Exploratory

- Done: **8**
- charters_executed: **8**
- bugs_per_charter: **1.25**
- new_tc_from_charters: **15**

## Активные локи (0)

- нет

## Эскалации (8)

- [2026-07-21T22:43:25Z] **BUG-013** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-19T17:30:00Z | нужно: ответить в ## Обсуждение
- [2026-07-24T05:10:04Z] **BUG-011** [sla:bug_open_major] — major-баг open с 2026-07-15T14:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-07-30T12:38:12Z] **BUG-016** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-28T12:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-01T16:01:07Z] **BUG-017** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-07-30T00:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-04T11:26:57Z] **BUG-021** [sla:question_unanswered] — ждёт ответа разработчика (awaiting: dev) с 2026-08-02T00:00:00Z | нужно: ответить в ## Обсуждение
- [2026-08-04T15:01:41Z] **BUG-016** [sla:bug_open_major] — major-баг open с 2026-07-28T12:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-04T15:01:41Z] **BUG-051** [sla:bug_open_minor] — minor-баг open с 2026-07-02T04:00:00Z без движения | нужно: Fixed/Rejected/Intended или комментарий с планом
- [2026-08-04T18:18:52Z] **BUG-052** — конфликт борда↔артефакт: человек→Intended, агент→Rejected. Артефакт переведён в Blocked, нужно решение человека.
