---
key: "TC-095"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Скрытие рейтинга Kudosed (не-Disliked) в Settings исключает только работы с этим рейтингом, остальные видны"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:visibility", "risk:R-06", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-21T15:54:38Z"
updated: "2026-07-21T15:54:38Z"
archived: false
resolution: "done"
---

# Скрытие рейтинга Kudosed (не-Disliked) в Settings исключает только работы с этим рейтингом, остальные видны

_Спроецировано из `test-cases/visibility/TC-095.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-095 — Скрытие Kudosed не задевает остальные рейтинги

## Предусловия
- Приложение запущено, `seeded_library` — по одной работе на каждый рейтинг:
  `LOVED=SAVE`, `KUDOSED=LIKE`, `READ=READ`, `PENDING=PENDING`,
  `DISLIKED=DISLIKE`.
- Disliked в hidden-set (дефолт) — DISLIKED изначально скрыт, остальные
  четыре видны.
- Открыта листинговая страница (replay `listing_basic.mitm`, содержит блёрбы
  всех пяти работ).

## Сценарий (Given-When-Then)

**Given** приложение запущено с `seeded_library`, открыт листинг: DISLIKED
скрыт (дефолт), LOVED/KUDOSED/READ/PENDING видны

**When** пользователь в Settings включает тумблер «Hide Kudosed works»
(`viewModel.toggleHideRating(Rating.LIKE)`, `hiddenRatings` становится
`{DISLIKE, LIKE}`), не трогая остальные тумблеры, и возвращается на уже
открытую вкладку Browse без повторной навигации листинга (тот же live-push
путь, что TC-015)

**Then** блёрб работы KUDOSED (`rating=LIKE`) теперь тоже скрыт
**And** блёрб работы DISLIKED остаётся скрытым (не изменился)
**And** блёрбы работ LOVED (`rating=SAVE`), READ (`rating=READ`), PENDING
(`rating=PENDING`) остаются видны — их рейтинги не входят в hidden-set

**Инвариант:** скрытие фильтрацией по членству в hidden-set верно для ЛЮБОГО
рейтинга, не только Disliked: включение per-rating тумблера для рейтинга X
исключает из рендера ТОЛЬКО работы с `rating == X`; работы с любым ДРУГИМ
рейтингом (в т.ч. уже скрытым по умолчанию Disliked) не меняют состояния
видимости. Обобщает инвариант TC-013 (доказанный только на представителе
Disliked) на второй, независимо выбранный рейтинг (Kudosed/`LIKE`) —
закрывает пробел «per-rating тестировался только на Disliked» со стороны
входа Settings (сторону side panel закрывает TC-094).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа (новая цель скрытия) | `KUDOSED`, `rating=LIKE` |
| Работа (дефолт, контроль) | `DISLIKED`, `rating=DISLIKE` |
| Работы-негатив | `LOVED` (`SAVE`), `READ` (`READ`), `PENDING` (`PENDING`) |

## Заметки для автоматизации
- Полностью переиспользует существующие шаги: `settings_steps.set_hide_rating`
  (`framework/steps/settings_steps.py:27`, `framework/screens/settings_screen.py:100`)
  уже параметризован по `rating_label` — вызвать с `"Kudosed"` вместо
  `"Disliked"`, дополнительной доработки локатора не требуется (в отличие от
  TC-092/093/094, где нужны НОВЫЕ методы).
- `browser_steps.assert_blurb_hidden`/`assert_blurb_visible` уже принимают
  произвольный `work_id` — вызвать на всех пяти `works.py::ALL` id.
- Блокеров нет: `seeded_library` уже покрывает все пять рейтингов, replay-
  фикстура `listing_basic.mitm` уже содержит все пять блёрбов — кейс готов к
  диспатчу test-automator без предварительной доводки инфраструктуры.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
