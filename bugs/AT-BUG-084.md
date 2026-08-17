---
id: AT-BUG-084
title: "in_webview choke point 2 (AT-BUG-047, Verified) рвётся НОВОЙ сигнатурой 'No such context found.' — не входит в _WEBVIEW_SWITCH_RACE_SIGNATURES, ретрай обрывается на 2-й попытке"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "test-maintainer, AT-BUG-082 regression pass (2 подряд test_downloads.py после fix, run 2/2, 2026-08-17)"
fixed_in: ""
last_seen_in: "run 2/2, tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off (TC-112), 2026-08-17T06:00Z (примерно, см. вывод прогона)"
test_cases: ["TC-112"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-17T06:12:28Z"
updated: "2026-08-17T06:12:28Z"
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

- [ ] Добавить `"No such context found."` (или более узкий фрагмент, если
      полная строка избыточно широка) в `_WEBVIEW_SWITCH_RACE_SIGNATURES`
      (`framework/core/contexts.py`) — классовое расширение уже существующего
      набора, не новый механизм.
- [ ] Device-free unit-регресс (по образцу существующих проб choke point 2,
      если такие есть в `framework/tests/test_*_unit.py`) — мок
      `driver.switch_to.context`, поднимающий `NoSuchContextException` с этим
      текстом на первой попытке, должен ретраиться и в итоге пройти.
- [ ] Живой регресс — TC-112 (и в идеале весь `test_downloads.py`) зелёный.
- [ ] Проверить, не появлялась ли эта сигнатура и в других логах/прогонах
      сессии (сиблинг-инстансы того же класса) — если да, дописать сюда как
      факт, не заводить дубль.

## Обсуждение

**[test-maintainer @ 2026-08-17T06:12:28Z]** Заведён ПОПУТНО при 2-прогонной
регресс-верификации `AT-BUG-082` (fix `assert_work_not_in_files_tab` уже
подтверждён на прогоне 1/2 — TC-112 там прошёл штатно; прогон 2/2 упал на
СОВЕРШЕННО ДРУГОМ, более раннем шаге того же теста, не расширяю scope
AT-BUG-082 починкой этого — другой класс дефекта, другой модуль
(`core/contexts.py`, не `steps/library_steps.py`)). Доклад + баг,
диспетчеризация/решение о переоткрытии `AT-BUG-047` — за Lead/очередь B4.
