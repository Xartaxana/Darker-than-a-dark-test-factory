---
key: "TC-200"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Баннер над листингом сообщает ОБЕ причины разом текстом «Some works may be hidden by visibility settings and active AO3 filter», когда активны и visibility-скрытие, и AO3-фильтр"
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

# Баннер над листингом сообщает ОБЕ причины разом текстом «Some works may be hidden by visibility settings and active AO3 filter», когда активны и visibility-скрытие, и AO3-фильтр

_Спроецировано из `test-cases/browser/TC-200.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-200 — Баннер: обе причины сразу → «…visibility settings and active AO3 filter»

## Предусловия
- Приложение запущено, `seeded_library` (в т.ч. `DISLIKED`, `rating=DISLIKE`).
- Settings НЕ тронуты: Display mode = Hide (дефолт), Disliked в hidden-set
  (дефолт) — `ratedHidden=true` без каких-либо действий.
- В БД засеян фильтр-профиль "My saved search" (`filter_profile_applied_seeded`).
- Открыт базовый листинг (replay `listing_basic.mitm`) БЕЗ применённого фильтра.

## Сценарий (Given-When-Then)

**Given** приложение запущено с `seeded_library`, Settings в дефолтном состоянии
(Disliked в hidden-set, Display mode=Hide), засеян фильтр-профиль "My saved
search", открыт базовый листинг без применённого фильтра

**When** пользователь раскрывает фильтр-панель и выбирает "My saved search"

**Then** страница обновляется на `rb.LISTING_FILTERED_URL`
**And** над `ol.work.index.group` появляется узел `#ao3-companion-hidden-notice`
с ДОСЛОВНЫМ текстом
**"Some works may be hidden by visibility settings and active AO3 filter"**
(`ao3_bridge.js:484`)
**And** блёрб работы DISLIKED на этой же (отфильтрованной) странице скрыт
(`display:none`) — оба механизма одновременно активны и согласованы с текстом
сообщения

**Инвариант (мастер-мэппинг):** текст/присутствие узла
`#ao3-companion-hidden-notice` — чистая функция ПАРЫ булевых флагов
`(ratedHidden, filterActive)` по таблице `ao3_bridge.js:479-487`:
- `(false, false)` → узла нет (TC-201);
- `(true, false)` → «…your visibility settings» (TC-197);
- `(false, true)` → «…the active AO3 filter» (TC-199);
- `(true, true)` → «…visibility settings and active AO3 filter» (этот кейс).

Функция не зависит ни от состава текущей листинговой страницы, ни от того, какая
конкретно работа под флагом попала на глаза пользователю — только от пары
флагов. Все четыре ячейки таблицы покрыты представителями (этот кейс и три
сиблинга); в СОВОКУПНОСТИ они и доказывают свойство, единичный кейс доказывает
только свою ячейку.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `DISLIKED` из `framework/data/works.py`, `rating=DISLIKE` |
| Фильтр-профиль | "My saved search" |
| `ratedHidden` | true |
| `ao3FilterActive` | true |
| Ожидаемый текст баннера | `Some works may be hidden by visibility settings and active AO3 filter` |

## Заметки для автоматизации
- Не блокер: метод чтения баннера — см. заметку TC-197.
- Та же инфраструктура применения фильтра, что TC-041/TC-199 (`filter_profile_applied_seeded`,
  `browser_steps.open_filter_dropdown`/`select_filter_option`).
- Единственное отличие Given от TC-199 — Settings НЕ трогаются (дефолт вместо
  явного выключения тумблера) — минимальная дельта, изолирующая именно четвёртую
  ячейку таблицы.
- **Батарея правил-реакций:** см. общую оценку в TC-201 (off-инвариант),
  TC-203 (edge-vs-level/idempotency/ретроактивность — н-п с обоснованием),
  TC-204 (propagation) — не дублирую здесь.

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
