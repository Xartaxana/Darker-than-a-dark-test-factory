---
key: "TC-239"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Открытие скачанной EPUB-работы (Open downloaded / Open in background tab) отдаёт файл внешнему ридеру, а не создаёт вкладку"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-16"]
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

# Открытие скачанной EPUB-работы (Open downloaded / Open in background tab) отдаёт файл внешнему ридеру, а не создаёт вкладку

_Спроецировано из `test-cases/downloads/TC-239.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-239 — Открытие EPUB отдаёт файл внешнему приложению

## Предусловия
- Работа W уже скачана в формате EPUB (`downloadPath` → реально
  существующий `<id>.epub`).

## Сценарий (Given-When-Then)

**Given** работа W скачана как EPUB, карточка показывает open-иконку

**When** пользователь тапает Book-иконку «Open downloaded» на карточке (и
отдельно, вторым прогоном того же сценария — пункт «Open in background
tab» в overlay длинного нажатия)

**Then** ОБА действия открывают файл через `ACTION_VIEW` во ВНЕШНЕМ
приложении (эмулируется заглушкой/выбором приложения в тестовом
окружении) — новая вкладка браузера НЕ создаётся, экран Library не
меняется
**And** если на устройстве нет обработчика EPUB — вместо запуска внешнего
приложения показан тост «No app found to open this file»

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | скачана как EPUB |
| Ожидаемый результат обоих входов | внешнее приложение, без новой вкладки |
| Без обработчика | тост «No app found to open this file» |

## Заметки для автоматизации
- **Блокер автоматизации `bugs/AT-BUG-071.md` устранён** (2026-08-16,
  test-maintainer B4): `_push_download_fixture` выводит расширение
  устройственного пути из `local_file.suffix` (не хардкод `.html`) —
  `seed_with_download`/`seed_with_comment_and_download` кладут файл под
  именем `<id>.epub`, если передан `framework/data/fixtures/downloaded_work.epub`.
  Кейс разблокирован для test-automator.
- **Наблюдение, НЕ баг (доложено test-strategist, §10 щ):** описание пункта
  «Open in background tab» в UI буквально гласит «Opens without leaving the
  library, so you can queue up several works.» (`LibraryScreen.kt:417`) —
  для `.epub`-работы это фактически НЕВЕРНО (приложение покидается,
  открывается внешний ридер). Дизайн фиксирует ФАКТИЧЕСКОЕ текущее
  поведение (внешний ридер) как ожидаемое по коду/реестру; несоответствие
  подписи — не предмет этого кейса и не заводится этим design'ом багом.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс (два эквивалентных входа с ОДНИМ Then —
      не дробится, см. заметку про реестр: title объединяет их)
- [x] Given воспроизводим фикстурами (после устранения AT-BUG-071)
- [x] Then — наблюдаемое поведение (внешнее приложение / тост)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Блокер автоматизации из заметок заведён test_debt-багом (AT-BUG-071)
- [x] Область не комбинаторная для этого кейса
