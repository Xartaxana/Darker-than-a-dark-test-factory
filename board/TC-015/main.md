---
key: "TC-015"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Выключение \"Enable filtering\" в Settings показывает все работы независимо от рейтинга"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:visibility", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T17:16:31Z"
updated: "2026-07-02T17:16:31Z"
archived: false
resolution: null
---

# Выключение "Enable filtering" в Settings показывает все работы независимо от рейтинга

_Спроецировано из `test-cases/visibility/TC-015.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-015 — Enable filtering выключен → всё видно

## Предусловия
- Приложение запущено, в Room засеяна работа W с `rating=DISLIKE`
  (`DISLIKED` из `framework/data/works.py`).
- В Settings "Enable filtering" выключен.
- Открыта листинговая страница (replay-фикстура), содержащая блёрб работы W.

## Сценарий (Given-When-Then)

**Given** приложение запущено, работа W засеяна с рейтингом Disliked
**And** в Settings "Enable filtering" выключен

**When** пользователь открывает листинговую страницу, содержащую блёрб работы W

**Then** блёрб работы W отображается (видим), несмотря на `rating=DISLIKE`
**And** бейдж/цвет Rate-кнопки работы W по-прежнему отражает Disliked (визуальный
бейдж не зависит от переключателя фильтрации, только видимость самого блёрба)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `DISLIKED` из `framework/data/works.py`, засеяна с `rating=DISLIKE` |

## Заметки для автоматизации
- Переключатель "Enable filtering" — глобальный тумблер в Settings, отдельный от
  per-rating hide toggles; убедиться, что тест трогает именно его, а не
  per-rating toggle для Disliked (тот при включённом Enable filtering тоже даёт
  скрытие — не тестируется здесь, это уже покрыто TC-013 через дефолт).
- Требует ту же replay-фикстуру листинга, что и TC-013, для сравнимости.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
