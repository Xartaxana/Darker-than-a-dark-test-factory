---
key: "TC-197"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p1"
summary: "Баннер над листингом сообщает о visibility-скрытии текстом «Some works may be hidden by your visibility settings» (ratedHidden=true, filterActive=false)"
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

# Баннер над листингом сообщает о visibility-скрытии текстом «Some works may be hidden by your visibility settings» (ratedHidden=true, filterActive=false)

_Спроецировано из `test-cases/browser/TC-197.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-197 — Баннер: только visibility-скрытие → «…by your visibility settings»

## Предусловия
- Приложение запущено, `seeded_library` (в т.ч. `DISLIKED` из `framework/data/works.py`,
  `rating=DISLIKE`, среди прочих эталонных работ).
- Settings НЕ тронуты: Display mode = **Hide** (дефолт, `SettingsScreen.kt:67`),
  Disliked в hidden-set (дефолт `hiddenRatings=setOf(DISLIKE)`, `:66`), ни один
  фильтр-профиль не выбран (`activeFilterId=null` дефолт) — `ao3FilterActive=false`.
- Открывается листинговая страница (replay `listing_basic.mitm`), содержащая блёрбы
  всех эталонных работ.

## Сценарий (Given-When-Then)

**Given** приложение запущено с `seeded_library`, Settings в дефолтном состоянии
(Display mode=Hide, Disliked в hidden-set, фильтр-профиль не выбран)

**When** пользователь открывает листинговую страницу `listing_basic.mitm`

**Then** над `ol.work.index.group` присутствует узел `#ao3-companion-hidden-notice`
с ДОСЛОВНЫМ текстом **"Some works may be hidden by your visibility settings"**
(`ao3_bridge.js:485-486`)
**And** блёрб работы DISLIKED на этой же странице реально скрыт (`display:none`) —
сообщение и факт скрытия согласованы, баннер не «сирота»

**Инвариант:** текст/присутствие узла `#ao3-companion-hidden-notice` — чистая функция
ПАРЫ булевых флагов `(ratedHidden, filterActive)` (`ao3_bridge.js:477-487`), не
состава текущей страницы: при `(true, false)` текст ВСЕГДА именно
"…by your visibility settings", независимо от того, сколько конкретно работ на
данной странице скрыто. Этот кейс — представитель ячейки `(true, false)` таблицы
из четырёх; полный мэппинг доказывают сиблинги: TC-199 `(false, true)`, TC-200
`(true, true)`, TC-201 `(false, false)`.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `DISLIKED` из `framework/data/works.py`, `rating=DISLIKE` |
| `ratedHidden` | true (Hide + hidden-set непуст) |
| `ao3FilterActive` | false (фильтр не выбран) |
| Ожидаемый текст баннера | `Some works may be hidden by your visibility settings` |

## Заметки для автоматизации
- **Не блокер (page-object-доработка, по образцу TC-092/093/094):**
  `framework/web/listing_page.py` не имеет метода чтения баннера. Локатор УЖЕ
  определён — `framework/web/selectors.py:61`
  `HIDDEN_NOTICE_ID = "ao3-companion-hidden-notice"` (объявлен, но нигде не
  использован). Нужен метод по образцу `is_hidden`/`opacity_of`, например
  `hidden_banner_text() -> str | None` (текст узла `#{HIDDEN_NOTICE_ID}` или
  `None`, если узла нет). Остальные 7 кейсов этой области (TC-198..204)
  переиспользуют этот же метод — заметка не дублируется по кейсам.
- Использовать `seeded_library` — уже содержит DISLIKED, отдельного сидинга не
  требуется; фикстура листинга — `listing_basic.mitm` (та же, что TC-013/092/093).
- Проверка скрытия блёрба — существующий `browser_steps.assert_blurb_hidden`
  (тот же приём, что TC-013).
- **Батарея правил-реакций:** этот кейс — позитивный представитель мэппинга
  (не off-инвариант и не propagation) — оценка применимости батареи целиком
  дана в TC-201 (off-инвариант), TC-203 (edge-vs-level/idempotency/
  ретроактивность — н-п с обоснованием) и TC-204 (propagation) — не дублирую
  здесь.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует (page-object-доработка, не test_debt)
- [x] Строка `Инвариант:` добавлена
- [x] Батарея правил-реакций оценена (см. TC-201/203/204)
