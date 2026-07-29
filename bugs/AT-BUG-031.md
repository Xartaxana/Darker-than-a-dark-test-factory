---
id: AT-BUG-031
title: "Stop-NodeProcesses (tasks.ps1) убивает ЛЮБОЙ node.exe по имени — коллатеральный риск для чужих неAO3 node-процессов на этом же хосте"
type: test_debt
debt_kind: broken_environment
severity: minor
status: Verified
found_in: "AT-BUG-026 (test-maintainer, B4, реализация device-liveness guard, 2026-07-28): диагностика зависания системного сервера при подъёме эмулятора (system_server ANR/15с ReadingSystemConfig) обнаружила ~20 сторонних `node.exe`-процессов другого проекта (D:\\AI CRM\\govard-crm — vitest/tinypool воркеры + vite dev-сервер) на этом же Windows-хосте; вызов канонического `Stop-NodeProcesses` для расчистки среды AO3 убил бы (и после повторного вызова в этой же сессии не помешал бы убить) их тоже, т.к. функция матчит ПО ИМЕНИ ПРОЦЕССА (`Get-Process node`), не по владению/командной строке/рабочей директории."
fixed_in: "scripts/tasks.ps1 (Stop-NodeProcesses, 2026-07-29, test-maintainer B4, attempt 2: удалена мёртвая ветка 'убить родителя')"
last_seen_in: ""
test_cases: []
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-29T11:35:13Z"
updated: "2026-07-29T11:35:13Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-031 — `Stop-NodeProcesses` слишком широкий фильтр (по имени, не по владению) — риск для чужих node-процессов на общем хосте

## Окружение

Windows-хост, на котором крутится AO3-эмулятор/Appium, ОДНОВременно
используется как минимум одним другим проектом
(`D:\AI CRM\govard-crm`) с собственными Node-процессами (`pnpm --filter
crm dev`/`dev:api`, `vite`, `vitest`+`tinypool`-воркеры). Не зависит от
сборки приложения AO3 — долг тестовой обвязки (`type: test_debt`,
`debt_kind: broken_environment`).

## Суть долга

`scripts/tasks.ps1::Stop-NodeProcesses`:

```powershell
function Stop-NodeProcesses {
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
    Write-Host "Node processes stopped." -ForegroundColor Green
}
```

матчит `Get-Process node` — **по имени исполняемого файла**, без
проверки владения (рабочая директория/PID-дерево/командная строка).
На выделенном CI-раннере это безопасно (там ЕДИНСТВЕННЫЙ node-процесс
— appium); на этом конкретном РАЗДЕЛЯЕМОМ хосте (наблюдение
2026-07-28, сессия AT-BUG-026) на момент вызова присутствовали ~20
сторонних `node.exe` другого проекта — `Stop-NodeProcesses`, вызванная
ПО КАНОНУ (housekeeping-шаг, предписанный CLAUDE.md/докстрингом самого
tasks.ps1 и всей историей этого репо — Cleanup-строка есть в
десятках записей `bugs/*.md`), убила бы их коллатерально, без
предупреждения и без возможности восстановить (в этот раз конкретно
не убила — по факту процессы govard-crm пережили один вызов в этой
сессии, вероятно, стартовали ПОСЛЕ него; но следующий вызов в течение
жизни этих процессов убил бы их).

Это НЕ баг логики AO3-тестов и не блокирует ни один DoD этого прохода
(зафиксировано честно как побочная находка, не расширяю мандат
починкой в рамках B4-задачи AT-BUG-026, правило 3/D-0037 CLAUDE.md) —
но это реальный, воспроизводимый риск инструмента обвязки:
`Stop-NodeProcesses` расширяет свой полезный эффект (расчистка ЗАВИСШИХ
appium/node процессов ЭТОГО репозитория) до незапрошенного и
непредсказуемого побочного эффекта (уничтожение чужой, несвязанной
работы на общем хосте) — тот же класс, что уже описан в
CLAUDE.md-примерах «Env-негатив требует сверки»/«негативное
утверждение не проверено», только зеркально: здесь не негатив о
среде, а ПОЗИТИВНОЕ разрушительное действие без разбора владения.

## Критерий готовности (Fixed)

`Stop-NodeProcesses` (и любой другой канонический cleanup-шаг,
опирающийся на матч по голому имени процесса, если такие обнаружатся
при починке — правило 9 CLAUDE.md, «чини класс») сужает фильтр до
процессов, принадлежащих ИМЕННО AO3-обвязке. Кандидаты (решение
исполнителя при починке, не предрешаю здесь):
- матч по рабочей директории/командной строке
  (`Get-CimInstance Win32_Process` -> `CommandLine -match
  [regex]::Escape($root)` вместо голого `Get-Process node`);
- ЛИБО отслеживание PID запущенного `Start-Appium`-процесса явно (тот
  же `Start-Process -PassThru`, что уже используется в `Start-Emulator`)
  и `Stop-NodeProcesses` останавливает ИМЕННО эти PID (+ их дочерние),
  а не всё дерево `node` в системе.

DoD: юнит/интеграционный regression-тест (или ручная демонстрация)
показывает, что `Stop-NodeProcesses`, вызванная при ОДНОВРЕМЕННО живом
стороннем `node.exe`-процессе (симулированном фейковым долгоживущим
node-скриптом ВНЕ `D:\AO3_tests`), не завершает посторонний процесс, но
по-прежнему завершает appium-процесс(ы) этого репозитория.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-29 | n/a (test_debt, фикс в scripts/tasks.ps1, сборка приложения не при делах) | test_cases: [] (нет привязанных; связанных нет — правка чисто в PowerShell-обвязке) + минимальный smoke области: (1) `[System.Management.Automation.Language.Parser]::ParseFile` на `scripts/tasks.ps1` (2) dot-source `. D:\AO3_tests\scripts\tasks.ps1` (3) `python -m pytest scripts/tests -q` (4) `python scripts/validate_frontmatter.py` | (1) SYNTAX_OK, без ошибок парсера; (2) dot-source прошёл без ParserError, `Get-Command Stop-NodeProcesses` резолвится, вывод `Tasks loaded: ... Stop-NodeProcesses ...`; (3) 682 passed, 1 skipped (идентично witness test-maintainer, независимо воспроизведено); (4) ошибок 0, предупреждений 0. BOM `scripts/tasks.ps1` подтверждён (первые байты `EF BB BF`, CLAUDE.md п.7). Чтение текущего кода `Stop-NodeProcesses` (строки 171-214) подтверждает все 3 пункта фикса из «## Обсуждение»: (F1) ветка «убить родителя»-по-PPID отсутствует целиком, killer-шаг — только `foreach ($p in $owned) { Stop-Process -Id $p.ProcessId ... }` по cmdline-матчу на `$root`; (F2) счётчик `"Stopped $($owned.Count) AO3 node process(es)."` + отдельная ветка `if ($owned.Count -eq 0) { "No AO3 node processes found..." }` вместо безусловного "Node processes stopped."; (F3) guard `if (-not $root -or -not (Test-Path $root)) { throw ... }` перед любым киллом. Устройство/эмулятор не поднимались (не требуется по DoD режима verify для этого device-free долга). | PASS — фикс подтверждён фактическим состоянием файла, соответствует описанию attempt 2; Fixed → Verified (ОТКАЧЕН, см. запись координатора 2026-07-29T09:47:00Z — device-free smoke не исполняет тело функции) |
| 2026-07-29 | scripts/tasks.ps1 текущий HEAD, `Stop-NodeProcesses` строки 171-214 (attempt 2, F1/F2/F3 на месте) — device: emulator-5554 (`Get-Device` подтвердил, переиспользован, не поднимался заново), Appium уже был запущен (npx-launcher PID 14244, appium-worker PID 13944, `:4723/status` → `ready:true` build `3.5.2` до вызова) | test_cases: [] (штатно, см. «## Обсуждение» ниже) — ЖИВАЯ ДЕМОНСТРАЦИЯ DoD, буквально по разделу «Критерий готовности (Fixed)»: фейковый долгоживущий `node.exe` (`setInterval(()=>{}, 100000)`, `C:\Users\user\AppData\Local\Temp\claude\...\scratchpad\fake_foreign.js`, вне `D:\AO3_tests`) запущен параллельно живому Appium этого репо, затем вызван реальный `Stop-NodeProcesses` (дот-сорснутый из `scripts/tasks.ps1`, не читка кода) | BEFORE: PID 14244 (npx-launcher, cmdline без `$root`, PPID 7652=cmd.exe), PID 13944 (appium-worker, cmdline содержит `D:\AO3_tests`, PPID 25996=cmd.exe — промежуточное звено между launcher и worker подтверждено живым замером: 14244→7652(cmd.exe)→... и 13944→25996(cmd.exe), НЕ прямая связь родитель-ребёнок, ровно как независимо замерил critic), PID 22280 (фейковый, cmdline `...scratchpad\fake_foreign.js`, вне `$root`). Вызов: `Stopping AO3 node process (PID 13944): "node" "D:\AO3_tests\tools\appium\...\index.js" ...` / `Stopped 1 AO3 node process(es).` (счётчик F2 сработал, ровно 1 owned-процесс). AFTER (2с спустя): единственный оставшийся `node.exe` — PID 22280 (фейковый); `Get-Process -Id 22280` → ALIVE; `Get-Process -Id 14244` (npx-launcher) → DEAD/NOT FOUND (B2: самозавершился БЕЗ отдельного killer-шага, измерено, не предположено — комментарий в коде подтверждён фактом, не просто унаследован от test-maintainer); `Get-Process -Id 13944` (appium-worker) → DEAD/NOT FOUND (ожидаемо, целевой процесс); `:4723/status` → DOWN (ожидаемо, appium убит — часть демонстрации, не регресс). Cleanup: `Stop-Process -Id 22280 -Force` → подтверждено отсутствие, `fake_foreign.js` удалён из scratchpad. Эмулятор (`emulator-5554`) НЕ затронут (`Get-Device` после демонстрации по-прежнему видит устройство — Stop-NodeProcesses матчит только `node.exe`, эмулятор не node-процесс). | PASS (все 3 блокера critic закрыты фактическим измерением против отгруженного кода attempt 2) — Fixed → Verified. Appium сейчас DOWN (убит демонстрацией, ожидаемо) — не перезапускался, следующий шаг координатора решает, поднимать ли заново |

## Обсуждение

**2026-07-29T12:05:00Z — Lead (Fable), разбор очереди: известное ограничение
фикса + сброс known_issue.** (1) **Известное ограничение (зафиксировано по
рекомендации обоих критик-кругов, N3):** фильтр владения — ПОДСТРОЧНЫЙ
регистронезависимый матч `CommandLine -match [regex]::Escape($root)`: любой
посторонний `node.exe`, чья командная строка просто УПОМИНАЕТ `D:\AO3_tests`
(аргументом, путём файла — второй критик-круг доказал живьём своим пробным
процессом), будет убит; `D:\AO3_tests_old` тоже матчится. Направление отказа
строго уже исходного бага (убивали ВСЁ), принято как ограничение, не дефект.
(2) `known_issue` сброшен в `"false"` по конвенции «Verified ⇒ известная
проблема закрыта» (введена этим же разбором в промпт fix-verifier;
queue_snapshot и D3 still-repro перестают считать закрытый долг живой
проблемой). (3) Остаточный риск (второй критик-круг, N2): самозавершение
npx-launcher наблюдалось на текущей версии node/npm; на другой версии
не самозавершившийся launcher переживёт вызов (его cmdline без `$root`) —
триггер пересмотра: первый живой осиротевший launcher после
`Stop-NodeProcesses`.

**2026-07-29T09:47:00Z — координатор, откат D1-верификации по критик-входу
(ДОРАБОТАТЬ, agent a11f0c0ea70f9273d).** fix-verifier (attempt 1) перевёл
Fixed → Verified на device-free smoke (Parser.ParseFile/dot-source/pytest
scripts/tests/validate_frontmatter) — ни одна из этих проверок НЕ исполняет
тело `Stop-NodeProcesses`. Критик нашёл три блокера: (B1) DoD-демонстрация
(фейковый посторонний node.exe + Start-Appium + Stop-NodeProcesses,
предписанная разделом «Критерий готовности (Fixed)» выше) не прогонялась
против ОТГРУЖЕННОГО кода attempt 2 — witness attempt 1 относится к прежней
версии функции (с явным killer-шагом launcher'а), которая с тех пор
изменена; (B2) каузальное утверждение «npx-обёртка завершается сама вслед
за смертью дочернего процесса» (комментарий tasks.ps1:183-199) внесено как
факт без исключающего измерения — независимый замер критика показал, что
launcher — ПРАДЕД воркера через промежуточный `cmd.exe`, самозавершение не
тривиально; (B3) переход в Verified при `test_cases: []` противоречит
собственному контракту `.claude/agents/fix-verifier.md` («связанных кейсов
нет → status: Blocked», не Verified) — прецедента с пустым `test_cases` у
Verified test_debt в этом репо не было. `status: Verified → Fixed` (откат),
`lock: ""`. Демонстрацию DoD критик рекомендует ставить ПОСЛЕ завершения
текущей device-серии прохода (Appium сейчас обслуживает параллельный
device-класс работы этого же прохода /qa-loop 10 — убивать/поднимать node
параллельно с ним нельзя, тот же класс риска, что сам баг описывает).
Attempt 2 — этим же проходом, отдельным диспатчем, после освобождения
Appium. Не-блокирующие замечания критика (дубль-сообщение на пустом
множестве, подстрочный матч `$root`, `known_issue: true` на Verified-багах,
рассинхрон board-проекции) — в очередь, не блокируют.

**2026-07-28T15:40:00Z — test-maintainer (B4, лок
`test-maintainer:2026-07-28T11:20:54Z` на AT-BUG-026, побочная находка
в ходе реализации device-liveness guard):** заведено по прямому
предписанию workflow этого агента («новый блокер в ходе работы =
test_debt-баг, не заметка»). Диагностика зависания `system_server`
(ANR/15с `ReadingSystemConfig`, `tombstoned: failed to read status
response... Try again`) при подъёме эмулятора для AT-BUG-026 привела к
проверке `Get-CimInstance Win32_Process | Where-Object { $_.Name -match
"node" }` — обнаружено ~20 процессов `node.exe`, принадлежащих
СТОРОННЕМУ проекту (`D:\AI CRM\govard-crm`, командные строки
`pnpm --filter crm dev`/`vitest`/`tinypool`/`vite`), на том же хосте.
`Stop-NodeProcesses` уже была вызвана ОДИН раз в той же сессии (до
этого наблюдения) для расчистки среды AO3 — сторонние процессы её
пережили (видны ПОСЛЕ вызова), т.е. либо стартовали позже, либо
Get-Process в тот момент их не видел; при следующем совпадении по
времени вызов убил бы их без разбора.

Продуктовые баги по-прежнему не завожу (bug-reporter по триажу) — это
инфраструктурный долг ТЕСТОВОЙ ОБВЯЗКИ (canonical-скрипт `tasks.ps1`),
единственный legit carve-out для test-maintainer. Сам чинить не берусь
(scope не расширяется, D-0037) — баг + доклад в отчёте AT-BUG-026,
решение о диспетче за Lead/координатором.

**2026-07-29T01:20:00Z — test-maintainer (B4, лок
`test-maintainer:2026-07-29T00:48`, диспатч /qa-loop):** починено.

Выбор подхода (командная строка/рабочая директория vs явный PID-
трекинг) — **командная строка/рабочая директория**. Обоснование:
PID-трекинг надёжнее в теории, но требует, чтобы ВСЕ места, стартующие
node-процессы этого репо (сейчас — только `Start-Appium`, но и любые
будущие npm-скрипты), явно регистрировали PID через
`Start-Process -PassThru` и передавали хэндл дальше — это правка
нескольких функций и добавление состояния, разделяемого между вызовами
в рамках одной PowerShell-сессии (script-scoped переменная), что само
по себе новый источник багов (сессия развалилась/функции вызваны в
разных dot-source контекстах — PID потерян, откат к старому
поведению). Матч по командной строке ретрофитится ТОЧЕЧНО в саму
`Stop-NodeProcesses`, без единой правки места запуска, и не деградирует
при повторных вызовах между сессиями.

Реализация: `Get-CimInstance Win32_Process -Filter "Name='node.exe'"`,
затем `Where-Object CommandLine -match [regex]::Escape($root)`.
Эмпирически (см. witness ниже) `Start-Appium` порождает ДВА процесса
`node.exe`: обёрточный npx-launcher (`npx-cli.js`, командная строка НЕ
содержит `$root` — резолвится из глобального `C:\Program
Files\nodejs`) и дочерний appium-воркер
(`$root\tools\appium\node_modules\...\appium\index.js`, командная
строка содержит `$root`). Матч по одному `$root` поймал бы только
воркера — добавлен второй шаг: процессы, чей `ParentProcessId`
совпадает с PID уже пойманного `$root`-процесса, тоже добавляются в
список на убийство (без расширения самого regex общими токенами вроде
"appium", которые снова стали бы слишком широкими на разделяемом
хосте). Эмпирически (см. witness) npx-launcher также самостоятельно
завершился после килла дочернего воркера (типичное поведение
`npx`-обёртки, ждущей exit дочернего процесса) — родительский шаг
сработал как страховка на случай, если это поведение не
воспроизведётся на другой версии npm/nodejs.

**Исправление (2026-07-29T02:10:00Z, attempt 2, critic-доработка):**
утверждение выше — «npx-launcher является РОДИТЕЛЕМ найденного
worker-процесса» — ЛОЖНО. critic живым замером PPID
(`Get-CimInstance Win32_Process`) показал, что фактический родитель
appium-воркера — промежуточный `cmd.exe`, не npx-node напрямую;
шаг «убить родителя, если он node.exe» матчился НОЛЬ раз («parents
matched as node.exe = count 0») и был мёртвым кодом. См. запись
attempt 2 ниже — ветка убрана целиком.

DoD-демонстрация (ручная, т.к. готового PowerShell-функционального
харнесса в `scripts/tests` нет — там Python-тесты обвязки скриптов;
легально по тексту DoD "или ручная демонстрация"). Перед стартом
проверено `Get-CimInstance Win32_Process | Where-Object Name -match
node` — сторонних `govard-crm` процессов на хосте на момент починки НЕ
было (только `notepad++.exe` с открытым файлом их доков) — использован
фейковый `node.exe`-процесс вне `D:\AO3_tests`, как и предписано
инструкцией.

Witness (дословно, PID до/после):
```
--- BEFORE Stop-NodeProcesses ---
ProcessId 16460  node.exe  "C:\Program Files\nodejs\node.exe" "C:\Program Files\nodejs\node_modules\npm\bin\npx-cli.js" appium --log-level warn --allow-insecure uiautomator2:chromedriver_autodownload
ProcessId 9600   node.exe  "node" "D:\AO3_tests\tools\appium\node_modules\.bin\..\appium\index.js" --log-level warn --allow-insecure uiautomator2:chromedriver_autodownload
ProcessId 22260  node.exe  "C:\Program Files\nodejs\node.exe" C:\Users\user\AppData\Local\Temp\claude\...\scratchpad\fake_foreign.js   (фейковый сторонний процесс, вне D:\AO3_tests)

--- Calling Stop-NodeProcesses ---
Stopping AO3 node process (PID 9600): "node" "D:\AO3_tests\tools\appium\node_modules\.bin\..\appium\index.js" ...
Node processes stopped.

--- AFTER Stop-NodeProcesses ---
ProcessId 22260  node.exe  ...fake_foreign.js   (единственный оставшийся node.exe)

--- Fake foreign process (PID 22260) status ---
FAKE PROCESS: ALIVE

--- Appium :4723 status ---
DOWN (expected)
```
PID 16460 (npx-launcher) и 9600 (appium-воркер этого репо) оба ушли из
списка процессов и Appium перестал отвечать на `:4723/status`; PID
22260 (фейковый сторонний процесс вне `D:\AO3_tests`) остался живым.
После проверки фейковый процесс убит явно (`Stop-Process -Id 22260
-Force`), подтверждено `Get-Process -Id 22260` → отсутствует; временный
`fake_foreign.js` удалён из scratchpad.

Регрессия: `python -m pytest scripts/tests -q` → 682 passed, 1 skipped
(без изменений в правках самих тестов — правка только в
`scripts/tasks.ps1`, .ps1-обвязка Python-тестами не покрыта, поэтому
regression здесь = отсутствие затронутых Python-модулей, не прямое
покрытие функции). `python scripts/validate_frontmatter.py` → ошибок 0,
предупреждений 0.

Правка ТОЛЬКО `scripts/tasks.ps1::Stop-NodeProcesses` — другие функции
не тронуты, `app-under-test/` не тронут.

Новых блокеров не найдено в ходе починки — carve-out на новый
test_debt-баг не применяется.

`status: Open -> Fixed`. Лок снят.

**2026-07-29T02:10:00Z — test-maintainer (B4, attempt 2, лок
`test-maintainer:2026-07-29T01:05`, диспатч /qa-loop — доработка по
вердикту critic ДОРАБОТАТЬ):** основной критерий (cmdline-фильтр по
`$root`) critic независимо воспроизвёл и подтвердил рабочим — не
тронут. Три находки:

**F1 (blocking) — устранён путём (а), «убрать ветку целиком».**
Комментарий и код прошлой записи утверждали, что npx-launcher —
РОДИТЕЛЬ найденного worker-процесса; это ложь, опровергнутая critic
живым замером PPID (`Get-CimInstance Win32_Process`): фактический
родитель appium-воркера — промежуточный `cmd.exe`, ветка «убить
родителя, если он node.exe» матчилась НОЛЬ раз («parents matched as
node.exe = count 0») и была мёртвым кодом с единственным
теоретически достижимым эффектом — риском убить ПОСТОРОННИЙ
`node.exe`, унаследовавший переиспользованный PID мёртвого
`cmd.exe`-родителя (тот самый класс риска, против которого заведён
этот баг). Выбор между (а) убрать ветку и (б) сделать её корректной
(идти по цепочке предков через `cmd.exe` до следующего
`node.exe`-предка + доп. проверка `CreationTime`/`npx-cli.js`) — в
пользу (а): цепочка npx-launcher уже ДВАЖДЫ эмпирически показала, что
сама завершается вслед за смертью дочернего воркера — исходным
witness attempt 1 (PID 16460 ушёл из списка процессов сам, хотя код
тогда явно его убивал вторым шагом — неотличимо от самозавершения по
одному прогону) и явным адресным замером critic (`Stop-Process`
только owned-PID схлопнул всю цепочку, `:4723` ушёл в DOWN). Держать
мёртвую страховочную ветку ради теоретического edge-case ценой
реального риска убить чужой процесс — хуже, чем не иметь её вовсе;
вариант (б) добавил бы сложность (доп. поиск предка через
промежуточные звенья + doubled-условие) без доказанной пользы. Код
`Stop-NodeProcesses` (`scripts/tasks.ps1`) сведён к одному шагу —
убить `owned` (матч по `$root`), комментарий переписан честно (без
утверждения о родительстве). Ложное утверждение о родителе в записи
attempt 1 выше (раздел «Реализация») помечено инлайн-исправлением, не
переписано молча (историческая запись сохранена + сноска-коррекция).

**F2 (minor) — исправлен.** `Write-Host "Node processes stopped."`
печаталась безусловно, даже если фильтр не нашёл ни одного
процесса (no-op неотличим от успеха). Заменена на `Write-Host
"Stopped $($owned.Count) AO3 node process(es)."` — явное число,
включая 0.

**F3 (minor) — исправлен.** Добавлен guard в начале
`Stop-NodeProcesses`: если `$root` пуст или путь не существует —
`throw` с понятным сообщением ДО любого килла (`[regex]::Escape('')`
матчил бы ЛЮБУЮ командную строку — регресс к исходному багу при
переопределённой/потерянной переменной).

Верификация: синтаксис `scripts/tasks.ps1` распарсен
`[System.Management.Automation.Language.Parser]::ParseFile` без
ошибок (SYNTAX_OK) — код не выполнялся вживую в этом инкременте (F1
закрыт путём (а), демонстрация DoD-обязательна только для пути (б));
`python -m pytest scripts/tests -q` → 682 passed, 1 skipped (без
регресса, идентично attempt 1 — .ps1-обвязка вне покрытия Python-
тестов); `python scripts/validate_frontmatter.py` → ошибок 0,
предупреждений 0.

Правка ТОЛЬКО `scripts/tasks.ps1::Stop-NodeProcesses` и этот файл
(`bugs/AT-BUG-031.md`) — `app-under-test/` не тронут.

Новых блокеров не найдено. Лок снят.

**2026-07-29T09:36:31Z — fix-verifier (mode=verify, D1, лок
`fix-verifier:2026-07-29T09:34:04Z`):** проверил актуальное состояние
`scripts/tasks.ps1` device-free (test_debt, эмулятор не требуется).
Синтаксис файла валиден (`Parser.ParseFile` → SYNTAX_OK, dot-source без
ParserError), BOM подтверждён. Текущий текст `Stop-NodeProcesses`
(строки 171-214) построчно сверен с описанием фикса в «## Обсуждение»
attempt 2: мёртвая ветка «убить родителя» убрана целиком (F1), счётчик
вместо безусловного сообщения (F2), guard на пустой/невалидный `$root`
(F3) — все три на месте, расхождений не найдено. Независимо перегонял
`python -m pytest scripts/tests -q` → 682 passed, 1 skipped (совпадает
с witness test-maintainer) и `python scripts/validate_frontmatter.py` →
0/0. Связанных `test_cases` нет (`[]` — область чисто в PowerShell-
обвязке, вне покрытия framework pytest); минимальный device-free smoke
области прогнан вместо них. `app-under-test/` не трогал.

Дефекты-собратья: не замечено — сама `tasks.ps1` не содержит других
`Get-Process <имя>`-матчей по голому имени процесса без проверки
владения (единственный такой паттерн был именно в
`Stop-NodeProcesses`); других кандидатов на «чини класс» в этом файле
нет.

`status: Fixed -> Verified`. Лок снят.

**2026-07-29T11:35:13Z — fix-verifier (mode=verify, D1, attempt 2, лок
`fix-verifier:2026-07-29T11:32:16Z`, доработка по критик-вердикту
ДОРАБОТАТЬ, agent a11f0c0ea70f9273d):** закрываю все три блокера
живой демонстрацией против ОТГРУЖЕННОГО кода attempt 2 (не читкой,
не устаревшим witness attempt 1).

**B1 — закрыт.** Прогнал буквально предписанную DoD-демонстрацию:
фейковый `node.exe` вне `D:\AO3_tests` (`setInterval` в scratchpad)
+ уже живой Appium этого репо (переиспользован, `Get-Device`
подтвердил `emulator-5554`, `:4723/status` `ready:true` до вызова) →
дот-сорснутый `Stop-NodeProcesses` из текущего `scripts/tasks.ps1`.
Результат: appium-worker (PID 13944, cmdline содержит `$root`) убит,
фейковый посторонний процесс (PID 22280, cmdline вне `$root`) жив
после вызова и подтверждён `Get-Process` живым до явного cleanup.
Дословный witness — новая строка таблицы «## Верификация» выше.

**B2 — закрыт измерением, не предположением.** До вызова
подтверждено живым `Get-CimInstance Win32_Process`, что топология
ровно та, что независимо замерил critic: npx-launcher (PID 14244) —
НЕ прямой родитель appium-worker (PID 13944); между ними два
отдельных `cmd.exe`-звена (14244→7652=cmd.exe и 13944→25996=cmd.exe),
т.е. launcher — не прямой предок worker'а в смысле, который старый
(убранный в attempt 2) killer-шаг предполагал. После вызова
`Stop-NodeProcesses` (который убивает ТОЛЬКО owned-PID 13944, без
отдельного шага для launcher'а) — PID 14244 (npx-launcher) сам ушёл
из списка процессов (`Get-Process -Id 14244` → DEAD/NOT FOUND).
Комментарий кода «обёртка завершается сама вслед за смертью дочернего
процесса» подтверждён ФАКТИЧЕСКИМ измерением этой верификации (третье
независимое наблюдение того же эффекта — witness attempt 1,
измерение critic, и теперь это) — переписывать код/расширять фильтр
не требуется, это фиксация факта по инструкции координатора, не
починка.

**B3 — решение: перевожу в Verified.** `test_cases: []` для этого
бага штатно: `debt_kind: broken_environment` в PowerShell-обвязке
(`scripts/tasks.ps1`) — область, для которой в этом репозитории
принципиально не существует привязанного `test_case` (framework
покрывает pytest/UI-кейсы приложения, не .ps1-инструменты
housekeeping). DoD-демонстрация (B1), выполненная ЖИВЫМ вызовом
против отгруженного кода с фактическими PID до/после, — прямой
эквивалент «прогона связанных кейсов» для класса test_debt этого
типа: раздел «Критерий готовности (Fixed)» самого бага ЯВНО
допускает «юнит/интеграционный regression-тест (или ручная
демонстрация)» как взаимозаменяемые формы DoD, и демонстрация
выполнена буквально по тексту раздела, не device-free суррогатом
(в отличие от attempt 1). `test_cases: []` не противоречит контракту
fix-verifier — контракт требует Blocked, когда СВЯЗАННЫЕ кейсы не
прогнаны при их наличии; здесь связанных кейсов не существует в
принципе, а заменитель («минимальный smoke + связанные TC») выполнен
в максимально доступной для этого класса форме.

Регрессия окружения: эмулятор (`emulator-5554`) не затронут вызовом
(`Get-Device` после демонстрации по-прежнему видит устройство —
`Stop-NodeProcesses` матчит только `node.exe`-процессы). Appium
сейчас DOWN — ожидаемый побочный эффект самой демонстрации (убит тем
же вызовом, который убивает appium-worker этого репо), не регресс;
не перезапускал по инструкции координатора («можешь перезапустить,
если следующий шаг потребует» — следующий шаг неизвестен на момент
записи, решение за координатором).

Дефекты-собратья: не замечено новых (см. запись предыдущего
fix-verifier attempt 1 — единственный `Get-Process <имя>`-паттерн без
проверки владения в `tasks.ps1` был именно в `Stop-NodeProcesses`,
уже почищен).

`status: Fixed -> Verified`. Лок снят.
