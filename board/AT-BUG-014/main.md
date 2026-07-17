---
key: "AT-BUG-014"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "Clear-EmulatorStaleLocks (AT-BUG-012) не удаляет hardware-qemu.ini.lock, когда это НЕПУСТАЯ директория (содержит pid) — Remove-Item без -Recurse падает NullReferenceException несмотря на -ErrorAction SilentlyContinue, Start-Emulator не поднимается"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-17T23:20:00Z"
updated: "2026-07-17T23:20:00Z"
archived: false
resolution: null
---

# Clear-EmulatorStaleLocks (AT-BUG-012) не удаляет hardware-qemu.ini.lock, когда это НЕПУСТАЯ директория (содержит pid) — Remove-Item без -Recurse падает NullReferenceException несмотря на -ErrorAction SilentlyContinue, Start-Emulator не поднимается

_Спроецировано из `bugs/AT-BUG-014.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-014 — `Clear-EmulatorStaleLocks` не переживает непустой `hardware-qemu.ini.lock`

## Окружение
- Хост Windows 11, эмулятор `ao3_test_api34` (API 34, WHPX). Не зависит от
  сборки приложения: долг тестовой обвязки (`type: test_debt`,
  `debt_kind: broken_environment`).

## Суть долга

`Clear-EmulatorStaleLocks` (`scripts/tasks.ps1`, введена AT-BUG-012) чистит
`multiinstance.lock`/`hardware-qemu.ini.lock` вызовом:

```powershell
Remove-Item $p -Force -ErrorAction SilentlyContinue
```

Это предполагает, что оба артефакта — плоские файлы. На практике
`hardware-qemu.ini.lock` бывает НЕПУСТОЙ ДИРЕКТОРИЕЙ (внутри лежит файл
`pid`) — так остаётся после жёсткого килла зависшего `qemu-system-x86_64`.
`Remove-Item -Force` без `-Recurse` на непустой директории в этой версии
PowerShell не просто выдаёт стандартную non-terminating ошибку "directory
not empty", а падает `NullReferenceException`, которую `-ErrorAction
SilentlyContinue` НЕ гасит (тот же класс, что и terminating-исключения,
которые ловятся через `-ErrorAction` не всегда — здесь конкретно не
ловится). Поскольку `$ErrorActionPreference = "Stop"` действует на уровне
скрипта, необработанное исключение останавливает весь `Start-Emulator`:
эмулятор не поднимается вообще, пока директория не будет убрана вручную.

Обнаружено побочно при witness-прогоне AT-BUG-013 (2026-07-17): в
окружении обнаружились стейл-процессы `emulator.exe`/`qemu-system-x86_64`
от предыдущей сессии (не убиты по завершении, несмотря на AT-BUG-012
witness, где `Stop-Process -Force` вроде бы применялся) — после их
форс-килла `hardware-qemu.ini.lock` остался директорией с `pid` внутри, и
`Clear-EmulatorStaleLocks` о неё споткнулась:

```
Remove-Item : Ссылка на объект не указывает на реальный объект.
    + FullyQualifiedErrorId : System.NullReferenceException,
      Microsoft.PowerShell.Commands.RemoveItemCommand
```

Ручной обход: `Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue`
снимает директорию целиком без ошибки.

## Критерий готовности (Fixed)

- `Clear-EmulatorStaleLocks` удаляет `hardware-qemu.ini.lock` независимо
  от того, файл это или непустая директория (`-Recurse` либо явная ветка
  по `Test-Path -PathType Container`), без падения скрипта в любом случае.
- Регресс: искусственно создать непустую директорию `hardware-qemu.ini.lock`
  (файл `pid` внутри) → `Clear-EmulatorStaleLocks` отрабатывает без
  исключения, директория снята.
- `Start-Emulator` после форс-килла зависшего `qemu-system-x86_64`
  (сценарий, воспроизведённый здесь) поднимается штатно без ручной
  предварительной очистки.
- Корневая причина (см. Обсуждение 22:35): фолбэк `Start-Emulator` на
  таймауте снапшот-буда убивает ПРАВИЛЬНЫЙ процесс — не только
  launcher `emulator.exe` (`$proc.Id` из `Start-Process`), но и
  фактический дочерний `qemu-system-x86_64.exe`, который на этом хосте
  НЕ завершается вместе с родителем и остаётся жить (наблюдалось: 30+
  минут), легитимно удерживая `hardware-qemu.ini.lock` — из-за чего
  `Clear-EmulatorStaleLocks` спотыкается не о МЁРТВЫЙ артефакт, а о
  ЖИВОЙ. Без этого исправления пункт 1 критерия (directory-safe
  Remove-Item) не решает проблему полностью — лок пересоздаётся живым
  процессом на каждой следующей попытке.

## Анализ

Тот же класс, что AT-BUG-012 (стейл-артефакты после нештатного завершения
qemu), но другая грань: AT-BUG-012 закрыл детект крэша снапшот-буда и
базовую зачистку file-локов; этот баг — что сама зачистка не покрывает
directory-форму лока. Severity minor: обход известен (ручной
`-Recurse`), встречено пока один раз, но блокирует Start-Emulator
полностью, пока не убрано вручную — не расширяю scope AT-BUG-013 этим
фиксом (D-0037), баг + доклад, диспатч на усмотрение Lead.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-17T20:55:00Z — test-maintainer, заведение (побочная находка при
AT-BUG-013):** блокер новый, отличный от долга AT-BUG-013 (гонка
package-сервиса после boot) и от уже закрытого AT-BUG-012 (детект крэша
снапшот-буда) — это дыра в самой зачистке локов, добавленной AT-BUG-012.
Расчистил окружение вручную (`Remove-Item -Recurse -Force` на
`hardware-qemu.ini.lock`, форс-килл стейл-процессов), чтобы продолжить
witness-прогон AT-BUG-013; `scripts/tasks.ps1` этим фиксом не трогаю —
диспатч на усмотрение Lead.

**2026-07-17T22:35:00Z — test-maintainer, root-cause найден (повторные
воспроизведения при регресс-прогонах AT-BUG-013):** тот же симптом
воспроизвёлся ЕЩЁ 5 раз подряд за сессию (2 харнесс-прогона по 3 цикла +
1 простой канонический цикл), несмотря на ручную зачистку между
попытками. Раскопка: `Start-Emulator`'ов фолбэк на таймауте снапшот-буда
делает `Stop-Process -Id $proc.Id` — но `$proc` это `Start-Process`
launcher `emulator.exe`, а НЕ фактический `qemu-system-x86_64.exe`
(отдельный дочерний процесс с ДРУГИМ PID). После одного из фолбэков
живой `qemu-system-x86_64` (PID зафиксирован, `StartTime` 21:51:25)
провисел 30+ минут, ничем не убитый, легитимно держа
`hardware-qemu.ini.lock` — из-за чего КАЖДАЯ следующая попытка
`Start-Emulator` натыкалась на тот же `NullReferenceException` уже не
как на редкий стейл-артефакт, а как на систематическое следствие
непонятого механизма. Убил процесс вручную (`Stop-Process -Id <pid>
-Force`) — `Get-Device`/`Get-Process` подтвердили чистое состояние.
Критерий готовности дополнен пунктом про корневую причину; фикс
по-прежнему на усмотрение Lead — не расширяю scope AT-BUG-013 (D-0037),
второй факт того же класса чиню на карте (правило 9 CLAUDE.md) той же
записью, не новым баг-файлом (Grep bugs/ по этому же id уже покрывает
класс «нештатное завершение qemu оставляет живые/полу-мёртвые
артефакты»).

**2026-07-17T23:20:00Z — test-maintainer, Open → Fixed (диспатч B4,
прямой регресс AT-BUG-012):**

`scripts/tasks.ps1`, BOM (`EF BB BF`) сверен ДО и ПОСЛЕ правки —
не пострадал.

- `Clear-EmulatorStaleLocks` (критерий 1): ветвление по
  `Test-Path $p -PathType Container` — директория снимается
  `Remove-Item -Recurse -Force`, плоский файл — как раньше
  (`Remove-Item -Force`). Без этой ветки непустая директория валила
  `NullReferenceException` сквозь `-ErrorAction SilentlyContinue`.
- `Start-Emulator`-фолбэк (критерий 4, корень): перед `Stop-Process
  -Id $proc.Id` (лаунчер) — `Get-CimInstance Win32_Process -Filter
  "ParentProcessId=$($proc.Id)"` ищет прямого qemu-ребёнка и убивает
  его первым; следом безусловный sweep всех `qemu-system*`-процессов
  этого хоста с `CommandLine -match 'ao3_test_api34'` — страховка на
  случай, если родственная связь лаунчер→qemu уже разорвана (что и
  наблюдалось в живом witness ниже: killed напрямую по PID, но связь
  parent/child к этому моменту уже была потеряна — sweep всё равно
  поймал бы его, если бы прямой kill не сработал).

Witness (все 4 пункта критерия закрыты живьём, эта сессия):
1. Regression-witness директории: искусственно создана
   `hardware-qemu.ini.lock/pid` (директория с файлом внутри) →
   `Clear-EmulatorStaleLocks` → `Removed stale lock: ...` без
   исключения, директория снята (`REMOVED_OK`).
2. Healthy-path witness: `Start-Emulator` (без параметров) —
   `Waiting for device boot (snapshot, up to 45s)... Emulator
   booted.` — здоровый путь не сломан правкой.
3. Force-kill witness (сценарий бага буквально): найден реальный
   процесс-tree (`emulator.exe` PID 19072 → `qemu-system-x86_64.exe`
   PID 6748), `Stop-Process -Id 6748 -Force` на ЧИСТО дочернем qemu
   (без затрагивания launcher-кода) → `hardware-qemu.ini.lock` стал
   стейл-директорией (симптом бага воспроизведён естественно) →
   `Start-Emulator` БЕЗ ручной очистки: `Removed stale lock:
   ...multiinstance.lock`, `Removed stale lock:
   ...hardware-qemu.ini.lock`, `Emulator booted.` — критерий 3 закрыт
   вживую.
4. Fallback-branch witness (сам исправленный код, не только
   последствие): эмулятор погашен начисто, затем `Start-Emulator
   -SnapshotBootTimeoutSec 3` (форсирует таймаут почти сразу) → лог
   фолбэка: `Killing qemu-system child process (PID 14580)...`,
   затем `Removed stale lock: ...multiinstance.lock` / `...
   hardware-qemu.ini.lock`, `Emulator booted.` — прямое доказательство,
   что фолбэк находит и убивает ИМЕННО qemu-ребёнка (не только
   лаунчер), после чего локи снимаются чисто и подъём завершается
   штатно `-no-snapshot-load`.
- `python scripts/arch_check.py` → «ошибок 0, предупреждений 0».
- Среда погашена: `adb -s emulator-5554 emu kill` → повторная
  проверка процессов → `NO_ZOMBIES_CONFIRMED` (два транзитных
  `emulator.exe`, замеченные сразу после kill, сами вышли к
  следующей проверке — лаунчер ждёт свой qemu-child и завершается
  вслед за ним, отдельно добивать не потребовалось); `Get-Device` →
  `NO DEVICE`; финальная `Clear-EmulatorStaleLocks` сняла оставшийся
  плоский `multiinstance.lock` от штатного `emu kill`-завершения.

Пересмотра стратегии/рисков не требует (инфраструктурный
bootstrap-фикс). Готово к `fix-verifier` (B4 → D1, долг тестовой
обвязки — сборку приложения ждать не нужно, guard test-maintainer).
