---
key: "TC-285"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "ao3ScrollToPercent прыгает к позиции по ПРОЦЕНТУ (не пикселям) и ретраит до 5 раз, пока контент дорастает; при scrollable==0 прыжка нет вовсе, вне страницы работы функции не существует"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-18"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-21T02:20:32Z"
updated: "2026-08-21T02:20:32Z"
archived: false
resolution: null
---

# ao3ScrollToPercent прыгает к позиции по ПРОЦЕНТУ (не пикселям) и ретраит до 5 раз, пока контент дорастает; при scrollable==0 прыжка нет вовсе, вне страницы работы функции не существует

_Спроецировано из `test-cases/browser/TC-285.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-285 — ao3ScrollToPercent: 0 вызовов scrollTo при scrollable==0 (даже все 5 попыток), 5 идентично-корректных вызовов при scrollable>0, функция отсутствует вне work-страницы

## Предусловия
- L2 bridge-harness (`framework/tests/bridge/`, фикстура `bridge_call`),
  маркер `@pytest.mark.bridge`.
- Фикстуры — `recording_builder.render_work_page_html(W.LOVED)` (work-
  страница, `chapter_titles` не важен для этой записи) и
  `render_listing_html([W.LOVED])` (не-work-страница) — литералами
  внутри теста.
- `request.url` для work-страницы — `https://archiveofourown.org/works/900000001`;
  для листинга — дефолтный `https://archiveofourown.org/works`.
- Каждая ветка — ОТДЕЛЬНЫЙ `bridge_call` (свежий jsdom-документ на
  ветку): геометрия (`document.body.scrollHeight`) и подмена
  `window.scrollTo` не должны переживать между ветками — независимость
  веток проще ДВУХ/ТРЁХ отдельных запросов, чем сброс состояния внутри
  одного (тот же принцип, что «два РАЗНЫХ `bridge_call`» в заметках
  TC-260 про `_didAutoAdvance`).

## Сценарий (Given-When-Then)

**Given** (Branch A — обязательная граница `scrollable==0`) work-
страница, `document.body.scrollHeight` НЕ затенён (дефолтный jsdom-ноль,
`test_layout_fail_open_canary.py`-подтверждённое B4-поведение —
`scrollable=Math.max(0, 0-innerHeight)=0`), `window.scrollTo` подменён
на счётчик-рекордер, `window.setTimeout` подменён на СИНХРОННЫЙ
немедленный вызов (чтобы отработали ВСЕ 5 попыток `attempt()`, не
только первая синхронная)

**When** `window.ao3ScrollToPercent(50)` вызван

**Then** счётчик `window.scrollTo` == 0 ЗА ВСЕ 5 попыток (не только за
первую синхронную) — при `scrollable<=0` guard `if (scrollable>0)`
никогда не берёт `true`-ветку, независимо от того, сколько раз
`attempt()` перевзведён

---

**Given** (Branch B — позитив: высокая страница, точная позиция, полный
цикл ретраев) work-страница, `document.body.scrollHeight` затенён
через `Object.defineProperty` на `4000` (управляемая непустая
геометрия, тот же приём, что уже принят `test_layout_fail_open_canary.
py`/TC-260/TC-263), `window.scrollTo` подменён на счётчик-рекордер,
`window.setTimeout` подменён на синхронный немедленный вызов

**When** `window.ao3ScrollToPercent(50)` вызван

**Then** `window.scrollTo` вызван РОВНО 5 раз (`tries` от `0` до `5`,
цикл `if (++tries<5) setTimeout(attempt,200)` перевзводится 4 раза
после первого синхронного вызова — итого 5 попыток), КАЖДЫЙ вызов —
`args == [0, Math.round((4000-innerHeight)*0.5)]` (`innerHeight`
читается ДИНАМИЧЕСКИ отдельным action'ом, не хардкодится) — все пять
попыток целятся в ОДНУ И ТУ ЖЕ позицию (геометрия здесь постоянна,
идемпотентный повтор, не дрейф)

---

**Given** (Branch C — функция вне work-страницы) листинговая страница
(НЕ work-страница) загружена бриджем

**Then** `typeof window.ao3ScrollToPercent === 'undefined'` — функция
физически ОТСУТСТВУЕТ (не просто no-op), подтверждает, что Kotlin-guard
`window.ao3ScrollToPercent && …` действительно необходим (без него —
`ReferenceError`, не тихий no-op)

**Инвариант:** значение процента (`pct`) отображается в ОДНУ И ТУ ЖЕ
относительную позицию (`scrollable * pct/100`) НЕЗАВИСИМО от конкретных
`scrollHeight`/`innerHeight` — только от их РАЗНОСТИ (`scrollable`),
поэтому позиция, снятая на другом экране/шрифте, воспроизводится
корректно (ради этого свойства функция вообще оперирует процентами, а
не пикселями, docs/01 п.2); при `scrollable<=0` функция гарантированно
НЕ действует ни на одной из своих ретрай-попыток, независимо от
переданного `pct`.

## Проверяемые данные
| Ветка | `window.scrollTo` вызовов | Аргументы |
|---|---|---|
| A (`scrollable==0`, все 5 попыток) | 0 | — |
| B (`scrollable=4000-innerHeight>0`) | 5 | `[0, round((4000-innerHeight)*0.5)]` на КАЖДЫЙ вызов |
| D (не work-страница) | функция не определена | `typeof === 'undefined'` |

## Заметки для автоматизации
- Инфраструктура уже принята и зелёная (N5/N6). Блокера нет.
- **Пограничное решение для F1/B10-гейта test-reviewer (ПРОЧИТАТЬ перед
  ревью, тот же водораздел, что в TC-284).** `docs/tasks/p2-pyramid-
  bridge.md` Р3 исключает из L2-кандидатов «scroll-restore» — это ссылка
  на ДРУГОЙ, пиксельный механизм `ao3_bridge.js:1205-1230`
  (`window.__ao3ScrollRestore`/`Android.peekScrollRestore()`,
  срабатывает АВТОМАТИЧЕСКИ при загрузке non-listing страницы), НЕ
  `window.ao3ScrollToPercent` этого кейса (процентный, вызывается
  ЯВНО Kotlin'ом ПО ДЕЙСТВИЮ пользователя — снекбар «Resume reading»,
  `browse-resume-offer-snackbar`). `request.peekScrollRestore` не
  задаётся (дефолт `0`) — держит `:1212-1230` неактивным, witness в
  предусловиях, не даёт ДВУМ механизмам интерферировать через общий
  `window.scrollTo`.
  Branch A — НЕ fail-open тавтология запрещённого класса (append/
  auto-READ): там негатив вакуумен, потому что ЕДИНСТВЕННЫЙ способ
  получить `scrollable<=0` — это НЕВОЗМОЖНОСТЬ jsdom считать layout
  (guard недостижим В ПРИНЦИПЕ иначе). Здесь `scrollable==0` — ИМЕННО
  ТА граница, которую сам код документирует и обрабатывает ЯВНО
  (`Math.max(0, ...)`, отдельная ветка `if (scrollable>0)`), а B4-ноль
  jsdom СОВПАДАЕТ с этим реальным продуктовым состоянием (короткая
  глава/страница ещё не отрендерилась) — граница подтверждается
  КОНТРАСТОМ с Branch B на ТОЙ ЖЕ функции: тот же код, единственная
  переменная — заданная геометрия — переключает результат с 0 на 5
  вызовов (наблюдаемость негативного Then, F-34).
- Синхронный патч `window.setTimeout` — легитимная харнесс-техника
  (прецедент: подмена `Element.prototype.getBoundingClientRect` в
  `test_layout_fail_open_canary.py`, `Location.prototype.replace` в
  TC-260/TC-263) — заменяет РЕАЛЬНОЕ ожидание 5×200мс детерминированной
  синхронной рекурсией, не требуя от харнесса (`flushMicrotasksAndTimers`
  — один тик `setTimeout(0)`) ждать отложенные таймеры дольше одного
  тика.
- Action-последовательности (порядок ОБЯЗАТЕЛЕН — подмена ПЕРЕД вызовом
  `ao3ScrollToPercent`):
  - Branch A: `{"id":"patchTimers","type":"eval","code":"window.setTimeout=function(fn){fn();return 0;};'patched'"}`,
    `{"id":"spyScroll","type":"eval","code":"window.__scrollToCalls=[];window.scrollTo=function(x,y){window.__scrollToCalls.push([x,y]);};'spied'"}`,
    `{"id":"jump","type":"eval","code":"window.ao3ScrollToPercent(50);'called'"}`,
    `{"id":"calls","type":"eval","code":"JSON.stringify(window.__scrollToCalls)"}` — ассерт: `json.loads(calls)==[]`.
  - Branch B: `{"id":"shadowScrollHeight","type":"eval","code":"Object.defineProperty(document.body,'scrollHeight',{get:function(){return 4000;},configurable:true});'shadowed'"}`,
    затем `patchTimers`/`spyScroll` как в Branch A,
    `{"id":"innerHeightProbe","type":"eval","code":"window.innerHeight"}`,
    `{"id":"jump", ...}`, `{"id":"calls", ...}` — ассерт: `len(json.loads(calls))==5` И
    каждый элемент `== [0, round((4000-innerHeight)*0.5)]` (Python
    `round`, банковское округление; при необходимости сверить с JS
    `Math.round` на `.5`-границах — здесь `(4000-innerHeight)*0.5`
    маловероятно ровно на `.5`, но автоматизатору стоит явно
    воспроизвести JS-семантику `Math.round`, не слепо доверять Python
    `round()`).
  - Branch C: `{"id":"typeofJump","type":"eval","code":"typeof window.ao3ScrollToPercent"}` — ассерт: `== "undefined"`.
- Батарея правил-реакций: **off-инвариант** — покрыт Branch A
  (`scrollable==0` — явный «эффекта нет» негатив) И Branch C (вне
  work-страницы — функции нет вовсе, ДВА разных «off»-состояния явно
  различены, не смешаны в одно); **идемпотентность** — покрыт Branch B
  (5 идентичных повторов на постоянной геометрии не расходятся, не
  накапливают смещение); **edge vs level** — н-п: нет семантики
  «пере-сохранение», единственный триггер — явный вызов функции;
  **ретроактивность** — н-п: нет понятия «размечено до/после» для
  чисто-функциональной операции прыжка; **propagation** — н-п:
  единственный эффект — `window.scrollTo` текущего документа, broadcast
  на другие вкладки вне скоупа этой записи реестра (тот же вывод, что
  TC-260 для соседнего bridge-правила).
- Ретраи с РЕАЛЬНО растущим контентом между попытками (`document.body.
  scrollHeight`, меняющий значение НА КАЖДОМ вызове геттера — симуляция
  «ленивый контент дорастает высоту») — естественный follow-up, не
  входит в обязательные Then докс/01 п.2 (граница `scrollable==0` и
  факт «до 5 раз» уже покрыты Branch A/B); можно закрыть отдельной
  веткой позже без дублирования Given.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс: три ветки — грани ОДНОГО контракта
      («когда и куда прыгает bridge»), не независимые сценарии
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение (счётчик/аргументы вызова
      `window.scrollTo`, `typeof`), а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет (P1), область (browser) и источник требования (R-18)
- [x] Кейс независим от порядка выполнения других кейсов (каждая ветка —
      отдельный `bridge_call`, отдельный jsdom-документ)
- [x] Блокер автоматизации отсутствует
- [x] Строка `Инвариант:` добавлена
- [x] Слой L2 обоснован; пограничное решение относительно Р3-исключения
      «scroll-restore» и относительно B4 fail-open запрета объяснено
      явно в заметках
- [x] Батарея правил-реакций пройдена по пунктам, пропуски — явной
      строкой «н-п: <причина>»
- [x] Наблюдаемость негативного Then (Branch A): контраст с Branch B на
      ТОЙ ЖЕ функции (0 vs 5 вызовов по ЕДИНСТВЕННОЙ переменной —
      геометрии) — не вакуумный негатив
