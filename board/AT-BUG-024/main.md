---
key: "AT-BUG-024"
project: "AO3"
issueType: "bug"
status: "bug-verified"
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
created: "2026-07-22T14:05:00Z"
updated: "2026-07-22T14:05:00Z"
archived: false
resolution: "done"
---

# Второй AVD (нижний API level, minSdk 26, rootable без Google Play) отсутствует в tools/avd — блокирует автоматизацию TC-109 (compatibility, P2)

_Спроецировано из `bugs/AT-BUG-024.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-07-22T15:50:00Z | framework env (test_debt, новая сборка приложения не требуется); тестируемая сборка 1.10 (versionCode 11), 6455af0cfc2c937e81975f59a250476c77aecb73 | Критерий п.1-2 (api26 AVD boot/install/CA) независимо; смок `-m p0` (46 TC) на api34 x2 | п.1-2: PASS независимо подтверждены. п.3: FAIL x2 (см. ниже) — не регресс фикса, среда деградировала (см. Обсуждение) | ЧАСТИЧНО — status НЕ переведён в Verified, остаётся Fixed; открыт ESC-006 |
| 2026-07-22T14:05:00Z | critic-вход (правило 3б, ESC-006) + координатор | п.1-2 (уже подтверждены выше) + п.3 в НАМЕРЕНИИ через прямой green-прогон test-maintainer (`46 passed`, 2026-07-22T11:40, С уже применённым фиксом) | critic независимо сверил historical Get-WinEvent (60 событий, та же дата-раскладка, поправка witness — offset≠timestamp), подтвердил sibling-класс AT-BUG-016-live эмпирически по исходнику (test_ao3_selectors.py, та же SORT_FILTER_FORM_URL), исключил регресс дважды (темпорально + прямой green с фиксом). Диспозиция (а): краш не блокирует этот баг, отдельный test_debt заведён (AT-BUG-026) | Fixed → Verified (`by: fix-verifier`, критерий выполнен на совокупности улик; ESC-006 resolved) |

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

**2026-07-22T15:50:00Z — fix-verifier (D1, лок fix-verifier:2026-07-22T12:50:00Z,
НЕ снят — приёмка за координатором):** независимая перепроверка критерия
готовности, свежий прогон (не копирую witness test-maintainer выше).

**Критерий п.1 (`ao3_test_api26` существует, поднимается штатной формой).**
`Start-Emulator -WritableSystem -AvdName ao3_test_api26` — чистый буд,
`Get-Device` → `DEVICE: emulator-5554`. Install-MitmCA witness (свежий):
`apex conscrypt store absent (API<29) - system-store mount only`,
`store=156 apex=0`, `CA visible in system store: OK` — идентично witness'у
test-maintainer. PASS.

**Критерий п.2 (приложение ставится/запускается, CA тем же путём).**
`Install-App` → `Performing Streamed Install / Success` (первая попытка упала
`Could not access the Package Manager` — транзиентное состояние сразу после
zygote-рестарта CA-скрипта, не отсутствие устройства; повтор без изменений
прошёл сразу — тот же класс, что F-30/п.6 CLAUDE.md, не воспроизводил
отдельно). Запуск `am start -n com.example.ao3_wrapper/.MainActivity` (без
`-W`, как у test-maintainer): `pidof` стабилен на одном PID (8239) дважды с
интервалом 5с; `dumpsys activity activities` → `mResumedActivity:
...com.example.ao3_wrapper/.MainActivity`; `adb logcat -d -b crash` по
пакету — пусто (WebViewFactory-креша, ранее найденного test-maintainer'ом
на `default`-образе, здесь нет — `google_apis`-образ подтверждён рабочим
независимо). PASS.

**Критерий п.3 (смок `-m p0` без регресса на api34) — НЕ подтверждён чистым
прогоном, 2/2 попытки.** После `adb emu kill` (api26) →
`Start-Emulator -WritableSystem` (api34, без `-AvdName`) → Install-MitmCA
witness `store=134 apex=134`, `CA visible in apex store: OK` (apex-путь API 34
не регрессировал, как и у test-maintainer) → `Install-App: Success` →
`Start-Appium: ready` → `Invoke-Pytest -m p0 -q`:
- Попытка 1: `16 passed`, затем `FAILED
  tests/canary/test_ao3_selectors.py::test_save_filter_button_idempotent_live`,
  затем 29 ERROR подряд (все — либо `adb.exe: no devices/emulators found`,
  либо `Room не создал ao3_ratings.db`, либо `WebDriverException:
  disconnected: not connected to DevTools` / `device 'emulator-5554' not
  found`) — эмулятор пропал ПОЛНОСТЬЮ (`Get-Device` сразу после runa →
  `NO DEVICE`, ни одного осиротевшего `qemu-system*`/`emulator*`-процесса).
  `1 failed, 16 passed, 97 deselected, 29 errors in 1804.84s`, `PYTEST_EXIT=1`.
- Диагностика: Windows Application event log (`Get-WinEvent Id=1000`) —
  краш `qemu-system-x86_64.exe`, `0xc0000005` (access violation), время
  `2026-07-22 14:59:24` — совпадает с моментом обрыва устройства.
  [Поправка critic-входа при приёмке: `0x6a1785af` в записи события —
  PE-timestamp самого бинарника `qemu-system-x86_64.exe` (константа,
  одинакова во всех записях, т.к. бинарник один и тот же), НЕ адрес/
  смещение сбоя; реальное «Смещение ошибки» различно в каждом крахе
  (см. ниже) — исходная формулировка «идентичное смещение» ошибочна.]
- Попытка 2 (после полного `Start-Emulator -WritableSystem` → `Install-App`
  → `Start-Appium` → `Invoke-Pytest -m p0 -q` заново): ИДЕНТИЧНАЯ картина —
  `16 passed` затем тот же провал на `test_save_filter_button_idempotent_live`
  (17-й тест по `--collect-only` порядку), `Get-Device` → `NO DEVICE`. Второй
  краш в event log: `qemu-system-x86_64.exe`, `0xc0000005`,
  `2026-07-22 15:32:37`. Процесс остановлен вручную (`Stop-Process`) после
  подтверждения повторного идентичного краха — дальнейшие 29 ошибок не несли
  бы новой информации (fail-fast, см. ниже).
- **Это НЕ регресс фикса AT-BUG-024.** (а) Изменения фикса — создание
  `ao3_test_api26`, параметризация `-AvdName` в `tasks.ps1`, условная
  apex-ветка `ca-mount.sh`/`install-mitm-ca.sh` — ни один не участвует в
  код-пути `-m p0` прогона на api34 (apex-путь api34 явно подтверждён
  неизменным — `store=134 apex=134` оба раза). (б) `qemu-system-x86_64.exe`
  `0xc0000005`, тот же бинарник и exception code — recurring: event log
  несёт тот же класс краха 21.07 17:19:50, 21.07 11:25:19, 20.07 03:36:26,
  19.07 (4 раза), 18.07 (5 раз), 15.07 (2 раза) — т.е. ЗАДОЛГО до фикса
  test-maintainer'а сегодня; независимая сверка critic'а (Get-WinEvent,
  60 событий) подтвердила ту же дату-раскладку И вскрыла, что реальное
  «Смещение ошибки» РАЗЛИЧНО в каждой записи (0x1b93, 0x1e92, 0x228c,
  0x2154, 0x186a, 0x11c0, 0x1dc7, 0x2071, 0x1b21, 0x28fe, 0x1c03, 0x2652,
  0x2d9c, 0x1f73, 0x18bd, 0x2652) — ожидаемо для крашей в динамически
  генерируемом коде (`unknown`-модуль, TCG-JIT/GPU-эмуляция), где адрес
  плывёт от прогона к прогону; класс краха держится на бинарнике/
  exception code/модуле/рекуррентности/тяжёлой странице, не на offset'е.
  (в) Точка провала — `test_save_filter_button_
  idempotent_live` (Sort&Filter live-рендер) — тот же класс страницы
  (тяжёлый live-рендер формы), что уже задокументирован как источник
  падений `qemu-system-x86_64.exe 0xc0000005` в `state/escalations.md`
  ESC-002 (`AT-BUG-016`, TC-040, тот же exception code, устранено там сужением
  live-forward до полностью самодостаточного flow). Здесь падает LIVE-вариант
  теста (не `.mitm`-replay), т.е. вне охвата фикса AT-BUG-016.
- **Fail-fast среды (docs/06 §5):** 2 идентичных env-класса отказа на одном
  и том же шаге (`qemu-system-x86_64.exe 0xc0000005` в момент/сразу после
  `test_save_filter_button_idempotent_live`) → протокол дальше не гоняю.
  Cleanup выполнен: `Stop-NodeProcesses`, `adb emu kill` (`no emulator
  detected` — уже мёртв), повторный `Get-Device` → `NO DEVICE`, проверка
  осиротевших `qemu-system*`/`emulator*` — пусто.
- **Решение по статусу.** `schemas/transitions.yaml` не определяет
  `Fixed → Blocked` для `bug` (только `Open/Reopened/Rejected → Blocked`) —
  не проставляю `Blocked` в frontmatter (был бы нелегальный переход).
  Критерии п.1/п.2 подтверждены чисто и независимо; п.3 недостижим чистым
  прогоном на этой сессии по причине, не относящейся к фиксу. Не перевожу в
  `Verified` (п.3 критерия буквально не выполнен зелёным прогоном) и не
  перевожу в `Reopened` (это исказило бы находку — исходный долг, отсутствие
  AVD, устранён и подтверждён; репро НЕ живо). Статус оставлен `Fixed` без
  изменений, заведена запись `ESC-006` в `state/escalations.md`
  (`env_issue_twice_in_a_row` из `immediate_alerts`, `state/sla.yaml`).
  Решение — за координатором: (а) принять критерии 1/2 как достаточные и
  перезапросить ТОЛЬКО п.3 отдельным прогоном после стабилизации среды, или
  (б) считать краш sibling-долгом (класс ESC-002/AT-BUG-016, но новая точка —
  LIVE, не replay, вариант `test_save_filter_button_idempotent_live`) и
  завести/расширить test_debt артефакт до перевода в Verified.
- **Аналог для SIBLING_MAP / test-maintainer (D-0043, не расширяю scope
  сам):** `qemu-system-x86_64.exe 0xc0000005` на live-рендере Sort&Filter —
  тот же класс, что ESC-002/AT-BUG-016 (TC-040 replay), но НЕ покрыт тем
  фиксом (там сужен только `.mitm`-flow, live-вариант остаётся тяжёлым
  форвардом на archiveofourown.org). Кандидат на отдельный test_debt/infra
  долг (broken_environment) или на расширение AT-BUG-016, решение —
  test-maintainer/Lead.

**Наблюдение для SIBLING_MAP / следующего теста-designer:** риск-буфер в
оценке объёма («WebView API 26 ≈ Chrome 58 против эталона») недооценил
класс проблемы — на `default`(AOSP)-образе WebView-пакета нет вовсе, а не
просто он древний; это относится к ЛЮБОМУ будущему AVD на образе `default`
(без Google-компонентов) для API, где WebView нужен приложению — фолбэк на
`google_apis` (без Play) в этом случае не опция, а необходимость.
Зафиксировано здесь как факт, не заводится отдельным test_debt-багом
(тот же диспатч уже закрывает найденный блокер, не новый).
