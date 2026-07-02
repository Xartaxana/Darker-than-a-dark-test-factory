---
key: "TC-013"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Work с рейтингом Disliked скрыт на листинге при включённой фильтрации"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:visibility", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T17:16:11Z"
updated: "2026-07-02T17:16:11Z"
archived: false
resolution: null
---

# Work с рейтингом Disliked скрыт на листинге при включённой фильтрации

_Спроецировано из `test-cases/visibility/TC-013.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-013 — Disliked скрыт при включённой фильтрации

## Предусловия
- Приложение запущено, в Room засеяна работа W с `rating=DISLIKE`
  (`framework/data/seed_db.py`, `DISLIKED` из `framework/data/works.py`).
- В Settings "Enable filtering" включён (дефолт), Disliked входит в hidden-ratings
  set (дефолтное правило из PROJECT.md §Priority rules).
- Открыта листинговая страница (replay-фикстура), которая среди прочих содержит
  блёрб работы W.

## Сценарий (Given-When-Then)

**Given** приложение запущено, работа W засеяна с рейтингом Disliked, фильтрация
включена и Disliked в hidden-set

**When** пользователь открывает листинговую страницу, содержащую блёрб работы W

**Then** блёрб работы W не отображается на странице (скрыт JS-бриджем,
`applyAllFilters`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `DISLIKED` из `framework/data/works.py`, засеяна с `rating=DISLIKE` |

## Заметки для автоматизации
- Сидинг через `seed_db.py` перед стартом приложения (данные должны быть в БД до
  первого рендера листинга, `applyAllFilters` читает `window.__ao3HiddenRatings`
  на каждом page load).
- Требует replay-фикстуры листинга, где присутствует блёрб с `ao3_id` работы W
  (совпадение `li#work_{id}` с засеянным `ao3Id`).
- Selector-риск (R-02): скрытие завязано на DOM-структуру `li.work.blurb` — если
  живой AO3 изменит разметку, кейс упадёт по SITE_CHANGED, не APP_BUG — учитывать
  при триаже.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
