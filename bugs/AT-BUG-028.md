---
id: AT-BUG-028
title: "AVD ao3_test_api26 несёт EOL WebView (Chrome 69.0.3497) без совместимого chromedriver — блокирует автоматизацию TC-109 (compatibility, P2)"
type: test_debt
debt_kind: missing_fixture
severity: minor
status: Verified
found_in: "framework env, не зависит от сборки приложения; текущая тестируемая сборка 1.10 (versionCode 11), 6455af0cfc2c937e81975f59a250476c77aecb73"
fixed_in: "framework env (framework/config/settings.py, framework/config/capabilities.py, framework/tests/test_compatibility.py, tools/avd/ao3_test_api29.*, docs/environment-setup.md, test-cases/compatibility/TC-109.md) — на текущей сборке 1.10 (versionCode 11), новая сборка приложения не требуется"
last_seen_in: "1.10 (versionCode 11)"
test_cases: ["TC-109"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-07-24T05:56:00Z"
updated: "2026-07-24T05:56:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
---

# AT-BUG-028 — ao3_test_api26 WebView EOL (Chrome 69), нет chromedriver — блокирует TC-109

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`) — вторая инфраструктурная предпосылка второго
AVD (после AT-BUG-024, который завёл сам AVD и решил проблему боута/CA/
установки). Обнаружен test-automator'ом при попытке автоматизации TC-109
(rule 14, 2026-07-22).

## Суть долга

AVD `ao3_test_api26` (образ `google_apis;android-26;x86_64`, заведён
AT-BUG-024) успешно поднимается, приложение ставится и запускается —
preflight `api26_device_required` в `framework/tests/test_compatibility.py`
это подтверждает. Но embedded System WebView этого образа — **Chrome
69.0.3497** (релиз ~2018, давно EOL). Appium/chromedriver-autodownload не
находит совместимый chromedriver для этой версии:

```
No Chromedriver found that can automate Chrome 69.0.3497
```

Любой шаг, переключающий WebView-контекст (`wait_app_ready`,
`open_work_page`, любая WebView-навигация — весь маршрут TC-109), падает
`WebDriverException` ДО начала сценария.

Тест `test_smoke_path_on_api26_no_regression`
(`framework/tests/test_compatibility.py`) написан и оставлен
`@pytest.mark.skip`-помеченным как witness находки (тот же паттерн, что
TC-020/BUG-012); `automated_by` TC-109 НЕ заполнен.

## Критерий готовности (Fixed)

Один из (решение test-maintainer/Lead при диспатче B4, задокументировать
выбор):
- Сайдлоад более новой версии System WebView на образ `ao3_test_api26`
  (APK Google WebView, совместимый с API 26, если существует такой канал
  дистрибуции для устаревшего API).
- Иной system-image/канал для API 26 (или ближайшего практичного API ≥26)
  с современным WebView, сохраняющий rootable/без-Google-Play свойства,
  уже установленные AT-BUG-024 (`adb root`, `PlayStore.enabled = no`).
- Legacy chromedriver вручную (найти/собрать бинарник, совместимый с Chrome
  69), задать явно в capabilities вместо autodownload — обходной путь,
  если апгрейд WebView образа недоступен/нецелесообразен.
- Зелёный прогон `test_smoke_path_on_api26_no_regression` (снять skip) —
  DOWNSTREAM-критерий (тот же паттерн deadlock-осторожности, что
  AT-BUG-024: TC-109 остаётся `automated_by` пуст до Fixed этого бага,
  снятие skip и первый зелёный прогон — часть верификации D1, не самого
  Fixed).
- Регресс на основном AVD (API 34) — без изменений, если правка затронет
  общие части `tasks.ps1`/образов.

## Анализ

Тот же класс, что AT-BUG-004/005/006/024/025 («механизм/фикстура
отсутствует, кейс написан заранее») — здесь грань конкретно WebView-версия
образа, обнаруженная ПОСЛЕ того, как AT-BUG-024 закрыл боут/CA/установку
(последовательные слои одной инфраструктурной задачи, не повторный провал
диагностики). Приоритет — по усмотрению Lead при следующем B4-диспатче;
TC-109 остаётся единственным заблокированным кейсом compatibility-пары
(TC-106/107/108/110/111 автоматизированы этим же проходом).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-24 | framework env (не завязано на сборку приложения); тестируемая сборка 1.10 (versionCode 11) не изменилась | TC-109 (`test_smoke_path_on_api26_no_regression`, AVD `ao3_test_api29`, БЕЗ `AO3_CHROMEDRIVER_EXECUTABLE`) + регресс api34 (`test_smoke.py`+`test_rating.py`, тот же WebView-код-путь, что тронула правка `capabilities.py`) | ao3_test_api29: `1 passed in 94.45s`, `PYTEST_EXIT=0` (независимый прогон fix-verifier, не полагается на 3 прогона отчёта фикса). api34 регресс: `15 passed in 465.36s`, `PYTEST_EXIT=0`. Код-сверка `settings.py`/`capabilities.py`: `CHROMEDRIVER_EXECUTABLE` пусто по умолчанию (`os.environ.get("AO3_CHROMEDRIVER_EXECUTABLE", "")`), пустая ветка → `appium:chromedriverAutodownload=True` (autodownload-путь не тронут) — подтверждено и косвенно зелёным api34-прогоном. TC-109.md: `status: Automated`, `automated_by` заполнен, уже прошёл F1 (test-reviewer, красная проба зафиксирована в кейсе) — сверено, не доверился пересказу. Cleanup обоих AVD подтверждён (`Get-Device` → `NO DEVICE`, нет осиротевших `qemu-system*`). | **Verified** (D1, fix-verifier) |

## Обсуждение

**2026-07-22T20:00:00Z — координатор (Sonnet, degraded-режим):** заведён по
докладу test-automator (a11y-compat batch, rule 14) — диспетчер задачи явно
указал воркеру не заводить баг самостоятельно на этот блокер (решение —
за координатором), что соблюдено (доклад в отчёте, не самозаведение).
Правило 9 CLAUDE.md: блокер, найденный при автоматизации, заводится
test_debt-багом сразу — тот же класс, что AT-BUG-024 (предыдущий слой той
же инфраструктурной задачи).

**2026-07-23T02:20:00Z — test-maintainer (диспатч B4, лок
test-maintainer:2026-07-22T16:50:00Z, НЕ снят — приёмка за координатором):**
долг устранён, критерий готовности выполнен путём "б" (иной образ на
ближайшем практичном API level).

**Попытка 1 — сверка альтернативного канала на самом API 26.** `sdkmanager
--list` (полный путь, тот же приём, что AT-BUG-024) подтвердила: для
`android-26` доступны только `default` (AOSP, нет WebView вовсе, см.
AT-BUG-024), `google_apis;x86_64` (уже используемый, Chrome 69 EOL) и
`google_apis_playstore;x86` (единственная Play-архитектура на этом API —
только x86, НЕ x86_64, и добавляет Google Play, что противоречит
rootable/без-Google-Play требованию критерия). Альтернативного канала с
современным WebView на самом API 26 нет — путь "б" в буквальном смысле "тот
же API 26" исчерпан.

**Попытка 2 — legacy chromedriver вручную (путь "в").** Скачан
`chromedriver_2.41_win32.zip`
(`https://chromedriver.storage.googleapis.com/2.41/`, `ChromeDriver
2.41.578737`, `Supports Chrome v67-69` — диапазон, покрывающий
69.0.3497), распакован в `tools\chromedriver-legacy\chromedriver.exe`.
Добавлена явная capability-механика: `framework/config/settings.py::
CHROMEDRIVER_EXECUTABLE` (env `AO3_CHROMEDRIVER_EXECUTABLE`, пусто по
умолчанию) → `framework/config/capabilities.py::build_options`
(`appium:chromedriverExecutable` вместо `appium:chromedriverAutodownload`,
только когда переменная задана — api34 не регрессирует).

Прогон `test_smoke_path_on_api26_no_regression` (skip снят, AVD
`ao3_test_api26`, `AO3_CHROMEDRIVER_EXECUTABLE` задан) упал на первом же
переключении WebView-контекста: `WebDriverException: The response to the
/status API is not valid: {"build":{"version":"alpha"},...}` (НЕ то же
сообщение, что исходная находка `No Chromedriver found...` — другая точка
провала). Диагностика по коду Appium
(`tools\appium\node_modules\appium-uiautomator2-driver\node_modules\
appium-chromedriver\build\lib\commands\process.js::waitForOnline`): текущий
`appium-chromedriver` жёстко требует `status.ready === true` в ответе
`/status`, иначе бросает именно это исключение.

Прямая эмпирическая проверка (локальный запуск бинарников, `GET /status`
на localhost, БЕЗ эмулятора):
- 2.41 (v67-69): `{"build":{"version":"alpha"},...}` — **нет** `ready`.
- 2.42 (v68-70): то же — **нет** `ready`.
- 2.43 (v69-71): то же — **нет** `ready`.
- 2.44 (v69-71): то же — **нет** `ready`.
- 2.45 (v70-72): `{"build":{"version":"2.45...},"ready":true,...}` — **есть**
  `ready`, но этот диапазон уже НЕ покрывает Chrome 69.

Вывод: поле `ready` появилось в chromedriver ровно на границе, где
поддержка Chrome 69 уже потеряна — ЛЮБОЙ chromedriver, совместимый с Chrome
69.0.3497, структурно не пройдёт readiness-проверку ТЕКУЩЕЙ версии Appium
(`appium 2.x`/`uiautomator2 8.0.1`, зафиксированной в `tools/appium`).
Путь "в" — тупиковый по конструкции для этой пары (Chrome 69 + текущий
Appium), не вопрос «трудно найти бинарник». Capability-механика оставлена
в коде (общая, безопасная — пуста по умолчанию), но НЕ используется для
решения этого бага.

**Попытка 3 (успешная) — путь "б", иной API level.** `sdkmanager --list`
подтвердила rootable без-Play образ `system-images;android-29;
google_apis;x86_64` (16 ревизия). Установлен, создан AVD `ao3_test_api29`
(`avdmanager create avd -d pixel_6`, тот же приём, что `ao3_test_api26`);
`config.ini`: `PlayStore.enabled = no`, `tag.id = google_apis` — те же
свойства, что и у основного/старого второго AVD. Быстрый пробный буд (без
CA/установки приложения) подтвердил embedded WebView этого образа:
`adb shell dumpsys package com.google.android.webview` →
`versionName=74.0.3729.185` (Chrome 74) — заведомо выше границы, на которой
появляется поле `ready` (2.45, v70-72).

**Полная верификация (канонические формы tasks.ps1/env.ps1):**
- `Start-Emulator -WritableSystem -AvdName ao3_test_api29` — чистый буд,
  `Get-Device` → `DEVICE: emulator-5554`. Install-MitmCA witness: `apex
  conscrypt store absent` (подтверждено прямой проверкой `test -d
  /apex/com.android.conscrypt/cacerts` → `ABSENT` — apex-модуль
  действительно отсутствует на этом образе API 29, не проверка ошиблась),
  `store=139 apex=0`, `CA visible in system store: OK`.
- `Install-App` → `Performing Streamed Install / Success` (без транзиентных
  ошибок в этот раз).
- `Start-Appium` → `ready`.
- `Invoke-Pytest -k test_smoke_path_on_api26_no_regression` — **3 прогона
  подряд, БЕЗ `AO3_CHROMEDRIVER_EXECUTABLE`** (autodownload штатно находит
  chromedriver для Chrome 74):
  - Попытка 1: `1 passed in 42.24s`, `PYTEST_EXIT=0`.
  - Попытка 2: `1 passed in 29.47s`, `PYTEST_EXIT=0`.
  - Попытка 3: `1 passed in 28.38s`, `PYTEST_EXIT=0`.
- Регресс на api34 (кратким smoke, не полным p0 — minor-баг, п.
  диспетчера): `Stop-NodeProcesses`/`adb emu kill` → `Start-Emulator
  -WritableSystem` (без `-AvdName`, api34) → `Install-App: Success` →
  `Start-Appium: ready` → `Invoke-Pytest tests/test_smoke.py
  tests/test_rating.py -v` (выбраны намеренно: оба модуля используют
  `wait_app_ready`/`open_work_page` — тот же код-путь `contexts.in_webview`
  → `build_options`, затронутый правкой `capabilities.py`) → **`15 passed
  in 449.60s`, `PYTEST_EXIT=0`** — регресса нет (autodownload-ветка
  `if/else` не тронута для пустой `CHROMEDRIVER_EXECUTABLE`).
- Cleanup: `Stop-NodeProcesses`, `adb emu kill`, `Get-Device` → `NO DEVICE`
  (сверено дважды после короткой паузы — race на первом чеке, второй чистый),
  проверка осиротевших `qemu-system*`/`emulator*` — пусто (сверено
  `Get-CimInstance Win32_Process`, пусто).

**Побочный артефакт диагностики.** `tools\avd\ao3_test_api26.ini`/`.avd`
оставлены на диске неиспользуемыми (не удалены — не мешают, `tasks.ps1`
уже параметризован `-AvdName` с AT-BUG-024, ничего по умолчанию на них не
ссылается); `tools\chromedriver-legacy\chromedriver.exe` (2.41) и
`tools\downloads\chromedriver_2.41_win32.zip` оставлены как рабочий
пример под задокументированную `CHROMEDRIVER_EXECUTABLE`-механику (хоть и
не используются для ЭТОГО решения). Диагностические zip-пробники
2.42/2.43/2.44/2.45/2.46 (скачаны в `tools\downloads\` для проверки, на
каком chromedriver впервые появляется поле `ready` в `/status`) удалены
после диагностики — не относятся к постоянным зависимостям репозитория
(housekeeping, CLAUDE.md); их извлечённые копии, использованные только для
локального `GET /status`, жили в scratchpad-директории сессии.

**Правки:** `framework/config/settings.py` (+`CHROMEDRIVER_EXECUTABLE`),
`framework/config/capabilities.py` (условная capability), `framework/
tests/test_compatibility.py` (skip снят, `API26_LEVEL` →
`SECOND_AVD_API_LEVEL="29"`, `SECOND_AVD_NAME`, докстринги/сообщения),
`docs/environment-setup.md` (таблица образов + разбор находки/решения),
`test-cases/compatibility/TC-109.md` (заголовок/фронтматтер/сценарий под
API 29, `automated_by` заполнен). Ни одна правка не коснулась
`app-under-test/`.

**Отмечено для test-strategist (не расширяю сам, D-0037):** второй AVD
(E3, docs/01-test-strategy.md §9) больше не покрывает буквальный
`minSdk=26` — только «ближайший практичный уровень». Оценка риска R-14 не
переоценена этим проходом; нужен отдельный проход test-strategist, чтобы
решить, устраивает ли это отклонение стратегию, или нужен более радикальный
путь (сайдлоад WebView-APK на сам API 26, путь "а" — не пробован в этом
диспатче: требует непроверенного стороннего APK-источника, вне бюджета
"2-3 разумные попытки" при уже найденном рабочем пути "б").

**Статус.** `Open → Fixed` (guard `type: test_debt`, `schemas/
transitions.yaml`, актор test-maintainer). Лок НЕ снят — снимет
координатор при приёмке.

**2026-07-24T05:56:00Z — fix-verifier (mode=verify, D1):** независимый
прогон на актуальной среде (лок fix-verifier:2026-07-24T05:26:00Z).
`Start-Emulator -WritableSystem -AvdName ao3_test_api29` → `Get-Device`
DEVICE, API 29 подтверждён (`getprop ro.build.version.sdk` → 29) →
`Install-App` Success (первая попытка упала транзиентно —
`PackageManagerInternal.freeStorage` NPE, тот же класс гонки boot vs
package manager, что уже отмечен в отчёте фикса — повтор через ~15с
прошёл) → `Start-Appium` ready (первый запуск не поднялся за 60s,
`Stop-NodeProcesses` + повтор — поднялся штатно) →
`Invoke-Pytest -k test_smoke_path_on_api26_no_regression -v`, БЕЗ
`AO3_CHROMEDRIVER_EXECUTABLE` (сверено отдельно: `env:
AO3_CHROMEDRIVER_EXECUTABLE` → `NOT SET`) — **`1 passed in 94.45s`,
`PYTEST_EXIT=0`**.

Переключение AVD: `Stop-NodeProcesses` + `adb emu kill` → `Get-Device`
NO DEVICE → `Start-Emulator -WritableSystem` (без `-AvdName`, api34,
сработал fallback `-no-snapshot-load` по известному AT-BUG-012, boot
всё равно завершился) → `Get-Device` DEVICE, API 34 подтверждён →
`Install-App` Success → `Start-Appium` ready → регресс
`Invoke-Pytest tests/test_smoke.py tests/test_rating.py -v`
(фоновый прогон, дождался блокирующим `Wait-Process` до завершения в
этом же ходе, не бросил на нотификацию) — **`15 passed in 465.36s`,
`PYTEST_EXIT=0`**.

Пункт DoD 4 (regression-safe пустой `CHROMEDRIVER_EXECUTABLE` на api34)
подтверждён точечным чтением кода (`settings.py`: default `""`;
`capabilities.py::build_options`: пустая ветка →
`appium:chromedriverAutodownload=True`, ветка `chromedriverExecutable`
не задета) — как и разрешал диспетчер, вместе с косвенным
подтверждением зелёного api34-регресса.

Пункт DoD 2 сверен самостоятельно (не пересказ фикса):
`test-cases/compatibility/TC-109.md` — `status: Automated`,
`automation_status: active`, `automated_by:
"framework/tests/test_compatibility.py::
test_smoke_path_on_api26_no_regression"`, F1-ревью test-reviewer уже
пройдено (независимое воспроизведение + красная проба
зафиксированы в самом кейсе).

Cleanup подтверждён: `Stop-NodeProcesses` + `adb emu kill` →
`Get-Device` NO DEVICE; проверка осиротевших процессов
(`Get-CimInstance Win32_Process` по `qemu*`/`emulator*`) — только два
штатных kill-helper'а (`emulator -kill <pid> -sleep 20`,
самозавершающиеся), реальных `qemu-system*`/эмулятор-инстансов нет.

Ни одна правка не коснулась `app-under-test/` (только frontmatter/
таблица этого бага и `test-cases/compatibility/TC-109.md` не
трогались — уже заполнены test-maintainer'ом).

**Дефекты-собратья:** не замечено новых аналогов сверх уже
задокументированных в этом баге (R-14 смещение отмечено
test-maintainer для test-strategist, capability-механика
`CHROMEDRIVER_EXECUTABLE` оставлена как общий примитив на будущее —
оба уже учтены выше, повторно не дублирую).

**Статус.** `Fixed → Verified` (guard `by: [fix-verifier]`,
`schemas/transitions.yaml`). Лок снят.
