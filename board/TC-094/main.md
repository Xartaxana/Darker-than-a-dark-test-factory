---
key: "TC-094"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Side panel — переключение рейтинга Kudosed (не-Disliked) скрывает работу и синхронно отражается в Settings (эквивалентность входов)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:38:17Z"
updated: "2026-07-20T01:38:17Z"
archived: false
resolution: null
---

# Side panel — переключение рейтинга Kudosed (не-Disliked) скрывает работу и синхронно отражается в Settings (эквивалентность входов)

_Спроецировано из `test-cases/browser/TC-094.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-094 — Side panel: скрытие Kudosed — второй вход в тот же фильтр

## Предусловия
- Приложение запущено, `seeded_library` (в т.ч. `KUDOSED` с `rating=LIKE`,
  `LIKE` НЕ входит в дефолтный hidden-set `{DISLIKE}` — работа изначально
  видна).
- Открыта листинговая страница (replay `listing_basic.mitm`, содержит блёрб
  KUDOSED), это НЕ work-страница (side panel рендерит рейтинговые иконки
  только при `!isWorkPage`, `BrowseSidePanel.kt:113`).
- Side panel развёрнут (`panelExpanded = true`).

## Сценарий (Given-When-Then)

**Given** приложение запущено с `seeded_library`, работа KUDOSED
(`rating=LIKE`) изначально видна на открытом листинге, side panel развёрнут
на вкладке Browse (не work-страница)

**When** пользователь нажимает иконку рейтинга **Kudosed** в side panel
(`ratingOptions` иконка с `contentDescription="Kudosed"`,
`onToggleRating(Rating.LIKE)` → `settingsViewModel.toggleHideRating(Rating.LIKE)`
— тот же метод ViewModel, что вызывает Switch в Settings)

**Then** блёрб работы KUDOSED скрывается на уже открытом листинге
(`display:none`, live-push тем же путём, что TC-015: `hiddenRatings` →
`MainActivity.kt:169-171` → `BrowserViewModel.setHiddenRatings` →
`ao3_bridge.js` `window.setHiddenRatings` → `applyAllFilters`)
**And** при последующем открытии экрана Settings тумблер «Hide Kudosed works»
показан включённым (`uiState.isHidden(Rating.LIKE) == true`) — то же
состояние, установленное через ДРУГОЙ вход

**Инвариант:** side panel и Settings читают и пишут ОДИН и тот же
`hiddenRatings`-set через один и тот же `toggleHideRating`; переключение
ЛЮБОГО рейтинга (включая НЕ-Disliked, здесь — Kudosed/`LIKE`) через ЛЮБОЙ из
двух входов даёт идентичный эффект фильтрации И идентично видно в другом
входе — эквивалентность входов (как темы/шрифта в TC-054), доказанная здесь
для измерения hidden-ratings и для рейтинга, отличного от Disliked.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `KUDOSED` из `framework/data/works.py`, `rating=LIKE` |
| Вход действия | Side panel, иконка рейтинга «Kudosed» |
| Вход проверки | Settings, Switch «Hide Kudosed works» |

## Заметки для автоматизации
- **Побочно закрывает orphan-запись реестра** (найдено при тегировании,
  D-0043-аналог): `sidepanel-settings-sync-hidden-ratings`
  (docs/feature-registry.yaml:193-196, title «Side panel отражает состояние
  скрытых рейтингов, синхронизированное с Settings») имела 0 покрытия, но НЕ
  была вынесена в `needs-design` §9 docs/01-test-strategy.md (в отличие от
  сиблинга `sidepanel-settings-sync-theme-font`, закрытого TC-054) — этот
  кейс её Then целиком покрывает (тот же паттерн, что TC-054, для другого
  измерения стейта), тегирую сюда же. test-strategist: проверить, не остались
  ли другие orphan-записи реестра без needs-design меток (вне скоупа этого
  прохода — не расширяю сам).
- Не блокер: `framework/screens/side_panel.py` пока не имеет метода тапа по
  рейтинговой иконке — добавить по образцу `tap_home`/`tap_contrast`
  (`self.tap(self.by_desc("Kudosed"))`, `contentDescription = opt.label` из
  `ratingOptions`, `RatingOverlay.kt:54` — `LIKE` → `"Kudosed"`). Обычная
  page-object-доработка (готовый, стабильный content-desc уже есть в коде
  приложения) — не test_debt.
- Проверка на стороне Settings — переиспользовать
  `settings_screen.is_rating_hidden("Kudosed", ...)` (уже существует,
  `framework/screens/settings_screen.py:93-98`, тот же `_hide_rating_switch_locator`,
  что использует TC-015 для Disliked — здесь просто другая метка рейтинга).
- Использовать `seeded_library` — уже содержит `KUDOSED` с `rating=LIKE`,
  отдельного сидинга не требуется; фикстура листинга — та же
  `listing_basic.mitm`.
- Не смешивать с TC-054 (эквивалентность темы/шрифта) — здесь предмет другой:
  hidden-ratings, причём намеренно НЕ Disliked (P0-ядро R-06 покрыло только
  Disliked; TC-095 закрывает генерализацию per-rating инварианта со стороны
  Settings, этот кейс — со стороны side panel).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
