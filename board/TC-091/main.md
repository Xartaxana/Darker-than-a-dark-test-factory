---
key: "TC-091"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Тап по выбранному чипу удаляет личный тег работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-10"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:41:26Z"
updated: "2026-07-20T01:41:26Z"
archived: false
resolution: null
---

# Тап по выбранному чипу удаляет личный тег работы

_Спроецировано из `test-cases/rating/TC-091.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-091 — Тап по чипу удаляет личный тег

## Предусловия
- Приложение запущено, режим replay (`listing_basic.mitm`).
- Работа W = `LOVED` засеяна фикстурой `tagged_work_seeded`
  (`framework/tests/conftest.py:314-325`: rating=LIKE, tags=["Fluff",
  "Angst"]). «Angst» заведомо отсутствует среди AO3-тегов карточки W и среди
  suggested-тегов overlay (см. TC-056 — тот же фикстурный факт).
- Открыта листинговая страница, содержащая блёрб работы W.

## Сценарий (Given-When-Then)

**Given** работа W (`LOVED`) засеяна с рейтингом Kudosed и личными тегами
`["Fluff", "Angst"]`; Rate-кнопкой работы W открыт нативный bottom-sheet,
раздел тегов раскрыт (тоггл «Hide tags») — «Fluff» и «Angst» видны как
выбранные чипы

**When** пользователь тапает по чипу «Angst»

**Then** чип «Angst» немедленно исчезает из раздела тегов целиком (тег не
входит в suggested-набор карточки W — не появляется повторно как unselected
suggested-чип, в отличие от «Fluff», который совпадает с AO3-тегом карточки);
чип «Fluff» остаётся видимым как выбранный
**And** после сворачивания раздела лейбл показывает «Saved tags (1)» (было
«Hide tags» с двумя чипами до удаления)
**And** после закрытия bottom-sheet тапом по затемнённой области, повторного
открытия Rate-кнопкой работы W и раскрытия раздела тегов «Angst» по-прежнему
отсутствует, «Fluff» по-прежнему присутствует — доказательство
персистентности удаления в Room, не только локального Compose-состояния
overlay

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `framework/data/works.py::LOVED` (900000001), rating=LIKE, tags=["Fluff","Angst"] (фикстура `tagged_work_seeded`) |
| Удаляемый тег | «Angst» (вне suggested-набора карточки W) |
| Остающийся тег | «Fluff» (совпадает с AO3-тегом карточки — см. TC-056) |

## Заметки для автоматизации
- Раскрытие раздела тегов с уже существующими тегами — существующий
  `RatingOverlay.toggle_tags()` (`framework/screens/rating_overlay.py:107-111`).
- Тап по уже выбранному чипу — новый метод, аналогичный
  `LibraryScreen.select_tag` (`framework/screens/library_screen.py:157-159`,
  тот же паттерн: `clickable` висит на родительском Row чипа, тап по
  найденному текстовому узлу физически попадает в его область):
  `RatingOverlay.tap_selected_chip(tag)` → `self.tap(self.by_text(tag))` —
  рутинная автоматизация, не блокер.
- Ассерция счётчика «Saved tags (N)» — тот же новый метод, что предложен в
  заметках TC-090 (`tags_count_label_visible(n)`), переиспользуется здесь.
- Отсутствие чипа после удаления — `is_present(by_text_contains("Angst"),
  timeout=короткий) == False`, тот же generic паттерн, что и в других
  негативных ассерциях фреймворка (например
  `library_steps.assert_work_not_in_tab`).
- Фикстура `tagged_work_seeded` и replay-инфраструктура уже верифицированы
  (`bugs/AT-BUG-004.md`, Verified) — блокеров нет.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область не комбинаторная (единичная CRUD-операция) — строка `Инвариант:` не требуется
