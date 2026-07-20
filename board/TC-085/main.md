---
key: "TC-085"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Переименование фильтр-профиля обновляет отображаемое имя и не меняет queryString"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:filter-profiles", "risk:R-09"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:07:01Z"
updated: "2026-07-20T01:07:01Z"
archived: false
resolution: null
---

# Переименование фильтр-профиля обновляет отображаемое имя и не меняет queryString

_Спроецировано из `test-cases/filter-profiles/TC-085.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-085 — Переименование фильтр-профиля сохраняет `queryString`

## Предусловия
- Приложение запущено с чистыми данными, в Room засеян один `FilterProfile` с именем
  "My saved search" и `queryString`, РАВНЫМ `recording_builder.FILTER_APPLIED_QUERY_STRING`
  (та же фикстура, что TC-041 — `filter_profile_applied_seeded`), так что применение этого
  профиля строит URL, байт-в-байт совпадающий со вторым flow `listing_basic.mitm`
  (`LISTING_FILTERED_URL`).
- Открыт экран Settings, секция "Saved AO3 Filters" показывает "My saved search".

## Сценарий (Given-When-Then)

**Given** в Settings в секции "Saved AO3 Filters" отображается сохранённый профиль
"My saved search" с известным `queryString`

**When** пользователь нажимает иконку "Rename" рядом с профилем, в открывшемся диалоге
"Rename filter" очищает предзаполненное поле (изначально содержит текущее имя) и вводит
"My renamed search", подтверждает кнопкой "Rename"

**Then** в Settings профиль отображается под новым именем "My renamed search", прежнее
имя "My saved search" в списке отсутствует
**And** при переходе на листинговую страницу и выборе "My renamed search" из фильтр-панели
страница обновляется тем же URL (`work_search[…]` параметры), что применялся бы под
старым именем ДО переименования — переименование меняет только отображаемое `name`,
`queryString` профиля остаётся неизменным (риск R-09: «сохранённый `queryString` теряется
или применяется не тот профиль» — этот кейс проверяет именно устойчивость `queryString`
к операции rename)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Имя профиля до | "My saved search" |
| Имя профиля после | "My renamed search" |
| queryString | `recording_builder.FILTER_APPLIED_QUERY_STRING` (неизменен) |

## Заметки для автоматизации
- Переиспользует фикстуру `filter_profile_applied_seeded` (conftest.py) — не требует новой
  фикстуры/сидинга/replay-записи, инфраструктура полностью готова (то же, что TC-041).
- Требует НОВОГО шага/локатора `rename_filter_profile(driver, old_name, new_name)` —
  по образцу уже существующего `settings_screen.py::_delete_button_locator`
  (XPath `following::` от текстового узла с именем профиля до ближайшего
  `content-desc="Rename"`, тот же приём disambiguation, что и для "Delete", см.
  комментарий в `settings_screen.py` строки 107-126). Не блокер — тот же класс
  работы, что уже сделан test-automator'ом для Delete в рамках TC-042.
- Диалог "Rename filter" предзаполняет поле ТЕКУЩИМ именем
  (`var dialogName by remember(filter.id) { mutableStateOf(filter.name) }`,
  SettingsScreen.kt) — шаг ввода должен очистить поле перед вводом нового имени
  (`clear()` + `send_keys`, не просто `send_keys` поверх), иначе получится
  конкатенация. Кнопка "Rename" задизейблена при пустом поле
  (`enabled = dialogName.isNotBlank()`).
- Для проверки "And" (URL после переименования) можно переиспользовать
  `browser_steps.assert_active_tab_url(driver, rb.LISTING_FILTERED_URL)` — тот же
  ассерт, что TC-041 использует ДО переименования.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область filter-profiles — CRUD над сохранёнными профилями, не комбинаторная
      область из банка C4 (фильтр/сортировка/рейтинг-видимость/backup/tabs/тема);
      строка `Инвариант:` не требуется (та же логика, что test-reviewer применил
      к TC-042 — CRUD-операция с одним элементом, не матрица).
