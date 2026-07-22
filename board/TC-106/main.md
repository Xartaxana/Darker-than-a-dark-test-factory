---
key: "TC-106"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p2"
summary: "Ключевые контролы (Rate/Note/тема/шрифт/таб) несут content-description или видимый текст в accessibility tree"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:accessibility", "risk:R-13", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-22T23:13:20Z"
updated: "2026-07-22T23:13:20Z"
archived: false
resolution: "done"
---

# Ключевые контролы (Rate/Note/тема/шрифт/таб) несут content-description или видимый текст в accessibility tree

_Спроецировано из `test-cases/accessibility/TC-106.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-106 — Content-description/текст на ключевых контролах (accessibility tree)

## Предусловия
- Приложение запущено с чистыми данными, работа W засеяна (`seed_with_download`
  либо базовый rating-seed, как в TC-009).
- Страница работы `/works/{id}` открыта в браузере.
- Панель рейтинга (`RatingOverlay`) раскрыта (тап по Rate-кнопке листинга/панели).
- Side panel раскрыта (жест/кнопка раскрытия — см. `BrowseSidePanel.kt`), видны
  контролы темы и размера шрифта.
- Открыто ≥2 вкладки (виден `TabStrip` с контролами New tab/Close tab и хотя бы
  одним табом).

## Сценарий (Given-When-Then)

**Given** приложение в описанном состоянии: `RatingOverlay` раскрыт, side panel
раскрыта, `TabStrip` виден с ≥2 вкладками

**When** accessibility tree читается напрямую через UiAutomator2 (`page_source`
либо `find_elements` по каждой зоне: панель рейтинга, side panel, tab strip) —
без взаимодействия с элементами, только инспекция дерева

**Then** каждый из следующих контролов несёт непустой `content-desc` ИЛИ
видимый `text` (хотя бы один из двух — Compose может выражать семантику через
соседний `Text`, смёрженный с кликабельным родителем):
- опции рейтинга в `RatingOverlay` (видимый текстовый лейбл `opt.label` на
  каждой кнопке — Loved/Liked/Read/Disliked)
- кнопка заметки (Note) — там, где применимо для текущего состояния работы
- переключатель темы в side panel (`content-desc` = "Switch to light mode" /
  "Switch to dark mode" в зависимости от текущего режима)
- контролы размера шрифта в side panel (`content-desc` = `opt.label` на
  каждой кнопке размера)
- контролы `TabStrip`: "New tab", "Close tab" (`content-desc`), сам таб —
  `content-desc` = `tab.label`

**And** ни один из перечисленных узлов не имеет ОДНОВРЕМЕННО пустого
`content-desc` И пустого `text`

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | ao3_id из `data/works.py` (та же, что TC-009) |
| Ожидаемые content-desc (side panel) | "Switch to light mode" / "Switch to dark mode", `opt.label` (font) |
| Ожидаемые content-desc (tab strip) | "New tab", "Close tab", `tab.label` |
| Ожидаемые текстовые лейблы (rating overlay) | `opt.label` рейтинговых опций (Loved/Liked/Read/Disliked) |

## Заметки для автоматизации
- Блокера нет: чистая инспекция accessibility tree через существующий
  UiAutomator2-драйвер (`page_source` / `driver.find_elements` по
  `AppiumBy.ANDROID_UIAUTOMATOR` или XPath на `content-desc`/`text`) — та же
  техника, что уже используют текущие screen-модули фреймворка для локаторов
  (`framework/screens/*`), без новой инфраструктуры/фикстур.
- Код-основание (сверено по `app-under-test`, не по памяти):
  `RatingOverlay.kt` (иконки опций несут `contentDescription = null`, но рядом
  `Text(opt.label, ...)` — видимый текст, смёрженный Compose с кликабельным
  родителем), `BrowseSidePanel.kt:110-111` (тема: явный `contentDescription`),
  `BrowseSidePanel.kt:126` (шрифт: `contentDescription = opt.label`),
  `TabStrip.kt:72-73,125-126` (New/Close tab), `BottomBar.kt:339`
  (`contentDescription = tab.label`).
- Если по факту прогона окажется, что какой-то из перечисленных узлов не
  проходит (пустой И content-desc, И text) — это находка для триажа
  (продуктовый баг доступности, заводит bug-reporter по вердикту триажа), не
  повод менять сам кейс.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...» (одна инспекция
  дерева, набор And-проверок над РЕЗУЛЬТАТОМ той же инспекции — не отдельные
  сценарии)
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение (accessibility tree — то, что
  реально читает screen reader/UiAutomator2), а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область НЕ комбинаторная (конечный поимённый список контролов, не
  семейство входов с инвариантом) — строка `Инвариант:` не требуется

## Ревью автотеста (F1, test-reviewer 2026-07-22)

Полный чек-лист F1 пройден, `Approved → Automated`.
- **Архитектура:** `arch_check.py` — 0 ошибок/предупреждений; локаторы/driver не в
  tests/, шаги в `a11y_steps`/`side_panel_steps`, sleep нет.
- **Traceability:** `@allure.id("TC-106")` == id, маркер `p2` == priority P2,
  `automated_by` резолвится, фича `nf-a11y-content-labels` в реестре.
- **Соответствие:** конечный поимённый список контролов (не комбинаторика) —
  assert'ы проверяют «узел несёт непустой content-desc ИЛИ text» для каждого
  named-контрола, что и есть суть GWT.
- **Зелёный прогон:** `Invoke-Pytest tests/test_accessibility.py` → PASSED (120.67s).
- **Красная проба (2026-07-22T23:13:20Z):** в `a11y_steps._assert_label` временно
  ужесточил условие `desc.strip() or text.strip()` → `and`. Прогон упал
  содержательно: `AssertionError: кнопка рейтинга SAVE ('Favorite'): и content-desc,
  и text пусты` (desc='', text='Favorite') — assert реально читает оба канала
  лейбла и доходит до узла, не тавтология. Порча откачена (Edit-обратно, source
  чист).
