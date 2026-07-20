---
key: "TC-083"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p0"
summary: "Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T09:15:18Z"
updated: "2026-07-18T09:15:18Z"
archived: false
resolution: null
---

# Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (replay)

_Спроецировано из `test-cases/canary/TC-083.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-083 — Save filter button: инъекция + идемпотентность (replay)

## Предусловия
- Приложение запущено, режим **replay**
  (`framework/data/recordings/sort_filter_form.mitm`).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме и открыта `sort_filter_form.mitm`
с формой Sort & Filter, изначально скрытой

**When** пользователь дважды переключает видимость формы (раскрыть → скрыть →
раскрыть)

**Then** после submit-кнопки формы присутствует РОВНО ОДНА кнопка
`[data-ao3-save-profile]`, независимо от количества переключений

**Инвариант:** тот же контракт идемпотентности, что TC-082, детерминированно
проверенный на записанной разметке (уже подтверждён вручную test-maintainer'ом
в AT-BUG-006 — этот кейс формализует находку регрессионным тестом).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/sort_filter_form.mitm` |
| Селектор | `[data-ao3-save-profile]` |

## Заметки для автоматизации
- Фикстура уже существует и Verified (AT-BUG-006) — блокеров нет.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
