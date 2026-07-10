---
key: "TC-056"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p3"
summary: "Личный тег, совпадающий с AO3-тегом карточки, подсвечивается на листинге"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:rating", "risk:R-10 (proposed, не утверждён в §5)"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-10T00:00:00Z"
updated: "2026-07-10T00:00:00Z"
archived: false
resolution: null
---

# Личный тег, совпадающий с AO3-тегом карточки, подсвечивается на листинге

_Спроецировано из `test-cases/rating/TC-056.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-056 — Совпадающий личный тег подсвечивается на карточке листинга

## Предусловия
- Приложение запущено с чистыми данными, режим прогона replay.
- В Room засеяна работа W (`framework/data/works.py`, например `LOVED`) через
  `seed_with_comment` с произвольным рейтингом, не влияющим на видимость (например
  LIKE), и личными тегами `tags=["Fluff", "Angst"]` (JSON-список; Room-конвертер
  `Converters.fromTagList`/`toTagList` хранит и читает его как JSON-массив строк).
- Открыта replay-листинговая страница `listing_basic.mitm` (та же фикстура `replay`,
  индирект-параметризация `rb.LISTING_BASIC_FILENAME`, что использует TC-013/043/045),
  содержащая блёрб работы W среди прочих эталонных работ. Каждый блёрб фикстуры несёт
  фиксированный набор AO3-тегов карточки: warning «Creator Chose Not To Use Archive
  Warnings», relationship «Test Ship/Other Ship», freeform «Fluff» (см.
  `framework/data/recording_builder.py::_blurb_html`). Личный тег «Fluff» совпадает с
  card-тегом дословно без учёта регистра; «Angst» не встречается ни у одной работы
  фикстуры.

## Сценарий (Given-When-Then)

**Given** работа W на листинге имеет личные теги `["Fluff", "Angst"]`, из которых
«Fluff» совпадает с одним из AO3-тегов её карточки (freeform «Fluff»), а «Angst» не
совпадает ни с одним AO3-тегом карточки

**When** пользователь просматривает листинговую страницу с блёрбом работы W (страница
догружена, bridge применил `applyRatings`/`highlightWorkTags`)

**Then** ссылка AO3-тега «Fluff» на карточке W получает атрибут `data-ao3-tag-hl` и
визуально выделена (фон/outline применены inline-стилем)
**And** остальные AO3-теги карточки W («Creator Chose Not To Use Archive Warnings»,
«Test Ship/Other Ship») атрибут `data-ao3-tag-hl` НЕ получают — подсвечивается только
реально совпадающий тег, личный тег «Angst» ни на что не влияет (не совпал ни с чем)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `framework/data/works.py::LOVED`, rating=LIKE, tags=["Fluff", "Angst"] |
| Совпадающий AO3-тег карточки | freeform «Fluff» |
| Несовпадающий личный тег | «Angst» (отсутствует на любой карточке фикстуры) |
| Фикстура листинга | `listing_basic.mitm` (`replay`, indirect-параметризация, как в TC-013) |

## Заметки для автоматизации
- `highlightWorkTags(li, personalTags)` (`ao3_bridge.js` ~296) сначала снимает ВСЕ
  существующие `data-ao3-tag-hl`/inline-стили с карточки, затем расставляет их заново —
  идемпотентно при повторных вызовах `applyRatings` (полезно, если сценарий когда-нибудь
  расширят проверкой снятия подсветки после смены тегов — сейчас не проверяется, только
  начальное состояние после первого применения).
- Сравнение регистронезависимое (`a.textContent.trim().toLowerCase()` против
  `t.toLowerCase()` для каждого личного тега) — тестовые значения намеренно взяты в
  «естественном» регистре («Fluff», не «fluff»), полного покрытия регистронезависимости
  этот кейс не требует (риск минорный, P3).
- Вызывается из `window.applyRatings` (~437) как `highlightWorkTags(li, workTags || [])`
  для каждого `li[id^="work_"].work.blurb`; `workTags` приходит из
  `window.__ao3Tags[workId]`, который Kotlin передаёт из
  `RatingRepository.buildListingMetadata` (личные теги работы — НЕ таксономия AO3).
- Не путать с индикатор-кнопкой «custom tags» (`makeTagButton`/`getCustomTags`,
  `ao3_bridge.js` ~286) — это ОТДЕЛЬНАЯ фича (кнопка появляется для тегов, которых НЕТ на
  карточке). В этом кейсе «Fluff» специально подобран так, чтобы БЫТЬ на карточке —
  кнопка-индикатор для него не появляется, что ожидаемо и не является предметом
  проверки здесь.
- Требуется новый локатор/степ в `framework/web/listing_page.py` (по аналогии с уже
  существующим `badge_for`/`is_hidden`): найти `a.tag` с текстом «Fluff» внутри
  `li#work_{id}` и прочитать атрибут `data-ao3-tag-hl` через `get_attribute`. Метода
  пока нет, но это рутинная автоматизация того же семейства локаторов — НЕ блокер:
  фикстура листинга (`listing_basic.mitm`) и сидинг личных тегов (`seed_with_comment`,
  столбец `tags`) уже существуют и рабочие (`bugs/AT-BUG-004.md`, статус `Verified`).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
