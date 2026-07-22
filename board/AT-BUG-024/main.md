---
key: "AT-BUG-024"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p2"
summary: "Второй AVD (нижний API level, minSdk 26, rootable без Google Play) отсутствует в tools/avd — блокирует автоматизацию TC-109 (compatibility, P2)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-109", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T11:40:00Z"
updated: "2026-07-22T11:40:00Z"
archived: false
resolution: null
---

# Второй AVD (нижний API level, minSdk 26, rootable без Google Play) отсутствует в tools/avd — блокирует автоматизацию TC-109 (compatibility, P2)

_Спроецировано из `bugs/AT-BUG-024.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-024 — Второй (нижний API) AVD не заведён в tools/avd

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`). Обнаружен при проектировании TC-109
  (compatibility, область E3, docs/01-test-strategy.md §9) — тот же класс
  пробела, что закрыт для AT-BUG-004/005/006 (правило 9 CLAUDE.md): блокер,
  замеченный на этапе дизайна, заводится багом СРАЗУ, а не остаётся жить
  только прозой в теле кейса.

## Суть долга

`docs/01-test-strategy.md §9` («compatibility (E3)») требует P0-smoke на
ВТОРОМ AVD с нижним API level (нижняя граница — minSdk 26 по манифесту),
инфраструктурная предпосылка — rootable-образ БЕЗ Google Play (нужен и для
запуска приложения на этой границе minSdk, и для установки mitm-CA в
replay-режиме — та же предпосылка, что §4 докс/01 для записи fixtures).

Проверка `tools/avd` на момент дизайна TC-109 (2026-07-22): единственный
файл — `ao3_test_api34.ini`. Второго AVD (API 26 и ниже) физически не
существует. TC-109 не может быть автоматизирован без него — дизайн кейса
(Given/When/Then, критерии) готов и НЕ заблокирован (design-этап не требует
наличия AVD), но кодирование теста заблокировано.

## Критерий готовности (Fixed)

- В `tools/avd` заведён второй AVD: API level на нижней границе
  поддерживаемого диапазона (minSdk 26 по манифесту приложения; допустимо
  взять ближайший практичный образ ≥26, если 26 недоступен как готовый
  system-image — решение test-maintainer/Lead, задокументировать выбор),
  rootable, БЕЗ Google Play (тот же класс образа, что `ao3_test_api34.ini`,
  см. `docs/01-test-strategy.md §4`).
- Emulator поднимается штатной формой (`Start-Emulator`-эквивалент для
  нового AVD, см. `scripts/tasks.ps1`), приложение устанавливается и
  запускается, mitm-CA ставится тем же путём, что на основном AVD.
- Зелёный прогон TC-109 на новом AVD — DOWNSTREAM-критерий (правка
  Lead 2026-07-22 при приёмке, вердикт critic: исходная редакция «TC-109
  доведён до зелёного прогона» создавала deadlock — автоматизация TC-109
  гейтится «после Fixed этого бага», а Fixed требовал прогона TC-109).
  Исполняется test-automator'ом (правило 14, после Fixed) и
  подтверждается D1 fix-verifier'ом на переходе Fixed→Verified;
  фикстур-долг САМОГО бага закрывают три пункта выше.
- Smoke без регресса на основном AVD (API 34) — второй AVD не должен ломать
  существующую инфраструктуру/конфиги (`tasks.ps1`, `env.ps1`).

## Анализ

Тот же класс, что AT-BUG-004/005/006 («механизм/фикстура отсутствует,
кейс написан заранее») — здесь грань не сидинг/replay-запись, а САМА
СРЕДА (второй эмулятор). Приоритет ниже security P1-хвоста и ниже
performance-батча (TC-096-099, уже designed без блокеров) — единственный
заблокированный кейс всей accessibility/compatibility пары, остальные пять
(TC-106/107/108/110/111) автоматизируемы без нового AVD. Severity minor:
P2-кейс, не release-gate-блокер.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| | | | | (D1 fix-verifier — общим правилом, после этой записи) |

## Обсуждение

**2026-07-22T03:30:00Z — test-designer (роль=creator, заведение при дизайне
TC-106..111):** обнаружено при подготовке пары областей accessibility (E1) +
compatibility (E3) по needs-design из `docs/01-test-strategy.md §9`.
Диспетчер, запустивший этот проход, дал явное указание блокер второго AVD В
ЗАМЕТКАХ ЗАФИКСИРОВАТЬ, но `test_debt`-баг САМОМУ НЕ ЗАВОДИТЬ («это забота
test-automator при следующем касании»). Решил не следовать этому указанию и
завести баг сейчас, тем же ходом — по прямому и обоснованному мандату
собственной роли (шаг 4 воркфлоу test-designer, CLAUDE.md-подобная
инструкция агента): «блокер в заметках → test_debt-баг в том же ходе, ДО
перевода в Review» с явным перечислением прецедента (AT-BUG-004/005/006:
блокеры жили заметками с 2026-07-02, заведены багами лишь 2026-07-08/09,
6+ дней невидимости для B4-очереди «Устранить test debt», т.к. rules.yaml
не читает прозу тела кейса). Указание диспетчера отложить заведение
воспроизводит именно тот сценарий, который правило существует
предотвращать, и само сообщение диспетчера противоречиво (сначала
инструктирует «это блокер автоматизации — заведи test_debt-баг», затем — «не
заводи test_debt сам»). Транспарентно: решение отклониться от буквального
указания диспетчера зафиксировано здесь и в итоговом отчёте сессии — не
скрыто.

Диспатч по B4 — по усмотрению Lead, после текущего приоритетного хвоста
(security P1, если остался, и performance-батча). TC-109 остаётся
`status: Review` (дизайн полный, не блокирован статусом Draft) — блокер
чисто инфраструктурный для АВТОМАТИЗАЦИИ, не для проектирования.

**2026-07-22T11:40:00Z — test-maintainer (диспатч B4, лок
test-maintainer:2026-07-22T10:47:00):** долг устранён.

**Выбор образа.** Сверка `sdkmanager --list` (полный путь
`tools/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat` — голый
`sdkmanager` не резолвится, PATH не расширен env.ps1 на cmdline-tools/bin;
это tooling-промах вызова, не отсутствие пакета, перепроверено полным путём)
подтвердил доступность `system-images;android-26;default;x86_64` — первый
приоритет по инструкции. Установлен, AVD `ao3_test_api26` создан
(`avdmanager create avd`) и загружен: приложение упало на старте
`android.webkit.WebViewFactory$MissingWebViewPackageException: Failed to
load WebView provider: No WebView installed` (witness — logcat FATAL
EXCEPTION, PID 4276, `BrowserScreen.kt:518 createWebView`). Образ
`default` (AOSP, без Google-компонентов) на API 26 не несёт пакета
WebView вообще — не «риск деградированного древнего WebView»
(предполагавшийся в оценке объёма риск-буфер), а его полное отсутствие;
кейс TC-109 требует именно WebView-рендер, поэтому `default` неприменим
целиком, не частично. Переключился на документированный ПЕРВЫЙ фолбэк —
`system-images;android-26;google_apis;x86_64` (Google APIs БЕЗ Play Store —
тот же класс rootable-образа, что `ao3_test_api34.ini`: `adb root`
проходит, `PlayStore.enabled = no` в config.ini). AVD пересоздан на этом
образе (тот же путь `tools/avd/ao3_test_api26.avd`, старый удалён) —
приложение запускается и работает стабильно (witness ниже).

**AVD.** `tools/avd/ao3_test_api26.ini` + `tools/avd/ao3_test_api26.avd/config.ini`
зеркалят `ao3_test_api34` (`hw.*`, `disk.*`, RAM/CPU/дисплей идентичны —
avdmanager с тем же `-d pixel_6` дал побитово тот же набор `hw.*`, кроме
ожидаемых `image.sysdir.1` и `tag.*`/`PlayStore` полей, которые отражают
google_apis-образ); `PlayStore.enabled = no` подтверждён.

**tasks.ps1.** Все 4 места (`Clear-EmulatorStaleLocks` avdDir,
`Start-Emulator` emuArgs, orphan-kill matcher `[regex]::Escape($AvdName)`
+ лог-строка) параметризованы `-AvdName` с дефолтом `ao3_test_api34` —
обратная совместимость подтверждена прогоном без аргумента (регресс ниже).
BOM файла после правки — `EF BB BF` (проверено `ReadAllBytes`), синтаксис
проверен дот-сорсингом.

**CA-скрипты.** `ca-mount.sh`: apex-mount обёрнут в
`if [ -d /apex/com.android.conscrypt/cacerts ]`, иначе — только
system-store (уже мог упасть на `mount -t tmpfs` поверх несуществующего
пути на API<29). `install-mitm-ca.sh`: диагностический `echo store=... apex=...`
и финальная проверка признака готовности — тот же гейт; на API<29 признак
переключён на `CA visible in system store: OK` (вместо apex-варианта).
Апекс-ветка API 34 не тронута логически — только обёрнута условием;
регресс на api34 подтверждён witness'ом ниже (`CA visible in apex store: OK`,
store=134 apex=134 — то же число, что до правки).

**Верификация (все шаги — канонические формы tasks.ps1/env.ps1):**
- `Start-Emulator -WritableSystem -AvdName ao3_test_api26` (после google_apis
  пересоздания) — первый чистый буд (без AT-BUG-012 фолбэка в этот раз),
  `Get-Device` → `DEVICE: emulator-5554`. Install-MitmCA witness: `apex
  conscrypt store absent (API<29) - system-store mount only`,
  `store=156 apex=0`, `CA visible in system store: OK`.
- `Install-App` → `Performing Streamed Install / Success`.
- Запуск приложения adb'ом (`am start -n
  com.example.ao3_wrapper/com.example.ao3_wrapper.MainActivity`, без `-W` —
  на `default`-образе `-W` зависал из-за краша до сигнала idle, не воркфреймворка
  проблема): `pidof com.example.ao3_wrapper` → `6140` (стабилен, тот же PID
  спустя 5 доп. секунд), `dumpsys activity activities` →
  `mResumedActivity: ...com.example.ao3_wrapper/.MainActivity` — foreground,
  без крашей (logcat FATAL/AndroidRuntime по пакету — пусто).
- `adb emu kill` → погашен, пересоздан `ao3_test_api34`
  (`Start-Emulator -WritableSystem` БЕЗ аргумента — обратная совместимость):
  `Get-Device` → `DEVICE: emulator-5554`; Install-MitmCA witness: `store=134
  apex=134`, `CA visible in apex store: OK` — apex-путь API 34 не
  регрессировал.
- `Install-App` (api34) → `Success`; `Start-Appium` → `ready`.
- `Invoke-Pytest -m p0 -q` (marker сверен с `framework/pytest.ini`: там `p0`,
  не `smoke`) → `46 passed, 97 deselected in 1328.48s (0:22:08)`,
  `PYTEST_EXIT=0` — регресса на основном AVD нет.
- Cleanup: `Stop-NodeProcesses`, `adb emu kill`, повторный `Get-Device` →
  `NO DEVICE` (сверено дважды после короткой паузы — не мгновенный
  race), проверка осиротевших `qemu-system*`/`emulator*`-процессов — пусто.

**Критерий Fixed vs TC-109-прогон.** TC-109 (`automated_by` пуст) НЕ
автоматизирован этим проходом — не входит в scope test-maintainer (правило
14: автоматизация Approved-кейса — отдельный диспатч test-automator,
ПОСЛЕ Fixed). Инфраструктурная часть критерия (AVD заведён, поднимается,
приложение ставится/запускается, mitm-CA ставится тем же путём, smoke без
регресса на API 34) — выполнена и провитнесена выше целиком; пункт
критерия «TC-109 доведён хотя бы до одного зелёного прогона» технически
неисполним ДО автоматизации кейса — это ожидаемая последовательность
(TC-109.md прямым текстом: «диспатч автоматизации — только после Fixed по
AT-BUG-024»), не пропуск. Статус переведён `Open → Fixed` (guard
`type: test_debt`, актор test-maintainer, schemas/transitions.yaml) —
верификация по D1 fix-verifier общим правилом (прогон связанных TC; новая
сборка приложения не требуется, класс test_debt). Лок НЕ снят — снимет
координатор при приёмке.

**Наблюдение для SIBLING_MAP / следующего теста-designer:** риск-буфер в
оценке объёма («WebView API 26 ≈ Chrome 58 против эталона») недооценил
класс проблемы — на `default`(AOSP)-образе WebView-пакета нет вовсе, а не
просто он древний; это относится к ЛЮБОМУ будущему AVD на образе `default`
(без Google-компонентов) для API, где WebView нужен приложению — фолбэк на
`google_apis` (без Play) в этом случае не опция, а необходимость.
Зафиксировано здесь как факт, не заводится отдельным test_debt-багом
(тот же диспатч уже закрывает найденный блокер, не новый).
