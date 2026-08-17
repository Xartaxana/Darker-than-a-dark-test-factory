---
id: AT-BUG-081
title: "assert_no_ratings() читает Room СРАЗУ после confirm_clear_all() — Clear all ratings пишет через viewModelScope.launch(Dispatchers.IO) без await, одноразовый adb-read гонится с записью"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "test-maintainer, AT-BUG-080 verification pass (изолированный повтор TC-004, 2026-08-16)"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-004"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-16T22:21:53Z"
updated: "2026-08-16T22:21:53Z"
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

- [ ] `assert_no_ratings()` (и симметрично `assert_rating_rows_empty`,
      `assert_ratings_present` — тот же слой) переведены на `poll_for`/
      `wait_for`-подобный опрос БД вместо одноразового чтения — ждать
      `count == "0"` в течение разумного бюджета (например 2-3с), а не
      падать по первому снимку.
- [ ] Красная проба/регресс-проверка: 3 зелёных ИЗОЛИРОВАННЫХ повтора
      `tests/test_smoke.py::test_clear_all_ratings` подряд (тот же протокол,
      которым долг обнаружен).
- [ ] Проверить остальные callers `read_rating_rows`/`assert_ratings_present`
      на тот же класс гонки (запись после UI-действия, читаемая одним
      снимком adb) — класс, не экземпляр.

## Обсуждение

**[test-maintainer @ 2026-08-16T22:21:53Z]** Заведён ПОПУТНО при верификации
`AT-BUG-080` (пункт 5 критерия готовности того бага — «3 зелёных изолированных
прогона TC-004»). Не расширяю scope AT-BUG-080 починкой этого — другой класс
дефекта (async DB race в Then-хелпере, не swipe/bounds-геометрия). Доклад +
баг, диспетчеризация фикса — за Lead/очередь B4.
