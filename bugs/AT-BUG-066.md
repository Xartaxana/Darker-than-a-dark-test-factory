---
id: AT-BUG-066            # test_debt, сквозная нумерация с BUG-xxx
title: "Персистентные системные настройки font_scale/night mode защищены только in-process try/finally — тот же класс остатка, что AT-BUG-064 (http_proxy)"
type: test_debt
debt_kind: broken_environment
severity: minor
status: Open
found_in: "test-maintainer (Sonnet), 2026-08-11, B4 rework AT-BUG-064 attempt 2 — найдено критиком по правилу 9 CLAUDE.md (класс, не экземпляр) при проверке секции «Сиблинги» AT-BUG-064."
last_seen_in: ""
test_cases: ["TC-049", "TC-107", "TC-110"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-11T17:35:00Z"
updated: "2026-08-11T17:35:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

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
критика (правило 9 CLAUDE.md — «чини класс, а не экземпляр», карта
`SIBLING_MAP.md` внутренней оси AO3 «персистентный Android-`settings`-стейт,
выставляемый обвязкой»):

1. **`framework/core/adb.py:179-186::set_font_scale()`** —
   `settings put system font_scale {scale}` (TC-107, `font_scale=1.3`).
   Защищён только `try/finally` в фикстуре `font_scale_1_3`
   (`framework/tests/test_accessibility.py:26-36`), восстанавливающей
   `1.0` (`DEFAULT_FONT_SCALE`).
2. **`framework/core/adb.py:173-176::set_night_mode()`** —
   `cmd uimode night yes/no` (TC-049 `test_settings.py:119-149`, TC-110
   `test_compatibility.py:109-149`). Защищён только `try/finally`
   в самих телах тестов (`app_steps.set_system_dark_mode(False)` в
   `finally`).

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
