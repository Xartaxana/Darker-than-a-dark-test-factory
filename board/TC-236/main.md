---
key: "TC-236"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Скачивание в формате EPUB сохраняет файл .epub с MIME application/epub+zip и появляется на вкладке Files"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T00:10:14Z"
updated: "2026-08-15T00:10:14Z"
archived: false
resolution: null
---

# Скачивание в формате EPUB сохраняет файл .epub с MIME application/epub+zip и появляется на вкладке Files

_Спроецировано из `test-cases/downloads/TC-236.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-236 — Скачивание работы в формате EPUB

## Предусловия
- Формат загрузки в Settings — EPUB (см. TC-235). Страница работы открыта
  через replay, несущая рабочую EPUB-ссылку (`li.download a[href*=".epub"]`).

## Сценарий (Given-When-Then)

**Given** формат загрузки — EPUB, страница работы с валидной EPUB-ссылкой
открыта

**When** пользователь скачивает работу (download-иконка на карточке или с
панели)

**Then** на диске появляется файл `<...>.epub`, `downloadPath` строки
указывает на него, MIME сохранённого файла — `application/epub+zip`
**And** работа появляется на вкладке Files экрана Library
**And** карточка показывает open-иконку (файл есть), а не download-иконку

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Формат | EPUB |
| Ожидаемое расширение | `.epub` |
| Ожидаемый MIME | `application/epub+zip` |

## Заметки для автоматизации
- **Блокер автоматизации — `bugs/AT-BUG-071.md`** (test_debt, заведён этим
  же ходом): нет mitm-записи work-страницы с EPUB-ссылкой. Кейс оставлен в
  `Review` — Given/Then полны, ограничение чисто инструментальное.
- Позитивный симметричный кейс к HTML-скачиванию (TC-032/033).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами (после устранения AT-BUG-071)
- [x] Then — наблюдаемое поведение (файл, MIME, вкладка, иконка)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Блокер автоматизации из заметок заведён test_debt-багом (AT-BUG-071)
- [x] Область не комбинаторная для этого кейса
