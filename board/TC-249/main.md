---
key: "TC-249"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p2"
summary: "Плавающие кнопки листания не перекрывают FAB «Scroll to top» и нижнюю панель"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-13"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T23:03:49Z"
updated: "2026-08-15T23:03:49Z"
archived: false
resolution: null
---

# Плавающие кнопки листания не перекрывают FAB «Scroll to top» и нижнюю панель

_Спроецировано из `test-cases/browser/TC-249.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-249 — Плавающие кнопки не перекрывают соседний интерактив

## Предусловия
- E-ink mode ON, «Show page-turn buttons» ON, работа прокручена так, что
  FAB «Scroll to top» тоже виден, нижняя панель на экране.

## Сценарий (Given-When-Then)

**Given** плавающие кнопки листания, FAB «Scroll to top» и нижняя панель
одновременно видны на экране

**When** измеряются bounding box каждого из трёх элементов

**Then** bounding box плавающих кнопок НЕ пересекается с bounding box FAB
«Scroll to top»
**And** bounding box плавающих кнопок НЕ пересекается с bounding box нижней
панели — оба соседних интерактивных элемента остаются тапабельными

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Элементы | плавающие кнопки листания, FAB Scroll to top, нижняя панель |
| Ожидаемое пересечение | 0 (для каждой пары) |

## Заметки для автоматизации
- Тот же геометрический приём, что у существующих `nf-a11y-interactive-overlap`
  проверок (если такие кейсы уже есть в области accessibility) — измерение
  bounding rect через UiAutomator2/Compose test API, без нового
  инструментария.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами
- [x] Then — наблюдаемое поведение (геометрия элементов)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Область не комбинаторная для этого кейса
