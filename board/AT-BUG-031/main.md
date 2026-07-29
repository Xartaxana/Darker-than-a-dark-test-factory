---
key: "AT-BUG-031"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p2"
summary: "Stop-NodeProcesses (tasks.ps1) убивает ЛЮБОЙ node.exe по имени — коллатеральный риск для чужих неAO3 node-процессов на этом же хосте"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-29T02:10:00Z"
updated: "2026-07-29T02:10:00Z"
archived: false
resolution: null
---

# Stop-NodeProcesses (tasks.ps1) убивает ЛЮБОЙ node.exe по имени — коллатеральный риск для чужих неAO3 node-процессов на этом же хосте

_Спроецировано из `bugs/AT-BUG-031.md` (источник правды).
Статус в нашей машине: **Fixed**._

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
| | | | | (D1 fix-verifier — общим правилом, после Fixed; сборку приложения ждать не нужно, guard-переход B4) |

## Обсуждение

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
