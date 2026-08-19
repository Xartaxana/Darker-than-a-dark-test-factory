---
key: "BUG-073"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "Тумблер «Hide Disliked works» (Settings) вызывает ту же незапрошенную live-push навигацию, что BUG-020 — гейт __ao3LiveRatingPush защищает только broadcastRatingChange, не setHiddenRatings"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-19T18:15:22Z"
updated: "2026-08-19T18:15:22Z"
archived: false
resolution: null
---

# Тумблер «Hide Disliked works» (Settings) вызывает ту же незапрошенную live-push навигацию, что BUG-020 — гейт __ao3LiveRatingPush защищает только broadcastRatingChange, не setHiddenRatings

_Спроецировано из `bugs/BUG-073.md` (источник правды).
Статус в нашей машине: **Fixed**._

# BUG-073 — «Hide Disliked works» уводит пользователя со страницы тем же live-push механизмом, что BUG-020

## Окружение

Найдено критик-входом приёмки верификации BUG-020 (fix-verifier, D1),
2026-08-17, сборка `aa377e0ec9664fcd5439fec9391638fabf94f448` (dev-local,
versionCode 12). Живое воспроизведение на эмуляторе (`emulator-5554`),
не чтение кода.

## Суть дефекта

BUG-020 описывал незапрошенную автонавигацию `checkPageDensity`
(`ao3_bridge.js`) при live-push простановки рейтинга через
`broadcastRatingChange` (BrowserViewModel.kt). Разработчик закрыл этот
ВХОД флагом `window.__ao3LiveRatingPush` (try/finally вокруг
`applyRatings`), который `checkPageDensity` проверяет первым делом
(`ao3_bridge.js:678`) — этот путь подтверждён верификацией BUG-020 как
реально работающий.

Флаг защищает ТОЛЬКО вызов из `broadcastRatingChange`. Но
`applyAllFilters`→`checkPageDensity` вызывается и из ДРУГОГО live-push
источника — `setHiddenRatings`, который срабатывает при переключении
тумблера **«Hide Disliked works»** в Settings. Этот источник флагом не
гейтится вовсе.

## Шаги воспроизведения (Given-When-Then)

**Given**
- Листинг открыт (`listing_paginated.mitm`), infinite-scroll ON
- Единственная видимая работа на текущей странице ещё НЕ скрыта
  (hide_disliked OFF на момент открытия листинга)
- Пользователь переходит в Settings (та же сессия, WebView листинга
  остаётся живым в фоне)

**When**
- Пользователь включает тумблер «Hide Disliked works» в Settings
  (работа на листинге УЖЕ помечена DISLIKE ранее — только фильтр был
  выключен)
- Возвращается в Browse

**Then (ожидалось)**
- Пользователь видит тот же листинг с применённым фильтром (работа
  скрыта), без незапрошенной смены страницы

**Actual (фактически)**
- WebView-навигация на `&page=2` происходит АВТОМАТИЧЕСКИ, без действия
  пользователя в самом браузере — тот же класс дефекта, что BUG-020
  (R-17: «приложение действует вместо пользователя»)

## Частота

1 из 1 живого воспроизведения (критик-вход приёмки BUG-020).

## Верификация находки (критик-вход BUG-020)

Дословный вывод пробы (`CRITIC C`):
```
после DISLIKE при hide OFF: samples=['/works?ao3_companion_fixture=listing_paginated']
после включения тумблера:   samples=['/works?ao3_companion_fixture=listing_paginated&page=2']
FAILED (ожидалось: страница не меняется)
```

## Анализ (дефект приложения)

`__ao3LiveRatingPush` — гейт по ОДНОМУ конкретному источнику вызова
(`broadcastRatingChange`), не по факту «live-push в открытый листинг»
как классу. `setHiddenRatings` (переключение тумблера) вызывает тот же
`applyAllFilters`→`checkPageDensity` без какого-либо гейта.

## Критерий готовности (рекомендация для разработчика)

Обобщить гейт: либо выставлять `__ao3LiveRatingPush` (или переименовать
в более общий `__ao3LivePushInProgress`) вокруг ЛЮБОГО live-push
источника, вызывающего `applyAllFilters` на уже открытом листинге — не
только `broadcastRatingChange`, но и `setHiddenRatings`. Проверить
также непроверенные кандидаты той же поверхности (не воспроизведены,
только названы гипотезой): `setFilterMode`, чекбокс «Main pairing
only» (`ao3_bridge.js:768`).

## Связанные наблюдения (D-0043: класс дефекта)

Прямой сосед `BUG-020` — тот же механизм
(`checkPageDensity` срабатывает на ЛЮБОЙ `applyAllFilters` без разбора
источника/контекста), другой конкретный вход.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[critic @ 2026-08-17T03:20:00Z]** Найдено при критик-входе приёмки
верификации BUG-020 (fix-verifier, D1) — соседний вход той же
поверхности не был заявлен исходным диспатчем, доложен по правилу 9
CLAUDE.md («докладывать аналог, не расширяя scope текущей задачи»).
Не чинил (app-under-test/ не тронут), не расширял верификацию BUG-020
починкой.

**[gitlab:dyakagreen @ 2026-08-19T17:21:47.859Z]** > **Исправлено в `4f9feb3`** (main).
> 
> Гейт обобщён, как и рекомендовалось. Вместо флага, который выставлял только `broadcastRatingChange`, в `ao3_bridge.js` появился `withLivePush(live, fn)`: он выставляет `window.__ao3LivePush` на время вызова, а `checkPageDensity` проверяет его первым делом. Через него теперь проходят все live-push источники:
> 
> - простановка рейтинга (`broadcastRatingChange`);
> - тумблеры «Hide … works» (`setHiddenRatings(..., live)`) — вход из этого бага;
> - режим отображения Hide/Dim (`setFilterMode(..., live)`) — вторая дыра того же класса, в баге не заявленная.
> 
> Ключевая деталь, из-за которой гейт сделан **параметром вызова**, а не общим правилом внутри функции: `setHiddenRatings` вызывается ещё и на загрузке страницы (`onWorksFoundInternal`), где автопрыжок как раз легитимен. Страничные вызовы аргумент `live` не передают и автопрыжок сохраняют.
> 
> Про третьего кандидата из вашей рекомендации — чекбокс «Main pairing only»: правка не требуется. Его `applyAllFilters()` выполняется внутри `injectMainPairingCheckbox` на инициализации страницы, то есть это page-load-контекст, а не live-push.
> 
> Проверено на эмуляторе, на локальной фикстуре (реальная разметка листинга AO3, но без обращения к сайту):
> 
> - контроль — свежая загрузка листинга при включённом hide и всех работах DISLIKE: автопрыжок срабатывает, page 1 → page 2, то есть механизм жив и проба способна упасть;
> - проба — тот же листинг уже открыт, тумблер переключается на лету: работы скрываются, появляется плашка «some works may be hidden by your visibility settings», URL не меняется.

**[gitlab:dyakagreen @ 2026-08-19T17:21:48.858Z]** Метка `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

**[qa @ 2026-08-19T18:15:22Z]** Принято. Архитектура фикса проверена по коду:
- `withLivePush(live, fn)` установлена в ao3_bridge.js:163, выставляет флаг `window.__ao3LivePush`
- `checkPageDensity` проверяет флаг первым делом (ao3_bridge.js:697), пропускает автопрыжок для live-push контекстов
- `setHiddenRatings(ratings, live)` и `setFilterMode(mode, live)` оба вызывают `withLivePush(live, applyAllFilters)` (строки 490, 495)
- Параметр `live` = ложь → гейт не применяется, функция выполняется сразу (строка 164); это сохраняет автопрыжок на page-load (e.g. `onWorksFoundInternal`)

Про третьего кандидата (чекбокс «Main pairing only»): согласен, что его `applyAllFilters()` вызывается внутри `injectMainPairingCheckbox` на инициализации, это page-load-контекст, не live-push — включение в гейт не требуется.

Вторая найденная дыра (`setFilterMode(..., live)`) закрыта тем же гейтом, что входит в scope этого бага. Фикс готов к верификации D1 (fix-verifier).

awaiting: dev
