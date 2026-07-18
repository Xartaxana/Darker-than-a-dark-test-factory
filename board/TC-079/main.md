---
key: "TC-079"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T08:56:39Z"
updated: "2026-07-18T08:56:39Z"
archived: false
resolution: null
---

# Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)

_Спроецировано из `test-cases/canary/TC-079.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-079 — Main-pairing include-чекбокс: инъекция + доступность (replay)

## Предусловия
- Приложение запущено, режим **replay**
  (`framework/data/recordings/sort_filter_form.mitm` — реальная страница
  `archiveofourown.org/tags/Fluff/works`, форма `#work-filters` в исходной
  разметке, Verified в AT-BUG-006).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме и открыта `sort_filter_form.mitm`
с раскрытой формой Sort & Filter, список `#include_relationship_tags` виден,
ни один пункт не отмечен

**When** пользователь отмечает РОВНО ОДИН чекбокс из
`#include_relationship_tags`

**Then** `[data-ao3-main-pairing-cb]` присутствует первым пунктом списка и
включён (`disabled=false`)
**And** снятие отметки возвращает чекбокс в отключённое состояние
(`disabled=true`, opacity 0.4)

**Инвариант:** тот же контракт, что TC-078, детерминированно проверенный на
записанной разметке формы (фикс якорь — не зависит от live-вариативности
списка relationship-тегов).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/sort_filter_form.mitm` |
| Селектор | `[data-ao3-main-pairing-cb]` |

## Заметки для автоматизации
- Фикстура уже существует и Verified (AT-BUG-006, форма подтверждена в
  исходной разметке через page_source живого Appium-сеанса) — блокеров нет.
- Селектор `[data-ao3-main-pairing-cb]` пока не в `selectors.py` — добавить
  при кодировании (не блокер).
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
