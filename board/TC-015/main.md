---
key: "TC-015"
project: "AO3"
issueType: "test-case"
status: "tc-review"
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
created: "2026-07-02T22:00:42Z"
updated: "2026-07-02T22:00:42Z"
archived: false
resolution: null
---

# Выключение "Enable filtering" в Settings показывает все работы независимо от рейтинга

_Спроецировано из `test-cases/visibility/TC-015.md` (источник правды).
Статус в нашей машине: **Review**._

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

## Заблокировано (test-automator, 2026-07-02)

Возвращён в `Review` — невозможно закодировать имеющимися средствами. Два
независимых блокера:

**1. Тот же replay-блокер, что у TC-013/TC-014** — кейс требует «ту же
replay-фикстуру листинга, что и TC-013», которой не существует (пустая
`framework/data/recordings/`, mitm-транспорт на Windows-хосте не доведён —
см. подробности в `TC-013.md`).

**2. Более фундаментальная проблема — расхождение между тест-кейсом и кодом
приложения.** Кейс описывает переключатель "Enable filtering" в Settings как
глобальный тумблер, отдельный от per-rating hide-переключателей (со ссылкой на
`PROJECT.md §Priority rules п.3`). Я прочитал `app-under-test/app/src/main/java/
com/example/ao3_wrapper/ui/settings/SettingsScreen.kt` (место рендера Content
Visibility секции, строки ~715–800) и `SettingsUiState`/`SettingsViewModel`
целиком — там **нет** глобального "Enable filtering" тумблера. Есть только:
- `filterRows.forEach { … Switch(checked = uiState.isHidden(row.rating), … ) }`
  — per-rating тумблеры «Hide {rating} works» (`toggleHideRating`), и
- `filterDisplayMode` («Hide» / «Dim»).

Ни `hiddenRatings`, ни `MainActivity.kt` (`browserViewModel.setHiddenRatings`),
ни `ao3_bridge.js` не содержат единого master-флага "enable filtering" — только
множество `hiddenRatings: Set<Rating>`, которое становится пустым, если
пользователь вручную выключит соответствующий per-rating тумблер (в частности
"Hide Disliked works" для этого кейса). Это, по сути, то же самое действие,
которое уже покрыто TC-013 (дефолтное состояние тумблера = включён, скрывает
Disliked) — выключение per-rating тумблера для Disliked даёт нужный эффект
(«все работы видны независимо от рейтинга Disliked»), но это не то же самое,
что описанный в кейсе отдельный «глобальный» переключатель, и `PROJECT.md`
здесь расходится с реализацией.

**Вывод:** это похоже на баг документации/тест-дизайна в духе уже известного
расхождения подписей вкладок Library (`BUG-001`) — `PROJECT.md §Priority rules
п.3` описывает функциональность ("Enable filtering"), которой в коде нет.
Кейс не может быть автоматизирован как написан. Возможные пути:
1. test-designer/product переформулирует TC-015 так, чтобы Given/When ссылался
   на реальный элемент UI — per-rating тумблер "Hide Disliked works" (тогда
   кейс станет дублировать/уточнять TC-013 в обратную сторону, нужно решить,
   отдельный ли это риск).
2. Либо это заводится как баг документации (`PROJECT.md` устарел) — по
   аналогии с BUG-001 — и в тест-кейс переносится ссылка на реальный тумблер.
Это решение вне полномочий test-automator (меняет формулировку Given/When
кейса) — эскалирую test-designer/владельцу проекта.

Даже без блокера №2, блокер №1 (replay) всё равно не позволил бы закодировать
кейс сейчас.
