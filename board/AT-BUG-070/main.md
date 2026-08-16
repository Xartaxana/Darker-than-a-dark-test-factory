---
key: "AT-BUG-070"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Нет надёжного приёма адресации execute_script/навигации к КОНКРЕТНОЙ НЕ-нулевой вкладке — sticky WebView context блокирует контраст-дверь Г2 (клик по ссылке) и точный Back-замер на deep-link-вкладке (CH-010)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T10:42:00Z"
updated: "2026-08-16T10:42:00Z"
archived: false
resolution: "done"
---

# Нет надёжного приёма адресации execute_script/навигации к КОНКРЕТНОЙ НЕ-нулевой вкладке — sticky WebView context блокирует контраст-дверь Г2 (клик по ссылке) и точный Back-замер на deep-link-вкладке (CH-010)

_Спроецировано из `bugs/AT-BUG-070.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-070 — нет observability-примитива для адресации execute_script к КОНКРЕТНОЙ не-нулевой вкладке (класс AT-BUG-018/019/022)

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture` — по конвенции этого репо категория
  «недостающая тестовая инфраструктура/наблюдательный примитив», тот же
  смысл, что у AT-BUG-022). Затрагивает ЛЮБОЙ сценарий с >1 живым WebView,
  которому нужно читать/исполнять JS ИМЕННО на визуально активной, но НЕ
  первой созданной вкладке — `framework/screens/browser_screen.py` (докстринг
  класса, `:255-270`), chromedriver/Appium/UiAutomator2.

## Суть долга

`driver.execute_script`/`driver.get`/`driver.current_url` внутри
`contexts.in_webview` при >1 живом `android.webkit.WebView` ВСЕГДА бьют по
вкладке, созданной ПЕРВОЙ (chromedriver «прилипает» к ней и не
переключается штатным `switch_to.context` на другую живую WebView) —
задокументированный класс AT-BUG-018 (long-press-инъекция поверх WebView),
AT-BUG-019 (`_find_pill` кликает по a11y-потомкам WebView вместо нативной
пилюли) и AT-BUG-022 (reduce-to-one не отличает «переключение сработало» от
no-op, когда цель — вкладка-0). Все три закрыты для СВОИХ узких классов
утверждений (long-press-инъекция, фильтр пилюли, различение активности),
но ни один не даёт ОБЩЕГО приёма «прочитать/исполнить JS на вкладке N,
N != 0, без свёртки числа вкладок к одной».

CH-010 (2026-08-14) наткнулась на ЭТОТ же класс дважды в одной сессии, на
двух разных целях:

1. **Контраст-дверь Г2** (`bugs/BUG-070.md`, «Обсуждение»): попытка
   проверить, что клик по ссылке ВНУТРИ страницы (в отличие от
   программного deep-link) проходит `shouldOverrideUrlLoading` и дописывает
   фильтр, требует прочитать `window.__ao3FilterActive`/баннер
   `#ao3-companion-hidden-notice` НА КОНКРЕТНОЙ deep-link-вкладке (позиция
   1, НЕ 0). Прочитанное сессией значение баннера «вероятнее всего читало
   tab-0 (исходную ФИЛЬТРОВАННУЮ вкладку), а не tab-1» — и было ЯВНО
   исключено из `bugs/BUG-070.md` как недостоверное доказательство. Дверь
   осталась непройденной (`mission_leftover` CH-010).
2. **Точный эффект Back на deep-link-вкладке** (`mission_leftover` CH-010,
   тот же followup): требует того же — измерения состояния КОНКРЕТНОЙ не
   нулевой вкладки ДО и ПОСЛЕ программной навигации Back, без свёртки
   соседних вкладок (которая замаскировала бы момент перехода, тот же класс
   конфаунда, что AT-BUG-022).

**Почему это НЕ дубликат AT-BUG-018/019/022.** Каждый из трёх решает УЗКУЮ
задачу СВОЕГО класса утверждений (жест long-press; выбор нативной пилюли
среди кандидатов; различение «переключение сработало» от no-op для цели =
вкладка-0). Ни один не даёт ОБЩЕГО механизма «читать DOM/JS-состояние
произвольной НЕ-нулевой вкладки, пока другие вкладки тоже живы» — именно
этого не хватает ДЛЯ ОБЕИХ находок CH-010 выше. AT-BUG-022 ближе всего по
духу (тот же sticky-context корень, тот же файл), но его
`assert_tab_became_active_via_scroll` — примитив АКТИВНОСТИ (нативный
скролл-жест + `scrollY`), не примитив ЧТЕНИЯ ПРОИЗВОЛЬНОГО JS-состояния
страницы конкретной вкладки; он явно НЕ решает «прочитать баннер/JS-флаг
на вкладке 1, пока вкладка 0 тоже жива» — это другой класс наблюдения
(DOM/JS-состояние страницы, не факт активности вкладки).

## Критерий готовности (Fixed)

Один из вариантов (решение исполнителя/Lead при доработке):
1. Найти надёжный способ адресовать `execute_script`/`driver.get`/чтение
   DOM-состояния ИМЕННО к вкладке с известной позицией N (N != 0), пока
   другие вкладки живы — например: закрыть ВСЕ вкладки, стоящие ПЕРЕД
   целевой, дав ей стать «эффективным нулём» (частичный reduce, не
   reduce-to-one — оставляя живыми вкладки ПОСЛЕ цели, если сценарию нужно
   доказать, что они НЕ затронуты); либо переключение `contexts` по
   стабильному `webview` handle, полученному ДРУГИМ способом, чем
   `current_url`-угадывание; либо иной приём, эмпирически подтверждённый
   контрольным сценарием (2+ живые вкладки, цель != 0, значение до/после
   действия должно РЕАЛЬНО различаться, не совпадать тривиально).
2. Если механизм в принципе недоступен на этом стеке — задокументировать
   как постоянное ограничение (по образцу решения AT-BUG-018 п.2), явно
   перечислив, какие Then-утверждения области filter-profiles/tabs
   ОСТАЮТСЯ недостижимыми автоматически (контраст-дверь Г2, точный
   Back-замер на deep-link-вкладке — как минимум) — решение по конкретному
   варианту за Lead/test-strategist.

Плюс: хотя бы ОДИН из двух заблокированных CH-010 сценариев (контраст-дверь
Г2 ИЛИ точный Back-замер) доведён до кейса/зелёного прогона на выбранном
механизме, если выбран вариант 1.

## Анализ

Класс — «наблюдательный примитив для DOM/JS-состояния произвольной
НЕ-нулевой вкладки отсутствует»: прямой сиблинг AT-BUG-022 (та же
sticky-context первопричина, `browser_screen.py` докстринг `:255-270`),
но другой конкретный пробел (JS/DOM-чтение страницы, не факт активности
вкладки). Приоритет — major (блокирует ДВЕ находки одной сессии CH-010,
обе — часть открытого R-09-риска «профиль применился не там»), не
critical: обе заблокированные грани — КОНТРАСТ/ДОПОЛНИТЕЛЬНОЕ измерение к
уже заведённым и красно-залоченным `bugs/BUG-070.md`/основному Г2-факту, не
единственный путь к сигналу о самом дефекте (`TC-206` полностью
самодостаточен без этого приёма — оба его оракула вне WebView-контекста).

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт разбора |
| 2026-08-16T06:20:00Z | framework (рабочее дерево, unstaged — test_debt, фикс исключительно во фреймворке, сборка приложения не требуется; app-under-test не менялся) | `test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor` (регресс-замок контраст-двери Г2, `@allure.id("AT-BUG-070-g2-contrast-door-non-zero-tab")`) x3 изолированно + полный `test_filter_profiles.py` (12 тестов, регрессия по всей области filter-profiles) | Изолированно: **PASSED/PASSED/PASSED**, 110.64s/47.42s/47.07s, `PYTEST_EXIT=0` каждый раз. Полный `test_filter_profiles.py -v`: **12 passed in 776.60s**, `PYTEST_EXIT=0` (новый тест — 4-й позиции из 12, соседи без регресса). `Get-Device` до серии → `emulator-5554` | **Open → Fixed** (test-maintainer, критерий готовности п.1 — механизм найден и эмпирически подтверждён, контраст-дверь Г2 доведена до зелёного регресс-замка) |
| 2026-08-16T10:06:17Z | framework (rework поверх критик round1 — B1/B2, unstaged; app-under-test не менялся) | `test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor` x3 изолированно (после B1/B2 rework) + полный `test_filter_profiles.py` (12 тестов) | Изолированно: **PASSED/PASSED/PASSED**, 60.29s/119.65s/58.78s, `PYTEST_EXIT=0` каждый раз. Полный `test_filter_profiles.py -v`: **12 passed in 1564.42s (0:26:04)**, `PYTEST_EXIT=0` (новый узел — 8-я позиция из 12 в этом прогоне, соседи без регресса). `Get-Device` до серии → `emulator-5554` | **Fixed (доработка round1 закрыта)** — B1 (доп. НЕ-WebView оракул на tab-1) и B2 (`finally`-восстановление handle) верифицированы живым прогоном |
| 2026-08-16T10:42:00Z | framework (рабочее дерево, unstaged, идентично состоянию критик round2 — фикс исключительно во фреймворке, `type: test_debt`, B4: новая сборка приложения не требуется; `app-under-test` не менялся) | `test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor` (`@allure.id("AT-BUG-070-g2-contrast-door-non-zero-tab")`, единственный связанный узел — `test_cases: []`, carve-out test_debt/CLAUDE.md «Границы»: замок и есть DoD-артефакт критерия готовности) x1 witness-подтверждающий прогон — критерий готовности уже 6x зелёный (test-maintainer 3x + критик round2 3x), полная регрессия `test_filter_profiles.py` дважды чистая (12/12 оба раза), повторная не требуется | `Get-Device` → `emulator-5554` (DEVICE, позитивная сверка), Appium `/status` → 200. **PASSED**, `1 passed in 77.93s (0:01:17)`, `PYTEST_EXIT=0`. AT-BUG-026 device-liveness guard: recoveries this session = 0/2 (без восстановлений) | **Fixed → Verified** (fix-verifier, D1) — фикс живой и стабильный на 7-м независимом прогоне подряд (3+3+1), рекомендация критик round2 «ПРИНЯТЬ без блокеров» подтверждена device-прогоном |

## Обсуждение

**2026-08-16T10:42:00Z — fix-verifier, D1: Fixed → Verified.** `type: test_debt`
(framework-only фикс, B4 — новая сборка приложения не требуется) —
`test_cases: []` штатно по carve-out CLAUDE.md «Границы» (инфраструктурный
долг фреймворка, привязываемых продуктовых TC в принципе нет; предметный
DoD-артефакт критерия готовности — сам регресс-замок
`test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor`,
исполнен живым device-прогоном, не прочитан). Дифф уже дважды прошёл
критик-вход (round1 ДОРАБОТАТЬ → закрыто, round2 ПРИНЯТЬ без блокеров) —
эта запись не переоткрывает вердикт, только штатно подтверждает
стабильность фикса дополнительным независимым прогоном на текущем рабочем
дереве. `Get-Device` → `emulator-5554` (позитивная сверка, DEVICE), Appium
`/status` → 200 до прогона. Witness:
```
Invoke-Pytest tests/test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor -v
  PASSED, 1 passed in 77.93s (0:01:17), PYTEST_EXIT=0
  AT-BUG-026 device-liveness guard: recoveries this session = 0/2
```
Полная регрессия `test_filter_profiles.py` не повторена в этом ходе —
дважды чисто прогнана ранее в этом же файле (12/12 оба раза, test-maintainer
+ критик round2), задача явно допускала ограничиться witness-прогоном.
`app-under-test/` не тронут. Аналогов рядом не замечено (D-0043) — второй
заблокированный CH-010 mission_leftover (точный Back-замер на deep-link-
вкладке) остаётся отдельным заведением следующего прохода, уже
задокументирован выше как явный остаток, не скрытый аналог этого бага.

**2026-08-16T10:06:17Z — test-maintainer, доработка критик round1 (2 блокера) закрыта, статус остаётся Fixed.**

Критик round1 вернул `Fixed` с ДОРАБОТАТЬ (2 блокера), не rejected — код,
закрывающий оба, был написан той же/следующей headless-сессией, но убит
heartbeat-таймаутом до живого прогона и до обновления этого файла. Этот ход
— верификация уже написанного rework (код читался, не переписывался заново)
+ живые прогоны + обновление документации.

- **B1 (регресс-замок не различал реальную адресацию от sticky-деградации).**
  `test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor`
  под гипотетической регрессией «`in_webview_handle` молча деградировал до
  sticky tab-0» читал бы `assert_webview_handle_url` тем же значением
  `LISTING_FILTERED_URL`, что уже стоит на tab-0 с Given, — тест был бы
  зелёным ДАЖЕ при поломке адресации (вырождался в уже зелёного соседа
  `test_same_url_renderer_navigation_reaches_interceptor`). Закрыто: добавлен
  НЕЗАВИСИМЫЙ НЕ-WebView оракул `app_steps.wait_persisted_tab_url_at(1,
  LISTING_FILTERED_URL, timeout=10)` СРАЗУ ПОСЛЕ WebView-оракула — читает
  persisted `open_tabs_urls` (тот же источник, что уже используется для
  Given/негатива tab-0 в этом же узле), независимый от `window_handles`-
  адресации канал. Новая функция `app_steps.wait_persisted_tab_url_at` —
  опрашивающий вариант уже существующего `assert_persisted_tab_url_at`
  (поллинг нужен: запись в prefs после `shouldOverrideUrlLoading` асинхронна,
  `apply()`), с тем же приёмом диагностики через `holder`/ленивое сообщение,
  что `wait_persisted_tab_count` (AT-BUG-036).
- **B2 (утечка выбранного chromedriver-окна между независимыми вызовами).**
  `in_webview_handle`/`in_webview_matching` оставляли driver переключённым
  на последнее адресованное/проитерированное окно на выходе (включая ОБА
  отказных пути `in_webview_matching` — `NoMatchingWebviewWindow` и
  `AssertionError` на неоднозначности) — следующий независимый
  `contexts.in_webview` на той же chromedriver-сессии молча читал/исполнял
  JS на оставленной, не активной вкладке. Закрыто: `_current_window_handle_
  or_none(driver)` фиксирует УЖЕ выбранное окно НА ВХОДЕ (до переключения;
  `None`, если это первый вызов на сессии — `WebDriverException`,
  восстанавливать нечего), оба примитива восстанавливают его в `finally` —
  покрывает и успешный путь, и оба отказных.

**Witness rework (живые прогоны, `emulator-5554`, синхронно, после
autotest-фикса `framework/core/contexts.py` +
`framework/steps/app_steps.py::wait_persisted_tab_url_at` +
`framework/tests/test_filter_profiles.py`):**
```
Invoke-Pytest tests/test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor -v
  run 1: PASSED, 1 passed in 60.29s, PYTEST_EXIT=0
  run 2: PASSED, 1 passed in 119.65s, PYTEST_EXIT=0
  run 3: PASSED, 1 passed in 58.78s, PYTEST_EXIT=0

Invoke-Pytest tests/test_filter_profiles.py -v  (полный модуль, 12 тестов)
  12 passed in 1564.42s (0:26:04), PYTEST_EXIT=0
```
`framework/steps/app_steps.py::wait_persisted_tab_url_at` уже существовала в
рабочем дереве (та же незакоммиченная сессия) — сверена по `git diff`,
сигнатура/поведение по образцу `assert_persisted_tab_url_at` с поллингом,
доработка не потребовалась. `app-under-test/` за этот ход не тронут.
Пересмотра стратегии/рисков доработка не требует (тот же класс/спека, что
и round1 — только устранение двух конкретных методологических пробелов
внутри уже принятого решения, не новый риск).

**2026-08-16T10:19:00Z — критик round2: ПРИНЯТЬ, без блокеров.** B1
перепроверен трассировкой гипотезы деградации (независимый prefs-канал не
вырождается вместе с адресацией) + собственным живым перепрогоном 3/3. B2
доказан ИСПОЛНЕНИЕМ (не чтением) — device-free проба всех путей выхода
(успех/оба отказа/исключение тела/битый handle/отсутствие entry-окна), 8/8
зелёных, точные последовательности `switch_to.window` сверены. Класс-полнота:
`switch_to.window` во всём репо — только в `contexts.py`, все под `finally`;
`git diff --stat` — 374 insertions/0 deletions (ни одна существующая строка
не тронута), собратьев вне этого файла нет. 4 неблокирующие находки —
батч мелочей (не новый test_debt, D-0043 — точечные методологические
хвосты того же rework, не отдельный класс):
1. `finally`-восстановление (`contexts.py:210,302`) может замаскировать
   исходное исключение, если `switch_to.window(original_handle)` сам
   бросит `WebDriverException` (недостижимо на текущих call-site'ах —
   никто не закрывает вкладки внутри блока).
2. `in_webview_at_tab_position`/`webview_url_at_tab_position`/
   `execute_script_at_tab_position` — ноль call-site'ов, не покрыты живым
   прогоном (только URL-маршрут `webview_handle_for_url` эмпирически
   подтверждён); покрыть прогоном либо снять как мёртвый API.
3. Исполнитель этого rework-хода не приложил `validate_frontmatter.py` к
   witness при правке frontmatter — критик прогнал сам (чисто).
4. При `original_handle is None` (первый вызов на свежей chromedriver-
   сессии) восстановления нет — известный, задокументированный остаток,
   не дефект-сюрприз.

**2026-08-16T06:20:00Z — test-maintainer (B4), Open → Fixed. Критерий
готовности п.1 — механизм найден, эмпирически подтверждён, контраст-дверь
Г2 доведена до зелёного регресс-замка.**

**Найденный механизм.** `driver.contexts`/`switch_to.context(...)`
(Appium-уровень) действительно даёт РОВНО один контекст `WEBVIEW_<pkg>`
независимо от числа живых вкладок и прилипает к вкладке-0 (это и есть сам
долг) — НО chromedriver, однажды подключённый к этому контексту, видит
ОСТАЛЬНЫЕ живые `android.webkit.WebView` того же процесса как отдельные
**окна** (CDP targets) на Selenium-уровне: `driver.window_handles`/
`driver.switch_to.window(handle)` — API, отдельный от Appium `contexts`,
до этого долга нигде в фреймворке не использовавшийся для адресации
конкретной вкладки. Эмпирически подтверждено (живой прогон, эмулятор
`emulator-5554`, 3 вкладки — Home/marker1/marker2, `contexts.
in_webview_matching`, см. докстринг `framework/core/contexts.py`):

- `driver.window_handles` внутри `in_webview` вернул 3 РАЗНЫХ handle;
  `switch_to.window(h)` + `current_url`/`title` на каждом дал 3 РАЗНЫХ
  пары (Home/marker1/marker2) — НЕ одно и то же "прилипшее" значение, как
  при штатном `driver.contexts`-переключении.
- **Изоляция**: JS-глобал (`window.__probe`), записанный на handle
  вкладки 2, НЕ виден на handle вкладки 1 или вкладки 0 (`None`/
  `undefined`) — подтверждает, что это НЕЗАВИСИМЫЕ JS-контексты, не общий
  sticky-объект.
- `window.scrollTo` на handle вкладки 2 НЕ изменил `scrollY`, прочитанный
  на handle вкладки 1 (0 → 0) — та же изоляция для скролла.
- **Стабильность**: набор `window_handles` идентичен (тот же `set`) после
  выхода из `in_webview` (`to_native`) и повторного входа — handle можно
  захватить один раз и переиспользовать между отдельными
  `in_webview`-блоками в рамках одного теста (действие внутри страницы,
  меняющее URL/title, НЕ инвалидирует handle — проверено адресно: захват
  `webview_handle_for_url` ДО `navigate_tab_via_page_js_to`, повторное
  обращение к ТОМУ ЖЕ handle ПОСЛЕ навигации через `in_webview_handle`
  успешно читает новый URL).

Это НЕ `current_url`-угадывание (явно исключено критерием готовности) —
адресация идёт по признаку, известному ЗАРАНЕЕ из независимого источника
(нативный заголовок чипа `TabInfo.title`/`tab_chip_title_at` — тот же
источник, что `document.title`, читается ДО входа в WEBVIEW; либо, когда
заголовки неоднозначны — как оказалось на фикстуре `listing_basic.mitm`,
где отфильтрованная и неотфильтрованная страницы несут ОДИН И ТОТ ЖЕ
`<title>` — известный URL из НЕ-WebView-оракула `app_steps.
assert_persisted_tab_url_at`/`open_tabs_urls`).

**Реализация** (`framework/core/contexts.py`):
`in_webview_matching(driver, predicate, ...)` — общий примитив: внутри
`in_webview` перебирает ВСЕ `window_handles`, матчит `(url, title)`
против `predicate`, бросает `NoMatchingWebviewWindow` при 0 совпадений
(список кандидатов для диагностики) или `AssertionError` при ≥2
(неоднозначность), иначе оставляет driver переключённым на найденное окно.
`in_webview_handle(driver, handle, ...)` — прямая адресация по уже
известному handle (без повторного матчинга), для возврата к ранее
захваченной вкладке после действия, которое могло сменить матчащий
признак. `framework/steps/browser_steps.py` добавляет прикладной слой:
`in_webview_at_tab_position`/`webview_url_at_tab_position`/
`execute_script_at_tab_position` (адресация по нативной позиции чипа —
общий случай), `webview_handle_for_url`/`navigate_tab_via_page_js_to`/
`assert_webview_handle_url` (адресация по известному URL + сохранение
handle через навигацию — случай неоднозначных заголовков, использован
ниже).

**Контраст-дверь Г2 доведена до зелёного регресс-замка** (критерий
готовности, «плюс»-часть): `framework/tests/test_filter_profiles.py::
test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor`
(`@allure.id("AT-BUG-070-g2-contrast-door-non-zero-tab")`) — Given tab-0
несёт применённый профиль; When реальный deep-link открывает tab-1 на
БАЗОВОМ URL (программная дверь `bugs/BUG-070.md`, оракул вне WebView —
`assert_persisted_tab_url_at`, тот же приём, что TC-206); захват
стабильного handle tab-1 по её ИЗВЕСТНОМУ URL (`webview_handle_for_url`
— заголовок здесь неоднозначен, обе фикстурные страницы делят один
`<title>`); When КОНТРАСТ — content-initiated (`window.location.href`)
навигация на тот же URL, адресованная ИМЕННО на tab-1 через захваченный
handle (`navigate_tab_via_page_js_to`); Then URL tab-1 (тот же handle)
становится ОТФИЛЬТРОВАННЫМ (`assert_webview_handle_url`) — content-
initiated дверь ДОХОДИТ до `shouldOverrideUrlLoading` и дописывает
фильтр, в отличие от deep-link, ДАЖЕ на не-нулевой/не-активной по
sticky-прилипанию вкладке; And tab-0 остаётся на своём URL (без
кросс-вкладочной утечки). Узел — регрессионный замок (`@allure.id`
описательный слаг, тот же паттерн, что уже используется соседним
`test_same_url_renderer_navigation_reaches_interceptor` и
`AT-BUG-047-*`), НЕ формальный TC — заведение отдельного TC (если решение
поднять контраст-дверь Г2 до продуктового покрытия R-09) остаётся за
test-designer, `test_cases` этого бага намеренно пуст.

**Точный Back-замер на deep-link-вкладке** (второй из двух заблокированных
CH-010 mission_leftover-пунктов) технически достижим ТЕМ ЖЕ механизмом
(`webview_url_at_tab_position`/`webview_handle_for_url` до и после
программной Back-навигации), но НЕ доведён до кейса этим ходом — критерий
готовности требует «минимум ОДИН из двух», Г2 выше закрывает эту часть
целиком; Back-замер остаётся заведением следующего прохода (test-designer/
test-maintainer), если решение поднять его до покрытия будет принято.

**Witness** (живые прогоны, framework, синхронно, `emulator-5554`,
Appium `:4723`):
```
Invoke-Pytest tests/test_filter_profiles.py::test_content_initiated_navigation_on_non_zero_tab_reaches_interceptor -v
  run 1: PASSED, 1 passed in 110.64s, PYTEST_EXIT=0
  run 2: PASSED, 1 passed in 47.42s, PYTEST_EXIT=0
  run 3: PASSED, 1 passed in 47.07s, PYTEST_EXIT=0

Invoke-Pytest tests/test_filter_profiles.py -v  (полный модуль, 12 тестов)
  12 passed in 776.60s (0:12:56), PYTEST_EXIT=0
```

**Смежная находка (доклад, не расширяю scope, D-0037).** Регрессионный
прогон `framework/tests/test_tabs.py` (полный файл, добровольная сверка —
`contexts.py` разделяемая инфраструктура) на ТОЙ ЖЕ уже давно живой
Appium/эмулятор-сессии дал 2 падения (`test_max_tabs_limit_blocks_11th_tab`,
`test_library_card_open_at_tab_limit_shows_dialog_and_switches_screen`) —
оба `ReadTimeoutError` на ОДНОМ вызове (`execute_script` внутри
`wait_home_page_loaded`), воспроизведено идентично и в изолированном
повторном прогоне (2/2). Диагностика (device жив, Appium `/status` отвечает
200 быстро) совпадает с уже задокументированным и `Verified`-закрытым
классом `bugs/AT-BUG-009.md` («позиционная деградация длинной живой
Appium/эмулятор-сессии»), который сам явно предсказывал рецидив как
основание для `Reopened`. Диффы этого бага (`contexts.py`/
`browser_steps.py`) структурно НЕ трогают `wait_home_page_loaded`/код,
на котором падает `test_tabs.py` (только новые функции добавлены, ни одна
существующая не изменена) — не регрессия этого фикса. Не дубликат, не
новый test_debt (класс уже поимённо покрыт `AT-BUG-009.md`, Verified,
предсказывавшим ровно такой рецидив) — заведена запись `state/
escalations.md` ESC-034 с решением (Reopened `AT-BUG-009` или нет) за
координатором/Lead; `AT-BUG-070`/этот регресс-замок этой находкой НЕ
блокированы (целевой тест использует другой механизм адресации, 3/3
зелёных, никогда не воспроизвёл этот класс).

`app-under-test/` не затронут за весь ход. Пересмотра стратегии/рисков не
требует (та же спека CH-010/R-09, тот же наблюдательный класс, что уже
разбирал test-designer при заведении) — проход test-strategist не нужен.

**[test-designer @ 2026-08-15] Заведено по followup CH-010 (#2).** Источник
— `exploratory-charters/CH-010.md`, `followup_tc[2]` дословно: «Test-gap
инфраструктуры: нужен надёжный приём адресации execute_script/навигации к
КОНКРЕТНОЙ не-нулевой вкладке (sticky WebView context, класс
AT-BUG-018/019/022, блокирует контраст-дверь Г2 через клик по ссылке и
точное измерение Back на deep-link-вкладке)». Один тикет на класс (не два
по числу заблокированных находок) — D-0043 CLAUDE.md, чиним класс, а не
экземпляр: обе грани (контраст-дверь Г2, Back-замер) — один и тот же
недостающий примитив адресации, не два независимых долга.

Проектирование `TC-206` (замок BUG-070, основной deep-link-сценарий) НЕ
блокировано этим долгом — Then кейса построен на двух безопасных оракулах
(`open_tabs_urls` из prefs, нативный UiAutomator2-триггер FilterPanel), ни
один из которых не заходит в WEBVIEW-контекст. `test_cases: []` этого
тикета намеренно пуст — на момент завода он не блокирует НИ ОДИН
спроектированный кейс, только два конкретных `mission_leftover`-пункта
самого чартера (не оформленные отдельными TC).

`app-under-test/` не затронут — только чтение и заведение тикета.
