---
id: AT-BUG-084
title: "in_webview choke point 2 (AT-BUG-047, Verified) рвётся НОВОЙ сигнатурой 'No such context found.' — не входит в _WEBVIEW_SWITCH_RACE_SIGNATURES, ретрай обрывается на 2-й попытке"
type: test_debt
debt_kind: flaky_test
severity: major
status: Verified
found_in: "test-maintainer, AT-BUG-082 regression pass (2 подряд test_downloads.py после fix, run 2/2, 2026-08-17)"
fixed_in: "framework/core/contexts.py (_WEBVIEW_SWITCH_RACE_SIGNATURES расширен
  третьей сигнатурой 'No such context found.'), framework/tests/test_in_webview_transient_race_unit.py
  (_webview_switch_race_exc_no_such_context + parametrize обеих race-проб) —
  test-maintainer, 2026-08-17"
last_seen_in: "run 2/2, tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off (TC-112), 2026-08-17T06:00Z (примерно, см. вывод прогона)"
test_cases: ["TC-112"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-18T05:20:00Z"
updated: "2026-08-18T05:20:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: "AT-BUG-084 B4: третья сигнатура choke point 2
  (NoSuchContextException: 'No such context found.') добавлена в
  _WEBVIEW_SWITCH_RACE_SIGNATURES (framework/core/contexts.py) — классовое
  расширение существующего набора, тот же bounded-ретрай механизм, новый
  механизм не вводился. Красная проба эмпирически подтверждена (см.
  «Верификация»): 2 новых device-free юнит-теста реально падали на pre-fix
  наборе сигнатур (не только логическим рассуждением), зелены на post-fix.
  TC-112 зелёный 3/3 изолированных живых прогона подряд (гонка на этой
  конкретной сигнатуре в этих 3 прогонах не встретилась — честно отмечаю:
  не наблюдалась, не 'подтверждена' — тест просто прошёл штатным путём без
  захода в ретрай-ветку)."
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-084 — `_switch_to_webview_with_race_retry` не распознаёт сигнатуру «No such context found.», ретрай обрывается досрочно

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/core/contexts.py::_switch_to_webview_with_race_retry`/
`_WEBVIEW_SWITCH_RACE_SIGNATURES` (AT-BUG-047 choke point 2, статус этого бага —
`Verified`, закрыт). Эмулятор `emulator-5554`, API 34.

## Обнаружено

ПОПУТНО при регресс-верификации `AT-BUG-082` (2 подряд прогона полного
`tests/test_downloads.py` после фикса `assert_work_not_in_files_tab`). Прогон
1/2 — `17 passed in 1698.05s`, зелёный (включая TC-112 — фикс AT-BUG-082
подтверждён на этом прогоне). Прогон 2/2 — `1 failed, 16 passed in 1616.84s`,
упал ТОТ ЖЕ узел TC-112, но НА СОВЕРШЕННО ДРУГОМ шаге и с ДРУГИМ классом
ошибки — не в `library_steps.assert_work_not_in_files_tab` (код, изменённый
AT-BUG-082), а в САМОМ ПЕРВОМ шаге теста, `app_steps.wait_app_ready`:

```
app_steps.py:140: in wait_app_ready
    return BrowserScreen(driver).wait_ao3_loaded()
core\contexts.py:157: in in_webview
    _switch_to_webview_with_race_retry(driver, name)
core\contexts.py:107: in _switch_to_webview_with_race_retry
    driver.switch_to.context(name)
appium.common.exceptions.NoSuchContextException: Message: No such context found.
```

Captured log call (WARNING):

```
AT-BUG-047 choke point 2 (in_webview/_switch_to_webview_with_race_retry):
попытка 1/3 провалена транзиентной сигнатурой 'uniqueContextId not found', ретраю
```

Ровно ОДНА строка ретрая (попытка 1/3 совпала с известной сигнатурой
`uniqueContextId not found` и ретраилась штатно) — но попытка 2 упала с ДРУГИМ
текстом («No such context found.», `NoSuchContextException`), который НЕ входит
в `_WEBVIEW_SWITCH_RACE_SIGNATURES = ("loader has changed while resolving
nodes", "uniqueContextId not found")` — `_matched_webview_switch_race_signature`
вернул `None`, код переброшен НЕМЕДЛЕННО (`if matched_signature is None: raise`),
не исчерпав оставшийся бюджет (2 попытки из 3 неиспользованы).

## Анализ (предварительный, не входит в мандат AT-BUG-082)

Этот failure НЕ относится к фиксу `AT-BUG-082` — `assert_work_not_in_files_tab`
(и вообще `library_steps`) в этом падении не участвует вовсе, тест упал на
`Given`-шаге ДО первого захода на work-страницу. Тот же choke point 2, что
`AT-BUG-047` (переключение в WEBVIEW-контекст гонится со стартом
chromedriver-прокси, пока стартовая загрузка Home ещё не осела) — но
ТРЕТЬЯ, ранее не задокументированная сигнатура того же транзиентного отказа
хендшейка (`NoSuchContextException: No such context found.` — по всей
видимости, гонка застигла прокси-старт в ЕЩЁ более раннем/позднем окне,
чем два уже известных случая). `AT-BUG-047` закрыт (`status: Verified`) —
не переоткрываю сам (решение по диспетчеризации/переоткрытию — за Lead),
только доклад + новый баг (тот же паттерн, что использован в
`bugs/AT-BUG-081.md`/`bugs/AT-BUG-083.md` этой сессии).

Единственное известное наблюдение — 1 инстанс на 34 прогона тестов
`test_downloads.py` в этой сессии (17 тестов × 2 прогона). Недостаточно для
классификации по правилу fail-fast (нужны 2 ИДЕНТИЧНЫХ env-класса фейла на
ОДНОМ И ТОМ ЖЕ вызове/шаге — здесь пока один инстанс, но с ДВУМЯ разными
сигнатурами внутри одного падения) — среда не помечается деградировавшей,
но сигнатура заслуживает добавления в `_WEBVIEW_SWITCH_RACE_SIGNATURES`
(классовая правка по образцу существующего набора, D-0043).

## Критерий готовности (Fixed)

- [x] Добавить `"No such context found."` (или более узкий фрагмент, если
      полная строка избыточно широка) в `_WEBVIEW_SWITCH_RACE_SIGNATURES`
      (`framework/core/contexts.py`) — классовое расширение уже существующего
      набора, не новый механизм.
- [x] Device-free unit-регресс (по образцу существующих проб choke point 2,
      если такие есть в `framework/tests/test_*_unit.py`) — мок
      `driver.switch_to.context`, поднимающий `NoSuchContextException` с этим
      текстом на первой попытке, должен ретраиться и в итоге пройти.
- [x] Живой регресс — TC-112 (и в идеале весь `test_downloads.py`) зелёный.
- [x] Проверить, не появлялась ли эта сигнатура и в других логах/прогонах
      сессии (сиблинг-инстансы того же класса) — если да, дописать сюда как
      факт, не заводить дубль.

## Верификация

**Правка.** `_WEBVIEW_SWITCH_RACE_SIGNATURES` (`framework/core/contexts.py`)
расширен третьим элементом `"No such context found."` (полная строка не
избыточно широка — она НЕ является подстрокой ничего постороннего в кодовой
базе, оставлена как есть, без сужения). Докстринг модуля и inline-комментарий
над кортежем дополнены абзацем про рецидив AT-BUG-084 (тот же паттерн, что
уже использован для двух предыдущих сигнатур).

**Различающий сигнал (критик-урок этой сессии — не полагаться на логическое
рассуждение вместо эмпирики):** добавлены 2 новых parametrize-кейса
(`no-such-context-found`, exc_factory =
`_webview_switch_race_exc_no_such_context`, поднимает РЕАЛЬНЫЙ
`appium.common.exceptions.NoSuchContextException("No such context found.")`)
в `framework/tests/test_in_webview_transient_race_unit.py`, в оба
существующих теста choke point 2
(`test_in_webview_retries_and_recovers_from_race_signature`,
`test_in_webview_race_retry_bounded_reraises_after_exhaustion`). Красная проба
ПОДТВЕРЖДЕНА ЭМПИРИЧЕСКИ: временно откачен ТОЛЬКО фикс сигнатур (кортеж
вернул к 2 элементам, тестовый файл с новыми кейсами оставлен как есть,
byte-copy pre-edit версии `contexts.py` сохранена в scratchpad ДО отката,
восстановлена после — `git status --porcelain` пуст на файле и до, и после,
откат/восстановление byte-copy, не `git checkout`), прогон дал реальный
RED:
```
tests/test_in_webview_transient_race_unit.py::test_in_webview_retries_and_recovers_from_race_signature[no-such-context-found] FAILED
tests/test_in_webview_transient_race_unit.py::test_in_webview_race_retry_bounded_reraises_after_exhaustion[no-such-context-found] FAILED
...
E   appium.common.exceptions.NoSuchContextException: Message: No such context found.
...
E   AssertionError: ретрай обязан быть bounded ровно 3 попытками, получили 1
2 failed, 6 deselected in 0.40s
PYTEST_EXIT=1
```
т.е. pre-fix код действительно перебрасывает `NoSuchContextException`
немедленно (1 попытка вместо 3) — тот же класс отказа, что в живом падении
TC-112. После восстановления фикса — GREEN:
```
tests/test_in_webview_transient_race_unit.py::test_in_webview_retries_and_recovers_from_race_signature[no-such-context-found] PASSED
tests/test_in_webview_transient_race_unit.py::test_in_webview_race_retry_bounded_reraises_after_exhaustion[no-such-context-found] PASSED
8 passed in 0.10s
PYTEST_EXIT=0
```

**Device-free unit-сьют (полный device-free срез после правки):**
```
313 passed, 191 deselected, 3 warnings in 26.33s (tests -k unit)
PYTEST_EXIT=0
```
(3 предсуществующих warning'а — AT-BUG-026 device-liveness guard pending-recovery,
не относятся к этому фиксу.)

**Живой регресс — TC-112 изолированно, 3 прогона подряд
(emulator-5554, каждый отдельным вызовом `Invoke-Pytest`):**
```
run 1: 1 passed in 100.03s (0:01:40), PYTEST_EXIT=0
run 2: 1 passed in 98.19s  (0:01:38), PYTEST_EXIT=0
run 3: 1 passed in 103.17s (0:01:43), PYTEST_EXIT=0
```
Честная оговорка (не выдаю отсутствие противоречия за подтверждение
механизма): ни в одном из этих 3 прогонов ретрай choke point 2 НЕ
срабатывал ни на одной сигнатуре (гонка транзиентна, окно — единицы секунд,
воспроизводится не каждый раз — так же, как в оригинальном обнаружении
AT-BUG-047/AT-BUG-084, где инстанс был 1 на 34 прогона). Три прогона зелёные
штатным путём, БЕЗ захода в ретрай-ветку — это удовлетворяет DoD-протокол
«3 зелёных подряд» (тест остаётся исправным после правки), но НЕ то, что
новая сигнатура была живьём поймана и отретраена постфактум — вклад правки
в устойчивость к реальной гонке этими 3 прогонами не проверен (ни один не
столкнулся с гонкой вообще). Различающий witness именно фикса — device-free
красная/зелёная проба выше, не эти 3 живых прогона.

**fix-verifier D1, 2026-08-18.** Долг фреймворка (`type: test_debt`) — верификация
не ждёт новую сборку приложения (правило D1 rules.yaml, B4), прогон на текущей
рабочей копии `framework/`.

Device-free unit-регресс, изолированный файл:
```
tests/test_in_webview_transient_race_unit.py ........ [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
8 passed in 0.42s
PYTEST_EXIT=0
```
Все 8 узлов зелёные, среди них оба заявленных новых parametrize-кейса
(`id=no-such-context-found`) в
`test_in_webview_retries_and_recovers_from_race_signature` и
`test_in_webview_race_retry_bounded_reraises_after_exhaustion` — прочитаны
дословно в `framework/tests/test_in_webview_transient_race_unit.py` (строки
137-142, 166-168, 194-196), присутствуют как заявлено.

Живой TC-112, изолированный spot-check (emulator-5554, API 34; свежий
эмулятор потребовал `Install-MitmCA` + повторный `Install-App` — package-
service после CA-триггернутого framework-рестарта не сразу принял `adb
install`, первая попытка упала `NullPointerException:
PackageManagerInternal.freeStorage` — env-глитч холодного старта, не
связан с фиксом, вторая попытка Install-App штатно `Success`):
```
tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off[placeholder_seeded_work0-work_with_download.mitm] .  [100%]
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
1 passed in 50.57s
PYTEST_EXIT=0
```
Как и в 3 прогонах test-maintainer'а, ретрай choke point 2 в этом spot-check
не сработал (гонка транзиентна) — прогон подтверждает, что тест остаётся
исправным после правки, не то, что новая сигнатура поймана живьём постфактум
(та же честная оговорка, что в записи test-maintainer'а выше).

Противоречий не найдено — оба прогона зелёные, `status: Verified`.

`python scripts/validate_frontmatter.py` (координатор, N1 мини-критик-входа
D1 — витнесс был заявлен диспатчу, но не записан в артефакт): `ошибок 0,
предупреждений 0`, `EXIT=0`.

**Пункт 4 критерия (сиблинг-инстансы в логах сессии) — проверено, дубль не
заведён:** `Grep "No such context found"` по `runs/` (10 файлов-хитов) и по
`bugs/` (только сам AT-BUG-084.md). Все 10 хитов в `runs/` — это НЕ фактически
поднятые исключения, а совпадение с ЛИТЕРАЛЬНОЙ СТРОКОЙ ИСХОДНОГО КОДА
appium-библиотеки (`error_handler.py`: `if message == 'No such context
found.':`), встроенной как фрагмент трейсбека в JSON allure-результатов
ДРУГИХ, не связанных падений (`RUN-20260804-1317`, `RUN-20260804-1624`,
`RUN-20260810-0145`, `RUN-20260811-0405`) — не реальные инстансы этой гонки.
Единственный подлинный инстанс сигнатуры за всю сессию — тот, что породил
этот баг (TC-112, AT-BUG-082 regression pass 2/2). Сиблингов не найдено,
дубль не заводился.

## Обсуждение

**[test-maintainer @ 2026-08-17T06:12:28Z]** Заведён ПОПУТНО при 2-прогонной
регресс-верификации `AT-BUG-082` (fix `assert_work_not_in_files_tab` уже
подтверждён на прогоне 1/2 — TC-112 там прошёл штатно; прогон 2/2 упал на
СОВЕРШЕННО ДРУГОМ, более раннем шаге того же теста, не расширяю scope
AT-BUG-082 починкой этого — другой класс дефекта, другой модуль
(`core/contexts.py`, не `steps/library_steps.py`)). Доклад + баг,
диспетчеризация/решение о переоткрытии `AT-BUG-047` — за Lead/очередь B4.

**[test-maintainer @ 2026-08-17T10:15:30Z]** Fixed. `_WEBVIEW_SWITCH_RACE_SIGNATURES`
расширен третьей сигнатурой `"No such context found."` — см. «Верификация»
за полным witness (эмпирически подтверждённая красная проба на pre-fix коде,
device-free unit-сьют 313 passed, TC-112 3/3 изолированных живых прогона
подряд, проверка сиблинг-инстансов в runs/ — не найдено, дубль не заводился).
`AT-BUG-047` (choke point 2) не переоткрывался — расширение того же
классового набора, тот же механизм, никакого нового поведения не введено.
Lock снят.

**[fix-verifier @ 2026-08-18T05:20:00Z]** Формальная D1-верификация
(`type: test_debt` — сборка приложения роли не играет, правило D1). Не
переоткрывал критик-приёмку — spot-check поверх уже состоявшегося объёма
(критик принял фикс: 0 блокеров, независимая красная проба + класс-полнота
прогоном соседей). Device-free `tests/test_in_webview_transient_race_unit.py`
изолированно: `8 passed in 0.42s`, `PYTEST_EXIT=0` — оба заявленных новых
parametrize-кейса (`no-such-context-found`) в файле подтверждены (строки
137-142, 166-168, 194-196). Живой TC-112 изолированно (emulator-5554, API 34):
`1 passed in 50.57s`, `PYTEST_EXIT=0` (свежий эмулятор потребовал
`Install-MitmCA` + повторный `Install-App` — package-service не сразу принял
`adb install` после CA-триггернутого framework-рестарта, чисто env-глитч
холодного старта, второй `Install-App` прошёл штатно). Противоречий не
найдено. `Fixed → Verified`, lock снят.
