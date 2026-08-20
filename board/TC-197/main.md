---
key: "TC-197"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Баннер над листингом отражает РОВНО причину скрытия по паре флагов (ratedHidden × filterActive): дословный текст на каждую комбинацию, узла нет при обеих false"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-20T16:45:00Z"
updated: "2026-08-20T16:45:00Z"
archived: false
resolution: null
---

# Баннер над листингом отражает РОВНО причину скрытия по паре флагов (ratedHidden × filterActive): дословный текст на каждую комбинацию, узла нет при обеих false

_Спроецировано из `test-cases/browser/TC-197.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-197 — Баннер над листингом: дословный текст — чистая функция пары флагов (ratedHidden × filterActive), полная таблица истинности

**Поглощает:** TC-199, TC-200, TC-201 (П1 spec-p1-dedup v7, docs/tasks/p1-dedup-lead-pass.md Р2:
«четыре P1-кейса на две булевы переменные... таблица истинности, выписанная кейсами»).
Один и тот же дорогой Given (`seeded_library` + приложение запущено + открыт листинг)
варьируется только состоянием Settings/фильтра — четыре варианта ниже покрывают
все четыре ячейки БЕЗ дублирования механизма.

## Предусловия
- Приложение запущено, `seeded_library` (в т.ч. `DISLIKED` из `framework/data/works.py`,
  `rating=DISLIKE`, среди прочих эталонных работ).
- Открывается листинговая страница (replay `listing_basic.mitm`), содержащая блёрбы
  всех эталонных работ; для вариантов B/C дополнительно засеян фильтр-профиль
  "My saved search" (`filter_profile_applied_seeded`, `queryString =
  rb.FILTER_APPLIED_QUERY_STRING` — та же фикстура, что TC-041).
- Конкретное состояние Settings (Display mode / hidden-set / выбранный
  фильтр-профиль) для КАЖДОГО варианта — своё, названо явно в Given этого
  варианта ниже; общая инфраструктура (сид, реплей) не меняется между
  вариантами — та же СТОИМОСТЬ Given, отличается только состав действий
  пользователя до открытия/после открытия листинга.

## Сценарий (Given-When-Then)

Таблица истинности по паре булевых флагов `(ratedHidden, filterActive)`
(`ao3_bridge.js:509-510,515-519`, было `:477-487` — критик-гейт прохода 10 сверил с HEAD); четыре варианта ниже проверяют все четыре ячейки.

### Вариант A — только visibility-скрытие (ratedHidden=true, filterActive=false) — родной сценарий TC-197

**Given** приложение запущено с `seeded_library`, Settings в дефолтном состоянии
(Display mode=Hide, Disliked в hidden-set, фильтр-профиль не выбран)

**When** пользователь открывает листинговую страницу `listing_basic.mitm`

**Then** над `ol.work.index.group` присутствует узел `#ao3-companion-hidden-notice`
с ДОСЛОВНЫМ текстом **"Some works may be hidden by your visibility settings"**
(`ao3_bridge.js:518`, было `:485-486`)
**And** блёрб работы DISLIKED на этой же странице реально скрыт (`display:none`) —
сообщение и факт скрытия согласованы, баннер не «сирота»

### Вариант B — только активный AO3-фильтр (ratedHidden=false, filterActive=true) — поглощает TC-199

**Given** приложение запущено с `seeded_library`, тумблер «Hide Disliked works»
выключен ДО навигации на листинг (`hiddenRatings` пуст), засеян фильтр-профиль
"My saved search", открыт базовый листинг без применённого фильтра

**When** пользователь раскрывает фильтр-панель и выбирает "My saved search"
(тот же путь, что TC-041 `test_apply_filter_profile`)

**Then** страница обновляется на `rb.LISTING_FILTERED_URL` (тот же URL, что TC-041)
**And** над `ol.work.index.group` на ЭТОЙ (отфильтрованной) странице появляется
узел `#ao3-companion-hidden-notice` с ДОСЛОВНЫМ текстом
**"Some works may be hidden by the active AO3 filter"** (`ao3_bridge.js:519`, было `:487`)
**And** ни один блёрб на странице не скрыт по visibility-фильтрации
(`hiddenRatings` пуст, в т.ч. блёрб DISLIKED виден) — сообщение говорит именно
и только о фильтре, не о visibility-настройках

### Вариант C — обе причины разом (ratedHidden=true, filterActive=true) — поглощает TC-200

**Given** приложение запущено с `seeded_library`, Settings в дефолтном состоянии
(Disliked в hidden-set, Display mode=Hide), засеян фильтр-профиль "My saved
search", открыт базовый листинг без применённого фильтра

**When** пользователь раскрывает фильтр-панель и выбирает "My saved search"

**Then** страница обновляется на `rb.LISTING_FILTERED_URL`
**And** над `ol.work.index.group` появляется узел `#ao3-companion-hidden-notice`
с ДОСЛОВНЫМ текстом
**"Some works may be hidden by visibility settings and active AO3 filter"**
(`ao3_bridge.js:516`, было `:484`)
**And** блёрб работы DISLIKED на этой же (отфильтрованной) странице скрыт
(`display:none`) — оба механизма одновременно активны и согласованы с текстом
сообщения

### Вариант D — ни visibility, ни фильтр не активны (ratedHidden=false, filterActive=false) — поглощает TC-201

**Given** приложение запущено с `seeded_library`, тумблер «Hide Disliked works»
выключен ДО навигации на листинг, фильтр-профиль не выбран

**When** пользователь открывает листинговую страницу, содержащую блёрбы всех
эталонных работ

**Then** узел `#ao3-companion-hidden-notice` ОТСУТСТВУЕТ в DOM — гейт создания
`ratedHidden || filterActive` (`ao3_bridge.js:511-514`, было `:479`) ложен при обоих флагах false
**And** ни один блёрб (в т.ч. DISLIKED) не скрыт и не затемнён — `display`/`opacity`
не изменены фильтрацией

**Инвариант (мастер-мэппинг всех четырёх вариантов):** текст/присутствие узла
`#ao3-companion-hidden-notice` — чистая функция ПАРЫ булевых флагов
`(ratedHidden, filterActive)` по таблице `ao3_bridge.js:511-519`, было `:479-487`:
- `(false, false)` → узла нет (вариант D);
- `(true, false)` → «…your visibility settings» (вариант A);
- `(false, true)` → «…the active AO3 filter» (вариант B);
- `(true, true)` → «…visibility settings and active AO3 filter» (вариант C).

Функция не зависит ни от состава текущей листинговой страницы, ни от того,
какая конкретно работа под флагом попала на глаза пользователю — только от
пары флагов; ни в одном варианте состав видимых работ на странице не меняет
ТЕКСТ, только присутствие/отсутствие узла коррелирует с наличием реально
скрытых блёрбов (And-проверки внутри каждого варианта). Все четыре ячейки
таблицы покрыты вариантами A–D в СОВОКУПНОСТИ этого одного кейса — единичный
вариант доказывает только свою ячейку.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `DISLIKED` из `framework/data/works.py`, `rating=DISLIKE` |
| Вариант A: `(ratedHidden, filterActive)` | `(true, false)` → «Some works may be hidden by your visibility settings» |
| Вариант B: `(ratedHidden, filterActive)` | `(false, true)` → «Some works may be hidden by the active AO3 filter» |
| Вариант C: `(ratedHidden, filterActive)` | `(true, true)` → «Some works may be hidden by visibility settings and active AO3 filter» |
| Вариант D: `(ratedHidden, filterActive)` | `(false, false)` → баннер отсутствует |
| Фильтр-профиль (B/C) | "My saved search", `queryString = rb.FILTER_APPLIED_QUERY_STRING` |

## Заметки для автоматизации
- **Не блокер (page-object-доработка, по образцу TC-092/093/094):**
  `framework/web/listing_page.py` не имеет метода чтения баннера. Локатор УЖЕ
  определён — `framework/web/selectors.py:61`
  `HIDDEN_NOTICE_ID = "ao3-companion-hidden-notice"` (объявлен, но нигде не
  использован). Нужен метод по образцу `is_hidden`/`opacity_of`, например
  `hidden_banner_text() -> str | None` (текст узла `#{HIDDEN_NOTICE_ID}` или
  `None`, если узла нет). Остальные кейсы этой области (TC-198, TC-202..204)
  переиспользуют этот же метод — заметка не дублируется по кейсам.
- Использовать `seeded_library` — уже содержит DISLIKED, отдельного сидинга не
  требуется; фикстура листинга — `listing_basic.mitm` (та же, что TC-013/092/093).
- Проверка скрытия блёрба — существующий `browser_steps.assert_blurb_hidden`
  (тот же приём, что TC-013).
- Инфраструктура применения фильтра (варианты B/C) — существующая, доказанная
  TC-041 (Automated): `filter_profile_applied_seeded` fixture, `browser_steps.
  open_filter_dropdown`/`select_filter_option`/`assert_active_tab_url`/
  `assert_active_filter_shown`. Не нужно ничего добавлять.
- `settings_steps.set_hide_rating(driver, "Disliked", False)` — существующий шаг
  (TC-015), выполнить ДО `open_listing` в вариантах B/D.
- `LISTING_FILTERED_URL` — второй flow в ТОМ ЖЕ `listing_basic.mitm` (та же HTML,
  что базовый листинг) — отдельного сидинга/записи не требуется.
- Не дублирует TC-041: тот кейс проверяет применение фильтра (URL/индикация
  «активно применён»); этот — исключительно текст баннера при каждой комбинации
  флагов. Единственное отличие Given варианта C от варианта B — Settings НЕ
  трогаются (дефолт вместо явного выключения тумблера) — минимальная дельта,
  изолирующая именно четвёртую ячейку таблицы.
- Каждый вариант — независимая Appium-сессия/прогон теста (параметризация
  ОДНОГО теста по паре флагов, П1 Р2 — «параметризация только внутри одного
  кейса»); варианты НЕ образуют journey/чекпойнты (нет мутации общего
  состояния между ними, каждый самодостаточен) — секция «Чекпойнты» здесь не
  нужна.
- **Батарея правил-реакций:** вариант A — позитивный представитель мэппинга
  (не off-инвариант и не propagation); вариант D — **off-инвариант**
  (ПРИМЕНИМО, явный негативный Then выше); **propagation** — ПРИМЕНИМО (код
  `BrowserScreen.kt:161-168` рассылает `setHiddenBanner` на ВСЕ открытые
  WebView разом) — покрыто ОТДЕЛЬНЫМ кейсом TC-204 (класс BUG-012), не
  дублируется здесь; **edge vs level** — н-п: у баннера нет «сохранения без
  семантического перехода» — `updateHiddenBanner()` не персистентный побочный
  эффект (не пишет в БД/сеть), а идемпотентный DOM-рендер, вызываемый на
  каждой загрузке страницы; лишний вызов с теми же значениями просто
  перезаписывает тот же `textContent` тем же значением; **ретроактивность** —
  н-п: нет персистентного per-объектного состояния, баннер полностью
  производный от ДВУХ live-флагов; **идемпотентность** — н-п по той же
  причине (замена `textContent`/`remove()` идемпотентны по построению).
  Полная оценка (унаследована от TC-201, не дублируется подробно) —
  переоценка эквивалентна оригинальной, т.к. механизм тот же.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий (параметризованный по паре флагов, 4 варианта таблицы
      истинности) — один кейс; нет «и ещё проверить...» вне заявленной
      таблицы
- [x] Given каждого варианта задаёт полное воспроизводимое фикстурами
      состояние
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения (что показывает баннер
      в каждой из четырёх комбинаций, включая явное «узла нет»)
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов (каждый вариант
      самодостаточен по Given)
- [x] Строка `Инвариант:` добавлена (мастер-мэппинг всех 4 вариантов)
- [x] Батарея правил-реакций оценена по всем вариантам (propagation — TC-204)
- [x] Поглощение явно названо: TC-199, TC-200, TC-201 (см. заголовок секции
      «Сценарий» и построчные пометки у каждого варианта)
- [x] Слой L3, строка «почему не L2» дана явно (координатор, 2026-08-20,
      ратификация обоснования F1-ревьюера ниже, независимо проверенного
      критик-гейтом): device-free L2-гарнизон (`framework/tests/bridge/
      test_filters.py`, jsdom) покрыл бы ТОЛЬКО таблицу истинности внутри
      `ao3_bridge.js::updateHiddenBanner`, но НЕ цепочку вычисления/инъекции
      исходных флагов из Kotlin (`MainActivity.kt:384-386` считает
      `ratedWorksHidden`/`ao3FilterActive`, `BrowserScreen.kt:676-677`
      инжектит их в WebView на `onPageFinished`) — именно там баг сломался бы
      незаметно для L2. L3 оправдан целостностью проверяемой цепочки, не
      инерцией уже написанного device-теста.

## Ревью автотеста

**test-reviewer, 2026-08-20T16:22:25Z — `changes_requested`.** Дефектов в
ТЕСТОВОМ КОДЕ не найдено: чек-листы 1-7, 9, 11 пройдены (витнесы ниже —
зелёный прогон 4/4 и красная проба ОБЕИХ ветвей ассерта уже сняты, повторять
их незачем). Единственный блокер — отсутствующее поле `layer` (чек-лист
п.10): кейс ПЕРЕРАБОТАН 2026-08-19 (коммит `dbed3510`, поглощение
TC-199/200/201, сценарий 4→18 шагов) — то есть уже ПОСЛЕ введения политики
слоёв 2026-08-16, а решение о слое не принято.

### Блокер 1 — нет поля `layer` у переработанного кейса (чек-лист п.10, П2 spec-p2-pyramid v4)

`test-cases/browser/TC-197.md:1-19` (frontmatter) — ключа `layer` нет вовсе.
Схема (`schemas/test-case.schema.yaml:17`) держит `layer` ОПЦИОНАЛЬНЫМ
намеренно (старые 256 кейсов не краснеют), поэтому `validate_frontmatter`
молчит — гейт «непусто И в enum + для L3/L4 строка «почему не L2»» держит
F1, см. `docs/01-test-strategy.md:268-274`.

Почему это не формальность именно здесь: таблица истинности баннера —
ЧИСТАЯ функция двух `window`-флагов внутри `ao3_bridge.js`
(`updateHiddenBanner`, :503-535: гейт `:511`, три текста `:515-519`), а
device-free L2-гарнизон уже существует и уже проверяет РОДСТВЕННУЮ ветку
того же бриджа (`framework/tests/bridge/test_filters.py::test_hide_mode_
sets_display_none_for_hidden_rating`, jsdom, `framework/bridge_harness/`).
Четыре инстанса нынешнего теста стоят ~8 мин устройства (замер ниже).
Контраргумент за L3 тоже есть и он содержательный: L2 НЕ покрывает цепочку
инъекции флагов из Kotlin (`MainActivity.kt:384-386` считает
`ratedWorksHidden`/`ao3FilterActive`, `BrowserScreen.kt:676-677` инжектит их
в `onPageFinished` ДО bridge-скрипта) — именно она и ломается в проде
незаметно. Ветка L2 «не гейтирована layout'ом» (чек-лист п.11, docs/02 §2а:
infinite-scroll/`scrollY`/scroll-restore) — баннер к этому списку не
относится, так что jsdom-зелёный там был бы содержательным.

**Что сделать:** проставить `layer:` из enum {L2, L3, L4, L5} и, если L3
(ожидаемо — ради цепочки инъекции флагов), добавить в кейс строку «почему
не L2» (дешевле и быстрее устройства — docs/01 §3), назвав ЯВНО, что именно
L2 доказать не может. Решение о слое — за автором кейса/дизайнером, не за
ревьюером: сам гейт существует ровно затем, чтобы этот выбор был сделан
письменно, поэтому поле не заполняется ревьюером «за автора».

### Витнес зелёного прогона (чек-лист п.6, воспроизведён независимо)

Команда: `powershell -NoProfile -ExecutionPolicy Bypass -Command
". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest -k
test_hidden_banner_matches_flag_combination -v"` (устройство сверено ДО
прогона: `Get-Device` → `DEVICE: emulator-5554`).

```
tests/test_hidden_banner.py::...[listing_basic.mitm-A-rated-hidden-only] PASSED [ 25%]
tests/test_hidden_banner.py::...[listing_basic.mitm-B-filter-active-only] PASSED [ 50%]
tests/test_hidden_banner.py::...[listing_basic.mitm-C-both-causes] PASSED [ 75%]
tests/test_hidden_banner.py::...[listing_basic.mitm-D-neither-cause] PASSED [100%]
================ 4 passed, 703 deselected in 494.34s (0:08:14) ================
PYTEST_EXIT=0
```

### Витнес красной пробы (чек-лист п.7) — тест УМЕЕТ падать обеими ветвями

Порча (одна, на уровне СОСТОЯНИЯ приложения, а не оракула — сдвиг ячеек
таблицы истинности на строку): временная замена списка `parametrize`
в `framework/tests/test_hidden_banner.py:57-62` на две пробы —
`(False, False, _BANNER_VISIBILITY_ONLY)` (флаги выключены, оракул ждёт
текст) и `(True, False, None)` (флаг включён, оракул ждёт отсутствия узла).
Порча выбрана так, чтобы бить в СОДЕРЖАТЕЛЬНЫЙ ассерт Then обеих ветвей
`if expected_banner is None` — включая негативную (класс 3 ложно-зелёных
негативов).

```
tests/test_hidden_banner.py::...[RED-A-flags-off-expect-text] FAILED [ 50%]
tests/test_hidden_banner.py::...[RED-D-flag-on-expect-absent] FAILED [100%]
...
E  selenium.common.exceptions.TimeoutException: Message: узел баннера скрытых
   работ не показал ожидаемый дословный текст 'Some works may be hidden by your
   visibility settings'          (steps/browser_steps.py:1739, ветка позитива)
E  AssertionError: узел баннера скрытых работ #ao3-companion-hidden-notice
   неожиданно присутствует в DOM (оба флага ratedHidden/filterActive должны быть
   false)                        (core/waits.py:90 ← browser_steps.py:1765,
                                  ветка негатива, assert_holds_for)
================ 2 failed, 703 deselected in 251.30s (0:04:11) ================
PYTEST_EXIT=1
```

Оба падения — на содержательных ассертах Then, текст падения называет суть
порчи (не таймаут-мусор инфраструктуры). Негативная ветка (`assert_hidden_
banner_absent`, переписанная критик-гейтом на `assert_holds_for`) доказанно
НЕ вакуумна: при реально созданном узле она падает на первом же опросе.

**Откат порчи — по байтовой копии** (CLAUDE.md «Дисциплина команд» п.8):
`git status --porcelain -- framework/tests/test_hidden_banner.py` ДО порчи —
ПУСТО; копия файла снята в scratchpad (`md5 = 68680a0efe3d0ed56b27891ba731f58b`).
После восстановления копии — сверка дословно:

```
$ md5sum framework/tests/test_hidden_banner.py
68680a0efe3d0ed56b27891ba731f58b *framework/tests/test_hidden_banner.py
$ git status --porcelain -- framework/tests/test_hidden_banner.py
(пусто)
$ git diff --stat -- framework/tests/test_hidden_banner.py
(пусто)
```

### Пройдено (для следующего круга — перепроверяется заново, но находок не было)

- **п.1 архитектура:** `python scripts/arch_check.py` → `ошибок 0`; ни одного
  WARN на `framework/tests/test_hidden_banner.py` / `test-cases/browser/TC-197.md`
  (26 WARN — чужой бейзлайн/ALLOWLIST, адресат — батч test-maintainer).
  Локаторов/драйвера в тесте нет (`HIDDEN_NOTICE_ID` — в `web/selectors.py:61`,
  чтение — в `web/listing_page.py:183-195`, шаги — в `steps/browser_steps.py`),
  `sleep` только внутри `core/waits.py::assert_holds_for`.
- **п.2 traceability:** `@allure.id("TC-197")` == id кейса; `@pytest.mark.p1` ==
  `priority: P1`; `@pytest.mark.replay` соответствует `listing_basic.mitm`;
  `automated_by` указывает на существующую функцию.
- **п.3 соответствие по смыслу + инвариант:** параметризация покрывает ВСЕ
  4 ячейки таблицы (свойство, а не единичный пример), дословные строки теста
  (`:43-45`) побайтово совпадают с `ao3_bridge.js:516/518/519`; And-ассерты
  `assert_blurb_hidden`/`assert_blurb_visible` держат согласованность
  «баннер не сирота» из каждого варианта.
- **п.4 фикстуры:** `library_and_filter_profile_seeded` объявлена ДО `driver`
  в сигнатуре (`:66`) — сидинг выполняется до создания Appium-сессии;
  `clean_state()` внутри фикстуры чистит состояние; `driver` — function-scope,
  зависимости от порядка тестов нет; дефолты `autoApplyFilter=true`
  (`SettingsScreen.kt:82/207`) и `filterDisplayMode="hide"` (`:73-74`)
  восстанавливаются `clean_state`, так что Given каждого варианта полон.
- **п.5 flake-риск:** все три ассерта Then — опрашивающие (`wait_until` /
  `assert_holds_for`), одноразовых чтений DOM после WebView round-trip нет;
  `open_filter_dropdown`/`assert_active_filter_shown` берут
  `BottomNav.ensure_visible()` (гонка с `AnimatedVisibility` панели закрыта);
  живого AO3 нет — весь трафик из replay-записи.
- **п.8 дубль-Given:** обоснование поглощения объявлено явно (шапка «Сценарий»,
  П1 Р2), общий дорогой Given переиспользуется намеренно — не находка.
- **п.9 проба на чекпойнт:** кейс не journey (явная строка в «Заметках»:
  «варианты НЕ образуют journey/чекпойнты»), требование отдельных `- проба:`
  на чекпойнт неприменимо; фактически проба снята на обе ветви ассерта.
- **п.11 bridge/layout-гейт:** неприменимо (не `layer: L2`, нет
  `@pytest.mark.bridge`).
