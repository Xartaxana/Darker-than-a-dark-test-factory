---
key: "TC-129"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Infinite scroll: тумблер OFF — скролл к концу листинга не подгружает следующую страницу, нумерованная пагинация остаётся штатной"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:settings", "risk:R-11", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-30T19:45:07Z"
updated: "2026-07-30T19:45:07Z"
archived: false
resolution: "done"
---

# Infinite scroll: тумблер OFF — скролл к концу листинга не подгружает следующую страницу, нумерованная пагинация остаётся штатной

_Спроецировано из `test-cases/settings/TC-129.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-129 — Infinite scroll OFF: скролл к концу листинга не подгружает следующую страницу

## Предусловия
- Приложение запущено с чистыми данными; тумблер «Infinite scroll (listing
  pages)» переключён в **OFF в Settings ДО перехода на листинговую страницу**
  (см. «Заметки для автоматизации» — гейт `ao3_bridge.js:530` вычисляется ОДИН
  РАЗ при инъекции скрипта на загрузке страницы, переключение ПОСЛЕ загрузки
  листинга на уже подписанный `scroll`-слушатель не действует ретроактивно —
  измерено чтением кода). **Атрибуция ИСПРАВЛЕНА (доработка attempt 2,
  критик-вход N4):** сам push (`LaunchedEffect`) у ОБОИХ тумблеров идентичен
  по коду (`BrowserScreen.kt:187-192` tap_to_scroll vs `:195-200`
  infinite_scroll — оба реактивно шлют `evaluateJavascript` при изменении
  prefs); различается не push, а ПОТРЕБЛЕНИЕ значения на стороне JS —
  `tap_to_scroll` читает флаг на КАЖДЫЙ клик (`:1153`), `infinite_scroll`
  читает его ОДИН РАЗ на гейте `:530` при инъекции скрипта, поэтому
  своевременно отправленное новое значение переменной уже не влияет на
  давно подписанный `scroll`-слушатель. docs/01 §9 уже несёт эту
  формулировку корректно — поправлен только текст этого кейса.
- Открыта replay листинговая страница `listing_paginated.mitm`, страница 1 из
  5 (`recording_builder.py::build_listing_paginated`), несущая реальную
  разметку `ol.pagination li.next a`.

## Сценарий (Given-When-Then)

**Given** `infinite_scroll = OFF` установлен ДО навигации; открыта страница 1
`listing_paginated.mitm` (1 work-блёрб + нумерованная пагинация «1, 2, Next
→»)

**When** пользователь скроллит листинг до самого конца страницы (за пределы
`ol.work.index.group`)

**Then** новый work-блёрб НЕ появляется — `ol.work.index.group` по-прежнему
несёт РОВНО 1 `li[id^="work_"]`, сетевого запроса на страницу 2 не происходит

**And** нумерованная пагинация ОСТАЁТСЯ видимой (пункты «1», «2» не получили
`display:none` — это происходит только внутри гейта `:541-545`, который
выполняется ТОЛЬКО при `infinite_scroll !== false`; «Next →» **исключён из
этой проверки доработкой attempt 2, критик-вход N5** — `:542` не прячет
`li.next` НИ В ОДНОМ состоянии тумблера, различают ТОЛЬКО пункты «1»/«2»,
включение «Next →» в перечень утверждало бы факт, которого код не производит)

**And** тап по ссылке «Next →» переводит на страницу 2 ПОЛНОЙ навигацией
(смена `pathname`/query, а не подгрузкой без перехода) — штатное поведение
AO3 без вмешательства bridge

**Инвариант:** при `infinite_scroll=OFF`, ЕСЛИ тумблер был OFF на момент
ЗАГРУЗКИ страницы листинга (перед инъекцией bridge-скрипта), подгрузка не
срабатывает НИ ПРИ КАКОЙ прокрутке ЭТОЙ загрузки страницы — единственная
развилка (`:530`) применяется один раз при загрузке страницы, поэтому
«выключено» — это отсутствие подписки на `scroll` вообще на данной загрузке, а
не молчаливая проверка внутри обработчика на каждый скролл.

**Non-goal (осознанно, решение оператора 2026-07-28, вопрос B2в
доработки-предшественника):** mid-session переключение тумблера (`ON->OFF`
ИЛИ `OFF->ON` ПОСЛЕ того, как страница листинга уже загружена) НЕ имеет
живого эффекта на infinite-scroll — это **Intended**, не баг, в отличие от
`tap_to_scroll`, где переключение живое (реактивный push, см. TC-124: `push`
у ОБОИХ тумблеров идентичен по коду, `BrowserScreen.kt:187-192` vs
`:195-200` — различается ПОТРЕБЛЕНИЕ, не сам push: `:1153` читает флаг на
КАЖДЫЙ клик, `:530` — гейт ОДИН РАЗ при инъекции). Этот кейс НЕ добавляет
отдельный сценарий на mid-session сторону — это явный non-goal, не пробел
дизайна области; если оператор пересмотрит решение, новый кейс проектируется
отдельным диспатчем.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| `infinite_scroll` | OFF (установлен до загрузки) |
| Число work-блёрбов до/после скролла до конца | 1 / 1 (не изменилось) |
| Нумерованная пагинация | видима, кликабельна |
| Тап «Next →» | полная навигация на страницу 2 |

## Заметки для автоматизации
- **Не заблокировано инфраструктурой** — `listing_paginated.mitm` уже
  существует (`framework/data/recordings/listing_paginated.mitm`, собран
  `scripts/build_replay_recordings.py::build_listing_paginated`) и несёт
  реальную разметку `ol.pagination li.next a` + филлер-контент **по эталону
  AT-BUG-015** (`recording_builder.py:168-173` — 80 филлер-абзацев на
  страницу, тот же приём, что `render_tab_marker_html`). **Замер СНЯТ
  доработкой attempt 2 (критик-вход Б1):** `scroll_listing_to_bottom`
  (`browser_steps.py`) теперь читает `window.scrollY`/`innerHeight`/
  `document.body.scrollHeight` сразу после `scrollTo` и приложен через
  `allure.attach`; фактический прогон на эмуляторе конвейера (2026-07-30)
  дал `scrollY≈4341.7 innerHeight=798 scrollHeight=5104` — документ фикстуры
  ЗАМЕТНО выше вьюпорта (5104 vs 798 px), скролл реально произошёл
  (`scrollY > 0`), негативный Then (`assert_work_blurb_count_holds`) НЕ
  вакуумен на этом устройстве/AVD. Прокручиваемость дополнительно доказана
  device-free юнитами `framework/tests/test_recording_builder_unit.py`
  на уровне HTML-структуры (число филлер-абзацев/наличие блока). Прежнее
  упоминание блокера в docs/01 §9 («нужна фикстура listing_paginated.mitm») —
  УСТАРЕЛО: фикстура собрана батчем builder'а 2026-07-28 ПОСЛЕ формулировки
  требования; новый test_debt-баг НЕ заводится (правило 4 воркфлоу
  test-designer — заводить баг ТОЛЬКО при подтверждённом блокере; здесь
  блокера уже нет).
- Новый Settings-степ «выключить тумблер Infinite scroll» — рутинная
  автоматизация по образцу `set_hide_rating`/`set_auto_download`
  (`framework/steps/settings_steps.py`).
- Переход на replay-URL: `rb.LISTING_PAGINATED_URL` (`https://
  archiveofourown.org/works?ao3_companion_fixture=listing_paginated`) через
  `@pytest.mark.parametrize("replay", ["listing_paginated.mitm"],
  indirect=True)` — тот же паттерн, что остальные replay-тесты
  (`framework/tests/conftest.py::replay`).
- Скролл «до самого конца» — программный `execute_script("window.scrollTo(0,
  document.body.scrollHeight);")` детерминированнее жеста; сетевой запрос на
  страницу 2 можно дополнительно подтвердить отсутствием второго work-id в
  `document.querySelectorAll('li[id^="work_"]')`.
- **Батарея правил-реакций (оценка применимости, CLAUDE.md):** infinite-scroll
  — не background-эффект в духе auto-download/kudos (реакция на СВОЁ прямое
  действие пользователя — скролл контента, который он читает, — а не побочный
  эффект НЕСВЯЗАННОГО сохранения); тем не менее off-инвариант ЯВНО покрыт этим
  кейсом (симметрично TC-123 для tap-to-scroll). Ретроактивность/edge-vs-level
  — н-п: тумблер не переоценивает прошлые состояния данных, только режим
  подписки на текущей загрузке страницы (сам этот факт — часть Given/находка
  этого кейса, не отдельного применения батареи). Идемпотентность/propagation
  — н-п: нет фонового состояния, разделяемого несколькими потребителями,
  каждая листинговая вкладка независима.

## Ревью автотеста (F1, test-reviewer, 2026-07-30)

**Вердикт: PASS** — `Approved -> Automated`, `automation_status: active`.

- **Архитектура (п.1):** `python scripts/arch_check.py` — «ошибок 0,
  предупреждений 0»; файл теста не в ALLOWLIST. Локаторы —
  `framework/web/selectors.py` (`PAGINATION_NUMBERED_ITEMS`/
  `PAGINATION_NEXT_LINK`), DOM-чтение — `framework/web/listing_page.py`,
  шаги — `framework/steps/{browser,settings,app}_steps.py`; в тесте нет
  ни локаторов, ни `driver.execute_script`, ни `sleep` (ожидания —
  `core/waits`: `wait_until`, `assert_holds_for`).
- **Traceability (п.2):** `@allure.id("TC-129")` == id кейса;
  `@pytest.mark.p1` == `priority: P1`; `@pytest.mark.replay` соответствует
  replay-фикстуре; `automated_by` указывает на существующую функцию
  `test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination`;
  `features: [settings-infinite-scroll-toggle]` есть в
  `docs/feature-registry.yaml:385`.
- **Соответствие кейсу (п.3):** ключевой нюанс порядка соблюдён —
  тумблер выключается в Settings (`disable_infinite_scroll`) и сверяется
  явным assert'ом (`assert_infinite_scroll_enabled(expected=False)`) ДО
  `open_tab("Browse")`/`open_listing(...)`, то есть ДО загрузки листинга и
  инъекции bridge-скрипта (гейт `ao3_bridge.js:530` сверен чтением кода —
  вычисляется один раз при инъекции). Then'ы реализуют GWT по существу, а
  не «элемент существует»: `assert_work_blurb_count_holds(1)` держит
  негатив ВЕСЬ бюджет (8 с, `assert_holds_for`) — это форма ИНВАРИАНТА
  («ни при какой прокрутке этой загрузки»), а не единичная выборка;
  `assert_pagination_numbered_items_visible` проверяет `display != none`
  именно у номерных пунктов, `.next`/`.previous` исключены селектором —
  корректно, `ao3_bridge.js:542` не прячет `li.next` НИ В ОДНОМ состоянии
  тумблера, поэтому свидетелем режима служат только номерные пункты;
  `assert_webview_location_changed` дополнительно требует `page=2`, а не
  любой смены location. Строка `Инвариант:` в кейсе присутствует.
- **Фикстуры и данные (п.4):** сигнатура `(replay, clean_app, driver)` —
  `pm clear` и подъём replay-прокси происходят ДО создания Appium-сессии
  (порядок фикстур корректен, HANDOFF); teardown `replay` возвращает прокси
  и глушит mitmdump в `finally`. Тест владеет своими данными, от порядка
  других тестов не зависит; фикстура `listing_paginated.mitm` покрывает
  все href пагинации (инвариант AT-BUG-006) — ухода на живой AO3 нет.
- **Flake-риск (п.5):** ожидания явные, гонок с Compose-анимациями нет
  (взаимодействие с пагинацией — в WebView через DOM API, не тап по
  родителю текстового узла); `scroll_listing_to_bottom` ассертит
  `scrollY > 0` и прикладывает геометрию в Allure — вакуумный негатив
  («документ не выше вьюпорта») исключён на устройстве.
- **Независимое воспроизведение (п.6):** прогон ревьюера на эмуляторе
  конвейера (`Get-Device` -> `DEVICE: emulator-5554`),
  `Invoke-Pytest -k test_infinite_scroll_off_keeps_native_pagination -q` ->
  `1 passed ... PYTEST_EXIT=0` (47.53 s). Повторный прогон после отката
  красной пробы — `1 passed ... PYTEST_EXIT=0` (46.78 s).
- **Красная проба (п.7), witness:** порча на уровне ДАННЫХ (тестовый код
  не менялся) — в page-1 flow `framework/data/recordings/
  listing_paginated.mitm` вшит `<script>`, дописывающий по первому
  scroll-событию второй `li[id^="work_"].work.blurb` (`work_90000001`),
  т.е. ровно тот наблюдаемый эффект, который кейс обязан отвергать при
  `infinite_scroll=OFF`. Команда: та же
  `Invoke-Pytest -k test_infinite_scroll_off_keeps_native_pagination -q`.
  Результат: `1 failed ... PYTEST_EXIT=1` (35.84 s), падение — на
  СОДЕРЖАТЕЛЬНОМ ассерте Then `browser_steps.py:2193`
  (`assert_work_blurb_count_holds`), текст указывает на суть порчи:
  «на листинге 2 work-блёрбов, ожидали ровно 1 — фоновая подгрузка
  (fetchAndAppend, ao3_bridge.js:557-615) сработала, хотя
  infinite_scroll=OFF ...: ['900000001', '90000001']» — не таймаут-мусор.
  Откат: `git checkout -- framework/data/recordings/listing_paginated.mitm`,
  `git status --porcelain` по этому пути чист, зелёный прогон после отката
  воспроизведён (см. п.6).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует (фикстура уже собрана)
- [x] Строка `Инвариант:` добавлена
- [x] Батарея правил-реакций оценена, применимые пункты названы, неприменимые
      — строкой «н-п: <причина>»
