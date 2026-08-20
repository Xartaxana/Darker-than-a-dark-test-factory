---
key: "AT-BUG-086"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "assert_theme_mode_pref читает SharedPreferences сразу после серии select_theme без settle — TC-005 (test_theme_toggle_stable) красный в test_smoke.py (структурно не связан с AT-BUG-083 fix)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-005", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-20T00:51:21Z"
updated: "2026-08-20T00:51:21Z"
archived: false
resolution: null
---

# assert_theme_mode_pref читает SharedPreferences сразу после серии select_theme без settle — TC-005 (test_theme_toggle_stable) красный в test_smoke.py (структурно не связан с AT-BUG-083 fix)

_Спроецировано из `bugs/AT-BUG-086.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-086 — `assert_theme_mode_pref` гонится с асинхронной записью SharedPreferences после серии `select_theme`, TC-005 красный в `test_smoke.py`

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/settings_steps.py::assert_theme_mode_pref` (строка 609-611)/
`select_theme`. Эмулятор `emulator-5554`, API 34.

## Обнаружено

ПОПУТНО при живом регрессе `AT-BUG-083` (settle+hold опрос для
`assert_work_not_in_tab`, `framework/steps/library_steps.py`) — НЕ относится к
самому фиксу AT-BUG-083, см. «Анализ». `Invoke-Pytest tests/test_smoke.py -q`
(после фикса AT-BUG-083): `1 failed, 8 passed in 340.16s`, единственное
падение — `test_theme_toggle_stable` (TC-005):

```python
for mode in ("DARK", "LIGHT", "SYSTEM"):
    settings_steps.select_theme(driver, mode)
settings_steps.assert_settings_loaded(driver)
settings_steps.assert_theme_mode_pref("SYSTEM")
```

```
AssertionError: theme_mode != SYSTEM в SharedPreferences: <?xml version='1.0' ...?>
<map>
    <string name="theme_mode">LIGHT</string>
    ...
</map>
```

`assert_theme_mode_pref` (`settings_steps.py:609-611`) — прямой
`adb.run_as("cat shared_prefs/ao3_settings.xml")` + подстрочная сверка,
БЕЗ единого settle-опроса, вызванный сразу после ТРЁХ последовательных
`select_theme` тапов (DARK→LIGHT→SYSTEM). `SharedPreferences.apply()`
асинхронна (тот же механизм, что задокументирован в `BUG-013` —
`theme_mode` пишется без дебаунса/синхронизации) — при быстрой серии
тапов запись ПОСЛЕДНЕГО (SYSTEM) тапа может ещё не долететь до диска в
момент чтения, либо более ранняя (LIGHT) запись физически завершается
ПОСЛЕ более поздней (SYSTEM) из-за неупорядоченного планирования диспетчера
`apply()` — файл ни на момент чтения не отражает финальный UI-выбор.
`assert_work_not_in_tab`/`library_steps.py` в цепочке вызовов ЭТОГО теста
НЕ участвуют вовсе (traceback падения целиком в `settings_steps.py`/`adb.py`) —
не тот же класс гонки, что AT-BUG-082/083 (Compose `HorizontalPager`), и не
тот же СЦЕНАРИЙ, что `BUG-013` (там триггер — `force-stop` в окне <100мс
СРАЗУ после ЕДИНСТВЕННОГО тапа; здесь триггер — БЫСТРАЯ СЕРИЯ из трёх тапов
без kill вообще, чтение просто не ждёт финального `apply()`-флаша).

## Почему НЕ почин здесь (D-0043 «класс, не экземпляр» — явный queued follow-up)

Мандат этой сессии — `AT-BUG-083` (`library_steps.py::assert_work_not_in_tab`,
гонка с анимацией `HorizontalPager`). Это падение — СОВЕРШЕННО ДРУГОЙ модуль
(`settings_steps.py`/`adb.py`, не `library_steps.py`/`LibraryScreen`) и ДРУГОЙ
UI/системный механизм (асинхронная запись `SharedPreferences`, не Compose-
анимация вкладок). Расширение scope AT-BUG-083 починкой этого не производится
(правило «новый блокер = test_debt-баг, не заметка»).

**АНАЛОГ УЖЕ БЫЛ НАЗВАН, НО НЕ ЗАВЕДЁН БАГОМ:** `AT-BUG-055`
(Verified, `assert_theme_mode_pref`/`assert_font_size_step_pref` названы как
«тот же класс дыры (нет rc-проверки), но НЕ дефект корректности (не даёт
ложный PASS) — кандидат для отдельного B4-прохода, не блокер») говорила про
слепоту ЧТЕНИЯ (adb rc не проверяется) — ЭТО падение другое: чтение честно
происходит (rc=0, файл реально прочитан), но СЛИШКОМ РАНО относительно
асинхронной записи, тот же класс гонки, что `AT-BUG-081`
(`_poll_ratings_marker`)/`AT-BUG-082`/`AT-BUG-083` («Then читает раньше, чем
состояние устаканилось»), в ЧЕТВЁРТОМ слое (SharedPreferences.apply(), не
Room, не Pager-анимация, не comment-collapse превью — см. `AT-BUG-085` за
третьим слоем).

## Критерий готовности (Fixed)

- [ ] Локализовать причину точнее (реальная неупорядоченность
      `apply()`-флашей ИЛИ просто отсутствие ожидания финального флаша перед
      чтением) — например, изолированный трайл: один `select_theme("SYSTEM")`
      без предшествующих DARK/LIGHT, сразу `assert_theme_mode_pref`; если
      воспроизводится и на одиночном тапе — окно гонки шире, чем казалось.
- [ ] Применить settle/poll-опрос по образцу `AT-BUG-081`
      (`_poll_ratings_marker`)/`AT-BUG-082` (`_poll_files_tab_absent`) к
      `assert_theme_mode_pref` — опрашивать `cat shared_prefs/ao3_settings.xml`
      до совпадения `theme_mode` с ожидаемым или таймаута, вместо ОДНОГО
      немедленного чтения. Проверить сиблингов того же файла-оракула
      (`assert_auto_apply_filter_pref`, `assert_font_size_step_pref`,
      `settings_steps.py:614-631`) на тот же класс (D-0043).
- [ ] Красная проба на РЕАЛЬНОМ pre-fix коде (git байтовая копия) +
      device-free различающий unit-тест (по образцу
      `test_library_files_tab_settle_unit.py`/`test_settings_ratings_fail_
      closed_unit.py`).
- [ ] Живой регресс: TC-005 (и в идеале весь `test_smoke.py`) зелёный минимум
      2 раза подряд.

## Обсуждение

**[test-maintainer @ 2026-08-20T00:51:21Z]** Заведён ПОПУТНО при живом
регрессе `AT-BUG-083` (`tests/test_smoke.py`, 1 из 6 файлов-потребителей
`assert_work_not_in_tab` по её мандату). Traceback падения TC-005 целиком в
`settings_steps.py`/`adb.py` — `library_steps.py`/`LibraryScreen` (предмет
AT-BUG-083) в цепочке вызовов не участвуют. Не расширяю scope AT-BUG-083
починкой этого — доклад + баг, диспетчеризация фикса за Lead/очередь B4.
