---
key: "TC-238"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p2"
summary: "Смена формата загрузки оставляет на диске оба файла: перезапись бьёт только по файлу той же крышки"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05"]
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

# Смена формата загрузки оставляет на диске оба файла: перезапись бьёт только по файлу той же крышки

_Спроецировано из `test-cases/downloads/TC-238.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-238 — Смешанные форматы на диске после смены формата

## Предусловия
- Работа W уже скачана в формате HTML (`downloadPath` → `<id>.html`,
  реально существующий файл).

## Сценарий (Given-When-Then)

**Given** работа W скачана как HTML

**When** пользователь переключает формат загрузки на EPUB (Settings) и
скачивает ту же работу W ПОВТОРНО

**Then** на диске остаются ОБА файла — старый `<id>.html` НЕ удалён,
появляется новый `<id>.epub`
**And** `downloadPath` строки W теперь указывает на `<id>.epub` — открытие
работы с карточки использует новый файл

## Проверяемые данные
| Параметр | Значение |
|---|---|
| До | `<id>.html` на диске, downloadPath → html |
| После повторного скачивания в EPUB | `<id>.html` + `<id>.epub` на диске, downloadPath → epub |

## Заметки для автоматизации
- **Блокер автоматизации `bugs/AT-BUG-071.md` устранён** (2026-08-16,
  test-maintainer B4): EPUB-ссылка + транзакция записаны
  (`framework/data/recordings/work_with_download_epub.mitm`), верифицированы
  регенерацией. Кейс разблокирован для test-automator.
- Судьбу двух файлов при последующем «Delete downloaded file» (сносит ОБА,
  `extractWorkId` матчит `html|epub`) — отдельная грань, покрыта смежной
  записью `settings-scan-duplicate-file-group`, не дублируется здесь.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами (после устранения AT-BUG-071)
- [x] Then — наблюдаемое поведение (состав диска + downloadPath)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Блокер автоматизации из заметок заведён test_debt-багом (AT-BUG-071)
- [x] Область не комбинаторная для этого кейса
