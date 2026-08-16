# П1: дедуп e2e-тестов + нормы слияния (spec-p1-dedup v5)

Слово оператора 2026-08-16: «тесты не должны копировать друг друга
(особенно эмуляторные); можно один тест подлиннее и несколько проверок;
можно параметризовать». П1+П2 утверждены, П3 после.

v5 — правки по критик-раунду 4 (2 блокера: carve-out по to=Blocked
убивал bug Verified→Open и automation retired→deprecated; фолбэк
board_inbound:186 безусловен). Статус: **план на критик-входе, раунд 5
(точечный)**. Автор: Lead (Fable). «Оператор в петле» — информирован.

## Факты (r1/r2, приняты; ключевые witness'ы критиков)

1. 1:1 TC↔тест; норма docs/02:116-117; в промптах норм дедупа нет.
2. Матрица: terminal: []; **валидатор терминальности не видит
   `from: "*"`-правил** (transitions.py:180-184) — класс задевает и
   run.Closed; from-СПИСОК одним правилом не поддержан (str(t["from"]));
   Review→Approved — by: [human] (борда).
3. Потребители статусов — ЛИТЕРАЛЫ: board_sync.py:701-704 (story-стадия
   + unknown_cases WARN), :733 (all==Automated → «Покрыта»), :744
   (знаменатель бейджа); STATUS_MAP/STATUSES/WORKFLOWS борды +
   board_inbound.INV_STATUS_MAP (коллапс при маппинге Merged→
   tc-automated: 153 ложных reject/проход — witness r2);
   queue_snapshot.py:37/:163/:165; coverage_map.py:36/:225/:230-233/:247;
   validate_frontmatter.py:285 (WARN automation_status при
   не-Automated). board_view.py — производный, правок не требует.
4. parity-тест НЕ в preflight qa-loop (там doctor+validate+arch_check,
   SKILL.md:93-112); parity красен только у того, кто гоняет
   scripts/tests (например, параллельный builder П2). Направление
   проверки одностороннее: TC→функция; «функция без TC» не проверяется.
5. Батарея TC-112..117: TC-114/115 red_lock BUG-014 (замок НЕ снят —
   Verified, но поле стоит), TC-116/117 — P2, TC-112/113 — разные
   фикстуры. Пилот TC-034/035/036: TC-035 (delete file) разрушает
   предусловие TC-036 — нужен пересидинг внутри journey.
6. rules.yaml:160-162 (ретрофит красной пробы) триггерится только по
   ПУСТОМУ red_probe — для journey слеп по построению.
7. bugs: BUG-047 (Verified) держит TC-035 контрольным путём верификации;
   fix-verifier.md:134 умеет только «прогон невозможен — automated_by
   пуст».
8. П2 N4 owns пересекается с П1 N4 не только промптами: schema,
   validate_frontmatter (+тесты), docs/02.

## Решения

### Р0. Статус `Merged` — точная механика (решение полного Lead)

1. schemas/test-case.schema.yaml: `statuses += Merged`; поле
   `merged_into` (`^$|^TC-\d+$`); правила validate:
   «Merged ⇒ automated_by пуст И automation_status ПУСТ И merged_into
   непуст» + обратное «merged_into непуст ⇒ status == Merged»;
   validate_frontmatter.py:285 — automation_status у поглощённого
   ОБНУЛЯЕТСЯ (не retired: automation-машина не трогается, пустое поле
   легально у не-Automated).
2. schemas/transitions.yaml: **ДВА правила** — `Automated → Merged` и
   `Approved → Merged`, оба `by: [human, lead]`, effects: [];
   `terminal: [Merged]`; **явный откат** `Merged → Review,
   by: [human, lead], rollback: true` (прецедент поля :82-84) — вместо
   случайного «звёздочного» пути.
3. **Фикс терминальности — ДЕКЛАРАТИВНЫЙ ФЛАГ в матрице (r4), интент
   каждой машины сохранён явным решением.** Валидатор матрицы
   (:180-184) НЕ меняется. Новое поле правила
   **`from_terminal: true`** (default false) = «правило матчит и
   терминальный from». Проставляется по КАЖДОМУ `*`-правилу (перепись
   r4, решения полного Lead):
   - bug `*`→Open (human, via_board) — **true**: путь переоткрытия
     Verified→Open сохранён (пин test_transitions.py:272-275 остаётся
     зелёным, док-путь docs/06:140/docs/07:97 жив);
   - test-case/run/charter `*`→Blocked (factory) — **true**:
     эскалационный интент пина :115-124 сохранён;
   - test-case `*`→Review — **false**: это и глушит воскрешение
     Merged (выход из Merged — только явный rollback-переход);
   - automation `*`→deprecated (human/test-strategist) — **true**:
     семантика смежной машины НЕ меняется (пин :149-156 дополняется
     позитивным кейсом human/strategist).
   Исполнители — ТРИ (r4): `transitions.find()`/`is_allowed` (учёт
   флага); `board_whitelist()` — без изменений семантики ключа `"*"`;
   **`board_inbound.py:186` — фолбэк на `allowed["*"]` применяется
   только для НЕтерминального src_status** (terminal-набор
   импортируется из transitions; ветка :183 `src_status == "*"` —
   поведение не меняется). Пины: LEGACY_WHITELIST
   (test_transitions.py:227-250), «`*` без флага не оживляет
   терминальный», «Verified→Open человеком жив», «retired→deprecated
   human/strategist жив», «откат rollback жив», **«Merged-карточку с
   борды не применить» — пин на `board_inbound.classify()` (полный
   путь с фолбэком), не на board_whitelist**.
4. **Борда: отдельная колонка `tc-merged`** (STATUSES + WORKFLOWS +
   STATUS_MAP, обратимость INV 1:1 — коллапс невозможен); юнит
   test_board_sync.py:162 расширяется. Защита от ручного перетаскивания
   — НЕ «отсутствие via_board» (дыру давало СТАРОЕ `*`-правило), а
   terminal-гард фолбэка board_inbound:186 из п.3 + пин «Merged-
   карточку с борды не применить» (на classify). **board_view.py:
   Merged-карточка в board-view.html НЕ отображается (COLUMNS:36, как
   сейчас tc-blocked) — принято сознательно, явная строка.**
5. Поимённые правки потребителей: board_sync.py:701-704 (Merged в
   литерал, БЕЗ попадания в unknown_cases), :733 («Покрыта» = все
   Automated|Merged), :744 (знаменатель бейджа БЕЗ Merged);
   queue_snapshot.py:37 (+колонка), :163 (tc_priority_automated:
   Merged не в знаменателе), :165 (P0-Merged не считается
   непокрытым — покрытие несёт journey из merged_into);
   coverage_map.py:36 (+Merged в порядок статусов), :225,
   :230-233 (total без Merged), :247 (P0/P1-Merged не «пробел»);
   impact_select.py:274-277 И близнец-smoke-листинг :282-285 (обе
   f-строки — «merged → TC-YYY»). Рассмотрены, правок НЕ требуют:
   coverage_map:445, board_sync:747, queue_snapshot:157 (все
   `== "Automated"` — для Merged безопасны, witness r3).
6. Потребители automated_by и ПИСАТЕЛИ ВЕРДИКТОВ (класс расширен r3):
   - fix-verifier.md + test-runner.md: «automated_by пуст И status
     Merged ⇒ гнать тест из merged_into»; если journey-цель сама без
     automated_by (окно пилота) — явный «прогон невозможен: journey
     не автоматизирован», не молчание (расширение существующей ветки
     fix-verifier.md:134);
   - **failure-analyst.md**: упавший тест, чей allure.id разрешается в
     Merged-кейс, — вердикт пишется строкой Обсуждения в
     merged_into-кейс (у Merged automation_status пуст, машина
     automation неприменима); правка промпта — owns N4.

### Р1. Journey-TC (границы уточнены)

- Journey несёт union features и union risk поглощённых.
- **Пересидинг внутри journey легален** и НЕ считается «другой
  фикстурой»: чекпойнт, разрушающий предусловие следующего, законен
  при явном пересидинге между чекпойнтами (сид дешевле новой
  Appium-сессии — в этом и выигрыш). Критерий границы вместо буквального
  «разные фикстуры»: **«разная СТОИМОСТЬ/природа Given»** (другой
  replay-файл, другой запуск приложения, другие env-условия —
  не сливать; один сид с вариациями — сливать можно).
- Запреты (без изменений): red_lock; разные приоритеты; разные
  suite-маркеры; регресс-замки known_issue/D3; кейсы из test_cases
  ОТКРЫТЫХ багов; смешение live/replay.
- **Потолок: ≤5 чекпойнтов на journey** (флейк-амплификация: один флейк
  гасит N рисков; детектор — счётчик карантина queue_snapshot.py:136 —
  named).
- DoD слияния: scripts/tests -q зелёный, validate 0/0, coverage_map
  без новых пробелов (witness'ы).

### Р2. Параметризация — только внутри одного кейса

(без изменений v2; правка parity-резолвера под func[param] — очередь
мелочей).

### Р3. Нормы в промпты

Как v2 (designer «дедуп прежде дизайна», automator, F1 «проба на
КАЖДЫЙ чекпойнт») + **машинный детектор проб** (validate читает тело —
_parse_frontmatter возвращает body, validate_frontmatter.py:376):
- машинная форма (r3, уточнена r4): чекпойнты = пункты нумерованного
  списка раздела `## Чекпойнты`; записи проб = строки, начинающиеся
  `- проба:` в разделе, чей заголовок начинается с `## Красная проба`
  (**матч по ПРЕФИКСУ** — существующие 16 секций несут суффикс
  «(red_probe, ретрофит — …)»); проза/иные упоминания не считаются.
  Связка носителей: frontmatter `red_probe` = ts ПОСЛЕДНЕЙ пробы —
  его читают rules.yaml:161 и F1 (как сегодня); строки `- проба:` —
  счётный носитель validate-правила; у journey при Automated
  red_probe непуст штатно (F1 ставит). Обе секции добавляются в
  docs/templates/test-case.md (файл в owns N4);
- **статус-гард (r3): правило — ERROR только при status==Automated**;
  до Automated (Review/Approved, пробы ещё не ставились — F1 впереди)
  правило молчит — Р4 не краснеет с шага 1;
- ретрофит-правило rules.yaml:160-162 для journey слепо по построению —
  компенсация: validate на пути preflight.
**Порядок норм (координация с П2): «сначала СЛОЙ (П2), потом дедуп
ВНУТРИ слоя; journey не склеивает через границу слоёв»** — дословно в
test-designer.md, первым пунктом блока.

### Р4. Порядок пилота (исправлен по r2 — гейты не краснеют ни в один момент)

1. Ручной диспатч test-designer (не when-условие): journey-TC (Review),
   чекпойнты: открыть файл (CSS) → удалить файл (рейтинг жив) →
   [пересидинг] → удалить работу (всё удалено). wip-лок на
   test-cases/downloads/*.
2. **Lead: Merged-переводы ПОЛНОСТЬЮ ДО любого кода** — статусы,
   `automated_by: ""`, `automation_status: ""`, merged_into у
   TC-034/035/036 (их функции ещё ЖИВЫ; parity односторонний — зелёный;
   старые тесты до удаления гоняются маркером p1, регресс не оголён).
   DoD: scripts/tests + validate прогоны.
3. Оператор: **Approve journey-TC на борде** (узел ожидания).
4. Очередь фабрики: правило B3 (Approved, automated_by пуст) →
   test-automator ОДНИМ диффом пишет journey-функцию И удаляет три
   старые; затем F1 (пробы по чекпойнтам). Ручных диспатчей нет.
5. Приёмка Lead: витness-пакет (scripts/tests, validate, coverage_map),
   критик-вход полного цикла пилота как образец.

**Окно шагов 2→4 — честно (r3):** в impact-режиме область downloads
между обнулением automated_by (шаг 2) и появлением его у journey
(шаг 4) ПУСТА (test-runner.md:55 гонит только automated_by-пути);
полная p1-регрессия жива. Митигция: шаги 2–4 планируются одним окном
координации, прогоны области в окне не диспатчатся (контроль Lead);
остаточный риск явной строкой, детектор — failure-analyst-правило
п.6 (упавший Merged-кейс виден и маршрутизируется в merged_into).

Раскатка: **корпус выбирается по ОБЩЕЙ ФИКСТУРЕ** (Grep фикстур по
framework/tests/), не по соседним id. Батарея TC-112..117 признана
непригодной (red_lock ×2, P2 ×2, разные фикстуры) — кроме пары
TC-116/117 (p2, вне метрики; сливать можно, выгода мала — решение
designer). Честная оценка: главный доказанный выигрыш — пилот +
группы с общей фикстурой в rating/library; процент выгоды НЕ
прогнозируется — меряется протоколом: full-прогон device-слоя
до/после, та же селекция/устройство, **фильтр `-m "(p0 or p1) and
not bridge"`** (bridge-тесты П2, приезжающие в p1 между замерами, не
загрязняют базу — дом формулы здесь по обязательству П2 N8).

## Четыре вопроса F-11

- **(а) Стоимость:** разовая — механика Merged (схема+матрица+валидатор
  терминальности+борда+потребители) и рефакторинг; постоянная —
  designer-чек дубля, оператор — Approve journey-кейсов.
- **(б) Оси перечислением:** schemas (test-case.schema, transitions) ↔
  scripts/transitions.py (+test_transitions — классовый фикс
  терминальности) ↔ validate_frontmatter (+тесты) ↔ board_sync +
  board_inbound (+test_board_sync; board_view — N/A, производный) ↔
  coverage_map ↔ queue_snapshot ↔ impact_select (:274-277) ↔
  fix-verifier.md + test-runner.md (правило merged_into) ↔ промпты
  test-designer/automator/reviewer (батч с П2; порядок норм П2 первым)
  ↔ docs/02 ↔ **докось: docs/03-agent-system.md:66, docs/05-board.md:
  20/65-66, docs/06-dark-factory.md:98/229, docs/templates/
  test-case.md:9-11** ↔ test-cases/** ↔ framework/tests/** ↔
  state/rules.yaml (не правится; шаг 4 идёт его правилами — названо) ↔
  qa-loop SKILL.md (не правится, строка сверки) ↔ генерируемые
  state/coverage-map.md, factory-status.md, escalations.md. Коммиты
  Р0/Р3 — механизменные (осевой блок + tier). **Пересечение owns с П2
  объявлено: schema, validate (+тесты), docs/02, промпты — единый батч
  N4 двух планов, склейка Lead.**
- **(в) Детекторы:** parity + validate — в DoD КАЖДОГО шага слияния
  (parity не в preflight — детектор именно DoD-прогон, названо честно);
  валидатор терминальности (+пин) — против воскрешения; коллапс борды
  невозможен by construction (1:1); coverage_map — потеря покрытия;
  счётчик карантина — флейк-амплификация; чек 8 калибровки — мёртвая
  норма.
- **(г) Не даёт пропустить:** validate-правила Merged (двусторонние) —
  код на preflight; транзишен-матрица + фикс валидатора — код;
  борда без via_board для Merged — код. На дисциплине: порядок шагов
  Р4 (ловят DoD-прогоны шага 2 и приёмка), выбор designer (ловит F1).

## DAG

- N1 recon — done. N2 v1 → r1 ДОРАБОТАТЬ. N3b v2 → r2 ДОРАБОТАТЬ
  (оператор в петле). N3d v3 → r3 ДОРАБОТАТЬ (5 блокеров: локализация
  фикса терминальности с сохранением интента `*`→Blocked, борда через
  terminal-aware whitelist, статус-гард и машинная форма детектора
  проб, окно 2→4 + триаж Merged). Критик-раунды accepted.
- N3f v4 → r4 ДОРАБОТАТЬ (carve-out по to бил Verified→Open;
  board_inbound:186). **N3h v5** — этот файл — done (декларативный
  from_terminal, три исполнителя, пин на classify, док-носители
  whitelist в owns). **N3i критик r5 (точечный)** — in progress.
- **N4 механизм Merged + нормы** — builder, после PASS r3 (батч
  промптов/схемы/validate/docs02 — общий с П2 N4). Owns (расширен):
  schemas/*, scripts/transitions.py, validate_frontmatter.py,
  coverage_map.py, queue_snapshot.py, board_sync.py, board_inbound.py,
  impact_select.py (+все их тесты), .claude/agents/test-designer.md,
  test-automator.md, test-reviewer.md, **fix-verifier.md,
  test-runner.md, failure-analyst.md**, docs/02, docs/03:66 (+строка:
  обнуление automation_status у Merged — второй путь смерти автотеста
  мимо машины automation с её retired; выбран сознательно, чтобы не
  плодить переходы автомашины для поглощённых), docs/05,
  docs/06:98/229 **и :140-141 (листинг whitelist)**,
  **docs/07-board-inbound.md:97-100 (док-носитель whitelist)**,
  docs/templates/test-case.md (+секции Чекпойнты/Красная проба).
  Non-goals: rules.yaml, qa-loop SKILL.md, test-cases/**,
  framework/tests/**. Критик-вход диффа обязателен.
- N5 пилот-дизайн (designer, wip-лок) → **N5a Merged-переводы Lead
  (ДО кода)** → **N5b Approve оператора (борда)**.
- N6 пилот-код — очередь фабрики (B3→F1) + критик-вход цикла.
- N7 раскатка — корпус по общей фикстуре.
- N8 приёмка — Lead: метрика-протокол, журнал, HANDOFF.
