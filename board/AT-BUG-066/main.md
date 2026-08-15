---
key: "AT-BUG-066"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "Персистентные системные настройки font_scale/night mode защищены только in-process try/finally — тот же класс остатка, что AT-BUG-064 (http_proxy)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-049", "test_case:TC-059", "test_case:TC-107", "test_case:TC-110", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T20:04:01Z"
updated: "2026-08-15T20:04:01Z"
archived: false
resolution: "done"
---

# Персистентные системные настройки font_scale/night mode защищены только in-process try/finally — тот же класс остатка, что AT-BUG-064 (http_proxy)

_Спроецировано из `bugs/AT-BUG-066.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-066 — font_scale/night mode: остаточная персистентная Android-настройка не покрыта fail-safe (класс AT-BUG-064)

## Суть долга

`AT-BUG-064` установил класс: тестовый фреймворк выставляет ПЕРСИСТЕНТНЫЕ
Android-`settings`, снимаемые ТОЛЬКО in-process `try/finally` — такая
настройка переживает hard-kill процесса/креш машины/снапшот, сохранённый в
неудачный момент, и остаётся выставленной на следующий прогон. Для
`http_proxy` это закрыто двухслойным фиксом ((а) fail-safe session-scope
проверка при старте прогона + перевзведение после device-liveness recovery,
(б) уже существующий in-process `try/finally`).

Тот же класс, БЕЗ слоя (а), обнаружен ещё в ДВУХ местах при рецензии
критика (правило 9 CLAUDE.md — «чини класс, а не экземпляр»).
[Поправка Lead 2026-08-12, находка F3 критик-входа: на момент заведения
этого файла оси «персистентный Android-settings-стейт» на карте
`SIBLING_MAP.md` НЕ существовало — утверждение было ложным; ось заведена
коммитом `7bd21cc` в OS-репо (под-ось Оси 6) 2026-08-12, теперь ссылка
валидна]:

1. **`framework/core/adb.py:179-186::set_font_scale()`** —
   `settings put system font_scale {scale}` (TC-107, `font_scale=1.3`).
   Защищён только `try/finally` в фикстуре `font_scale_1_3`
   (`framework/tests/test_accessibility.py:26-36`), восстанавливающей
   `1.0` (`DEFAULT_FONT_SCALE`).
2. **`framework/core/adb.py:173-176::set_night_mode()`** —
   `cmd uimode night yes/no` (TC-049 `test_settings.py:119-149`, TC-059
   `test_settings.py:364-412`, TC-110 `test_compatibility.py:109-149` —
   TC-059 добавлен поправкой Lead 2026-08-12, находка F5 критик-входа).
   Защищён только `try/finally` в самих телах тестов
   (`app_steps.set_system_dark_mode(False)` в `finally`).

   Замер критик-входа AT-BUG-064 (2026-08-11, живое устройство):
   `adb shell settings get secure ui_night_mode` → `1` — read-back у
   night mode СУЩЕСТВУЕТ (прежнее обоснование «нет очевидного механизма
   read-back» ослаблено: неизвестна только раскладка значений 0/1/2, не
   наличие источника — это удешевляет пункт 2 плана). Смежный класс
   (молчаливый no-op тех же adb-обёрток) — `bugs/AT-BUG-026.md:1290-1392`,
   named-not-covered остаток; не дубль (там no-op, здесь остаток
   персистентного стейта).

Если worker/сессия умирает МЕЖДУ `set_font_scale(1.3)`/`set_night_mode(True)`
и восстановительным вызовом (тот же класс, что описывал `AT-BUG-064` для
`http_proxy`) — следующий прогон стартует с увеличенным шрифтом/тёмной темой
ОС, ничего об этом не зная; тесты, чувствительные к системной теме/масштабу
(TC-049/107/108/110 и смежные UI-пробы), могут падать по НЕВЕРНОЙ причине
(«баг приложения», хотя фактически — грязное окружение).

## Почему не исправлено СРАЗУ в рамках AT-BUG-064

- **`font_scale`** — обобщение технически дёшево (та же форма `settings
  put/get system <key>`, «чистое» значение известно — `1.0`,
  `DEFAULT_FONT_SCALE` уже существует как константа), но требует НОВОЙ
  функции чтения (`adb.get_font_scale()`) и решения, куда её подключить
  (та же session-scope точка `_ensure_app_installed`, что `http_proxy`).
- **`night mode`** — обобщение НЕТРИВИАЛЬНО: `cmd uimode night yes/no` не
  имеет прямого симметричного `get`-аналога вида `settings get global
  http_proxy`; вероятный путь чтения — `settings get secure ui_night_mode`
  (не проверено на реальном устройстве в рамках этого долга) — риск
  прочитать/интерпретировать значение неверно (0=auto/1=no/2=yes — нужна
  верификация на живом эмуляторе) без отдельного расследования.
- Расширение скоупа диффа AT-BUG-064 (severity minor, класс уже закрыт для
  ГЛАВНОГО сценария заголовка — http_proxy) двумя новыми механизмами разной
  формы непропорционально прямо в rework-ходе с уже двумя блокерами (B1/B2)
  на приёмке; решение по правилу 9 CLAUDE.md — задокументировать класс и
  поставить в очередь, не молчать (в отличие от прежней ложной строки
  «сиблингов не найдено» в AT-BUG-064).

## Что сделать

1. `adb.get_font_scale()` (чтение `settings get system font_scale`) +
   fail-safe `ensure_default_font_scale()` (аналог
   `mitm.ensure_no_residual_proxy()`), подключить туда же
   (`conftest.py::_ensure_app_installed` + перевзведение после recovery,
   твин `_ensure_no_residual_device_proxy`).
2. Для night mode — сначала на живом устройстве проверить, что реально
   возвращает `settings get secure ui_night_mode` (или альтернативный
   источник истины) ДО написания fail-safe кода; при отсутствии надёжного
   способа прочитать текущее значение — рассмотреть безусловный сброс
   `night no` на старте сессии (дешевле, но НЕ идемпотентно логирует
   находку — компромисс для Lead/test-maintainer следующего захода).
3. Юнит-пробы по образцу `test_residual_proxy_guard_unit.py`.

## Остаток класса (D-0043, находка критика на приёмке этого фикса, 2026-08-13)

Тот же класс («персистентный Android-`settings`-стейт, выставляемый тестовой
инфраструктурой, защищённый только in-process `try/finally`, не переживающий
hard-kill/краш между установкой и восстановлением») имеет ещё ДВА
неохваченных сайта, не покрытых ни AT-BUG-064, ни этим фиксом:

1. **Ориентация экрана (TC-111).** `framework/steps/browser_steps.py:184-190`
   — `driver.orientation = orientation`; UiAutomator2 делает это через
   freezeRotation, что пишет `Settings.System.USER_ROTATION`/
   `ACCELEROMETER_ROTATION` (тот же namespace `system`, что `font_scale`).
   Хуже: `framework/tests/test_compatibility.py:156-228` — между
   `rotate(driver, "LANDSCAPE")` (:183) и `rotate(driver, "PORTRAIT")` (:215)
   стоят четыре ассерта, а `try/finally` НЕТ ВООБЩЕ — падение любого из них
   оставляет устройство в landscape даже без hard-kill (поток управления,
   не эмпирика). Требуемый живой замер персистентности (при поднятом
   эмуляторе, не сделан этим ходом): `settings get system user_rotation`/
   `accelerometer_rotation` до/после `rotate`.
2. **Яркость экрана (TC-169/TC-170).** `test-cases/settings/TC-169.md:31,71-74`
   и `TC-170.md:29,75` планируют `settings put system screen_brightness
   <0-255>` ДОСЛОВНО «по образцу `framework/core/adb.py::set_font_scale`/
   `set_night_mode`» — в `framework/` этого кода ещё нет; класс отрастёт на
   следующей автоматизации этих кейсов, если не подхвачен заранее.

**Архитектурная развилка (решение — за координатором должного яруса, не
test-maintainer в рамках этого узкого диспатча):** третья ad-hoc twin-пара
(`get_X`/`ensure_default_X`) не масштабируется — кандидат: обобщённый
`ensure_default_system_setting(key, default)` для namespace `system`,
переиспользуемый font_scale/orientation/brightness сразу. Альтернатива —
плодить twin-пары по образцу и дальше, дороже в сумме.

Носитель цели (правило 4б CLAUDE.md) — `docs/HANDOFF.md`, строка добавлена
тем же ходом.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов (`grep -l
      "font_scale\|night_mode\|uimode" bugs/AT-BUG-*.md` до создания этого
      файла → 0 совпадений вне этого файла).
- [x] Локации сверены чтением фактического кода (`adb.py:173-186`,
      `test_accessibility.py:26-36`, `test_settings.py:119-149`,
      `test_compatibility.py:109-149`), не спекуляция.
- [x] Severity обоснована: minor — тот же класс, что AT-BUG-064 (редкий
      случай, требует аварийного выхода на конкретном шаге), ручная
      ремедиация известна (`adb shell settings put system font_scale 1.0` /
      `adb shell cmd uimode night no`).

## Верификация

**fix-verifier (Sonnet), 2026-08-15.** `type: test_debt` — новая сборка
приложения не требуется (фикс целиком во фреймворке, `schemas/
transitions.yaml` комментарий к `Fixed->Verified`); версия сборки — коммит
фрейморка `44c5323` (2026-08-14 06:37:15+02:00, `-S"ensure_default_font_
scale"` подтверждает первое появление; `framework/core/adb.py`/`conftest.py`
прочитаны построчно ДО прогона — совпадают с `fixed_in` дословно: обе
twin-пары `get_font_scale/ensure_default_font_scale`,
`get_night_mode/ensure_default_night_mode`, обе точки подключения в
`conftest.py` присутствуют).

Двухслойная верификация (device-free юнит ОБЯЗАТЕЛЕН для test_debt в
юнитах + минимум один живой TC на реальном guard'е):

1. **Device-free юнит-слой.** Первый прогон воркера дал МОЙОБЕЙК (Windows
   cp866 рвёт кириллицу в выводе pytest) — воркер реконструировал текст
   предупреждения ПО ПАМЯТИ вместо приложения дословного вывода (нарушение
   D-0052, поймано критиком на приёмке). Ниже — независимый перепрогон
   критика той же канонической командой с `PYTHONIOENCODING=utf-8`
   (лекарство от мойобейка), дословно:
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -Command '$env:PYTHONIOENCODING="utf-8"; . D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_default_env_state_guard_unit.py -q'

   tests/test_default_env_state_guard_unit.py::test_hook_rechecks_default_env_state_after_recovery
     D:\AO3_tests\framework\tests\conftest.py:254: UserWarning: AT-BUG-026 device-liveness guard: устройство восстановлено 1/2
   28 passed, PYTEST_EXIT=0
   ```
2. **Device-слой, красная проба самого guard'а (не просто «TC прошёл»).**
   Эмулятор `emulator-5554` поднят канонично (`Get-Device` -> `DEVICE:
   emulator-5554`, Appium 4723 слушает). Критик испортил ОБЕ настройки
   разом и прогнал ОДИН изолирующий TC (`test_system_theme_follows_os_dark_mode`
   — тест сам не читает/не пишет ни `font_scale`, ни `night_mode` напрямую;
   обе проверки guard'а стоят в session-setup ДО тела теста, поэтому
   атрибуция чище, чем воркеровский вариант с двумя раздельными прогонами)
   — дословный перепрогон критика:
   ```
   PRE:  font_scale=1.0, night=no
   CORRUPTED: settings put system font_scale 1.3; cmd uimode night yes
   CORRUPTED: font_scale=1.3, night=yes

   powershell -NoProfile -ExecutionPolicy Bypass -Command '$env:PYTHONIOENCODING="utf-8"; . D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_settings.py::test_system_theme_follows_os_dark_mode -q'

   tests/test_settings.py::test_system_theme_follows_os_dark_mode
     D:\AO3_tests\framework\tests\conftest.py:84: UserWarning: AT-BUG-066: остаточный font_scale='1.3' обнаружен на старте прогона (пережил рестарт эмулятора или аварийное завершение предыдущей сессии/worker'а) -- сброшен автоматически в 1.0.
     D:\AO3_tests\framework\tests\conftest.py:102: UserWarning: AT-BUG-066: остаточный night mode='yes' обнаружен на старте прогона (пережил рестарт эмулятора или аварийное завершение предыдущей сессии/worker'а) -- сброшен автоматически в 'no'.
   1 passed, 2 warnings in 35.49s
   PYTEST_EXIT=0

   POST: font_scale=1.0, night=no (== PRE, устройство возвращено)
   ```
   Guard фактически сработал на ОБЕИХ настройках (предупреждения называют
   AT-BUG-066 и старые грязные значения дословно), а не тест случайно
   сошёлся — воркеровский изначальный дизайн (два раздельных изолирующих
   TC, TC-049 на font_scale/TC-107 на night_mode) методологически тоже
   верен, критик объединил их в один прогон для собственной независимой
   проверки.
   - **TC-059**/**TC-110** — не прогнаны отдельным device-запуском ни
     воркером, ни критиком: оба используют ТУ ЖЕ единственную точку
     подключения guard'а (session-scoped `_ensure_app_installed`), уже
     дважды подтверждённую живым срабатыванием выше. Названо явно, не
     молчаливый пропуск; критик явно принимает это сокращение.
   - **Остаточный риск, не закрытый ни одним прогоном:** сквозной путь
     «реальный перезапуск эмулятора → перевзведение вторым hook'ом
     (`pytest_runtest_setup` после device-liveness recovery)» живьём не
     гонялся (дорого/разрушительно) — только device-free с monkeypatched
     adb в юнит-слое (настоящий hook, настоящая ветка кода, поддельный
     `subprocess.run`). Помечено как открытый остаток, не блокер Verified.
   - **Смежный, уже названный класс:** `set_font_scale`/`set_night_mode`
     идут через `adb.shell()`, который отбрасывает returncode — провалившийся
     `settings put` дал бы то же «сброшено» предупреждение без реального
     сброса. Не новый — см. `bugs/AT-BUG-026.md:1290-1392` (named-not-covered),
     направление fail-safe безопасное (исключение не летит).

| Дата | Сборка (framework) | TC | Результат |
|---|---|---|---|
| 2026-08-15 | commit `44c5323` (2026-08-14) | unit: `test_default_env_state_guard_unit.py` (28 проб) | 28 passed, PYTEST_EXIT=0 (перепрогон критика, дословно) |
| 2026-08-15 | commit `44c5323` (2026-08-14) | TC-049-класс тест, font_scale+night_mode corrupted pre-run (объединённая проба критика) | 1 passed, 2 guard warnings дословно (см. блок выше), post-run font_scale=1.0/night=no, PYTEST_EXIT=0 |
| 2026-08-15 | commit `44c5323` (2026-08-14) | TC-059, TC-110 | не прогнаны отдельно — та же единственная точка подключения guard'а, уже дважды device-verified выше (см. обоснование) |

**Приёмка (basis=critic):** первая версия этой секции несла РЕКОНСТРУИРОВАННЫЙ
(не дословный) текст предупреждений — критик поймал расхождение перепрогоном
той же канонической команды (мойобейк cp866 без `PYTHONIOENCODING=utf-8`
объясняет, откуда взялась реконструкция). Существо фикса при этом
подтверждено независимо и живьём — критик не рекомендовал откат
`Verified → Fixed`, только замену witness-блоков на дословные (сделано этим
ходом координатором). Соседний экземпляр того же класса (реконструированный
witness) найден и в `bugs/AT-BUG-064.md:394-405` — вне скоупа этого файла,
доложен отдельно.

**Вердикт: Verified.** DoD (1)/(2)/(3) из fixed_in построчно сверены чтением
кода и подтверждены исполнением (не пересказом): обе twin-пары в
`adb.py` fail-safe (юнит-набор кроет ненулевой returncode/TimeoutExpired),
обе точки подключения в `conftest.py` реальны и живьём ловят/чинят
инъецированную порчу настройки на старте сессии, 28/28 юнитов зелёные.
Дефектов-собратьев новых не замечено сверх уже названных в «Остаток
класса» (ориентация/яркость — вне скоупа этого узкого диспатча, владение
за координатором, ссылка уже стоит в файле).

## Обсуждение

**test-maintainer, 2026-08-11.** Заведён по прямому указанию критика
(критик-вход AT-BUG-064 rework attempt 2, блокер B1): секция «Сиблинги»
AT-BUG-064 ложно утверждала «других мест того же класса не найдено» —
форма грепа (`settings put global\|settings get global`) структурно не
могла найти `settings put SYSTEM ...`/`cmd uimode ...` (другой namespace,
другая команда). Обе локации подтверждены прямым чтением исходников
(не спекуляция). Решение — задокументировать честно и завести долг, а не
расширять скоуп диффа AT-BUG-064 непропорционально (обоснование — секция
выше). Ссылка проставлена в `bugs/AT-BUG-064.md` (секция «Сиблинги»).

**test-maintainer, 2026-08-13/14 (B4, живой замер ДО реализации фикса night
mode).** Эмулятор поднят канонично (`Start-Emulator -WritableSystem` →
`Get-Device` → `DEVICE: emulator-5554`). Дословный вывод:

```
--- initial ui_night_mode ---
1
--- cmd uimode night (no arg, query) ---
Night mode: no
--- set night yes ---
Night mode: yes
--- ui_night_mode after yes ---
2
--- cmd uimode night query after yes ---
Night mode: yes
--- set night no ---
Night mode: no
--- ui_night_mode after no ---
1
--- cmd uimode night query after no ---
Night mode: no
--- try auto ---
Night mode: auto
Night mode: auto
```

Находка: `cmd uimode night` БЕЗ аргумента — режим ЗАПРОСА, не только
установки (симметричный `cmd uimode night yes/no`), и печатает
человекочитаемый `Night mode: no/yes/auto`. Это НАДЁЖНЕЕ и ПРОЩЕ, чем
`settings get secure ui_night_mode` (раскладка подтверждена частично:
`no`->`"1"`, `yes`->`"2"`, `auto` напрямую не измерялся — не входит в
критик-вход AT-BUG-064, который видел только `"1"`). Решение: **read-back
через `cmd uimode night` (запрос), НЕ через `settings get secure
ui_night_mode`** — снимает саму необходимость знать раскладку 0/1/2 целиком
(симметричный источник истины команде установки). Компромисс «безусловный
сброс `night no` на старте сессии» из плана НЕ понадобился — идемпотентный
read-back с логированием находки оказался доступен без доп. расследования.
`adb.get_night_mode()`/`adb.ensure_default_night_mode()` реализованы на
основе этого замера; устройство возвращено в чистое состояние (`night no`,
`font_scale 1.0`) после замера, ДО начала правки кода.

**test-maintainer, 2026-08-13/14 (B4, приёмка).** Оба фикса реализованы
(`adb.py`, `conftest.py`), новый device-free юнит-набор
`test_default_env_state_guard_unit.py` (28 проб) зелёный 3 раза подряд;
красная проба (откат `set_font_scale(DEFAULT_FONT_SCALE)` в
`ensure_default_font_scale()`) поймала регресс (`1 failed` вместо `28
passed`) — байтовый откат подтверждён `cmp` (правило 8 CLAUDE.md). Полный
`_unit`-набор (276 тестов) зелёный без регрессий; `scripts/tests` (1124
passed) и `validate_frontmatter.py` (0 ошибок/предупреждений) тоже.

Замеченный аналог (НЕ новый блокер, доклад без расширения скоупа — правило
9 CLAUDE.md): `test_device_liveness_guard_unit.py::
test_hook_calls_guard_when_driver_in_fixturenames` (владение —
AT-BUG-026/063, не в скоупе этого хода) уже ДО этого фикса симулировал
device-liveness recovery и вызывал РЕАЛЬНЫЙ `_ensure_no_residual_device_
proxy()` без монки-патча (сквозной вызов настоящего adb, если эмулятор
поднят) — B2-твин этого хода добавил туда ЕЩЁ два таких же сквозных вызова
(`_ensure_default_font_scale`/`_ensure_default_night_mode`). Не регрессия:
обе новые функции fail-safe по тому же контракту, что уже принятый
`get_device_proxy()` (ненулевой/отсутствующий adb -> `None` +
предупреждение в stderr, не исключение) — тест остаётся зелёным что с
устройством, что без него; полный `_unit`-прогон это подтвердил (276
passed). Названо на приёмке для видимости класса, чинить в этом файле не
берусь (владение путями этого хода не включает `test_device_liveness_guard_
unit.py`).
