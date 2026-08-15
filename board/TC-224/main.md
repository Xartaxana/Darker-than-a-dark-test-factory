---
key: "TC-224"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Ручной прогон с несуществующим Snippet ID показывает «Snippet не найден» и не меняет локальные данные"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:sync", "risk:R-16"]
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

# Ручной прогон с несуществующим Snippet ID показывает «Snippet не найден» и не меняет локальные данные

_Спроецировано из `test-cases/sync/TC-224.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-224 — Ошибка 404: сниппет не найден

## Предусловия
- Синхронизация настроена с валидным токеном, но Snippet ID указывает на
  несуществующий сниппет (мок GitLab отвечает `404` на `GET
  /api/v4/snippets/<id>`). Локально есть оценённая работа (для проверки
  «данные не изменились»).

## Сценарий (Given-When-Then)

**Given** Snippet ID указывает на несуществующий сниппет, локально есть
оценённая работа X

**When** пользователь нажимает «Sync now»

**Then** показан диалог «Sync failed» с дословным текстом «Snippet <id> not
found. Check the snippet ID, or clear it to create a new one.»
**And** локальные данные работы X НЕ изменились (рейтинг/вкладка те же, что
до прогона — второй обязательный Then негативного сценария)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Snippet ID | указывает на несуществующий сниппет |
| Ответ мока | 404 |
| Диалог | «Snippet <id> not found. Check the snippet ID, or clear it to create a new one.» |

## Заметки для автоматизации
- Sync-фикстура (мок 404-ответа) отсутствует — информация для
  test-automator, не блокер.
- Второй Then (данные не изменились) — прямая сверка Room до/после через
  `read_work_ratings_full()`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс
- [x] Given воспроизводим фикстурами
- [x] Then — наблюдаемое поведение (диалог + неизменность данных)
- [x] Приоритет/область/источник указаны
- [x] Независим от порядка других кейсов
- [x] Область не комбинаторная для этого кейса
