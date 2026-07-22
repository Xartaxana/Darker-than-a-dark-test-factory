# HANDOFF — точка возобновления

Обновлено: 2026-07-22 (5), координатор Sonnet «/qa-loop 20 — F1 +
automate + red-probe ретрофит + needs-design закрытие». Проход: cap
переопределён на 20, использовано 10 (F1 TC-079; automate TC-096..099
— TC-099 потребовал attempt 2 после critic REJECT на пороге
memory-trend, исправлено settle-дисциплиной обоих замеров + порогом
0.15→0.08 на эмпирически падающем негативном контроле; F1-batch
TC-096..099 вслед за automate; **red-probe ретрофит ЗАКРЫТ
ПОЛНОСТЬЮ** — 28/28 кандидатов, 5 area-батчей; **needs-design
ЗАКРЫТА ЦЕЛИКОМ** — все 4 non-func области Этапа 4 теперь designed:
E2 perf, E4-min security P1 (TC-100..105), E1 a11y + E3 compat P2
(TC-106..111, объединённый диспатч во избежание file-коллизии)).
Rule 19 (charter) — не триггерит: settings-кластер BUG-012/013
предшествует CH-004, каденция 72ч не истекла. Каждый Sonnet-класс
результат (test-automator x2, test-designer x2) — РЕАЛЬНЫЙ
critic-вход (тир-матрица D-0058: для равного яруса queued-to-lead
недоступен, только critic); каждый Opus-класс — basis=queued-to-lead.
Sibling: AT-BUG-024 (второй AVD отсутствует, заведён test-designer
вопреки противоречивой инструкции координатора — ратифицировано);
TC-104 dual-assert independence, aapt-vs-dumpsys, TC-099
baseline_pss, TC-005 слабый assert — все в очередь, не блокеры.
Эмулятор/Appium погашены, NO DEVICE подтверждён канонически.
Коммиты: 24203ca (проход), ca32c15 (фикс mangled-path). Полный текст
— docs/09-history.md §«Шапка 2026-07-22 (5)».

Шапка (4) (Fable «Этап 5 мультипроектность»: runbook
docs/12-new-project-onboarding.md, security P1 заведён, anti-двойной-
зачёт nf-perf, 4 parity-теста, ратификация окна деградации (3),
boot-диета первый пробой) — VERBATIM в docs/09-history.md
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
не поглощать молча. Затем — preflight шаг 0 (сверка яруса).
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

1. **Проход /qa-loop — очередь артефакт-триггерная.** F1-долг ЗАКРЫТ,
   правило 15 (red_probe ретрофит) ЗАКРЫТО целиком (28/28),
   правило 16 (needs-design) ЗАКРЫТО целиком (все 4 non-func области
   Этапа 4 designed). Приоритет теперь: **B4 test debt AT-BUG-024**
   (второй AVD нижнего API отсутствует — блокирует автоматизацию
   TC-109; существенная инфра-задача, НЕ мелкий фикс — оценить
   реальный объём до диспатча, возможен отдельный фокус-проход, не
   попутный слот обычного /qa-loop); ЗАТЕМ обычная очередь
   автоматизации (Approved-кейсы TC-100..111 designed этой сессией,
   automated_by пуст — правило 14 подхватит). Чартеров Planned нет;
   АВТОЗАВЕДЕНИЕ сработает по каденции 72ч от 2026-07-21T18:40Z либо
   раньше по APP_CHANGED/кластеру (settings-кластер BUG-012/013 уже
   существовал ДО CH-004 — не новый, не событийный триггер сам по
   себе, но следующий НОВЫЙ баг той же зоны — событийный триггер).
2. **Порт-батч os-port-0722** (решения Lead 2026-07-22 по входящим
   OS, см. «Открытые хвосты»): builder-спека одним батчем — (а)
   порт escape_check + scripts/escape_allowlist.json с кросс-репо
   sha-пинами концессий CLAUDE.md на OS DECISIONS_FULL + новый
   .githooks/pre-commit; (б) scripts/wiring_check.py +
   SessionStart-хук в .claude/settings.json; (в) схема + чекер
   вердикта критика + правило в critic.md (frontmatter model не
   трогать — S2). Приёмка: critic обязателен (механизмы, схема
   данных); placement на live path и Rule-10 блоки в
   коммит-сообщениях — Lead-коммитом (паттерн D-0069 OS).
3. **Калибровка №4** — штатно ~2026-07-25. От сессии (5) добавить:
   тир-матрица D-0058 на практике — Sonnet-координатор НЕ может
   принять Sonnet-тир результат через queued-to-lead, только через
   реальный critic (4 отдельных критик-дозвона за проход, не 0);
   деривация зоны бага для кластерной ветки правила 19 (предшествующий
   кластер ≠ новый кластер — сверка по status_since vs executed_at
   последнего чартера); фантом-класс от собственной путаницы
   координатора (delegated до понимания path-коллизии) — закрыт
   штатным closes-phantom, но стоит отметить как пример «координатор
   тоже ошибается, механизм ловит».
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

- **РЕШЕНИЕ Lead 2026-07-22 по входящему N4/D-0082 (escape-allowlist)
  — ПЕРЕНЯТЬ адаптированно, кросс-репо форма** (разбор
  os-inbox-0722, scout-двухпроходка D-0066, приёмка в routing-log):
  пиннуем sha256 секций OS DECISIONS_FULL.md, обосновывающих
  концессии нашего CLAUDE.md (skip-льгота D-0058, батчинг D-0081,
  fail-open замер D-0083, льготы деградации D-0039/D-0042) — дрейф
  обоснований происходит в ЧУЖОМ git и нам не виден (прецедент: их
  repin D-0089 вскрылся на их же сидах). Чекер переносим (decision_file
  — поле entry, абсолютный путь легален). Требует нового
  .githooks/pre-commit — вводится вместе с wiring-чеком (ниже).
  Признанное отличие внутри решения: AO3-собственные концессии без
  внешнего носителя решения (reopen-семантика) НЕ пиннятся —
  named-not-covered до появления собственного файла решений; детектор
  утечки — первый живой инцидент дрейфа такой концессии.
  Реализация — порт-батч os-port-0722 (СЛЕДУЮЩИЙ ШАГ п.2).

- **РЕШЕНИЕ Lead 2026-07-22 по входящему D-0087 (judge-приёмка
  лист-класса) — ПРИЗНАННОЕ ОТЛИЧИЕ, не перенимать:** (а) лист-класс
  конвейера у нас уже принимается машинными гейтами фабрики (D1
  fix-verifier, F1 test-reviewer — функциональный аналог их
  «калиброванного судьи», причём с запретом ручного диспатча очереди);
  (б) не-конвейерный лист принимается через basis=critic — вход без
  Lead-чтения уже есть (двухслойный критик-вход); (в) предпосылок
  OS-механики нет: ни шлюза, ни JUDGE_SYSTEM_PROMPT, ни аналога их
  чека 30 калибровки, ни $/задачу-замера — без калибровочной сетки
  basis "judge" стал бы каналом самосертификации (класс F-22).
  BASIS_VALUES log_append.py НЕ расширять. Пересмотр — только с
  evidence дороговизны critic-входа на листах (еженедельная
  калибровка). Референс: OS docs/DECISIONS_FULL.md D-0087.

- **Батч мелочей (D-0081)** — пп.(1)–(5) прежнего списка ЗАКРЫТЫ
  2026-07-21 Fable-сессией «улучшение фабрики» двумя принятыми батчами
  (misc-batch-0721: a07b2fd/027681e/6e79586/ac620f3; misc-batch2-0721:
  5bbba9c/1dfc25d — оба critic PASS, witness в routing-log): parity-тесты
  rules.yaml↔enum↔роли↔model (двусторонние, scripts/tests/
  test_rules_agent_parity.py), дедуп `_iter_charters` (charter_utils.py),
  runbook `-Gpu host` в environment-setup (+точная атрибуция сигнатур
  021/016), комментарий схемы features. Судьба бывших (3) и (5):
  automated_by-аудит 9eb15e4 — В РАБОТЕ (automated-by-audit-0721,
  аудит + parity-тест automated_by→функция); решение по пустому
  `features` ПРИНЯТО оператором 2026-07-21 — НЕ допускать, вместо
  этого nf-записи реестра — В РАБОТЕ (nf-registry-0721). ЖИВОЙ
  остаток батча:
  (1) sibling-находка CH-004 (exploratory-tester, 2026-07-21T18:40:00Z):
  `driver.get()` на WebView этого приложения виснет неограниченно, если
  load-событие не срабатывает — воспроизведено И под live, И под replay
  одинаково (не Cloudflare-специфично), `driver.set_page_load_timeout`
  не реализован UiAutomator2-драйвером; любая `driver.get`-автоматизация
  должна оборачивать вызов в try + ручной поллинг readyState (приём,
  которым сама exploratory-сессия обошла зависание) — кандидат на
  test_debt-баг framework-уровня, не заведён этим проходом (решение за
  test-automator/Lead); (7) та же сессия: двухпальцевые жесты
  (brightness drag/font pinch) через Appium W3C actions не триггерят
  pointerInput classifier — механизмы настроек #4/#5 CH-004 остались
  непокрытыми ПО ЭТОЙ причине (не по недостатку времени), уже в
  `mission_leftover` CH-004, но сама причина (жест-классификатор) стоит
  зафиксировать здесь для следующего чартера/test-automator.
  (Нумерация (1)/(2) — бывшие (6)/(7) списка до свипа 2026-07-21.)
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

- ~~F-49 (финал-сообщение воркера теряет содержательную часть)~~ и
  ~~вопрос OS про прозаические закрытия фантомов~~ — оба ЗАКРЫТЫ
  (2026-07-21/07-20 полным Lead); полные вердикты — docs/09-history.md
  §«Закрытый хвост F-49 от OS-репо» и окрестности.
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
- ~~Порт D-0082~~, ~~калибровка №3 a/б/в~~, ~~журнал-тесты~~,
  ~~hygiene_gate v2~~ — все ЗАКРЫТЫ (07-19/07-20/07-21); полные
  нарративы — docs/09-history.md §«Закрытые хвосты 07-19».
- Некритичные замечания critic по AT-BUG-004 инкр.3 (при касании
  файлов): докстринг assert_rating_badge_visible; ListingPage.badge_for.
- TC-028: устаревшая заметка про эскалацию seed_db — почистит reviewer.
- TC-015.md: несущий факт «WebView живёт между табами» (MainActivity.kt:471,
  от которого зависит истинность «без reload») не процитирован явно в
  теле кейса — некритичная находка critic, дописать при следующей правке.
- Опционально (владелец): del C:\Windows\System32\drivers\aehd.sys.
- **РЕШЕНИЕ Lead 2026-07-22 по входящему t-257 (wiring-integrity чек)
  — ПЕРЕНЯТЬ адаптированно:** класс «хуки умирают молча» применим к
  нам буквально: core.hooksPath — ЛОКАЛЬНЫЙ git-конфиг (свежий клон =
  commit-msg/mechanism_gate мёртв молча), hygiene_gate.py в PreToolUse
  умирает молча при битом файле/python вне PATH. Адаптация:
  scripts/wiring_check.py (каналы: hooksPath→.githooks с ожидаемым
  набором {commit-msg, pre-commit-после-порта-escape}; hooks из
  .claude/settings.json по нашему паттерну `python scripts/*.py`;
  python в PATH) + регистрация SessionStart-хуком в settings.json —
  печать WIRING OK/WARNING на старте сессии, fail-open (никогда не
  ломает старт). Сейчас Session Start — дисциплина SKILL.md; код-гейт
  по D-0063 сильнее. Референс: OS tools/session_context.py (wiring) +
  tools/test_session_context_wiring.py. Реализация — os-port-0722.
- **РЕШЕНИЕ Lead 2026-07-22 по входящему t-259 (машиночитаемый вердикт
  критика) — ПЕРЕНЯТЬ адаптированно:** critic.md п.6 уже требует
  явный вердикт + след, но свободным текстом — basis=critic
  тир-матрицы опирается на вердикт, который ничто не проверяет
  механически. Порт: схема с маппингом на наши исходы
  (ПРИНЯТЬ/fit, ДОРАБОТАТЬ/fit_with_fixes, ОТКЛОНИТЬ/blocker; поля
  verdict/blockers/class_completeness/trail) +
  scripts/critic_verdict_check.py (последний fenced ```json,
  fail-closed: нет/бит блок = вердикт возвращается без приёмки) +
  правило в critic.md. Скоуп — только .claude/agents/critic.md
  (QA-агенты покрыты схемами agent-output, ось 6); frontmatter
  `model` critic.md НЕ трогать (FP-риск parity-теста S2, см. хвост
  выше). Референс: OS tools/critic_verdict.schema.json +
  tools/critic_verdict_check.py + правило 16 critic_staged.md.
  Реализация — os-port-0722.
