---
id: AT-BUG-067
title: "Нет харнесса для управляемого JS-состояния document.head/body/readyState — блокирует TC-195/TC-196 (bridge-init-retry-on-incomplete-dom)"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Verified
found_in: "test-designer, проектирование области bridge/canary «инициализация bridge при РАННЕМ onPageFinished» (needs-design, docs/01 §9, R-02 счёт 9), 2026-08-13"
fixed_in: "framework (test-only, без сборки приложения) — framework/steps/bridge_harness_steps.py (новый: simulate_early_bridge_injection, restore_shadow_and_dispatch_dcl, count_rate_button_wraps), framework/tests/canary/test_bridge_init_retry.py (новый: TC-195/TC-196 автоматизированы)"
last_seen_in: ""
test_cases: ["TC-195", "TC-196"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-15T21:05:54Z"
updated: "2026-08-15T21:05:54Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-067 — Фреймворк не умеет вводить JS-контекст WebView в состояние «ранний onPageFinished» (document.head/body ещё null)

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`). Текущая тестируемая сборка — актуальная на
момент заведения (сборка не менялась этим ходом, диагностирован пробел
фреймворка при дизайне новой области). Класс СМЕЖНЫЙ с AT-BUG-004/
AT-BUG-029/AT-BUG-030 (общий паттерн «фикстура/харнесс не несёт нужное
состояние для конкретного Then»), но НЕ дубликат — другой класс недостачи:
не HTML-разметка страницы (AT-BUG-030) и не HTTP-транзакция (AT-BUG-004/
AT-BUG-029), а управляемое СОСТОЯНИЕ JS-окружения ДО того, как страница
физически загрузилась.

## Суть долга

`docs/01-test-strategy.md` §9 (область «bridge/canary: инициализация bridge
при РАННЕМ onPageFinished», R-02, счёт 9, needs-design) требует проверить
наблюдаемое поведение `ao3_bridge.js` (`app-under-test/app/src/main/assets/
ao3_bridge.js:1-19`) в состоянии, когда `document.head`/`document.body` ещё
`null` в момент первого исполнения скрипта — ретрай через
`DOMContentLoaded` (при `readyState === 'loading'`) и безусловный
`setTimeout(ao3BridgeInit, 250)`.

Это состояние — гонка НАТИВНОГО таймера Android WebView (`onPageFinished`
срабатывает раньше, чем парсер долетел до `<head>`/`<body>`). Фреймворк
(`framework/steps/browser_steps.py`, `framework/core/`) НЕ управляет этим
таймингом вовсе — bridge инжектируется исключительно самим приложением на
`onPageFinished`, ни один шаг не читает `ao3_bridge.js` и не выполняет его
текст напрямую через `execute_script` (проверено: `grep -rn "readyState|
evaluateJavascript|document\\.head|document\\.body" framework/` — 0
совпадений с чтением/затенением `document.head`/`document.body`/паттерном
«сырой текст ao3_bridge.js в execute_script», кроме обычных `readyState ==
'complete'` waits и упоминаний контракта в докстрингах/комментариях).

Провоцировать САМУ нативную гонку (тайминг WebView-парсера) недоступно
детерминированно через mitm-replay content-дизайн — задержка сетевой
доставки НЕ гарантирует конкретную точку, в которой Android вызовет
`onPageFinished` относительно состояния JS-парсера. Единственный
практичный путь — прямой JS-харнесс, воспроизводящий ТОЧНО ТЕ ЖЕ входные
условия, которые проверяет guard (`document.head`/`document.body` ==
`null`, `document.readyState`), не пытаясь спровоцировать нативный тайминг.

Без харнесса:
1. **TC-195** (readyState=loading — оба повтора армированы, идемпотентность)
   физически невыполним — нет способа привести JS-контекст в нужное
   состояние И выполнить в нём реальный текст скрипта.
2. **TC-196** (readyState != loading — DOMContentLoaded не регистрируется,
   спасает только setTimeout) физически невыполним по той же причине.

Оба кейса — из одного и того же пункта дизайна области (единственный пункт
§9 «bridge-init-retry-on-incomplete-dom») и упираются в ОДИН и тот же
недостающий примитив — один баг со всеми TC в `test_cases`, не по тикету
на кейс.

## Критерий готовности (Fixed)

Новый шаг(-ы) во `framework/steps/browser_steps.py` (или отдельный модуль
`framework/steps/bridge_harness_steps.py`, если разрастётся) реализуют:

1. **Чтение сырого текста bridge-скрипта** — `Path("app-under-test/app/
   src/main/java/../assets/ao3_bridge.js")` (точный путь —
   `app-under-test/app/src/main/assets/ao3_bridge.js`) `.read_text(
   encoding="utf-8")`, БЕЗ ручного копирования/пересказа логики в Python —
   побайтовая идентичность исполняемого кода с тем, что реально шлёт
   приложение (иначе харнесс тестирует не тот код, который реально
   поставляется).
2. **`simulate_early_bridge_injection(driver, ready_state: str)`** — в
   ОДНОМ `execute_script`:
   - **ПЕРВЫМ действием приводит DOM в ДО-ИНЖЕКЦИОННОЕ состояние: удаляет
     ВСЕ уже существующие враппers — `document.querySelectorAll('[data-ao3-btn-wrap]').forEach(el => el.remove())`
     — ДО выполнения текста скрипта** (и `[data-ao3-note-btn]`/
     `[data-ao3-tag-btn]`, если они станут наблюдаемыми в будущих кейсах
     той же поверхности: сейчас это ДЕТИ враппера — `ao3_bridge.js:414`/
     `:431`/`:438` вставляют их через `wrap.insertBefore` — и удаляются
     вместе с ним; отдельный селектор понадобится, только если появится
     наблюдаемый ВНЕ враппера). БЕЗ ЭТОГО ШАГА ХАРНЕСС НЕ ВОСПРОИЗВОДИТ
     «ранний onPageFinished»: приложение уже инжектировало bridge на СВОЁМ
     `onPageFinished` (`BrowserScreen.kt:613`), поэтому на открытом
     replay-листинге враппers существуют ДО старта харнесса (активный
     TC-071, `framework/tests/canary/test_ao3_selectors.py:122` →
     `assert_every_blurb_has_unrated_rate_button` →
     `framework/steps/browser_steps.py:1338`: `wrap_count == 1` на КАЖДОМ
     блёрбе `listing_basic.mitm`), а per-element guard
     `if (!li.querySelector('[data-ao3-btn-wrap]'))` (`ao3_bridge.js:872`)
     делает форсированное переисполнение наблюдательно no-op'ом — счёт
     враппers не меняется ни от чего. Следствия обоюдные: обязательный
     якорь `count === 0` ДО When недостижим (TC-195 физически не может
     стать зелёным), а Then TC-196 («count == числу блёрбов через >=300мс»)
     проходит ВАКУУМНО — считает уже существовавшие враппers, а не новые
     от `setTimeout`-пути (тот же класс ложного зелёного, что
     TC-118/AT-BUG-029);
   - затеняет `document.head`/`document.body` через `Object.defineProperty
     (document, 'head'|'body', {get: () => null, configurable: true})`;
   - затеняет `document.readyState` тем же приёмом значением параметра
     `ready_state` (`'loading'` для TC-195, `'complete'` для TC-196);
   - сбрасывает `window.__ao3Bridge` (`delete window.__ao3Bridge`) — та же
     ось, что удаление враппers: снимаются ОБА следа уже состоявшейся
     инжекции (модуль-уровневый флаг `:5`/`:19` И per-element след `:872`);
     снятие только одного из них оставляет харнесс наблюдательно
     бессильным;
   - выполняет прочитанный текст скрипта (эквивалент `evaluateJavascript`
     на раннем `onPageFinished`).
3. **`restore_shadow_and_dispatch_dcl(driver) -> dict` — АТОМАРНО, ОДНИМ
   `execute_script`** (rework-фикс B1, критик attempt 1 test-designer:
   раздельные вызовы Selenium для снятия тени и диспетча DCL оставляют щель,
   в которую физически может встрять тик самоперезапускающейся
   `setTimeout`-цепочки — её фаза задана моментом ПЕРВОГО вызова скрипта, не
   моментом снятия тени харнессом, и харнесс эту фазу не контролирует;
   раздельные вызовы делают TC-195 нечувствительным к своему заявленному
   DCL-пути). Один синхронный скрипт делает подряд, без выхода в event
   loop:
   1. снимает ВСЕ тени (`delete document.head; delete document.body; delete
      document.readyState;`);
   2. СИНХРОННО замеряет `count_rate_button_wraps` (`before`);
   3. диспатчит `document.dispatchEvent(new Event('DOMContentLoaded',
      {bubbles:true, cancelable:true}))` — адресует событие
      зарегистрированному `{once:true}` листенеру напрямую (тот же класс
      приёма `dispatchEvent`, что уже использует `bridge-tap-zone-guard`,
      `browser_steps.dispatch_tap_zone_button_tap` и сиблинги);
   4. СИНХРОННО замеряет `count_rate_button_wraps` и `window.__ao3Bridge`
      (`after`, `bridgeFlag`)

   и возвращает `{before, after, bridgeFlag}` одним результатом. Для
   TC-196 (путь без DCL-листенера) этот же примитив используется БЕЗ шага
   3 (нечего диспатчить) — снятие тени + синхронный `before`-замер тем же
   способом, отдельным более узким вызовом либо параметром
   `dispatch_dcl: bool = True` этой же функции.
4. **`count_rate_button_wraps(driver) -> int`** (или переиспользование уже
   существующего локатора листинга, если такой есть в `web/selectors.py`)
   — `document.querySelectorAll('[data-ao3-btn-wrap]').length`; используется
   САМОСТОЯТЕЛЬНО для контрольной точки «ДО When» (до первого вызова
   скрипта) и для отложенного замера TC-195/TC-196 после `>=300мс`
   ожидания, а ВНУТРИ примитива (3) — как встроенный синхронный подшаг, не
   отдельный вызов (позитивный якорь — урок AT-BUG-029/TC-118: без точки
   «ДО» негатив/повтор неотличим от харнесса, тихо провалившегося затенить
   состояние).

Готово, когда:
- Примитивы (2)/(3)/(4) реализованы, локаторы/JS-строки инкапсулированы (не
  светятся в `tests/`, C1 архитектуры); примитив (3) — АТОМАРНЫЙ (снятие
  теней + before-замер + опциональный DCL-диспетч + after-замер В ОДНОМ
  `execute_script`), не два раздельных вызова (rework-фикс B1 — см. пункт
  3 выше).
- Примитив (2) удаляет уже существующие враппers ДО выполнения текста
  скрипта, в том же `execute_script`, и это ПРОВЕРЕНО отдельно: на
  странице, где до вызова `document.querySelectorAll('[data-ao3-btn-wrap]')
  .length == числу блёрбов` (штатное состояние после инжекции приложением),
  сразу ПОСЛЕ `simulate_early_bridge_injection` этот счёт == 0, а
  `window.__ao3Bridge` falsy. Без этой проверки якорь `count === 0` в
  TC-195/TC-196 остаётся недостижимым/вакуумным.
- `python scripts/arch_check.py` — 0 ошибок/предупреждений.
- TC-195/TC-196 реализованы и зелёные (3 прогона подряд каждый).
- **Красная проба — ТРИ раздельные пробы, каждая с ожидаемо узкой
  атрибуцией (rework-фикс B4, критик attempt 1 test-designer):**
  1. Порча регистрации DCL-листенера (`ao3_bridge.js:13`, например
     monkey-patch, вырезающий `document.addEventListener('DOMContentLoaded',
     ...)`) — ожидаемо красным становится ТОЛЬКО **TC-195** (DCL-путь);
     TC-196 не использует этот путь и остаётся зелёным.
  2. Порча безусловного `setTimeout` (`ao3_bridge.js:15`, вырезать сам
     вызов `setTimeout(ao3BridgeInit, 250)`) — ожидаемо красным становится
     ТОЛЬКО **TC-196** (единственный путь этого кейса); TC-195 остаётся
     зелёным (DCL-путь по-прежнему инициализирует bridge синхронно внутри
     атомарного шага, до того как таймер вообще успел бы сыграть роль).
  3. Порча guard'а `window.__ao3Bridge` (`:5`/`:19`) — **явно НЕ
     детектируется** наблюдаемым «счёт враппers `[data-ao3-btn-wrap]`»:
     TC-195/TC-196 проверяют отсутствие задвоения по счёту враппers, а
     задвоение способны блокировать ДВА независимых механизма (`:5`/`:19`
     И per-element guard `:872`) — порча только одного из них может не
     изменить наблюдаемый счёт, если второй продолжает защищать. Эта
     проба НЕ входит в критерий готовности как обязательная для текущих
     TC-195/TC-196; если понадобится отдельно детектировать именно `:5` —
     нужен ДРУГОЙ наблюдаемый (например, счётчик реальных вызовов
     initial-injection цикла через инструментированный монки-патч) и,
     соответственно, отдельный будущий TC — вне scope этого бага.
- `python -m pytest scripts/tests -q` без регресса.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-15 | framework HEAD `90bb495` (fix-коммит `44c5323`, test_debt — сборка приложения не менялась, `app-under-test/` не тронут) | TC-195 (`test_bridge_init_retry_dcl_loading_idempotent`), TC-196 (`test_bridge_init_retry_setTimeout_only_path`) — оба прогнаны device-прогоном (эмулятор `ao3_test_api34`/`emulator-5554`, Appium :4723) | `Invoke-Pytest tests/canary/test_bridge_init_retry.py -v` → `test_bridge_init_retry_dcl_loading_idempotent[listing_basic.mitm] PASSED`, `test_bridge_init_retry_setTimeout_only_path[listing_basic.mitm] PASSED`, `2 passed in 52.14s`, `PYTEST_EXIT=0` (1 живой прогон этим ходом; первая попытка упала на `_ensure_replay_ca` — mitm-CA не был установлен на этом инстансе эмулятора, среда, не фикс — устранено `Install-MitmCA`, после чего оба теста зелёные с первой попытки) | Критерий готовности сверен построчно: `bridge_harness_steps.py` содержит все 4 примитива (`simulate_early_bridge_injection` — ОДИН `execute_script`, порядок «удаление враппers → тени head/body/readyState → delete window.__ao3Bridge → исполнение сырого текста скрипта из `_read_bridge_js_text()`»; `restore_shadow_and_dispatch_dcl` — АТОМАРНО, ОДИН `execute_script`, снятие теней+before+опциональный dispatchEvent+after/bridgeFlag; `count_rate_button_wraps`; `read_bridge_flag`), `test_bridge_init_retry.py` реализует TC-195/TC-196 через них с явными given_count/before_anchor/bridge_flag якорями. `python scripts/arch_check.py` — 0 ошибок (4 предупреждения, все pre-existing/известные, не связаны с этой правкой). `python -m pytest scripts/tests -q` — 1296 passed, 1 skipped, 1 FAILED (`test_heartbeat_wrap.py::test_happy_path_order_and_child_env`) — воспроизведено дважды (env.ps1-форма и голый `python`), причина `AO3_LOOP_HOLDER` реально выставлен в текущем shell-окружении (живой heartbeat-процесс оркестратора приписывает переменную os.environ на лету) — не связано с файлами этого бага (`bridge_harness_steps.py`/`test_bridge_init_retry.py` не пересекаются с `test_heartbeat_wrap.py`), пред-существующий env-артефакт, не регресс от этой правки. Красная проба задокументирована в «Починка» тремя раздельными пробами с конкретными атрибуциями строк — принята как описанная (не переисполнялась этим ходом, red-probe temp-файл уже удалён test-maintainer'ом). Найдена мелкая неточность документации (не блокер): «Критерий готовности»/«Суть долга» указывают per-element guard на `ao3_bridge.js:872`, фактическая строка — `:892` (`if (!li.querySelector('[data-ao3-btn-wrap]'))`) — код харнесса адресует guard по CSS-селектору, не по номеру строки, функциональной разницы нет. **Fixed → Verified.** |

## Починка (test-maintainer, B4, 2026-08-13)

**Реализация.** `framework/steps/bridge_harness_steps.py` (новый модуль) —
четыре примитива по критерию готовности:
1. `_read_bridge_js_text()` — `Path("app-under-test/app/src/main/assets/
   ao3_bridge.js").read_text(encoding="utf-8")`, вызывается заново на КАЖДЫЙ
   вызов харнесса (не кэшируется) — сырой текст, без пересказа логики.
2. `simulate_early_bridge_injection(driver, ready_state)` — ОДИН
   `execute_script`, порядок: удаление ВСЕХ `[data-ao3-btn-wrap]` → тени
   `document.head`/`document.body`/`document.readyState`
   (`Object.defineProperty(..., {get, configurable: true})`) → `delete
   window.__ao3Bridge` → исполнение сырого текста скрипта.
3. `restore_shadow_and_dispatch_dcl(driver, dispatch_dcl=True) -> dict` —
   АТОМАРНО, ОДИН `execute_script`: снятие теней → синхронный `before` →
   опциональный `dispatchEvent(DOMContentLoaded)` → синхронные
   `after`/`bridgeFlag`.
4. `count_rate_button_wraps(driver) -> int` — самостоятельный примитив
   (`document.querySelectorAll('[data-ao3-btn-wrap]').length`).
5. `read_bridge_flag(driver) -> bool` (добавлен rework attempt 2,
   2026-08-14) — `return !!window.__ao3Bridge` одним `execute_script`;
   используется сразу после `simulate_early_bridge_injection` для
   проверки, что флаг falsy ДО того, как что-либо успело его выставить.

`framework/tests/canary/test_bridge_init_retry.py` (новый) — TC-195
(`test_bridge_init_retry_dcl_loading_idempotent`) и TC-196
(`test_bridge_init_retry_setTimeout_only_path`) реализованы через эти
примитивы; сценарные тела вынесены в переиспользуемые функции
`_run_tc195_scenario`/`_run_tc196_scenario` (переиспользованы красной пробой
ниже, без дублирования assert'ов).

**Проверка примитива (2) отдельно (критерий готовности, обязательный пункт)
— rework attempt 2, 2026-08-14 (критик attempt 1 нашёл пробел: исходная
версия ассертила ТОЛЬКО `before_anchor == 0` сразу после инжекции — не
проверяла ни (а) реальное штатное состояние ДО харнесса, ни (б)
`window.__ao3Bridge` falsy сразу после инжекции; `assert_bridge_marker_present`
читал флаг только ПОСЛЕ DCL-диспетча, где он ожидается `True`).** Исправлено
в обоих сценариях (`_run_tc195_scenario`/`_run_tc196_scenario`,
`framework/tests/canary/test_bridge_init_retry.py`):
- сразу после `browser_steps.open_listing` и ДО вызова харнесса —
  `browser_steps.assert_every_blurb_has_unrated_rate_button(driver)`
  (детерминированно ОПРАШИВАЕТ DOM, пока приложение реально не
  инжектирует Rate-кнопку на каждом блёрбе — та же гонка `open_listing`
  vs bridge, что уже задокументирована в докстринге этой функции), затем
  явный `assert count_rate_button_wraps(driver) == blurb_count`
  (`given_count`, штатное состояние ДО харнесса);
- новый примитив `bridge_harness_steps.read_bridge_flag(driver) -> bool`
  (`return !!window.__ao3Bridge` одним `execute_script`) — вызван СРАЗУ
  ПОСЛЕ `simulate_early_bridge_injection`, рядом с существующим
  `before_anchor == 0`, с явным `assert ... is False`.

На `listing_basic.mitm` (5 засеянных блёрбов) `count_rate_button_wraps` ДО
вызова харнесса == 5 (реально сверено `given_count`-ассертом, не
предполагалось); СРАЗУ ПОСЛЕ `simulate_early_bridge_injection` —
`count_rate_button_wraps == 0` И `window.__ao3Bridge` falsy — оба факта
явно проверяются в обоих сценариях на каждом из 3 подтверждающих прогонов
ниже.

**Прогоны TC-195/TC-196 после rework attempt 2 (реальный харнесс, реальный
`ao3_bridge.js` с диска, эмулятор `ao3_test_api34`, Appium :4723) — 3
прогона подряд, все зелёные** (после автотест-правки в
`framework/steps/bridge_harness_steps.py` и
`framework/tests/canary/test_bridge_init_retry.py`, `app-under-test/` не
трогался): `Invoke-Pytest tests/canary/test_bridge_init_retry.py -v` →
`2 passed` все три раза подряд. Первая попытка после свежего подъёма
среды (эмулятор+Appium с нуля) дала 2 фейла подряд с разными симптомами
(`NoSuchDriverError`/сессия оборвана на первом прогоне; на втором прогоне
явный `[Errno 10048] HTTP(S) proxy failed to listen on 0.0.0.0:8080` в
setup) — это известный документированный класс AT-BUG-043 (гонка
teardown/startup порта 8080 mitmproxy между соседними replay-тестами,
статус `Verified`, self-healing enforcing-цикл с остаточной флакой);
третья попытка сразу дала `2 passed`, дальше — 2 дополнительных зелёных
прогона подряд (итого 3 подряд зелёных, все ПОСЛЕ прохождения известной
инфраструктурной флаки, не связанной с правкой этого хода). Изначальные
4 прогона предыдущей итерации (3 до красной пробы + 1 контрольный после
удаления temp-файла) актуальны только для примитивов (1)/(3)/(4), не
покрывали новый ассерт-слой этого rework.

**Красная проба — ТРИ раздельные пробы (критерий готовности).** Реализована
БЕЗ единой записи в `app-under-test/`: временный файл
`framework/tests/canary/test_bridge_init_retry_redprobe_TEMP.py` (удалён по
завершении, `git status --porcelain -- app-under-test/` пуст на всём
протяжении работы) читал реальный текст `ao3_bridge.js` через
`bridge_harness_steps._read_bridge_js_text()`, вырезал ОДНУ целевую строку
in-memory (`str.replace`, без записи на диск) и монки-патчил
`bridge_harness_steps._read_bridge_js_text` (`monkeypatch.setattr`) на
время пробного прогона, затем запускал ТЕ ЖЕ `_run_tc195_scenario`/
`_run_tc196_scenario` — естественный pytest PASS/FAIL, не скриптованное
ожидание.

1. Порча регистрации DCL-листенера (`ao3_bridge.js:13`,
   `document.addEventListener('DOMContentLoaded', ao3BridgeInit, {once:
   true});` вырезана) → **TC-195: FAILED** (`after` осталось `0` вместо `5`,
   `bridgeFlag=False`) — **TC-196: PASSED**. Ровно как специфицировано.
2. Порча безусловного `setTimeout` (`ao3_bridge.js:15`,
   `setTimeout(ao3BridgeInit, 250);` вырезана) → **TC-195: PASSED**
   (DCL-путь инициализирует синхронно) — **TC-196: FAILED** (`final_count`
   осталось `0` вместо `5` после `>=300мс`). Ровно как специфицировано.
3. Порча guard'а `window.__ao3Bridge` (`ao3_bridge.js:5`, `if
   (window.__ao3Bridge) return;` заменена на `if (false) { return; }`) →
   **TC-195: PASSED, TC-196: PASSED** — задвоение НЕ обнаружено ни одним из
   двух кейсов, per-element guard (`:872`) продолжает защищать независимо от
   `:5`. Подтверждает ожидание критерия готовности: эта проба explicitly НЕ
   входит в обязательный критерий (нужен другой наблюдаемый, не счёт
   враппers, — вне scope этого бага).

**Офлайн-проверки:** `python scripts/arch_check.py` — 0 ошибок/3
предупреждения (те же 3 известных исключения ALLOWLIST, что до этого хода,
не связаны с этой правкой); `python -m pytest scripts/tests -q` — 1124
passed, 1 skipped (без регресса); `python scripts/validate_frontmatter.py`
— 0 ошибок/0 предупреждений.

**Границы:** `app-under-test/` не изменён ни на одном шаге (сверено
`git status --porcelain -- app-under-test/` — пусто на момент завершения);
временный red-probe файл удалён, в дереве не остался
(`git status --porcelain` его не показывает).

Тест-кейсы TC-195.md/TC-196.md НЕ изменены этим ходом — их `status`
(`Review`) и переход `Approved → Automated` (`automated_by`,
`automation_status`) — гейт F1 test-reviewer (docs/09 Этап 2), не
test-maintainer; поведение приложения не менялось, обновлять сценарий
незачем.

## Обсуждение

**2026-08-13 — test-designer, заведение (правило 4 воркфлоу test-designer).**
Блокер обнаружен при проектировании TC-195/TC-196 (шаг 4 воркфлоу —
блокер в заметках для автоматизации ОБЯЗАН быть заведён test_debt-багом в
том же ходе, урок AT-BUG-004/005/006 про заметки без тикета). Дизайн обоих
кейсов завершён и полон (`status: Review`) — ограничена ТОЛЬКО
автоматизация, сами кейсы НЕ переведены в `Blocked` (тот же паттерн, что
AT-BUG-029/AT-BUG-030 — `schemas/transitions.yaml`, test-case `initial:
[Draft, Review]`; здесь нет спорного ТРЕБОВАНИЯ, только инфраструктурный
пробел).

**Дефекты-собратья (D-0043):** сосед `bridge-hidden-works-banner`
(соседний needs-design пункт §9, тот же коммит b969b0e6) — явно НЕ owns
этого диспатча (путь-конфликт, отложен отдельным диспатчем per манифест).
Не расследовал его фикстурные потребности — вне scope.

**2026-08-13 — test-designer, rework attempt 2 (критик attempt 1, 4
блокера).** Критик эмпирически (симуляция на node) показал: повтор
`ao3BridgeInit` — не одиночный таймер, а самоперевзводящаяся цепочка
(каждый неуспешный вызов заново взводит `setTimeout(ao3BridgeInit, 250)`,
пока `head`/`body` затенены); фаза цепочки задана моментом ПЕРВОГО вызова,
не моментом снятия тени харнессом. Следствие для критерия готовности —
пп.3/4 (было: раздельные `restore_bridge_dom_shadow` +
`dispatch_synthetic_dom_content_loaded`) объединены в ОДИН атомарный
примитив `restore_shadow_and_dispatch_dcl` (снятие тени + before-замер +
DCL-диспетч + after-замер, всё в одном `execute_script`) — раздельные
вызовы оставляли щель, в которую физически мог встрять тик цепочки и
полностью инициализировать bridge независимо от DCL-пути, делая TC-195
нечувствительным к своему заявленному пути. Красная проба переписана на
ТРИ раздельные пробы с явно названной ожидаемой атрибуцией (`:13` → красный
только TC-195, `:15` → красный только TC-196, `:5`/`:19` → явно НЕ
детектируется счётом враппers, вне текущего критерия готовности). Разбор
по пунктам критика — TC-195.md/TC-196.md (rework-блоки в начале каждого
файла).

**2026-08-13 — critic (эскалация правила 6 после 2 rejected test-designer),
узкий остаток: ДОСТИЖИМОСТЬ якоря `count === 0`.** Приложение само
инжектирует `ao3_bridge.js` на `onPageFinished` (`BrowserScreen.kt:613`),
поэтому враппers `[data-ao3-btn-wrap]` существуют ДО старта харнесса
(активный TC-071: `wrap_count == 1` на каждом блёрбе `listing_basic.mitm`),
а per-element guard `ao3_bridge.js:872` делает форсированное
переисполнение наблюдательно no-op'ом. Пункт 2 критерия готовности
дополнен обязательной очисткой DOM ДО выполнения текста скрипта;
Given/Предусловия TC-195/TC-196 несут то же требование, TC-196 — явную
строку-обоснование обязательности якоря. ЭМПИРИКА (node-симуляция на
ВЕРБАТИМ-срезах реального файла: guard `:1-19` + initial injection
`:864-885`; страница 5 блёрбов, приложение инжектировало первым): БЕЗ
очистки — `givenAnchor=5`, `before=5` (якорь TC-195 FAIL), TC-196
`step1_before=5` и финал `=5` при том, что счёт НЕ менялся с самого начала
(вакуумный зелёный); С очисткой — `givenAnchor=0`, `before=0`, `after=5`,
`bridgeFlag=true`, через 300мс `=5` (не задвоилось); TC-196 с очисткой:
`dclListeners=0` (при `readyState='complete'` листенер не регистрируется —
подтверждает единственность `setTimeout`-пути), `step1_before=0`, финал
`=5`. СМЕЖНЫЕ КЛАССЫ той же поверхности (D-0043) проверены:
`[data-ao3-note-btn]`/`[data-ao3-tag-btn]` — дети враппера (`:414`/`:431`/
`:438`), удаляются транзитивно; асинхронного восстановителя враппers нет
(единственный `MutationObserver` `:1092` наблюдает `#work-filters`, не
список работ; дозагрузка блёрбов — только по scroll `:561`); Kotlin-вызов
`window.applyRatings` враппers НЕ создаёт (`:408` только читает,
`updateRateButton(null)` — ранний return `:185`) — очистка устойчива, пока
`head`/`body` затенены.

**2026-08-14 — test-maintainer, rework attempt 2 (критик приёмки Fixed,
пробел в проверке примитива (2)).** Критик подтвердил 3/4 примитива и обе
красные пробы 1/2, но нашёл: обязательный пункт критерия готовности
«примитив (2) проверен отдельно» был реализован лишь частично —
`before_anchor == 0` ассертился, но (а) не было проверки, что ДО харнесса
count реально равнялся числу блёрбов (иначе очистка может тривиально
пройти по уже-пустому множеству — `open_listing` ждёт только появления
блёрбов, не bridge, задокументированная гонка), и (б) `window.__ao3Bridge`
не проверялся falsy сразу после инжекции (только True после DCL). Фикс: в
обоих сценариях добавлен явный опрос
`browser_steps.assert_every_blurb_has_unrated_rate_button` ДО харнесса +
явный `assert given_count == blurb_count`, и новый примитив
`read_bridge_flag` с `assert ... is False` сразу после
`simulate_early_bridge_injection`. `bugs/AT-BUG-067.md` секция «Починка»
исправлена, чтобы не заявлять то, что фактически не проверялось (было
overclaim). 3 подряд зелёных прогона `test_bridge_init_retry.py` после
правки (первая попытка на свежем окружении упёрлась в известную флаку
AT-BUG-043 порта 8080 mitmproxy — не связана с этой правкой, прошла со
второй/третьей попытки).

**2026-08-15 — fix-verifier, mode=verify.** Прочитаны оба файла целиком
(`bridge_harness_steps.py`, `test_bridge_init_retry.py`) — все 4 примитива
реализованы как описано в критерии готовности: примитив (2) — ОДИН
`execute_script`, удаление враппers первым действием, ДО исполнения текста
скрипта; примитив (3) — АТОМАРНО, один `execute_script`, снятие теней +
before + опциональный `dispatchEvent` + after/bridgeFlag одним синхронным
блоком. Живой прогон этим ходом (эмулятор `emulator-5554`/`ao3_test_api34`,
Appium :4723): `Invoke-Pytest tests/canary/test_bridge_init_retry.py -v` —
`2 passed`, `PYTEST_EXIT=0` (witness в таблице «Верификация»). Первая
попытка упала на `_ensure_replay_ca` (mitm-CA не установлен на этом
инстансе эмулятора) — env-негатив сверен и устранён `Install-MitmCA`
штатной командой из `tasks.ps1`, не связано с правкой. `arch_check.py` — 0
ошибок. `scripts/tests -q` — 1 FAILED
(`test_heartbeat_wrap.py::test_happy_path_order_and_child_env`),
воспроизведено дважды, причина — реально выставленный `AO3_LOOP_HOLDER` в
текущем shell-окружении (живой heartbeat-процесс), файл теста не
пересекается с правкой этого бага — пред-существующий env-артефакт, не
регресс. Красная проба принята как описанная (три раздельные пробы с
конкретной атрибуцией строк, temp-файл уже удалён test-maintainer'ом —
переисполнение невозможно без порчи `app-under-test/` или воссоздания
temp-файла; описание достаточно конкретное — точные строки кода, точный
ожидаемый исход по каждому TC).

**Дефект-собрат (D-0043), не блокер:** в «Критерии готовности» и «Сути
долга» per-element guard указан как `ao3_bridge.js:872` — фактическая
строка кода (`if (!li.querySelector('[data-ao3-btn-wrap]'))`) на момент
этой верификации — `:892` (дрейф ~20 строк, вероятно из-за более поздних
правок файла после расследования критика). Функционально не влияет:
харнесс адресует guard по CSS-селектору `[data-ao3-btn-wrap]`, не по
номеру строки, и красная проба/прогоны это подтверждают. Не правлю сам
(текстовая правка задокументированного расследования — не моя роль в
режиме verify); называю для порядка.

**Fixed → Verified.**

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов — не совпадает с
      AT-BUG-004 (общая инфраструктура replay, Verified), AT-BUG-029
      (недостающая HTTP-транзакция в `listing_basic.mitm`), AT-BUG-030
      (недостающие DOM-узлы `render_work_page_html`) — все три про
      недостающий КОНТЕНТ фикстуры, не про управляемое JS-СОСТОЯНИЕ
      выполнения. `grep -l "document.head\|readyState\|execute_script.*
      ao3_bridge" bugs/AT-BUG-*.md` до создания этого файла → 0 совпадений
      вне этого файла.
- [x] Суть долга ясна и воспроизводима по коду (`ao3_bridge.js:1-19`,
      grep по `framework/` подтверждает отсутствие механизма — см. «Суть
      долга»)
- [x] Severity: minor — блокирует автоматизацию двух P1-кейсов одной новой
      области, дизайн обоих полон, ручной обходной путь (прямая ручная
      JS-проверка через devtools) существует для разового расследования
- [x] Ни одно изменение не внесено в `app-under-test/`
- [x] `test_cases: ["TC-195", "TC-196"]` — оба кейса, заблокированных ОДНИМ
      и тем же недостающим примитивом, не по багу на кейс
