---
key: "TC-087"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Save note сохраняет введённый текст комментария работы"
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

# Save note сохраняет введённый текст комментария работы

_Спроецировано из `test-cases/rating/TC-087.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-087 — Save note сохраняет введённый комментарий

## Предусловия
- Приложение запущено с чистыми данными, режим replay (`listing_basic.mitm`,
  `framework/data/recording_builder.py`).
- Работа W = `KUDOSED` (`framework/data/works.py`, ao3_id 900000002) в дефолтном
  состоянии — рейтинг и комментарий ещё не выставлены (строка `WorkRating` для
  W не создана, сидинг не требуется).
- Открыта листинговая страница, содержащая блёрб работы W.

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными, открыта replay-листинговая
страница с работой W (`KUDOSED`), у которой нет ни рейтинга, ни комментария;
Rate-кнопкой работы W открыт нативный bottom-sheet (`RatingOverlay`)

**When** пользователь раскрывает поле комментария (тоггл «Add a note»),
вводит текст «New saved note» и нажимает «Save note»

**Then** bottom-sheet не закрывается сам (`onSaveNote` не подразумевает
dismiss), поле комментария сворачивается в компактный превью-режим
(иконка заметки + введённый текст «New saved note» видны без раскрытия)
**And** после закрытия bottom-sheet тапом по затемнённой области и повторного
открытия того же bottom-sheet Rate-кнопкой работы W комментарий по-прежнему
предзаполнен текстом «New saved note» — доказательство персистентности в Room
(`RatingRepository.getWorkRating`), а не только локального Compose-состояния
overlay, которое было бы потеряно при пересоздании composable

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `framework/data/works.py::KUDOSED` (900000002), рейтинг/комментарий не заданы |
| Введённый комментарий | «New saved note» |

## Заметки для автоматизации
- Шаги/степы для ввода и сохранения уже существуют и используются в
  `rating_steps.add_note_via_listing_overlay` (TC-074/075, живая ветка):
  `RatingOverlay.toggle_comment()` / `.enter_comment(text)` / `.save_note()`
  (`framework/screens/rating_overlay.py:90-105`) — переиспользовать те же
  методы напрямую в replay-контексте, отдельного нового локатора не требуется.
- Повторное открытие: `rating_steps.dismiss_rating_overlay` (тап по scrim,
  `RatingOverlay.dismiss`) + `browser_steps.tap_rate_button` снова.
- Ассерция персистентности переиспользует уже существующий
  `RatingOverlay.comment_text_visible(text)` (`framework/screens/
  rating_overlay.py:72-76`, частичное совпадение текста, работает независимо
  от expanded/collapsed состояния поля) — новый метод не нужен, блокера нет.
- Отличие от TC-044 (Note-кнопка на карточке листинга открывает overlay с уже
  существующим комментарием) — там предмет проверки — путь ВХОДА в overlay
  через отдельную кнопку карточки; здесь вход через обычную Rate-кнопку, а
  предмет — сама операция сохранения (комментария на входе не было).
- Реплей-инфраструктура и сидинг уже верифицированы (`bugs/AT-BUG-004.md`,
  статус Verified) — блокеров нет.

## Ревью автотеста

- **F1 пройдено** (test-reviewer, 2026-07-21). Архитектура: `arch_check.py` без
  [ERROR]; ввод/сохранение — в `rating_overlay.py`, шаги в `rating_steps`,
  sleep нет. Traceability: `@allure.id("TC-087")` == id, `@pytest.mark.p1`/
  `replay` соответствуют, `automated_by` существует. Соответствие кейсу:
  единичная CRUD-операция; Then проверяет СУТЬ — после dismiss+reopen комментарий
  предзаполнен из Room (`getWorkRating`), а не локальным Compose-состоянием
  (которое пересоздание composable потеряло бы). Фикстура: `clean_app`+replay,
  сидинг не нужен (строка создаётся самим сохранением). Flake:
  `comment_text_visible` — частичное совпадение с wait.
- **Зелёный прогон:** `Invoke-Pytest -k test_save_note_persists_comment`
  → 1 passed (PYTEST_EXIT=0).
- **Красная проба (2026-07-21T10:31:08Z):** временно испортил ожидаемый текст
  проверки персистентности (`assert_comment_persisted(driver, comment)` →
  `"WRONG persisted probe"`). Прогон УПАЛ осмысленно: переоткрытый overlay нёс
  реально сохранённый «New saved note», assert не совпал — AssertionError
  «комментарий «WRONG persisted probe» не сохранился … потеряна персистентность
  в Room». Откачено (`git checkout`), дифф framework/ чист.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область не комбинаторная (единичная CRUD-операция) — строка `Инвариант:` не требуется
