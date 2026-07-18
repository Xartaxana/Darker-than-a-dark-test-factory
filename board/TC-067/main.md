---
key: "TC-067"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "ao3_bridge.js инжектируется на replay-странице (window.__ao3Bridge marker, детерминированная регрессия)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T08:55:01Z"
updated: "2026-07-18T08:55:01Z"
archived: false
resolution: null
---

# ao3_bridge.js инжектируется на replay-странице (window.__ao3Bridge marker, детерминированная регрессия)

_Спроецировано из `test-cases/canary/TC-067.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-067 — Инъекция bridge на replay-странице (replay)

## Предусловия
- Приложение запущено с чистыми данными, режим **replay**
  (`framework/data/recordings/ao3_home_smoke.mitm`).
- Вкладка Browse открывает записанный URL этой фикстуры.

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме и вкладка Browse загружает
записанную страницу `ao3_home_smoke.mitm`

**When** страница полностью загружается (`onPageFinished` срабатывает)

**Then** в JS-контексте страницы присутствует маркер инъекции
`window.__ao3Bridge === true`

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/ao3_home_smoke.mitm` |
| Маркер | `window.__ao3Bridge` (boolean) |

## Заметки для автоматизации
- Тот же способ чтения маркера, что в TC-066 (`execute_script`), но детерминированно
  — без сетевой/Cloudflare-переменной live-режима, годится для регулярной
  регрессии (не только ежедневного live-прогона).
- Фикстура `ao3_home_smoke.mitm` уже существует в `framework/data/recordings/` —
  инфраструктурных блокеров нет.
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
