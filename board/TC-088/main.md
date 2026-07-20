---
key: "TC-088"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Clear note очищает сохранённый комментарий работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-10"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:38:26Z"
updated: "2026-07-20T01:38:26Z"
archived: false
resolution: null
---

# Clear note очищает сохранённый комментарий работы

_Спроецировано из `test-cases/rating/TC-088.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-088 — Clear note очищает комментарий

## Предусловия
- Приложение запущено, режим replay (`listing_basic.mitm`).
- Работа W = `READ` засеяна фикстурой `note_work_seeded`
  (`framework/tests/conftest.py:328-335`: rating=LIKE, comment="Existing note
  text").
- Открыта листинговая страница, содержащая блёрб работы W.

## Сценарий (Given-When-Then)

**Given** работа W (`READ`) имеет рейтинг Kudosed и сохранённый комментарий
«Existing note text»; Rate-кнопкой работы W открыт нативный bottom-sheet —
комментарий показан в свёрнутом превью-режиме (иконка заметки + текст,
`RatingOverlay.kt` ~178-186)

**When** пользователь тапает по свёрнутому превью (раскрывает поле
комментария) и нажимает «Clear note»

**Then** поле комментария немедленно пустеет, а область комментария
возвращается к тогглу «Add a note» (свёрнутый превью со старым текстом больше
не отображается — локальное Compose-состояние `comment=""`,
`showComment=false`)
**And** после закрытия bottom-sheet тапом по затемнённой области и повторного
открытия Rate-кнопкой работы W комментарий остаётся пустым (виден тоггл
«Add a note», а не превью со старым текстом) — доказательство персистентности
очистки в Room, не только временного локального состояния overlay

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `framework/data/works.py::READ` (900000003), rating=LIKE, comment="Existing note text" (фикстура `note_work_seeded`) |

## Заметки для автоматизации
- Раскрытие СВЁРНУТОГО превью — новый шаг: коллапс-строка кликабельна
  (`Modifier...clickable { showComment = true }`, `RatingOverlay.kt:182`),
  предлагаемый метод `RatingOverlay.tap_comment_preview(text)` →
  `self.tap(self.by_text_contains(text))`. Рутинная автоматизация того же
  семейства, что существующие локаторы (`comment_text_visible` уже ищет по
  тому же селектору для чтения, не тапа) — не блокер.
- Кнопка «Clear note» — новый метод `RatingOverlay.clear_note()` →
  `self.tap(self.by_text("Clear note"))`, по образцу уже существующего
  `save_note()` (`framework/screens/rating_overlay.py:101-105`) — не блокер.
- Проверка возврата к «Add a note» — уже существующий метод
  `RatingOverlay.add_note_toggle_visible()` (`framework/screens/
  rating_overlay.py:32-33`) подходит напрямую, новый локатор не нужен.
- Повторное открытие — `rating_steps.dismiss_rating_overlay` +
  `browser_steps.tap_rate_button`, как в TC-087.
- Фикстура `note_work_seeded` и replay-инфраструктура уже верифицированы
  (`bugs/AT-BUG-004.md`, Verified) — блокеров нет.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область не комбинаторная (единичная CRUD-операция) — строка `Инвариант:` не требуется
