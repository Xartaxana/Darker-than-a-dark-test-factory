---
id: AT-BUG-032
title: "restart_app_via_adb / adb.force_stop не наблюдают реальную смерть процесса — TC-025 и test_reading_ux.py (персистентность через рестарт) не отличают холодный старт от no-op"
type: test_debt
debt_kind: missing_evidence
severity: minor
status: Verified
found_in: "critic-вход приёмки TC-134 (attempt 1, 2026-07-31): при ревью нового restart_app_via_adb-теста критик установил, что adb.force_stop() (framework/core/adb.py:45-46) вызывает shell(), которая отбрасывает returncode (adb.py:37-42) — ни force_stop, ни restart_app_via_adb (app_steps.py:401-411), ни какой-либо вызывающий тест нигде не читают adb.pidof_app() до/после, чтобы доказать, что процесс реально умер и пересоздался. При тихом отказе force-stop (устройство занято/permission/отвал adb) am start -W доставляет component-intent ЖИВОМУ процессу — эффект неотличим от холодного старта для тестов, которые проверяют только персистентное СОСТОЯНИЕ (вкладки/URL/тумблеры), а не факт пересоздания процесса."
fixed_in: "framework/tests/test_tabs.py (TC-025) и framework/tests/test_reading_ux.py (TC-125) переведены с app_steps.restart_app_via_adb на уже существующую app_steps.restart_app_via_adb_asserting_new_process (единая точка pid-проверки в app_steps.py, введена TC-134). test_compatibility.py:129 (единственный оставшийся вызывающий restart_app_via_adb) НЕ переведён — вне заявленного скоупа этого бага (только TC-025/TC-125); там НЕТ структурной гарантии смерти процесса (seed_db.ensure_db_initialized между clean_state() и рестартом сам делает am start -W + ещё один неконтролируемый force_stop) — см. очередь F3/F4 ниже, честно отражено в докстринге app_steps.py. perf_steps.measure_cold_start (TC-096) вообще не вызывает restart_app_via_adb — независимый путь, не относится к этому багу. 2026-07-31, test-maintainer B4 (attempt 2, критик-фикс: убраны ложные критерии безопасности из докстринга/этого поля, убрано жёсткое TC-134 из assert-сообщения)."
last_seen_in: "1.10"
test_cases: ["TC-025"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-31T18:20:00Z"
updated: "2026-07-31T18:20:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-032 — restart_app_via_adb не доказывает, что процесс реально был убит

## Окружение
Долг тестовой системы (`type: test_debt`, `debt_kind: missing_evidence`). Не зависит от сборки приложения — фикс целиком во `framework/`.

## Суть долга

`framework/steps/app_steps.py:401-411` (`restart_app_via_adb`):
```python
adb.force_stop()
adb.shell(f"am start -W -n {settings.APP_PACKAGE}/{settings.APP_ACTIVITY}", timeout=settings.ADB_LAUNCH_TIMEOUT)
```
`adb.force_stop()` = `shell(f"am force-stop {_PKG}")` (`framework/core/adb.py:45-46`); `shell()` возвращает только `.stdout`, returncode/stderr отброшены (`adb.py:37-42`). Ни здесь, ни в вызывающих тестах никто не читает `adb.pidof_app()` (`adb.py:189-193`, уже существует) до/после рестарта.

**Конкретный сценарий поломки:** force-stop тихо не срабатывает (device busy/permission/отвал adb) → приложение остаётся живым и на переднем плане → `am start -W` без `-d` на живой `singleTask`-Activity доставляет component-intent РАБОТАЮЩЕМУ инстансу (эмпирически подтверждено этим же репозиторием, `adb.py:296-303`: `TotalTime: 0` + `Warning: Activity not started, intent has been delivered to currently running top-most instance.`) → `MainActivity.onNewIntent` сбрасывает `deepLinkHandled`, но `dataString` пуст → поведение приложения не отличается от «ничего не произошло». Тесты, проверяющие только СОСТОЯНИЕ (вкладки/URL из prefs, значение тумблера), это состояние и так не меняется — они проходят зелёным, не проверив заявленный сценарий «холодный старт».

## Затронутые вызывающие (по критик-трассировке TC-134, 2026-07-31)

1. **`framework/tests/test_tabs.py:253` (TC-025, персистентность вкладок через рестарт)** — дыра того же класса: при no-op вкладки остаются в живой памяти, тест зелёный без проверки персистентности через реальную смерть процесса.
2. **`framework/tests/test_reading_ux.py:455`** — дыра того же класса: комментарий теста утверждает «значение тумблера пережило смерть процесса», но живой процесс отдаст то же значение из памяти без всякой персистентности.
3. **НЕ затронуты** (первоначальная оценка attempt 1 — **ИСПРАВЛЕНО attempt 2, critic-вход**, см. discussion ниже и докстринг `restart_app_via_adb_asserting_new_process`): `framework/tests/test_compatibility.py:129` — заявление «`pm clear` сам убивает процесс, холодный старт гарантирован структурно» было ЛОЖНЫМ: между `clean_state()` (:123) и рестартом (:129) идёт `seed_with_comment()` (:124) → `seed_db.ensure_db_initialized` (:50-65), который сам делает `am start -W` и ЕЩЁ ОДИН неконтролируемый `force_stop()` — структурной гарантии смерти процесса на момент вызова НЕТ (см. F3 в «Анализ»); `framework/steps/perf_steps.py:33` (`measure_cold_start`, TC-096) вообще НЕ вызывает `restart_app_via_adb` (независимый путь с собственной, реальной защитой через `clear_app_data()` с проверкой returncode) — упоминание его в этом списке было категориальной ошибкой.

## Критерий готовности (Fixed)

- `restart_app_via_adb` (или обёртка над ним) доказывает смену pid: `adb.pidof_app()` до (assert not None — «убивать нечего») и после (assert not None и != pid до — «force-stop не сработал»). Проверка — шагом в `app_steps.py` (тесты не импортируют `framework.core`, `scripts/arch_check.py`), не разбросана по вызывающим тестам поодиночке — иначе класс повторится в следующем новом тесте.
- `test_tabs.py::test_tabs_persist_url_and_scroll_after_restart` (TC-025) и `test_reading_ux.py` (соответствующий тест на строке ~455) переведены на укреплённую версию, перепрогнаны зелёными.
- Исключающий прогон приложен: временная подмена `force_stop` на no-op показывает содержательное падение новой pid-проверки, затем откатывается.
- Smoke без регресса.

## Анализ

Тот же класс дефекта, что B2/B3 у TC-131/TC-133 (вакуумно-зелёный негатив / стимул без позитивного контроля), но в уже существующем с TC-025 примитиве, не в новом коде — обнаружен только сейчас при третьем ревью подряд той же поверхности (двух свежих кейсов, TC-133/TC-134). Приоритет minor: реальные отказы force-stop на стабильном локальном эмуляторе редки, но при возникновении дают ложно-зелёный прогон дважды (TC-025 и test_reading_ux), а не честный красный.

**Известные аналоги той же поверхности — в очередь (не в скоупе DoD этого бага; названы, не исполняются здесь — решение о диспетчеризации за Lead, D-0037/правило 9 CLAUDE.md):**

- **F3** — корень класса (`adb.force_stop()`, отбрасывающий returncode через `shell()`) живёт ещё в 6 местах `framework/data/seed_db.py` (строки ~64, 65, 135, 158, 272, 332) — влияет на свежесть/детерминированность данных КАЖДОГО сидящего теста (тот же класс, что и здесь: тихий отказ force-stop неотличим от успеха). В частности именно эта неопределённость — причина, по которой `test_compatibility.py:129` (единственный оставшийся сырой вызывающий `restart_app_via_adb`) не получает структурной гарантии смерти процесса от `seed_with_comment()`/`ensure_db_initialized`.
- **F4** — соседний механизм той же поверхности («перезапуск с претензией на пересоздание процесса», но без наблюдения факта смерти): `app_steps.restart_app` (использует Appium `driver.terminate_app`/`activate_app`, вызывается `test_side_panel.py:95`, TC-051, с претензией «force-stop + relaunch») — возвраты `terminate_app`/`activate_app` не проверяются, смерть процесса не наблюдается через `pidof_app()`. Не входит в карту «вызывающих `restart_app_via_adb`» этого бага (другая функция, другой примитив — Appium API, не `core/adb`), но тот же класс дефекта на той же по смыслу поверхности.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-31 | 1.10 (test_debt, фикс целиком во `framework/`, приложение не менялось) | TC-025 (`test_tabs.py::test_tabs_persist_url_and_scroll_after_restart`) + TC-125 (`test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch`, единственный из `test_cases` бага — TC-025; TC-125 прогнан дополнительно как второй затронутый фиксом кейс) | Код: обёртка `restart_app_via_adb_asserting_new_process` (`app_steps.py:465-520`) ассертит `pid_before is not None` (:512), `pid_after is not None` (:515) и `pid_after != pid_before` (:516); оба теста реально вызывают именно её (`test_tabs.py:254`, `test_reading_ux.py:457`), не голый `restart_app_via_adb`. Независимый зелёный прогон: `Invoke-Pytest tests/test_tabs.py::test_tabs_persist_url_and_scroll_after_restart tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch` — `2 passed in 126.70s`, PYTEST_EXIT=0. Исключающая проба: `adb.force_stop()` временно превращён в no-op (`return` перед `shell(...)`), TC-025 прогнан заново — упал содержательно ИМЕННО на pid-проверке: `AssertionError: pid не изменился (2859) — am force-stop процесс НЕ убил (adb.shell отбрасывает returncode), релонч свёлся к доставке intent'а в живой процесс: холодный старт не состоялся` (`app_steps.py:516`); порча немедленно откачена, `git diff -- framework/core/adb.py` пуст после отката (подтверждено). `arch_check.py` и `validate_frontmatter.py` — 0 ошибок/0 предупреждений оба, прогнаны после отката порчи. `app-under-test/` не тронут. | Verified — все три пункта критерия готовности подтверждены живым прогоном (не пересказом): pid-ассерты в коде, зелёный независимый прогон обоих переведённых тестов, содержательное падение на исключающей пробе с откатом. Smoke p0 (49 passed) уже приложен test-maintainer'ом в «Обсуждении» attempt 1/2 на build 1.10 — не перегонялся повторно (точечная верификация двух конкретных TC, не полный regression-suite; run-артефакт не требуется — named-not-covered по правилам fix-verifier). |

## Обсуждение

**2026-07-31T01:05:00Z — Lead (Sonnet, координатор /qa-loop), заведение бага:**
Классовый долг вскрыт критиком при ревью TC-134 (attempt 1, rejected по B1 — новый тест на том же примитиве не отличает kill+relaunch от no-op). Фикс TC-134 самого нового теста — отдельным точечным диспатчем (не расширяет этот баг, использует локальную обёртку `restart_app_via_adb_asserting_new_process`, предложенную критиком). Этот баг — про УЖЕ существующие TC-025/test_reading_ux, вне скоупа диспатча TC-134 (правило D-0037 — не расширять scope исполнителя). Диспетчеризация по правилу B4 (`state/rules.yaml` «Устранить test debt») — следующим проходом /qa-loop.

**2026-07-31T10:55:57Z — test-maintainer (Sonnet), фикс:** обёртка
`app_steps.restart_app_via_adb_asserting_new_process` (единая точка pid-проверки
в `app_steps.py`, уже существовала со времён TC-134, ничего нового не
вводилось) переиспользована для двух старых вызывающих: `test_tabs.py::
test_tabs_persist_url_and_scroll_after_restart` (TC-025, строка 253/254) и
`test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch` (TC-125,
строка 455/456, ранее ошибочно упомянута в критик-трассировке бага как
«строка ~455», TC-номер там не указан — уточнён здесь). Докстринг обёртки
дополнен перечислением НЕзатронутых вызывающих (`test_compatibility.py:129`,
`perf_steps.measure_cold_start`) со ссылкой на этот баг — единая точка,
класс не повторится в следующем новом тесте на том же примитиве.

Оба теста прогнаны зелёными 3 раза подряд каждый (`Invoke-Pytest
tests/test_tabs.py::test_tabs_persist_url_and_scroll_after_restart
tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch`,
PYTEST_EXIT=0 все три раза).

Исключающая (красная) проба: `adb.force_stop()` временно превращён в no-op
(`return` перед `shell(...)`), TC-025 прогнан заново — упал ИМЕННО на новой
pid-проверке:
```
AssertionError: pid не изменился (8090) — am force-stop процесс НЕ убил
(adb.shell отбрасывает returncode), релонч свёлся к доставке intent'а в
ЖИВОЙ процесс: холодный старт TC-134 не состоялся
steps\app_steps.py:498: AssertionError
```
Порча немедленно откачена (`git diff -- framework/core/adb.py` пуст после
отката — подтверждено).

Smoke без регресса: `Invoke-Smoke` (канонический прогон p0, foreground с
блокирующим ожиданием по PID до завершения) — `49 passed, 199 deselected in
1537.96s`, 0 упавших. `arch_check.py` и `validate_frontmatter.py` — 0/0
ошибок и предупреждений (прогнано до начала фикса и снова не требовалось —
изменения не касаются структуры импортов/frontmatter агентов).

`app-under-test/` не тронут — весь фикс в `framework/tests/test_tabs.py`,
`framework/tests/test_reading_ux.py`, `framework/steps/app_steps.py`
(докстринг).

**2026-07-31 — critic-вход приёмки attempt 1: ДОРАБОТАТЬ, 2 блокера.**
Функциональное ядро (перевод TC-025/TC-125 на
`restart_app_via_adb_asserting_new_process`) принято как корректное и
перепрогнано зелёным независимо (2 passed 106.37s) — не тронуто. Блокеры:
**F1** — докстринг обёртки и `fixed_in` содержали ЛОЖНЫЕ критерии
безопасности для двух «не затронутых» вызывающих голого `restart_app_via_adb`:
(а) `test_compatibility.py:129` заявлял «`pm clear` сам убивает процесс —
холодный старт гарантирован структурно», хотя между `clean_state()` и этим
вызовом `seed_with_comment()` → `seed_db.ensure_db_initialized` сам делает
`am start -W` и ещё один неконтролируемый `force_stop()` — гарантии нет; (б)
`perf_steps.measure_cold_start` (TC-096) вообще не вызывает
`restart_app_via_adb` — независимый путь, упоминание в списке вызывающих было
категориальной ошибкой. **F2** — assert-сообщение в общей обёртке жёстко
называло «TC-134», хотя обёртка используется TC-025/TC-125/TC-134 — вводит в
заблуждение при диагностике отказа на любом из трёх.

**2026-07-31 — test-maintainer (Sonnet), фикс attempt 2 (текстовые правки,
функциональное ядро НЕ тронуто):**
- F1: докстринг `restart_app_via_adb_asserting_new_process` в `app_steps.py` и
  поле `fixed_in` этого файла переписаны честно — `test_compatibility.py:129`
  описан как использующий `restart_app_via_adb` фактически как простой старт
  без структурной гарантии смерти процесса (с точной трассировкой через
  `seed_db.py:50-65`), `perf_steps.measure_cold_start` убран из списка
  вызывающих `restart_app_via_adb` вовсе (он им не является) и описан как
  независимый путь со своей реальной защитой (`clear_app_data()` с проверкой
  returncode, `adb.py:75-81`).
- F2: из assert-сообщения в `app_steps.py` убрано жёсткое упоминание
  "TC-134" — текст сделан нейтральным, общим для всех вызывающих обёртку.
- F3/F4: явно перечислены в очередь в разделе «Анализ» (корень класса в
  `seed_db.py` — 6 мест; соседний механизм той же поверхности —
  `app_steps.restart_app`/`test_side_panel.py:95`, TC-051) — не исполнялись,
  scope не расширялся (правило D-0037).
- Witness: `tests/test_tabs.py::test_tabs_persist_url_and_scroll_after_restart
  tests/test_reading_ux.py::test_tap_to_scroll_survives_kill_and_relaunch`
  прогнаны дважды подряд после текстового фикса (текст/докстринг, не логика) —
  `2 passed in 106.91s` и `2 passed in 109.23s`, `PYTEST_EXIT=0` оба раза.
  `arch_check.py` и `validate_frontmatter.py` прогнаны ПОСЛЕ всех правок (не
  до) — `0 ошибок, 0 предупреждений` оба.
- `app-under-test/`, `seed_db.py`, `perf_steps.py`, `test_side_panel.py` не
  тронуты — фикс attempt 2 целиком текстовый, в `app_steps.py` (докстринг +
  сообщение assert'а) и `bugs/AT-BUG-032.md`.

Статус переведён Open → Fixed (B4, guard `type: test_debt`), lock снят.

**2026-07-31T18:20:00Z — fix-verifier (Sonnet), верификация D1:** это `type:
test_debt`, но с реально существующими и привязанными кейсами (`test_cases:
["TC-025"]`) — carve-out «DoD-демонстрация вместо TC» не применяется, гоняю
факт-прогон обоих затронутых тестов напрямую (устройство подтверждено
`Get-Device` → `emulator-5554`).

Прошёл все 4 пункта DoD бага независимо:
1. Код: `restart_app_via_adb_asserting_new_process` (`app_steps.py:511-520`)
   реально ассертит pid до/после — прочитано глазами, не с чужих слов; оба
   теста (`test_tabs.py:254`, `test_reading_ux.py:457`) реально зовут именно
   её, `test_compatibility.py:129` (вне скоупа) остался на голом
   `restart_app_via_adb` — соответствует заявленному в `fixed_in`.
2. Независимый зелёный прогон обоих тестов одной командой — `2 passed in
   126.70s`, PYTEST_EXIT=0.
3. Исключающая проба: `force_stop()` временно no-op → TC-025 упал именно на
   `assert pid_after != pid_before` (не вакуумно, не таймаутом на другом
   шаге) → откат, `git diff -- framework/core/adb.py` пуст (`git status
   --porcelain` подтверждает: файл не в списке изменённых).
4. `arch_check.py`/`validate_frontmatter.py` — 0/0 после моих правок (правки
   были только в `bugs/AT-BUG-032.md`, `framework/core/adb.py` не
   изменился по сумме).

Smoke (p0) не перегонял повторно — уже приложен зелёным (49 passed) в
«Обсуждении» на этой же сборке 1.10 тем же ходом фикса; точечная
D1-верификация двух TC регресс-суйта не требует. `app-under-test/` не
трогал. Статус Fixed → Verified, `known_issue` уже был `"false"` (не
трогаю), lock снят.

**Дефекты-собратья (D-0043):** F3 (`seed_db.py`, 6 мест того же
returncode-отбрасывающего `force_stop`) и F4 (`app_steps.restart_app` через
Appium API, `test_side_panel.py:95`, TC-051) уже названы в очереди самим
багом (раздел «Анализ») — не дублирую, подтверждаю, что они остаются вне
скоупа этой верификации и по-прежнему не исполнены.
