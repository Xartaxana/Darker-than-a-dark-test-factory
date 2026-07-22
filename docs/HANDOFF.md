# HANDOFF — точка возобновления

Обновлено: 2026-07-22 (6), Lead Fable «входящие OS + порты механизмов
+ AT-BUG-024 + аппрув TC-100..111 + батч мелочей». Сессия: (1) разбор
4 входящих OS (двухпроходка D-0066, 2 scout) — решения Lead: N4
escape-allowlist ПРИНЯТ (кросс-репо sha-пины концессий CLAUDE.md на
OS DECISIONS_FULL), t-257 wiring-чек ПРИНЯТ, t-259 машиночитаемый
вердикт критика ПРИНЯТ, D-0087 judge-приёмка — ПРИЗНАННОЕ ОТЛИЧИЕ
(гейты фабрики + basis=critic уже покрывают лист-класс; BASIS_VALUES
не расширять); полные тексты решений — «Открытые хвосты». (2)
Порт-батч os-port-0722 РЕАЛИЗОВАН тем же днём (builder 650 passed,
106 новых тестов → critic ПРИНЯТЬ → Lead placement 542e8be):
.githooks/pre-commit + scripts/escape_check.py (сид 5 записей),
scripts/wiring_check.py SessionStart-хуком (строка WIRING на буте —
её отсутствие = находка), правило 16 critic.md + scripts/
critic_verdict_check.py — чекер провалидировал ОБА живых вердикта
этой сессии (VERDICT OK x2). (3) AT-BUG-024 Fixed фокус-проходом
/qa-loop B4 (test-maintainer + critic ПРИНЯТЬ): второй AVD
ao3_test_api26 — образ google_apis (default API26 НЕ НЕСЁТ WebView
вовсе — MissingWebViewPackageException, урок в environment-setup);
tasks.ps1 параметризован -AvdName (обратная совместимость живым
прогоном); CA-скрипты с apex-гейтом (API<29 — system-store); p0
46/46 зелёный; deadlock-пункт критерия Fixed переформулирован Lead'ом
на приёмке (TC-109-прогон = downstream, правило 14 + D1). (4)
TC-100..111 Review→Approved по слову оператора (human-переход
transitions.yaml). (5) misc-batch-0722: sibling-четвёрка шапки (5)
ЗАКРЫТА (TC-099 baseline через settle; TC-005 assert усилен
pref-проверкой с красной пробой обеими сторонами — selected-локатора
в Compose нет, ратифицировано; независимость static/behavioral и
aapt-vs-dumpsys — заметками автоматизации TC-100/101/104); заведён
AT-BUG-025 (driver.get-класс, Open — B4-цель). (6) Рецидив «жду
фоновый» у builder — разбужен SendMessage по протоколу, классовый
пробел закрыт: канон-блок в builder.md (правило 9, коммит 22e7b85).
Эмулятор/Appium погашены, NO DEVICE подтверждён канонически. Коммиты:
1534523, 542e8be, 3544823, 0e0f4bb, 4d107d4, 1d66fc3, ea7f129,
1a560e5, 22e7b85. Полный текст — docs/09-history.md §«Шапка
2026-07-22 (6)».

Шапка (5) (Sonnet «/qa-loop 20»: F1 TC-079, automate+F1 TC-096..099,
red-probe ретрофит 28/28, needs-design закрыта целиком) — VERBATIM в
docs/09-history.md §«Шапка 2026-07-22 (5)»; шапка (4) — §«Шапка
2026-07-21 (4)», как и все предыдущие.

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

- **Решения Lead 2026-07-22 по 4 входящим OS — ВСЕ РАЗОБРАНЫ**
  (os-inbox-0722, двухпроходка D-0066): escape-allowlist (N4/D-0082)
  — ПРИНЯТ и реализован (кросс-репо sha-пины; AO3-собственные
  концессии без внешнего носителя решения НЕ пиннятся —
  named-not-covered); judge-приёмка (D-0087) — ПРИЗНАННОЕ ОТЛИЧИЕ,
  не перенимать: **BASIS_VALUES log_append.py НЕ расширять**,
  пересмотр — только с evidence дороговизны critic-входа на листах;
  wiring-чек (t-257) и машиночитаемый вердикт критика (t-259) —
  ПРИНЯТЫ и реализованы (os-port-0722). Полные тексты четырёх
  решений + не-блокирующие наблюдения порта (пустой entries exit 0;
  fail-open и на относительный decision_file; BaseException-шов
  wiring при будущих не-__main__-guarded хук-скриптах) —
  docs/09-history.md §«Решения Lead по входящим OS 2026-07-22».

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
  (1) sibling-находка CH-004 про `driver.get()`-зависание — ЗАВЕДЁН
  bugs/AT-BUG-025.md (2026-07-22, misc-batch-0722, Open, B4-цель;
  вся фактура и критерий Fixed — в баге); (7) та же сессия: двухпальцевые жесты
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
- Решения по t-257 (wiring-чек) и t-259 (вердикт критика) — см.
  сводный пункт «Решения Lead 2026-07-22 по 4 входящим OS» выше;
  оперативные следствия: строка WIRING на буте (её отсутствие =
  находка, Session Start-блок выше), вердикт критика без валидного
  fenced-json не принимается (координатор гоняет
  scripts/critic_verdict_check.py до приёмки, правило 16 critic.md).
