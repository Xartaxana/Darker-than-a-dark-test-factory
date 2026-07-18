---
key: "TC-066"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "ao3_bridge.js инжектируется в живую AO3-страницу (window.__ao3Bridge marker)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T08:54:33Z"
updated: "2026-07-18T08:54:33Z"
archived: false
resolution: null
---

# ao3_bridge.js инжектируется в живую AO3-страницу (window.__ao3Bridge marker)

_Спроецировано из `test-cases/canary/TC-066.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-066 — Инъекция bridge на живой AO3-странице (live)

## Предусловия
- Приложение запущено с чистыми данными, режим **live**, тестовая учётка
  залогинена в WebView (cookie).
- Вкладка Browse открыта; активна произвольная реальная страница
  archiveofourown.org (домашняя, листинг, work-страница — контракт не зависит
  от конкретного URL, кроме `about:blank`).

## Сценарий (Given-When-Then)

**Given** приложение запущено live и вкладка Browse загружает произвольную
страницу archiveofourown.org

**When** страница полностью загружается (`onPageFinished` срабатывает,
WebView больше не в состоянии `about:*`)

**Then** в JS-контексте страницы присутствует маркер инъекции
`window.__ao3Bridge === true` — наблюдаемый факт того, что bridge выполнился,
а не косвенное следствие (наличие кнопок и т.п., которое зависит от типа
страницы)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Страница | любая реальная archiveofourown.org (не `about:blank`) |
| Маркер | `window.__ao3Bridge` (boolean) |

## Заметки для автоматизации
- Читать маркер через `driver.execute_script("return window.__ao3Bridge === true")`
  (или эквивалент Appium `execute_script` в WEBVIEW-контексте), НЕ через
  DOM-локатор — это JS-глобал, не элемент дерева.
- Live-падение (Cloudflare interstitial, R-03) триажится по обычной live-конвенции
  (§4 docs/01) — на interstitial-странице `window.location.hostname` тоже
  `archiveofourown.org`, страница технически грузится и bridge выполняется
  (гвард по hostname в самом ao3_bridge.js касается только `peekScrollRestore`,
  не общей инъекции) — падение маркера здесь означало бы либо смену механизма
  инъекции (`onPageFinished`), либо изменение guard-логики bridge.
- Маркер: `@pytest.mark.p0 @pytest.mark.live`.
- Сиблинг-кейс TC-067 — тот же маркер в replay-режиме (детерминированная
  регрессия).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
