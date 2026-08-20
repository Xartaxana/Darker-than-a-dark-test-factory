---
key: "AT-BUG-090"
project: "AO3"
issueType: "bug"
status: "bug-blocked"
priority: "p2"
summary: "assert_chip_absent — негативный Then сразу после tap_selected_chip/reopen_listing_overlay без settle/hold (4-й член класса AT-BUG-081/082/083/085), TC-091; код-фикс написан 2026-08-20, live-верификация BLOCKED (environment)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-091", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-20T21:15:00Z"
updated: "2026-08-20T21:15:00Z"
archived: false
resolution: null
---

# assert_chip_absent — негативный Then сразу после tap_selected_chip/reopen_listing_overlay без settle/hold (4-й член класса AT-BUG-081/082/083/085), TC-091; код-фикс написан 2026-08-20, live-верификация BLOCKED (environment)

_Спроецировано из `bugs/AT-BUG-090.md` (источник правды).
Статус в нашей машине: **Blocked**._

# AT-BUG-090 — `assert_chip_absent` читал `chip_visible` сразу после стейт-меняющего действия без settle/hold (TC-091; фикс написан 2026-08-20, live-верификация BLOCKED — environment)

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/steps/rating_steps.py::assert_chip_absent`, вызывается из
`framework/tests/test_rating_listing.py` (TC-091,
`test_tap_selected_chip_removes_tag`).

## Статус: код-фикс готов, live-верификация BLOCKED (env)

**Обновление 2026-08-20T21:15:00Z:** код-фикс написан и device-free проверен
(settle+hold, зеркало AT-BUG-085 — см. «Обсуждение» ниже); живая
верификация TC-091 (DoD-пункт «зелёный живой прогон») уперлась в
деградацию среды (adb/Appium instrumentation timeouts) ДО того, как
дошла до изменённого кода — `status: Blocked`, `blocked_reason:
environment`, ждёт восстановления среды и повторной верификации.
Красных прогонов TC-091 на исходном коде по-прежнему НЕТ (изначальный
превентивный характер тикета не изменился — см. историю ниже) —
следующий абзац описывает КАК тикет был заведён, не текущее состояние.

**Красных прогонов ПОКА нет (историческая формулировка при заведении
тикета).** Этот тикет заведён НЕ по факту наблюдаемого
флейка (в отличие от AT-BUG-085, где TC-115 реально упал в живом прогоне), а
превентивно — решением Lead по эскалации `AT-BUG-085-CHIP-ABSENT-CLASS-SIBLING`
(`state/escalations.md:2590`, 2026-08-20T03:22:31Z): класс дефекта («негативный
Then одноразовым `is_present`-примитивом короткого замыкания сразу после
стейт-меняющего действия, без settle/hold-опроса») уже доказан ТРИЖДЫ на
СОСЕДНИХ примитивах того же модуля/семейства модулей —

1. **AT-BUG-081** — `_poll_ratings_marker` (`library_steps.py`/родственный модуль),
2. **AT-BUG-082/083** — `_poll_files_tab_absent`/`_poll_tab_absent`
   (`library_steps.py`, `HorizontalPager`-переходы),
3. **AT-BUG-085** — `_poll_comment_collapsed` (`rating_steps.py`, ЭТОТ ЖЕ файл,
   комментарий-превью `RatingOverlay`),

— и `assert_chip_absent` (chip-виджет `RatingOverlay`, тот же composable-семья,
что комментарий AT-BUG-085) структурно идентичен ПРЕ-фикс форме
`assert_comment_collapsed_with_text` из AT-BUG-085: `not <примитив
короткого замыкания>(...)` сразу после действия, меняющего состояние
(`tap_selected_chip` — удаление тега; `reopen_listing_overlay` — закрытие/
переоткрытие bottom-sheet), без единого settle-чтения между действием и
чтением. Механизм риска идентичен AT-BUG-085 (`BaseScreen.is_present` ждёт
ПОЯВЛЕНИЯ узла, но возвращает `True` немедленно на первом снимке, если узел
ещё присутствует — не ждёт ИСЧЕЗНОВЕНИЯ) — см. `rating_steps.py:311-358`
(докстринг `_poll_comment_collapsed`/блок-комментарий класса).

## Суть долга

`framework/steps/rating_steps.py::assert_chip_absent` (ИСХОДНАЯ, ДОФИКСОВАЯ
реализация — тикет описывает проблему, которую фиксит; на HEAD после
2026-08-20T21:15:00Z функция переведена на settle+hold, см. «Обсуждение»):

```python
@allure.step("Then чип «{tag}» отсутствует среди тегов overlay")
def assert_chip_absent(driver, tag: str, timeout: int = 3):
    assert not RatingOverlay(driver).chip_visible(tag, timeout=timeout), (
        f"чип «{tag}» неожиданно присутствует среди тегов overlay"
    )
```

`chip_visible(...)` — тот же класс примитива, что был у `comment_expanded()`
до фикса AT-BUG-085: `is_present`-опрос, ждущий ПОЯВЛЕНИЯ узла до `timeout`,
но возвращающий `True` немедленно на первом снимке без ожидания
ИСЧЕЗНОВЕНИЯ. `not chip_visible(...)` вызывается СРАЗУ после
`tap_selected_chip` (удаление тега — стейт-меняющее действие) или
`reopen_listing_overlay` (закрытие+переоткрытие bottom-sheet, тоже
стейт-меняющее) — ни settle-, ни hold-фазы между действием и чтением нет.

## Адрес (СТРОГО, критик-гейт О7 AT-BUG-085, 2026-08-20 — адрес сверен по
фактическому файлу этим тикетом, номера НЕ уехали)

Сверено чтением `framework/tests/test_rating_listing.py` (2026-08-20,
`test_tap_selected_chip_removes_tag`, TC-091):

- **`framework/tests/test_rating_listing.py:366`**:
  ```python
  rating_steps.assert_chip_absent(driver, "Angst")
  ```
  — сразу ПОСЛЕ `rating_steps.tap_selected_chip(driver, "Angst")` (строка 363).
  Принадлежит классу — чинить.
- **`framework/tests/test_rating_listing.py:379`**:
  ```python
  rating_steps.assert_chip_absent(driver, "Angst")
  ```
  — сразу ПОСЛЕ `rating_steps.reopen_listing_overlay(driver, work.ao3_id)`
  (строка 377) + `rating_steps.open_tags_section(driver)` (строка 378).
  Принадлежит классу — чинить.

**НЕ ЧИНИТЬ `framework/tests/test_rating_listing.py:324`** (TC-090,
`test_add_freeform_tag_persists`):
```python
rating_steps.assert_chip_absent(driver, tag)
```
Эта строка — часть **Given**, ДО каких-либо стейт-меняющих действий этого
теста (тег `"spoiler-test"` ещё ни разу не добавлялся на чистом состоянии —
проверка «тега точно нет в начале», не «тег только что исчез после
действия»). Классу «Then сразу после действия без settle» НЕ принадлежит —
критик-гейт О7 AT-BUG-085 явно исключил эту строку из адреса, сверено
дословно тем же ходом.

## Направление фикса

По образцу `_poll_comment_collapsed` (AT-BUG-085, `rating_steps.py:359-408`) —
settle+hold опрос вместо одноразового чтения: settle-фаза (короткий поллинг,
пока `chip_visible` не сойдётся к `False`, ограниченный таймаутом) + hold-фаза
(`waits.assert_holds_for`-подобный бюджет, подтверждающий, что чип НЕ
перепоявляется обратно). Альтернативно — примитив `base_screen.wait_absent`
(если он уже покрывает нужную семантику ожидания исчезновения узла;
`framework/screens/base_screen.py` содержит `wait_absent` — сверить
сигнатуру перед выбором между copy-paste `_poll_comment_collapsed`-паттерна и
переиспользованием существующего примитива).

## Критерий готовности (Fixed)

- [x] Негативный ассерт `assert_chip_absent` переведён на settle/hold-полл
      (или эквивалентный `wait_absent`), а не одноразовое
      `not chip_visible(...)`. (`_poll_chip_absent`, `rating_steps.py`,
      2026-08-20)
- [x] Юнит-пин (device-free), различающий старую одноразовую семантику от
      новой settle/hold — по образцу `test_rating_comment_collapse_settle_
      unit.py` (AT-BUG-085). (`framework/tests/test_rating_chip_absent_
      settle_unit.py`, 6 тестов, `6 passed in 2.35s`)
- [x] `framework/tests/test_rating_listing.py:324` (TC-090, Given) НЕ
      затронут. (только `rating_steps.py`/новый юнит-файл/`arch_check.py`
      правились; `test_rating_listing.py` не тронут, сверено диффом)
- [ ] TC-091 зелёный (живой прогон), регресс не хуже baseline. **BLOCKED**
      (env_degraded, см. «Обсуждение» 2026-08-20T21:15:00Z и
      `state/escalations.md` ESC-037) — не достигнут в этом ходе.
- [x] Сиблинг-аудит по D-0043: остальные негативные `assert_*` в
      `rating_steps.py` уже проверены AT-BUG-085 (`assert_note_overlay_
      expanded_with_text`/`assert_overlay_still_open` — позитивные опросы,
      вне класса); повторная сверка не обязательна — фикс не коснулся
      других функций файла (только `assert_chip_absent`/`_poll_chip_absent`).

## Верификация (заполняет fix-verifier)

| Дата | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|
| — | — | — | Blocked (env), ждёт восстановления среды и живой верификации TC-091 |

## Обсуждение

**[builder @ 2026-08-20T11:52:04Z]** Заведён по прямому решению Lead
(state/escalations.md, запись `AT-BUG-085-CHIP-ABSENT-CLASS-SIBLING`,
2026-08-20T03:22:31Z: «завести test_debt-тикет ПРЕВЕНТИВНО»). Статус
превентивный подтверждён явно в тексте («Статус: ПРЕВЕНТИВНЫЙ» выше) —
красных прогонов TC-091 не зафиксировано ни в одном известном run-артефакте
на момент заведения тикета. Адрес (`:366`/`:379`, НЕ `:324`) сверен построчным
чтением фактического `framework/tests/test_rating_listing.py` этим же
ходом — номера строк совпадают с критик-гейтом О7 AT-BUG-085 дословно, не
уехали. Awaiting: none.

**[test-maintainer @ 2026-08-20T21:15:00Z]** Код-фикс: `assert_chip_absent`
переведён на settle+hold опрос (`_poll_chip_absent`, `framework/steps/
rating_steps.py`) — прямой аналог `_poll_comment_collapsed` (AT-BUG-085):
settle-фаза (до `_CHIP_ABSENT_SETTLE_TIMEOUT=3.0s`, интервал 0.3s,
`chip_visible(tag, timeout=1)`) + hold-фаза (`assert_holds_for`, бюджет
`_CHIP_ABSENT_HOLD_BUDGET=4.0s`, интервал 0.3s) — бюджеты позаимствованы у
`_COMMENT_COLLAPSE_*` без отдельного живого замера на этом конкретном
чтении (тот же осознанный trade-off, что у AT-BUG-085: направление отказа
безопасное — ложный красный, не ложный зелёный). `timeout`-параметр
`assert_chip_absent` убран (не имел вызывающих с explicit override —
сверено grep по всему `framework/`, все 3 call-sайта используют дефолт).

Device-free доказательство: новый файл `framework/tests/test_rating_chip_
absent_settle_unit.py` (6 тестов, прямой аналог `test_rating_comment_
collapse_settle_unit.py` AT-BUG-085 — транзитный стейл-позитив
проглатывается, старая одноразовая семантика ловит тот же сценарий и
падает, persistent-регрессия НЕ маскируется, settle-граница/hold-бюджет
тратится честно, поздняя ре-экспансия ловится ТОЛЬКО hold-фазой) —
`Invoke-Pytest tests/test_rating_chip_absent_settle_unit.py -v` →
дословно `6 passed in 2.35s`, `PYTEST_EXIT=0`.

Архитектурный гейт: `python scripts/arch_check.py` до фикса — `ошибок 1`
(новый файл импортирует `RatingOverlay` в `tests/`, легитимно по прецеденту
AT-BUG-059/062/082/083/085, но не был в ALLOWLIST); добавлена запись
`("tests/test_rating_chip_absent_settle_unit.py", "locators")` в
`scripts/arch_check.py::ALLOWLIST`. Отдельно снята СТАВШАЯ ФАНТОМНОЙ
запись `NEGATIVE_THEN_SETTLE_BASELINE[("steps/rating_steps.py",
"assert_chip_absent", "chip_visible")]` (правило 4 arch_check больше не
матчит эту функцию — паттерн `assert not X.chip_visible()` ушёл из AST
после фикса; оставленная запись сломала бы `test_real_repo_negative_then_
settle_baseline`). После обеих правок: `python scripts/arch_check.py` →
`ошибок 0` (26 WARN, тот же состав, что до фикса, минус исчезнувший
rating_steps-хит). `python -m pytest scripts/tests/test_arch_check.py -q`
→ `54 passed`. `python -m pytest scripts/tests -q` → `1923 passed, 1
skipped` — единственный failure в первом прогоне
(`test_p3_appium_url_and_memory.py::test_test_appium_healthy_env_default_
actually_reaches_listening_socket`, порт-коллизия) перепрогнан ИЗОЛИРОВАННО
→ `1 passed in 11.56s` (неродственный флейк, к этому диффу не относится).

Живая верификация (DoD «TC-091 зелёный, живой прогон») — **BLOCKED**.
`Get-Device` → `DEVICE: emulator-5554`; `Test-AppiumHealthy` (shallow) →
`OK (shallow, /status ready=true)` — оба здоровы ДО попытки.
`Invoke-Pytest 'tests/test_rating_listing.py::
test_tap_selected_chip_removes_tag' -v` упал ЕЩЁ В ФИКСТУРЕ
(`tagged_work_seeded` → `app_steps.clean_state()` →
`seed_db.ensure_db_initialized()`), ДО первого вызова изменённого кода:
`adb -s emulator-5554 shell am start -W -n com.example.ao3_wrapper/
com.example.ao3_wrapper.MainActivity` → `TimeoutError` (`core/adb.py:34`,
60s); последующий exception-handling сам вызвал `adb.force_stop()` → `am
force-stop com.example.ao3_wrapper` → ВТОРОЙ, ИДЕНТИЧНЫЙ по классу
`TimeoutError` (`core/adb.py:34`, 30s). 2 подряд `TimeoutError` на
adb-слое — буквальный триггер CLAUDE.md «Fail-fast среды» (docs/06 §5).
Диагностический мини-прогон СРАЗУ после падения: `Get-Device` →
`DEVICE: emulator-5554` (эмулятор всё ещё видим на adb-уровне); `Test-
AppiumHealthy -Deep` → **FAILED, 2/2 попытки**, дословно: `POST /session`
не удался оба раза с `"The instrumentation process cannot be initialized
within 30000ms timeout..."` (`uiautomator2-server/core.js:158`). Три
независимых сигнала (adb `am start -W` timeout, adb `am force-stop`
timeout, Appium `-Deep` instrumentation-init timeout 2/2) сходятся на
ОДНОМ классе деградации, не пересекающемся с изменённым кодом (падение —
в Given-сидинге фикстуры, задолго до первого вызова `assert_chip_absent`/
`_poll_chip_absent`). Не отлаживал на битой среде далее (докстринг
CLAUDE.md §«Fail-fast среды») — остановился, задокументировал диагноз,
`status: Open → Blocked` (`blocked_reason: environment`), полный witness
и запрос к Lead/человеку о восстановлении среды — `state/escalations.md`,
запись **ESC-037**. Код-дифф НЕ откатан (готов к повторной верификации).
`test_cases: ["TC-091"]` не меняю (сам кейс не затронут — только
реализация шага). `lock` снят.

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* (`bugs/AT-BUG-*.md`,
      status != Verified/Rejected) — новый экземпляр класса, не дубликат
      AT-BUG-081/082/083/085 (разные адреса кода)
- [x] Точная позиция в коде сверена чтением файла: `:366` и `:379`
      (принадлежат классу), `:324` явно исключён (Given, TC-090)
- [x] Severity обоснована — превентивный долг, красных прогонов нет,
      механизм риска идентичен трижды уже доказанному классу
- [x] Сиблинги AT-BUG-081/082/083/085 и класс дефекта идентифицированы
- [x] Направление фикса приложено (settle/hold-полл по образцу
      `_poll_comment_collapsed`/`wait_absent`)
- [x] Ни одного изменения в тестовой системе не внесено; только анализ
- [x] Долг-класс определён (негативный Then без settle/hold, flaky_test)
