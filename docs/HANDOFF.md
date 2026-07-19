# HANDOFF — точка возобновления

Обновлено: 2026-07-19 (4), сессия «/qa-loop 10» (Sonnet-координатор
→ Fable-хвост). (1) Проход /qa-loop 10: D1 — AT-BUG-016/018
Verified; B4 — AT-BUG-019 Fixed (weak locator `_find_pill`),
AT-BUG-020 Fixed (дубликат 019), AT-BUG-021 Fixed (soak host 0/15,
config-mitigation); needs-design switchTab → TC-084, заблокирован
новым AT-BUG-022 (chromedriver sticky-к-вкладке-0); чартеры CH-002
(находка → BUG-013, гонка персиста theme_mode) и CH-003 (чисто, швы
держатся) исполнены. Все Sonnet-приёмки — через critic-вход
(D-0058). (2) Fable-хвост: окно деградации закрыто с приёмкой,
очередь Lead разобрана — enum agent-output
(+exploratory-tester/test-reviewer, c7c155a), GPU-решение (дефолт не
меняем, host вписан в заметки TC-078/080/082), scroll-restore закрыт
в §9, hygiene_gate v2 остаётся хвостом. Читать первым при старте.
Итоги прошлых сессий — git-история и docs/09-history.md.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short`,
`git log origin/master..master --oneline` и
`python scripts/log_append.py open-dispatches` (D-0076: показанные
открытые delegated сверить — воркер жив / результат ждёт / фантом;
фантом — пометкой в notes следующего события). Грязное дерево или
неотправленные коммиты = прошлая сессия закрылась без
handoff-проверки — зафиксировать находкой в журнале (`log_append`),
не поглощать молча. Затем — preflight шаг 0 (сверка яруса).
**Сверка яруса (D-0058/D-0042):** окно деградации 2026-07-19T13:20:20
(старт сессии на Sonnet) ЗАКРЫТО `lead_restored` 2026-07-19T15:52:33
(оператор поднял модель на Fable той же сессией; приёмка окна D-0044
выполнена — чистое, все приёмки шли с critic-входом). Последнее
событие журнала окна не открывает — новая сессия сверяет ярус штатно
по своей фактической модели (правило 4а), унаследованных ограничений
нет.
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

## Где мы (2026-07-19 (4), «/qa-loop 10» Sonnet + Fable-хвост)

Дерево чистое, запушено, журнал закрыт (`open-dispatches` пуст,
последнее событие — `lead_restored`), эмулятор и Appium погашены
(`Get-Device` → NO DEVICE). Сделано этой сессией:

1. **Проход /qa-loop 10** (координатор Sonnet, все приёмки с
   critic-входом): D1 — AT-BUG-016 (qemu-краш TC-040) и AT-BUG-018
   (long-press TC-026) Verified; B4 — AT-BUG-019 Fixed
   (`_find_pill`: исключение a11y-потомков WebView по цепочке
   предков), AT-BUG-020 Fixed (дубликат 019 — контролируемый A/B
   доказал тот же корень), AT-BUG-021 Fixed как config-mitigation
   (soak 11 прогонов/15 live-вызовов под `AO3_EMU_GPU=host`, 0
   крашей; НЕ статистическая гарантия класса — честная оговорка в
   баге); needs-design switchTab → TC-084 (Review), заблокирован
   новым **AT-BUG-022** (chromedriver прилипает к вкладке-0 —
   наблюдаемость активной вкладки не решена, гипотеза
   scrollY-асимметрии ждёт B4); чартеры: **CH-002** → находка
   **BUG-013** (гонка персиста `theme_mode`, окно <100мс, minor,
   awaiting dev; верификация/WontFix — только со свежим сырым
   witness prefs-ридов), **CH-003** (пользовательские пути) — чисто,
   швы держатся, test-gap слинкован с TC-084. Ретраи по критик-veto:
   TC-084 attempt 2, BUG-013 attempt 2 — оба приняты после доработки.
2. **Fable-хвост:** окно деградации 13:20..15:52 закрыто с приёмкой
   (чистое); очередь Lead разобрана (детали — commit c7c155a +
   журнал): enum agent-output +exploratory-tester/test-reviewer
   (enforcement починился той же правкой, тест на границе, 429
   passed); GPU-дефолт НЕ меняется, host-конфиг вписан в заметки
   TC-078/080/082 (носитель исполнителя — иначе следующий live-прогон
   пошёл бы под swiftshader); scroll-restore switchTab закрыт в §9;
   hygiene_gate v2 — остаётся хвостом.

## Где мы — архив (2026-07-19 (3) «калибровка №3 + очередь Lead +
чартеры», 2026-07-19 «`/qa-loop 15`+Fable-хвост», 2026-07-18
«`/qa-loop 30`», 2026-07-17 вечер «механизмы+планы», 2026-07-17/18
ночь «Sonnet→Fable марафон»)

Полные нарративы — `docs/09-history.md`. Коротко 2026-07-19 (3):
калибровка №3 (F-48→D-0082, кодификация каузального негатива),
очередь Lead пп.1-4 (GPU-диагностика host, hygiene_gate v1, батч
мелочей, switchTab needs-design), чартеры CH-002/003 заведены,
механизм параллельности qa-loop. Коротко 2026-07-19
(/qa-loop 15 + Fable-хвост): AT-BUG-015/017 Verified, AT-BUG-016
Fixed (3 захода, +сиблинг AT-BUG-019), AT-BUG-018 закрыт найденным
механизмом (TC-026 автоматизирован), canary A+B 12 P0 Automated
(+AT-BUG-020 регрессия TC-009), batch C → AT-BUG-021, BUG-012 =
APP_BUG/low, канон фоновых прогонов исправлен во всех 5 промптах.
Коротко 2026-07-18: AT-BUG-015
Fixed (первый заход), 44 кейса Approved→Automated за 9 батчей (browser/
downloads/errors/filter-profiles/library/rating/settings/tabs/visibility),
canary R-02 design (18 кейсов, needs-design снята) вне очереди по слову
оператора, автоматизация явно отложена — **эта сессия её забрала**.
Коротко раньше: 15/15 AT-BUG-005..014 Verified; TC-042/TC-057 Automated;
bring-up-класс закрыт; permission-audit + канон долгих прогонов;
heartbeat/loop_lock built (выключен).

## СЛЕДУЮЩИЙ ШАГ

1. **Проход /qa-loop — очередь артефакт-триггерная:** D1
   (fix-verifier по Fixed test_debt AT-BUG-019/020/021 — сборку не
   ждут; для 021 live-прогоны ТОЛЬКО под `AO3_EMU_GPU=host`, см.
   заметки TC-078); F1 (test-reviewer: TC-026, TC-040, TC-078/080/082
   — все Approved + automated_by без review); B4 — AT-BUG-022
   (наблюдаемость активной вкладки: проверить гипотезу
   scrollY-асимметрии на эмуляторе, 2+ вкладки, цель ≠ 0); правило 15
   (red_probe retrofit остатка, ~28 кандидатов — не тронуто два
   прохода); правило 16 (needs-design: switchTab снова стоит — НО
   B4-правило выше, AT-BUG-022 возьмётся раньше ре-дизайна; старые
   E1/E2/E3/security). Чартеров Planned нет; кандидат нового —
   остаток CH-003 (seed 1 rating-на-длинной-странице, seed 4
   backup/restore, seed 5 фильтр+deep-link, deep-link на лимите 10
   вкладок) — заведение за Lead/человеком.
2. **Калибровка №4** — штатно ~2026-07-25. Материал: false-accept
   test-automator 2/8, первый живой FP hygiene_gate, экономика
   плотных дней, 2 rejected-цикла этого прохода (TC-084, BUG-013 —
   оба spec-класс, пойманы критиком), атрибуции exploratory-tester
   до enum-фикса (CH-001..003 писали ложные имена — не переписывать,
   учесть при чтении журналов).
3. **Подготовка репетиции (docs/11)** — без изменений; включение
   heartbeat-задачи — слово владельца.

**Решение человека в очереди:** блокирующих НЕТ. Опциональные:
включение heartbeat/дата репетиции (п.3), BUG-013 — передать
разработчику или принять WontFix (окно <100мс, minor; верификация
любого исхода — только со свежим сырым witness prefs-ридов),
GitLab-токен (Этап 4 п.8), Get-Date в allowlist (висит с
калибровки №2).

**Очередь Lead от `/qa-loop 10` — разобрана полным Lead той же
сессией** (все 4 пункта: enum agent-output закрыт, GPU-решение
принято, scroll-restore закрыт, hygiene_gate v2 остаётся хвостом) —
резюме в «Где мы» п.2, детали — commit c7c155a + routing-журнал.

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

- **Вопрос от OS-репо (2026-07-20, находка сверки правил трёх
  носителей):** читает ли ваш `log_append.py open-dispatches`
  закрытия фантомов, записанные ПРОЗОЙ в notes («фантом — пометкой
  в notes следующего события», ваш Session Start)? У OS ровно этот
  класс дал 13 ложных «висяков» на буте — вылечен машиночитаемым
  closes:-токеном (их журнал). Если ваш сканер прозу не парсит —
  тот же дефект-класс жив у вас; решение о вашей форме токена — ваш
  Lead. Контекст: OS session_context.py (их фикс 07-19).
  оператора «портируй в АО3»**: правило 4в CLAUDE.md +
  scripts/tier_measure.py (порт замера) + log_append stderr-warn
  MISMATCH при записи ярусных событий с worker_ref async:/agent:
  (строго ПОСЛЕ записи, fail-open, не блокирует; критик-вход Opus,
  451 passed каноном). Вашим сессиям: warn виден в результате
  Bash-вызова log_append — разбирайте MISMATCH до использования
  результата как слова яруса. Текст: OS docs/DECISIONS_FULL.md
  D-0083.
- ~~Порт D-0082~~ — **ИСПОЛНЕН 2026-07-19 тем же днём** (правило 4б
  CLAUDE.md + чек 3 session-handoff, коммит 2873db0; полный текст —
  OS docs/DECISIONS_FULL.md D-0082).
- **Восстановлено калибровкой №3 (2026-07-19; класс F-48 OS-репо —
  кросс-деплойные очередь-пункты, жившие только в notes OS-журнала,
  испарялись):** (а) ~~hygiene_gate-адаптация~~ — ЗАКРЫТА 07-19:
  v1 warn-хук scripts/hygiene_gate.py (оба журнала + PowerShell-формы
  записи, без permissionDecision, fail-open) + PreToolUse в
  settings.json, critic ПРИНЯТЬ, живой e2e; v2-кандидат — см. хвост
  ниже;
  (б) ~~кодификация 4 старых AO3 defect_found~~ — ЗАКРЫТА 07-19:
  at-bug-010 → critic.md пр.7 (validate_frontmatter в механическом
  слое артефакт-диффов), at-bug-014 → critic.md пр.12 (runtime-ветки
  только прогоном), part4-фантом покрыт «истина=код»+D-0046,
  AT-BUG-016/017-классы покрыты фиксами и правилом 14;
  (в) ~~at-bug-014-разбор~~ — ЗАКРЫТ 07-19: рецидив был при живом
  правиле 12 (порт 3f4014b 07-16 < дефект 07-17), но формулировка
  покрывала семантику данных, не runtime процессов — дыра
  формулировки, не утечка дисциплины; закрыта расширением пр.12.
- ~~Журнал: 2 недостающих теста log_append, кириллические
  SystemExit~~ — ЗАКРЫТО 07-19 батчем мелочей (misc-batch-scripts-0719:
  оба теста written, mojibake-корень — reconfigure после parse_args —
  устранён; заодно errors=replace в 12 скриптах класса и doctor-баг
  «rc!=0 = полный клон»).
- hygiene_gate v2 (остаточный риск critic, не блокер): подстрочная
  детекция «канонического вызова» гасится упоминанием log_append.py в
  любом месте команды (комментарий-обход) — ужесточить до
  формы-префикса при касании; для WARN-режима v1 приемлемо. Обратная
  сторона той же грубости — первый живой FALSE-POSITIVE (07-19, этой
  же сессией): git commit, чьё СООБЩЕНИЕ упоминает «orchestrator-log»
  и содержит `>` в тексте, словил warn — v2 должен исключать
  commit-message-контекст.
- Некритичные замечания critic по AT-BUG-004 инкр.3 (при касании
  файлов): докстринг assert_rating_badge_visible; ListingPage.badge_for.
- TC-028: устаревшая заметка про эскалацию seed_db — почистит reviewer.
- TC-015.md: несущий факт «WebView живёт между табами» (MainActivity.kt:471,
  от которого зависит истинность «без reload») не процитирован явно в
  теле кейса — некритичная находка critic, дописать при следующей правке.
- Опционально (владелец): del C:\Windows\System32\drivers\aehd.sys.
