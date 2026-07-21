---
key: "TC-089"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p2"
summary: "Карточка Library показывает индикатор комментария и личных тегов сохранённой работы"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-10", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-21T10:31:08Z"
updated: "2026-07-21T10:31:08Z"
archived: false
resolution: "done"
---

# Карточка Library показывает индикатор комментария и личных тегов сохранённой работы

_Спроецировано из `test-cases/library/TC-089.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-089 — Индикатор комментария и тегов на карточке Library

## Предусловия
- Приложение запущено, режим replay допустим, но для этого кейса достаточно
  чистого состояния БЕЗ открытия листинга — только сидинг + экран Library.
- Работа W = `PENDING` засеяна ОДНИМ вызовом `seed_with_comment` с рейтингом
  Pending, непустым комментарием «Library indicator note» и непустым JSON-
  списком личных тегов `["indicator-tag"]` (новая фикстура, комбинирующая ОБА
  поля на одной работе — ни одна из существующих этого не делает:
  `note_work_seeded` не сидит `tags`, `disliked_work_with_tags_seeded` и
  `tagged_work_seeded` не сидят `comment`).

## Сценарий (Given-When-Then)

**Given** работа W (`PENDING`) засеяна с рейтингом Pending, комментарием
«Library indicator note» и личными тегами `["indicator-tag"]`

**When** пользователь открывает экран Library, вкладку PENDING

**Then** карточка работы W показывает note-иконку (`Icons.Outlined.EditNote`,
`contentDescription="View note"`) — индикатор наличия сохранённого
комментария
**And** та же карточка работы W показывает строку личных тегов
«indicator-tag» — индикатор наличия сохранённых тегов
(оба индикатора наблюдаются ОДНОВРЕМЕННО на одной и той же карточке — оба
поля происходят из одной и той же сохранённой строки `WorkRating`, точка
регресса модели: правка `comment`/`tags` в `WorkRating`/`Converters.kt`,
ломающая один из двух индикаторов, ловится именно здесь)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `framework/data/works.py::PENDING` (900000004), rating=PENDING, comment="Library indicator note", tags=["indicator-tag"] |

## Заметки для автоматизации
- Индикатор тегов — уже существующая ассерция `library_steps.assert_work_tags_visible`
  (`framework/steps/library_steps.py:54-62`, использует
  `LibraryScreen.has_tags_text`, `framework/screens/library_screen.py:45-46`)
  — переиспользовать напрямую, новый локатор не нужен.
- Индикатор комментария (note-иконка) — метода пока нет, нужен новый:
  `LibraryScreen.has_note_icon(timeout=...)` →
  `self.is_present(self.by_desc("View note"), timeout=...)`, по образцу уже
  существующих `has_download_icon`/`has_open_icon`
  (`framework/screens/library_screen.py:65-69`) — рутинная автоматизация того
  же семейства локаторов, не блокер.
- Новая фикстура `note_and_tags_work_seeded` — тривиальное расширение того же
  паттерна, что 4 соседних фикстуры (`framework/tests/conftest.py:281-335`):
  `app_steps.seed_with_comment([(W.PENDING, "PENDING", "Library indicator
  note", json.dumps(["indicator-tag"]))])`. Не блокер — тот же вызов уже
  используется 4 раза для других комбинаций полей.
- Реплей/сидинг-инфраструктура для `comment`/`tags` уже верифицирована
  (`bugs/AT-BUG-004.md`, Verified) — этот кейс не открывает листинговую
  страницу вообще (индикатор наблюдается сразу на Library), поэтому не
  зависит от replay-фикстуры листинга.
- Не дублирует TC-045 (личные теги не влияют на видимость — там же
  проверяется отображение тегов на карточке Library, но БЕЗ комментария и не
  как предмет кейса, а как побочное подтверждение сохранности): здесь
  предмет — сам факт индикации ОБОИХ полей одной карточкой, включая
  note-иконку, которую TC-045 не проверяет вовсе.

## Ревью автотеста

- **F1 пройдено** (test-reviewer, 2026-07-21). Архитектура: `arch_check.py` без
  [ERROR]; `has_note_icon`/`has_tags_text` — в `library_screen.py`, шаги в
  `library_steps`, sleep нет. Traceability: `@allure.id("TC-089")` == id,
  `@pytest.mark.p2` == priority, `automated_by` существует. Соответствие кейсу:
  не комбинаторная область; оба индикатора (note-иконка + строка тегов)
  проверяются на одной карточке PENDING-вкладки — оба из одной строки
  `WorkRating`. Замечание к охвату (не блокер): `has_note_icon`/`has_tags_text`
  — экранно-глобальные `by_desc`/`by_text_contains`, не привязаны к конкретной
  карточке; для этого кейса безопасно, т.к. фикстура сидит РОВНО одну работу
  (единственная карточка на вкладке). Фикстура `note_and_tags_work_seeded`
  сидит ДО Appium-сессии, комбинирует оба поля.
- **Зелёный прогон:** `Invoke-Pytest -k test_library_card_shows_note_icon_and_tags`
  → 1 passed (PYTEST_EXIT=0).
- **Красная проба (2026-07-21T10:31:08Z):** временно убрал comment из фикстуры
  `note_and_tags_work_seeded` (`"Library indicator note"` → `None`). Прогон УПАЛ
  осмысленно: карточка отрисовалась (has_work прошёл), но note-иконка исчезла —
  AssertionError «note-иконка не отображена на карточке «A Pending Test Work»».
  Откачено (`git checkout -- framework/tests/conftest.py`), дифф framework/ чист.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область не комбинаторная (единичное отображение поля) — строка `Инвариант:` не требуется
