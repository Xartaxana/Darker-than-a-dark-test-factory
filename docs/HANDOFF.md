# HANDOFF — точка возобновления

Обновлено: 2026-07-23 (7), координатор Sonnet (degraded, весь проход —
самодетекция «Fable» на старте была ошибочной, ретроактивный
`lead_degraded`) «/qa-loop 20 — B4-цепочка AT-BUG-024..028 + полная
автоматизация E4-min/E1/E3 (TC-100..111) + F1». 12 триггеров из 20.
(1) AT-BUG-024 Fixed→Verified: п.1-2 (AVD api26) чисто, п.3 (smoke p0)
дал 2 краша qemu 0xc0000005 — critic-диагностика ESC-006 подтвердила
sibling AT-BUG-016-live (не регресс), нашла и поправила фактическую
ошибку витнесса fix-verifier'а (`0x6a1785af` — PE-timestamp бинарника,
не offset сбоя); заведён AT-BUG-026 на сам краш. (2) AT-BUG-025
(driver.get зависает в WebView без общего таймаут-хелпера) — Fixed за
2 попытки: attempt 1 REJECTED критиком (реальный блокер B1 — urllib3
`ReadTimeoutError` НЕ наследует builtin `TimeoutError`, misread автора),
attempt 2 закрыл ветку правильно + новый device-free тест на саму
ветку таймаута; Verified тем же проходом. (3) AT-BUG-026 (qemu-краш
под тяжёлым live-рендером) — 2 ремедиации (GPU `host`-параметризация,
демоушен TC-082 p0→p1) не дали DoD; critic поймал ложную находку
воркера «краш подтверждён и на replay» (упавший тест рухнул в
fixture-setup ДО рендера — witness'а на replay нет). Open, эскалирован:
диагностика (replay-изолированный краш-цикл) и архитектура (пересмотр
DoD «p0 без единого краха×3» для вероятностной хрупкости) — в очередь,
не решено этим циклом. (4) AT-BUG-027 (sibling driver.get вне
framework/steps/) и (5) AT-BUG-028 (AVD api26 несёт EOL WebView Chrome
69 — legacy chromedriver эмпирически отвергнут, `status.ready`
структурно недостижим для этой пары; AVD переведён api26→api29) — оба
Fixed, оба приняты с критик-входом. (6) Rule 14+F1: 12 Approved-кейсов
(security P1 TC-100-105 через новый `aapt dump xmltree`-парсер +
accessibility/compatibility TC-106-111, включая разблокированный
TC-109) автоматизированы и прошли полный F1 (не ретрофит) — все
Automated. Класс-находки в очередь: schema `automated_by` не тянет 2
теста на один TC-id (TC-104); side-panel scrim прячет весь a11y-tree
(HANDOFF «Открытые хвосты», R-13 триаж). Каждый Sonnet-класс результат
(fix-verifier×2, test-maintainer×4, test-automator×2) — РЕАЛЬНЫЙ
critic-вход (basis=critic, self-accept недоступен в degraded-режиме);
Opus-класс (critic-диагностика, test-reviewer×3 батча) —
basis=queued-to-lead. Эмулятор/Appium погашены, NO DEVICE подтверждён
канонически. Коммит: 7f292a0 (push d33855e..7f292a0).

Шапка (6) (Fable: входящие OS + порты механизмов + AT-BUG-024 + аппрув
TC-100..111 + батч мелочей) — VERBATIM в docs/09-history.md §«Шапка
2026-07-22 (6)»; шапка (5) — §«Шапка 2026-07-22 (5)»; шапка (4) —
§«Шапка 2026-07-21 (4)», как и все предыдущие.

Предыдущие шапки дня — VERBATIM в docs/09-history.md §«HANDOFF-свип
2026-07-21»: (3) Sonnet «/qa-loop 10» (D1 AT-BUG-022/023 Verified, E2
TC-096..099, F1 batch 6, CH-004 Done); (2) Fable «CH-004 +
автозаведение чартеров»; (1) «/qa-loop 10 Sonnet → подъём Fable» —
класс «деливерабл-дрейф» AT-BUG-022, пост-коммит сверка деливераблов
в чек-листе /qa-loop.
Читать первым при старте. Итоги прошлых сессий — git-история и
docs/09-history.md.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short`,
`git log origin/master..master --oneline` и
`python scripts/log_append.py open-dispatches` (D-0076: показанные
открытые delegated сверить — воркер жив / результат ждёт / фантом;
фантом закрывается токеном `closes-phantom:<task_id>` в notes
следующего события — проза сканером не читается). Грязное дерево или
неотправленные коммиты = прошлая сессия закрылась без
handoff-проверки — зафиксировать находкой в журнале (`log_append`),
не поглощать молча. С 2026-07-22 SessionStart-хук печатает строку
`WIRING: OK`/`WIRING WARNING` (scripts/wiring_check.py, os-port-0722)
— отсутствие строки на буте или WARNING = находка, разобрать до
Lead-действий (класс «хуки умирают молча»). Затем — preflight шаг 0 (сверка яруса).
**Сверка яруса (D-0058/D-0042):** деградации НЕТ — окно 14:51:04
сессии (3) закрыто `lead_restored` 2026-07-21T17:12:05 с приёмкой
окна (D-0044, 7 queued-to-lead ратифицированы без замечаний). Новая
сессия сверяет свой ярус штатно (п.4а протокола CLAUDE.md).
**Бут-перечень чтения:** этот файл → `docs/09-improvement-plan.md`
(единый план развития, компактный `[X]`/`[ ]`-срез статусов; нарративы —
docs/09-history.md, НЕ бут).

Здесь ТОЛЬКО resume-заметки и критичный контекст (G1). Остальное:

| Что | Где |
|---|---|
| Очередь, счётчики, локи, эскалации | `state/factory-status.md` — **генерируется** `scripts/queue_snapshot.py`; ручные числа запрещены (A4) |
| Карта покрытия фич → кейсы | `state/coverage-map.md` — **генерируется** `scripts/coverage_map.py` |
| План развития (ЕДИНЫЙ: фазы + этапы, [X]/[ ]-статусы) | [09-improvement-plan.md](09-improvement-plan.md) — бут; нарративы в [09-history.md](09-history.md) |
| Спека репетиции тёмного дня | [11-dark-day-rehearsal.md](11-dark-day-rehearsal.md) (согласована критиком, решения владельца §6) |
| Спецификация фабрики (события, D1–D14, SLA) | [06-dark-factory.md](06-dark-factory.md) |
| Runtime-модель оркестрации | [03-agent-system.md](03-agent-system.md) §1 |
| История сессий | git log + docs/09-history.md |

«Где мы (2026-07-20 (2), борда и механизмы)» — сметено в
docs/09-history.md (boot-budget sweep 2026-07-21).

## Где мы — архив

Сметено целиком в docs/09-history.md §«HANDOFF-свип 2026-07-21»
(boot-диета; краткие сводки сессий 07-17..07-20 дублировали полные
нарративы history — указатель вместо дублей).

## СЛЕДУЮЩИЙ ШАГ

1. **Проход /qa-loop — очередь артефакт-триггерная.** AT-BUG-024
   ЗАКРЫТ (Fixed, шапка (6) п.3). Живые цели: (а) **правило 14 —
   автоматизация 12 Approved-кейсов TC-100..111** (заметки
   автоматизации несут aapt-инструмент, независимость
   static/behavioral TC-104, форвард-флаг doctor-api26 для TC-109;
   TC-109 — на ao3_test_api26 через `Start-Emulator -WritableSystem
   -AvdName ao3_test_api26`, его зелёный прогон даст D1-верификацию
   AT-BUG-024 Fixed→Verified); (б) **B4 — AT-BUG-025** (driver.get
   класс: общий navigate-хелпер, критерий Fixed в баге). Чартеров
   Planned нет; автозаведение — каденция 72ч от 2026-07-21T18:40Z
   (≈2026-07-24 19:40) либо раньше по APP_CHANGED/новому кластеру
   зоны (settings-кластер BUG-012/013 — старый, сам по себе не
   триггер; следующий НОВЫЙ баг той же зоны — событийный триггер).
2. ~~Порт-батч os-port-0722~~ — ИСПОЛНЕН 2026-07-22 (шапка (6) п.2;
   DAG docs/tasks/2026-07-22_os-port-0722.md, витнессы в routing-log).
3. **Калибровка №4** — штатно ~2026-07-25. От сессии (5) добавить:
   тир-матрица D-0058 на практике — Sonnet-координатор НЕ может
   принять Sonnet-тир результат через queued-to-lead, только через
   реальный critic (4 отдельных критик-дозвона за проход, не 0);
   деривация зоны бага для кластерной ветки правила 19 (предшествующий
   кластер ≠ новый кластер — сверка по status_since vs executed_at
   последнего чартера); фантом-класс от собственной путаницы
   координатора (delegated до понимания path-коллизии) — закрыт
   штатным closes-phantom, но стоит отметить как пример «координатор
   тоже ошибается, механизм ловит». От сессии 2026-07-22 (os-port):
   **детектор утечки правила 16 critic.md** — выборочная сверка
   accepted-событий с basis=critic (или agent=critic) периода: в
   транскрипте критика есть fenced json-вердикт И координатор прогнал
   scripts/critic_verdict_check.py до приёмки (упоминание в notes);
   плюс контроль строки WIRING в бутах сессий периода (детектор
   wiring_check самого себя).
4. **Подготовка репетиции (docs/11)** — без изменений; включение
   heartbeat-задачи — слово владельца.

**Решение человека в очереди:** блокирующих НЕТ. Опциональные:
включение heartbeat/дата репетиции (п.3), BUG-013 — передать
разработчику или принять WontFix (окно <100мс, minor; верификация
любого исхода — только со свежим сырым witness prefs-ридов),
GitLab-токен (Этап 4 п.8), Get-Date в allowlist (висит с
калибровки №2).

## Как поднять окружение (в новом окне)

```powershell
. D:\AO3_tests\scripts\env.ps1     # JAVA_HOME/ANDROID_HOME/PATH
. D:\AO3_tests\scripts\tasks.ps1   # Start-Emulator, Start-Appium, Install-App, Get-Device...
. D:\AO3_tests\scripts\board.ps1   # Show-Board (живая доска)
```

Эмулятор `ao3_test_api34` (API 34, WHPX). Replay:
`Start-Emulator -WritableSystem` — CA ставится автоматически (признак:
«CA visible in apex store: OK»); затем `Install-App` → mitmdump → прокси
`10.0.2.2:8080`. **CA стирается ЛЮБЫМ ребутом** — runbook:
`ReadTimeoutError` на replay-навигации → первым кандидатом CA
(AT-BUG-011 — код-гейт в фикстуре `replay`, Verified). Ловушка: битый
quickboot-снапшот (AT-BUG-012, Verified) — фолбэк на `-no-snapshot-load`
уже в `Start-Emulator`. **Новое (AT-BUG-017, Fixed):** первая навигация
после `set_device_proxy`+`start_replay` может словить интермиттентный
`net::ERR_PROXY_CONNECTION_FAILED` (NAT-race qemu) — закрыто device-side
reachability guard в `mitm.wait_device_proxy_reachable`, тест не должен
больше это видеть; если увидишь — не known-issue, а регресс, диагностика
в bugs/AT-BUG-017.md.

## Критичные факты (беречь токены)

- **Истина = код приложения.** PROJECT.md устарел (BUG-001; решение
  владельца 07-17: эталон = фактический UI/код). CLAUDE.md точнее.
- **Локаторы**: код (место рендера!) → живое дерево
  (`python scripts/ui_snapshot.py`) → скриншот. Ловушки Compose:
  `tab.label.uppercase()`, `AnimatedVisibility`, клик на родителе,
  `UiScrollable` не видит Compose-скролл. DocumentsUI — классические View.
- **Порядок фикстур критичен**: сидинг строго ДО Appium-сессии;
  фикстуры — framework/tests/conftest.py.
- **Teardown-класс:** весь device-setup + yield в одном try, finally
  чистит идемпотентно. Critic проверяет всегда.
- **Долгие прогоны (канон 07-17, ИСПРАВЛЕН 07-19):** >~9 мин не влезает
  в foreground Bash (600 с) — субагент запускает через run_in_background,
  но ждёт PYTEST_EXIT В ПРЕДЕЛАХ ХОДА (Get-CimInstance → Wait-Process
  -Timeout 500 повторно); «ход БЕЗ отчёта → нотификация» УДАЛЁН из
  промптов как эмпирически ложный для субагентов (13 инцидентов
  07-18/19). Длинные device-диспатчи — Agent run_in_background:true
  (SKILL шаг 2) — это уровень КООРДИНАТОРА, там нотификация работает.
- **Журнал**: accepted/rejected только с `--by` (матрица ярусов в
  log_append.py); delegated — только после фактического запуска, с
  worker_ref (D-0076).
- **Обязательные поля кейса:** `features` (id из реестра, пусто = ERROR);
  `red_probe` ставит только test-reviewer.
- **Рейтинг-бейдж на листинге** = background-color `[data-ao3-rate-btn]`;
  `[data-ao3-badge]` МЁРТВ.
- **`savePanelRating`**: синтетический `ao3_id` → 404 → пустые поля;
  обход — `placeholder_seeded_work`.
- **Env-негатив ≠ отсутствие объекта** (CLAUDE.md п.6): устройство —
  только `Get-Device`; несущие утверждения о среде — после измерения
  (F-30); пустой grep — только с позитивным контролем формы (F-34).
- **Эмулятор + GPU-инференс не совмещать**; гасить при ПУСТОЙ
  эмуляторной очереди — сделано на закрытии этой сессии (`NO DEVICE`
  подтверждено канонически), новая сессия поднимает с нуля.
- Cloudflare bot-check (R-03) — главный риск canary-baseline (и теперь
  live-половины canary-кейсов TC-066/068/070/072/074/076/078/080/082).
- `.ps1` с кириллицей — только UTF-8 BOM.
- **Subagent-фон — ПОЧИНЕНО 2026-07-19 полным Lead:** ложный канон
  «запусти фоновый pytest и заверши ход, разбудит нотификация» удалён
  из всех 5 промптов device-агентов (fix-verifier/test-maintainer/
  test-automator/test-reviewer/test-runner) + строки SKILL.md qa-loop —
  заменён на «запусти run_in_background, но дождись PYTEST_EXIT в
  пределах хода (Get-CimInstance → Wait-Process -Timeout 500 повторно)».
  Детектор рецидива: координатор qa-loop (нотификация агента с
  нерезультатом «жду фоновый» → SendMessage-резюме + строка
  orchestrator-log) + чек калибровки OS-репо по транскриптам.
- **Тяжёлый live-рендер AO3 в эмуляторном WebView** — известный класс
  нестабильности (AT-BUG-016 Fixed для TC-040 через self-contained
  mitm-flow; AT-BUG-021 — новый кандидат-сиблинг, ИНОЙ путь/сигнатура,
  не диагностирован). Любая фикстура/степ, форвардящая тяжёлый live-AO3
  контент (`server_replay_extra=forward`, `mitm.py:129`) или
  напрямую навигирующая на тяжёлую live-страницу (`open_live_listing`)
  — кандидат в тот же класс при касании.

## Открытые хвосты (вне текущей очереди)

- **A11y-находка (test-automator, a11y-compat batch, 2026-07-22):**
  раскрытие side panel (BrowseSidePanel, собственный fullscreen-scrim)
  убирает WebView/TabStrip/BottomBar/RatingMenu ЦЕЛИКОМ из
  accessibility tree (UiAutomator2) — тот же класс, что уже
  задокументированная находка `top_chrome_avg_luma` (fullscreen-toggle
  reflow), теперь воспроизведена ещё и через поворот экрана (device
  rotation), держится ≥10с, не самовосстанавливается по тапу.
  Кандидат в R-13 (accessibility) триаж — решение test-strategist/
  test-designer при следующем касании области, не заведено как баг
  (неопределённость: намеренный UX-дизайн scrim vs дефект). Не
  расширяет scope TC-106/111 (обойдено операционализацией: TC-106 —
  последовательная инспекция, TC-111 — WebView-rect прокси вместо
  взаимодействия с side panel).

- **ВХОДЯЩЕЕ ОТ OS 2026-07-22 №2 (гейт-батч t-278, критик F1, ось 1
  карты OS):** ваш `scripts/mechanism_gate.py` (порт 0a0a8c6 от
  07-12) вероятно несёт исходный дефект `find_tier_declaration` —
  `.search()` матчит только ПЕРВУЮ `tier:`-строку сообщения (критик
  t-068: цитированная строка маскирует настоящую). Штабной фикс
  07-22: `find_tier_declarations` (plural, `.findall()`), отказ если
  ХОТЬ ОДНА найденная строка ниже планки (fail-closed на цитатах —
  осознанный трейдофф, формулировку гарантии штабной критик просил
  не переоценивать). Решение перенять/признать отличие — за вашим
  Lead по процедуре входящих (прецедент os-inbox-0722);
  первоисточник: Operating-System-for-LLMs/tools/mechanism_gate.py +
  тест «две tier-строки».

- **Решения Lead 2026-07-22 по 4 входящим OS — ВСЕ РАЗОБРАНЫ**
  (os-inbox-0722): escape-allowlist ПРИНЯТ, judge-приёмка (D-0087) —
  ПРИЗНАННОЕ ОТЛИЧИЕ (**BASIS_VALUES log_append.py НЕ расширять**),
  wiring-чек и вердикт критика ПРИНЯТЫ и реализованы (os-port-0722).
  Полный текст — docs/09-history.md §«Решения Lead по входящим OS
  2026-07-22».

- **Батч мелочей (D-0081)** — largely закрыт; automated_by-аудит и
  nf-registry — В РАБОТЕ (automated-by-audit-0721, nf-registry-0721).
  ЖИВОЙ остаток: двухпальцевые жесты (brightness drag/font pinch) через
  Appium W3C actions не триггерят pointerInput classifier — механизмы
  настроек #4/#5 CH-004 непокрыты по этой причине (не по недостатку
  времени), уже в `mission_leftover` CH-004, причина зафиксирована
  здесь для следующего чартера/test-automator.
- **Швы automated_by-семейства — named-not-covered (решение Lead
  2026-07-21, правило 10г):** названы critic'ом при приёмке
  automated-by-audit-0721; shadowing уже закрыт кодом (5b3fc0e),
  осознанно НЕ заводятся: collectability (текстовый `def` ≠ реально
  собирается pytest'ом — тот же корень, что низкий false-OK на def в
  докстринге), automated_by↔allure.id-связка, red_probe-поле↔
  существование пробы. Детектор утечки: первый живой инцидент любого
  из них (триаж/приёмка) = прецедент заведения кода; превентивно не
  заводить.
- Знание при правках `.claude/agents/critic.md`: parity-тест S2 читает
  frontmatter `model` ВСЕХ dispatch-агентов, включая critic, тогда как
  гейт log_append резолвит scout/builder/critic статикой — дрейф
  `model` в critic.md уронит S2 при корректном гейте (fail-safe
  FP-риск; вердикт critic misc-batch2-0721).
- Прозаический status-лаг §9 designed-областей docs/01 (проза
  «Review», факт Automated) — свип при следующем ревью §9 (находка
  strategist nf-registry-0721; не load-bearing для needs-design
  триггера).
- **CH-004 Done (2026-07-21T18:40:00Z, /qa-loop 10 Sonnet):** 5 находок
  все `ok` (флагманская гипотеза «theme-reload теряет scroll» НЕ
  подтвердилась — scrollY/dim-состояние переживают reload), 0
  продуктовых багов. `mission_leftover` — 8 пунктов (live seed-1
  rating-panel + AT-BUG-021 host soak, механизмы #4/#5, остаток #1
  под-настроек, seeds 3/4/5, лимит 10 вкладок) — вход для следующего
  charter-designer прохода по каденции.
- **Первый цикл автозаведения** — CH-004 теперь Done (executed_at
  2026-07-21T18:40:00Z); правило «Завести следующий exploratory-чартер»
  сработает через 72ч от этой отметки (либо раньше по APP_CHANGED/
  кластеру ≥2 багов одной зоны — этот проход не дал ни одного). Первый
  живой Proposed-чартер прогнать через гейт
  внимательно — обкатка критик-режима charter-plan-review.

- **Порт D-0083 — исполнен по слову оператора «портируй в АО3»**
  (заголовок пункта восстановлен 07-20 — был повреждён слиянием с
  соседним при прошлой правке): правило 4в CLAUDE.md +
  scripts/tier_measure.py (порт замера) + log_append stderr-warn
  MISMATCH при записи ярусных событий с worker_ref async:/agent:
  (строго ПОСЛЕ записи, fail-open, не блокирует; критик-вход Opus,
  451 passed каноном). Вашим сессиям: warn виден в результате
  Bash-вызова log_append — разбирайте MISMATCH до использования
  результата как слова яруса. Текст: OS docs/DECISIONS_FULL.md
  D-0083. **Первое живое срабатывание — 2026-07-20 (`/qa-loop 20+10`):**
  MISMATCH пойман на собственной ошибке координатора (bug-reporter
  задекларирован `sonnet`, замер дал `haiku`) — разобран честной
  записью в следующем `accepted` (не эскалирован: Haiku ниже Sonnet,
  accept легален по матрице). Механизм подтверждён рабочим на первом
  же реальном случае.
- Мелкие точечные заметки «при касании файла» (некритичные, не
  load-bearing): AT-BUG-004 инкр.3 докстринги (assert_rating_badge_visible,
  ListingPage.badge_for); TC-028 устаревшая заметка про эскалацию
  seed_db; TC-015.md — факт «WebView живёт между табами»
  (MainActivity.kt:471) не процитирован в теле кейса. Опционально
  (владелец): del C:\Windows\System32\drivers\aehd.sys.
- Оперативные следствия входящих OS (t-257/t-259, см. пункт выше):
  строка WIRING на буте (её отсутствие = находка); вердикт критика без
  валидного fenced-json не принимается (scripts/critic_verdict_check.py
  до приёмки, правило 16 critic.md).
