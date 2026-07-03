# 04 — Дорожная карта внедрения

Каждая фаза имеет критерий выхода — без него не переходим дальше (принцип gate из BMAD TEA).

> **Статус Фазы 0: ЗАВЕРШЕНА.** Окружение развёрнуто, виртуализация включена
> (AEHD 2.2), эмулятор `ao3_test_api34` работает, debug-APK собран и установлен.
> Спайк **A пройден** (Appium видит и native, и WEBVIEW-контекст, читает URL/title AO3),
> спайк **C пройден** (сидинг Room через `run-as`), спайк **B ПРОЙДЕН (2026-07-03)** —
> доказан полный цикл record→replay HTTPS WebView; блокером был не firewall, а доверие
> к CA в mount-namespace приложения на Android 14 (решено namespace-aware установкой CA
> + перезапуском фреймворка + правкой SELinux-контекста). Подробности и переиспользуемые
> скрипты — [environment-setup.md](environment-setup.md) §Спайк B, `scripts/`.

## Фаза 0 — Окружение и проверка гипотез (риск-спайки)

1. Android SDK + AVD API 34 (образ **без** Google Play — нужен root для CA mitmproxy).
2. Сборка debug-APK приложения из исходников без правок (`gradlew assembleDebug`);
   фиксация версии в `state/app-under-test.yaml`.
3. Appium 2 + uiautomator2 driver + Python-окружение.
4. **Спайк A:** виден ли контекст `WEBVIEW_com.example.ao3_wrapper` на debug-сборке
   (WebView remote debugging). Если нет — фиксируем fallback-стратегию: web-слой
   через accessibility tree.
5. **Спайк B:** mitmproxy replay страницы AO3 внутри WebView (системный CA на AVD).
6. **Спайк C:** сидинг данных — restore backup-JSON через UI и/или `run-as` push Room-БД.

**Выход:** «hello world» тест зелёный: приложение стартует, AO3 (replay) загрузился,
рейтинг выставлен, бейдж виден. Результаты спайков задокументированы в
`docs/02-framework-architecture.md`.

## Фаза 1 — Каркас фреймворка ✅ (2026-07-02)

Реализованы все слои из docs/02: config, core (driver/waits/adb/contexts/reporting/mitm),
screens (Browser, Library, Settings, navigation, rating overlay), web (listing, work
page, selectors), steps (app/rating/library/settings), data (works + сидинг Room),
conftest с фикстурами, Allure, `scripts/tasks.ps1`, авто-артефакты падений.

**Итог:** P0 smoke из **9 тестов** (запуск+AO3, навигация, 5× засеянная работа в своей
вкладке Library, clear-all, переключение тем) — **дважды подряд 9/9 зелёные**, ~3.5 мин
на AVD. Сидинг Room и WebView-контекст работают сквозь весь стек. См.
[framework/README.md](../framework/README.md).

**Полезные находки Фазы 1** (переданы в Фазу 2 / test-designer):
- Расхождение подписей вкладок Library: PROJECT.md обещает «Loved/Liked/Downloads»,
  фактически «Favorite/Kudosed/Files» — кандидат в баг документации.
- Cloudflare bot-check на старте — материал для сценариев риска R-03.
- Нижняя навигация скрыта за пилюлей на Browse; панель инструментов слева (PanelSide).

## Фаза 2 — Документация и тест-дизайн

test-strategist и test-designer (первые два агента) формируют:
стратегию (уже заложена в docs/01), тест-кейсы GWT по всем P0/P1-областям
(~60–80 кейсов: рейтинги, фильтрация видимости, табы, Library, downloads,
filter profiles, backup/restore, settings, error handling), traceability-матрицу.
Человек утверждает P0/P1-кейсы.

**Выход:** все P0/P1-области имеют Approved-кейсы; матрица показывает план покрытия.

## Фаза 3 — Автоматизация P0/P1

test-automator кодирует кейсы по конвенциям; canary-suite на live AO3; регрессия в
replay. Карантин-механизм для flaky (`@pytest.mark.quarantine` + отдельный отчёт).

**Выход:** P0 автоматизирован на 100%, P1 ≥ 80%; полный regression ≤ 40 минут на AVD.

## Фаза 4 — Агентная оркестрация

Порядок скорректирован (решение пользователя): агенты созданы РАНЬШЕ полного
тест-дизайна, чтобы конвейер работал уже сейчас.

- ✅ **Реализовано (2026-07-02):** все 9 агентов в `.claude/agents/`, оркестрация
  `state/rules.yaml` + журнал `state/orchestrator-log.md` + `state/traceability.md`,
  скиллы `.claude/skills/` (`/qa-loop`, `/run-suite`, `/triage`), каталоги артефактов
  `test-cases/`, `bugs/`, `runs/` с READMEs и статусными машинами.
- ⏳ **Осталось:** прогон полного цикла на искусственных сценариях — подложить
  намеренно сломанную запись (SITE_CHANGED-путь), «сломать» тест (TEST_BUG-путь),
  найти реальный баг (APP_BUG → bug-report → Fixed → fix-verifier). Первый живой вход
  уже есть: фоновая задача про расхождение вкладок Library для test-designer.

**Выход:** сквозной цикл из docs/03 §6 пройден без ручных подсказок агентам;
человек нужен только в точках из docs/03 §4.

## Фаза 4.5 — Тёмная фабрика (событийный контур) — спецификация: docs/06

Цель: разработчик пушит + двигает карточку на борде → фабрика всё делает сама;
человек приходит раз в день. Спецификация (события, матрица реакций D1–D12, SLA,
автономность) написана 2026-07-03: [06-dark-factory.md](06-dark-factory.md);
`state/rules.yaml` v2 и `state/sla.yaml` уже отражают её. Осталась реализация:

1. **build-watch** — скрипт: `git fetch` в `app-under-test/`, новые коммиты →
   `gradlew assembleDebug` → обновить `state/app-under-test.yaml` (+ coalescing D11).
2. **sla-sweep + stale-locks** — скрипт шага 0: просрочки из `state/sla.yaml` →
   `state/escalations.md` + метка `attention` в board_sync; снятие протухших локов
   (первый клиент — TC-021, лок висит с 2026-07-02).
3. **board-inbound** — обратный канал борды (whitelist переходов, комментарии ↔
   `## Обсуждение`, конфликт → Blocked); публикация борды на GitHub Pages, чтобы
   разработчик мог двигать карточки удалённо.
4. **Обновить агентов** под docs/06: fix-verifier (режимы recheck-rejected /
   still-repro), bug-reporter (role=responder, ведение `## Обсуждение`),
   failure-analyst (вердикт APP_CHANGED, сверка с git log приложения),
   qa-orchestrator (pre_steps, принцип «permission-окно = дефект» — деградировать
   и логировать, а не ждать).
5. **Расписание** — heartbeat `/qa-loop` каждые 2–4 часа + ночная регрессия +
   дневной canary (Task Scheduler / scheduled tasks CC); анти-наложение через
   `state/loop.lock`.
6. **Дайджест** — генерация дневной сводки; канал доставки наружу (push/почта) —
   решение владельца.

**Выход (репетиция тёмного дня):** искусственный суточный прогон без человека у
клавиатуры — подложить новую сборку с частичным фиксом, Rejected-баг, комментарий-
вопрос и сломанный тест; фабрика проходит все ветки матрицы D1–D12, ни одного
permission-окна, все зависшие позиции корректно всплыли в escalations/дайджесте.

## Фаза 5 — Эксплуатация

Ночная регрессия + дневной canary по расписанию; P2/P3-покрытие по остаточному
принципу; ежемесячная ревизия стратегии и flaky-карантина; обновление recordings
при изменениях AO3; еженедельный `/permission-audit` и чистка `settings.local.json`;
ревизия SLA-порогов по фактической скорости реакции разработчика.

## Открытые вопросы (решаются в Фазе 0)

| Вопрос | Влияет на | План |
|---|---|---|
| ~~Доступен ли WEBVIEW-контекст на debug-сборке~~ | ✅ спайк A: да, `chromedriverAutodownload` | — |
| ~~mitmproxy replay внутри WebView~~ | ✅ спайк B (2026-07-03): record→replay доказан | — |
| Проходит ли Cloudflare bot-check на эмуляторе с тестовой учёткой | Размер live-suite | Спайк на живом AO3; при жёстком боте live сводится к canary с ручной сессией |
| ~~`run-as` сидинг Room или только restore через UI~~ | ✅ спайк C: `run-as` работает | — |
| Куда зеркалить баги: только `bugs/` или ещё GitLab Issues | Воркфлоу bug-reporter | Решение владельца проекта; по умолчанию — файлы |
