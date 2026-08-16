---
key: "TC-237"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Скачивание в EPUB без доступной ссылки на странице завершается ошибкой «EPUB download link not found on page»"
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

# Скачивание в EPUB без доступной ссылки на странице завершается ошибкой «EPUB download link not found on page»

_Спроецировано из `test-cases/downloads/TC-237.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-237 — Ошибка скачивания EPUB без ссылки на странице

## Предусловия
- Формат загрузки — EPUB. Страница работы открыта через replay, НЕ несущая
  EPUB-ссылку в списке download-форматов. **Такой записи в
  `framework/data/recordings/` НЕТ**: `_download_list_html`
  (`framework/data/recording_builder.py:477`, `exts = ("pdf","html","mobi","epub")`)
  кладёт в `ul.download-list` ВСЕ четыре формата, поэтому все существующие
  work-страницы (включая `work_with_download.mitm`) несут рабочую
  `.epub`-ссылку. Нужна новая запись либо флаг билдера «страница без
  epub-пункта».

## Сценарий (Given-When-Then)

**Given** формат загрузки — EPUB, открыта страница работы БЕЗ доступной
EPUB-ссылки

**When** пользователь пытается скачать работу

**Then** скачивание завершается ошибкой с дословным текстом «EPUB download
link not found on page»
**And** `downloadPath` строки НЕ выставлен, файл не появляется на диске,
карточка по-прежнему показывает download-иконку

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Формат | EPUB |
| Страница | без EPUB-ссылки (HTML/PDF есть, EPUB нет) |
| Ожидаемая ошибка | «EPUB download link not found on page» |

## Заметки для автоматизации
- **Блокер автоматизации `bugs/AT-BUG-071.md` устранён** (2026-08-16,
  test-maintainer B4): work-страница БЕЗ `.epub`-ссылки записана
  (`framework/data/recordings/work_no_epub_link.mitm`, флаг
  `include_epub=False` у `_download_list_html`/`render_work_page_html`,
  билдер `build_work_no_epub_link()`), верифицирована регенерацией
  (`scripts/build_replay_recordings.py`, побайтовое сравнение с копией
  «до» — пустой diff). Кейс разблокирован для test-automator.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами (существующая запись без EPUB-ссылки)
- [x] Then — наблюдаемое поведение (текст ошибки + неизменность состояния)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Блокер автоматизации из заметок заведён test_debt-багом (AT-BUG-071)
- [x] Область не комбинаторная для этого кейса
