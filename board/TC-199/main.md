---
key: "TC-199"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Баннер над листингом сообщает только об активном AO3-фильтре текстом «Some works may be hidden by the active AO3 filter» (ratedHidden=false, filterActive=true)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-06"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T23:03:49Z"
updated: "2026-08-15T23:03:49Z"
archived: false
resolution: null
---

# Баннер над листингом сообщает только об активном AO3-фильтре текстом «Some works may be hidden by the active AO3 filter» (ratedHidden=false, filterActive=true)

_Спроецировано из `test-cases/browser/TC-199.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-199 — Баннер: только активный AO3-фильтр → «…by the active AO3 filter»

## Предусловия
- Приложение запущено, `seeded_library` (в т.ч. `DISLIKED`, `rating=DISLIKE`).
- В Settings тумблер «Hide Disliked works» ВЫКЛЮЧЕН ДО навигации на листинг
  (`hiddenRatings` пуст) — тот же приём порядка, что TC-015/092: действие в
  Settings ДО первой загрузки листинговой страницы, чтобы флаг попал через
  инъекцию `onPageFinished`, а не только через live-push. Display mode остаётся
  Hide (не имеет значения при пустом hidden-set — `ratedHidden=false` в любом
  случае).
- В БД засеян фильтр-профиль "My saved search" (фикстура
  `filter_profile_applied_seeded`, `queryString = rb.FILTER_APPLIED_QUERY_STRING`
  — та же, что TC-041), `autoApplyFilter=true` (дефолт, не трогаем).
- Открыт базовый листинг (replay `listing_basic.mitm`) БЕЗ применённого фильтра.

## Сценарий (Given-When-Then)

**Given** приложение запущено с `seeded_library`, тумблер «Hide Disliked works»
выключен, засеян фильтр-профиль "My saved search", открыт базовый листинг без
применённого фильтра

**When** пользователь раскрывает фильтр-панель и выбирает "My saved search"
(тот же путь, что TC-041 `test_apply_filter_profile`)

**Then** страница обновляется на `rb.LISTING_FILTERED_URL` (тот же URL, что TC-041)
**And** над `ol.work.index.group` на ЭТОЙ (отфильтрованной) странице появляется
узел `#ao3-companion-hidden-notice` с ДОСЛОВНЫМ текстом
**"Some works may be hidden by the active AO3 filter"** (`ao3_bridge.js:487`)
**And** ни один блёрб на странице не скрыт по visibility-фильтрации
(`hiddenRatings` пуст, в т.ч. блёрб DISLIKED виден) — сообщение говорит именно
и только о фильтре, не о visibility-настройках

**Инвариант:** для пары `(false, true)` текст ВСЕГДА именно "…by the active AO3
filter" — как и в TC-197, свойство не зависит от того, реально ли активный
AO3-фильтр исключил хоть одну работу с ТЕКУЩЕЙ страницы; `ao3FilterActive` — факт
«профиль выбран и авто-применение включено» (`MainActivity.kt:284`), а не факт
«эта страница физически отфильтрована». Дополняет мэппинг TC-197/TC-200/TC-201.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `DISLIKED` из `framework/data/works.py` — остаётся ВИДНОЙ (негативный контроль) |
| Фильтр-профиль | "My saved search", `queryString = rb.FILTER_APPLIED_QUERY_STRING` |
| `ratedHidden` | false (hidden-set пуст) |
| `ao3FilterActive` | true |
| Ожидаемый текст баннера | `Some works may be hidden by the active AO3 filter` |

## Заметки для автоматизации
- Не блокер: метод чтения баннера — см. заметку TC-197.
- Инфраструктура применения фильтра — существующая, доказанная TC-041
  (Automated): `filter_profile_applied_seeded` fixture, `browser_steps.
  open_filter_dropdown`/`select_filter_option`/`assert_active_tab_url`/
  `assert_active_filter_shown`. Не нужно ничего добавлять.
- `settings_steps.set_hide_rating(driver, "Disliked", False)` — существующий шаг
  (TC-015), выполнить ДО `open_listing`.
- `LISTING_FILTERED_URL` — второй flow в ТОМ ЖЕ `listing_basic.mitm` (та же HTML,
  что базовый листинг) — отдельного сидинга/записи не требуется.
- Не дублирует TC-041: тот кейс проверяет применение фильтра (URL/индикация
  «активно применён»); этот — исключительно текст баннера при этой комбинации
  флагов.
- **Батарея правил-реакций:** см. общую оценку в TC-201 (off-инвариант),
  TC-203 (edge-vs-level/idempotency/ретроактивность), TC-204 (propagation) —
  не дублирую.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует
- [x] Строка `Инвариант:` добавлена
- [x] Батарея правил-реакций оценена (см. TC-201/203/204)
