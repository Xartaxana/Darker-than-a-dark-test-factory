---
key: "TC-058"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p3"
summary: "Fullscreen toggle в side panel скрывает верхнюю полосу вкладок и переключает подпись контрола (вход и выход)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-11"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-10T00:00:00Z"
updated: "2026-07-10T00:00:00Z"
archived: false
resolution: null
---

# Fullscreen toggle в side panel скрывает верхнюю полосу вкладок и переключает подпись контрола (вход и выход)

_Спроецировано из `test-cases/browser/TC-058.md` (источник правды).
Статус в нашей машине: **Review**._

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

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
