---
id: AT-BUG-036
title: "app_steps.wait_persisted_tab_count: диагностика «последнее наблюдение» мертва — f-строка message вычисляется до первого опроса, holder всегда None"
type: test_debt
debt_kind: flaky_test
severity: minor
status: Fixed
found_in: "test-reviewer, F1-ревью батча tabs TC-131..135 (2026-07-31): в собственной красной пробе ревьюера падение честное (TimeoutError на содержательном Then), но текст диагностики — «не стало 1 (последнее наблюдение: None)» при фактически прочитанных 2 вкладках: f-строка параметра message= вычисляется в момент ВЫЗОВА wait_for, до первого опроса, поэтому holder.get('count') в ней всегда None."
fixed_in: "test-maintainer (Sonnet), 2026-08-01, attempt 2: `framework/steps/app_steps.py::wait_persisted_tab_count` — `except TimeoutError as exc: wait_err = exc`; если `holder` пуст (ни одного успешного наблюдения — predicate падал на КАЖДОМ опросе), исходный `TimeoutError` пробрасывается ЦЕЛИКОМ (сохраняет тип исключения и `; last error: ...`-контекст `wait_for` для fail-fast-детектора среды, AT-BUG-009); иначе `assert` несёт фактическое последнее наблюдение + причину `wait_err`, если она была. Закреплено device-free юнитом `framework/tests/test_wait_persisted_tab_count_diagnostics_unit.py` (обе ветки). Попутно исправлена неверная формулировка N1 в записи discussion attempt 1 (ошибочно утверждала, что `None` возникает при нечитаемом prefs — на деле `_parse_persisted_tabs` глотает ошибки парсинга и возвращает `0`, `None` — только при исключении в самом опросе)."
last_seen_in: "1.10"
test_cases: ["TC-131", "TC-135", "TC-136"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-01T22:20:47Z"
updated: "2026-08-01T22:26:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-036 — мёртвая диагностика wait_persisted_tab_count

## Окружение
Долг тестовой системы (`type: test_debt`; `debt_kind: flaky_test` — ближайшая категория схемы: дефект не роняет тест ложно, но уводит ТРИАЖ падения не туда, что и есть операционный симптом флейк-класса). Не зависит от сборки приложения — фикс целиком во `framework/steps/`.

## Суть долга

`framework/steps/app_steps.py:311-328` (`wait_persisted_tab_count`): параметр `message=` передаётся f-строкой, которая вычисляется в момент вызова `wait_for` — ДО первого опроса. `holder.get('count')` в этот момент всегда `None`, поэтому при любом таймауте диагностика печатает «(последнее наблюдение: None)» независимо от фактически прочитанных значений.

Живой пример (красная проба test-reviewer, F1-ревью TC-135, 2026-07-31): порча предпосылки дала честное падение `TimeoutError: число вкладок в open_tabs_urls не стало 1 … (последнее наблюдение: None)` — при том, что опрос реально читал 2 вкладки. «None» читается как «prefs вообще не прочитан» (класс ENV_ISSUE) и уведёт триаж в сторону от фактического «прочитано 2, ожидали 1» (класс APP_BUG/TEST_BUG).

## Корректный образец в этом же дереве

`framework/steps/settings_steps.py:285-297` — тот же приём сделан правильно: ожидание в `try/except TimeoutError`, затем `assert` с ЧТЕНИЕМ ПОСЛЕ ожидания — диагностика несёт фактическое последнее значение.

## Затронутые вызывающие

Все тесты, использующие `wait_persisted_tab_count` с ненулевым ожиданием (Grep по `framework/`): `test_tabs.py` (TC-131, TC-135 и соседи), заметки автоматизации TC-136. Обход сиблингов внутренней оси `framework/steps/` выполнен ревьюером при F1: других экземпляров класса «f-строка диагностики вычисляется до опроса» не найдено.

## Критерий готовности (Fixed)

- Диагностика `wait_persisted_tab_count` при таймауте печатает фактическое последнее прочитанное значение (приём settings_steps.py:285-297 или эквивалент — ленивое вычисление message).
- Красная проба: искусственный таймаут (ожидание заведомо недостижимого счёта) показывает в тексте падения РЕАЛЬНОЕ последнее наблюдение (не None); прогон приложен, порча откачена.
- Существующие вызывающие зелёные (точечный прогон TC-131 или TC-135 достаточен + красная проба выше).
- arch_check/validate_frontmatter 0/0.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-01 | 1.10 (не зависит от сборки приложения) | TC-135 (`test_cold_start_deep_link_reuses_single_home_tab`) + device-free `test_wait_persisted_tab_count_diagnostics_unit.py` (2 пробы) + красная проба обеих веток `wait_persisted_tab_count` | PASSED (см. дословный witness в discussion attempt 2) | test-maintainer, самопрогон (fix-verifier не запускался отдельным проходом в рамках этого B4-диспатча) |

## Обсуждение

**2026-07-31T18:18:00Z — Lead (Fable), заведение по докладу test-reviewer (правило 9):**
Доклад-аналог из F1-ревью батча TC-131..135 (не блокировал приёмку — падение содержательное, дефект только в тексте диагностики). Ревьюер код не правил (граница роли). Диспетчеризация — правило B4 следующим проходом.

**2026-08-01T22:12:01Z — координатор (Sonnet), attempt 1 ОТКЛОНЁН critic-вердиктом
(ДОРАБОТАТЬ), статус возвращён Open:** фикс attempt 1 (ленивое чтение `holder`
через `try/except TimeoutError: pass`) реально устранил `None` в диагностике
(подтверждено красной пробой), НО **сам факт `except TimeoutError: pass`
выбрасывает исходное исключение целиком** — вместе с ним теряется контекст
`wait_for` (`; last error: ...`), которым опирается зарегистрированный
fail-fast-детектор среды (`.claude/agents/{test-runner,test-maintainer,
test-automator,test-reviewer}.md`, матч по имени `TimeoutError`/
`ReadTimeoutError` на одном шаге, класс AT-BUG-009). На падающем предикате
(зависший adb) новый код отдаёт голый `AssertionError` без единого упоминания
причины — TOT ЖЕ класс увода триажа `ENV_ISSUE→TEST_BUG`, для которого этот
баг заведён, только с обратным знаком. Критик прогнал старую/новую ветку
device-free и показал разницу дословно. Redispatch attempt 2 с точным
фиксом критика: `except TimeoutError as exc: wait_err = exc`, причина —
в тексте assert'а (или переброс исходного `TimeoutError`, если `holder` пуст).
Неблокирующие находки критика (в очередь, не в этот дифф): N1 — докстринг
бага неверно описывает ветку `None` (сейчас исправляю ниже); N2 — тот же
`except TimeoutError: pass` в `settings_steps.assert_filter_profile_count`
(образец, откуда скопирован приём) несёт тот же изъян; N3 — вакуумный
класс «последнее наблюдение: 0» при мёртвом adb неотличимо от честного нуля;
N4 — нет регрессионного device-free юнита на саму диагностику (закрыть тем
же ходом attempt 2).

**Остаток класса «`except TimeoutError` глотает исключение `wait_for`, env-контекст теряется» (правило 5, ЗАВЕРШЁННЫЙ ПЕРЕЧЕНЬ по critic-входу attempt 2, 2026-08-01T22:26Z):**
исходный обход F1-ревьюера покрывал только предшествующий класс
(замороженная f-строка), не этот (глотание исключения) — уточнение N6.
Экземпляры:
- N2 — `framework/steps/settings_steps.py:291-297`
  (`assert_filter_profile_count`, образец, откуда скопирован приём) — тот
  же изъян, не почищен этим диффом.
- **N2а (найден critic-входом attempt 2, НЕ был в исходном перечне)** —
  `framework/steps/perf_steps.py:140-153` (`wait_memory_settled`):
  на предикате, падающем на каждом опросе (зависший `adb.total_pss_kb()`),
  `readings` остаётся пустым, `except TimeoutError: pass` глотает
  исключение целиком, `return readings[-1]` даёт `IndexError` —
  СТРОЖЕ, чем в app_steps.py: падение выглядит багом фреймворка, а не
  деградацией среды, env-причина уничтожена полностью (не просто ослаблена).
- N3 — вакуумный класс «последнее наблюдение: 0» при мёртвом adb
  неотличимо от честного нуля (предсуществует, не введён этим диффом).
- N5 (новый, critic attempt 2) — смешанная ветка (≥1 успешное наблюдение,
  затем зависший adb) в ИСПРАВЛЕННОМ `wait_persisted_tab_count` даёт
  `AssertionError` с причиной В ТЕКСТЕ, но БЕЗ литерала
  `TimeoutError`/`ReadTimeoutError` — до фикса этот сценарий отдавал
  `TimeoutError` (имя матчилось registered fail-fast-детектором
  `.claude/agents/{test-runner,test-maintainer,test-automator,
  test-reviewer}.md`, который сформулирован как матч ПО ИМЕНИ
  исключения). Не блокер (контекст сохранён текстом), но остаточный риск
  для будущего касания.

Устранение N2/N2а/N3/N5 — не входит в критерий готовности ЭТОГО фикса
(критик attempt 2 подтвердил: «кода менять не нужно, прогонов не нужно» —
запись в очередь достаточна). Следующий B4-проход по любому из них — новая
задача, отдельный диспатч.

**2026-08-01T22:05:00Z — test-maintainer (Sonnet), фикс (B4):**

Причина подтверждена чтением `framework/steps/waits.py::wait_for` — `message`
принимается как обычная `str`, а не отложенный колбэк (в отличие от
`wait_until`/`WebDriverWait.until`, которому можно передать объект
condition); f-строка, подставленная НАПРЯМУЮ в аргумент вызова, застывает
значением на момент вызова — до единственного последующего опроса.
Применил приём `settings_steps.assert_filter_profile_count`
(`framework/steps/settings_steps.py:285-297`): `wait_for` в
`try/except TimeoutError`, затем `assert holder.get("count") ==
expected_count` с f-строкой диагностики, читающей `holder["count"]` УЖЕ
ПОСЛЕ того, как опрос произошёл.

Дифф (`framework/steps/app_steps.py`, `wait_persisted_tab_count`):

```python
    try:
        wait_for(_check, timeout=timeout, message="число вкладок в open_tabs_urls не сошлось")
    except TimeoutError:
        pass
    assert holder.get("count") == expected_count, (
        f"число вкладок в open_tabs_urls не стало {expected_count} "
        f"(последнее наблюдение: {holder.get('count')})"
    )
```

**Критерий 1 (диагностика несёт фактическое значение)** — код выше: `assert`
вычисляет f-строку сообщения ПОСЛЕ вызова `wait_for`/опроса, `holder["count"]`
на этот момент несёт последнее реально прочитанное значение.

**Исправление (2026-08-01T22:20:47Z, N1 критика attempt-1-ревью):** формулировка выше
БЫЛА НЕВЕРНОЙ. `None` НЕ возникает из «опрос не смог распарсить prefs» —
`_parse_persisted_tabs` глотает `JSONDecodeError`/`TypeError` и честно
возвращает `[]` (`len([]) == 0`), то есть нечитаемый/битый/пустой
`open_tabs_urls` даёт наблюдение `0`, не `None`. `holder.get("count")`
остаётся `None` РОВНО в одном случае: опрос НИ РАЗУ не завершился без
исключения — т.е. само чтение (`_read_tabs_prefs_raw()`, `adb.run_as`)
падало на КАЖДОЙ попытке (например, завис adb — AT-BUG-009), и `holder`
никогда не был присвоен. Это именно та ветка, которую attempt 1 ломал
(`except TimeoutError: pass` терял контекст `wait_for`) и которую чинит
attempt 2 (см. запись ниже) — в этой ветке правильное поведение теперь не
«показать None», а пробросить исходный `TimeoutError` целиком.

**Критерий 2 (красная проба, дословный вывод)** — окружение поднято
канонически (`env.ps1` → `tasks.ps1` → `Start-Emulator -WritableSystem` →
`Install-App` → `Start-Appium`). Живое состояние prefs ДО пробы (одна
персистнутая вкладка, `am start` дефолтного экрана):

```
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <int name="active_tab_index" value="0" />
    <string name="open_tabs_urls">[{&quot;historyEntries&quot;:[{&quot;scrollY&quot;:0,&quot;url&quot;:&quot;https://archiveofourown.org/&quot;},{&quot;scrollY&quot;:0,&quot;url&quot;:&quot;https://archiveofourown.org/works/900000001&quot;}],&quot;historyIndex&quot;:1,&quot;scrollY&quot;:0,&quot;url&quot;:&quot;https://archiveofourown.org/works/900000001&quot;}]</string>
</map>
```

Искусственный недостижимый счёт (заведомо непроходимый `expected_count`,
timeout=3с) через прямой вызов ИСПРАВЛЕННОЙ `wait_persisted_tab_count`
(скрипт-проба вне репозитория — сама `framework/steps/app_steps.py` НЕ
портилась, откатывать нечего; изолированный вызов через `adb`, без
Appium-сессии):

```
D:\AO3_tests\framework\.venv\Scripts\python.exe red_probe_at_bug_036.py
CAUGHT AssertionError: число вкладок в open_tabs_urls не стало 999999 (последнее наблюдение: 1)
```

Реальное последнее наблюдение (`1`) — не `None`. Красная проба честная
(искусственный недостижимый `expected_count`, не изменение исходников) и не
оставила следов в репозитории — портить/откатывать было нечего.

**Критерий 3 (существующие вызывающие зелёные)** — точечный прогон TC-135
(`test_cold_start_deep_link_reuses_single_home_tab`, использует
`wait_persisted_tab_count(1, timeout=5)` напрямую) через каноническую форму:

```
powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_tabs.py -k test_cold_start_deep_link_reuses_single_home_tab -v"

============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\AO3_tests\framework\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\AO3_tests\framework
configfile: pytest.ini
plugins: allure-pytest-2.16.0, rerunfailures-16.4
collecting ... collected 11 items / 10 deselected / 1 selected

tests/test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab[tab_markers.mitm] PASSED [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
====================== 1 passed, 10 deselected in 22.92s ======================
PYTEST_EXIT=0
```

Окружение погашено по завершении (`Stop-NodeProcesses` — Appium; каноническая
форма `env.ps1`-загруженного `adb emu kill` — эмулятор; `Get-Device` после
подтвердил `NO DEVICE`).

**Критерий 4 (arch_check/validate_frontmatter 0/0):**

```
> python D:\AO3_tests\scripts\arch_check.py
arch_check: ошибок 0, предупреждений 0

> python D:\AO3_tests\scripts\validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

Все 4 пункта критерия готовности выполнены дословным witness'ом выше.
`app-under-test/` не тронут. Затронутые вызывающие (`test_tabs.py`
TC-131/TC-135 и соседи, заметки TC-136) используют ту же
`wait_persisted_tab_count` без изменения сигнатуры — фикс внутренний,
вызывающий код не менялся. Обход сиблингов внутренней оси
`framework/steps/` уже выполнен ревьюером при F1 (в баге) — повторно не
искал.

(attempt 1 отклонён critic-вердиктом — см. запись 2026-08-01T22:12:01Z ниже;
статус не менялся этим ходом, changed в attempt 2.)

**2026-08-01T22:20:47Z — test-maintainer (Sonnet), attempt 2 (B4, redispatch
после critic REJECT):**

Причина attempt-1-регресса (см. запись координатора 22:12:01Z выше) —
`except TimeoutError: pass` глотал исходное исключение целиком. Применён
точный фикс критика: `except TimeoutError as exc: wait_err = exc`; если
`holder` пуст (predicate падал на КАЖДОМ опросе — ни одного успешного
наблюдения), исходный `TimeoutError` пробрасывается ЦЕЛИКОМ (`raise` без
аргументов внутри `except`) — сохраняет и тип исключения, и `; last
error: ...`-контекст `wait_for`, на который матчит fail-fast-детектор
среды. Если наблюдение хотя бы одно было — `assert` несёт фактическое
последнее наблюдение (сохранено исправление attempt 1) и, если `wait_for`
всё же поймал исключение на каком-то опросе, причину `wait_err` — тоже в
тексте, не теряется.

Дифф (`framework/steps/app_steps.py`, `wait_persisted_tab_count`):

```python
    holder: dict[str, int] = {}
    wait_err: TimeoutError | None = None

    def _check() -> bool:
        holder["count"] = len(_parse_persisted_tabs(_read_tabs_prefs_raw()))
        return holder["count"] == expected_count

    try:
        wait_for(_check, timeout=timeout, message="число вкладок в open_tabs_urls не сошлось")
    except TimeoutError as exc:
        wait_err = exc
        if "count" not in holder:
            raise
    assert holder.get("count") == expected_count, (
        f"число вкладок в open_tabs_urls не стало {expected_count} "
        f"(последнее наблюдение: {holder.get('count')})"
        + (f"; ожидание прервано: {wait_err}" if wait_err is not None else "")
    )
```

**N1 (формулировка критерия 1 в записи attempt 1)** — исправлена НАПРЯМУЮ в
самом тексте attempt-1-записи выше (не отдельной ремаркой): верное
объяснение — `None` возникает ТОЛЬКО когда опрос ни разу не завершился без
исключения (само чтение падало на каждой попытке); нечитаемый/битый JSON
даёт наблюдение `0` (`_parse_persisted_tabs` глотает `JSONDecodeError`/
`TypeError` -> `[]`), не `None`.

**N4 (регресс-гвард)** — `framework/tests/test_wait_persisted_tab_count_diagnostics_unit.py`,
device-free (монкипатч `app_steps._read_tabs_prefs_raw`), 2 пробы:
1. читаемые prefs + недостижимый count -> `AssertionError` с реальным
   последним наблюдением (не `None`);
2. падающий на каждом опросе predicate (симуляция AT-BUG-009) ->
   пробрасывается исходный `TimeoutError` с `; last error: ...`-контекстом.

Дословный прогон:

```
powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_wait_persisted_tab_count_diagnostics_unit.py -v"

============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\AO3_tests\framework\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\AO3_tests\framework
configfile: pytest.ini
plugins: allure-pytest-2.16.0, rerunfailures-16.4
collecting ... collected 2 items

tests/test_wait_persisted_tab_count_diagnostics_unit.py::test_wait_persisted_tab_count_shows_last_observation_on_readable_timeout PASSED [ 50%]
tests/test_wait_persisted_tab_count_diagnostics_unit.py::test_wait_persisted_tab_count_preserves_timeout_context_on_failing_predicate PASSED [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
============================== 2 passed in 2.45s ==============================
PYTEST_EXIT=0
```

**Критерий 2 (красная проба, ОБЕ ветки, дословный вывод, живой эмулятор):**
скрипт-проба вне репозитория (сама `framework/steps/app_steps.py` НЕ
портилась), вывод писан напрямую в UTF-8-файл (консоль Windows PowerShell
5.1 в этой среде мангрирует кириллицу независимо от chcp) и прочитан
обратно:

```
=== BRANCH A: readable prefs, недостижимый count -> AssertionError с последним наблюдением ===
CAUGHT AssertionError: число вкладок в open_tabs_urls не стало 999999 (последнее наблюдение: 1); ожидание прервано: число вкладок в open_tabs_urls не сошлось (after 3s)

=== BRANCH B: падающий предикат (симуляция зависшего adb) -> TimeoutError с контекстом ===
CAUGHT TimeoutError: число вкладок в open_tabs_urls не сошлось (after 3s); last error: adb shell run-as ... не ответил за 10s (AT-BUG-009)
```

Branch A (readable prefs, недостижимый ожидаемый счёт) — честный
`AssertionError` с РЕАЛЬНЫМ последним наблюдением (`1`), не `None`.
Branch B (predicate падает на каждом опросе — симуляция зависшего adb) —
исходный `TimeoutError` пробрасывается ЦЕЛИКОМ, несёт `; last error:
...`-контекст с сигнатурой `AT-BUG-009` — именно то, что искал критик.

**Критерий 3 (существующие вызывающие зелёные)** — точечный прогон TC-135
через каноническую форму (окружение поднято канонически: env.ps1 →
tasks.ps1, эмулятор уже был поднят и виден `Get-Device` -> `DEVICE:
emulator-5554`, `Start-Appium`, `Install-App`):

```
powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_tabs.py -k test_cold_start_deep_link_reuses_single_home_tab -v"

============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\AO3_tests\framework\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\AO3_tests\framework
configfile: pytest.ini
plugins: allure-pytest-2.16.0, rerunfailures-16.4
collecting ... collected 12 items / 11 deselected / 1 selected

tests/test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab[tab_markers.mitm] PASSED [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
====================== 1 passed, 11 deselected in 20.34s ======================
PYTEST_EXIT=0
```

Окружение погашено частично по завершении (`Stop-NodeProcesses` — Appium,
запущенный этим ходом; эмулятор был поднят ДО начала этой сессии
(`Get-Device` подтвердил `DEVICE: emulator-5554` до старта работы) —
оставлен как есть, не мой к выключению).

**Критерий 4 (arch_check/validate_frontmatter 0/0):**

```
> python D:/AO3_tests/scripts/arch_check.py
arch_check: ошибок 0, предупреждений 0

> python D:/AO3_tests/scripts/validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

Все 4 пункта критерия готовности выполнены дословным witness'ом. Ни одна
правка `app-under-test/` не затронута. **Не входит в этот дифф (в очередь,
не в скоуп)**: N2 (тот же изъян в `settings_steps.assert_filter_profile_count`)
и N3 (вакуумный класс «последнее наблюдение: 0» при мёртвом adb) — критик
явно оставил их вне attempt 2, scope не расширялся. Status: Open → Fixed
(guard `type: test_debt`, `by: test-maintainer`), лок снят.
