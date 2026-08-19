# П2: пирамида как политика + bridge-слой без эмулятора (spec-p2-pyramid v4)

Слово оператора 2026-08-16: пирамида по референсу «D:\EPAM QA factory\
test-factory-blueprint.html» §05; дарк-фактори; «не для каждого теста
должен быть нужен эмулятор». П1+П2 утверждены, П3 после.

v4 — правки по критик-раунду 3 (2 блокера DAG-слоя + 5 сборочных;
существо Р1–Р5 подтверждено r3). Статус: **план принят; N4 посажен
2026-08-16 (p1p2-N4-batch-build), N5 посажен 2026-08-19 (критик-раунд
4 блокера → ретрай attempt 2 → принят Lead Fable, журнал task_id
p2-n5-bridge-harness)**. Автор: Lead (Fable). «Оператор в петле» —
информирован.

## Факты (r1 — эмпирика критика, принята)

1. Ядро кандидатов ИСПОЛНЕНО в jsdom 29.1.1 против наших фикстур
   (~150 мс init): applyRatings (бейджи/SVG/note/tag/подсветка),
   applyAllFilters (hide/dim различимы), getWorkData (payload точный),
   пагинация (скрытие номерных li), rateWork-клик с 7 аргументами.
   MutationObserver/DOMParser/localStorage/getComputedStyle есть;
   fetch/IntersectionObserver/navigator.clipboard/execCommand/
   requestAnimationFrame — НЕТ.
2. **Layout fail-OPEN:** getBoundingClientRect() всюду нули → scroll-
   гейтированные ветки (infinite-scroll append, auto-READ
   onWorkFinished) срабатывают на ЛЮБОМ scroll — тест такой ветки
   зелёный, не проверяя ничего.
3. `tools/` ЦЕЛИКОМ в .gitignore:2 (git check-ignore подтверждён;
   урок t-155 в самом .gitignore) — дом harness'а там нелегален.
4. `render_work_page_html` не несёт dd.relationship/dd.freeform —
   onWorkPageInfo отдаёт `"[]","[]"` (остаток класса AT-BUG-074).
5. Фильтр-форма (#work-filters, include/exclude_relationship_tags)
   живёт ТОЛЬКО в записанной sort_filter_form.mitm, не в генерируемых
   фикстурах.
6. Subprocess node из venv-python: локаль cp1251, node пишет UTF-8 —
   `text=True` без encoding даёт ТИХУЮ порчу кириллицы при успешном
   json.loads; node.exe в пути с пробелом. Прецедента node-вызова из
   python в репо нет. `tasks.ps1:346-391 Stop-NodeProcesses` убивает
   node-процессы по матчу $root — заденет harness.
7. Схема: опциональное `layer` (enum) не красит 257 кейсов —
   ПРОВЕРЕНО патченной копией (0 ошибок 0 предупреждений); `layer: ""`
   проходит валидатор молча — F1-чек обязан требовать «непусто И в
   enum».
8. qa-loop SKILL.md:250-266: test-automator/test-reviewer — device-класс
   БЕЗУСЛОВНО → L2-диспатчи сериализуются за эмулятором, выгода
   очереди без правки не реализуется.
9. Маркеры юнит-проб сейчас: p0:0 / p1:99 / p2:104; regression =
   `-m "p0 or p1"`, smoke = `-m p0`.

## Решения

### Р1. Политика слоёв в docs/01 (+ поле в кейсе)

Слои: L1 unit (дев; аудит — отдельная программа, non-goal, строка в
очередь Lead) / **L2 bridge** (device-free) / L3 e2e-replay / L4
e2e-live / L5 manual-agent+exploratory. Правило явного решения: НОВЫЙ
кейс несёт `layer`; для L3/L4 — строка «почему не L2». L1 в enum
отсутствует ОБОСНОВАННО (строка в docs/01): QA-кейс существует ⇒ это
не unit разработчика; L1-намерение = вопрос разработчику, не кейс.
Enforcement:
- schema: `layer` опциональный enum [L2,L3,L4,L5] (проверено — старые
  кейсы не краснеют; порядок правок схема/кейсы некритичен: WARN);
- F1: для нового/переработанного кейса — «`layer` НЕПУСТО И в enum»
  (пустая строка проходит валидатор молча — гейт держит F1) +
  обоснование «почему не ниже».
**Suite-маркер L2 = p1** (решение Lead): smoke (p0) остаётся чисто
девайсным 49/49; L2 и контракт-тесты едут в regression; база счёта
метрик — см. Р5.

### Р2. Контракт-слой записей (класс AT-BUG-074 системно)

Реестр `framework/data/bridge_selectors.py`: селектор → функции бриджа →
какие страницы обязаны нести узел. Покрытие: генерируемые фикстуры И
**записанные .mitm** (факт 5 — sort_filter_form.mitm в реестре). Два
теста (device-free): (1) каждый селектор реестра встречается в
ao3_bridge.js — детектор переименования/удаления; **односторонний:
НОВЫЙ селектор бриджа не ловится** (явная строка; компенсация —
impact-map: ao3_bridge.js в wide_impact, любая правка бриджа = полная
регрессия + F1 новых bridge-тестов); (2) каждая страница несёт узлы
заявленных на неё селекторов. **Динамически собираемые селекторы
(`label[for=…]`, `'work_'+id`) — вне скоупа реестра** (явная строка).

### Р3. Bridge-harness: Node + jsdom, дом `framework/bridge_harness/`

- **Дом — версионируемый** (B1: tools/ в .gitignore): package.json +
  package-lock.json коммитятся; `framework/bridge_harness/node_modules/`
  — строка в .gitignore; подкаталоги harness'а НЕ называть `tools`
  (bare-pattern .gitignore:2 бьёт на любой глубине — класс t-155).
  Единственная прод-зависимость — jsdom.
- **Bootstrap (B7):** функция `Ensure-BridgeHarness` в
  scripts/tasks.ps1 — НОВАЯ логика (`npm ci` в framework/bridge_harness
  при отсутствии node_modules; образца npm-ci в репо НЕТ: Start-Appium
  (:327-344) зависимостей не ставит, :353-356 — комментарий внутри
  Stop-NodeProcesses); строка в docs/02 и в онбординге docs/12.
  Отсутствие node/jsdom при p1-прогоне = **ЖЁСТКИЙ отказ** с
  сообщением-инструкцией — не молчаливый skip (конвейер однохостовый,
  установка — шаг онбординга). DoD N5: свежий клон →
  Ensure-BridgeHarness → зелёный bridge-прогон.
  **Вся harness-инфраструктура — ОДИН дом, узел N5** (r3):
  Ensure-BridgeHarness + Stop-NodeProcesses-исключение + строка
  .gitignore (node_modules) — owns N5, НЕ N4; witness исключения
  (`Get-CimInstance Win32_Process` при живом harness) — DoD N5.
- Механика: `runScripts:"outside-only"` (проверено), fixture-HTML из
  recording_builder/записей, мок `window.Android` (Proxy-рекордер) +
  **стабы объявленным контрактом**: `fetch` (управляемые ответы для
  пагинации), `navigator.clipboard.writeText` (управляемый
  resolve/reject), `document.execCommand` (управляемый bool),
  `peekScrollRestore` → 0 по умолчанию (3000 добавляет ~3с ретраев).
  Оговорка в норме: clipboard-тесты проверяют **JS-фолбэк бриджа, не
  поведение WebView** (класс BUG-071 — guard, порядок веток).
- **Fail-open границы (B4):** формулировка нормы — «layout-гейты в
  jsdom ИНВЕРТИРУЮТСЯ (нулевая геометрия делает их проходимыми)»;
  ЗАПРЕТ ассертов на layout-гейтированных ветках (infinite-scroll
  append-триггер, auto-READ по scrollY/rect) — они остаются L3;
  harness несёт **канарейку нулевого layout** (тест, УТВЕРЖДАЮЩИЙ
  rect==0/scrollHeight==0 — если jsdom однажды получит layout,
  канарейка упадёт и границы пересматриваются осознанно).
- Тесты — pytest `framework/tests/bridge/` с ЛОКАЛЬНЫМ conftest
  (единое no-op переопределение _ensure_app_installed на слой — вместо
  копии в каждом файле; arch_check.rglob гейты не обходятся —
  проверено r1). Subprocess-протокол (факт 6, класс AT-BUG-079):
  list-argv, shell=False, абсолютные пути, данные через файл/stdin (не
  argv), `encoding="utf-8"` обязателен, **кириллическая канарейка в
  протоколе**, timeout, внятный отказ при отсутствии node/jsdom.
- Кандидаты пилота (эмпирически подтверждены): applyRatings-бейджи,
  applyAllFilters, getWorkData; +clipboard-guard со стаб-контрактом;
  +**персистентность main-pairing через localStorage** (находка r1 —
  работает в jsdom; требует фикстуры фильтр-формы из
  sort_filter_form.mitm). onWorkPageInfo — после Р2-фикса фикстуры
  (см. owns). НЕ кандидаты: infinite-scroll append, auto-READ, scroll-
  restore (layout/scroll).
- **Фикстуры дорабатываются тем же этапом**: `render_work_page_html`
  расширяется узлами dd.relationship/dd.freeform — значения ЛИТЕРАЛАМИ
  по образцу _blurb_html (recording_builder.py:321-322; у Work таких
  полей нет — works.py НЕ трогать) — закрывает факт 4 и остаток класса
  AT-BUG-074. **Перегенерация записей — того же узла (B9):**
  `scripts/build_replay_recordings.py` и
  `framework/data/recordings/*.mitm` (9 версионируемых) — в owns N5;
  DoD: перегенерация, коммит .mitm, зелёный test_recording_builder_unit
  (иначе запись дрейфует от генератора — класс AT-BUG-054).
- **Маркер `bridge` (B11):** bridge-тесты несут `@pytest.mark.bridge`
  (+p1; регистрация в pytest.ini). Регрессия run-suite ВКЛЮЧАЕТ их
  (p1); **метрики времени device-слоя (протокол Р5 и П1 N8) считаются
  фильтром `-m "(p0 or p1) and not bridge"`** — база счёта не
  загрязняется. run-suite SKILL.md — правка одной строкой (ось в (б)).
- **Clipboard (n2):** L2-clipboard-тест — ДОПОЛНЕНИЕ, не перенос:
  device-покрытие класса BUG-071 остаётся L3/L4, раскатка N7 его не
  снимает.

### Р4. Нормы в промпты (координация с П1)

test-designer: **порядок норм записан (B6): «сначала СЛОЙ, потом дедуп
ВНУТРИ слоя; journey НЕ склеивает через границу слоёв»**. test-automator:
bridge-протокол + красная проба мутацией fixture-HTML. F1: чеки layer
(«непусто И в enum») + «почему не ниже» + **чек «bridge-тест не
ассертит ветку под layout-гейтом» (B10 — дом запрета; список
гейтированных веток — в норме docs/02)** + канарейки.
**Общий батч с П1 N4 расширен (B8): промпты + schemas/test-case.
schema.yaml + scripts/validate_frontmatter.py (+тесты) + docs/02 —
ЕДИНЫЙ диспатч N4 обоих планов, склейка Lead** (П1 v3 объявил то же —
коллизия снята). Строка взаимной зависимости в p1-e2e-dedup.md — дом
ОДИН: узел N8 (путь p1-файла в owns N8).

### Р5. Явные N/A и правки конвейера (B5)

- **qa-loop SKILL.md:250-266 (owns):** правка — УТОЧНЕНИЕ
  существующего перечня (строка :259 «классифицируй по содержанию
  диспатча» уже есть — не спорить с ней, а дополнить примером):
  диспатч по кейсу layer=L2/маркеру bridge — документный класс, не
  device. Без этого выгода очереди не реализуется (факт 8).
- **tasks.ps1 Stop-NodeProcesses (owns N5, см. Р3):** исключение
  harness-процессов по подстроке `bridge_harness` в CommandLine
  (матч :379 по $root — bridge_harness лежит под ним, исключение
  обязательно); DoD N5: entrypoint — файл ВНУТРИ
  framework/bridge_harness/, запуск абсолютным путём + witness
  `Get-CimInstance Win32_Process` при живом harness.
- N/A (явные строки): state/impact-map.yaml — ao3_bridge.js остаётся
  wide_impact до раскатки L2 (сужение — отдельное решение после N7);
  schemas/run.schema.yaml — не правится, но протокол метрики N7
  фиксирует: сравнение времени прогонов — литерально
  `-m "(p0 or p1) and not bridge"` (нормативна формула; p1 содержит
  и юнит-пробы — они в базе остаются, вычитается только bridge);
  rules.yaml — не правится (условия читают status/automated_by/review —
  layer не нужен; проверено r1).

## Четыре вопроса F-11

- **(а) Стоимость:** поддержка harness'а и реестра (обновление при
  правках бриджа — и это детектор, не только цена); designer думает о
  слое; node-пакет в дереве репо. Окупается: секунды vs 30–130 с/тест,
  автоматизация без очереди на девайс.
- **(б) Оси перечислением:** docs/01 (политика) ↔ schema+validate
  (layer) ↔ промпты (designer/automator/reviewer — батч с П1, порядок
  норм) ↔ framework/tests/bridge/** (+локальный conftest) ↔
  framework/bridge_harness/** ↔ framework/data (bridge_selectors,
  recording_builder) ↔ **.claude/skills/qa-loop/SKILL.md** (layer-aware
  классификация) ↔ **scripts/tasks.ps1** (Stop-NodeProcesses) ↔
  .gitignore (node_modules) ↔ docs/02 ↔ **docs/12 (онбординг —
  строка Ensure-BridgeHarness)** ↔ app-under-test/ao3_bridge.js
  (только чтение) ↔ N/A: impact-map.yaml, run.schema.yaml, rules.yaml
  (со строками-обоснованиями, Р5). Коммиты — механизменные (осевой
  блок + tier).
- **(в) Детекторы:** контракт-тесты Р2 — маркеры **p1 + bridge** → в
  каждом regression-прогоне (и вычитаются из device-метрики тем же
  маркером); канарейка нулевого layout; кириллическая канарейка
  протокола; F1-чеки layer + **чек «bridge-тест не ассертит ветку под
  layout-гейтом» (B10)**; красные пробы bridge-тестов; чек 8
  калибровки OS.
- **(г) Не даёт пропустить:** validate (enum layer), контракт-тесты и
  канарейки — код на пути прогона. На дисциплине (с named-детекторами):
  F1-чеки — промптовая дисциплина ревьюера, детектор её утечки — чек 8
  калибровки; выбор слоя designer'ом (ловит F1); односторонность
  реестра (компенсация wide_impact).

## DAG

- N1 recon — done/accepted. N2 v1 → r1 ДОРАБОТАТЬ. N3b v2 → r2
  ДОРАБОТАТЬ (B7–B11, журнал 11:48Z).
- **N3d v3** — этот файл — done. **N3e** — done (план принят, журнал
  N4 delegated/accepted 2026-08-16).
- **N4** — done/accepted 2026-08-16 (p1p2-N4-batch-build).
- **N5** — **done/accepted 2026-08-19** (критик-вход: 4 блокера с
  живыми witness → ретрай attempt 2 → независимые зонды Lead, принят;
  25 bridge-тестов зелёные device-free; witness жнец-исключения —
  инцидент 2026-08-19T00:17:56, правило 4 расширено коммитом 2643bab).
- **N4 политика+схема+нормы** — builder, единый батч с П1 N4 (склейка
  Lead; правило склейки: **owns побеждает non-goal** — qa-loop
  SKILL.md для П1 non-goal, для П2 owns → в склейке owns; скоуп =
  объединение owns).
  Owns: docs/01, docs/02, schema+validate_frontmatter (+тесты),
  промпты test-*, qa-loop SKILL.md (:250-266 layer-aware). БЕЗ
  tasks.ps1/.gitignore (дом — N5, r3-блокер 1).
- **N5 harness MVP + пилот** — builder: framework/bridge_harness/**,
  framework/tests/bridge/** (+conftest), framework/data/
  bridge_selectors.py, **framework/data/recording_builder.py**
  (dd.relationship/dd.freeform литералами),
  **scripts/build_replay_recordings.py + framework/data/recordings/
  *.mitm (перегенерация, B9)**, scripts/tasks.ps1
  (Ensure-BridgeHarness + Stop-NodeProcesses-исключение),
  **.gitignore** (node_modules — дом здесь, N4 отказался),
  framework/pytest.ini (маркер bridge), пилотные тесты (бейджи,
  фильтры, getWorkData, clipboard-стаб, localStorage main-pairing) +
  обе канарейки + красные пробы. Критик-вход обязателен.
- **N6 контракт-слой** — builder (исполнитель назван), критик-вход
  обязателен, **строго ПОСЛЕ N5, не параллельно** (общие
  bridge_selectors.py и framework/tests/bridge/). Owns:
  framework/tests/bridge/test_contract_*.py (тот же дом bridge/ с
  локальным conftest), framework/data/bridge_selectors.py (доводка
  реестра под записанные страницы). Маркеры: **p1 + bridge**.
- N7 раскатка переносов — designer/automator конвейерно; метрика:
  протокол Р5.
- N8 приёмка — Lead: журнал, HANDOFF, очередь «аудит L1 unit-слоя»,
  правка p1-e2e-dedup.md ДВУМЯ частями (owns N8, единственный дом,
  D-0080 4а): строка взаимной зависимости N4 И литеральная формула
  метрики `-m "(p0 or p1) and not bridge"` в протокол П1 N8.
