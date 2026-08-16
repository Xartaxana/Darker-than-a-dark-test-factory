---
key: "TC-240"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "«Open in e-reader app» открывает скачанный файл любого формата внешним приложением; без файла — неактивен с подсказкой"
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

# «Open in e-reader app» открывает скачанный файл любого формата внешним приложением; без файла — неактивен с подсказкой

_Спроецировано из `test-cases/downloads/TC-240.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-240 — «Open in e-reader app»: HTML и EPUB, и disabled-состояние

## Предусловия
- Одна работа H скачана как HTML, одна работа E скачана как EPUB, третья
  работа N НЕ скачана вовсе — все три с открытым overlay длинного нажатия.

## Сценарий (Given-When-Then)

**Given** работа H (HTML, скачана), работа E (EPUB, скачана), работа N (не
скачана) — у каждой открыт overlay длинного нажатия

**When** пользователь тапает «Open in e-reader app» у H, затем у E

**Then** ОБА тапа отдают соответствующий файл внешнему приложению через
`ACTION_VIEW` (H — MIME `text/html`, E — MIME `application/epub+zip`) —
пункт работает для ОБОИХ форматов, не только для EPUB
**And** у работы N пункт «Open in e-reader app» показан НЕАКТИВНЫМ (disabled)
с подписью «No downloaded file for this work.»

## Проверяемые данные
| Параметр | Значение |
|---|---|
| H | скачана как HTML → MIME text/html |
| E | скачана как EPUB → MIME application/epub+zip |
| N | не скачана → пункт disabled, «No downloaded file for this work.» |

## Заметки для автоматизации
- Ветка H (HTML) automatable существующим сидером без блокера. Ветка E
  (EPUB) — **блокер `bugs/AT-BUG-071.md` устранён** (2026-08-16,
  test-maintainer B4, тот же класс, что TC-239 — extension-aware
  `_push_download_fixture`) — при кодировании допустимо разбить на 2 теста
  с одним `@allure.id("TC-240")` (образец — TC-104), обе ветки H и E теперь
  automatable.
- Ветка N (disabled) не требует скачанного файла — automatable без
  блокера.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс (три состояния ОДНОГО контрола: HTML/EPUB/
      disabled — согласно title реестра, объединяющему их одним Then
      «работает для обоих форматов» + отдельный disabled-Then)
- [x] Given воспроизводим фикстурами (ветка EPUB — после устранения AT-BUG-071)
- [x] Then — наблюдаемое поведение (внешнее приложение / disabled-подпись)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Блокер автоматизации (частичный, ветка EPUB) заведён test_debt-багом (AT-BUG-071)
- [x] Область не комбинаторная для этого кейса
