---
key: "AT-BUG-094"
project: "AO3"
issueType: "bug"
status: "bug-rejected"
priority: "p1"
summary: "Стек 2 (ao3_test_api29): rating_steps.open_work_page → open_deep_link(HOME) Given-паттерн не обновляет tabs[0].url в приложении — TabStrip никогда не появляется, блокирует live-автоматизацию TC-150 (и потенциально TC-106/TC-148/др. с тем же Given на этом стеке)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-150", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-21T11:00:00Z"
updated: "2026-08-21T11:00:00Z"
archived: false
resolution: null
---

# Стек 2 (ao3_test_api29): rating_steps.open_work_page → open_deep_link(HOME) Given-паттерн не обновляет tabs[0].url в приложении — TabStrip никогда не появляется, блокирует live-автоматизацию TC-150 (и потенциально TC-106/TC-148/др. с тем же Given на этом стеке)

_Спроецировано из `bugs/AT-BUG-094.md` (источник правды).
Статус в нашей машине: **Rejected**._

# AT-BUG-094 — стек 2 (api29): `open_work_page` → `open_deep_link(HOME)` не обновляет `tabs[0].url`, TabStrip не появляется

## Окружение

- Стек 2: `emulator-5556` (AVD `ao3_test_api29`, Chrome/WebView 74.0.3729.185 —
  см. `bugs/AT-BUG-028.md`), Appium `:4725`, APK dev-local versionCode 12.
- `Test-AppiumHealthy -Deep` на `:4725` — сессия создаётся/удаляется с 1-й
  попытки (среда как таковая здорова, это НЕ вход в правило «Fail-fast
  среды» docs/06 §5 — класс исключения там `ReadTimeoutError`/`TimeoutError`,
  здесь честный `AssertionError` на детерминированно воспроизводимом
  расхождении состояния).
- Поверхность: `framework/steps/rating_steps.py::open_work_page` →
  `framework/screens/browser_screen.py::open_work()` (навигация WebView через
  `driver.get()`/`framework/core/navigate.py`, ожидание маркера
  `window.__ao3AppDark`) → `framework/steps/app_steps.py::open_deep_link` →
  `framework/steps/browser_steps.py::assert_tab_strip_visible`. Тот же Given
  использует `framework/tests/test_accessibility.py::
  test_key_controls_have_accessible_label_or_text` (TC-106, уже
  `status: Automated`) и `test_native_chrome_touch_targets_at_least_48dp`
  (TC-148, уже `status: Automated`) — оба валидированы (судя по `automated_by`
  и отсутствию карантина) на стеке 1 (api34), НЕ на стеке 2.

## Суть долга

Given TC-150/TC-106 (буквально идентичный код во всех трёх тестах модуля):

```python
app_steps.wait_app_ready(driver)
rating_steps.open_work_page(driver, work.ao3_id)
app_steps.open_deep_link(browser_steps.HOME_URL)
browser_steps.assert_tab_strip_visible(driver, timeout=10)
```

На стеке 2 `assert_tab_strip_visible` падает **100% воспроизводимо** (3/3
прогона TC-150, 1/1 TC-106) — `TabStrip` никогда не появляется, даже с
увеличенным таймаутом (диагностический прогон с `timeout=30` — тот же
результат за полный бюджет, что исключает простую задержку/гонку по
времени).

**Root-cause (диагностирован живыми прогонами, не гипотеза).**
`BrowserViewModel.openOrNavigateDeepLink` (app-under-test,
`ui/browser/BrowserViewModel.kt:816-823`):

```kotlin
fun openOrNavigateDeepLink(url: String) {
    val state = _uiState.value
    if (state.tabs.size == 1 && state.tabs[0].url == HOME_URL) {
        navigateActiveTabTo(url)   // ← фактически происходит на стеке 2
    } else {
        openTab(url, background = false)   // ← ожидается (добавление вкладки)
    }
}
```

Ветка `navigateActiveTabTo` (навигация НА МЕСТЕ, вкладка НЕ добавляется, счёт
остаётся 1) срабатывает потому, что `state.tabs[0].url` **всё ещё равен
`HOME_URL`** в момент вызова — то есть предшествующая навигация
`rating_steps.open_work_page` НЕ обновила состояние `BrowserViewModel`,
несмотря на то, что WebView **реально** отобразил целевую страницу.

**Контролируемый эксперимент (2 прогона, ОБА с `clean_app` — гарантированно
чистое однотабное состояние на старте, а не унаследованное от предыдущего
прогона):**

| Сценарий | `current_url`/`document.title` после `open_work_page` | Сентинел `works/<id>` в `ao3_settings.xml` (опрос 10с) | Счёт вкладок после `open_deep_link(HOME)` |
|---|---|---|---|
| Синтетический фикстурный id `900000001` (заведомо 404 — см. докстринг `conftest.py::placeholder_seeded_work`: «для синтетических ao3_id... скрейп вернёт пустые поля») | `https://archiveofourown.org/works/900000001`, `«404 Error \| Archive of Our Own»` (настоящий шаблон 404 AO3, не Cloudflare) | **Не появился** (`TimeoutError` после 10с) | **1** (осталась одна вкладка — `navigateActiveTabTo` сработал) |
| РЕАЛЬНАЯ, живая на момент прогона работа (скрейплена с `/works`, id `90451726`), полностью догрузилась | `https://archiveofourown.org/works/90451726/chapters/240485331`, реальный заголовок главы (`My Love My Life - Chapter 1 - ...`) | **Не появился** (`TimeoutError` после 10с) | **1** (та же ветка) |

Оба контролируемых прогона дали **идентичный** результат независимо от
404-vs-200 содержимого страницы — это исключает гипотезу «маршрут ломается
только для 404-фикстуры». `onPageLoaded(tabId, url)`
(`BrowserViewModel.kt:636-661`) вызывается СИНХРОННО из
`WebViewClient.onPageFinished` (`BrowserScreen.kt:645-664`) ДО инъекции
маркера `window.__ao3AppDark` (строка 670) — то есть по коду ожидается, что
маркер появляется ПОСЛЕ обновления `tabs[0].url`; на стеке 2 это наблюдаемо
НЕ так (маркер появляется, `tabs[0].url` — нет). Точный механизм расхождения
(WebViewClient.onPageFinished не долетает до `onPageLoaded` на этой сборке
WebView 74 / другой tabId в замыкании / иное) НЕ дочерчен до конца —
дальнейшая диагностика требует чтения/инструментирования кода приложения
(`app-under-test/`), что вне мандата test-automator.

**Побочное наблюдение (не путать с причиной, честно отмечено — не incident,
для осторожности будущих live-диагностик на этом стеке).** Один
неконтролируемый диагностический прогон ПОЗЖЕ в этой же сессии (навигация на
`/works` после уже ~8 живых запросов к archiveofourown.org за 20 минут)
получил `document.title == "Just a moment..."` — Cloudflare-интерстишл
(рейт-лимит/бот-чек, см. `app-under-test/CLAUDE.md` «Testing — never load
AO3»). Это НЕ объясняет два контролируемых прогона таблицы выше (у обоих —
подтверждённо РЕАЛЬНЫЙ, не Cloudflare-контент), но означает, что дальнейшие
live-диагностики этого класса стоит вести экономно (пауза между прогонами/
использовать replay, где возможно), чтобы не усугублять троттлинг для всей
фабрики.

## Влияние

Блокирует стабильную (2+ зелёных подряд) live-автоматизацию TC-150 на стеке 2
(api29) — задача, ради которой это расследование велось. Тот же Given-паттерн
используют TC-106 и TC-148 (`status: Automated`, `automated_by` уже
заполнен) — их `automated_by`-статус НЕ переоткрывается этим багом (они
валидированы на стеке 1/api34, где паттерн, по всем признакам, работает
штатно — ни разу не пойман сбойным в их истории); но ЛЮБОЙ будущий прогон
ЭТИХ тестов на стеке 2 предсказуемо повторит тот же сбой — сиблинг-риск,
доклад по правилу 9 CLAUDE.md, не расширяю scope самостоятельным фиксом их
кейсов.

## Критерий готовности (Fixed)

Один из:
- Найден и подтверждён живым прогоном код-грунтованный root-cause расхождения
  между WebView-видимым состоянием (JS `document.title`/`current_url`) и
  `BrowserViewModel.tabs[0].url` конкретно на API 29/WebView 74 (может
  потребовать логкэт-инструментирования `app-under-test/` — вне мандата
  test-automator/test-maintainer автономно писать код приложения; кандидат:
  дев-консультация/чтение с dev, либо эмпирическая проба с доп. логами через
  `adb logcat` без правки кода приложения).
- ЛИБО найден тестовый observability-примитив/обходной Given-паттерн (по
  аналогии `bugs/AT-BUG-022.md`), детерминированно доказывающий готовность
  `tabs[0].url` ПЕРЕД `open_deep_link` НА ЭТОМ стеке — и живой прогон TC-150
  (2+ зелёных подряд) на нём.
- Хотя бы один зелёный прогон TC-150 на стеке 2 после фикса, с
  `automated_by` заполненным test-automator'ом следующим ходом.

## Чек-лист качества
- [x] Дубликаты проверены — `Grep bugs/` по `navigate-in-place`,
  `navigateActiveTabTo`, `state.tabs[0].url`, `api29`/`Chrome 74` — совпадений
  с этим механизмом не найдено (`AT-BUG-087` — соседний класс: гонка
  ActivityManager/`pm clear` при ХОЛОДНОМ старте, другой триггер и другая
  сигнатура; `AT-BUG-028` — только про отсутствие chromedriver для Chrome 69
  на api26, разрешено переходом на api29).
- [x] Окружение указано (стек 2, эмулятор/Appium/APK).
- [x] Репро-шаги — буквально Given TC-150/TC-106 (общий код).
- [x] Severity: major — блокирует automation P2-кейса и грозит скрытым
  сиблинг-риском для 2 уже Automated кейсов при будущих прогонах на этом
  стеке.
- [x] Артефакты: два контролируемых живых прогона задокументированы
  дословно (таблица выше), код-цитаты `BrowserViewModel.kt`/`BrowserScreen.kt`
  сверены построчно с деревом `app-under-test/`.
- [x] Ни один код приложения не изменён — только чтение и временные
  диагностические pytest-файлы (не закоммичены, удалены в этом же ходе).
- [x] `type: test_debt`, `debt_kind: broken_environment` — расхождение между
  WebView-состоянием и app state специфично для образа стека 2.
- [x] Лок не нужен (баг Open, никто не начал фикс).

## Rejected 2026-08-21 (Lead, пилот N4) — артефакт подмены устройства

Диагноз опровергнут критик-раундом эскалации TC-149 и контрольным
прогоном. Корень всех «api29-симптомов» этого бага — отсутствие
`appium:udid` в caps: Appium-сессия «стека 2» фактически привязывалась
к `emulator-5554` (api34, стек 1), в то время как adb-сидинг и
deep-link (`ANDROID_SERIAL`) шли в `emulator-5556`. «Расхождение
WebView-состояния и app state» наблюдалось потому, что ДРАЙВЕР И
УСТРОЙСТВО БЫЛИ РАЗНЫМИ: оба «контролируемых эксперимента» таблицы выше
меряли экран 5554 при сидинге 5556. Доказательства подмены — вердикт
критика по TC-149 (байт-идентичный page_source со стеком 1, logcat 5556
без строк инструментации, часы устройств) + решающий M2-замер Lead
(`AO3_DEVICE=emulator-5556`, `bound deviceUDID=emulator-5554`).

Фикс корня: коммит `4a3605c7` (`appium:udid`-пин + fail-fast гвардия
`DEVICE_BINDING_MISMATCH` в `create_driver`).

Контрольный прогон ПОСЛЕ фикса (Lead, дословно): TC-106
(`test_key_controls_have_accessible_label_or_text`, тот же
`open_work_page → open_deep_link(HOME) → assert_tab_strip_visible`
Given) на подлинном `emulator-5556` по лизе стека 2 —
`1 passed, 5 deselected in 29.93s`, `PYTEST_EXIT=0`, recoveries 0/2.
Deep-link-паттерн на реальном api29 работает штатно; дефект образа
api29 не существует. `BrowserViewModel.openOrNavigateDeepLink` вне
подозрений.
