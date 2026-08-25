# П1: дедуп e2e-тестов + нормы слияния (spec-p1-dedup v7)

Слово оператора 2026-08-16: «тесты не должны копировать друг друга
(особенно эмуляторные); можно один тест подлиннее и несколько проверок;
можно параметризовать». П1+П2 утверждены, П3 после.

v6 — правки по критик-раунду 5 (2 блокера: гард по терминальности
src_status ломал Verified→Open с борды — нужен порульный по флагу;
откат из Merged красил validate). Б1 (from_terminal) подтверждён
эмпирикой r5. Статус: **план на критик-входе, раунд 6 (точечный)**.
Автор: Lead (Fable). «Оператор в петле» — информирован.

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
   by: [human, lead], rollback: true, БЕЗ via_board** (иначе ключ
   Merged попадает в board_whitelist — краснеет пин паритета и
   открывается борд-путь из терминального; двигать Merged можно только
   транзишеном руками/Lead). **Механика отката (r5):** откат ОБЯЗАН
   тем же ходом обнулить `merged_into` (иначе двустороннее
   validate-правило п.1 красит сам санкционированный выход); кейс
   возвращается в Review с пустыми automated_by/automation_status
   (функция уже удалена — легально у не-Automated). **Конфликтная
   ветка борды:** apply_conflict пишет Blocked мимо whitelist —
   для Merged-карточки (признак: **`artifact_status` на диске**, не
   cursor_artifact) конфликт = ЭСКАЛАЦИЯ БЕЗ смены статуса; строка
   эскалации и обновление курсора выполняются, не выполняется только
   запись статуса (правка board_inbound.apply_conflict, файл в owns).
3. **Фикс терминальности — ДЕКЛАРАТИВНЫЙ ФЛАГ в матрице (r4), интент
   каждой машины сохранён явным решением.** Валидатор матрицы
   (:180-184) НЕ меняется. Новое поле правила
   **`from_terminal: true`** (default false) = «правило матчит и
   терминальный from». Проставляется по КАЖДОМУ `*`-правилу (перепись
   r4, решения полного Lead):
   - bug `*`→Open (human, via_board) — **true**: путь переоткрытия
     Verified→Open сохранён (пин test_transitions.py:272-275 остаётся
     зелёным, док-путь docs/06:140/docs/07:97 жив);
   - run/charter `*`→Blocked (factory) — **true**: эскалационный
     интент пина :115-124 сохранён; **test-case `*`→Blocked —
     `false`** (r6, решение полного Lead): у test-case terminal
     впервые непуст, и true открывал бы фабрике Merged→Blocked при
     непустом merged_into (ERROR validate); эскалация по Merged-кейсу
     = эскалация БЕЗ смены статуса, симметрично решению по
     apply_conflict; для нетерминальных статусов test-case поведение
     `*`→Blocked не меняется (флаг гейтит только терминальный from).
     Уточнение (r7): на ФАБРИЧНОЙ ветке переход просто отсутствует —
     эскалация без смены статуса реализуется только бордовой веткой
     apply_conflict; фабричного писателя эскалаций НЕ изобретать.
     Пин: **«фабрика не выводит из Merged» (is_allowed по всем
     фабричным акторам = пусто)**;
   - test-case `*`→Review — **false**: это и глушит воскрешение
     Merged (выход из Merged — только явный rollback-переход);
   - automation `*`→deprecated (human/test-strategist) — **true**:
     семантика смежной машины НЕ меняется (пин :149-156 дополняется
     позитивным кейсом human/strategist).
   **Область гарда (явно, r6): from_terminal гейтит ТОЛЬКО правила с
   `from: "*"`; правило с ЯВНЫМ терминальным from (rollback-переходы:
   Merged→Review, bug Verified→Fixed) матчит без флага.** Пин «откат
   rollback жив» ОБЯЗАТЕЛЕН — слова rollback в scripts/tests сегодня
   нет вовсе (негатив r6 со следом), сетки под альтернативное чтение
   не существует.
   Исполнители — ТРИ (r5: гард ПОРУЛЬНЫЙ по флагу, не по
   терминальности src — иначе ломается Verified→Open с борды, у bug
   нет прямого правила из Verified, только `*`→Open с флагом):
   - `transitions.find()`/`is_allowed` — учёт флага;
   - `transitions` отдаёт **board-aware хелпер `board_allowed(itype,
     frm, to)` поверх find()** (учитывает from_terminal и via_board;
     **guard НЕ участвует** — семантика board_whitelist; иная
     реализация через is_allowed с meta=None молча превратила бы
     будущее guard-правило в reject) + публичный аксессор
     `terminal(itype)`; `board_whitelist()` и пин LEGACY_WHITELIST
     НЕ трогаются;
   - `board_inbound.classify()` зовёт `board_allowed` вместо
     собственного фолбэка на `allowed["*"]` (:186) — классификатор
     перестаёт дублировать логику матрицы (единый источник правды).
   Пины: LEGACY_WHITELIST не тронут (test_transitions.py:227-250),
   «`*` без флага не оживляет терминальный», «Verified→Open человеком
   жив» (is_allowed), «retired→deprecated human/strategist жив»,
   «откат rollback жив», и ДВА пина на classify(): негативный
   «Merged-карточку с борды не применить» + **ПОЗИТИВНЫЙ «bug
   Verified→Open с борды применяется»** (без него класс регрессии
   без детектора).
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

   > **ПРЕДОХРАНИТЕЛЬ ШАГА 4 (внесён 2026-08-25 по критик-раунду 2 по
   > `arch_check`; поставлен в носитель ЦЕЛИ намеренно — раньше указатель
   > лежал только в `docs/HANDOFF.md` с формулой «пометить при первом
   > касании», то есть исполнитель этого шага его бы не увидел).**
   > Удаление тест-функций `TC-034/035/036` из
   > `framework/tests/test_downloads.py` (строки 107/135/157) СДЕЛАЕТ
   > КРАСНЫМ real-repo пин правила 6 в
   > `scripts/tests/test_arch_check.py`
   > (`test_real_repo_automated_by_allure_id_link_test_side_baseline`):
   > пин ключуется кортежем `(файл, функция, метод)`, три записи из него
   > исчезнут. **Это ОЖИДАЕМЫЙ красный, а не поломка** — обнови множество
   > пина ТЕМ ЖЕ диффом и назови причину в сообщении коммита. Чего делать
   > НЕЛЬЗЯ: молча подогнать множество под новый вывод, не поняв, почему
   > оно изменилось, — ровно так `test_dedup_check::
   > test_repo_baseline_covers_the_current_corpus` пролежал красным
   > четверо суток (21.08→25.08).
   > **Второй предохранитель — к шагу 2.** Пока кейсы `Merged`, а их
   > функции живы, правило 5 (`priority`-маркер, ярус ERROR) сверяет
   > маркер теста с приоритетом СЛИТОГО кейса. Сегодня совпадение
   > `P1`↔`p1` случайно; любая промежуточная пометка вроде «сделать `p3`,
   > покрыто journey» уронит канонический `scripts/tests` ошибкой,
   > названной по слитому кейсу. Правило учат молчать по `Merged`
   > эскалацией того же критик-раунда — если на момент шага 2 молчание
   > ещё не приехало, маркер не трогай.
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
  20/65-66, docs/06-dark-factory.md:98/229/140-141,
  docs/07-board-inbound.md:97-100 (док-носители whitelist),
  docs/templates/test-case.md:9-11** ↔ test-cases/** ↔
  framework/tests/** ↔
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
- N3f v4 → r4 ДОРАБОТАТЬ. N3h v5 → r5 ДОРАБОТАТЬ (гард по src_status
  бил Verified→Open с борды; откат без обнуления merged_into).
  N3j v6 → r6 ДОРАБОТАТЬ (1 блокер: from_terminal:true на test-case
  `*`→Blocked открывал фабрике Merged→Blocked; board_allowed
  подтверждён точным дифом NONE). **N3l v7** — этот файл — done
  (test-case `*`→Blocked = false, эскалация по Merged без смены
  статуса, область гарда только from:"*", пин rollback обязателен,
  поле apply_conflict = artifact_status, guard вне board_allowed,
  квалификаторы в док-литералы). N3m критик r7 — **ПРИНЯТЬ** (блокер
  закрыт сверкой матрицы; 2 замечания внесены). **ПЛАН ПРИНЯТ.**
  DoD-строка builder'у N4 (r7-замечание 2): при правке docs/06/07
  проверить литералы фабричного «любой → Blocked» для test-case на
  тот же квалификатор «кроме терминальных (Merged)».
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
  docs/06:98/229 **и :140-141 (листинг whitelist — литерал «любой →
  Review» дополняется квалификатором «кроме терминальных (Merged)»)**,
  **docs/07-board-inbound.md:97-100 (тот же квалификатор в :99)**,
  docs/templates/test-case.md (+секции Чекпойнты/Красная проба).
  Non-goals: rules.yaml, qa-loop SKILL.md, test-cases/**,
  framework/tests/**. Критик-вход диффа обязателен.
- N5 пилот-дизайн (designer, wip-лок) → **N5a Merged-переводы Lead
  (ДО кода)** → **N5b Approve оператора (борда)**.
- N6 пилот-код — очередь фабрики (B3→F1) + критик-вход цикла.
- N7 раскатка — корпус по общей фикстуре.
- N8 приёмка — Lead: метрика-протокол, журнал, HANDOFF.
