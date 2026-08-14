---
id: AT-BUG-064            # test_debt, сквозная нумерация с BUG-xxx
title: Остаточный device-прокси переживает перезапуск эмулятора
type: test_debt
debt_kind: broken_environment
severity: minor
status: Verified
found_in: "source_commit cc201f789f0fb123722bbba7b29b8e0c6412dac1 (versionCode 12, dev-local)"
fixed_in: "test-maintainer (Sonnet), 2026-08-11: (а) `framework/core/mitm.py::get_device_proxy()`/`ensure_no_residual_proxy()` -- новые функции читают текущий `global http_proxy` устройства и снимают его, если он НЕ \"чист\" (не пусто/`\"null\"`/`\":0\"`); подключены через новый чистый хелпер `framework/tests/conftest.py::_ensure_no_residual_device_proxy()`, вызываемый из УЖЕ существующей session-scoped autouse-фикстуры `_ensure_app_installed` -- запускается РАЗ на весь pytest-прогон, ДО ЛЮБОГО теста (live или replay), не только внутри `replay`-фикстуры (та покрывала бы лишь replay-тесты -- недостаточно, наблюдение бага: остаток пойман БЕЗ единого replay-теста в сессии). (б) `try/finally` вокруг `set_device_proxy()`/`start_replay()`/`yield` в фикстуре `conftest.py::replay` УЖЕ существовал (введён AT-BUG-043 attempt 2, `conftest.py:833-860`) -- прочитан и верифицирован целиком, повторной реализации не требовалось; задокументировано как necessary-but-insufficient слой (не покрывает hard-kill/креш машины/снапшот, снятый в неудачный момент -- ровно тот класс, что закрывает (а)). B4 rework attempt 2 (критик-вход, блокеры B1/B2): B2 -- `_ensure_no_residual_device_proxy()` теперь ТАКЖЕ вызывается из `pytest_runtest_setup()` (`conftest.py:108-181`, вызов на л. 180) СРАЗУ после `_reset_ca_check()`, если в текущем тесте произошёл device-liveness recovery (AT-BUG-026), -- твин уже существующего паттерна `_reset_ca_check`; без этого проверка (а) была недостижима ровно для сценария заголовка бага (прокси переживает ПЕРЕЗАПУСК эмулятора recovery-путём, не только session-старт). B1 -- ложная строка «сиблингов не найдено» исправлена на честную (см. «Сиблинги»); реальные сиблинги (`adb.py::set_font_scale`/`set_night_mode`) НЕ покрыты тем же fail-safe в этом ходе (обоснование непропорциональности + план -- новый test_debt `AT-BUG-066`)."
last_seen_in: ""
test_cases: []
runs: [RUN-20260811-0405]
duplicates: []
regression_of: ""
status_since: "2026-08-13T22:09:12Z"
updated: "2026-08-13T22:09:12Z"
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

# AT-BUG-064 — Остаточный device-прокси переживает перезапуск эмулятора

## Окружение
- Эмулятор: AVD `ao3_test_api34`, снапшот-буд (`-no-snapshot-load` не применялся)
- Режим: replay (проблема заметна при смене режимов между replay-проходом и live-прогоном)
- Приложение: dev-local (versionCode 12, cc201f78)

## Шаги воспроизведения (Given-When-Then)

**Given** окружение поднято с нуля (`Start-Emulator -WritableSystem`, `Install-App`, Appium запущен)

**When** запущен replay-прогон (TC-009), который вызывает `set_device_proxy()` в фикстуре setup, затем ПЕРЕЗАПУЩЕН эмулятор через снапшот-буд (без БЕЗ переустановки приложения и ПЕРЕД следующим live-прогоном)

**Then (ожидалось)** прокси устройства снят (очищен), эмулятор поднят чистым, отсутствует настройка `http_proxy` в системных параметрах

**Actual (фактически)** после перезапуска эмулятора прокси `10.0.2.2:8080` остаётся выставленным в системных параметрах Android, что приводит к `net::ERR_PROXY_CONNECTION_FAILED` на live-прогонах (прокси недоступен, mitm не поднят)

## Частота
Всегда, когда: (1) replay-прогон завершился с вызовом `set_device_proxy()` и (2) эмулятор перезагружается через snapshot-boot ДО явного снятия прокси, и (3) следующий live-прогон пытается открыть реальный URL.

Наблюдено в RUN-20260811-0405, перепрогон попытка c: `adb shell settings get global http_proxy` → `10.0.2.2:8080` на СВЕЖЕЗАГРУЖЕННОМ эмуляторе, без единого replay-теста в этой сессии.

## Артефакты
- Triaged smoke-run: `runs/RUN-20260811-0405.md`, раздел «Дефекты-собратья (г)»
- Механизм: `framework/core/mitm.py` функции `set_device_proxy()` (л. 506-523) и `clear_device_proxy()` (л. 525-541)
- Фикстура replay: `framework/tests/conftest.py::replay`

## Анализ (bug-reporter)

Из прочтения `framework/core/mitm.py`:

- `set_device_proxy()` (л. 506-523) выполняет: `subprocess.run([adb, "shell", "settings", "put", "global", "http_proxy", "10.0.2.2:8080"], ...)`
  - Это persistent-настройка операционной системы Android (записывается в global settings database)
  - Настройка **НЕ** удаляется при перезагрузке эмулятора через `-snapshot-load`, т.к. это состояние persists в пользовательских настройках

- `clear_device_proxy()` (л. 525-541) должна снять прокси: `subprocess.run([adb, "shell", "settings", "put", "global", "http_proxy", ":0"], ...)`
  - Однако гарантия вызова отсутствует на путях аварийного завершения
  - Если worker/session умирает между `set_device_proxy()` и `clear_device_proxy()`, или если `clear_device_proxy()` отрабатывает ПОСЛЕ того, как уже сделан снапшот эмулятора, оставшийся прокси переживает рестарт

- Workaround: вручную снять канонической формой `adb shell settings put global http_proxy :0` — это кончает воспроизведение

Поведение соответствует документации mitm.py л. 11: «прокси гостя выставлен на 10.0.2.2:8080 (set_device_proxy)» — настройка сделана явно в Android settings, это не временная сессионная переменная.

## Предложенные кандидаты фикса

**(а) Fail-safe проверка остаточного прокси на подъёме окружения:**
- При вызове `Start-Emulator` (задач.ps1) или инициализации фикстуры `replay` — проверить наличие выставленного прокси `adb shell settings get global http_proxy` и снять его, если он остался от предыдущей сессии
- Этот путь ловит случайный остаток после любого аварийного выхода предшествующего прогона

**(б) Finally-гарантия clear_device_proxy в фикстуре replay:**
- Обернуть `set_device_proxy()` и `start_replay()` в `try/finally` блок внутри фикстуры `conftest.py::replay`, чтобы `clear_device_proxy()` гарантировалась даже при аварийном завершении test-воркера
- Это закроет дыру на вызовах до снятия снимка эмулятора

Комбинация обоих подходов предпочтительна: (б) закрывает дефект в штатном потоке, (а) ловит остатки от предыдущих сессий и других аварийных случаев.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых багов (`bugs/`, status != Verified/Rejected) — `grep -l "остаточный прокси\|clear_device_proxy\|broken_environment" bugs/AT-BUG-*.md` → результаты только для этого бага
- [x] Репро-шаги воспроизводят проблему (наблюдалось в RUN-20260811-0405, перепрогон попытка c, диагностический вывод аттачирован)
- [x] Severity обоснована: minor — редкий случай (требует аварийного выхода на конкретном шаге), ручная ремедиация известна (снять вручную каноничной формой)
- [x] Механизм и коды функций сверены по фактическому содержимому mitm.py (не спекуляция)
- [x] Ссылка на связанный run и триаж failure-analyst приложена
- [x] B4 test-maintainer, 2026-08-11: (а) реализован (`framework/core/mitm.py`
      + `framework/tests/conftest.py::_ensure_no_residual_device_proxy`); (б)
      проверен уже существующим (AT-BUG-043, повторно не писан). Красная
      проба откачена по байтовой копии (`cmp` подтвердил идентичность), 3
      подряд зелёных прогона нового unit-набора, соседние device-free пробы и
      `python -m pytest scripts/tests -q` зелёные, `validate_frontmatter.py`
      чист, `app-under-test/` не тронут. `status: Open -> Fixed`, лок снят.

## Обсуждение

**test-maintainer, 2026-08-11 — реализация.**

Прочитан `framework/core/mitm.py` целиком (`set_device_proxy`/
`clear_device_proxy`, л. 506-541) и `framework/tests/conftest.py::replay`
целиком (на момент attempt 1: л. 727-803; строки ниже актуализированы ПОСЛЕ
B4 rework attempt 2 -- добавление B2-фикса выше по файлу сдвинуло функцию
на `conftest.py:784-860`, см. «B2» ниже) — обе функции, что называл
артефакт.

**(б) уже реализован, повторно не пишу.** `conftest.py::replay`
(актуально: л. 784-860) УЖЕ оборачивает `mitm.set_device_proxy()` +
`mitm.start_replay()` + `mitm.wait_device_proxy_reachable()` + `yield` в
`try`, с `finally`, безусловно зовущим `mitm.stop()`/`mitm.clear_device_
proxy()` (раздельным вложенным `try/finally`, чтобы `stop()` не мог
заблокировать `clear_device_proxy()`) — это фикс AT-BUG-043 attempt 2
(критик-вход, блокер 1), сделанный ДО завода этого бага. Проверено
чтением: `try:` стоит прямо перед `mitm.set_device_proxy()` (актуально:
л. 833), `finally:` покрывает и `stop()`, и `clear_device_proxy()`
(актуально: л. 838-860) — ЛЮБОЕ штатное Python-исключение
setup/теста/`stop()` гарантированно доходит до `clear_device_proxy()`.
Задача не требовала переписывать это заново.

**Но (б) недостаточен для СЦЕНАРИЯ этого бага.** `try/finally` защищает
только от исключений ВНУТРИ живого CPython-процесса — не от hard-kill
(`taskkill /F`, обрыв worker'а), краша хост-машины или снапшота эмулятора,
сохранённого в неудачный момент (ровно то, что называет артефакт: «worker/
сессия умирает между `set_device_proxy()` и `clear_device_proxy()»). Именно
поэтому реализован (а) — независимый слой на СЛЕДУЮЩЕМ старте.

**(а) — куда: Python session-scope, не PowerShell `Start-Emulator`.**
Рассмотрены оба места, названные артефактом:
- `scripts/tasks.ps1::Start-Emulator` поднимает окружение один раз в начале
  дня/сессии — ловит остаток только на буде эмулятора, но в репозитории НЕТ
  PowerShell-тестовой инфраструктуры (Pester и т.п. отсутствуют, проверено
  `Glob`/`Grep` — 0 совпадений); "красная проба" и device-free unit-
  верификация из DoD были бы недостижимы без нового test-раннера — риск
  непропорционален.
- Фикстура `replay` — НЕ подходит: она инстанцируется только для тестов,
  явно запросивших `replay` (`@pytest.mark.replay`). Наблюдение самого бага
  (RUN-20260811-0405) — остаток пойман на прогоне БЕЗ единого replay-теста,
  чисто live-тестом. Проверка внутри `replay` пропустила бы ровно
  воспроизведённый случай.
- Выбрано: session-scope точка входа `conftest.py::_ensure_app_installed`
  (`scope="session", autouse=True`) — единственная фикстура, которая уже
  гарантированно инстанцируется ДЛЯ КАЖДОГО теста сессии, live и replay
  одинаково, ДО первой навигации. Логика вынесена в отдельную ЧИСТУЮ функцию
  `_ensure_no_residual_device_proxy()` (не саму fixture-функцию — pytest 9
  запрещает прямой вызов декорированной fixture, тот же приём, что уже
  существующие `_ensure_replay_ca`/`_ensure_upstream_fast`), чтобы
  device-free юнит-проба могла звать её напрямую с монки-патченным
  `mitm.ensure_no_residual_proxy`.
- Присоединено ИМЕННО к `_ensure_app_installed`, а не к новой отдельной
  `autouse`-фикстуре: `_ensure_app_installed` — единственная существующая
  session-autouse точка, которую ~20 device-free `test_*_unit.py`
  переопределяют no-op'ом, чтобы не трогать устройство при сборе полного
  набора. Отдельная НОВАЯ session-autouse фикстура заставила бы КАЖДУЮ из
  них ловить реальный `adb`-вызов, если её тоже не переопределить бы —
  присоединение к уже переопределяемой точке даёт классовую полноту без
  правки полутора десятков файлов.

**Новая логика (`framework/core/mitm.py`):**
- `get_device_proxy()` — читает `adb shell settings get global http_proxy`
  (тот же `ADB_SHELL_TIMEOUT`/`TimeoutError`-паттерн, что
  `set_device_proxy`/`clear_device_proxy`, AT-BUG-009).
- `ensure_no_residual_proxy() -> str | None` — если значение НЕ "чисто"
  (не пусто/`"null"`/`":0"`), зовёт `clear_device_proxy()` и возвращает
  СТАРОЕ значение (для логирования); иначе — `None`, без единой лишней
  adb-записи (счастливый путь: одно чтение).

**Почему это не маскировка.** Причина дефекта — persistent Android-
настройка, которую teardown ОДНОЙ сессии не гарантированно снимает при
её аварийной смерти; фикс не ослабляет никакой assert и не глотает
ошибку — он добавляет ВТОРОЙ независимый момент проверки (старт СЛЕДУЮЩЕЙ
сессии), symmetричный по духу существующему паттерну `_ca_checked`/
`_upstream_checked` этого же файла (fail-safe на границе сессии, не внутри
теста).

**Красная проба (откат чист, правило 8 CLAUDE.md).** Байтовая копия
`framework/core/mitm.py` (уже несущего мою правку) снята в scratchpad ДО
порчи (`git status --porcelain` зафиксирован: ` M framework/core/mitm.py`
— ожидаемо, файл уже нёс легитимный дифф этой задачи). Временно убран
вызов `clear_device_proxy()` внутри `ensure_no_residual_proxy()` (закомментирован,
функция возвращает старое значение, НЕ снимая прокси). Прогон
`test_ensure_no_residual_proxy_clears_stale_value` упал ОСМЫСЛЕННО, поймав
ровно диагностированный класс дефекта (прокси НЕ снят):
```
assert len(calls) == 2
AssertionError: assert 1 == 2
 +  where 1 = len([['...adb.exe', 'shell', 'settings', 'get', 'global', 'http_proxy']])
```
— т.е. вторая (put-)команда не ушла вовсе; остальные 8 тестов модуля
остались зелёными (не задеты). Файл восстановлен ИЗ БАЙТОВОЙ КОПИИ (не
`git checkout`); `cmp` байтовой копии и восстановленного файла подтвердил
побайтовую идентичность (`IDENTICAL: byte-for-byte restore confirmed`).

## Верификация (attempt 1 — исторический снимок; см. «B4 rework attempt 2» ниже за актуальные счётчики после B2-фикса: файл вырос до 12 тестов, `_unit`-набор — до 237)

Device-free unit-уровень (тот же класс ограничения, что предыдущие два
задачи этого прохода, AT-BUG-062/063 — реальный краш/аварийное завершение
worker'а МЕЖДУ `set_device_proxy()`/`clear_device_proxy()` непропорционально
дорог/рискован для детерминированного воспроизведения в рамках этой
задачи; честно, не переоцениваю доказанность). Новый файл
`framework/tests/test_residual_proxy_guard_unit.py` (9 тестов на attempt 1, device-free,
монки-патчит только `subprocess.run`):
- `get_device_proxy()` парсит/обрезает вывод adb; зависший adb даёт явную
  `TimeoutError` с тегом AT-BUG-064 (не голый `TimeoutExpired`).
- `ensure_no_residual_proxy()` — noop на чистом устройстве (`"null"`/`":0"`/
  пусто, параметризовано 4 вариантами) — ноль лишних adb-записей;
  на остаточном прокси — снимает его (get+put) и возвращает старое значение.
- `conftest._ensure_no_residual_device_proxy()` — предупреждает
  `warnings.warn` с тегом AT-BUG-064, когда `mitm.ensure_no_residual_proxy()`
  нашёл остаток; молчит на чистом устройстве.

Доказывает КОРРЕКТНОСТЬ ЛОГИКИ (а) — не доказывает, что реальный аварийно
убитый worker + реальный snapshot-boot реального эмулятора воспроизводят
и лечат ровно этот сценарий живьём; это доказывалось бы отдельным дорогим
live-экспериментом (убить процесс pytest в момент между `set_device_proxy`/
`clear_device_proxy`, сохранить снапшот, перезагрузить, замерить), вне
скоупа минимальной верификации этой задачи. Уверенность: средняя —
код-путь и unit-уровень доказаны, живой end-to-end цикл НЕ воспроизведён.

Прогоны (дословно):
```
$ powershell ...; Invoke-Pytest tests/test_residual_proxy_guard_unit.py -q
.........
9 passed in 0.07s
PYTEST_EXIT=0
```
(3 подряд зелёных прогона после восстановления из байтовой копии —
0.07s/0.07s/0.08s, все `9 passed`, `PYTEST_EXIT=0`.)

Регрессия по соседним device-free пробам, трогающим тот же участок
`conftest.py`/`mitm.py` (`test_mitm_proxy_reachable_unit.py`,
`test_replay_ca_check_unit.py`, `test_mitm_upstream_guard_unit.py`,
`test_mitm_port_race_unit.py`, `test_device_liveness_guard_unit.py`):
```
40 passed, 1 warning in 3.16s
PYTEST_EXIT=0
```

Полный device-free `_unit`-набор (регрессия правки session-autouse
фикстуры на ВСЕ ~20 файлов, которые её переопределяют no-op'ом):
```
$ Invoke-Pytest tests -k _unit -q
211 passed, 174 deselected, 1 warning in 22.79s
PYTEST_EXIT=0
```

```
$ python -m pytest scripts/tests -q
1120 passed, 1 skipped in 31.68s
```

```
$ python scripts/validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

**Сиблинги (правило 9 CLAUDE.md) — ИСПРАВЛЕНО, см. B4 rework attempt 2
ниже.** ~~Единственный другой персистентный Android-`settings`-стейт...
других мест того же класса не найдено~~ — эта строка была НЕВЕРНОЙ (найдено
критиком на приёмке attempt 1): грепом `"settings put global\|settings get
global"` структурно нельзя найти другой namespace (`system`) или другую
команду (`cmd uimode`) — вывод «не найдено» ничего не доказывал за
пределами формы самого паттерна (тот же класс, что F-34 CLAUDE.md про
негативный греп без позитивного контроля). Честная версия — см. секцию
«B1: ложное утверждение "сиблингов не найдено"» ниже.

**app-under-test/ не тронут.**

## B4 rework attempt 2 (критик-вход, блокеры B1/B2) — test-maintainer, 2026-08-11

Критик подтвердил ОСНОВНОЙ сценарий эмпирически (остаточный прокси на
живом устройстве → прогон сессии → `PYTEST_EXIT=0` + `:0`), но нашёл 2
блокера. Оба закрыты этим ходом.

### B1: ложное утверждение "сиблингов не найдено" — сиблинги реально есть

Грепом того же семантического класса («персистентное состояние ОС гостя,
выставляемое тестовой инфраструктурой, снимаемое только in-process
teardown'ом»), но БЕЗ сужения на namespace/команду `http_proxy`, найдены:

- **`framework/core/adb.py:179-186::set_font_scale()`** — `settings put
  system font_scale {scale}` (используется `test_accessibility.py:26-36`,
  фикстура `font_scale_1_3`, TC-107).
- **`framework/core/adb.py:173-176::set_night_mode()`** — `cmd uimode night
  yes/no` (используется `test_compatibility.py:109-149` TC-110,
  `test_settings.py:119-149` TC-049).

Оба защищены ТОЛЬКО in-process `try/finally` (класс (б) — как `http_proxy`
ДО этого бага), fail-safe слоя (а) у них нет. Решение (не молчу, правило 9
CLAUDE.md): фикс СЕЙЧАС непропорционален (обоснование — см. `AT-BUG-066`,
заведён этим ходом, `debt_kind: broken_environment`, содержит и класс
находки, и оценку стоимости обобщения для каждого из двух мест
раздельно — `font_scale` дёшево, `night mode` требует отдельного
расследования способа чтения текущего значения). Ссылка: `bugs/AT-BUG-066.md`.
Ложная строка в «Сиблинги» выше зачёркнута, не удалена (сохраняет след
находки критика).

### B2: своя же поверхность recovery не была покрыта — ядро заголовка бага

`framework/tests/conftest.py::pytest_runtest_setup()` (device-liveness
recovery, AT-BUG-026) перезапускает эмулятор через `tasks.ps1::Start-Emulator`
— ТОТ ЖЕ snapshot-boot механизм, что называет заголовок этого бага
(«...переживает перезапуск эмулятора»). session-scoped проверка (а),
добавленная attempt 1, вызывается ТОЛЬКО из `_ensure_app_installed`
(инстанцируется РАЗ на весь прогон, ДО первого теста) — недостижима для
recovery, случившегося В СЕРЕДИНЕ прогона.

Фикс — твин уже существующего в том же хуке паттерна `_reset_ca_check()`
(introduced AT-BUG-026 F4, тот же класс проблемы для `_ca_checked`):
`conftest.py::pytest_runtest_setup()` теперь зовёт
`_ensure_no_residual_device_proxy()` СРАЗУ рядом с `_reset_ca_check()`,
если в текущем тесте произошёл recovery (`_pending_recovery_warning is not
None`). В отличие от CA-кеша, `ensure_no_residual_proxy()` не кеширует
результат сама (каждый вызов заново читает `adb shell settings get global
http_proxy`) — повторный вызов после recovery не требует отдельного
flag-сброса, только самого вызова.

Юнит-пробы (device-free, `test_residual_proxy_guard_unit.py`, тот же приём
прямого вызова `pytest_runtest_setup(fake_item)` с duck-typed `.fixturenames`,
что `test_device_liveness_guard_unit.py` для B1 AT-BUG-026 — файл НЕ
трогается, владеет им параллельный AT-BUG-063 rework):
- recovery произошёл → `_ensure_no_residual_device_proxy()` вызвана ровно 1 раз;
- recovery НЕ произошёл → НЕ вызвана;
- тест без фикстуры `driver` → хук вообще не трогает guard/проверку.

### Витнесс (device, эмпирический — тот же класс, что критик снял для attempt 1)

```
$ adb shell settings put global http_proxy 10.0.2.2:8080
$ adb shell settings get global http_proxy
10.0.2.2:8080
$ Invoke-Pytest -k test_app_launches_and_loads_ao3 -v
tests/test_smoke.py::test_app_launches_and_loads_ao3 PASSED  [100%]
UserWarning: AT-BUG-064: остаточный device-прокси '10.0.2.2:8080'
  обнаружен на старте прогона (пережил рестарт эмулятора или аварийное
  завершение предыдущей сессии/worker'а) -- снят автоматически.
  [поправка Lead-батча 0812, F4: цитата была не дословна («на старте
  сессии»); фактическая строка кода — «на старте прогона», см.
  `conftest.py:59-63`; сам прогон этим ходом не переснимался, дословность
  сверена с исходником]
1 passed, 410 deselected, 1 warning in 22.80s
PYTEST_EXIT=0
$ adb shell settings get global http_proxy
:0
```

Тест PASSED против РЕАЛЬНОГО archiveofourown.org (не replay) — доказывает,
что прокси был реально снят ДО навигации, не только залогирован.

Прогоны юнит-набора после B2-фикса (3 подряд):
```
$ Invoke-Pytest tests/test_residual_proxy_guard_unit.py -q
............
12 passed in 0.10s / 0.08s / 0.08s
PYTEST_EXIT=0  (все три раза)
```

Регрессия device-free `_unit`-набора после B2:
```
$ Invoke-Pytest tests -k _unit -q
237 passed, 174 deselected, 2 warnings in 21.07s
PYTEST_EXIT=0
```

`python scripts/validate_frontmatter.py` — чист (см. ниже). `app-under-test/`
не тронут. Лок снят этим ходом.

## Верификация (заполняет fix-verifier)

Carve-out применён (`test_cases: []` штатно для `type: test_debt` в
обвязке — conftest.py/mitm.py, fix-verifier.md «Границы»): вместо
device-прогона кейсов — документная сверка первоисточника (код в
репозитории на текущем `HEAD`) + независимый device-free механический
перепрогон.

**Сверка кода (не пересказ бага).** Прочитаны целиком: `framework/core/
mitm.py::get_device_proxy()` (л. 543-586) и `::ensure_no_residual_proxy()`
(л. 589-616) — обе функции существуют и реализуют описанное (чтение
`adb shell settings get global http_proxy`, снятие через
`clear_device_proxy()` при непустом/не-`"null"`/не-`":0"` значении).
`framework/tests/conftest.py::_ensure_no_residual_device_proxy()` (л.
37-63) существует, вызывается из ДВУХ точек, подтверждено greр'ом и
чтением: (1) `_ensure_app_installed` (л. 78, session-scoped autouse) и
(2) `pytest_runtest_setup()` (л. 197, сразу после `_reset_ca_check()`,
внутри `if _pending_recovery_warning is not None:` — B2-фикс на
device-liveness recovery). Обе точки — ровно то, что называет
`fixed_in`. Замечен ПОЗДНЕЙШИЙ (не документированный в этом баге, но не
противоречащий) хардненинг `get_device_proxy()` — F2, коммит `a474f32`
«батч мелочей 0812»: обработка ненулевого `returncode` adb
(offline/unauthorized устройство) явным `None` вместо fail-open — это
аддитивное усиление того же фикса, не расхождение с `fixed_in`,
упомянуто здесь для полноты следа.

**Механический перепрогон (независимый, этот ход, дата 2026-08-14):**

```
$ powershell ...; Invoke-Pytest tests/test_residual_proxy_guard_unit.py -q
..............                                                           [100%]
=== warnings summary ===
tests/test_residual_proxy_guard_unit.py::test_hook_rechecks_residual_proxy_after_recovery
  conftest.py:196: UserWarning: AT-BUG-026 device-liveness guard: восстановление 1/2
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
14 passed, 1 warning in 0.14s
PYTEST_EXIT=0
```
(14, не 12 — файл вырос после F2/`a474f32`: 3 новых теста на
`get_device_proxy` returncode-ветку/параметризацию; регрессии нет,
исходные 11+1 сценариев по-прежнему зелёные.)

```
$ python -m pytest scripts/tests -q
1124 passed, 1 skipped in 40.44s
```
(1124, не 1120 — тот же класс роста набора между 2026-08-11 и
2026-08-14, не регрессия.)

```
$ python scripts/validate_frontmatter.py
validate_frontmatter: ошибок 0, предупреждений 0
```

`schemas/transitions.yaml` сверен: `{from: Fixed, to: Verified, by:
[fix-verifier]}` легален; для `type: test_debt` новая сборка приложения
не требуется (та же строка схемы, л. 92-93). `output-metadata.json`
(`app-under-test/app/build/outputs/apk/debug/`) сверен: `versionCode: 12`,
`versionName: "dev-local"` — совпадает с заявленным в `fixed_in`/
`found_in` (source_commit `cc201f789f...`, dev-local).

| Дата | Версия сборки | Прогнанные проверки | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-14 | dev-local (versionCode 12, `cc201f789f0fb123722bbba7b29b8e0c6412dac1`; test_debt — верификация build-независима, D1 не ждёт новую сборку приложения) | `test_cases: []` — carve-out (обвязка/conftest, ФАКТИЧЕСКИ исполнимых device-кейсов нет). Замена: (1) документная сверка первоисточника — `framework/core/mitm.py::get_device_proxy`/`ensure_no_residual_proxy` и ДВЕ точки вызова `_ensure_no_residual_device_proxy()` в `conftest.py` (`_ensure_app_installed`, `pytest_runtest_setup`) прочитаны целиком, реализация соответствует `fixed_in`; (2) независимый механический перепрогон `tests/test_residual_proxy_guard_unit.py` + `scripts/tests` + `validate_frontmatter.py` | `test_residual_proxy_guard_unit.py`: `14 passed, 1 warning in 0.14s`, PYTEST_EXIT=0. `scripts/tests`: `1124 passed, 1 skipped in 40.44s`. `validate_frontmatter.py`: `ошибок 0, предупреждений 0`. Код-сверка: обе функции (а) и обе точки вызова (б)/B2 присутствуют и подключены как описано в `fixed_in` — расхождений не найдено. | fix-verifier: **`Fixed → Verified`.** Обоснование замены device-прогона — явно выше (carve-out fix-verifier.md, test_debt/обвязка); первоисточник — код репозитория на текущем `HEAD`, не пересказ разработчика.
