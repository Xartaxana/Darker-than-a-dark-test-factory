---
key: "TC-088"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Clear note очищает сохранённый комментарий работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-10", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-21T10:31:08Z"
updated: "2026-07-21T10:31:08Z"
archived: false
resolution: "done"
---

# Clear note очищает сохранённый комментарий работы

_Спроецировано из `test-cases/rating/TC-088.md` (источник правды).
Статус в нашей машине: **Automated**._

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

## Ревью автотеста

- **F1 пройдено** (test-reviewer, 2026-07-21). Архитектура: `arch_check.py` без
  [ERROR]; `tap_comment_preview`/`clear_note` — в `rating_overlay.py`, шаги в
  `rating_steps`, sleep нет. Traceability: `@allure.id("TC-088")` == id,
  `@pytest.mark.p1`/`replay`, `automated_by` существует. Соответствие кейсу:
  единичная CRUD-операция; Then проверяет СУТЬ — после dismiss+reopen комментарий
  остаётся пустым (виден тоггл «Add a note», а не превью старого текста) —
  персистентность очистки в Room (`comment=""` → `null`), не локальное
  состояние. Фикстура `note_work_seeded` сидит ДО Appium-сессии. Flake:
  `add_note_toggle_visible` с wait; повторная проверка после reopen с timeout=8.
- **Зелёный прогон:** `Invoke-Pytest -k test_clear_note_removes_comment`
  → 1 passed (PYTEST_EXIT=0).
- **Красная проба (2026-07-21T10:31:08Z):** временно пропустил вызов
  `rating_steps.clear_note(driver)` (комментарий не очищается). Прогон УПАЛ
  осмысленно: поле осталось развёрнутым со старым текстом, тоггл «Add a note»
  не появился — AssertionError «после Clear note ожидали тоггл «Add a note»
  вместо превью со старым текстом». Откачено (`git checkout`), дифф framework/
  чист.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область не комбинаторная (единичная CRUD-операция) — строка `Инвариант:` не требуется
