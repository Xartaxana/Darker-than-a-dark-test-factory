---
key: "AT-BUG-072"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p1"
summary: "Нет автоматизационного примитива нажатия клавиш громкости (KEYCODE_VOLUME_UP/DOWN) — блокирует листание страниц кнопками громкости"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-252", "test_case:TC-253", "test_case:TC-254", "test_case:TC-255", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-18T07:52:00Z"
updated: "2026-08-18T07:52:00Z"
archived: false
resolution: "done"
---

# Нет автоматизационного примитива нажатия клавиш громкости (KEYCODE_VOLUME_UP/DOWN) — блокирует листание страниц кнопками громкости

_Спроецировано из `bugs/AT-BUG-072.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-072 — нет обёртки над `adb shell input keyevent KEYCODE_VOLUME_UP/DOWN` с наблюдаемым подтверждением

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`).

## Суть долга

`browse-volume-button-paging` (сборка 59be96c6, `MainActivity.kt:105-124`)
перехватывает `KEYCODE_VOLUME_DOWN`/`KEYCODE_VOLUME_UP` для листания
страниц кнопками громкости. Тестопригодность прямо названа
test-strategist (docs/01-test-strategy.md §9): «клавиши подаются `adb
shell input keyevent 24/25` — примитива в фабрике может не быть».

Проверено: в `framework/steps/app_steps.py` есть только
`send_app_to_background` (`input keyevent KEYCODE_HOME`, с ожиданием
факта ухода в фон через `driver.query_app_state`) — прецедент формы, но
НЕ примитив для VOLUME_UP/DOWN. Голого `adb shell input keyevent 24`
недостаточно по классу «пустой/ошибочный вывод env-инструмента ≠ факт»
(CLAUDE.md, дисциплина команд п.6): нажатие клавиши само по себе не
наблюдаемо (`adb.shell` глотает returncode), поэтому тихо не сработавшее
нажатие неотличимо от штатного эффекта без явного ожидания последствия
(здесь — сдвиг scroll-позиции активной вкладки), тем же приёмом, что
`send_app_to_background` ждёт уход в фон.

Заблокированные кейсы: TC-252 (основной эффект листания обеими клавишами),
TC-253 (off-инвариант — клавиши при выключенной настройке), TC-254
(асимметрия перехвата поверх оверлея/панели/диалога), TC-255 (граница
перехвата — вкладки Library/Settings) — все требуют реального нажатия
клавиш громкости.

## Критерий готовности (Fixed)

- В `framework/steps/app_steps.py` (или аналоге) есть функция вида
  `press_volume_key(driver, direction)`, отправляющая `input keyevent
  KEYCODE_VOLUME_DOWN`/`KEYCODE_VOLUME_UP` и дожидающаяся наблюдаемого
  последствия (параметризуемый oracle — например, сдвиг scroll-позиции
  активной вкладки ЛИБО появление системного индикатора громкости, в
  зависимости от сценария), по образцу `send_app_to_background`.
- Хотя бы один из заблокированных кейсов (рекомендация: TC-252, основной
  позитивный путь) доведён до зелёного прогона на этом примитиве.
- Smoke без регресса.

## Анализ

Класс — «механизм адб есть, обёртки с наблюдаемым подтверждением нет»,
тот же, что породил `send_app_to_background`/`AT-BUG-004`-класс общих
`app_steps`-примитивов. Чинит фабрика по правилу «Устранить test debt»
(B4). Fixed не ждёт сборку приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт разбора |
| 2026-08-18T07:10:00Z | framework (test-only, `type: test_debt` — код уже был в рабочем дереве/HEAD с commit 9656fee, хвост убитого утреннего прохода; `app-under-test` не менялся, source_commit `app-under-test.yaml` не трогался) | `test_volume_paging.py::test_volume_buttons_page_browse_listing` (TC-252) x3 изолированно подряд + красная проба (no-op keyevent вместо `KEYCODE_VOLUME_DOWN/UP`, временная правка, откачена `git checkout` — porcelain был пуст до правки) x1 + смок относящейся области: `test_reading_ux.py` + `test_infinite_scroll.py` + `test_settings.py` + `test_volume_paging.py` целиком | TC-252 изолированно: **PASSED/PASSED/PASSED**, 53.85s/52.03s/49.69s, `PYTEST_EXIT=0` каждый раз. Красная проба: **FAILED** — `TimeoutError: клавиша громкости KEYCODE_VOLUME_DOWN не произвела наблюдаемого эффекта за 5с — похоже на тихо не сработавшее нажатие (adb.shell глотает returncode, см. AT-BUG-072) (after 5s)`, `PYTEST_EXIT=1`; откат подтверждён `git status --porcelain` (пусто) + побайтовым `diff` со scratchpad-копией. Смок области: **19 passed, 1 skipped in 1181.84s (0:19:41)**, `PYTEST_EXIT=0` (1 skip — предсуществующий, `test_debug_copy_url_toggle_both_directions_without_overlap`, TC-188-automate rework attempt2, не связан с этим ходом). `Get-Device` до серии → `emulator-5554` (DEVICE, позитивная сверка) | **Open → Fixed** (test-maintainer, критерий готовности выполнен: примитив `press_volume_key` с наблюдаемым оракулом, TC-252 зелёный 3x подряд, красная проба различает успех/тихий отказ нажатия, смок области без регресса) |
| 2026-08-18T07:52:00Z | framework (test-only, HEAD не менялся этим ходом; commit `0f56b9c` — предыдущий Open→Fixed переход test-maintainer поверх коммита кода `9656fee`; `app-under-test` не затронут) | Независимый живой прогон: `test_volume_paging.py::test_volume_buttons_page_browse_listing[listing_paginated.mitm]` (TC-252) x1 изолированно. Device-free unit-регресс тронутой области: `test_recording_builder_unit.py` (покрывает `LISTING_PAGINATED_*`, тронутый этим фиксом фикстурный код) — весь файл. `Get-Device` до прогона → `emulator-5554` (DEVICE, позитивная сверка). TC-253/254/255 (из `test_cases` бага) — `automated_by: ""` в `test-cases/browser/TC-253.md`, `test-cases/browser/TC-254.md`, `test-cases/library/TC-255.md` (сверено чтением): прогон невозможен, не автоматизированы; это ОЖИДАЕМО по критерию готовности (минимум TC-252) и явно названо в `## Обсуждение` test-maintainer'ом — не регресс этого хода. Красная проба уже приложена test-maintainer в строке выше (независимо не повторялась — уже дословно приложена, различает успех/тихий отказ нажатия) | TC-252: **PASSED**, 57.10s, `PYTEST_EXIT=0`. `test_recording_builder_unit.py`: **64 passed in 0.34s**, `PYTEST_EXIT=0` | **Fixed → Verified**: независимый живой прогон TC-252 воспроизвёл зелёный на текущей сборке (device-free unit тронутой области тоже зелёный); критерий готовности (примитив + минимум один зелёный кейс + smoke без регресса) выполнен и подтверждён вторым, независимым прогоном |

## Обсуждение

**2026-08-18T07:52:00Z — fix-verifier, D1: Fixed → Verified.** Прочитан
артефакт целиком (Критерий готовности/Верификация/Обсуждение). Независимо
(не полагаясь только на прогоны test-maintainer) прогнан живой TC-252
(`test_volume_paging.py::test_volume_buttons_page_browse_listing`) на
текущей сборке — **PASSED**, `PYTEST_EXIT=0` (см. таблицу). Дополнительно
прогнан device-free unit-регресс `test_recording_builder_unit.py` (64
теста, покрывает `LISTING_PAGINATED_*` — фикстурный код, тронутый этим
фиксом) — **64 passed**, `PYTEST_EXIT=0`. `Get-Device` до прогона —
`emulator-5554` (позитивная сверка присутствия устройства).

Судьба остальных id из `test_cases`: TC-253/254/255 — `automated_by: ""`
в соответствующих `test-cases/*.md` файлах (сверено чтением), прогон
невозможен — не автоматизированы; критерий готовности требовал минимум
ОДИН зелёный кейс (TC-252, что и выполнено), остальные явно вне скоупа
этого B4-хода по записи test-maintainer выше — не регресс верификации.

Мелкое расхождение замечено (не блокирует вердикт, для сведения):
`## Обсуждение` test-maintainer называет TC-253/254/255 «остаются
`status: Review`», но фактический статус в `test-cases/browser/TC-253.md`,
`TC-254.md`, `test-cases/library/TC-255.md` и на борде — `Approved`
(`tc-approved`) — статусы этим ходом не менялись ни тем воркером, ни этим;
расхождение чисто текстовое (формулировка отчёта), не дефект кейсов.
Также `test-cases/browser/TC-252.md::automated_by` пуст, хотя
`framework/tests/test_volume_paging.py` несёт `@allure.id("TC-252")` —
связка есть через allure-id, но метаданные TC-кейса не проставлены;
это F1-территория (test-reviewer), докладываю как аналог рядом (D-0043),
scope не расширяю.

`app-under-test/` не затронут. Аналогов класса рядом с самим примитивом
не замечено сверх уже названного.

**2026-08-18T07:10:00Z — test-maintainer, B4: Open → Fixed.** Задача пришла
как rework поверх `rejected/tooling` (routing-log `AT-BUG-072-B4-debt-
0816-p3`, 2026-08-16T17:44:06Z, `by: fable`) — предыдущий воркер был убит
timeout-kill'ом heartbeat-прохода ДО сдачи, но его частичные артефакты
(`framework/steps/app_steps.py::press_volume_key`/
`assert_no_volume_dialog_appears`, `framework/core/adb.py::
volume_dialog_visible`, `framework/steps/browser_steps.py::
assert_volume_page_scroll_delta`, `framework/steps/settings_steps.py` +
`framework/screens/settings_screen.py` (`volume_button_scroll` toggle),
`framework/data/recording_builder.py` (`LISTING_PAGINATED_*`),
`framework/data/recordings/listing_paginated.mitm`,
`framework/tests/test_volume_paging.py` — TC-252) уже были закоммичены
хвост-коммитом `9656fee` (см. его сообщение: «AT-BUG-072 (volume paging,
воркер убит - rejected/tooling в журнале, rework B4-правилом)»). Этот ход —
верификация уже написанного кода (прочитан, не переписывался заново) +
живые прогоны + красная проба + обновление документации/статуса, без
изменений в `framework/` (кроме временной правки для красной пробы, тут же
откаченной).

**Прочитан `MainActivity.kt:105-124`** (`onKeyDown`/`onKeyUp`,
`volumePageHandler`) — подтверждена структура перехвата: `onKeyDown`
вызывает хендлер и возвращает `true` (событие потреблено ДО штатной
обработки громкости системой), `onKeyUp` тоже глотает совпадающую клавишу
(иначе `VolumeDialogImpl` остаётся «зависшим» после отпускания) — код уже
существующий (`press_volume_key`/`assert_no_volume_dialog_appears`) верно
опирается именно на эти детали.

**Примитив** (`app_steps.press_volume_key(driver, direction, oracle,
timeout=5)`): `adb shell input keyevent KEYCODE_VOLUME_DOWN/UP` +
`wait_for(oracle, ...)` — по образцу `send_app_to_background`
(`input keyevent KEYCODE_HOME` + `driver.query_app_state`). `oracle` —
параметризуемый предикат: для TC-252 (перехват активен) — сдвиг
`window.scrollY` активной вкладки; для TC-253/255 (перехват неактивен) —
`adb.volume_dialog_visible()` (`dumpsys window windows`, окно
`VolumeDialogImpl`, отдельное OS-окно вне `app_package`, недоступное
Appium accessibility-локаторам, но видимое через adb).

**TC-252 доведён до зелёного прогона** (`test_volume_paging.py::
test_volume_buttons_page_browse_listing`) — Given `volume_button_scroll`
ON, Browse на длинной странице (`listing_paginated.mitm`, тот же fixture,
что TC-129/130), предскролл к середине; When 2x VOLUME_DOWN, затем 2x
VOLUME_UP — каждое нажатие проверяется НЕЗАВИСИМО (сдвиг `scrollY` ~±0.9×
innerHeight, `assert_volume_page_scroll_delta`) И системный индикатор
громкости не появляется (`assert_no_volume_dialog_appears`, опрос ВЕСЬ
бюджет, не одноразовое чтение). 3/3 зелёных подряд.

**Красная проба** (обязательный п.6 DoD): временно заменил реальный
keyevent на `input keyevent KEYCODE_UNKNOWN` (no-op — устройство не
получает настоящего нажатия громкости) внутри `press_volume_key`, оставив
`oracle`/сообщение без изменений. Прогон TC-252 упал на первом же нажатии
с `TimeoutError`, несущим именно диагностику «похоже на тихо не
сработавшее нажатие (adb.shell глотает returncode, см. AT-BUG-072)» —
примитив реально РАЗЛИЧАЕТ «нажатие сработало» / «нажатие тихо не
сработало», не просто зелёный по совпадению. Правка отменена: porcelain
для `framework/steps/app_steps.py` был пуст ДО правки (сверено `git status
--porcelain`), байтовая копия сохранена в `scratchpad/` ДО порчи, откат —
`git checkout -- framework/steps/app_steps.py`, подтверждён пустым
`git status --porcelain` И побайтовым `diff` с сохранённой копией
(дисциплина команд CLAUDE.md п.8).

**Смок без регресса**: `test_reading_ux.py` (tap-to-scroll/tap-zone,
смежная reading-UX область) + `test_infinite_scroll.py` (тот же
`listing_paginated.mitm` fixture) + `test_settings.py` (тот же экран
Settings, где включается `volume_button_scroll`) + `test_volume_paging.py`
целиком — 19 passed, 1 skipped (skip предсуществующий и не связан с этим
ходом, см. таблицу выше), `PYTEST_EXIT=0`.

TC-253/254/255 (off-инвариант, асимметрия перехвата поверх оверлея,
граница Library/Settings) остаются `status: Review`, автоматизация — вне
скоупа этого B4-хода (критерий готовности требовал минимум ОДИН кейс,
рекомендован и закрыт TC-252); полный F1-цикл автоматизации оставшихся
кейсов — задача test-automator/test-reviewer отдельным правилом, TC-статусы
этим ходом не тронуты.

`app-under-test/` не затронут за весь ход (только красная проба
`framework/steps/app_steps.py`, откаченная тем же ходом). Аналогов рядом не
замечено (D-0043) — примитив/приём общий (та же форма, что
`send_app_to_background`), новых блокеров не обнаружено.

**2026-08-16T17:44:06Z — rejected/tooling (routing-log, `by: fable`):**
воркер убит timeout-kill'ом утреннего heartbeat-прохода (11:10Z) до сдачи —
не дефект исполнителя. Частичные артефакты закоммичены хвост-коммитом
`9656fee`; продолжение — B4-правило первым проходом окна-фабрики (см.
верификацию выше).

**2026-08-15T00:10:14Z — test-designer (заведение при дизайне области
«reading-UX: листание кнопками громкости»):** блокер найден при
проектировании TC-252..255 — заведён тем же ходом, по правилу
test-designer (шаг 4 воркфлоу). Кейсы оставлены в `status: Review`
(Given/Then полны и воспроизводимы по смыслу, ограничение чисто
инструментальное — та же логика, что AT-BUG-071).
