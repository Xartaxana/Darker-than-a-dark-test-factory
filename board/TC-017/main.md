---
key: "TC-017"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Comment-only запись (rating=null) не появляется ни в одной рейтинговой вкладке Library"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-04"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T17:05:35Z"
updated: "2026-07-02T17:05:35Z"
archived: false
resolution: null
---

# Comment-only запись (rating=null) не появляется ни в одной рейтинговой вкладке Library

_Спроецировано из `test-cases/library/TC-017.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-017 — Comment-only не появляется в рейтинговых вкладках

## Предусловия
- Приложение запущено, в Room засеяна работа W с `rating=NULL`, `comment="test note"`
  (comment-only запись, без рейтинга) — требует расширения `seed_db.py` для вставки
  `rating=NULL` (см. заметку в TC-014).
- Открыт экран Library.

## Сценарий (Given-When-Then)

**Given** приложение запущено и работа W засеяна как comment-only (`rating=null`,
`comment` не пуст)

**When** пользователь по очереди открывает вкладки FAVORITE, KUDOSED, READ, PENDING,
DISLIKED экрана Library

**Then** ни в одной из пяти рейтинговых вкладок работа W не отображается

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | любая из `framework/data/works.py`, засеяна с `rating=NULL`, `comment="test note"` |

## Заметки для автоматизации
- Требует доработки `seed_db.py` для поддержки `rating=NULL` (см. TC-014) — единая
  зависимость для обоих кейсов, стоит решить один раз.
- Downloads/FILES-вкладка не входит в скоуп (там критерий — наличие файла, не
  рейтинг) — не проверяется здесь.
- Комплементарен TC-014 (видимость на листинге) — этот кейс про видимость в Library,
  разные экраны и разные наблюдаемые поведения, не дублирование.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
