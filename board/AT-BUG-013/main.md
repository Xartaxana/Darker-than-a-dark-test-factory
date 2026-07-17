---
key: "AT-BUG-013"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "Install-App сразу после Start-Emulator (boot_completed=1) может словить race «cmd: Can't find service: package» — package manager ещё не готов, retry секундами позже проходит"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T00:20:00Z"
updated: "2026-07-18T00:20:00Z"
archived: false
resolution: "done"
---

# Install-App сразу после Start-Emulator (boot_completed=1) может словить race «cmd: Can't find service: package» — package manager ещё не готов, retry секундами позже проходит

_Спроецировано из `bugs/AT-BUG-013.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-013 — `Install-App` сразу после boot_completed=1 гонится с package-сервисом

## Окружение
- Хост Windows 11, эмулятор `ao3_test_api34` (API 34, WHPX). Не зависит от
  сборки приложения: долг тестовой обвязки (`type: test_debt`,
  `debt_kind: broken_environment`).

## Суть долга

`Start-Emulator` (scripts/tasks.ps1) считает эмулятор готовым по
`sys.boot_completed == 1`. Это НЕ гарантирует готовность всех системных
сервисов гостя — `package` (Package Manager) иногда поднимается позже.
Вызов `Install-App` сразу вслед за `Start-Emulator` может упасть:

```
adb.exe: failed to install ...\app-debug.apk: cmd: Can't find service: package
```

Обнаружено побочно при witness-прогоне AT-BUG-012 (2026-07-17): после
`Start-Emulator -WritableSystem` (boot прошёл штатно, без крэша снапшота)
`Install-App` упал этой ошибкой; `Get-Device` в этот момент уже показывал
устройство. Появившаяся из-за этого недоступность приложения каскадом
уронила Appium-сессию теста (`Appium Settings app is not running after
30000ms` — тот же корень: пока package-сервис не встал, ни один apk,
включая io.appium.settings, поставить/поднять нельзя). Ручной повторный
вызов `Install-App` минуты спустя (после `pm list packages` уже отдавал
непустой список) — `Success` немедленно. Это подтверждает гонку (race), а
не постоянную поломку.

## Критерий готовности (Fixed)

- Диагностирован фактический сигнал готовности package-сервиса (например,
  устойчивый непустой ответ `adb shell pm list packages`/`pm path
  android`, а не только `sys.boot_completed`).
- `Install-App` (или `Start-Emulator`) получает короткий ретраинг/ожидание
  этого сигнала перед первой попыткой install, с таймаутом и явным
  сообщением при неудаче (не молчаливый бесконечный retry).
- Регресс: `Start-Emulator` → сразу `Install-App` (без ручной паузы) —
  3 подряд успешных install без ручного вмешательства.

## Анализ

Класс — тот же дух, что AT-BUG-011 (environment-предусловие проверяется
таймаутом/крэшем вместо явной проверки готовности), но другой сервис
(package manager, не CA) и другой симптом (install-отказ, не
ReadTimeoutError). Severity minor: обход дёшев (ручной повтор Install-App
секундами позже), встречено пока один раз.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-18 | scripts/tasks.ps1 HEAD (`fixed_in`) | Нет TC (env-фикс); регресс `Start-Emulator -WritableSystem` → сразу `Install-App` (без паузы), НЕЗАВИСИМАЯ verifier-сессия | `Start-Emulator` (снапшот-таймаут → живой автофолбэк, см. AT-BUG-012) → `Get-Device: emulator-5554` → `Install-App` немедленно → `Performing Streamed Install` / `Success`, без race «Can't find service: package» | Verified |

## Обсуждение

**2026-07-17T20:35:00Z — test-maintainer, заведение (побочная находка при
AT-BUG-012):** блокер новый, отличный от долга AT-BUG-012 (тот про
crash quickboot-снапшота; этот — про готовность package-сервиса после
УЖЕ успешного boot). Не расширяю scope AT-BUG-012 починкой — по правилу
(D-0037) баг + доклад, диспатч на усмотрение Lead. Witness полностью в
`bugs/AT-BUG-012.md` (раздел «Обсуждение», запись test-maintainer).

**2026-07-17T22:40:00Z — test-maintainer, реализация + частичный
witness, статус ОСТАЁТСЯ Open (критерий 3 не закрыт полностью):**

Критерий 1 (диагностика сигнала) и критерий 2 (ожидание перед install)
реализованы в `scripts/tasks.ps1`:
- Новая `Wait-PackageServiceReady` — поллинг `adb shell pm path android`
  (устойчивый непустой ответ с `package:` — фактический сигнал
  готовности package-сервиса, не только `sys.boot_completed`) с
  таймаутом (по умолчанию 30с) и явным `Write-Warning` при неудаче
  (не молчаливый бесконечный retry).
- `Install-App` вызывает `Wait-PackageServiceReady` первой строкой перед
  `adb install`, таймаут параметризован (`-PackageServiceTimeoutSec`).
- BOM файла (UTF-8 with BOM) проверен ДО и ПОСЛЕ правки — `EF BB BF` в
  обоих случаях.
- `python scripts/arch_check.py` → «ошибок 0, предупреждений 0».

Регресс (критерий 3, «3 подряд успешных install без ручного
вмешательства») НЕ закрыт полностью — собран только 1 чистый цикл, не
3. Хронология сессии:
- Первая попытка (сложный harness-скрипт, job `b9dtifqkw`): RUN 1 —
  ЧИСТЫЙ УСПЕХ (`Start-Emulator` → сразу `Install-App` →
  `Performing Streamed Install` / `Success`, без ручной паузы). Это
  прямое доказательство, что `Wait-PackageServiceReady` не тормозит и
  не ломает здоровый путь, и что немедленный install после boot проходит
  (то же место, где раньше ловился race «Can't find service: package»).
  RUN 2 упал ДО `Install-App` — сработал фолбэк `Start-Emulator` на
  таймауте снапшот-буда (класс AT-BUG-012), а внутри фолбэка
  `Clear-EmulatorStaleLocks` упала `NullReferenceException` на непустой
  `hardware-qemu.ini.lock` — заведён `bugs/AT-BUG-014.md` (новый,
  отдельный блокер, не трогаю AT-BUG-012 код).
- Вторая попытка (harness с recurse-safe очисткой + try/catch, job
  `b625p3u0x`): RUN 1 SUCCESS, RUN 2/3 FAIL той же причиной (снапшот-таймаут
  → фолбэк → та же NullReferenceException) — `Install-App` не достигнут.
- Третья попытка (harness с graceful-kill+grace-period, job `ba67eein2`):
  ВСЕ 3 цикла FAIL той же причиной, `Install-App` ни разу не достигнут.
- По указанию координатора — отказ от сложных harness-скриптов, простой
  канонический цикл (`. tasks.ps1; Start-Emulator; Install-App`, job
  `bqiii5z10`): снова тот же фолбэк → та же NullReferenceException.
  Раскопка корня (см. `bugs/AT-BUG-014.md`, запись 22:35): `Start-Emulator`
  на фолбэке убивает `Stop-Process -Id $proc.Id` — PID launcher'а
  `emulator.exe`, НЕ фактического дочернего `qemu-system-x86_64.exe`,
  который остаётся жить (провисел 30+ минут, подтверждено `Get-Process`)
  и легитимно держит лок — поэтому КАЖДАЯ следующая попытка натыкалась на
  тот же крэш, это не флуктуация, а системное следствие незамеченного
  раньше механизма (задокументировано в AT-BUG-014, не чиню
  AT-BUG-012-код сам — D-0037).

Итог: 1 чистое успешное наблюдение `Install-App` немедленно после
`Start-Emulator` (положительное свидетельство фикса, race не
воспроизвёлся) + 6 неудач, ВСЕ до `Install-App` (не относятся к
`Wait-PackageServiceReady`, относятся к отдельному, уже
задокументированному экологическому блокеру AT-BUG-014). Полных «3
подряд» не набрано за разумное время сессии — статус ОСТАЁТСЯ `Open`
(не маскирую критерий, не подделываю «Fixed» без выполненного пункта
3). Среда погашена (`Get-Device` → `NO DEVICE`, зомби-процесс
`qemu-system-x86_64` от фолбэка убит вручную, лок-артефакты сняты),
лок снят. Рекомендация: повторить регресс (`Start-Emulator` → сразу
`Install-App`, x3) следующей сессией ПОСЛЕ починки корня AT-BUG-014
(зомби-процесс на фолбэке) — тогда `Start-Emulator` перестанет падать
до достижения `Install-App`, и «3 подряд» будет собрать реально, а не
упираться в чужой блокер.

**2026-07-17T23:45:00Z — test-maintainer, Open → Fixed (attempt 2,
критерий 3 закрыт после починки AT-BUG-014 этим же проходом):**

`scripts/tasks.ps1` НЕ трогаю в этой записи — реализация
(`Wait-PackageServiceReady`) уже полная с записи 22:40:00Z; эта
попытка — только регресс-witness критерия 3 (собрать «3 подряд»),
теперь без чужого блокера AT-BUG-014 на пути.

Простой секвенциальный цикл (по указанию координатора — без
собственного harness/teardown-скрипта): каждый прогон —
канонический `. tasks.ps1; Start-Emulator; Install-App` через один
`run_in_background`-вызов, ожидание фактического завершения job
(нотификация), затем `adb emu kill` + поллинг `Get-CimInstance
Win32_Process` до `CLEAN` перед следующим циклом. Перед стартом
серии — `Get-Device` → `NO DEVICE`, проверка процессов —
чисто (0 emulator/qemu).

- **RUN 1** (job `b52xa91fp`): `Start-Emulator` → `Waiting for
  device boot (snapshot, up to 45s)... Emulator booted.` →
  `Install-App` → `Performing Streamed Install` / `Success`. Чисто,
  без стейл-локов (среда была девственно чистой).
- Teardown 1: `adb emu kill` → `OK`; поллинг процессов →
  `CLEAN` (оба транзитных `emulator.exe` вышли сами, ожидаемо по
  witness AT-BUG-014).
- **RUN 2** (job `bc1ibylxn`): `Start-Emulator` → `Removed stale
  lock: ...multiinstance.lock` (штатная зачистка обычного
  post-`emu kill` артефакта, не путать с blocking directory-lock
  AT-BUG-014) → `Waiting for device boot... Emulator booted.` →
  `Install-App` → `Performing Streamed Install` / `Success`.
- Teardown 2: `adb emu kill` → `OK`; поллинг → `CLEAN`.
- **RUN 3** (job `bqfrr6lal`): та же картина — `Removed stale lock:
  ...multiinstance.lock` → `Emulator booted.` → `Install-App` →
  `Performing Streamed Install` / `Success`.

**3/3 подряд успешных `Start-Emulator` → сразу `Install-App` без
ручного вмешательства — критерий 3 закрыт.** Ни разу не встретился
ни симптом AT-BUG-013 (`Can't find service: package`), ни симптом
AT-BUG-014 (NullReferenceException на directory-lock/фолбэк) — оба
фикса держат здоровый путь стабильно.

Финальный teardown: `adb emu kill` → поллинг процессов → `CLEAN`
(0 `emulator.exe`/`qemu-system-x86_64.exe`); `Get-Device` → `NO
DEVICE`. `python scripts/arch_check.py` на актуальном HEAD → «ошибок
0, предупреждений 0». `scripts/tasks.ps1` этим проходом не менялся
(owns этой задачи — только `bugs/AT-BUG-013.md`).

Пересмотра стратегии/рисков не требует (инфраструктурный
regression-witness, поведение приложения не менялось). Новых
блокеров не обнаружено. `status: Open → Fixed`, лок снят. Готово к
`fix-verifier` (B4 → D1, долг тестовой обвязки — сборку приложения
ждать не нужно, guard test-maintainer).

**2026-07-18T00:20:00Z — fix-verifier (D1, независимая верификация,
Fixed → Verified):**

Часть консолидированной 7-багов device-сессии (тот же лок
`fix-verifier:2026-07-17T21:02:01`). Прямой регресс-witness этой же
сессии (не переиспользование чужого прогона): `Start-Emulator
-WritableSystem` → `Get-Device` → `emulator-5554` → **`Install-App`
СРАЗУ, без паузы** → `Performing Streamed Install` / `Success`. Race
«Can't find service: package» не воспроизвёлся. Это независимое,
четвёртое по счёту (после witness'а test-maintainer 3/3) подтверждение
здорового пути `Wait-PackageServiceReady`.

Замеченный аналог (не расширяю scope, докладываю по правилу 9 —
уже отмечен critic'ом на приёмке 20:55:05Z в очереди Lead):
`framework/core/adb.py::install()`/`scripts/env.ps1::Install-Ao3Apk`
всё ещё не несут `Wait-PackageServiceReady`-паттерн — не блокер
Verified (primary конвейерный путь через `Install-App` прикрыт и
подтверждён), но повторяю находку явно, чтобы она не потерялась между
D1-проходами.

`python scripts/arch_check.py` → `ошибок 0, предупреждений 0`.
`app-under-test/` не тронут. Правки этого хода — только `bugs/
AT-BUG-013.md` (frontmatter + эта запись, снятие лока). Статус
переведён `Fixed → Verified`.
