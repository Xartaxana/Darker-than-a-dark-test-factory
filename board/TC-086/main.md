---
key: "TC-086"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Переименование в имя, совпадающее с другим сохранённым профилем, — разрешено, оба queryString сохраняются раздельно"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:filter-profiles", "risk:R-09"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T01:07:11Z"
updated: "2026-07-20T01:07:11Z"
archived: false
resolution: null
---

# Переименование в имя, совпадающее с другим сохранённым профилем, — разрешено, оба queryString сохраняются раздельно

_Спроецировано из `test-cases/filter-profiles/TC-086.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-086 — Переименование в имя-дубликат не сливает и не теряет профили

## Предусловия
- Приложение запущено с чистыми данными, в Room засеяны 2 фильтр-профиля с разными
  именами и разными `queryString` через `two_filter_profiles_seeded`: "Profile A"
  (`queryString`: `work_search%5Bquery%5D=profile-a-test`) и "Profile B" (`queryString`:
  `work_search%5Bquery%5D=profile-b-test`) — сырое хранимое (URL-кодированное) значение,
  как его реально сеет фикстура (conftest.py) и возвращает `read_filter_profiles`.
- Открыт экран Settings, секция "Saved AO3 Filters" показывает оба профиля.

## Сценарий (Given-When-Then)

**Given** в Settings отображаются 2 сохранённых профиля с разными именами и разными
`queryString`: "Profile A" и "Profile B"

**When** пользователь нажимает "Rename" рядом с "Profile B", в диалоге очищает поле и
вводит имя "Profile A" (совпадающее с уже существующим профилем), подтверждает "Rename"

**Then** приложение НЕ показывает диалог ошибки/конфликта — операция завершается без
предупреждения (код не содержит проверки уникальности `name`, см. `requirements`)
**And** в Settings отображаются ДВЕ отдельные строки с именем "Profile A" (список не
схлопывается в одну запись, бывший "Profile B" не удалён и не потерян — это то самое
поведение, которого опасается R-09: «сохранённый `queryString` теряется или применяется
не тот профиль»)
**And** в БД приложения (`filter_profiles`, прочитано напрямую через `seed_db.read_filter_profiles()`
— host-side, не зависит от on-device sqlite3-бинаря, тот же приём, что
`backup_steps.assert_filter_profiles_match()` использует для этой же таблицы в TC-021 —
а не через UI, единственный способ различить две одноимённые строки) присутствуют ДВЕ записи с
`name = "Profile A"`: одна с исходным `queryString` первого профиля
(`work_search%5Bquery%5D=profile-a-test`), другая — с `queryString` бывшего "Profile B"
(`work_search%5Bquery%5D=profile-b-test`), НЕ изменившимся при переименовании — переименование
затронуло только поле `name` одной строки (по её `id`), `queryString` ни одной из двух
записей не пострадал и не перезаписал другой

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Profile A (не трогаем) | name="Profile A", queryString=`work_search%5Bquery%5D=profile-a-test` |
| Profile B → переименован | name было "Profile B" → "Profile A", queryString=`work_search%5Bquery%5D=profile-b-test` (неизменен) |

## Заметки для автоматизации
- Переиспользует существующую фикстуру `two_filter_profiles_seeded` (conftest.py) —
  без новой фикстуры/сидинга/replay-записи; queryString обеих записей — произвольные
  opaque-строки (как и в TC-042), навигация по ним не требуется, поэтому байт-в-байт
  соответствие recorded-flow не нужно.
- **Селекторы Settings по имени неоднозначны для этого кейса**:
  `settings_screen.py::has_filter_profile`/`delete_filter_profile` матчат
  `by_text(name)` — с двумя строками "Profile A" на экране такой локатор находит
  ПЕРВУЮ (в document order), не различая, какая именно. Это НЕ повод заводить
  test_debt-блокер: проверка "Then" рассчитана на прямое чтение `filter_profiles` через
  `seed_db.read_filter_profiles()` (host-side python-sqlite3, не зависит от
  on-device бинаря — та же таблица, что уже читает `backup_steps.assert_filter_profiles_match()`
  для TC-021). НЕ использовать `settings_steps.py::assert_no_ratings`/`assert_ratings_present`
  как образец — те деградируют к UI-фолбэку при отсутствии on-device sqlite3
  (`NOSQLITE → return`), что здесь дало бы молчаливый false-green: у TC-086 UI-фолбэка
  нет по построению (весь смысл — UI не различает дубликаты). Для "И" (2 строки в
  Settings) достаточно посчитать количество узлов `by_text("Profile A")`
  (`find_elements`, не `is_present`) — небольшое расширение `SettingsScreen`
  (метод, считающий совпадения), не блокер.
- Если позже потребуется автоматизировать ещё и клик "применить именно ЭТОТ
  дубликат из FilterPanel" (не входит в Then этого кейса) — `select_filter_option`/
  `filter_dropdown_has_option` (browser_screen.py) тоже матчат по `by_text(name)` и
  так же не различают дубликаты; понадобится позиционный локатор (XPath с индексом)
  или прямое чтение БД вместо клика. Этот кейс такого клика не требует (Then
  проверяет БД и список Settings, не выбор дубликата в панели), поэтому это
  заметка на будущее, не блокер текущего TC-086.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение (список Settings + данные БД), а не
      внутреннюю Compose-реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область filter-profiles — CRUD, не комбинаторная область банка C4; строка
      `Инвариант:` не требуется (как и для TC-042); Then тем не менее явно называет
      проверяемое свойство (два queryString не сливаются и не теряются при
      совпадении имён) — по существу то же, чего требует C4, просто без формального
      маркера, так как область вне банка.
