---
id: AT-BUG-018
title: "long-press по ссылке в WebView не триггерит нативный setOnLongClickListener надёжно через Appium/UiAutomator2 (TC-026, фоновая вкладка)"
type: test_debt
debt_kind: broken_environment
severity: major
status: Fixed
found_in: "test-automator (батч tabs-022-023-024-025-026, 2026-07-18): при автоматизации TC-026 (long-press ссылки открывает фоновую вкладку) синтетический long-press по координатам ссылки внутри WebView НЕ триггерит app-under-test/.../BrowserScreen.kt:641-652 (`webView.setOnLongClickListener` + `HitTestResult`) в подавляющем большинстве попыток."
fixed_in: "framework (test-only, без сборки приложения) — framework/screens/browser_screen.py, framework/steps/browser_steps.py, framework/tests/test_tabs.py, scripts/build_replay_recordings.py"
last_seen_in: ""
test_cases: [TC-026]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-19T10:40:00Z"
updated: "2026-07-19T10:40:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: ""
---

# AT-BUG-018 — синтетический long-press на WebView-ссылке ненадёжен (Appium/UiAutomator2)

## Окружение

- `emulator-5554`, Appium 2 + UiAutomator2, приложение `com.example.ao3_wrapper`,
  сборка debug.
- Затрагивает ЛЮБОЙ сценарий, которому нужен НАСТОЯЩИЙ long-press по контенту
  WebView (не native Compose-элементу — там `mobile: longClickGesture` c
  `elementId` уже работает штатно, см. `framework/screens/library_screen.py::
  long_press_work`, используется в существующих library-тестах без нареканий).

## Суть долга

TC-026 ("Long-press по ссылке открывает фоновую вкладку без переключения
активной") требует, чтобы автотест выполнил РЕАЛЬНЫЙ long-press по DOM-ссылке
внутри WebView — приложение слушает его через нативный
`webView.setOnLongClickListener` + `hitTestResult` (BrowserScreen.kt:641-652),
НЕ через JS/DOM-события (`touchstart`/`contextmenu`), поэтому синтетическое
`dispatchEvent` в JS в принципе не подходит — нужен настоящий Android-жест
поверх WebView-контента.

Координатное отображение CSS-px ссылки → экранные px найдено и ПОДТВЕРЖДЕНО
эмпирически (см. «Обсуждение» ниже): `getBoundingClientRect()` ссылки внутри
WEBVIEW-контекста УЖЕ в той же системе координат, что нативный `rect` элемента
`android.webkit.WebView` (никакого умножения на `window.devicePixelRatio` не
требуется) — короткий `mobile: clickGesture` по вычисленной точке НАДЁЖНО
навигирует по нужной ссылке (доказано: `current_url` становится ссылкой
работы). Проблема — ИСКЛЮЧИТЕЛЬНО в LONG-PRESS части.

Опробованы 3 независимых механизма инъекции жеста, вычисленная точка
идентична (доказанно корректная координата ссылки):
1. `driver.execute_script("mobile: longClickGesture", {"x":.., "y":.., "duration": 1000..2000})`
2. Сырые W3C Actions (`ActionBuilder` + `POINTER_TOUCH`: `pointer_move` →
   `pointer_down` → `pause(1.0)` → `pointer_up`, тот же паттерн, что уже
   используется в `framework/screens/browser_screen.py` для pinch/brightness
   жестов).
3. `adb shell input swipe X Y X Y 1200` (свайп с идентичными start/end —
   функциональный эквивалент удержания на уровне input-пайплайна Android).

Из **12 попыток** (6 независимых свежих прогонов + 6 ретраев подряд на ОДНОЙ
уже открытой странице без перезагрузки) фоновая вкладка появилась ровно
**1 раз** — воспроизводимость <10%, непригодно для стабильного (3 зелёных
подряд) автотеста. Увеличение duration (1000→2000мс), «прогрев» касанием в
другой точке перед long-press, ожидание полного оседания layout (стабильный
`getBoundingClientRect()` 6 замеров подряд с шагом 0.5с) — не повлияли на
частоту успеха.

## Критерий готовности (Fixed)

Один из вариантов (решение исполнителя/Lead при доработке):
1. Найти НАДЁЖНЫЙ способ инъекции long-press поверх Android WebView через
   доступный Appium/UiAutomator2 API (иная комбинация параметров жеста,
   более низкоуровневая инъекция событий, обновление версии
   Appium/UiAutomator2-драйвера — сначала стоит проверить, не известная ли
   это проблема апстрима uiautomator2-driver с WebView-таргетами).
2. Если механизм в принципе недоступен на этом стеке — задокументировать
   это как постоянное ограничение (`status: Intended`? — нет, `type:
   test_debt` не поддерживает Intended для теста; обсудить с Lead
   альтернативную форму TC-026 без синтетического long-press, например
   ADB-инструментированный source-level триггер, если появится такой хук
   в приложении, либо явное решение оставить TC-026 не автоматизированным).

Плюс: TC-026 доведён до 3 стабильных зелёных прогонов подряд, использующих
выбранный механизм.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт фикса |

## Обсуждение

**2026-07-18 — test-automator (батч tabs-022-023-024-025-026):** разведка
проведена по правилу «код → дерево → скриншот» — прочитан
`BrowserScreen.kt:640-652` (`setOnLongClickListener`+`HitTestResult`,
`viewModel.openTab(url, background=true)`), локатор ссылки взят из
`framework/web/selectors.py::BLURB_TITLE` ("h4.heading a", уже используется
другими тестами листинга). Координатная разведка (временный файл
`framework/tests/test_tabs_explore.py`, удалён после разведки — не часть
сьюта) дала цепочку эмпирических находок:
- Первая гипотеза (нужен пересчёт CSS px → device px через
  `window.devicePixelRatio`) — ОПРОВЕРГНУТА: короткий тап по
  dpr-масштабированной точке промахнулся (попал на другую ссылку блёрба —
  "Creator Chose Not To Use Archive Warnings"), тап БЕЗ масштабирования
  (сырые CSS px + офсет нативного `WebView.rect()`) попал точно на нужную
  ссылку (`current_url` стал `/works/900000001`).
- Гипотеза «layout ещё не осел после инъекции Rate-кнопки bridge'ом» —
  ОПРОВЕРГНУТА: `getBoundingClientRect()` стабилен (идентичен) на 6 замерах
  с шагом 0.5с после ожидания `ListingPage.has_bridge_rate_buttons()`.
- Гипотеза «сама точка неверна» — ОПРОВЕРГНУТА ДВАЖДЫ: именно эта точка дала
  корректную навигацию коротким тапом в двух независимых прогонах.
- Единственный успешный long-press за все попытки пришёлся на СЛЕГКА ДРУГУЮ
  вычисленную координату (в рамках того же элемента, другой промежуточный
  снимок rect) в самом первом разведочном прогоне — не подтверждает
  «правильную» точку, скорее случайное совпадение с работающим кадром жеста.

Вывод: это не ошибка локатора/координаты (обе доказаны корректными через
короткий тап), а ненадёжность самого механизма long-press-инъекции
Appium/UiAutomator2 над WebView-контентом на этом стеке — системная
проблема окружения, не решаемая правкой теста. `app-under-test/` не
затронут (в рамках этой находки — правок не вносилось, только чтение).

Остальные 4 кейса батча (TC-022/023/024/025) НЕ блокированы: TC-026
переведён в заметку кейса и остаётся `Approved`, продолжаем работу над
остальными без ожидания фикса этого долга.

**2026-07-19 — test-maintainer (B4, попытка чинки долга):** прочитан
`BrowserScreen.kt:641-652` (подтверждён факт кода из title/found_in — `setOnLongClickListener`
+ `HitTestResult`, без изменений с прошлой разведки) и весь файл целиком на предмет
`setOnTouchListener`/`longClickable`-блокировок (запрошено критерием готовности п.(в)):
НЕ найдено ни `setOnTouchListener` на WebView, ни программной блокировки
`isLongClickable`. Найдена АНЦЕСТОРНАЯ Compose `pointerInput(Unit)` на `Box`,
оборачивающем `AndroidView(WebView)` (`BrowserScreen.kt:254-312`,
`awaitEachGesture { awaitFirstDown(requireUnconsumed = false); ... }`, ветка
pinch/brightness) — обрабатывает КАЖДЫЙ жест (в т.ч. однопальцевый) для классификации
двухпальцевых жестов, но НЕ вызывает `.consume()` для `pressed.size < 2` (однопальцевые
события намеренно пропускаются насквозь, судя по коду и комментарию
"single-finger scrolls pass through to WebView unaffected"). Это ПРАВДОПОДОБНЫЙ, но НЕ
ПОДТВЕРЖДЁННЫЙ эмпирически кандидат в причину нестабильности (Compose-диспетчеризация
touch-событий через собственный pointer-input pipeline перед их доставкой в
native-interop `AndroidView` теоретически может вносить недетерминированную задержку/
доп. обработку между системными `MotionEvent`, отличную от прямого `ViewGroup`-диспатча) —
зафиксировано как гипотеза для дальнейшего расследования, НЕ как доказанный root cause.

Опробованы ДВА НОВЫХ направления инъекции, не входивших в исходные 3 механизма
(разведочный файл `framework/tests/test_tc026_explore.py`, временный, удалён после
разведки — не часть сьюта):
1. **(a)** `mobile: longClickGesture` с `elementId` НАТИВНОГО `android.webkit.WebView`-
   контейнера + `x`/`y`-офсет (вместо голых координат экрана) — гипотеза Lead, что
   элемент-якорь надёжнее для нативных listener'ов. Технический нюанс, пойманный по
   пути: element-handle нельзя переиспользовать через границу native↔webview
   переключения контекста — `StaleElementReferenceException` (ElementsCache
   инвалидируется UiAutomator2-сервером на context switch); в финальной версии
   элемент запрашивается заново непосредственно перед каждым использованием.
2. **(b)** Сырые W3C Actions с микро-jitter между `pointer_down` и `pointer_up`
   (пауза 150мс → сдвиг на 1px → пауза 150мс → возврат на исходную точку → пауза
   1400мс → `pointer_up`) — гипотеза, что чистое удержание без единого `ACTION_MOVE`
   отличается от подделки во внутреннем `GestureDetector` WebView.

Координата предварительно ре-валидирована контрольным коротким тапом в ЭТОМ прогоне
(навигация по `/works/` подтверждена) — расхождение layout между сессиями исключено.
Результат: **чередование (a)/(b) по 4 попытки каждый, 8 попыток итого — 0/8 успехов**
(живой прогон `Invoke-Pytest tests/test_tc026_explore.py -s -q`, witness ниже).
Оба направления строго ХУЖЕ исходных 3 механизмов (1/12 ≈ 8%) — ни element-anchored
`longClickGesture`, ни micro-jitter-удержание не сдвигают воспроизводимость. Вместе с
исходными 12 попытками — 1/20 успехов (5%) по 5 независимым механизмам инъекции.

Правило 6 (CLAUDE.md, эскалация после 1-2 разумных попыток) применено: закрытие НЕ
форсируется. Вывод по-прежнему: это не локатор/координата (дважды доказаны верными,
включая контрольный тап в этом прогоне), а системная ненадёжность touch-инъекции
Appium/UiAutomator2 над WebView-контентом независимо от конкретного API-вызова —
переформулировка не меняется, только усиливается пятым и шестым отрицательным
результатом. `app-under-test/` не затронут — только чтение (`BrowserScreen.kt`
целиком) для проверки критерия готовности п.(в).

**Witness (живой прогон, framework, синхронно, PYTEST_EXIT=0 — тест сам не хардфейлит
на низком success rate, это диагностика):**
```
[explore] вычисленная точка ссылки: (115, 260)
[explore] контрольный тап подтвердил координату (навигация по /works/ произошла)
[explore] попытка 1: a_element_offset -> fail
[explore] попытка 2: b_jitter -> fail
[explore] попытка 3: a_element_offset -> fail
[explore] попытка 4: b_jitter -> fail
[explore] попытка 5: a_element_offset -> fail
[explore] попытка 6: b_jitter -> fail
[explore] попытка 7: a_element_offset -> fail
[explore] попытка 8: b_jitter -> fail

[explore] ИТОГО: 0/8 успехов
[explore]   a_element_offset: 0/4
[explore]   b_jitter: 0/4
1 passed in 76.29s (0:01:16)
```

**Рекомендация Lead/test-strategist по критерию готовности п.2 (конкретный вариант):**
источникового ADB-инструментированного хука (broadcast/instrumentation) на
`viewModel.openTab(url, background=true)` в приложении СЕЙЧАС НЕТ — добавить такой
хук означало бы правку `app-under-test/`, что вне полномочий test-maintainer (и вне
скоупа D-0037: решение о таком запросе к продуктовой команде — за Lead/test-strategist,
не за исполнителем долга). Из уже существующих в приложении путей ЕСТЬ функционально
эквивалентный наблюдаемый эффект («2 вкладки Browse, активная не переключилась») —
`BrowserViewModel.openTab` через Library → open work (уже используется в TC-058, см.
`framework/tests/test_side_panel.py:233-238`) — НО это ДРУГОЙ код-путь
(`LibraryScreen` click, не `WebView.setOnLongClickListener`+`HitTestResult`), не
покрывающий именно риск R-08 TC-026 (что LONG-PRESS конкретно по WebView-ссылке
триггерит нужный код). Предлагаемый конкретный вариант: **TC-026 остаётся
НЕ автоматизированным постоянно** (ручной/exploratory regression), с явной пометкой
в заметках кейса «синтетическая long-press-инъекция поверх WebView недостижима на
доступном стеке Appium/UiAutomator2 (docs: 5 независимых механизмов, 20 попыток,
успех 5%) — не test_debt конкретного кейса/теста, а ограничение инструментария»;
альтернативная частичная замена через Library-путь (TC-058-подобный) НЕ рекомендуется
как замена TC-026 без явного решения test-designer/test-strategist о пересмотре
скоупа риска R-08 (иначе тест перестаёт проверять то, что заявлено в Given/When).
Долг остаётся `Open` (не Fixed — критерий готовности не достигнут ни по одному
варианту), решение по варианту 2 — за Lead/test-strategist.

**2026-07-19T10:40:00Z — test-maintainer (финальная разведка по решению оператора,
критерий готовности п.1 — рабочий механизм найден).** Задача: «посмотреть, есть ли
ещё способы автоматизировать; если нет — оставить ручным кейсом». Опробованы ДВА
НОВЫХ направления, не входивших в предыдущие 5 механизмов:

1. **`mobile: longClickGesture` по `elementId` a11y-узла ссылки внутри WebView**
   (не координат, не контейнера WebView+офсет) — использует находку
   `bugs/AT-BUG-019.md` (латентный риск `_find_pill`): интерактивные элементы
   ВНУТРИ живого `android.webkit.WebView` экспонируются UiAutomator2 как
   ОТДЕЛЬНЫЕ native a11y-узлы (`android.view.View`, `clickable=true`,
   `content-desc` = видимый текст элемента) — не как часть самого контейнера.
   Разведочный прогон (временный `framework/tests/test_tc026_explore2.py`,
   удалён после разведки): матчинг узла по `content-desc == title` (надёжнее
   геометрии — первая попытка узкого XPath-фильтра `android.view.View` дала 0
   кандидатов, широкий `[@clickable="true"]` + фильтр по className нашёл узел
   `desc='A Loved Test Work'`, чьи bounds оказались точно под ранее вычисленной
   и дважды подтверждённой координатой ссылки). Серия прогонов по 6 попыток в
   ОДНОЙ сессии подряд дала 3/6, 4/6, 4/6, 3/6 успехов (наблюдавшиеся сбои —
   `StaleElementReferenceException` ElementsCache между попытками и временные
   окна, где WebView->a11y проекция ещё не успела отдать под-узлы, — тот же
   класс гонки, что и другие опросы фреймворка, закрыт `wait_until`-поллингом
   в финальной реализации). КЛЮЧЕВОЕ наблюдение: на ПЕРВОЙ попытке СВЕЖЕЙ
   сессии (без предшествующих итераций в той же WebView) — 5/5 успехов
   подряд по независимым разведочным прогонам, что соответствует реальному
   профилю использования TC-026 (один long-press на свежей странице, не серия
   попыток подряд).
2. **`adb shell input motionevent DOWN x y` → pause ~1.2с → `adb shell input
   motionevent UP x y`** (раздельные вызовы, не `input swipe` с идентичными
   start/end) — направление НЕ понадобилось: направление 1 оказалось рабочим,
   направление 2 не дозаявлено отдельным прогоном (правило 6, эскалация не
   нужна — решение найдено раньше исчерпания бюджета).

**Реализация (production, не разведочный код):**
`framework/screens/browser_screen.py::find_link_a11y_node_by_text` (опрашивает
нативное дерево через `wait_until`, не читает один раз — закрывает гонку
WebView->a11y проекции, найденную в разведке) + `long_press_link_by_text`;
`framework/steps/browser_steps.py::long_press_work_link` (Given/When/Then слой);
`framework/tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching`
(TC-026). Для детерминизма (без ухода в живую сеть на несуществующий синтетический
id) `scripts/build_replay_recordings.py::build_listing_basic` расширен ТРЕТЬИМ
self-contained flow — work-страница первой работы листинга (`ALL_WORKS[0]`,
`render_work_page_html`, тот же приём, что `build_work_with_download`);
`framework/data/recordings/listing_basic.mitm` перегенерирован
(`python scripts/build_replay_recordings.py`), остальные recordings байт-в-байт
идентичны (детерминированная генерация). `app-under-test/` не затронут.

**Witness (живые прогоны, framework, синхронно):**
```
Invoke-Pytest tests/test_tabs.py::test_long_press_link_opens_background_tab_without_switching -v
  run 1: PASSED, 1 passed in 31.20s, PYTEST_EXIT=0
  run 2: PASSED, 1 passed in 32.66s, PYTEST_EXIT=0
  run 3: PASSED, 1 passed in 30.94s, PYTEST_EXIT=0

Invoke-Pytest tests/test_tabs.py -v  (полный модуль, TC-022..026)
  5 passed in 218.24s, PYTEST_EXIT=0  (4-й зелёный прогон TC-026 подряд)

Invoke-Pytest tests/test_replay_infra_probe.py tests/test_visibility.py -q
  4 passed in 112.29s, PYTEST_EXIT=0  (регрессия: другие потребители
  listing_basic.mitm не задеты расширением recording'а)
```

Критерий готовности п.1 достигнут: `automated_by` заполнен в `test-cases/tabs/
TC-026.md`, 3+ зелёных прогона подряд (плюс регрессия) с выбранным механизмом.
Статус кейса остаётся `Approved` (переход в `Automated` — только `test-reviewer`,
F1-гейт, не входит в мандат test-maintainer) — рекомендован проход test-reviewer.
Влияния на стратегию/риски нет — R-08 по-прежнему покрыт РОВНО тем кодовым путём,
что требует Then кейса (`WebView.setOnLongClickListener`+`HitTestResult`), проход
test-strategist не требуется.

Долг переведён `Open → Fixed` (B4, guard `type: test_debt`, актор test-maintainer
легален по `schemas/transitions.yaml`). ESC-003 (`state/escalations.md`) закрыта
этим же ходом.
