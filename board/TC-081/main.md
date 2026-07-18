---
key: "TC-081"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T09:15:14Z"
updated: "2026-07-18T09:15:14Z"
archived: false
resolution: null
---

# Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)

_Спроецировано из `test-cases/canary/TC-081.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-081 — Exclude-main-pairing чекбокс: инъекция + доступность (replay)

## Предусловия
- Приложение запущено, режим **replay**
  (`framework/data/recordings/sort_filter_form.mitm`).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме и открыта `sort_filter_form.mitm`
с раскрытой формой Sort & Filter, список `#exclude_relationship_tags` виден,
ни один пункт не отмечен

**When** пользователь отмечает РОВНО ОДИН чекбокс из
`#exclude_relationship_tags`

**Then** `[data-ao3-excl-main-pairing-cb]` присутствует первым пунктом списка
и включён (`disabled=false`)
**And** снятие отметки возвращает чекбокс в отключённое состояние

**Инвариант:** тот же контракт, что TC-080, детерминированно проверенный на
записанной разметке формы.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/sort_filter_form.mitm` |
| Селектор | `[data-ao3-excl-main-pairing-cb]` |

## Заметки для автоматизации
- Фикстура уже существует и Verified (AT-BUG-006) — блокеров нет; если живая
  разметка `exclude_relationship_tags` в записи окажется пустой (0
  relationship-тегов на записанной странице `tags/Fluff/works`), фолбэком
  проверить на другой существующей форме/через live — фиксировать этот факт
  test-automator'у, а не считать design-предпосылку недоказанной заранее (я
  не имею доступа к устройству в этом ходе, чтобы сверить содержимое живым
  деревом).
- Селектор `[data-ao3-excl-main-pairing-cb]` пока не в `selectors.py`.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
