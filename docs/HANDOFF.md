# HANDOFF — точка возобновления

Обновлено: 2026-07-18 (закрытие прохода `/qa-loop 30`: AT-BUG-015
Fixed, правило 14 закрыто полностью — 9 батчей, 44 кейса Automated;
canary R-02 design вне очереди по слову оператора, 14/18 уже Approved,
автоматизация явно отложена на следующий проход). Читать первым при
старте. Итоги прошлых сессий — git-история этого файла и
docs/09-history.md.

**Session Start (детектор пропуска handoff, .claude/skills/session-handoff/):**
первым действием новой сессии — `git status --short`,
`git log origin/master..master --oneline` и
`python scripts/log_append.py open-dispatches` (D-0076: показанные
открытые delegated сверить — воркер жив / результат ждёт / фантом;
фантом — пометкой в notes следующего события). Грязное дерево или
неотправленные коммиты = прошлая сессия закрылась без
handoff-проверки — зафиксировать находкой в журнале (`log_append`),
не поглощать молча. Затем — preflight шаг 0 (сверка яруса).
**ВАЖНО (сверка яруса, D-0058/D-0042):** это закрытие произошло НА
Sonnet — оператор явно переключил модель в середине сессии
(`lead_degraded` записан 01:05:10, `lead_restored` НЕ записан,
окно намеренно переживает сессию, D-0039). Если новая сессия стартует
на Fable — это сам по себе видимый подъём (правило 4б CLAUDE.md):
тем же ходом ретроактивная сверка не нужна (окно уже задокументировано
корректно), но приёмка накопленного за окно (D-0044) и `lead_restored`
— первое действие полного Lead. Если новая сессия снова на Sonnet —
окно просто продолжается, новый `lead_degraded` не дублировать.
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

## Где мы (2026-07-18, проход `/qa-loop 30`, координатор Sonnet)

Дерево чистое, все коммиты запушены (AO3 `58b256d`; OS-репо не
трогался этой сессией). Журнал закрыт, открытых диспатчей нет,
эмулятор/Appium в состоянии среды после последнего device-диспатча —
**не сверено явно этим handoff'ом** (см. «Живое состояние» ниже, это
FAIL шага 3, чинится следующим действием). Сделано:

1. **AT-BUG-015 (TC-047 scroll) → Fixed.** Root cause диагностирован
   измерением (Browse root короче innerHeight → `scrollTo` клампится к
   0), Given сменён на `/tos`, assert с допуском 2px.
2. **Правило 14 закрыто полностью, 9 батчей, 44 кейса Approved→Automated:**
   browser (TC-058) · downloads (TC-032/033/037) · errors (TC-046) ·
   filter-profiles (TC-041, TC-040 отдельно — см. AT-BUG-016) · library
   (TC-006/031/060-065, 8) · rating (TC-009-012/043-045/056, 8 — TC-043/045
   через цикл доработки, class-фикс AT-BUG-017 по пути) · settings
   (TC-018/019/059, TC-020 отдельно — см. BUG-012) · tabs (TC-022-025,
   TC-026 отдельно — см. AT-BUG-018; полный цикл доработки + средовой
   инцидент с зависшими процессами на 8080) · visibility (TC-013/014/015 —
   TC-015 через rejected/attempt-2, реальный дефект понимания live-push
   механизма пойман красной пробой critic'а и исправлен).
3. **Canary R-02 bridge-контракт — вне очереди по слову оператора:**
   18 кейсов дизайна (TC-066-083), P3-контракт (docs/10) покрыт суммой
   полностью, 3 needs-design метки docs/01 §9 сняты. 14/18 уже Approved
   (оператор одобрил через живую борду по ходу дизайна) — **автоматизация
   ЯВНО отложена на следующий проход** (dispatch_skipped 15:30:26, не
   силентный кап).
4. **Баги:** AT-BUG-016 (TC-040 детерминированный краш qemu на
   live-рендере, Open, skip-guard на тест уже стоит), AT-BUG-017
   (интермиттентный `net::ERR_PROXY_CONNECTION_FAILED` вне
   rerun-whitelist — class-фикс device-side reachability guard,
   **Fixed**), AT-BUG-018 (TC-026 long-press по WebView-ссылке ненадёжен
   <10% успеха, Open, 3 механизма исчерпаны), BUG-012 (Clear all ratings
   не broadcast'ит открытым вкладкам — app_bug, Open, **ждёт решения
   оператора** APP_BUG vs Intended).
5. **Находки в очередь Lead (промпт/схема-уровень, не тронуты
   Sonnet-координатором намеренно — D-0058):** (а) `test-automator`
   систематически теряет префикс `framework/` в `automated_by` (2 случая
   за проход) — промпт агента нуждается в явном напоминании; (б)
   субагенты систематически запускают pytest в фоне из СВОИХ диспатчей и
   виснут в ожидании нотификации, которой не будет (только координатор
   её получает) — наблюдалось ~6 раз, каждый требовал SendMessage-резюме;
   базовые инструкции device-QA агентов нужно явно запретить это; (в)
   `schemas/agent-output.schema.yaml` `agent`-enum не содержит
   `test-reviewer` (сам ревьюер это заметил); (г) реестровая
   гранулярность `bridge-rate-note-tag-buttons` (bundles 3 разных
   Then-исхода под одним id) — найдено test-designer при canary-дизайне;
   (д) остаток C4-класса «нет строки Инвариант» — частично закрыт (весь
   tabs-батч, TC-058), сиблинги TC-052/053/055 (browser) вне scope этого
   прохода.
6. **watch-item:** одиночный P0-smoke сбой `test_library.py::
   test_change_rating_moves_work_between_tabs` (TC-016) во время
   побочного regression-прогона tabs-воркера — не расследован, не
   воспроизведён повторно, несвязан с изменённым в этом проходе кодом.

## Где мы — архив (2026-07-17 вечер «механизмы+планы», 2026-07-17/18
ночь «Sonnet→Fable марафон»)

Полные нарративы — `docs/09-history.md` (разделы «Lead-сессия
2026-07-17 вечер» и «Sonnet→Fable марафон 2026-07-17/18 ночь»), вынесены
туда 2026-07-18 (boot-диета, п.4 session-handoff). Коротко: 15/15
AT-BUG-005..014 Verified; TC-042/TC-057 Automated; bring-up-класс
закрыт (package-сервис wait, TC-007); хозяйство docs/09 (sla_utils,
utf-8-гейт, реестр); механизмы SIBLING_MAP/fail-fast/чеки 24/27/28;
docs/01 утверждён владельцем; permission-audit + канон долгих прогонов;
heartbeat/loop_lock built (выключен).

## СЛЕДУЮЩИЙ ШАГ

1. **Решение оператора: BUG-012** (Clear all ratings не broadcast'ит
   открытым вкладкам) — APP_BUG (чинить `SettingsScreen.kt::
   confirmClearAll`, добавить `broadcastRatingChange`-путь) или Intended
   (переформулировать TC-020.Then под факт «нужен reload»)? Блокирует
   TC-020 (Approved, `automated_by` пуст, ждёт этого решения).
2. **Фабричная очередь — /qa-loop:** правило 14 — canary-кейсы
   TC-066..079 (14 Approved, `automated_by` уже placeholder от
   test-designer, framework/tests/canary/ не существует — реальная
   автоматизация ещё не начата); TC-080..083 (4, ещё Review — сначала
   Approve); правило 15 (красная проба, retrofit) — ~27 Automated-кейсов
   без `red_probe`; правило 16 (needs-design) — E1/E2/E3/security
   (нефункциональные области, ниже canary по приоритету docs/01).
   Отдельно: AT-BUG-016/018 (test_debt, оба Open) и BUG-012 (app_bug,
   Open) ждут диспетчеризации фикса вне правила 14.
3. **Еженедельная калибровка** (просрочена дольше обычного). Материал
   этой сессии: систематический класс «субагент виснет на фоновом
   job'е своего диспатча» (~6 раз); дважды пропущенный префикс
   `framework/` в `automated_by`; фантомный `delegated` (worker-ref
   указывал не на того агента, поймано и исправлено тем же ходом);
   находка critic на critic-приёмке (validate_frontmatter поймал
   `AT-BUG-` префикс на `app_bug` — переименовано в `BUG-012`); реестровая
   гранулярность `bridge-rate-note-tag-buttons`; schema-enum пробел
   (`test-reviewer` отсутствует в `agent-output.schema.yaml`).
4. **Промпт-уровень (в очередь полного Lead, не тронуто Sonnet-координатором
   намеренно — D-0058 механизм-гейт):** дополнить `test-automator`
   явным напоминанием про полный путь в `automated_by`; дополнить базовые
   инструкции device-QA агентов явным запретом на фоновый Bash из
   собственных диспатчей субагента (только синхронные вызовы).
5. **Подготовка репетиции (docs/11):** гейт §1 фактически выполнен
   (15/15 старых AT-BUG Verified; AT-BUG-016/018 — новые, после этой
   сессии, не входят в старый гейт). Патчи-подкладки режима A, сев
   П5/П16/П17/П19+backdate П2, включение heartbeat на окно — без
   изменений с прошлого handoff.
6. **Дыра switchTab** — решение test-strategist (строка в docs/09), без
   изменений с прошлого handoff.

**Решение человека в очереди:** BUG-012 (п.1 выше) — единственное
блокирующее. Остальное — рутинная координация.

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
- **Долгие прогоны (канон 07-17):** >~9 мин не влезает в foreground
  Bash (600 с) — только run_in_background; фоновый job → ход БЕЗ
  финального отчёта → нотификация → отчёт с witness; длинные
  device-диспатчи — Agent run_in_background:true (SKILL шаг 2).
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
- **Subagent-фон:** device-QA субагенты систематически путают свой
  фоновый Bash-вызов с координаторским `run_in_background` — у
  субагента НЕТ автономного пробуждения, только координатор получает
  нотификацию. Каждый такой случай в этой сессии требовал
  SendMessage-резюме с явным «работай синхронно». Промпт-фикс — в
  очереди (СЛЕДУЮЩИЙ ШАГ п.4).

## Открытые хвосты (вне текущей очереди)

- Журнал: 2 недостающих теста log_append (rejected-после-accepted;
  frontmatter с нераспознанным model), кириллические SystemExit —
  без изменений с прошлого handoff, не тронуто.
- Некритичные замечания critic по AT-BUG-004 инкр.3 (при касании
  файлов): докстринг assert_rating_badge_visible; ListingPage.badge_for.
- TC-028: устаревшая заметка про эскалацию seed_db — почистит reviewer.
- TC-015.md: несущий факт «WebView живёт между табами» (MainActivity.kt:471,
  от которого зависит истинность «без reload») не процитирован явно в
  теле кейса — некритичная находка critic, дописать при следующей правке.
- Опционально (владелец): del C:\Windows\System32\drivers\aehd.sys.
