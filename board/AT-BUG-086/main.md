---
key: "AT-BUG-086"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p2"
summary: "assert_theme_mode_pref читает SharedPreferences без settle сразу после select_theme (гонка воспроизводится уже на ОДНОМ тапе) — TC-005 (test_theme_toggle_stable) красный в test_smoke.py (структурно не связан с AT-BUG-083 fix); пофикшено settle-poll'ом"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-005", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-20T05:36:44Z"
updated: "2026-08-20T05:36:44Z"
archived: false
resolution: null
---

# assert_theme_mode_pref читает SharedPreferences без settle сразу после select_theme (гонка воспроизводится уже на ОДНОМ тапе) — TC-005 (test_theme_toggle_stable) красный в test_smoke.py (структурно не связан с AT-BUG-083 fix); пофикшено settle-poll'ом

_Спроецировано из `bugs/AT-BUG-086.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-086 — `assert_theme_mode_pref` гонится с асинхронной записью SharedPreferences уже на одном `select_theme`, TC-005 красный в `test_smoke.py`

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

`assert_theme_mode_pref` (`settings_steps.py:609-611`, pre-fix) — прямой
`adb.run_as("cat shared_prefs/ao3_settings.xml")` + подстрочная сверка,
БЕЗ единого settle-опроса, вызванный сразу после ТРЁХ последовательных
`select_theme` тапов (DARK→LIGHT→SYSTEM). `SharedPreferences.apply()`
асинхронна (тот же механизм, что задокументирован в `BUG-013` —
`theme_mode` пишется без дебаунса/синхронизации). **На момент заведения**
рассматривались две гипотезы: (1) запись ПОСЛЕДНЕГО (SYSTEM) тапа не
долетела до диска к моменту чтения, ИЛИ (2) более ранняя (LIGHT) запись
физически завершается ПОСЛЕ более поздней (SYSTEM) из-за неупорядоченного
планирования диспетчера `apply()`. **СНЯТО фиксом (см. «Обсуждение»,
2026-08-20T05:36:44Z):** локализация показала гонку уже на ОДНОМ тапе —
верна гипотеза (1) в чистом виде (простое отсутствие ожидания флаша),
гипотеза (2) переупорядочения не измерялась напрямую и исключена по
устройству `SharedPreferences`/`QueuedWork` (generation-guard не даёт
более раннему `apply()` перезаписать более поздний коммит), не
экспериментом — остаточный риск см. в докстринге `_poll_settings_prefs`.
`assert_work_not_in_tab`/`library_steps.py` в цепочке вызовов ЭТОГО теста
НЕ участвуют вовсе (traceback падения целиком в `settings_steps.py`/`adb.py`) —
не тот же класс гонки, что AT-BUG-082/083 (Compose `HorizontalPager`), и не
тот же СЦЕНАРИЙ, что `BUG-013` (там триггер — `force-stop` СРАЗУ после
тапа; здесь — чтение без ожидания финального `apply()`-флаша, kill вообще
не участвует; различитель «один тап vs серия» снят локализацией — гонка
воспроизводится уже на одиночном тапе).

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

- [x] Локализовать причину точнее (реальная неупорядоченность
      `apply()`-флашей ИЛИ просто отсутствие ожидания финального флаша перед
      чтением) — например, изолированный трайл: один `select_theme("SYSTEM")`
      без предшествующих DARK/LIGHT, сразу `assert_theme_mode_pref`; если
      воспроизводится и на одиночном тапе — окно гонки шире, чем казалось.
      **Выполнено** — см. «Обсуждение» ниже: race воспроизводится уже на
      ОДНОМ тапе (6/8 немедленных чтений не увидели финальное значение),
      причина — простое отсутствие ожидания флаша, не переупорядочение.
- [x] Применить settle/poll-опрос по образцу `AT-BUG-081`
      (`_poll_ratings_marker`)/`AT-BUG-082` (`_poll_files_tab_absent`) к
      `assert_theme_mode_pref` — опрашивать `cat shared_prefs/ao3_settings.xml`
      до совпадения `theme_mode` с ожидаемым или таймаута, вместо ОДНОГО
      немедленного чтения. Проверить сиблингов того же файла-оракула
      (`assert_auto_apply_filter_pref`, `assert_font_size_step_pref`,
      `settings_steps.py:614-631`) на тот же класс (D-0043).
      **Выполнено** — новый общий `settings_steps._poll_settings_prefs`,
      применён ко всем трём хелперам (оба сиблинга структурно того же
      класса: тот же файл-оракул, тот же `apply()`-механизм записи,
      вызываются сразу после UI-действия в живых тестах TC-181/TC-050/051).
- [x] Красная проба на РЕАЛЬНОМ pre-fix коде (git байтовая копия) +
      device-free различающий unit-тест (по образцу
      `test_library_files_tab_settle_unit.py`/`test_settings_ratings_fail_
      closed_unit.py`). **Выполнено** —
      `framework/tests/test_theme_mode_pref_settle_unit.py` (5 тестов, все
      зелёные): различающие пробы на все три хелпера + красная проба
      pre-fix кода на записанной гонке.
- [x] Живой регресс: TC-005 (и в идеале весь `test_smoke.py`) зелёный минимум
      2 раза подряд. **Выполнено** — TC-005 изолированно 2/2 (`1 passed in
      44.24s` / `1 passed in 44.40s`), полный `test_smoke.py` 2/2 (`9 passed
      in 651.61s` / `9 passed in 589.69s`).

## Обсуждение

**[test-maintainer @ 2026-08-20T00:51:21Z]** Заведён ПОПУТНО при живом
регрессе `AT-BUG-083` (`tests/test_smoke.py`, 1 из 6 файлов-потребителей
`assert_work_not_in_tab` по её мандату). Traceback падения TC-005 целиком в
`settings_steps.py`/`adb.py` — `library_steps.py`/`LibraryScreen` (предмет
AT-BUG-083) в цепочке вызовов не участвуют. Не расширяю scope AT-BUG-083
починкой этого — доклад + баг, диспетчеризация фикса за Lead/очередь B4.

**[test-maintainer @ 2026-08-20T05:36:44Z] Фикс (B4).**

**Локализация (пункт 1).** Изолированный живой трайл на `emulator-5554`:
`select_theme("DARK")` + settle(1с) → 8 раз подряд `select_theme("SYSTEM")`
+ НЕМЕДЛЕННОЕ raw-чтение `cat shared_prefs/ao3_settings.xml` → обратно
`select_theme("DARK")` + settle(1с). Результат: `[False, False, False, True,
True, False, False, False]` — **6 из 8** немедленных чтений сразу после
ОДНОГО тапа НЕ увидели финальное значение SYSTEM. Вывод: гонка
воспроизводится уже на единичной записи, окно гонки ШИРЕ, чем предполагала
исходная формулировка бага (серия из трёх тапов) — **этого пробника
достаточно**, чтобы объяснить наблюдаемый отказ простым отсутствием
ожидания финального флаша. **Гипотеза «переупорядочение `apply()`-флашей
между несколькими тапами» НЕ измерялась** (пробник одного тапа по
построению не может её наблюдать) — исключается не экспериментом, а по
устройству `SharedPreferences`/`QueuedWork` (Android сериализует
`apply()`-записи одного файла на одном фоновом потоке в порядке вызова,
поздний коммит не может откатить более ранний — generation-guard). Если
бы это устройство подвело, `_poll_settings_prefs` без hold-фазы (пункт
«Фикс» ниже) остановился бы на транзиентном совпадении и TC-005 снова
зафлейкал бы — это остаточный риск, не доказанный ноль.

**Фикс (пункт 2).** Новый общий `settings_steps._poll_settings_prefs`
(settle-опрос, без hold-фазы — см. её докстринг за обоснованием, почему
hold здесь не нужен в отличие от `_poll_tab_absent`: файл перезаписывается
атомарно, откат без новой явной записи не бывает, в отличие от
колеблющейся Pager-анимации). Применён к `assert_theme_mode_pref` и к обоим
сиблингам того же файла-оракула — `assert_auto_apply_filter_pref`,
`assert_font_size_step_pref` (D-0043 сиблинг-аудит: оба структурно того же
класса — тот же файл, тот же `apply()`-механизм, оба живых вызывающих теста
(TC-181 `test_filter_profiles.py:316`, TC-050/051 `test_side_panel.py:74,99`)
читают СРАЗУ после UI-действия). Новые константы
`settings.SETTINGS_PREFS_POLL_TIMEOUT`/`SETTINGS_PREFS_POLL_INTERVAL`
(`framework/config/settings.py`, дефолты 3.0s/0.3s — те же значения, что
`RATINGS_DB_POLL_*`, той же оценкой по порядку, не профилированием этого
конкретного флаша).

**Красная проба + device-free unit (пункт 3).**
`framework/tests/test_theme_mode_pref_settle_unit.py` (5 тестов):
- 3 различающих теста (по одному на каждый из трёх хелперов) — мок
  `adb.run_as` записанной последовательностью «2 стухших снимка + 1
  settled», доказывают, что поллинг реально повторяет чтение (ровно 3
  вызова, не падает на первом снимке).
- 1 таймаут-тест — доказывает, что при ПЕРСИСТЕНТНОМ несовпадении опрос
  всё равно честно падает `AssertionError` (не бесконечный retry, не тихий
  pass).
- 1 красная проба (`test_pre_fix_single_read_would_have_failed_on_recorded_race`)
  — байтовая копия РЕАЛЬНОГО pre-fix кода (`git show
  HEAD:framework/steps/settings_steps.py`, строки 609-611 ДО этого коммита,
  сверено дословно) на ТОЙ ЖЕ записанной гонке падает
  `AssertionError` — доказывает, что мок-сценарий реально различает
  старый/новый код, не тривиален.
Все 5 зелёные: `5 passed in 0.21s`. `arch_check.py`: 0 ошибок — новый файл
мокает только `adb.run_as`/`settings_steps`, не импортирует
screens/driver-классы, ALLOWLIST не требует новой записи.

**Живой регресс (пункт 4).** TC-005 изолированно 2/2 подряд: `1 passed in
44.24s`, `1 passed in 44.40s`. Полный `tests/test_smoke.py` 2/2 подряд:
`9 passed in 651.61s (0:10:51)`, `9 passed in 589.69s (0:09:49)`, оба
`PYTEST_EXIT=0`, device-liveness guard recoveries 0/2 в обоих прогонах.

**`python -m pytest scripts/tests -q`** (полный suite, не только
`framework/tests`): `1704 passed, 1 skipped in 51.59s`.

`fixed_in` заполнен из `state/app-under-test.yaml` (сборка приложения не
менялась — фикс целиком в `framework/`). `app-under-test/` не трогал.
`lock` снят, `status: Open -> Fixed` (легальный актор test-maintainer,
guard `type: test_debt`, `schemas/transitions.yaml`).

Новых блокеров класса «недостающая фикстура/неавтоматизируемый UI/сломанный
тул» не найдено — сиблинг-аудит (D-0043) полностью закрыт в рамках этого же
хода (оба сиблинга починены здесь же, не отдельным test_debt-багом).
