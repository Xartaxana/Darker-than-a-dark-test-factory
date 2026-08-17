---
key: "AT-BUG-081"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "assert_no_ratings() читает Room СРАЗУ после confirm_clear_all() — Clear all ratings пишет через viewModelScope.launch(Dispatchers.IO) без await, одноразовый adb-read гонится с записью"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-004", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-17T04:59:00Z"
updated: "2026-08-17T04:59:00Z"
archived: false
resolution: "done"
---

# assert_no_ratings() читает Room СРАЗУ после confirm_clear_all() — Clear all ratings пишет через viewModelScope.launch(Dispatchers.IO) без await, одноразовый adb-read гонится с записью

_Спроецировано из `bugs/AT-BUG-081.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-081 — `assert_no_ratings()` гонится с асинхронной записью `confirmClearAll()`

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/settings_steps.py::assert_no_ratings` (одноразовый adb-read БД
СРАЗУ после `SettingsScreen.confirm_clear_all()`, без поллинга/retry) против
`SettingsViewModel.confirmClearAll()` (`SettingsScreen.kt:545-548`):

```kotlin
fun confirmClearAll() {
    _uiState.update { it.copy(showClearDialog = false) }
    viewModelScope.launch(Dispatchers.IO) { repo.clearAllRatings() }
}
```

Запись в Room запущена в `viewModelScope.launch(Dispatchers.IO)` — не await'ится
диалогом и ничем не сигнализируется UI-слою (нет индикатора/флага «удаление
завершено»). `settings_steps.assert_no_ratings()` делает ОДИН adb-read
(`sqlite3 ... SELECT COUNT(*) FROM work_ratings`) сразу после того, как UI-тап
на «Clear all» вернул управление — без поллинга.

## Обнаружено

Найдено ПОПУТНО при верификации фикса `AT-BUG-080` (не относится к самому
фиксу — см. «Анализ»): 3 изолированных перезапуска `tests/test_smoke.py::
test_clear_all_ratings` (TC-004) подряд дали PASS / **FAIL** / PASS. Второй
прогон упал на `settings_steps.assert_no_ratings()`:

```
AssertionError: ожидали 0 рейтингов, в БД: '5'
```

при том что ШАГ «открыт диалог «Clear all ratings» и подтверждён» (включает
`open_clear_all_dialog`+`clear_dialog_visible`+`confirm_clear_all`) прошёл
БЕЗ ошибки — то есть тап по «Clear all» состоялся штатно, но чтение БД
опередило завершение асинхронной записи.

## Анализ (изолирующее наблюдение — не в AT-BUG-080)

Логкат упавшего прогона (`method: '-android uiautomator', selector:
'new UiSelector().text("Clear all ratings")'` в 22:15:21) показывает: якорь
«Clear all ratings» был найден СРАЗУ с bounds `[42,1937][293,1980]` —
НЕ обрезан кромкой вьюпорта (запас от нижней границы вьюпорта далеко
больше `SWIPE_ANCHOR_MARGIN_PX=24`), поэтому механизм `AT-BUG-080`
(`BaseScreen._settle_clipped_anchor`, доп. свайп при обрезанном якоре) в
этом прогоне НЕ СРАБОТАЛ ВООБЩЕ — ни одного доп. `driver.swipe` между
нахождением анкора и тапом «Clear…»/«Clear all» в логе нет. Код,
изменённый `AT-BUG-080`, в этом конкретном инстансе исполнился идентично
докоммитной версии (ветка "не обрезан" — no-op и там, и там). Это
ИЗОЛИРУЮЩЕЕ наблюдение (не совместный зелёный прогон): вклад `AT-BUG-080`
в ЭТОТ конкретный красный прогон исключён по факту неисполнения
изменённой ветки, а не предположением.

Причина в другом слое: `assert_no_ratings()` не ждёт завершения
`Dispatchers.IO`-корутины `repo.clearAllRatings()` — это гонка между UI-таче
(быстрый Appium round-trip) и Room-записью, читаемой напрямую через
`adb shell run-as ... sqlite3` (собственный процесс, спавнится не мгновенно,
но порядок гонки может уложиться в единицы-десятки ms при холодном IO
диспетчере/загруженной системе).

## Критерий готовности (Fixed)

- [x] `assert_no_ratings()` (и симметрично `assert_rating_rows_empty`,
      `assert_ratings_present` — тот же слой) переведены на `poll_for`/
      `wait_for`-подобный опрос БД вместо одноразового чтения — ждать
      `count == "0"` в течение разумного бюджета (например 2-3с), а не
      падать по первому снимку.
- [x] Красная проба/регресс-проверка: 3 зелёных ИЗОЛИРОВАННЫХ повтора
      `tests/test_smoke.py::test_clear_all_ratings` подряд (тот же протокол,
      которым долг обнаружен).
- [x] Проверить остальные callers `read_rating_rows`/`assert_ratings_present`
      на тот же класс гонки (запись после UI-действия, читаемая одним
      снимком adb) — класс, не экземпляр.

## Верификация

Fix: `_poll_ratings_marker(read_fn, settled, timeout=None)`
(`framework/steps/settings_steps.py`) — опрашивает `read_fn()` до
`settings.RATINGS_DB_POLL_TIMEOUT` (3.0s, шаг `RATINGS_DB_POLL_INTERVAL`
0.3s), пока `settled(out)` не станет `True`; `settled` возвращает `True`
НЕМЕДЛЕННО на `NOSQLITE`/отсутствии `OK`-маркера (детерминированные исходы,
не гонка — ждать их «устаканивания» нечего) и только количественная ветка
(count == "0" / rows == "" / count not in ("0","")) реально ждёт. Три
хелпера (`assert_no_ratings`, `assert_ratings_present`,
`assert_rating_rows_empty`) переведены на эту функцию; `_read_ratings_count()`
вынесена как общий read для первых двух (не разъезжающиеся копии SQL-команды).

**Различающий сигнал (критик-урок этой сессии — не полагаться на "тест
прошёл" как на доказательство фикса):** добавлен
`test_assert_no_ratings_polls_until_settled`
(`framework/tests/test_settings_ratings_fail_closed_unit.py`) — мок
`adb.run_as` отдаёт `"5\nOK\n"`, `"5\nOK\n"`, `"0\nOK\n"` НА
ПОСЛЕДОВАТЕЛЬНЫЕ вызовы (симуляция реальной гонки: 2 снимка «запись ещё в
процессе», 3-й — «завершилась»). Различающая сила ПРОВЕРЕНА эмпирически, НЕ
предположена: отдельный standalone-скрипт-проба
(`scratchpad/prefix_race_probe.py`, реальный файл РЕПОЗИТОРИЙ НЕ трогает —
verbatim-копия ДОКОММИТНОГО (pre-fix) тела `assert_no_ratings` в изолированном
модуле) прогнан на ТОЙ ЖЕ последовательности моков `"5\nOK\n"/"5\nOK\n"/
"0\nOK\n"` — дословный вывод:
```
CONFIRMED pre-fix fails on the race sequence: AssertionError: ожидали 0 рейтингов, в БД: '5'
calls made: 1
```
т.е. pre-fix (одноразовое чтение) падает НА ПЕРВОМ вызове (1 call), забирая
только "5\nOK\n" и никогда не видя "0\nOK\n" — тот же ассерт-текст, что и
реальный красный прогон TC-004 (bugs/AT-BUG-081.md «Обнаружено»:
`ожидали 0 рейтингов, в БД: '5'`). ТЕКУЩИЙ (пост-фикс) код на ТОЙ ЖЕ
последовательности проходит за 3 вызова (см. `test_assert_no_ratings_
polls_until_settled` выше, живой прогон в device-free unit-сьюте ниже) —
разница в поведении между pre-fix и post-fix на идентичном входе
подтверждена, не предположена. Симметричный
`test_assert_no_ratings_raises_after_budget_exhausted` доказывает, что опрос
не превращается в бесконечное молчание — персистентный дефект (count всегда
`"7"`) всё ещё даёт честный `AssertionError` по истечении бюджета.

**Device-free unit-сьют (после рефакторинга, включая 2 новых теста):**
```
25 passed in 0.75s (tests/test_settings_ratings_fail_closed_unit.py)
305 passed, 191 deselected in 23.04s (tests -k _unit, полный device-free срез)
PYTEST_EXIT=0
```

**Красная проба B4 (протокол обнаружения — 3 ИЗОЛИРОВАННЫХ повтора
`tests/test_smoke.py::test_clear_all_ratings`, каждый отдельным вызовом
`Invoke-Pytest`, emulator-5554):**
```
run 1: 1 passed in 102.08s (0:01:42), PYTEST_EXIT=0
run 2: 1 passed in 105.88s (0:01:45), PYTEST_EXIT=0
run 3: 1 passed in 99.19s  (0:01:39), PYTEST_EXIT=0
```
Три подряд PASSED — тот же протокол, которым долг обнаружен (PASS/FAIL/PASS
до фикса).

**Критерий готовности пункт 3 (остальные callers того же класса гонки) —
проверено, не просто продекларировано:**
- `tests/test_settings.py::test_clear_all_ratings_shows_confirmation_dialog`
  (TC-018) — `assert_ratings_present()`: **правка критик-входа (Н2)** — прогнан
  вместе с `test_cancel_clear_all_dialog_keeps_data` (TC-019, `2 passed in
  197.63s`, `PYTEST_EXIT=0`), но реально вызывает `assert_ratings_present()`
  только TC-018; TC-019 проверяет вкладки Library, этого хелпера не касается
  (регрессии не найдено ни в одном, атрибуция уточнена).
- `tests/test_settings.py::test_clear_all_ratings_badge_resets_after_reload[works_multi.mitm]`
  (TC-020, ветка (б)) — `assert_rating_rows_empty()` сразу после
  `clear_all_ratings()`: `1 passed in 106.56s`, `PYTEST_EXIT=0`.
- `tests/test_backup_restore.py::test_backup_clear_restore_returns_original_data`
  (TC-021) — `assert_no_ratings()` сразу после `clear_all_ratings()`:
  `1 passed in 200.16s`, `PYTEST_EXIT=0`.
- Проверен СИБЛИНГ-класс (не caller `settings_steps`, но та же природа гонки
  — async Room-запись без await): `rating_steps.wait_for_rating`
  (AT-BUG-074) уже опрашивает `seed_db.read_work_ratings_full()` через
  `wait_for` — не затронут долгом, уже поллит.
**Формальная D1-верификация (fix-verifier, 2026-08-17T04:59:00Z) — test_debt-класс,
сборка приложения роли не играет (правило D1); фикс уже прошёл полный критик-вход
приёмки в этой же сессии (см. `[critic @ 2026-08-17T04:38:00Z]` ниже — независимый
красный/зелёный на реальном git-откате `settings_steps.py`, класс-полнота grep'ом +
чтением app-source, живой TC-004 изолированно). Ниже — SPOT-CHECK поверх этого объёма,
не повтор с нуля:**
- `framework/tests/test_settings_ratings_fail_closed_unit.py` (device-free): `25 passed
  in 0.62s`, `PYTEST_EXIT=0`.
- `tests/test_smoke.py::test_clear_all_ratings` (TC-004, изолированный вызов
  `Invoke-Pytest`, emulator-5554): `1 passed in 110.23s (0:01:50)`, `PYTEST_EXIT=0`.
- `python scripts/validate_frontmatter.py`: `ошибок 0, предупреждений 0`.
- Оба прогона зелёные → `Fixed` → `Verified`, lock снят.
- Проверен `SettingsScreen.importFromUri` (Restore, читается
  `backup_steps.assert_restored_fields_match`/`assert_filter_profiles_match`)
  — живым чтением `app-under-test` (`SettingsScreen.kt:401-454`):
  `repo.upsertWorkRating`/`upsertFilterProfile` вызываются `suspend`-функциями
  ВНУТРИ ТОГО ЖЕ `viewModelScope.launch(Dispatchers.IO)` блока, который
  синхронно (await) исполняется ДО `_importState.value = ImportState.Done(...)`
  — к моменту, когда UI показывает диалог результата (наблюдаемый Then-сигнал
  `assert_restore_result_dialog`), запись УЖЕ завершена. НЕ тот же класс гонки,
  что `confirmClearAll()` (который вообще не обновляет никакое UI-состояние
  по завершении) — не тронут, полей опроса не требует.

## Обсуждение

**[test-maintainer @ 2026-08-16T22:21:53Z]** Заведён ПОПУТНО при верификации
`AT-BUG-080` (пункт 5 критерия готовности того бага — «3 зелёных изолированных
прогона TC-004»). Не расширяю scope AT-BUG-080 починкой этого — другой класс
дефекта (async DB race в Then-хелпере, не swipe/bounds-геометрия). Доклад +
баг, диспетчеризация фикса — за Lead/очередь B4.

**[test-maintainer @ 2026-08-17T04:20:00Z]** Fixed. `assert_no_ratings`/
`assert_ratings_present`/`assert_rating_rows_empty` переведены на
`_poll_ratings_marker` (опрос до 3.0s/0.3s, settled немедленно на
NOSQLITE/ERROR-ветках) — см. «Верификация» за полным witness (device-free
unit-сьют + 3 изолированных TC-004 подряд + все остальные caller'ы того же
класса перепрогнаны зелёными). Класс закрыт полностью (пункт 3 критерия —
проверены ВСЕ caller'ы `read_rating_rows`/`assert_ratings_present`/
`assert_no_ratings`/`assert_rating_rows_empty`, ни одного queued follow-up не
осталось; сиблинг-класс `wait_for_rating`/`importFromUri` проверены и
подтверждены НЕ подверженными этой гонке). Lock снят.

**[critic @ 2026-08-17T04:38:00Z]** Критик-вход приёмки: ПРИНЯТЬ, 0
блокеров. Красная проба перепрогнана СИЛЬНЕЕ заявленного — реальный откат
`settings_steps.py` на pre-fix коммит байтовой копией (не только copy-скрипт
в scratchpad), красный на подлинном докоммитном коде, восстановлен md5-сверкой.
Живой TC-004 изолированно PASSED. Класс-полнота пройдена собственным grep'ом
(ровно 4 боевых call site) и чтением app-source (3 экземпляра
`viewModelScope.launch` в SettingsScreen.kt, 2 непочиненных гейтятся UI-опросом
ДО чтения БД — не того же класса). Н2 (TC-019 не вызывает `assert_ratings_present`)
устранена координатором выше. **Очередь (Н1, не блокер):** регресс-замок
покрывает только 1 из 3 переведённых хелперов (`assert_no_ratings`) —
`assert_rating_rows_empty` и `assert_ratings_present` не имеют своего
последовательного мок-теста; точечный откат ИМЕННО этих двух хелперов красной
пробой не поймается. Кандидат для будущего B4-прохода: 2 параметризованных
кейса по образцу существующего.

**[fix-verifier @ 2026-08-17T04:59:00Z]** Формальная D1-верификация (test_debt —
сборка приложения роли не играет). Не переоткрывал критик-приёмку — только
spot-check поверх уже состоявшегося объёма (см. «Верификация» выше):
device-free `test_settings_ratings_fail_closed_unit.py` 25/25 PASSED +
изолированный `tests/test_smoke.py::test_clear_all_ratings` (TC-004) PASSED +
`validate_frontmatter.py` 0/0. `Fixed → Verified`, lock снят. Открытая заметка
критика (Н1, не блокер) — регресс-замок пока покрывает только
`assert_no_ratings` из трёх переведённых хелперов — остаётся в очереди
B4-follow-up, закрытию не мешает.
