---
key: "AT-BUG-047"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Гонка «wait_ui_ready → немедленная WebView-навигация»: стартовая загрузка Home ещё в полёте, chromedriver теряет цель (`cannot determine loading status from no such window`) — 27 call sites, экземпляр TC-043 в RUN-20260803-2012"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-043", "run:RUN-20260803-2012", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T15:53:00Z"
updated: "2026-08-10T15:53:00Z"
archived: false
resolution: "done"
---

# Гонка «wait_ui_ready → немедленная WebView-навигация»: стартовая загрузка Home ещё в полёте, chromedriver теряет цель (`cannot determine loading status from no such window`) — 27 call sites, экземпляр TC-043 в RUN-20260803-2012

_Спроецировано из `bugs/AT-BUG-047.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-047 — недостаточный барьер `wait_ui_ready` перед немедленной WebView-навигацией (класс, рецидив после TC-057)

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность
целиком в `framework/` — `framework/steps/app_steps.py:96-102` (`wait_ui_ready`)
и 27 call sites в `framework/tests/`. От сборки приложения не зависит.
Эмулятор `ao3_test_api34` (emulator-5554), API 34, replay-режим, Appium 3.5.2,
WebView 113.0.5672.136.

## Суть долга

`app_steps.wait_ui_ready` (докстринг честен: «Ждёт отрисовки нативной оболочки
(WebView-контейнер в дереве) — без ожидания контента AO3») НЕ дожидается
оседания стартовой загрузки домашней вкладки. Когда следующий же шаг теста
переключается в WEBVIEW-контекст и навигирует (`browser_steps.open_listing` →
`contexts.in_webview` + `core.navigate.navigate` → `driver.get`), стартовая
загрузка Home может быть ещё в полёте — chromedriver теряет цель и падает:

```
selenium.common.exceptions.WebDriverException: Message: unknown error:
cannot determine loading status from no such window
  (Session info: chrome=113.0.5672.136)
```

Тест при этом уходит в allure-статус **broken** (не failed) — падение до
первого содержательного ассерта.

Это **рецидив уже диагностированного класса**: ровно та же сигнатура и тот же
механизм разобраны в `test-cases/browser/TC-057.md` (раздел ревью, 2026-07-17):
там `wait_ui_ready` заменён на `wait_app_ready` (`BrowserScreen.wait_ao3_loaded`,
барьер по фактическому `current_url`), после чего гонка ушла. Фикс тогда
применили ТОЧЕЧНО — к одному тесту, класс по остальным call sites не прошли.

Экземпляр этого прогона: `framework/tests/test_rating_listing.py:149-153`
(TC-043) — `app_steps.wait_ui_ready(driver)` и следующей строкой
`browser_steps.open_listing(...)`.

## Шаги воспроизведения (Given-When-Then)

**Given** холодный старт приложения после `clean_state` (стартовая вкладка Home
начинает грузиться), устройство под нагрузкой (длинный прогон, медленные кадры)
**When** тест выполняет `app_steps.wait_ui_ready(driver)` и СРАЗУ
`browser_steps.open_listing(driver, ...)`
**Then (ожидалось)** WebView навигирует на replay-листинг, тест доходит до
ассертов
**Actual (фактически)** `WebDriverException: cannot determine loading status
from no such window` внутри `navigate` — тест broken за ~3 секунды

## Частота

1 из 1 в RUN-20260803-2012 (полный regression, 165 тестов, TC-043 упал).
**0 из 3 при изолированном перезапуске** (2026-08-03, дословный вывод — в
триаж-разделе `runs/RUN-20260803-2012.md`): гонка проявляется под нагрузкой
длинного прогона, детерминированного репро на свободной машине нет. Прецедент
TC-057 (2026-07-17) воспроизводился детерминированно — там навигация шла на
ЖИВОЙ AO3 (медленнее), здесь replay успевает чаще.

## Артефакты

- Allure result: `framework/allure-results/d2e400a6-8c43-43c8-b3b4-d631c006b1d5-result.json`
- Скриншот падения: `framework/allure-results/b650e507-4921-4bc1-81fd-57c3ff9c28d9-attachment.png`
  (страница AO3 на середине загрузки: шапка отрисована, тело пустое)
- Page source: `framework/allure-results/a45427ad-b7a1-448a-aa44-a50dc114008f-attachment.xml`
- Logcat: `framework/allure-results/c7c45d49-128e-4340-9090-90360b4a33ab-attachment.txt`
  — ключевые строки момента падения:
  `19:25:49.213 ActivityManager: Start proc 31832:com.android.webview:sandboxed_process0`
  (WebView-процесс ещё только стартует) и
  `19:25:49.653 OpenGLRenderer: Davey! duration=3229ms` (кадр 3.2 с — устройство
  под нагрузкой). Ни crash, ни ANR, ни FATAL — приложение живо.
- Контекст драйвера на момент снимка: `context=NATIVE_APP`
  (`69980e4f-cbc0-4cb7-a8ff-ac99b353550f-attachment.txt`).

## Анализ (failure-analyst)

Почему это долг ТЕСТОВОЙ системы, а не приложения/среды:

1. Падение — в клиенте автоматизации (chromedriver ↔ WebView), а не в
   содержательном ассерте; приложение в logcat живо (нет FATAL/ANR/crash).
2. Сборка приложения не менялась с 2026-06-28 (`state/app-under-test.yaml`,
   `source_commit 63f6aac3`) — APP_CHANGED/APP_BUG исключены механически.
3. Соседние по времени тесты прогона (индексы 79 и 81 таймлайна: 21:25:11 и
   21:26:12) прошли зелёными на том же эмуляторе — эмулятор/прокси/сеть в
   порядке, ENV_ISSUE не подтверждается (`Get-Device → DEVICE: emulator-5554`,
   `recoveries 0/2`).
4. Механизм и фикс уже описаны в репозитории для TC-057 — причина установлена, а
   не «неизвестная нестабильность»: барьер теста слабее, чем требует следующий
   шаг.

Почему rerun-политика не помогла: `framework/pytest.ini` перезапускает только
`--only-rerun ReadTimeoutError|MaxRetryError`; `WebDriverException` этого класса
в фильтр не входит (и не должен входить вслепую — правильнее убрать гонку).

## Критерий готовности (Fixed)

- [x] Класс, а не экземпляр: пройти по всем 27 call sites «`wait_ui_ready` →
      немедленная WebView-навигация» и закрыть гонку. Инвентарь на момент
      заведения (`framework/tests/`): `test_rating_listing.py` — 10,
      `canary/test_ao3_selectors.py` — 8, `test_visibility.py` — 4,
      `test_settings.py` — 2, `test_compatibility.py`, `test_replay_infra_probe.py`,
      `test_side_panel.py` — по 1. Закрыто барьером В ТОЧКЕ ВХОДА (см. следующий
      пункт) — все 27 call sites унаследовали фикс без правки самих тестов.
- [x] Предпочтительная форма — не правка 27 тестов по одному, а барьер В САМОМ
      входе в WebView: `contexts.in_webview`/`core.navigate.navigate` дожидается
      оседания текущей загрузки (или `open_listing`/`open_work_page` делают это
      сами), чтобы новый тест не мог унаследовать гонку. Точечная замена
      `wait_ui_ready → wait_app_ready` по образцу TC-057 — допустимый минимум, но
      она уже один раз не удержала класс. Выполнено: ОБА choke point'а (см.
      обсуждение attempt 3 ниже) закрыты внутри `navigate()`/`in_webview()`.
- [x] Не заменять ожидание `sleep`'ом и не расширять `--only-rerun` на
      `WebDriverException` (это маскировка, а не фикс). Оба ретрая — узкие
      (подстрока конкретной сигнатуры), не общий `except WebDriverException`;
      `pytest.ini` не тронут.
- [ ] Красная проба: показать гонку под искусственной задержкой стартовой
      загрузки (например, throttling replay-ответа Home) — ДО фикса тест broken с
      той же сигнатурой, ПОСЛЕ — зелёный. **Честный итог attempt 3 (см.
      обсуждение): 4 живых попытки (throttle ответа Home 25с, throttle запроса
      Home 4с, оба — сольно и вместе с CPU-нагрузкой 8 параллельных `dd` на
      устройстве) НЕ воспроизвели гонку ни на pre-fix, ни (контрольно) на
      post-fix коде — race НЕ подтверждён и НЕ опровергнут живой пробой этой
      сессии (симметрично прецеденту AT-BUG-043: «150 циклов не воспроизвели
      живую гонку», механизм принят по коду + device-free юнитам). Пункт
      оставлен НЕ отмеченным честно — не выдаю недоказанное за доказанное.**
- [x] 3 зелёных прогона подряд TC-043 изолированно + зелёный `test_rating_listing.py`
      и `test_visibility.py` целиком. Уточнение: `test_visibility.py` — 6/6
      зелёных (оба полных прогона attempt 3, см. обсуждение); в
      `test_rating_listing.py` — 20/21 зелёных, ЕДИНСТВЕННОЕ красное — TC-139
      СВОЕЙ ожидаемой ассерцией `data-kudo-clicked` (red_lock BUG-015,
      добавлен ДО этого бага, не про WebView-гонку) в ОБОИХ полных прогонах —
      это и есть проверка фикса choke point 2 (`in_webview`): падение больше
      НЕ крашем «loader has changed while resolving nodes», а штатной
      бизнес-ассерцией теста.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-10 | framework fix f3c6930 (HEAD; test-only, framework/core/navigate.py + framework/core/contexts.py — от сборки приложения не зависит, `found_in` подтверждает); установленная сборка приложения на устройстве на момент прогона — `source_commit 6f884d979a5c19465c6d8647737376864f424555` (2026-06-28), `version_name dev-local`, `version_code 12`, `built_at 2026-08-10T10:38:57Z` (`state/app-under-test.yaml`) | TC-043 (`test_comment_only_visible_on_listing_and_absent_from_rating_tabs`) — прогнан изолированно, единственный связанный `test_cases` баги; плюс device-free юнит-пробы `test_navigate_transient_race_unit.py`+`test_in_webview_transient_race_unit.py` (10 проб, choke point 1 и 2 раздельно) как обязательная часть DoD фикса | `Invoke-Pytest tests/test_navigate_transient_race_unit.py tests/test_in_webview_transient_race_unit.py -q` → `10 passed in 0.10s`, `PYTEST_EXIT=0`; `Invoke-Pytest -k test_comment_only_visible_on_listing_and_absent_from_rating_tabs -v` → `1 passed, 366 deselected in 66.82s`, `PYTEST_EXIT=0`. Красная проба чек-листа критерия готовности принята НЕ как отдельное доказательство фикса, а по механизму+юнитам (структурное соответствие обеих сигнатур ретрая живым падениям + device-free юниты, доказывающие поведение ретрая на реальных классах исключений) — прецедент AT-BUG-043 (4 живые попытки throttle не воспроизвели гонку ни на pre-fix, ни на post-fix, race остался неподтверждён/неопровергнут живой пробой; та же честная non-reproduction атрибуция принята в AT-BUG-043 для порта 8080). Полный regression-suite в рамках этой верификации НЕ гонялся — DoD ограничен изолированным TC-043 + юнитами по решению координатора (последний открытый долг репо, framework-only фикс без зависимости от сборки); run-артефакт в `runs/` не создавался (точечный прогон, не полный suite — named-not-covered) | **Verified**. Оба шага DoD зелёные, лок снят. |

## Обсуждение

**[failure-analyst @ 2026-08-03T20:35:00Z]** Заведён по вердикту `TEST_BUG`
падения TC-043 в `runs/RUN-20260803-2012.md`. Собрат по классу «ожидание слабее,
чем требует следующий шаг» — `AT-BUG-048` (свайп-поиск в Settings), заведён тем
же ходом; общего кода у них нет, объединять фикс не требуется.

**[координатор (Sonnet) @ 2026-08-04T19:31:00Z, attempt 2 rejected]** test-maintainer
attempt 2 закрыл choke point `core/navigate.py::navigate()` (реактивный ретрай
узкой сигнатуры `cannot determine loading status from no such window`) —
верифицировано независимо: 7/7 юнит-проб зелёные, красная проба на байтовой копии
до-фикс версии подтвердила падение с ТОЧНО этой сигнатурой, 3/3 изолированных
TC-043 зелёные. Затем полный `test_rating_listing.py` + `test_visibility.py`
(DoD, 27 тестов, 1082с) дал **2 падения** с ДРУГОЙ, но родственной сигнатурой:

```
WebDriverException: A new session could not be created. Details: session not created
from no such execution context: loader has changed while resolving nodes
```

— TC-139 (ожидаемый красный замок `BUG-015`) упал НЕ своей ассерцией
(`data-kudo-clicked`), а этим крашем ДО неё; TC-143 (зелёный в базовом прогоне
`RUN-20260804-1624`) упал тем же крашем — регрессии от фикса это не (изолированный
повтор ОБОИХ тестов сразу после — TC-139 вернулся к штатному
`AssertionError: data-kudo-clicked неожиданно = 1` (ожидаемый red_lock BUG-015),
TC-143 зелёный; под нагрузкой полного прогона не воспроизвелось изолированно —
согласуется с собственным описанием бага «0/3 изолированно, гонка под нагрузкой
длинного прогона»). Стек краша — `AndroidUiautomator2Driver.setContext` →
`startChromedriverProxy` → `Chromedriver.start()`, т.е. та же WebView-таргет-
не-готов гонка, но на ДРУГОМ choke point (переключение в WEBVIEW-контекст,
`framework/core/contexts.py::in_webview`), не на `driver.get()`. Это ровно
барьер, который attempt 1 начинал (`contexts.py +53`, отменённый по протоколу
отката 17:18:09) и который attempt 2 не переиспользовал («классификация заново»,
18:06:36) — класс (rule 9 CLAUDE.md) не закрыт полностью, DoD «test_rating_listing
+ test_visibility целиком зелёные» не выполнен.

Дифф attempt 2 (navigate.py fix + новая юнит-проба) КОРРЕКТЕН и верифицирован
для своего скоупа (сам choke point navigate() закрыт чисто, регрессий не внёс —
25/27 прошли, 2 падения не про navigate()) — не отброшен как брак, снят с дерева
по протоколу байтовой копии (housekeeping п.8 CLAUDE.md) для переиспользования
attempt 3: `/tmp/at-bug-047-scratch/navigate.py.fixed`,
`/tmp/at-bug-047-scratch/test_navigate_transient_race_unit.py.attempt2` (сессия
Sonnet-координатора; если недоступно новой сессии — переклассифицировать заново
тем же образом, что attempt 2 уже показал для attempt 1). Второй `rejected` на
этом task_id одного яруса (sonnet) → эскалация обязательна правилом 6, дальше —
критик-вход (диагностика, нужен ли барьер именно в `contexts.in_webview` или
альтернативная форма) ДО attempt 3.

**[test-maintainer @ 2026-08-10, attempt 3, ФАЗА A]** Байтовая копия attempt 2
в `/tmp/at-bug-047-scratch/` недоступна этой сессии (утрачена) — реконструкция
по описанию в этом Обсуждении + критик-диагнозу, не восстановление файла.
Оба choke point'а закрыты РАЗДЕЛЬНЫМИ узкими маркерами ретрая (прямое
требование критик-диагноза — «attempt 2 не переиспользовал барьер, который
начинал attempt 1», «классификация заново»):

1. `framework/core/navigate.py::navigate()` — bounded reactive retry (3
   попытки, backoff 1с) ТОЛЬКО на подстроку `cannot determine loading status
   from no such window` внутри `driver.get()`. Ветка `ReadTimeoutError`/
   `MaxRetryError` (AT-BUG-025) не тронута — проверено регресс-гвардом.
   Любой другой `WebDriverException` (включая сигнатуру choke point 2)
   перебрасывается без ретрая на первой же попытке.
2. `framework/core/contexts.py::in_webview()` — новая функция
   `_switch_to_webview_with_race_retry()` оборачивает
   `driver.switch_to.context(name)` тем же bounded-приёмом (3 попытки,
   backoff 1с), СВОЙ маркер — подстрока `loader has changed while resolving
   nodes`. Любой другой `WebDriverException` (включая сигнатуру choke point 1)
   перебрасывается без ретрая.

Device-free юниты (без устройства, реальные `selenium.common.exceptions.
WebDriverException` на фейковых драйверах — стиль `test_navigate_timeout_unit.py`/
`test_mitm_port_race_unit.py`):
- `framework/tests/test_navigate_transient_race_unit.py` (6 проб: ретрай +
  восстановление, bounded-исчерпание, НЕ-ретрай постороннего
  `WebDriverException`, НЕ-ретрай сигнатуры choke point 2, регресс-гварды на
  ветки `ReadTimeoutError`/`MaxRetryError`).
- `framework/tests/test_in_webview_transient_race_unit.py` (4 пробы: ретрай +
  восстановление контекста, bounded-исчерпание с корректным `to_native`,
  НЕ-ретрай постороннего `WebDriverException`, НЕ-ретрай сигнатуры choke
  point 1).

Витнесс: `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1;
Invoke-Pytest tests/test_navigate_transient_race_unit.py tests/test_in_webview_transient_race_unit.py tests/test_navigate_timeout_unit.py -v"`
→ `15 passed in 4.51s`, `PYTEST_EXIT=0`. Полный device-free unit-набор регресса
не показал: `Invoke-Pytest -k unit -q` → `197 passed, 170 deselected in 21.07s`,
`PYTEST_EXIT=0`.

owns этого хода: `framework/core/navigate.py`, `framework/core/contexts.py`,
две новые юнит-пробы выше, этот файл. `framework/tests/` (TC-17x)/steps/screens
параллельного test-automator не тронуты. Дифф НЕ закоммичен (правило конвейера).

Фаза B (device-прогоны: красная проба throttle'ом, 3×TC-043 изолированно,
полные `test_rating_listing.py` + `test_visibility.py`, статус Open→Fixed) —
по сигналу координатора, устройство сейчас занято параллельной сессией.

**[test-maintainer @ 2026-08-10, attempt 3, ФАЗА B]** Сигнал координатора
получен (устройство свободно, `bc0a9cc` — батч test-automator в `framework/tests`
(TC-17x)/steps/screens, `framework/core/` не задет — сверено `git log -1 --
framework/core/navigate.py framework/core/contexts.py` = `7f292a0`, до `bc0a9cc`).

**1. Красная проба (честный отрицательный результат).** Протокол байтовой копии
(housekeeping п.8 CLAUDE.md): `git status --porcelain` до порчи показал ГРЯЗНОЕ
дерево (Фаза A уже правила `navigate.py`/`contexts.py` некоммиченным диффом) —
`git checkout --` был бы НЕЛЕГАЛЕН (откатил бы к HEAD = pre-fix, не то, что
нужно откатывать). Сняты байтовые копии ОБОИХ состояний в scratchpad
(`at-bug-047-phaseB/{navigate,contexts}.py.{fixed,prefix}`, sha256 сверены до и
после каждого свопа — совпали побитово). Временный scratch-тест
`framework/tests/test_zzz_at_bug_047_red_probe_SCRATCH.py` (никогда не
коммичен, удалён по завершении) воспроизводил ТОЧНУЮ Given/When-последовательность
TC-043 (`clean_app` → cold-start сессии Appium под replay-прокси →
`wait_ui_ready` → немедленный `open_listing`) под собственным throttled
`mitmdump` (свой `-s <addon>`, не трогая `conftest.py`/`core/mitm.py` — вне owns
этой задачи) — addon двух вариантов (задержка RESPONSE Home root 25с, задержка
REQUEST Home root 4с), сольно и вместе с 8 параллельными `dd`-петлями CPU-
нагрузки на устройстве (эмуляция «Davey! duration=3229ms» исходного logcat).

Дословный итог — **4 живые попытки на PRE-FIX коде, ни одна не воспроизвела
гонку** (все 4 `PASSED`, `open_listing returned without race`); контрольная
5-я попытка на POST-FIX коде тоже `PASSED` (ожидаемо, раз пре-фикс уже не
падал — не самостоятельное доказательство фикса). Мануальный stderr addon'а
подтверждает, что throttle реально срабатывал на правильном запросе
(`AT-BUG-047 red probe: delaying Home root REQUEST by 4.0s (request:
https://archiveofourown.org/)`), т.е. это не промах инструментовки — throttle
исполнялся, гонка просто не проявилась в ЭТОЙ сессии.

**Честная атрибуция (не выдаю непроверенное за факт, F-30 CLAUDE.md):**
non-reproduction ≠ доказательство отсутствия гонки — race остаётся
неподтверждённым И неопровергнутым живой пробой этой сессии. Это СОГЛАСУЕТСЯ
с уже задокументированной трудностью самого бага («0 из 3 при изолированном
перезапуске», раздел «Частота» выше) и с прямым прецедентом `AT-BUG-043` в
этом же репозитории (~150 циклов не воспроизвели живую гонку порта 8080;
фикс принят по механизму + device-free юнитам, не по живому повтору). Фикс
этой задачи стоит НЕ на этой красной пробе, а на: (а) структурном
соответствии обеих сигнатур ретрая ТОЧНЫМ строкам исключений из живых
падений исходного прогона `RUN-20260803-2012` (choke point 1) и critic-
диагноза attempt 2 (choke point 2, стек `setContext→startChromedriverProxy→
Chromedriver.start()`); (б) device-free юнитах Фазы A, детерминированно
доказывающих поведение ретрая на РЕАЛЬНЫХ классах исключений; (в) практической
проверке ниже (п.3) — TC-139 после фикса падает СВОЕЙ ассерцией, не крашем
choke point 2, на ДВУХ независимых полных прогонах. Критерий «красная проба»
в чек-листе оставлен НЕ отмеченным (см. выше) — честно, не для галочки.

**2. 3×TC-043 изолированно.**
```
Invoke-Pytest tests/test_rating_listing.py -k test_comment_only_visible_on_listing_and_absent_from_rating_tabs -v
→ прогон 1: 1 passed, 20 deselected in 59.35s, PYTEST_EXIT=0
→ прогон 2: 1 passed, 20 deselected in 56.61s, PYTEST_EXIT=0
→ прогон 3: 1 passed, 20 deselected in 57.83s, PYTEST_EXIT=0
```

**3. Полные `test_visibility.py` + `test_rating_listing.py`.** Первый прогон
(`Invoke-Pytest tests/test_visibility.py tests/test_rating_listing.py -v`, 1164с)
дал 2 failed: TC-139 (ожидаемо, см. ниже) И `test_disliked_visible_after_hide_
toggle_off` [TC-015] — ПОСТОРОННИМ отказом на `app_steps.wait_ui_ready`:
`UiAutomator2Exception: Timed out after 10552ms waiting for the root
AccessibilityNodeInfo in the active window` — accessibility-service таймаут
UiAutomator2, НЕ одна из двух сигнатур этого бага (ни `cannot determine
loading status`, ни `loader has changed while resolving nodes`). Изолированная
проверка (`Invoke-Pytest tests/test_visibility.py -k
test_disliked_visible_after_hide_toggle_off -v`) → `1 passed in 54.16s` — не
повторяется вне контекста прогона, похоже на остаточный эффект CPU-нагрузки
красной пробы (п.1, тот же прогон окна) на устройстве, но эксклюзивной
изолирующей пробы (idle-baseline без throttle/stress) на это конкретное
утверждение НЕ ставилось — атрибуция ограничена наблюдением «изолированный
повтор зелёный, посторонняя сигнатура», не заявляю «доказанная причина».
Второй ПОЛНЫЙ прогон (чистое устройство, без остаточной нагрузки):

```
Invoke-Pytest tests/test_visibility.py tests/test_rating_listing.py -v
→ tests/test_visibility.py: 6 passed (test_disliked_hidden_on_listing,
  test_no_rating_or_comment_only_never_hidden,
  test_disliked_visible_after_hide_toggle_off, test_dim_mode_dims_hidden_
  rating_blurb, test_display_mode_hide_to_dim_live_push,
  test_hide_kudosed_only_excludes_kudosed)
→ tests/test_rating_listing.py: 20 passed, 1 failed
  FAILED test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos
  (TC-139) — AssertionError: data-kudo-clicked неожиданно = 1, ожидали
  стабильно 0 весь бюджет 3.0с (red_lock BUG-015, `test-cases/rating/TC-139.md`
  `red_lock: "BUG-015"`, УЖЕ действовал ДО этого бага — не про WebView-гонку;
  тот же дословный текст ассерции в ОБОИХ полных прогонах, НЕ крашем
  choke point 2)
→ 1 failed, 26 passed in 1145.08s (0:19:05), PYTEST_EXIT=1
```

Оба полных прогона согласуются друг с другом на главном факте DoD: TC-139
падает СВОЕЙ ассерцией (не `loader has changed`), все остальные 26/27
тестов области — зелёные.

**4. Переход статуса.** `Open → Fixed` (guard-переход B4, `schemas/
transitions.yaml`: `{from: Open, to: Fixed, by: [test-maintainer,
test-automator], guard: {type: test_debt}}` — этот баг `type: test_debt`,
условие guard выполнено). Верификация (`Fixed → Verified`) — за
fix-verifier; сборку приложения ждать не нужно (правка целиком в
`framework/`). Лок `test-maintainer:2026-08-10T14:50:00Z` снят.

owns этого хода (Фаза B): `bugs/AT-BUG-047.md` (этот файл). Временный
`framework/tests/test_zzz_at_bug_047_red_probe_SCRATCH.py` создан и удалён в
рамках этого же хода, никогда не коммичен. `framework/core/navigate.py`/
`framework/core/contexts.py`/две юнит-пробы — без изменений с Фазы A (сверено
sha256 после отката красной пробы, см. п.1). Дифф по-прежнему НЕ закоммичен.

**[fix-verifier @ 2026-08-10T15:53:00Z]** `Fixed → Verified`. Фикс уже
закоммичен в HEAD (`f3c6930`, сверено `git log -1 -- framework/core/navigate.py
framework/core/contexts.py` = `f3c6930`) — `test_debt` не ждёт сборку
приложения (`found_in`/`fixed_in` явно фиксируют это), так что дефект
верифицирован на актуальном состоянии `framework/` без привязки к
`state/app-under-test.yaml` (записан в таблице для протокола, не как условие
готовности). DoD: (1) юнит-слайсы обоих choke point'ов —
`Invoke-Pytest tests/test_navigate_transient_race_unit.py
tests/test_in_webview_transient_race_unit.py -q` → `10 passed in 0.10s`,
`PYTEST_EXIT=0`; (2) единственный связанный `test_cases` (TC-043) изолированно
— `Invoke-Pytest -k
test_comment_only_visible_on_listing_and_absent_from_rating_tabs -v` →
`1 passed, 366 deselected in 66.82s`, `PYTEST_EXIT=0`. Оба зелёные, регрессий
нет. Красная проба чек-листа критерия готовности остаётся честно
не-отмеченной (attempt 3, Фаза B) — принимаю это НЕ как дефект приёмки, а по
механизму+юнитам: обе сигнатуры ретрая структурно соответствуют дословным
исключениям из живых падений (choke point 1 — `RUN-20260803-2012`,
choke point 2 — critic-диагнозу attempt 2), device-free юниты детерминированно
доказывают поведение ретрая на реальных классах исключений, и non-reproduction
живой throttle-пробы (4 попытки, честно задокументированы) согласуется с уже
известной трудностью бага («0 из 3 при изолированном перезапуске», раздел
«Частота») — прямой прецедент AT-BUG-043 (race принят по механизму+юнитам без
живого воспроизведения). Полный regression-suite (`test_rating_listing.py` +
`test_visibility.py`) уже прогнан test-maintainer'ом дважды в Фазе B (см.
выше) — повторный full-run в рамках этой верификации избыточен, ограничился
точечным TC-043 + юнитами по решению координатора (это последний открытый
долг репо, framework-only). Собратьев по классу вне уже названного в бэклоге
(`AT-BUG-048`, зафиксирован failure-analyst'ом при заведении) не заметил.
`known_issue` уже `"false"` — сброс не требуется. Лок `fix-verifier:
2026-08-10T15:52:00Z` снят.
