---
key: "TC-014"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p0"
summary: "Work без рейтинга (или comment-only, rating=null) никогда не скрывается фильтрацией"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:visibility", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T00:00:00Z"
updated: "2026-07-02T00:00:00Z"
archived: false
resolution: null
---

# Work без рейтинга (или comment-only, rating=null) никогда не скрывается фильтрацией

_Спроецировано из `test-cases/visibility/TC-014.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-014 — Work без рейтинга / comment-only не скрывается

## Предусловия
- Приложение запущено с чистыми данными (работа A — вообще без строки `WorkRating`).
- В Room дополнительно засеяна работа B с `rating=null`, `comment="test note"`
  (comment-only запись, без рейтинга).
- Фильтрация включена, Disliked (и по возможности другие рейтинги) в hidden-set.
- Открыта листинговая страница (replay-фикстура), содержащая блёрбы работ A и B.

## Сценарий (Given-When-Then)

**Given** приложение запущено, фильтрация включена и Disliked в hidden-set
**And** работа A не имеет строки `WorkRating` в БД
**And** работа B имеет строку с `rating=null` и непустым `comment`

**When** пользователь открывает листинговую страницу, содержащую блёрбы работ A и B

**Then** блёрб работы A отображается (видим)
**And** блёрб работы B отображается (видим), несмотря на наличие comment-only записи

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа A | любая из `framework/data/works.py`, не засеяна в БД |
| Работа B | другая работа из `framework/data/works.py`, засеяна с `rating=NULL`, `comment="test note"` |

## Заметки для автоматизации
- `seed_db.py._insert_rows` сейчас принимает `rating` как обязательный enum-параметр
  из `_RATING_ENUM` — для этого кейса потребуется поддержка `rating=NULL` (comment-
  only запись); согласовать с test-automator/data доработку сидинг-скрипта, либо
  вставлять напрямую отдельным SQL в тесте, не трогая `app-under-test/`.
- Не смешивать с TC-013 (Disliked скрыт) — здесь фокус на негативную проверку
  (единственный источник ложного срабатывания фильтрации — если бы работы без
  рейтинга или comment-only ошибочно скрывались).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
