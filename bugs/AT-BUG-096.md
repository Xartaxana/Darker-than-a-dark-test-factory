---
id: AT-BUG-096
title: "framework/web/base_page.py::contrast_of() передаёт WebElement аргументом в execute_script — на стеке 2 (ao3_test_api29, chromedriver=74.0.3729.6/chrome=74.0.3729.185) getComputedStyle получает НЕ Element (`parameter 1 is not of type 'Element'`), блокирует TC-149 ДО оракула"
type: test_debt
debt_kind: broken_environment
severity: major
status: Fixed
found_in: "test-automator, TC-149 attempt 3 (стабилизация на стеке 2, после фикса AT-BUG-095/DEVICE_BINDING_MISMATCH), стек 2 (emulator-5556, ao3_test_api29), Appium :4725, APK dev-local vc12, 2026-08-21"
fixed_in: "test-automator (Sonnet), 2026-08-21: `framework/web/base_page.py::contrast_of()` переписан на приём CSS-селектора (строка) вместо `WebElement`; `_CONTRAST_OF_ELEMENT_JS` резолвит узел ВНУТРИ инжектированного скрипта через `document.querySelector(arguments[0])` (кидает `Error` с текстом селектора, если querySelector нашёл 0 узлов — вместо молчаливого прохода дальше). Вызывающие места (`listing_page.py::rate_button_contrast/note_button_contrast`, `work_page.py::title_contrast/body_paragraph_contrast`) переданы селекторами (`wait_css(selector)` для ожидания рендера + `contrast_of(selector)`) вместо уже найденного `WebElement`. Формула контраста (getComputedStyle color/эффективный background, подъём по родителям) НЕ менялась. Живой прогон TC-149 (`Invoke-Pytest tests/test_accessibility.py -k test_computed_contrast_holds_wcag_threshold_light_and_dark`) на стеке 2 (`emulator-5556`, `chromedriver=74.0.3729.6`) дважды подряд дошёл до первого Then-ассерта — `JavascriptException` (`parameter 1 is not of type 'Element'`) больше НЕ возникает, симптом устранён; регресс на стеке 1 (api34) — TC-149 остаётся единственным потребителем `contrast_of`, паттерн `execute_script(script, element)` в остальном фреймворке отсутствовал (см. Grep-сверку в разделе «Обсуждение» ниже) — регрессировать было нечему."
last_seen_in: ""
test_cases: ["TC-149"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-21T12:51:45Z"
updated: "2026-08-21T12:51:45Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: environment
lock: ""
gitlab_issue: ""
---

# AT-BUG-096 — `contrast_of()` передаёт `WebElement` аргументом в `execute_script` — на chromedriver=74 (стек 2, api29) `getComputedStyle` получает не-Element, TC-149 падает ДО оракула

## Окружение

- Стек 2: `emulator-5556` (AVD `ao3_test_api29`), Appium `:4725`, APK
  dev-local versionCode 12. WebView `chrome=74.0.3729.185`,
  `chromedriver=74.0.3729.6` (тот же образ, что успешно прошёл TC-109,
  `bugs/AT-BUG-028.md`, — базовая навигация/interaction на этом chromedriver
  работает, проблема специфична для конкретного паттерна вызова ниже).
- Поверхность: `framework/web/base_page.py::contrast_of()` (:95-100),
  вызывается из `listing_page.py::rate_button_contrast/note_button_contrast`
  (:98-107) и `work_page.py::title_contrast`/тело (:29-39) — единственный
  путь вычисления WCAG-контраста в кейсе TC-149.
- Это ПЕРВЫЙ реальный прогон TC-149 на api29 (два предыдущих attempt
  блокировались раньше: DEVICE_BINDING_MISMATCH на чужом устройстве,
  затем `AT-BUG-095` — оба сняты до этого прогона).

## Суть долга

`contrast_of()` передаёт уже найденный Selenium/Appium `WebElement` вторым
аргументом в `execute_script`, ожидая, что внутри инжектированного JS
`arguments[0]` будет реальным DOM `Element`:

```python
# framework/web/base_page.py:95-100
def contrast_of(self, element) -> dict:
    return self.driver.execute_script(self._CONTRAST_OF_ELEMENT_JS, element)
```

```js
// _CONTRAST_OF_ELEMENT_JS, :70-71
var el = arguments[0];
var cs = window.getComputedStyle(el);
```

На стеке 1 (api34, более новый chromedriver) этот паттерн — стандартный
Selenium-приём (клиент сериализует `WebElement` по W3C-схеме
`element-6066-11e4-a52e-4f735466cecf`, chromedriver резолвит её в реальный
DOM-узел перед инъекцией `arguments[0]`). На стеке 2 chromedriver 74
(2019, ранняя эпоха W3C-протокола в Chrome/chromedriver) резолвит объект
некорректно — `arguments[0]` внутри инжектированного скрипта НЕ является
`Element`, и браузерный `getComputedStyle` бросает `TypeError`:

Дословная сигнатура (идентична в ДВУХ прогонах подряд, `attempt 3`, оба
на `emulator-5556`):

```
selenium.common.exceptions.JavascriptException: Message: javascript error: Failed to execute 'getComputedStyle' on 'Window': parameter 1 is not of type 'Element'.
  (Session info: chrome=74.0.3729.185)
  (Driver info: chromedriver=74.0.3729.6 (255758eccf3d244491b8a1317aa76e1ce10d57e9-refs/branch-heads/3729@{#29}),platform=Windows NT 10.0.26200 x86_64)
```

Оба прогона падают на ОДНОЙ и той же точке — первый вызов
`measure_listing_badge_contrast` -> `rate_button_contrast` ->
`contrast_of` -> `execute_script` (`tests/test_accessibility.py:307` ->
`steps/a11y_steps.py:350` -> `web/listing_page.py:102` ->
`web/base_page.py:100`), ДО первого Then-ассерта
(`assert_all_nodes_meet_contrast_threshold`, TC-149.md Then) — красный ДО
оракула, не флейк порогового значения контраста.

## Влияние

Блокирует TC-149 (единственный на данный момент кейс, использующий
`contrast_of`) на стеке 2 целиком — Given/When/Then кейса корректны, код
теста написан и стабилен (2/2 идентичных прогона), но оракул физически не
достижим на этом chromedriver. Класс шире одного кейса: ЛЮБОЙ будущий
тест, передающий `WebElement` аргументом в `execute_script` на стеке 2,
получит тот же симптом (сиблинг-риск, правило 9 CLAUDE.md) — на момент
завода это единственная поверхность в `framework/web/`
(`Grep -n "execute_script" framework/web framework/steps` — совпадения
только в `base_page.py::bridge_marker_present` (без element-аргумента,
не затронут) и `base_page.py::contrast_of`).

## Направление фикса (не диспатчу сам — решение о диспатче за Lead, D-0037)

`_CONTRAST_OF_ELEMENT_JS` можно переписать на приём CSS-селектора
(строка) вместо `WebElement` и резолвить узел ВНУТРИ инжектированного
скрипта через `document.querySelector(selector)` — тогда через границу
Appium/chromedriver уходит только примитив (строка), а не сериализованная
ссылка на элемент, которую chromedriver 74, по всей видимости, резолвит
некорректно. Потребует правки сигнатуры `contrast_of()` и всех четырёх
вызывающих мест (`listing_page.py::rate_button_contrast/
note_button_contrast`, `work_page.py::title_contrast`/тело) — сейчас они
передают уже найденный `wait_css`/`rate_button` элемент, а не селектор;
альтернатива — оставить текущий локатор-объект, но внутри `contrast_of`
доставать `id`/уникальный атрибут и строить `querySelector` по нему
(вариант обсуждения, не решение). Регресс на стеке 1 (api34, новый
chromedriver) проверить обязательно — паттерн `execute_script(script,
element)` используется ТОЛЬКО в этом кейсе, ретеста существующих зелёных
кейсов не требует, но живой прогон TC-149 на api34 остаётся частью
критерия готовности ниже.

## Критерий готовности (Fixed)

- `contrast_of()` (или её вызывающие места) вычисляет WCAG-контраст узла
  БЕЗ передачи `WebElement` аргументом в `execute_script` (либо иначе
  устраняет причину `parameter 1 is not of type 'Element'` на
  chromedriver 74) — конкретный механизм на усмотрение реализующего,
  критерий — устранение симптома, не конкретный API.
- Живой прогон TC-149 (`@pytest.mark.replay`) на стеке 2 (api29,
  `emulator-5556`) доходит минимум до первого Then-ассерта
  (`assert_all_nodes_meet_contrast_threshold`) — оракул физически
  достижим (независимо от того, зелёный он или ловит реальный
  контраст-дефект).
- Регресс на стеке 1 (api34) — существующее покрытие `contrast_of` (пока
  единственный потребитель — TC-149) остаётся зелёным на новом коде.

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-21 | dev-local vc12, стек 2 (emulator-5556, chromedriver=74.0.3729.6) | TC-149 (2 прогона подряд) | Оба прогона дошли до первого Then-ассерта (`assert_all_nodes_meet_contrast_threshold`) — `JavascriptException` не возникает; кейс красный на самом оракуле (2/8 узлов ниже WCAG-порога, идентично 2/2 — см. `test-cases/accessibility/TC-149.md`), не на исключении | Симптом AT-BUG-096 устранён — оракул физически достижим |

## Обсуждение

**[test-automator @ 2026-08-21T00:00:00Z]** Заведён на TC-149 attempt 3
(стек 2, после фикса DEVICE_BINDING_MISMATCH коммитом 4a3605c7 и
AT-BUG-095 CA-чека) — первый реальный прогон теста на api29. Живой
witness bound `deviceUDID=emulator-5556` (гвардия
`DEVICE_BINDING_MISMATCH` не сработала — устройство корректное), CA
установлен (`AT-BUG-095` фикс подтверждён на этом же прогоне — фикстура
`replay` прошла setup чисто, `RuntimeError` о CA не возник). Два подряд
прогона (`Invoke-Pytest tests/test_accessibility.py -k
test_computed_contrast_holds_wcag_threshold_light_and_dark`) дали
ИДЕНТИЧНУЮ сигнатуру: та же строка кода, та же JS-ошибка, тот же
`chrome=74.0.3729.185`/`chromedriver=74.0.3729.6`. Красный ДО оракула
(первый Then-ассерт `assert_all_nodes_meet_contrast_threshold` не
достигнут) — по протоколу диспатча (DoD п.4) обходы в тесте не
применялись, воркароунд НЕ реализован, только диагностика и направление
фикса. Дубликаты проверены (`Grep bugs/` по `chromedriver|getComputedStyle|
execute_script.*element|not of type`) — совпадений не найдено, это первый
экземпляр класса. `AT-BUG-028`/`AT-BUG-095` — соседние блокеры того же
стека, но другого слоя (chromedriver-совместимость AVD целиком / CA-чек),
не дублируют этот (специфичен для передачи `WebElement` аргументом в
`execute_script`, а не для самой возможности запускать JS в WebView —
`bridge_marker_present()`, JS без element-аргумента, работает штатно на
этом же стеке в других кейсах).

TC-149.md остаётся `Approved`, `automated_by` пуст — блокер снят фиксом
AT-BUG-095/4a3605c7, но упёрся в НОВЫЙ (этот). Кейс — не test_debt самой
оракульной части (Given/When/Then корректны, тест написан), долг —
именно в реализации `contrast_of()` под chromedriver 74.

**[test-automator @ 2026-08-21T12:51:45Z]** Фикс реализован по направлению
из раздела выше: `contrast_of()` (`framework/web/base_page.py`) принимает
CSS-селектор (строку) вместо `WebElement`, узел резолвится ВНУТРИ
инжектированного скрипта через `document.querySelector`. Правки:
`base_page.py::contrast_of`/`_CONTRAST_OF_ELEMENT_JS` (сигнатура + резолв
узла), `listing_page.py::rate_button_contrast/note_button_contrast`
(строят тот же селектор, что уже используют `rate_button`/`note_button`,
ждут рендер `wait_css(selector)`, передают селектор), `work_page.py::
title_contrast/body_paragraph_contrast` (аналогично, селекторы уже были
строками — просто убрана лишняя обёртка в `WebElement`). Формула контраста
не менялась. `python scripts/arch_check.py` — 0 ошибок (только
предсуществующие warnings, к этой цепочке не относятся); `python -m
py_compile` трёх файлов — чисто.

Живой прогон (`Invoke-Pytest tests/test_accessibility.py -k
test_computed_contrast_holds_wcag_threshold_light_and_dark`, стек 2 —
`Use-DeviceStack -N 2` + `Invoke-Pytest` в ОДНОМ вызове, иначе
`AO3_DEVICE`/`APPIUM_URL` не наследуются между отдельными процессами
PowerShell и прогон молча уходит на дефолтный стек 1): 2/2 подряд —
`JavascriptException` НЕ возникает, оба прогона доходят до первого
Then-ассерта. Оракул на живом стеке 2 находит РЕАЛЬНЫЙ контраст-дефект
(стабильно 2/2, идентичные ratio/color/effective_bg):

```
листинг×Dark: Rate-бейдж (data-ao3-rate-btn): ratio=1.32 (порог 4.5) color=rgb(0, 0, 0) effective_bg=rgba(42, 32, 24, 1) fontSize=13.3px bold=False large=False
листинг×Dark: Note-кнопка (data-ao3-note-btn): ratio=1.49 (порог 4.5) color=rgb(0, 0, 0) effective_bg=rgba(50, 41, 43, 1) fontSize=13.3px bold=False large=False
```

Остальные 6/8 узлов держат порог (Light/Dark work-страница, Light
листинг). Похоже на реальный продуктовый дефект: инжектированные
Rate/Note-инлайновые цвета (`ao3_bridge.js` BADGE-палитра) не меняются
при переключении темы, а engine-level Force Dark стека 2
(`chromedriver=74.0.3729.6`/старый WebView) частично затемняет ТОЛЬКО
явный inline `background-color`, оставляя тёмный fg-текст нетронутым —
даёт near-black-on-near-black. Это НЕ находка этого test_debt-тикета
(вне мандата test-automator заводить продуктовые баги) — оставлено
триажу/bug-reporter по обычному вердикту приёмки.

Grep-сверка сиблингов (`execute_script.*element`-паттерн, критерий п.6
диспатча): `Grep -n "execute_script" framework/web framework/steps` —
единственные совпадения: `base_page.py::bridge_marker_present` (без
element-аргумента, не затронут) и уже починенный `contrast_of`. Других
мест, передающих `WebElement` аргументом в `execute_script`, в
`framework/web`/`framework/steps` НЕТ — класс закрыт полностью, не
только для TC-149.

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* (`chromedriver`,
      `getComputedStyle`, `execute_script.*element`, `not of type`) — не
      найдено
- [x] Точная дословная JS-сигнатура ошибки приложена (идентична 2/2
      прогонов)
- [x] Severity обоснована — major: блокирует единственный существующий
      потребитель (`contrast_of`, TC-149) на целом стеке, риск шире при
      появлении новых execute_script(element)-паттернов
- [x] Направление фикса приложено (querySelector внутри скрипта вместо
      WebElement-аргумента) — вариант, не диктат реализации
- [x] Ни одного изменения в `framework/`/`app-under-test/` этим тикетом
      не внесено — только диагностика двух живых прогонов
- [x] `type: test_debt`, `debt_kind: broken_environment` — специфично для
      chromedriver 74 образа стека 2, не для логики теста/кейса
- [x] Лок не нужен (баг Open, никто не начал фикс)
