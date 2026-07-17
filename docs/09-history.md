# 09-history — история выполнения плана развития

Архив нарративов выполнения [09-improvement-plan.md](09-improvement-plan.md)
(паттерн D-0078 OS-репо: закрытый пункт — полный нарратив сюда VERBATIM тем
же коммитом, в живом плане остаётся короткая `[X]`-строка). Не boot-путь,
грузится точечно. Вынос учреждён 2026-07-17 (слово оператора: живой план —
короткие статусы, история — отдельно). Хронология правок — git обоих файлов.

## Часть I — фазовые нарративы (закрытые фазы)

### Фаза 0 — Окружение и риск-спайки ✅ (2026-07-02/03)

SDK + AVD API 34 (без Google Play — root для CA), debug-APK из исходников,
Appium 2 + uiautomator2. Спайки: **A** ✅ WEBVIEW-контекст виден на
debug-сборке (`chromedriverAutodownload`); **B** ✅ record→replay HTTPS
WebView — блокером был не firewall, а доверие к CA в mount-namespace
приложения на Android 14 (решено namespace-aware установкой CA +
перезапуском фреймворка + правкой SELinux-контекста), подробности и скрипты
— environment-setup.md §Спайк B; **C** ✅ сидинг Room через `run-as`.
Гипервизор на старте — AEHD 2.2; с 2026-07-09 — WHPX, AEHD удалён
(environment-setup.md).

### Фаза 1 — Каркас фреймворка ✅ (2026-07-02)

Все слои docs/02: config, core (driver/waits/adb/contexts/reporting/mitm),
screens (Browser, Library, Settings, navigation, rating overlay), web
(listing, work page, selectors), steps (app/rating/library/settings), data
(works + сидинг Room), conftest с фикстурами, Allure, `scripts/tasks.ps1`,
авто-артефакты падений. Итог: P0 smoke из 9 тестов — дважды подряд 9/9,
~3.5 мин на AVD. Полезные находки переданы дальше: расхождение подписей
вкладок Library с PROJECT.md (позже класс BUG-001), Cloudflare bot-check
(R-03), нижняя навигация скрыта за пилюлей на Browse.

### Фаза 4 — Агентная оркестрация ✅ (2026-07-02)

Агенты созданы РАНЬШЕ полного тест-дизайна (решение владельца): 9 агентов на
старте (к 2026-07-17 — 14: 11 конвейерных + scout/builder/critic),
`state/rules.yaml`, журнал оркестратора, скиллы (/qa-loop, /run-suite,
/triage), каталоги артефактов со статусными машинами. Репетиция сквозного
цикла 2026-07-04 вскрыла A1 (вложенная оркестрация субагентов не работает)
— закрыто Этапом 1 (диспетчеризация на верхнем уровне, docs/03 §1).

## Часть II — сверки и закрытые этапы

### §1. Сверка находок ревью docs/08 с фактическим состоянием (2026-07-07)

| Находка | Статус | Комментарий |
|---|---|---|
| A1 вложенная оркестрация | **Подтверждена, не исправлена** | `/qa-loop` всё ещё запускает qa-orchestrator субагентом; совпадает с критической находкой репетиции тёмного дня (HANDOFF) |
| A2 pre_steps неисполняемы | **Подтверждена** | реализован только `board_inbound.py`; `stale_locks`/`sla_sweep`/`build_watch` — описания; `state/escalations.md` нет |
| A3 сломанный venv | **Не воспроизводится** | `framework/.venv` работает (Python 3.12.10), python в PATH; doctor-скрипт всё равно нужен для автономности |
| A4 ручные счётчики | **Подтверждена** | HANDOFF: «41 Approved»; факт по frontmatter: 37 Approved, 9 Automated, 8 Review, 1 Draft |

(Все четыре закрыты Этапом 1 — A1/A2/A4 механизмами, A3 — doctor.py.)

### Этап 1 — Runtime-фундамент — ✅ ВЫПОЛНЕН 2026-07-07

Все 5 пунктов реализованы (55 pytest scripts/tests зелёные), интеграционная
проверка пройдена: pre_steps в бою (снят протухший лок TC-021), планировщик
--dry-run вернул корректный план + 3 находки (smoke_status исправлен, §9
стратегии протух, canary-правило переведено в [план] до Этапа 3). Задачи
«сильной модели». Без этого этапа конвейер полуручной.

1. **A1 — диспетчеризация с верхнего уровня.** `/qa-loop`-скилл сам читает
   `rules.yaml`, выполняет pre_steps-скрипты и диспатчит воркеров глубины 1
   (синхронно). qa-orchestrator — read-only планировщик для --dry-run.
   Обновлены docs/03 §1, docs/06, промпт, SKILL.md. Выход достигнут: полный
   проход диспатчит >1 воркера, ноль осиротевших локов.
2. **A2 — исполняемые pre_steps.** `scripts/stale_locks.py`,
   `scripts/sla_sweep.py`, `scripts/build_watch.py` — идемпотентные, с
   pytest-тестами (по образцу board_inbound), единый формат
   `state/escalations.md`. build_watch: git fetch app-under-test → новые
   коммиты → gradlew assembleDebug → app-under-test.yaml (+ coalescing D11).
   Первый клиент stale_locks — лок TC-021 (висел с 2026-07-02).
3. **A4 + G1 — генерируемый статус.** `scripts/queue_snapshot.py` собирает
   `state/factory-status.md` из frontmatter; HANDOFF сокращён до resume
   notes; ручные счётчики в документах запрещены.
4. **A3-профилактика — doctor.** `scripts/doctor.py`: python/venv/adb/
   эмулятор/Appium/node/gradle; при провале — эскалация вместо тихого
   падения.
5. **G3 — схемы frontmatter.** `schemas/{test-case,bug,run,rules}.schema.yaml`
   + валидация в preflight /qa-loop: битый frontmatter ловится до
   диспетчеризации.

Хвост (жив в плане): блок разрешений новых скриптов в .claude/settings.json
ждал подтверждения владельца.

### Этап 2 — Исполняемые контракты workflow — ✅ (2026-07-07, все кроме п.7)

1. **C3 + F3 — статусные машины как код.** `schemas/transitions.yaml`
   (акторы, via_board, эффекты, ссылки на D1–D12) + `scripts/transitions.py`;
   whitelist board_inbound выводится из матрицы; 15 self-tests; попутно
   исправлен pingpong в sla_sweep (Fixed не блокируем — шанс fix-verifier;
   Rejected-спор блокируем по D4). Хвосты: тесты парсера permission_audit —
   ✅ 2026-07-07 (35 тестов + вынос collect_suspects); репетиция тёмного дня
   как повторяемый регресс — осталась (жива в плане).
2. **B1/B2/B5 — недостающие ветки workflow.** `resolution:
   accepted_risk|wontfix` + обязательный resolution_comment, `known_issue`
   (дедуп APP_BUG, still-repro D3 расширен, секция дайджеста),
   `blocked_reason` enum во всех трёх схемах (sla_sweep pingpong и
   board_inbound-конфликт проставляют product_decision автоматически;
   validate_frontmatter WARN). sla_sweep молчит для resolution/known_issue
   багов (docs/06 D13/D14). 10 новых self-tests (86 всего).
3. **B3/B4 — lifecycle автотеста и test debt.** Машина `automation`
   (active/quarantined/needs_maintenance/deprecated/retired; карантинит
   failure-analyst, выводит ТОЛЬКО test-maintainer после 3 зелёных);
   sla_sweep quarantine_expired; test debt — bugs/ с type: test_debt +
   debt_kind, guard-переходы Open|Reopened→Fixed для maintainer/automator
   (только test_debt), Fixed не ждёт сборку, отдельная секция digest;
   правила B3/B4 в rules.yaml. Первый клиент: AT-BUG-002.
4. **C2 — evidence contract.** `schemas/evidence.yaml` (6 вердиктов,
   21 элемент) + `scripts/evidence.py` + разделы в
   failure-analyst/fix-verifier + 9 self-tests.
5. **F2 — agent output schema.** `schemas/agent-output.schema.yaml`
   (result: success|blocked|degraded|failed + summary/changed_files/
   evidence/next_rules/escalations), парсер `scripts/agent_output.py`
   (нет блока → degraded), контракт вшит в /qa-loop и docs/03 §5 п.7.
6. **F1 — test-reviewer.** Отдельная роль (opus), «вторые глаза», тестовый
   код не правит; гейт Approved→Automated только у него; возврат —
   review: changes_requested.
7. GitLab Issues — отложено решением владельца 2026-07-07 в Этап 4 п.8.
8. **C1 — архитектурные чеки.** `scripts/arch_check.py` (AST: запрет
   локаторов/screens/web в tests/, обязательные @allure.id + suite-маркер)
   + 23 теста; preflight-шаг 3 /qa-loop; реальные нарушения test_smoke.py →
   ALLOWLIST + AT-BUG-002.

### Этап 4 п.4 — C4 инварианты: механизм (2026-07-14)

Банк инвариантов docs/10 P5: обязанность строки `Инвариант: …` в промпте
test-designer + детектор в п.3 чек-листа test-reviewer; сами инвариантные
кейсы/тесты — штатным конвейером. Прецедент реальной дыры от отсутствия
инварианта — TC-021 (filterProfiles не покрыты round-trip'ом,
changes_requested 2026-07-14); в TC-027..030 ревьюер дыры не нашёл.
Очередь-ретрофит (жива в плане): TC-013/014/015, TC-027..030, TC-038,
TC-047/048/049 — заведены до механизма, строки инварианта не имеют.

### Этап 4 п.9 — фикс кириллицы sync-виджета: класс бага и путь A (референс для пути B)

- **Причина (класс):** Dart `ascii/latin1.encode` на не-Latin1 строке
  (`_UnicodeSubsetEncoder` → `ArgumentError` "Contains invalid characters.",
  кладёт саму строку в значение — оттого в ошибке виден весь JSON коммита).
  Кириллица в commit message косвенно попадает в энкодер на шаге `checkSync`.
- **Путь A — сделан и НЕ сработал (2026-07-08):**
  `install-update-trackstate.yml` перепинен с upstream
  `IstiN/trackstate@v2099.173.100715142411` на форк
  `Xartaxana/trackstate-by-Dark-Factory@2b258f68…` (полный 40-символьный
  SHA). Баг есть и в `main` форка; прямого `ascii/latin1.encode` в
  исходниках нет → вызов косвенный.
- **Путь B — референс шагов (живой план):** (1) собрать Flutter web из форка
  локально (flutter 3.35.3, те же `--dart-define`, что в workflow),
  воспроизвести sync на репозитории с кириллицей; (2) поймать стек-трейс —
  сейчас проглатывается (`workspace_sync_service.dart` `on Object catch`
  показывает только `'$error'`); временно пробросить stackTrace, найти
  файл:строку косвенного encode (кандидат — `github_trackstate_provider`
  `checkSync`/`_readHostedRepositoryDelta`); (3) патч utf8 вместо
  ascii/latin1, пуш в форк, обновить SHA-пин, передеплой; (4) опционально
  PR/issue в upstream. Детектор (F-11в): сам виджет («Attention needed»
  пропадает). См. память trackstate-board-sync-cyrillic-defect, docs/05.

### Этап 4 п.10 — доделка борды: развёрнутый скоуп владельца (2026-07-14)

Одним заходом с п.9 (та же локальная сборка из форка, тот же цикл
патч → пин SHA → передеплой; фикс кириллицы первым — разблокирует
sync-виджет). Требования:
- **Шаг 0 — аудит «из коробки»** (урок пути A: сначала проверить
  эмпирически): что `main` форка уже умеет из списка — дорабатывать только
  фактические пробелы.
- **Правая панель тикета** (детальная карточка из канбана) и
  **сортировки/фильтры** по статусам/приоритетам.
- **Переименование/добавление колонок** — с коммитом (ок по решению
  владельца). Ожидаемо не код форка, а проекция: project.json/статус-маппинг
  в board_sync.py (единственное место маппинга — docs/05). ВНИМАНИЕ: набор
  колонок = маппинг статусов → сверить со schemas/transitions.yaml и
  whitelist board_inbound (docs/06 §3, docs/07), чтобы колонка не рождала
  нелегальных переходов; ЭТА часть — механизм, через гейт F-11.
- **Комментарии в обе стороны:** (а) система → UI: реплики «## Обсуждение»
  проецируются board_sync в комментарии TrackState (формат реверсится —
  помечено в docs/07 §«Обвязка»); (б) владелец → система: комментарий в UI →
  коммит → board_inbound переносит в артефакт (канал есть, расширить на
  фактический формат TrackState).
- **Approve-кнопка НЕ нужна:** drag + board_inbound-whitelist достаточны;
  кнопка ✓ остаётся особенностью локальной стадии-1 (board_server.py).
- **Детектор (F-11в):** визуальная приёмка владельцем после передеплоя +
  контур board_inbound (реплика/переход доходит до артефакта).

### Дополнения по ревью docs/10 — выполненные части

- **доп.10 seeded defects, ярус 1 (2026-07-17, слово оператора):**
  обязательная «красная проба» в чек-листе F1 test-reviewer (п.7 промпта) —
  каждый НОВЫЙ автотест доказывает умение падать на одной контролируемой
  порче данных/окружения, без касания кода приложения. Ретрофит на принятые
  Automated-тесты — машинный: поле `red_probe` в test-case.schema.yaml,
  правило rules.yaml «Красная проба существующего автотеста» (test-reviewer,
  режим red-probe-only), счётчик долга «Automated без red_probe» в
  factory-status.
- **доп.11 exploratory, шаги 1–2 (2026-07-14):** каталог
  exploratory-charters/ + README, docs/templates/charter.md, роль
  exploratory-tester (opus); charter.schema.yaml + AREAS, правило
  rules.yaml, скан SKILL.md, метрики charters_* в queue_snapshot, охват
  stale_locks (блокер critic: reaper не видел charter-локи — класс TC-021).
  Остаток класса «типы артефактов в N местах» (вердикт critic
  e4-pipeline-wiring; жив в плане): (а) transitions.yaml — машины charter
  нет (риск LOW); (б) sla_sweep — SLA-порогов для charter нет (LOW);
  (в) board-проекция — charter'ы не видны (косметика); (г) КОРЕНЬ: единый
  источник списка областей-типов (validate_frontmatter.AREAS vs
  board_sync._iter_artifacts vs локальные сканеры) — следующая новая
  область добавляется в ОДНОМ месте. (а)–(г) — одна задача рефакторинга.
- **доп.12 coverage-проекция:** генерируемый граф
  feature → risk → TC → automated test → last green (coverage_map.py).
  Находка реализации (r10-coverage-map, 2026-07-14): схемы не связывали run
  с TC — закрыто пер-TC результатами: `tc_results` в run-артефакте
  (2026-07-16) + фичевая трассабилити (реестр 74 фич, поле features,
  детектор протухания реестра — 2026-07-17); рукописный coverage-yaml не
  заводится, state/traceability.md удалён как ручной дубль.

### §5. Сверка внешнего ревью docs/10 с фактическим состоянием (2026-07-14)

Основание: docs/10 (2026-07-13); фактура сверена разведкой r10-adoption-recon
(routing-log 2026-07-14): canary-пакет пуст, coverage-model/
exploratory-charters нет, неавтоматизированные P0 и статусы R-09/R-10
подтверждены пофайлово.

| Пункт ревью | Сверка | Решение |
|---|---|---|
| P1 regression не регулярный | Подтверждено (07-10: smoke passed, regression not_run) | Release-readiness вытянута вперёд (r10-release-readiness); регулярный gate — Этап 4 п.6 |
| P2 P0-гэпы | Подтверждено дословно: TC-009/013/014/015 (AT-BUG-004), TC-021 (AT-BUG-005) | Уже пункты 2–3 Этапа 3; нового не заводим |
| P3 canary отсутствует | Подтверждено (пустой пакет, правило [план]) | Этап 3/rules.yaml; bridge-контракт ревью — DoD диспатча |
| P4 project intake | Для AO3 не требуется | Стратегическая развилка владельца, не пункт очереди |
| P5 инварианты | Частично уже C4 | C4 дополнен банком инвариантов ревью |
| P6 seeded defects | Новое | Этап 4 доп.10 |
| P7 exploratory charters | Новое (каталога нет — сверено) | Этап 4 доп.11 |
| P8 non-func раньше | E1–E3 уже в Этапе 4 | Порядок прежний (решение владельца 07-14) |
| P9 security smoke | Конфликт с отказом E4 | Принят минимальный скоуп (07-14) — доп.13 |
| P10 R-09/R-10 proposed | Подтверждено | Утверждены оба (07-14), внесены в §5 стратегии |
| D1 historical-снимки | Подтверждено расхождение | ✅ 07-14: числа из docs/01 §9 убраны, раскладка HISTORICAL |
| D2 release-readiness | Частично Этап 4 п.6 | Вытянуто вперёд: секция в queue_snapshot → factory-status; стартовые метрики — только считаемые |
| D3 gate-driven roadmap | Принято как форма | Для НОВЫХ крупных пунктов — owner/input/output/exit; ретроспективно не переписываем |
| §6 метрики (~35) | — | Оптом не берём; стартовый набор в release-readiness |
| §5.2 coverage graph | coverage-model.yaml нет (сверено) | Доп.12 — генерируемая проекция, не рукописный yaml |

Развилки владельца — решены 2026-07-14: (а) R-09/R-10 утверждены (BUS 4,
DATA 4); (б) security — минимальный smoke-скоуп; (в) порядок E1–E3 прежний.

### Мелкое хозяйство — закрытое

- Убраны scratch_screen*.png из корня (0 png в корне на 2026-07-17).
- Закоммичены README.md, docs/08, docs/09, .agents/ (в репо с 07-07).
- Косметика/классы, доложенные builder'ами 07-14 и живые в плане, — см.
  «Мелкое хозяйство» живого документа.

## Heartbeat-механизм (Фаза 4.5, 2026-07-17)

Закрыт последний несделанный механизм гейта репетиции (docs/11 §1).
Состав: (1) `scripts/loop_lock.py` (builder heartbeat-loop-lock, критик —
«принять»; 14 тестов + 384 полного набора зелёные): acquire/release/status,
BUSY-выход при живом чужом локе, REAPED протухшего (порог sla.lock_stale) с
инкрементом счётчика подряд снятых, LOOP-эскалация с тегом `[loop:reaped]`
при ≥2 (тег намеренно НЕ `[sla:*]` — rewrite sla_sweep стирает чужие
sla-строки; находка builder, подтверждена критиком эмпирически), release
сбрасывает счётчик; атомарная запись tmp+replace. Принятое ограничение
(критик N1): истинного mutex под гонкой нет — проходы сериализованы
heartbeat-планировщиком, O_EXCL по рецидиву. (2) Интеграция: preflight 0а
и чек-лист завершения qa-loop SKILL; REAPED-строку в orchestrator-log
пишет координатор прохода (двойного логирования из скрипта нет —
архитектурное решение, подтверждено критиком). (3) Планировщик: задача
`AO3-QA-Heartbeat` (каждые 2 ч → `scripts/heartbeat.cmd`: headless
`/qa-loop 3`, Sonnet-координатор, лог `logs/heartbeat.log` в gitignore) —
создана ВЫКЛЮЧЕННОЙ; включение — слово владельца / старт репетиции.
Очередь-остаток: общий helper load_lock_stale_hours + N2 (битый лок в
death-streak) — хозяйство docs/09. Контекст дня: loop.lock был третьим
экземпляром класса «обещанный механизм без кода» (F-45-родня), вскрыт
вопросом оператора «что будет, если heartbeat выяснит, что фабрика стоит».

## Слияние планов (2026-07-17)

docs/04-roadmap.md (фазовая карта старта, 2026-07-02..04) влит Частью I в
docs/09 по слову оператора, файл удалён (история — git). Тем же днём
docs/09 переведён в статусный [X]/[ ]-формат, нарративы вынесены сюда;
docs/09 добавлен в бут-перечень (HANDOFF Session Start + boot-бюджет
session-handoff + чек 10 калибровки OS).
