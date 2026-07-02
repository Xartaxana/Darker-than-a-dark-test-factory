---
key: "TC-009"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Простановка каждого из 5 рейтингов из листинга (Rate-кнопка → bottom-sheet)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-04"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T17:05:58Z"
updated: "2026-07-02T17:05:58Z"
archived: false
resolution: null
---

# Простановка каждого из 5 рейтингов из листинга (Rate-кнопка → bottom-sheet)

_Спроецировано из `test-cases/rating/TC-009.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-009 — Пять рейтингов из листинга

## Предусловия
- Приложение запущено с чистыми данными.
- Открыта листинговая страница AO3 (search/tag browse/user works — replay-фикстура
  с записанным листингом из `framework/data/recordings/`), содержащая как минимум
  одну работу (`li.work.blurb`) с инжектированной Rate-кнопкой (28px circle,
  top-right блёрба, после `p.datetime`).

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными и открыта листинговая страница с
работой W (Rate-кнопка видна и не активирована)

**When** пользователь нажимает Rate-кнопку у работы W, в открывшемся нативном
bottom-sheet (`RatingOverlay`) выбирает рейтинг «R» (Loved / Liked / Read / Pending /
Disliked)

**Then** bottom-sheet закрывается (или подтверждает сохранение согласно UI)
**And** бейдж/стиль Rate-кнопки на карточке блёрба работы W обновляется без
перезагрузки листинга
**And** работа W появляется в соответствующей вкладке Library после перехода на экран
Library

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | синтетическая работа из replay-фикстуры листинга (см. framework/data/recordings) |
| Рейтинг R | один из: Loved(SAVE) / Liked(LIKE) / Read(READ) / Pending(PENDING) / Disliked(DISLIKE) |

## Заметки для автоматизации
- Требует replay-режим (детерминированный листинг) или live с известной тестовой
  работой — предпочтителен replay согласно docs/01 §4.
- Локатор Rate-кнопки: искать в живом DOM/дереве, не по предположению из кода —
  `ao3_bridge.js` инжектирует круг 28px после `p.datetime`; сверить фактическое
  content-description/accessibility label на живом дереве перед фиксацией локатора
  в screens/web-слое (test-automator).
- Параметризовать по 5 значениям Rating, аналогично TC-007, но точка входа — листинг,
  не панель work page (разные компоненты: bottom-sheet `RatingOverlay` vs встроенная
  `RatingMenu`).
- LIKE/SAVE может авто-кликать kudos на открытой work-page вкладке того же work, если
  такая открыта — не проверяется здесь.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
