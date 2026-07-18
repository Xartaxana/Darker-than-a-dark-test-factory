---
key: "TC-058"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p3"
summary: "Fullscreen toggle в side panel скрывает верхнюю полосу вкладок и переключает подпись контрола (вход и выход)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-11", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T03:22:18Z"
updated: "2026-07-18T03:22:18Z"
archived: false
resolution: "done"
---

# Fullscreen toggle в side panel скрывает верхнюю полосу вкладок и переключает подпись контрола (вход и выход)

_Спроецировано из `test-cases/browser/TC-058.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-058 — Side panel Fullscreen toggle скрывает TabStrip и переключает подпись (вход/выход)

## Предусловия
- Приложение запущено с чистыми данными; открыты ДВЕ вкладки Browse (например, через
  long-press по ссылке на открытой странице — тот же способ, что использует TC-026 для
  фоновой вкладки, либо иной существующий способ открытия второй вкладки). При >1
  вкладке полоса вкладок (`TabStrip`) отображается вверху экрана в обычном (не
  fullscreen) режиме — это и есть наблюдаемый прокси для проверки скрытия/показа при
  fullscreen (системные status/navigation bars программно скрываются тем же тумблером,
  но не имеют стабильного наблюдаемого прокси через accessibility-дерево — не
  проверяются этим кейсом отдельно).
- Side panel развёрнут, показывает иконку Fullscreen с contentDescription «Enter
  fullscreen» (исходно НЕ fullscreen).

## Сценарий (Given-When-Then)

**Given** открыты 2 вкладки Browse, `TabStrip` виден вверху экрана; side panel
развёрнут, иконка Fullscreen имеет contentDescription «Enter fullscreen»

**When** пользователь нажимает иконку Fullscreen в side panel

**Then** `TabStrip` скрывается, иконка меняет contentDescription на «Exit fullscreen»
(режим fullscreen включён)

**When** пользователь нажимает ту же иконку повторно

**Then** `TabStrip` снова отображается, иконка возвращается к contentDescription
«Enter fullscreen» (режим fullscreen выключен) — toggle симметричен, повторный тап
возвращает исходное наблюдаемое состояние

**Инвариант:** `TabStrip` виден ⟺ (`tabs.size>1` ∧ `¬isFullscreen`); подпись
контрола Fullscreen всегда отражает ТЕКУЩЕЕ значение `isFullscreen` («Enter
fullscreen» при `false`, «Exit fullscreen» при `true`); toggle — инволюция: два
последовательных тапа по иконке Fullscreen возвращают оба наблюдаемых признака
(видимость `TabStrip` и подпись контрола) к исходному состоянию (тождество).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Число открытых вкладок Browse | 2 |
| contentDescription до входа в fullscreen | «Enter fullscreen» |
| Видимость TabStrip до/после входа | видим → скрыт |
| contentDescription после выхода из fullscreen | «Enter fullscreen» (вернулось) |

## Заметки для автоматизации
- Локатор кнопки — по contentDescription, который переключается между «Enter
  fullscreen»/«Exit fullscreen» (сам этот текст — второй, помимо `TabStrip`,
  наблюдаемый признак состояния).
- `TabStrip` рендерится ТОЛЬКО при `!isFullscreen && uiState.tabs.size > 1`
  (`MainActivity.kt` ~406) — при 1 вкладке (состояние по умолчанию после
  `clean_app`) условие `tabs.size > 1` не выполняется независимо от fullscreen, и
  проверка ничего не покажет: предусловие ОБЯЗАНО открыть вторую вкладку раньше
  первого тапа по Fullscreen, иначе сценарий вырождается (ложно-позитивный «TabStrip
  скрыт», потому что его не было изначально).
- Открытие второй вкладки — тот же механизм, что и в TC-026 (long-press ссылки на
  открытой WebView-странице → `viewModel.openTab(url, background=true)`,
  `BrowserScreen.kt` ~647); степ пока не написан во `framework/steps/browser_steps.py`
  (модуль `framework/tests/test_tabs.py` для области tabs ещё не существует) — это
  рутинная автоматизация (клик + long-press, без новой replay-записи или сидинга),
  НЕ инфраструктурный блокер класса `AT-BUG-004`.
- Скрытие системных status/navigation bars (`WindowInsetsControllerCompat`) тем же
  тумблером — часть кода (`LaunchedEffect(isFullscreen)`, ~202-214), но не проверяется
  этим кейсом: устойчивого способа прочитать видимость системных баров через
  accessibility-дерево UiAutomator2 нет (это системный UI, а не элемент приложения);
  при необходимости можно добавить отдельную проверку через `adb shell dumpsys window`
  вне локатор-based модели фреймворка — не запрошено явно, не блокер, просто вне
  скоупа этого GWT.
- Автоматизация (2026-07-18): вторая вкладка открыта не через long-press (TC-026 сам
  ещё не автоматизирован), а через Library → тап по карточке работы
  (`WorkCard.onClick -> onOpenWork(work.url)`, `LibraryScreen.kt` ~878) — `openTab`
  ВСЕГДА добавляет вкладку независимо от способа вызова; допустимая альтернатива по
  примечанию выше «иной существующий способ». Найдено на живом дереве/скриншотах:
  ПОЛНЫЙ цикл вход+выход fullscreen оставляет accessibility-провайдер WebView в
  состоянии, где TabStrip/BottomNav перестают отдаваться в UiAutomator2-дерево
  (`page_source`), хотя визуально отрисованы корректно (подтверждено скриншотом) —
  похоже на известный класс WebView-accessibility-багов на resize/reflow системных
  баров, не специфичный для кода TabStrip и вне скоупа правки app-under-test. Тест
  использует пиксельный прокси (средняя яркость верхней полосы экрана,
  `BrowserScreen.top_chrome_avg_luma`) вместо accessibility-дерева для проверки
  видимости TabStrip ПОСЛЕ входа в fullscreen — тот же класс решения, что HUD
  `LevelIndicator` в TC-053/TC-055.

## Ревью автотеста

### Повторное ревью (F1, полный чек-лист) — test-reviewer, 2026-07-18T03:22:18Z — вердикт: **PASS** (Approved→Automated, automation_status: active)

Оба замечания первого захода отработаны и приняты (critic-вход, task_id tc058-rework):
- п.3/C4: строка `**Инвариант:**` добавлена (TC-058.md:45-49) — формулирует именно
  СВОЙСТВО (видимость `TabStrip` ⟺ `tabs.size>1 ∧ ¬isFullscreen`; подпись ⟺
  `isFullscreen`; toggle — инволюция). Assert'ы теста проверяют обе стороны инволюции
  (видимо→скрыто→видимо через пиксельный luma-прокси + Enter→Exit→Enter подпись),
  а не единичный пример.
- п.5/flake: `assert_top_chrome_darkened`/`assert_top_chrome_restored`
  (`browser_steps.py:184-215`) переведены на `wait_until`-поллинг порога, скрытая
  связка с таймаутом `_dismiss_fullscreen_system_hint` устранена. Device-free юнит-проба
  (`framework/tests/test_top_chrome_wait_unit.py`) доказывает поллинг И его падение
  таймаутом.

Пройдены все 7 пунктов:
- п.1 архитектура: `arch_check` — 0 ошибок / 0 предупреждений; ALLOWLIST пуст (файл не
  внесён «под себя»); локаторы/пиксельные прокси в `screens/`, шаги в `steps/`, `sleep` нет.
- п.2 traceability: `@allure.id("TC-058")` == id; `@pytest.mark.p3` == P3;
  `automated_by` → существующая функция (`test_side_panel.py:232`).
- п.3 соответствие/инвариант: см. выше — свойство, не пример.
- п.4 фикстуры/данные: `loved_work_seeded` первым параметром до `driver` (сидинг ДО
  Appium-сессии), фикстура владеет данными (`clean_state` + seed), независима.
- п.5 flake-риск: явные ожидания (`wait_until`), нет `sleep`, системный hint снят
  хелпером; наблюдаемый прокси — нативный Compose-хром (пиксельный luma), не зависит
  от загрузки WebView-контента (отсутствие `@pytest.mark.live` корректно).
- п.6 зелёный прогон (на устройстве, emulator-5554):
  `Invoke-Pytest tests/test_side_panel.py -k test_side_panel_fullscreen_hides_tabstrip_and_toggles_label`
  → `1 passed, 7 deselected in 42.37s` (PYTEST_EXIT=0). Device-free юнит-проба:
  `Invoke-Pytest tests/test_top_chrome_wait_unit.py` → `4 passed` (PYTEST_EXIT=0).
- п.7 красная проба (мутационная): порча на уровне шага — `toggle_fullscreen`
  (`side_panel_steps.py:116-118`) временно превращён в no-op (`pass` вместо
  `SidePanel(driver).tap_fullscreen()`), т.е. tap Fullscreen подавлен. Прогон на порче
  → тест **УПАЛ** на `assert_top_chrome_darkened` (`test_side_panel.py:275`) с осмысленным
  `TimeoutException: «верхняя полоса не потемнела после входа в fullscreen относительно
  baseline=234.5 за 10с»` (`1 failed, 7 deselected in 46.02s`, PYTEST_EXIT=1) — падение
  указывает на суть инварианта (вход в fullscreen обязан скрыть верхний хром/TabStrip),
  не таймаут-мусор. Порча откачена в том же ходе через Edit (не `git checkout` — файл нёс
  непринятую в дерево rework-правку, которую нельзя терять); byte-exact подтверждён:
  `git hash-object framework/steps/side_panel_steps.py` == `0ff90ce…` (совпал с
  замером ДО порчи).

### Первый заход (F1, статический прогон пп.1-5) — test-reviewer, 2026-07-18 — вердикт: **changes_requested** (пп.6-7 отложены, найден блокер на этапе статики)

### Блокер (чек-лист п.3 — соответствие кейсу / C4-инвариант)
- `test-cases/browser/TC-058.md` (тело кейса, секция «Сценарий») — кейс
  комбинаторной области (видимость `TabStrip` × `tabs.size>1` × симметричный toggle
  Fullscreen) НЕ содержит формальной строки `**Инвариант:**`. Кейс создан
  2026-07-15 — ПОСЛЕ введения C4-механизма (07-14, «строка `Инвариант:` у designer
  + детектор в F1», docs/09-improvement-plan.md:112), т.е. должен был родиться с
  инвариантом. Прямой сиблинг — TC-050 (Contrast-toggle той же side panel) — строку
  несёт (`test-cases/browser/TC-050.md:37`). Свойство обратимости здесь названо
  только прозой в Then (строки 42-43 кейса), а не как C4-инвариант, детектируемый
  F1. Ретрофит-детектор — сам этот F1-проход, поэтому пропуск чиню здесь.
  **Что сделать:** добавить строку `**Инвариант:**`, формулирующую именно свойство,
  например: «`TabStrip` виден ⟺ (`tabs.size>1` ∧ `¬isFullscreen`); подпись контрола
  отражает `isFullscreen`; toggle — инволюция (два тапа = тождество наблюдаемого
  состояния)». Assert'ы теста уже покрывают обе стороны свойства (вход и выход,
  `test_side_panel.py:275,285` + иконка `:277,287`) — правку кода теста блокер, скорее
  всего, НЕ требует, но после появления инварианта сверить покрытие формально.

### Замечание (чек-лист п.5 — flake-устойчивость; чинить в том же круге)
- `framework/steps/browser_steps.py:184-197`
  (`assert_top_chrome_darkened`/`assert_top_chrome_restored`) — luma читается
  ОДНОРАЗОВО сразу после `toggle_fullscreen`, без `wait_until`-поллинга порога.
  Settle-буфер под анимированный reflow (hide `systemBars()` + resize WebView,
  продолжается после возврата тапа) обеспечивается лишь ПОБОЧНО: таймаутом
  `is_present("GOT IT", timeout=3)` в `side_panel_steps.py:97-118`
  (`_dismiss_fullscreen_system_hint`) — при выходе из fullscreen подсказка не
  появляется, и 3с ожидания дают задержку случайно. Устойчивость не должна зависеть
  от incidental-задержки чужого хелпера: обернуть пороговую проверку в `wait_until`
  (тот же модуль уже делает так — `assert_webview_darkened`/`_lightened`,
  строки 60-89). Пороги с запасом (86<117, 174>117), поэтому не жёсткий блокер, но
  правится дёшево и снимает скрытую связку с `_dismiss_fullscreen_system_hint`.

### Проверено и принято (для прозрачности)
- п.1 архитектура: `arch_check` — 0 ошибок/предупреждений; локаторы/пиксельные
  прокси в `screens/`, шаги в `steps/`, `sleep` нет; пиксельный luma-прокси
  (`top_chrome_avg_luma`) — тот же принятый класс, что HUD LevelIndicator TC-053/055.
- п.2 traceability: `@allure.id("TC-058")` == id; `@pytest.mark.p3` == priority P3;
  `automated_by` указывает на существующую функцию.
- п.4 фикстуры/данные: `loved_work_seeded` первым параметром до `driver` — сидинг ДО
  Appium-сессии (порядок критичен, соблюдён), фикстура владеет данными и опирается на
  `clean_state`; отсутствие `@pytest.mark.live` корректно (наблюдаемый прокси —
  нативный Compose-хром, не зависит от загрузки WebView-контента).

### Дефекты-собратья (D-0043, вне scope этого ревью — в очередь C4-ретрофита)
Тот же класс «комбинаторный/симметричный кейс без строки `**Инвариант:**`» замечен у
уже-Automated кейсов, НЕ покрытых ретрофитом 07-17/18 (тот взял 11 старых + TC-050/054):
`test-cases/browser/TC-052.md` (границы enable/disable «A±»), `TC-053.md`
(симметричный pinch/spread), `TC-055.md` (симметричный drag яркости). Доклад списком,
ревью на них не расширяю. (TC-057 — единичная навигация Home, не комбинаторный, не отношу.)

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
